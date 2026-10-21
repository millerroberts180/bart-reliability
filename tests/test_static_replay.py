"""Static replay export, tested on the synthetic replay that tests/test_local_api.py uses.

The warehouse and bundle are built the same way, and the website contract checks come
from that module. Nothing touches the network.
"""

import json
import re
import shutil
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from modeling_fixtures import DAYS, build_synthetic_warehouse, local, synthetic_config
from test_local_api import AS_OF, api_config, conforms, held

import bart_reliability.static_replay.export as static_export
from bart_reliability.api.app import create_app
from bart_reliability.api.config import load_api_config
from bart_reliability.api.replay import ReplayEngine
from bart_reliability.serving.bundle import build_bundle
from bart_reliability.serving.config import load_bundle_config
from bart_reliability.serving.schema import sha256_file
from bart_reliability.static_replay.contract import KEEP, NESTED, api_fields, future_times, project
from bart_reliability.static_replay.export import (
    MANIFEST,
    ExportError,
    ExportSpec,
    board_file,
    encode_manifest,
    export_replay,
    history_file,
    load_export_spec,
    read_manifest,
    verify_export,
)
from bart_reliability.static_replay.main import main as cli

REPO = Path(__file__).resolve().parents[1]
DECODER = REPO / "web" / "src" / "data" / "apiDecode.ts"


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    return build_synthetic_warehouse(tmp_path_factory.mktemp("wh"), with_stations=True)


@pytest.fixture(scope="module")
def bundle(warehouse, tmp_path_factory):
    root = tmp_path_factory.mktemp("bundle")
    cfg = replace(
        load_bundle_config(), output_dir=root / "bundle", min_calibration_examples_per_horizon=5
    )
    return build_bundle(warehouse, synthetic_config(root / "run"), cfg)


def spec_for(warehouse, bundle, out: Path, **overrides) -> ExportSpec:
    snapshot = ReplayEngine(warehouse, AS_OF, 21600).snapshot
    spec = ExportSpec(
        as_of=AS_OF,
        source_feed_timestamp=snapshot.feed_timestamp,
        model_version=bundle.metadata["model"]["version"],
        bundle_id=bundle.metadata["bundle_id"],
        warehouse_sha256=sha256_file(warehouse),
        output_dir=out,
    )
    return replace(spec, **overrides)


@pytest.fixture(scope="module")
def exported(warehouse, bundle, tmp_path_factory):
    config = api_config(warehouse, bundle.bundle_dir)
    spec = spec_for(warehouse, bundle, tmp_path_factory.mktemp("export"))
    return export_replay(config, spec), config, spec


def files_of(export_dir: Path) -> dict[str, bytes]:
    return {
        p.relative_to(export_dir).as_posix(): p.read_bytes()
        for p in sorted(export_dir.rglob("*"))
        if p.is_file()
    }


def copy_of(exported, tmp_path) -> Path:
    target = tmp_path / exported[0].out_dir.name
    shutil.copytree(exported[0].out_dir, target)
    return target


def rewrite(export_dir: Path, rel: str, data: bytes) -> None:
    """Change a file and update the manifest to match, so only parity can notice."""
    (export_dir / rel).write_bytes(data)
    manifest = json.loads((export_dir / MANIFEST).read_bytes())
    manifest["files"][rel] |= {
        "bytes": len(data),
        "sha256": static_export.hashlib.sha256(data).hexdigest(),
    }
    (export_dir / MANIFEST).write_bytes(encode_manifest(manifest))


# -- what is exported ------------------------------------------------------------------


