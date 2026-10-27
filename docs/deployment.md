# Deploying the collector

Runs `bart-collect` as a systemd service on a small Ubuntu 24.04 server. Only the
collector runs there: no web server, database server, or open application port.
Collected snapshots stay on the server under the repository's git-ignored `data/`.

## Status: retired

Collection ended intentionally after a verified final backup, and the production server
(a DigitalOcean Droplet) was then retired. The steps below record how the collector was
deployed, so it can be deployed again for a new collection.

| Final backup | From its manifest, `data/raw/server_exports/2026-10-20/audit/export_manifest.json` |
|---|---|
| Export cutoff | 2026-10-20 19:40:00 UTC (12:40:00 PDT): every completed snapshot collected before it |
| Snapshots | 30,180 files (15,090 per feed), 385,325,199 bytes |
| Collected | 2026-10-10 08:11:07 UTC to 2026-10-20 19:39:23 UTC |
| Server inventory | 2026-10-20 19:43:43 to 19:44:06 UTC, read-only |
| Verified | The local copy's file count, sizes and SHA-256 match the manifest for all 30,180 files, and every file passes the project's validator |

- **Snapshots after the cutoff:** the inventory saw 8 more snapshots, 4 per feed,
  collected from 19:40:23 to 19:43:23 UTC. Like anything collected later, they were not
  exported and are not part of the project's data.
- **What depends on the server:** nothing now.
  - **The public site:** a static historical replay on GitHub Pages
    ([static_replay.md](static_replay.md)), with no server dependency.
  - **Processing, models and the local API:** all run from the local backup
    ([data_checkpoint_2026-10-20.md](data_checkpoint_2026-10-20.md)).

Replace `<server>` with your server's address. Run the server commands as root.

## Layout

| Path | Owner | Contents |
|---|---|---|
| `/opt/bart-reliability` | `bart` | Clone of this repository (read-only to the service) |
| `/opt/bart-reliability/.venv` | `bart` | Python virtual environment |
| `/opt/bart-reliability/data/raw/gtfs_rt/` | `bart` | Snapshots, `<feed>/<YYYY-MM-DD>/<HHMMSS>Z.pb` |
| `/opt/bart-reliability/logs/collector.log` | `bart` | JSON-lines log (also in the journal) |
| `/etc/systemd/system/bart-collector.service` | root | Copy of `deploy/systemd/bart-collector.service` |
| `/etc/logrotate.d/bart-collector` | root | Copy of `deploy/logrotate/bart-collector` |

## Install

```bash
# Packages: only the venv module is missing on a stock Ubuntu 24.04 image.
apt-get update && apt-get install -y --no-install-recommends python3-venv git

# Unprivileged system user with no login shell.
adduser --system --group --home /var/lib/bart --shell /usr/sbin/nologin bart

git clone https://github.com/millerroberts180/bart-reliability.git /opt/bart-reliability
mkdir -p /opt/bart-reliability/data /opt/bart-reliability/logs
chown -R bart:bart /opt/bart-reliability

cd /opt/bart-reliability
sudo -u bart git checkout <commit>      # optional: pin a reviewed commit instead of main
sudo -u bart -H python3 -m venv .venv
sudo -u bart -H env PIP_NO_CACHE_DIR=1 .venv/bin/pip install --upgrade pip
# constraints.txt pins every dependency to the versions verified in production.
sudo -u bart -H env PIP_NO_CACHE_DIR=1 .venv/bin/pip install -c deploy/constraints.txt .
sudo -u bart git rev-parse HEAD          # record the deployed commit

cp deploy/systemd/bart-collector.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/bart-collector.service
systemctl daemon-reload
systemctl enable --now bart-collector
```

The unit starts after the network is online, restarts 10 s after any crash with no
retry limit, and starts on boot. It runs as `bart` with a read-only filesystem except
`data/` and `logs/`, which must exist before the service starts.

Confirm the installed unit is the reviewed one:

```bash
sha256sum deploy/systemd/bart-collector.service /etc/systemd/system/bart-collector.service
```

## Log rotation

`logs/collector.log` is rotated daily, compressed, and kept for 14 rotations
(`collector.log-YYYYMMDD.gz`). The config uses `copytruncate` because the collector
holds the file open and never reopens it: installing or running logrotate never
signals or restarts the collector. Lines written in the instant between the copy
and the truncate can be lost from the file; the journal keeps every line. `su bart
bart` makes logrotate act as `bart`, since `logs/` is owned by `bart`.

