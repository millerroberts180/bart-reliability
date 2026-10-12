"""Download a 511 historical GTFS archive without ever exposing the API token.

The token is read from a local, git-ignored .env file and sent only as a request
parameter. It never appears in command-line arguments, logs, error messages, or the
provenance file written next to the archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import requests

from bart_reliability.collector.logging_setup import configure_logging

logger = logging.getLogger(__name__)

DATAFEEDS_URL = "https://api.511.org/transit/datafeeds"
ENV_VAR = "OPEN511_API_KEY"
REDACTED = "<redacted>"
USER_AGENT = "bart-reliability-lab/0.1 (research)"


class Open511Error(RuntimeError):
    """Raised for configuration or download failures. Messages never contain the token."""


def load_api_key(env_path: Path = Path(".env"), var: str = ENV_VAR) -> str:
    """Return the token from `var` in a .env file (or the environment as a fallback)."""
    value = None
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, raw = line.partition("=")
            if key.strip().removeprefix("export ").strip() == var:
                value = raw.strip().strip("'\"")
    value = value or os.environ.get(var)
    if not value:
        raise Open511Error(f"{var} is not set in {env_path} or the environment")
    return value


def redact(text: str, secret: str) -> str:
    """Remove the secret, and any api_key query value, from text."""
    if secret:
        text = text.replace(secret, REDACTED)
    return re.sub(r"(api_key=)[^&\s'\"]+", rf"\1{REDACTED}", text)


def download_historic(
    api_key: str,
    operator_id: str,
    historic: str,
    out_dir: Path,
    session: requests.Session | None = None,
    timeout: float = 600,
) -> dict:
    """Stream the archive to out_dir/<operator>_<historic>.zip and write provenance.

    Never overwrites an existing archive. Returns the provenance dict.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{operator_id}_{historic}.zip"
    if target.exists():
        raise Open511Error(f"{target} already exists; not overwriting")

    session = session or requests.Session()
    params = {"api_key": api_key, "operator_id": operator_id, "historic": historic}
    retrieved_at = datetime.now(UTC)
    fd, tmp_name = tempfile.mkstemp(dir=out_dir, prefix=".", suffix=".part")
    digest = hashlib.sha256()
    size = 0
    try:
        try:
            with session.get(
                DATAFEEDS_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                stream=True,
                timeout=timeout,
            ) as response:
                status = response.status_code
                headers = {
                    k: response.headers.get(k)
                    for k in ("Content-Type", "Content-Length", "Last-Modified", "ETag")
                    if response.headers.get(k)
                }
                if status != 200:
                    body = response.text[:300]
                    raise Open511Error(f"511 returned HTTP {status}: {redact(body, api_key)}")
                with os.fdopen(fd, "wb") as f:
                    fd = None
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                final_url = redact(response.url, api_key)
        except requests.RequestException as e:
            raise Open511Error(f"511 request failed: {redact(str(e), api_key)}") from None

        if not zipfile.is_zipfile(tmp_name):
            raise Open511Error("511 response is not a ZIP archive")
        os.link(tmp_name, target)
    finally:
        if fd is not None:
            os.close(fd)
        Path(tmp_name).unlink(missing_ok=True)

    with zipfile.ZipFile(target) as archive:
        members = [{"name": i.filename, "size": i.file_size} for i in archive.infolist()]
    provenance = {
        "source": DATAFEEDS_URL,
        "request_params": {"operator_id": operator_id, "historic": historic, "api_key": REDACTED},
        "final_url": final_url,
        "retrieved_at": retrieved_at.isoformat(timespec="seconds"),
        "http_status": status,
        "response_headers": headers,
        "archive": target.name,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "members": members,
    }
    text = json.dumps(provenance, indent=1)
    if api_key in text:  # defensive: provenance must never hold the token
        raise Open511Error("refusing to write provenance containing the API token")
    target.with_suffix(".provenance.json").write_text(text + "\n")
    return provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download a 511 historical GTFS archive.")
    parser.add_argument("--operator-id", default="RG")
    parser.add_argument("--historic", required=True, help="e.g. 2026-09-so")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    configure_logging(None)
    try:
        key = load_api_key(args.env_file)
        provenance = download_historic(key, args.operator_id, args.historic, args.out_dir)
    except Open511Error as e:
        logger.error("open511_download_failed", extra={"fields": {"reason": str(e)}})
        return 2
    summary = {k: provenance[k] for k in ("archive", "bytes", "sha256", "retrieved_at")}
    logger.info("open511_download_complete", extra={"fields": summary})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