def test_every_request_the_website_can_make_has_one_file(exported):
    result, _, spec = exported
    client = TestClient(create_app(exported[1]))
    expected = {"health.json", "model.json", "stations.json"}
    for station in client.get("/api/v1/stations").json():
        for group in station["boardingGroups"]:
            expected.add(board_file(station["id"], group["id"]))
            board = client.get(
                f"/api/v1/stations/{station['id']}/predictions",
                params={"boarding_group": group["id"]},
            ).json()
            expected |= {history_file(t["predictionId"]) for t in board["trains"]}
    files = files_of(result.out_dir)
    assert set(files) - {MANIFEST} == expected
    assert result.out_dir.name == f"v1-{AS_OF:%Y%m%dT%H%M%SZ}"
    assert result.parity.ok and result.parity.identical == len(expected)
    counts = result.manifest["counts"]
    assert counts["files"] == len(expected) and counts["trains"] == counts["historyFiles"] > 0
    assert sum(counts["trainsByStatus"].values()) == counts["trains"]


def test_files_are_the_api_answers_reduced_to_what_the_website_reads(exported):
    """Asked again over HTTP, the API's answer reduced to the kept fields equals each file,
    and every file satisfies the website's TypeScript contract."""
    result, config, _ = exported
    client = TestClient(create_app(config))
    files = {k: json.loads(v) for k, v in files_of(result.out_dir).items() if k != MANIFEST}

    def check(rel, model, response):
        assert response.status_code == 200
        problems = []
        assert files[rel] == project(model, response.json(), rel, problems)
        assert problems == []
        return files[rel]

    conforms("HealthStatus", check("health.json", "HealthStatus", client.get("/api/v1/health")))
    conforms(
        "ModelMetadata", check("model.json", "ModelMetadata", client.get("/api/v1/model/metadata"))
    )
    for station in check("stations.json", "Station", client.get("/api/v1/stations")):
        conforms("Station", station)
        for group in station["boardingGroups"]:
            conforms("BoardingGroup", group)
            rel = board_file(station["id"], group["id"])
            board = check(
                rel,
                "PredictionResponse",
                client.get(
                    f"/api/v1/stations/{station['id']}/predictions",
                    params={"boarding_group": group["id"]},
                ),
            )
            conforms("PredictionResponse", board)
            conforms("ModelMetadata", board["model"])
            assert board["dataMode"] == "historical_replay"
            assert board["replay"] == {"asOf": AS_OF.strftime("%Y-%m-%dT%H:%M:%SZ")}
            for train in board["trains"]:
                conforms("TrainPrediction", train)
                if train["revisionInterval"]:
                    conforms("RevisionInterval", train["revisionInterval"])
                pid = train["predictionId"]
                history = check(
                    history_file(pid),
                    "PredictionHistoryPoint",
                    client.get(f"/api/v1/predictions/{pid}/history"),
                )
                for point in history:
                    conforms("PredictionHistoryPoint", point)
            for alert in board["alerts"]:
                conforms("AlertContext", alert)


def test_files_hold_only_the_kept_fields(exported):
    def walk(model, value):
        if isinstance(value, list):
            for item in value:
                walk(model, item)
        elif isinstance(value, dict):
            assert list(value) == [f for f in api_fields(model) if f in KEEP[model]]
            for key, item in value.items():
                if (model, key) in NESTED:
                    walk(NESTED[(model, key)], item)

    models = {"health": "HealthStatus", "model": "ModelMetadata", "stations": "Station"}
    models |= {"boards": "PredictionResponse", "history": "PredictionHistoryPoint"}
    for rel, data in files_of(exported[0].out_dir).items():
        if rel != MANIFEST:
            walk(models[rel.split("/")[0].removesuffix(".json")], json.loads(data))


def test_kept_fields_are_exactly_what_the_website_decoder_reads():
    """KEEP must follow web/src/data/apiDecode.ts: a field the website reads cannot be
    missing from the export, and a field it never reads is not published."""
    source = DECODER.read_text()
    variables = {
        "s": "Station",
        "g": "BoardingGroup",
        "i": "RevisionInterval",
        "t": "TrainPrediction",
        "a": "AlertContext",
        "m": "ModelMetadata",
        "r": "PredictionResponse",
        "p": "PredictionHistoryPoint",
        "h": "HealthStatus",
    }
    reads = {model: set() for model in KEEP}
    for var, name in re.findall(r"\b([sgitamrph])\.([a-z][A-Za-z]+)\b", source):
        reads[variables[var]].add(name)
    # provenance() reads the data mode of every object body, then replay.asOf on a board
    # and asOf on the health response.
    assert "body.dataMode" in source and "object(body.replay, `${path}.replay`).asOf" in source
    assert ": body.asOf" in source
    reads["PredictionResponse"] |= {"dataMode", "replay"}
    reads["HealthStatus"] |= {"dataMode", "asOf"}
    reads["ReplayInfo"] |= {"asOf"}
    assert {m: set(fields) for m, fields in KEEP.items()} == reads