```bash
install -o root -g root -m 0644 deploy/logrotate/bart-collector /etc/logrotate.d/bart-collector
logrotate -d /etc/logrotate.d/bart-collector     # dry run: changes nothing
systemctl list-timers logrotate.timer            # runs daily at 00:00 UTC
```

On its first run logrotate only records the new log in its state file, so the first
archive appears after the **second** daily run. Then `ls -l logs/` should show
`collector.log` (still mode 0640, owned by `bart`) and `collector.log-YYYYMMDD.gz`. To force a rotation for testing:
`logrotate -f /etc/logrotate.d/bart-collector`.

## Firewall

Allow SSH **before** enabling the firewall, then confirm a new SSH login still works
before closing your current session.

```bash
ufw allow OpenSSH
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
ufw status verbose        # expect only 22/tcp (v4 and v6) allowed in
```

The collector only makes outbound HTTPS requests to `api.bart.gov`.

## Operate

```bash
systemctl status bart-collector
journalctl -u bart-collector -f                     # live JSON log
journalctl -u bart-collector -o cat | grep -E '"level": "(WARNING|ERROR)"'
find /opt/bart-reliability/data/raw/gtfs_rt -name '*.pb' | wc -l
du -sh /opt/bart-reliability/data
systemctl restart bart-collector                    # after config or code changes
```

Check snapshots with the project's validator:

```bash
cd /opt/bart-reliability
sudo -u bart .venv/bin/python -c "
import pathlib
from bart_reliability.collector.validate import validate_feed
files = sorted(pathlib.Path('data/raw/gtfs_rt').rglob('*.pb'))
for p in files:
    validate_feed(p.read_bytes())  # raises ValidationError on a bad file
print(len(files), 'snapshots valid')"
```

### Update to a new version

```bash
cd /opt/bart-reliability
sudo -u bart git pull --ff-only
sudo -u bart -H env PIP_NO_CACHE_DIR=1 .venv/bin/pip install -c deploy/constraints.txt .
install -m 0644 deploy/systemd/bart-collector.service /etc/systemd/system/
install -m 0644 deploy/logrotate/bart-collector /etc/logrotate.d/
systemctl daemon-reload
systemctl restart bart-collector
```

Run git as `bart`: as root, git refuses a repository owned by another user.

### Copy data off the server

```bash
rsync -av --exclude '.*' <user>@<server>:/opt/bart-reliability/data/raw/gtfs_rt/ \
    data/raw/server_exports/<YYYY-MM-DD>/gtfs_rt/
```

`--exclude '.*'` skips a snapshot that is mid-write. Filenames never collide, so
repeated syncs only add new snapshots. To verify a copy, compare
`find . -name '*.pb' | wc -l` and `sha256sum` output on both sides. While the
collector runs, list the files on the server first and compare exactly that list.

## Known limitations

- **Logs are written twice**, to the journal and to `logs/collector.log` (rotated as
  above). The journal is bounded by journald's own size limits.
- **Stopping the service** (`systemctl stop`, reboot) ends the process with SIGTERM.
  The missed interval appears as a gap in `cycle_complete` events, not as a
  `collector_stopped` event.
- **Disk:** snapshots are uncompressed protobuf, roughly 40 KB per trip-update file at
  daytime service levels, about 2.4 MB per hour and up to ~60 MB per day. Directory
  overhead (4 KB blocks per small file) adds to that. Watch `du`.
- **Single server:** if the server itself is down, intervals are missed. Restarts
  catch up on the fixed 60 s schedule; they never backfill.
- **Automatic security updates.** Ubuntu's unattended upgrades run daily, and
  `needrestart` restarts services that use an upgraded library. This happened once
  during the 24-hour test (an OpenSSL update) and cost no interval; see
  [collection_validation.md](collection_validation.md). Through the 10.5-day checkpoint it
  stayed the only automatic restart. Kernel updates need a reboot instead, and automatic reboot is
  off: one was pending on 2026-10-20
  ([data_checkpoint_2026-10-20.md](data_checkpoint_2026-10-20.md)). To keep the collector from being restarted
  automatically, for example during a timed test:
  `echo '$nrconf{override_rc}{qr(^bart-collector\.service$)} = 0;' > /etc/needrestart/conf.d/bart-collector.conf`.
  Then restart it yourself after security updates.
- **SSH as root.** These steps assume key-only root SSH (Ubuntu's DigitalOcean
  default). For a longer-lived server, add a sudo user and set `PermitRootLogin no`.
