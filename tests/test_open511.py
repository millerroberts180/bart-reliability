"""Synthetic tests for the 511 feasibility tooling. No network access and no real token."""

import csv
import io
import json
import zipfile

import duckdb
import pyarrow.parquet as pq
import pytest
import requests
import responses

from bart_reliability.open511.audit import audit, extract_bart_subset
from bart_reliability.open511.download import (
    DATAFEEDS_URL,
    Open511Error,
    download_historic,
    load_api_key,
    redact,
)
from bart_reliability.open511.extract import extract_subset
from bart_reliability.open511.ids import bart_route_short_name, bart_trip_id, gtfs_seconds

TOKEN = "test-token-0123456789abcdef"


def zip_bytes(files: dict[str, list[list[str]]], bom: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, rows in files.items():
            text = io.StringIO()
            csv.writer(text, lineterminator="\n").writerows(rows)
            archive.writestr(name, ("﻿" if bom else "") + text.getvalue())
    return buffer.getvalue()


# --- token handling ----------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [f"OPEN511_API_KEY={TOKEN}", f'OPEN511_API_KEY="{TOKEN}"', f"export OPEN511_API_KEY='{TOKEN}'"],
)
def test_load_api_key_from_env_file(tmp_path, monkeypatch, line):
    monkeypatch.delenv("OPEN511_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"# comment\nOTHER=1\n{line}\n")
    assert load_api_key(env) == TOKEN


def test_missing_key_error_never_contains_a_value(tmp_path, monkeypatch):
    monkeypatch.delenv("OPEN511_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OTHER=secret-value\n")
    with pytest.raises(Open511Error) as info:
        load_api_key(tmp_path / ".env")
    assert "secret-value" not in str(info.value)


def test_redact_removes_token_and_api_key_parameters():
    text = f"GET {DATAFEEDS_URL}?api_key={TOKEN}&operator_id=RG failed for {TOKEN}"
    out = redact(text, TOKEN)
    assert TOKEN not in out
    assert "api_key=<redacted>&operator_id=RG" in out


@responses.activate
def test_download_writes_archive_and_sanitized_provenance(tmp_path):
    body = zip_bytes({"agency.txt": [["agency_id"], ["BA"]]})
    responses.get(DATAFEEDS_URL, body=body, content_type="application/zip")
    provenance = download_historic(TOKEN, "RG", "2026-09-so", tmp_path)

    archive = tmp_path / "RG_2026-09-so.zip"
    assert archive.read_bytes() == body
    request_url = responses.calls[0].request.url
    assert "operator_id=RG" in request_url and "historic=2026-09-so" in request_url
    text = (tmp_path / "RG_2026-09-so.provenance.json").read_text()
    assert TOKEN not in text
    assert json.loads(text)["request_params"]["api_key"] == "<redacted>"
    assert "api_key=<redacted>" in provenance["final_url"]
    assert provenance["members"] == [{"name": "agency.txt", "size": 13}]
    assert not list(tmp_path.glob(".*part"))


@responses.activate
def test_download_errors_never_contain_the_token(tmp_path):
    responses.get(DATAFEEDS_URL, status=401, body=f"Invalid api_key={TOKEN}")
    with pytest.raises(Open511Error) as info:
        download_historic(TOKEN, "RG", "2026-09-so", tmp_path)
    assert TOKEN not in str(info.value)
    assert "401" in str(info.value)

    responses.replace(
        responses.GET,
        DATAFEEDS_URL,
        body=requests.ConnectionError(f"failed {DATAFEEDS_URL}?api_key={TOKEN}"),
    )
    with pytest.raises(Open511Error) as info:
        download_historic(TOKEN, "RG", "2026-09-so", tmp_path)
    assert TOKEN not in str(info.value)
    assert not list(tmp_path.iterdir())  # nothing partial left behind


@responses.activate
def test_download_rejects_non_zip_and_never_overwrites(tmp_path):
    responses.get(DATAFEEDS_URL, body=b"<html>maintenance</html>")
    with pytest.raises(Open511Error, match="not a ZIP"):
        download_historic(TOKEN, "RG", "2026-09-so", tmp_path)
    (tmp_path / "RG_2026-09-so.zip").write_bytes(b"existing")
    with pytest.raises(Open511Error, match="already exists"):
        download_historic(TOKEN, "RG", "2026-09-so", tmp_path)
    assert (tmp_path / "RG_2026-09-so.zip").read_bytes() == b"existing"


# --- extraction and identifiers ------------------------------------------------------


def test_extract_subset_filters_streams_and_keeps_strings(tmp_path):
    rows = [["trip_id", "stop_id", "agency_id"]]
    rows += [[f"BA:{i:07d}:20260930", "0900101", "BA"] for i in range(5)]
    rows += [["AC:1", "52268", "AC"], ["BA:9", "", "BA"]]
    path = tmp_path / "rg.zip"
    path.write_bytes(zip_bytes({"stop_observations.txt": rows}, bom=True))

    n = extract_subset(
        path, "stop_observations.txt", tmp_path / "o.parquet", "agency_id", equals="BA"
    )
    table = pq.read_table(tmp_path / "o.parquet")
    assert n == 6 == table.num_rows
    assert table.column_names == ["trip_id", "stop_id", "agency_id"]  # BOM stripped
    assert table.column("stop_id").to_pylist()[0] == "0900101"  # leading zero kept
    assert table.column("stop_id").to_pylist()[-1] is None  # blank -> null
    assert (
        extract_subset(
            path, "stop_observations.txt", tmp_path / "p.parquet", "trip_id", prefix="BA:00"
        )
        == 5
    )
    assert (
        extract_subset(
            path, "stop_observations.txt", tmp_path / "q.parquet", "trip_id", isin={"AC:1", "BA:9"}
        )
        == 2
    )
    with pytest.raises(ValueError, match="no column"):
        extract_subset(path, "stop_observations.txt", tmp_path / "r.parquet", "nope", equals="x")


def test_identifier_rules():
    assert bart_trip_id("BA:1965520:20260930") == "1965520"
    assert bart_trip_id("BA:389141710") == "389141710"  # ADDED trips have no suffix
    assert bart_trip_id("AC:-738754239") is None
    assert bart_route_short_name("BA:Blue-N") == "Blue-N"
    assert bart_route_short_name("AC:45") is None
    assert gtfs_seconds("26:42:55") == 96175
    assert gtfs_seconds(None) is None


# --- audit ---------------------------------------------------------------------------


@pytest.fixture
def audit_inputs(tmp_path):
    """One BART trip T1 with 4 stops; observations include an origin artifact,
    a single-observation trip, a duplicate with conflicting times, and an ADDED trip."""
    wh = tmp_path / "wh.duckdb"
    with duckdb.connect(str(wh)) as con:
        con.execute("CREATE TABLE static_trips AS SELECT * FROM (VALUES ('T1'), ('T2')) t(trip_id)")
        con.execute("""CREATE TABLE static_stops AS SELECT * FROM (VALUES
            ('A10-1', '900101'), ('A20-1', '900201'), ('A30-1', '900301'), ('A40-1', '900401'))
            t(stop_id, stop_code)""")
        con.execute("""CREATE TABLE static_stop_times AS SELECT * FROM (VALUES
            ('T1', 0, 'A10-1', '08:00:00', '08:00:00'), ('T1', 2, 'A20-1', '08:10:00', '08:10:00'),
            ('T1', 3, 'A30-1', '08:20:00', '08:20:00'), ('T1', 4, 'A40-1', '08:30:00', '08:30:00'),
            ('T2', 0, 'A10-1', '09:00:00', '09:00:00'), ('T2', 2, 'A20-1', '09:10:00', '09:10:00'))
            t(trip_id, stop_sequence, stop_id, arrival_time, departure_time)""")
    header = [
        "trip_id",
        "schedule_relationship",
        "service_date",
        "vehicle_id",
        "stop_sequence",
        "observed_arrival_time",
        "observed_departure_time",
        "uncertainty",
        "route_id",
        "agency_id",
        "to_stop_id",
        "scheduled_arrival_time",
    ]
    obs = [
        header,
        # T1: origin artifact 75 minutes late, then three real stops (one duplicated)
        [
            "BA:T1:20260930",
            "0",
            "20260901",
            "3-door",
            "0",
            "09:15:00",
            "09:15:00",
            "30",
            "BA:Blue-N",
            "BA",
            "900101",
            "08:00:00",
        ],
        [
            "BA:T1:20260930",
            "0",
            "20260901",
            "3-door",
            "2",
            "08:11:30",
            "08:11:30",
            "30",
            "BA:Blue-N",
            "BA",
            "900201",
            "08:10:00",
        ],
        [
            "BA:T1:20260930",
            "0",
            "20260901",
            "3-door",
            "3",
            "08:21:00",
            "08:21:00",
            "30",
            "BA:Blue-N",
            "BA",
            "900301",
            "08:20:00",
        ],
        [
            "BA:T1:20260930",
            "0",
            "20260901",
            "3-door",
            "3",
            "08:22:40",
            "08:22:40",
            "30",
            "BA:Blue-N",
            "BA",
            "900301",
            "08:20:00",
        ],
        [
            "BA:T1:20260930",
            "0",
            "20260901",
            "3-door",
            "4",
            "08:31:00",
            "08:31:00",
            "30",
            "BA:Blue-N",
            "BA",
            "900401",
            "08:30:00",
        ],
        # T2: only an origin observation
        [
            "BA:T2:20260930",
            "0",
            "20260901",
            "2-door",
            "0",
            "10:10:00",
            "10:10:00",
            "30",
            "BA:Blue-N",
            "BA",
            "900101",
            "09:00:00",
        ],
        # ADDED trip, not in the schedule
        [
            "BA:389141710",
            "1",
            "20260901",
            "3-door",
            "1",
            "11:00:00",
            "11:00:00",
            "30",
            "",
            "BA",
            "900201",
            "",
        ],
        # another agency, filtered out by extraction
        [
            "AC:1",
            "0",
            "20260901",
            "6105",
            "1",
            "11:00:00",
            "11:00:00",
            "0",
            "AC:45",
            "AC",
            "52268",
            "",
        ],
    ]
    regional = {
        "stop_observations.txt": obs,
        "routes.txt": [["route_id", "agency_id"], ["BA:Blue-N", "BA"], ["AC:45", "AC"]],
        "trips.txt": [
            ["route_id", "service_id", "trip_id"],
            ["BA:Blue-N", "BA:T1:20260930", "BA:T1:20260930"],
            ["BA:Blue-N", "BA:T2:20260930", "BA:T2:20260930"],
        ],
        "stop_times.txt": [
            ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"]
        ]
        + [
            [f"BA:{t}:20260930", code, str(seq), arr, arr]
            for t, seq, code, arr in [
                ("T1", 0, "900101", "08:00:00"),
                ("T1", 2, "900201", "08:10:00"),
                ("T1", 3, "900301", "08:20:00"),
                ("T1", 4, "900401", "08:30:00"),
                ("T2", 0, "900101", "09:00:00"),
                ("T2", 2, "900201", "09:10:00"),
            ]
        ],
        "calendar_dates.txt": [
            ["service_id", "date", "exception_type"],
            ["BA:T1:20260930", "20260901", "1"],
            ["BA:T2:20260930", "20260901", "1"],
            ["BA:T2:20260930", "20260902", "1"],
        ],
    }
    archive = tmp_path / "rg.zip"
    archive.write_bytes(zip_bytes(regional))
    bart_dir = tmp_path / "bart"
    return archive, bart_dir, wh


def test_audit_measures_coverage_matching_and_artifacts(audit_inputs):
    archive, bart_dir, wh = audit_inputs
    counts = extract_bart_subset(archive, bart_dir)
    assert counts["stop_observations"] == 7  # AC row excluded

    a = audit(bart_dir, wh, ("20260901", "20260930"))
    assert a["schedule_relationship"] == {"0": 6, "1": 1}
    assert a["matching"]["trip_exact"] == 0
    assert a["matching"]["trip_normalized"] == 6
    assert a["matching"]["stop_via_stop_code"] == 7
    assert a["matching"]["stop_time_and_stop_agree"] == 6
    assert a["regional_schedule_vs_bart"] == {"regional_stop_times": 6, "identical": 6}
    assert a["coverage"]["scheduled_trip_days"] == 3
    assert a["coverage"]["observed_trip_days"] == 2
    assert a["coverage"]["single_observation_trip_days"] == 1
    assert a["coverage"]["scheduled_stop_events"] == 8
    assert a["origin_artifact"]["origin_rows"] == 2
    # Usable: T1's non-origin rows only (T2 has a single, origin, observation).
    assert a["usable"]["rows"] == 4
    assert a["usable"]["trip_days"] == 1
    assert a["usable_ordering"] == {"consecutive_pairs": 3, "decreasing": 0, "equal": 0}
    assert a["duplicates"] == {"duplicate_keys": 1, "conflicting_times": 1, "max_spread_s": 100}


def test_audit_is_reproducible(audit_inputs):
    archive, bart_dir, wh = audit_inputs
    extract_bart_subset(archive, bart_dir)
    assert audit(bart_dir, wh, ("20260901", "20260930")) == audit(
        bart_dir, wh, ("20260901", "20260930")
    )