# -- determinism and no future data ----------------------------------------------------


def test_two_exports_from_the_same_inputs_are_byte_identical(exported, tmp_path):
    result, config, spec = exported
    again = export_replay(config, spec, tmp_path)
    assert again.out_dir != result.out_dir
    assert files_of(again.out_dir) == files_of(result.out_dir)


def test_export_does_not_depend_on_anything_after_as_of(exported, bundle, tmp_path):
    """Holding a train after as_of changes the warehouse, not one exported byte."""
    result, _, spec = exported
    held_db = build_synthetic_warehouse(tmp_path / "wh", perturb=held, with_stations=True)
    held_sha = sha256_file(held_db)
    assert held_sha != spec.warehouse_sha256
    other = export_replay(
        api_config(held_db, bundle.bundle_dir),
        replace(spec, warehouse_sha256=held_sha),
        tmp_path / "out",
    )
    a, b = files_of(result.out_dir), files_of(other.out_dir)
    assert {k: v for k, v in a.items() if k != MANIFEST} == {
        k: v for k, v in b.items() if k != MANIFEST
    }
    ma, mb = json.loads(a[MANIFEST]), json.loads(b[MANIFEST])
    assert mb["provenance"]["warehouse"]["sha256"] == held_sha
    # Each synthetic build writes its schedule ZIP with the build time inside, so only
    # the archive hash differs there; the real export pins one warehouse.
    for m in (ma, mb):
        m["provenance"]["warehouse"].pop("sha256")
        for schedule in m["provenance"]["staticSchedule"]:
            schedule.pop("archiveSha256")
    assert ma == mb


def test_observed_times_after_as_of_are_flagged():
    as_of = AS_OF
    later = (as_of + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now = as_of.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert future_times({"feedTimestamp": now, "currentEtaAt": later}, as_of) == []
    assert (
        future_times({"trains": [{"currentEtaAt": later, "likelyFinalEtaAt": later}]}, as_of) == []
    )
    assert future_times([{"feedTimestamp": later}], as_of) == [
        f"$[0].feedTimestamp: {later} is after the replay time"
    ]
    assert future_times({"alerts": [{"visibleSince": later}]}, as_of)
    assert future_times({"replay": {"collectedAt": later}}, as_of)
    assert future_times({"arrivedAt": now}, as_of) == ["$.arrivedAt: unclassified time field"]
    assert future_times({"asOf": "2026-10-09 08:16"}, as_of) == [
        "$.asOf: not a timestamp with a time zone"
    ]


def test_an_answer_with_a_future_observation_is_not_exported(exported, monkeypatch, tmp_path):
    _, config, spec = exported
    real = static_export._ask_everything

    async def with_future_alert(app):
        answers = await real(app)
        board = next(a for a in answers if a.model == "PredictionResponse")
        board.body["alerts"] = [
            {
                "alertId": "x",
                "scope": "system",
                "category": "unclassified",
                "headerText": "",
                "descriptionText": None,
                "visibleSince": (spec.as_of + timedelta(minutes=1)).isoformat(),
            }
        ]
        return answers

    monkeypatch.setattr(static_export, "_ask_everything", with_future_alert)
    with pytest.raises(ExportError, match="after the replay time"):
        export_replay(config, spec, tmp_path)
    assert list(tmp_path.iterdir()) == []


# -- pins and health ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("as_of", AS_OF + timedelta(minutes=1), "is not the pinned"),
        ("source_feed_timestamp", AS_OF - timedelta(minutes=5), "replay snapshot"),
        ("model_version", "9.9.9+000000000000", "model"),
        ("bundle_id", "0" * 64, "not healthy"),
        ("warehouse_sha256", "f" * 64, "warehouse SHA-256"),
    ],
)
def test_every_input_must_match_its_pin(warehouse, bundle, tmp_path, field, value, message):
    spec = spec_for(warehouse, bundle, tmp_path, **{field: value})
    with pytest.raises(ExportError, match=message):
        export_replay(api_config(warehouse, bundle.bundle_dir), spec)
    assert list(tmp_path.iterdir()) == []


def test_a_config_pinning_another_bundle_is_refused(warehouse, bundle, tmp_path):
    config = api_config(warehouse, bundle.bundle_dir, bundle_id="1" * 64)
    with pytest.raises(ExportError, match="different bundle_id"):
        export_replay(config, spec_for(warehouse, bundle, tmp_path))


def test_an_in_sample_replay_is_not_exported(warehouse, bundle, tmp_path):
    inside = local(DAYS[2], 8, 16, 30)  # before the bundle's calibration cutoff
    config = api_config(warehouse, bundle.bundle_dir, as_of=inside)
    spec = spec_for(warehouse, bundle, tmp_path, as_of=inside)
    with pytest.raises(ExportError, match="not healthy.*inside the data this model used"):
        export_replay(config, spec)
    assert list(tmp_path.iterdir()) == []


# -- verification, missing files and damaged manifests ----------------------------------


def test_verify_finds_no_difference_in_an_untouched_export(exported):
    result, config, spec = exported
    report = verify_export(result.out_dir, config, spec)
    assert report.ok
    assert report.differences == report.missing == report.extra == []
    assert report.identical == report.requests == result.manifest["counts"]["files"]


def test_verify_reports_a_changed_answer(exported, tmp_path):
    export_dir = copy_of(exported, tmp_path)
    boards = [r for r in read_manifest(export_dir)["files"] if r.startswith("boards/")]
    rel = next(r for r in boards if json.loads((export_dir / r).read_bytes())["trains"])
    board = json.loads((export_dir / rel).read_bytes())
    eta = board["trains"][0]["currentEtaSeconds"]
    board["trains"][0]["currentEtaSeconds"] = eta + 60
    rewrite(export_dir, rel, json.dumps(board, separators=(",", ":")).encode())
    report = verify_export(export_dir, *exported[1:])
    assert not report.ok and not report.manifest_identical
    assert report.differences == [f"{rel}: $.trains[0].currentEtaSeconds: {eta + 60} != {eta}"]
    assert report.identical == report.requests - 1


def test_a_missing_file_is_reported(exported, tmp_path):
    export_dir = copy_of(exported, tmp_path)
    manifest = read_manifest(export_dir)
    rel = next(r for r in manifest["files"] if r.startswith("history/"))
    (export_dir / rel).unlink()
    with pytest.raises(ExportError, match=f"{re.escape(rel)}: listed but missing"):
        read_manifest(export_dir)
    # Removed from the manifest too, the gap is still found: the API answers that request.
    del manifest["files"][rel]
    manifest["counts"]["files"] -= 1
    (export_dir / MANIFEST).write_bytes(encode_manifest(manifest))
    report = verify_export(export_dir, *exported[1:])
    assert not report.ok and report.missing == [rel]


def _corrupt(name):
    def mutate(export_dir: Path):
        path = export_dir / MANIFEST
        manifest = json.loads(path.read_bytes())
        first = next(iter(manifest["files"]))
        if name == "not JSON":
            path.write_bytes(b'{"schemaVersion": ')
            return
        if name == "no manifest":
            path.unlink()
            return
        if name == "unlisted file":
            (export_dir / "boards" / "extra.json").write_bytes(b"{}")
            return
        if name == "missing key":
            del manifest["counts"]
        elif name == "extra key":
            manifest["generatedOn"] = "today"
        elif name == "wrong type":
            manifest["files"] = []
        elif name == "other schema version":
            manifest["schemaVersion"] = "static-replay-2"
        elif name == "not historical replay":
            manifest["dataMode"] = "live"
        elif name == "path outside the export":
            manifest["files"]["../outside.json"] = manifest["files"].pop(first)
        elif name == "malformed entry":
            manifest["files"][first]["sha256"] = "abc"
        elif name == "wrong size":
            manifest["files"][first]["bytes"] += 1
        elif name == "wrong hash":
            manifest["files"][first]["sha256"] = "0" * 64
        elif name == "wrong file count":
            manifest["counts"]["files"] += 1
        path.write_bytes(encode_manifest(manifest))

    return mutate


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("not JSON", "not valid JSON"),
        ("no manifest", "no manifest.json"),
        ("missing key", "exactly the keys"),
        ("extra key", "exactly the keys"),
        ("wrong type", "wrong type"),
        ("other schema version", "unsupported schemaVersion"),
        ("not historical replay", "historical_replay"),
        ("path outside the export", "not a path an export contains"),
        ("malformed entry", "malformed entry"),
        ("wrong size", "manifest says"),
        ("wrong hash", "SHA-256 differs"),
        ("wrong file count", "counts.files"),
        ("unlisted file", "boards/extra.json: not in the manifest"),
    ],
)
def test_a_damaged_manifest_is_rejected(exported, tmp_path, damage, message):
    export_dir = copy_of(exported, tmp_path)
    _corrupt(damage)(export_dir)
    with pytest.raises(ExportError, match=message):
        read_manifest(export_dir)
    with pytest.raises(ExportError, match=message):
        verify_export(export_dir, *exported[1:])


# -- atomic writes, paths and the repository spec ----------------------------------------


def test_a_failed_export_leaves_the_previous_one_untouched(exported, monkeypatch, tmp_path):
    result, config, spec = exported
    previous = copy_of(exported, tmp_path)
    before = files_of(previous)
    failing = static_export.ParityReport(requests=1, differences=["x: changed"])
    monkeypatch.setattr(static_export, "verify_export", lambda *a: failing)
    with pytest.raises(ExportError, match="parity check failed"):
        export_replay(config, spec, tmp_path)
    assert files_of(previous) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [previous.name]


def test_a_new_export_replaces_the_previous_one_whole(exported, tmp_path):
    result, config, spec = exported
    previous = copy_of(exported, tmp_path)
    (previous / "boards" / "stale.json").write_bytes(b"{}")
    again = export_replay(config, spec, tmp_path)
    assert again.out_dir == previous
    assert files_of(previous) == files_of(result.out_dir)
    assert sorted(p.name for p in tmp_path.iterdir()) == [previous.name]


def test_ids_become_paths_only_when_safe():
    assert board_file("MONT", "to-EMBR") == "boards/MONT/to-EMBR.json"
    assert history_file("2026-10-20:1965254:11") == "history/2026-10-20_1965254_11.json"
    for bad in (("../x", "to-A"), ("MONT", "to/A"), ("MONT", "")):
        with pytest.raises(ExportError, match="not safe"):
            board_file(*bad)
    for bad in ("2026-10-20:a_b:3", "2026-10-20:a/b:3", "2026-10-20:x:y", "no-colons"):
        with pytest.raises(ExportError):
            history_file(bad)


def test_export_holds_no_paths_or_server_details(exported, warehouse, bundle):
    result, config, _ = exported
    private = [
        str(warehouse.parent),
        str(bundle.bundle_dir),
        str(result.out_dir.parent),
        str(Path.home()),
        "127.0.0.1",
        "localhost",
        ".building",
    ]
    for rel, data in files_of(result.out_dir).items():
        text = data.decode()
        assert not [p for p in private if p in text], rel
    assert result.manifest["provenance"]["warehouse"] == {
        "file": warehouse.name,
        "sha256": sha256_file(warehouse),
    }


def test_repository_spec_pins_the_october_20_replay():
    spec = load_export_spec()
    api = load_api_config()
    assert spec.as_of == api.as_of
    assert spec.as_of.isoformat() == "2026-10-20T17:00:00+00:00"
    assert spec.source_feed_timestamp.isoformat() == "2026-10-20T16:59:23+00:00"
    assert spec.model_version == "0.2.0+886fcd260732"
    assert spec.bundle_id == api.bundle_id
    assert spec.bundle_id == "db2382848a9ff29a298aa6d320623daf532ac4d813475bf30a8e052e84ed6087"
    assert spec.warehouse_sha256 == (
        "19dd5cfc686bed4f223adbfe5c5d26ef8385e5d1a152da5aa2be7af9378e55cc"
    )
    assert spec.name == "v1-20261020T170000Z"
    # The generated export stays out of Git.
    assert "data/static_replay/" in (REPO / ".gitignore").read_text().splitlines()


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace('model_version = "0.2.0+886fcd260732"\n', ""), "missing keys"),
        (lambda s: s + 'extra = "x"\n', "unknown keys"),
        (lambda s: s.replace("db2382848a9ff29a", "db23"), "bundle_id must be"),
        (lambda s: s.replace("19dd5cfc686bed4f", "19dd"), "warehouse_sha256 must be"),
        (lambda s: s.replace("2026-10-20T16:59:23Z", "2026-10-20T17:00:01Z"), "after as_of"),
        (lambda s: s.replace("2026-10-20T16:59:23Z", "yesterday"), "source_feed_timestamp"),
        (lambda s: s.replace("2026-10-20T17:00:00Z", "2026-10-20T17:00:00"), "as_of"),
    ],
)
def test_spec_values_are_checked(tmp_path, edit, message):
    path = tmp_path / "spec.toml"
    path.write_text(edit((REPO / "config" / "static_replay.toml").read_text()))
    with pytest.raises(ExportError, match=message):
        load_export_spec(path)


def test_command_line_exports_and_verifies(exported, warehouse, bundle, tmp_path, capsys):
    _, config, spec = exported
    api_toml = (REPO / "config" / "local_api.toml").read_text()
    for key, value in {
        "as_of": spec.as_of.isoformat(),
        "warehouse": str(warehouse),
        "bundle": str(bundle.bundle_dir),
        "bundle_id": spec.bundle_id,
    }.items():
        api_toml = re.sub(rf'(?m)^{key} = ".*"$', f'{key} = "{value}"', api_toml)
    spec_toml = "\n".join(
        [
            f'as_of = "{spec.as_of.isoformat()}"',
            f'source_feed_timestamp = "{spec.source_feed_timestamp.isoformat()}"',
            f'model_version = "{spec.model_version}"',
            f'bundle_id = "{spec.bundle_id}"',
            f'warehouse_sha256 = "{spec.warehouse_sha256}"',
            f'output_dir = "{tmp_path / "out"}"',
        ]
    )
    (tmp_path / "api.toml").write_text(api_toml)
    (tmp_path / "spec.toml").write_text(spec_toml)
    args = ["--spec", str(tmp_path / "spec.toml"), "--api-config", str(tmp_path / "api.toml")]

    assert cli(["export", *args]) == 0
    summary = json.loads(capsys.readouterr().out)
    export_dir = Path(summary["export"])
    assert export_dir == tmp_path / "out" / spec.name
    assert summary["parity"]["ok"] and summary["parity"]["differences"] == []
    assert summary["sizes"]["total"]["files"] == summary["counts"]["files"]
    assert summary["sizes"]["firstView"]["files"][:2] == ["health.json", "stations.json"]

    assert cli(["verify", *args]) == 0
    assert json.loads(capsys.readouterr().out)["parity"]["identical"] == summary["counts"]["files"]
    rewrite(export_dir, "model.json", b'{"modelVersion":"x"}')
    assert cli(["verify", str(export_dir), *args]) == 1
    assert json.loads(capsys.readouterr().out)["parity"]["differences"]
    (export_dir / MANIFEST).write_bytes(b"[]")
    assert cli(["verify", str(export_dir), *args]) == 1
    assert "exactly the keys" in json.loads(capsys.readouterr().out)["error"]
    assert cli(["export", "--spec", str(tmp_path / "missing.toml")]) == 2
