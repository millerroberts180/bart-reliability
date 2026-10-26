"""The published static replay (web/public/replay): publishing, and the offline check that
CI and the Pages workflow run without the warehouse or the bundle."""

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from modeling_fixtures import build_synthetic_warehouse, synthetic_config
from test_local_api import api_config
from test_static_replay import spec_for

from bart_reliability.serving.bundle import build_bundle
from bart_reliability.serving.config import load_bundle_config
from bart_reliability.static_replay.check import INDEX, check_public, publish, read_index
from bart_reliability.static_replay.export import (
    MANIFEST,
    ExportError,
    encode,
    encode_manifest,
    export_replay,
    load_export_spec,
)
from bart_reliability.static_replay.main import main as cli

REPO = Path(__file__).resolve().parents[1]
PUBLISHED = REPO / "web" / "public" / "replay"


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic")
    warehouse = build_synthetic_warehouse(root / "wh", with_stations=True)
    cfg = replace(
        load_bundle_config(), output_dir=root / "bundle", min_calibration_examples_per_horizon=5
    )
    bundle = build_bundle(warehouse, synthetic_config(root / "run"), cfg)
    config = api_config(warehouse, bundle.bundle_dir)
    return export_replay(config, spec_for(warehouse, bundle, root / "export"))


@pytest.fixture
def published(exported, tmp_path) -> Path:
    public = tmp_path / "public" / "replay"
    publish(exported.out_dir, public)
    return public


def edit(public: Path, rel: str, change) -> None:
    """Change one published file, keeping the manifest and index consistent with it, so
    only the content checks can notice. `change` maps the parsed body to a new body, or
    returns bytes to write as they are."""
    index = json.loads((public / INDEX).read_bytes())
    export_dir = public / index["export"]
    new = change(json.loads((export_dir / rel).read_bytes()))
    data = new if isinstance(new, bytes) else encode(new)
    (export_dir / rel).write_bytes(data)
    manifest = json.loads((export_dir / MANIFEST).read_bytes())
    manifest["files"][rel] |= {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    rewrite_manifest(public, manifest)


def rewrite_manifest(public: Path, manifest: dict) -> None:
    index = json.loads((public / INDEX).read_bytes())
    raw = encode_manifest(manifest)
    (public / index["export"] / MANIFEST).write_bytes(raw)
    index["manifestSha256"] = hashlib.sha256(raw).hexdigest()
    (public / INDEX).write_bytes(encode(index) + b"\n")


def first(public: Path, prefix: str, where=lambda body: True) -> str:
    export_dir = public / read_index(public)["export"]
    for path in sorted(export_dir.rglob("*.json")):
        rel = path.relative_to(export_dir).as_posix()
        if rel.startswith(prefix) and where(json.loads(path.read_bytes())):
            return rel
    raise AssertionError(f"no {prefix} file")


def with_trains(body) -> bool:
    return bool(body["trains"])


# -- the replay in the repository ----------------------------------------------------------


def test_the_published_replay_passes_the_offline_check():
    summary = check_public(PUBLISHED)
    spec = load_export_spec()
    assert summary["export"] == spec.name == "v1-20261020T170000Z"
    assert summary["asOf"] == "2026-10-20T17:00:00Z"
    assert summary["sourceFeedTimestamp"] == "2026-10-20T16:59:23Z"
    assert summary["model"]["modelVersion"] == spec.model_version
    assert summary["model"]["bundleId"] == spec.bundle_id
    assert summary["warehouse"] == {
        "file": "bart_checkpoint_2026-10-20.duckdb",
        "sha256": spec.warehouse_sha256,
    }
    counts = summary["counts"]
    assert (counts["files"], counts["stations"], counts["boards"]) == (1155, 50, 95)
    assert (counts["trains"], counts["historyFiles"], counts["emptyBoards"]) == (1057, 1057, 5)
    assert counts["trainsByStatus"] == {
        "fallback_required": 2,
        "ok": 79,
        "outside_model_horizon": 949,
        "outside_model_population": 27,
    }
    manifest = (PUBLISHED / summary["export"] / MANIFEST).read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == summary["manifestSha256"]


def test_only_the_reduced_replay_is_published():
    files = [p.relative_to(PUBLISHED).as_posix() for p in PUBLISHED.rglob("*") if p.is_file()]
    assert all(f.endswith(".json") for f in files)
    assert len(files) == 1157  # 1,155 answers, the manifest and the index
    for path in PUBLISHED.rglob("*.json"):
        text = path.read_text()
        assert "/Users/" not in text and "/home/" not in text and "127.0.0.1" not in text


def test_the_checker_needs_no_warehouse_model_or_server():
    """The Pages workflow installs only pydantic, so the check must not import more."""
    code = (
        "import sys; import bart_reliability.static_replay.main; "
        "print(sorted(m for m in ('duckdb', 'pyarrow', 'numpy', 'pandas', 'joblib', 'sklearn', "
        "'fastapi', 'starlette') if m in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


# -- publishing ----------------------------------------------------------------------------


def test_publish_copies_the_export_and_names_it_in_the_index(exported, published):
    index = read_index(published)
    assert list(index) == ["schemaVersion", "dataMode", "export", "asOf", "manifestSha256"]
    assert index["export"] == exported.out_dir.name
    assert index["asOf"] == exported.manifest["replay"]["asOf"]
    copied = published / index["export"]
    for path in exported.out_dir.rglob("*"):
        if path.is_file():
            assert (copied / path.relative_to(exported.out_dir)).read_bytes() == path.read_bytes()
    assert sorted(p.name for p in published.iterdir()) == sorted([INDEX, index["export"]])
    assert check_public(published)["counts"] == exported.manifest["counts"]


def test_publish_replaces_the_previous_replay_whole(exported, published):
    (published / "stale.json").write_bytes(b"{}")
    publish(exported.out_dir, published)
    assert not (published / "stale.json").exists()
    assert sorted(p.name for p in published.parent.iterdir()) == ["replay"]


def test_publish_refuses_a_damaged_export(exported, tmp_path):
    damaged = tmp_path / exported.out_dir.name
    shutil.copytree(exported.out_dir, damaged)
    (damaged / "health.json").write_bytes(b"{}")
    public = tmp_path / "public" / "replay"
    with pytest.raises(ExportError, match="health.json: 2 bytes, manifest says"):
        publish(damaged, public)
    assert not public.parent.exists()


# -- the offline check ---------------------------------------------------------------------


def _set(path: list, value):
    def change(body):
        target = body
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return body

    return change


def _first_ok_train(body):
    return next(t for t in body["trains"] if t["predictionStatus"] == "ok")


def damage(name: str, public: Path) -> None:
    board = first(public, "boards/", with_trains)
    history = first(public, "history/")
    export_dir = public / read_index(public)["export"]
    manifest = json.loads((export_dir / MANIFEST).read_bytes())
    index = json.loads((public / INDEX).read_bytes())
    if name == "unsupported index schema":
        index["schemaVersion"] = "static-replay-2"
    elif name == "extra index key":
        index["notice"] = "x"
    elif name == "unsafe export name":
        index["export"] = "../outside"
    elif name == "manifest hash":
        index["manifestSha256"] = "0" * 64
    elif name == "stray file":
        (public / "extra.json").write_bytes(b"{}")
        return
    elif name == "extra field":
        edit(public, board, _set(["trains", 0, "stopId"], "A30-1"))
        return
    elif name == "wrong type":
        edit(public, board, _set(["trains", 0, "currentEtaSeconds"], "60"))
        return
    elif name == "fields out of order":
        edit(public, board, lambda b: {k: b[k] for k in reversed(list(b))})
        return
    elif name == "not compact":
        edit(public, board, lambda b: json.dumps(b, indent=1).encode())
        return
    elif name == "invalid JSON":
        edit(public, history, lambda b: b"[{")
        return
    elif name == "future observation":
        edit(public, history, _set([0, "feedTimestamp"], "2030-01-01T00:00:00Z"))
        return
    elif name == "after the source snapshot":
        as_of = manifest["replay"]["asOf"]
        edit(public, history, _set([-1, "feedTimestamp"], as_of))
        return
    elif name == "model block":
        edit(public, board, _set(["model", "modelVersion"], "9.9.9"))
        return
    elif name == "forecast without numbers":

        def change(body):
            _first_ok_train(body)["revisionProbability"] = None
            return body

        edit(
            public,
            first(
                public, "boards/", lambda b: any(t["predictionStatus"] == "ok" for t in b["trains"])
            ),
            change,
        )
        return
    elif name == "numbers without a forecast":

        def change(body):
            train = next(t for t in body["trains"] if t["predictionStatus"] != "ok")
            train["predictedRevisionSeconds"] = 5
            return body

        edit(
            public,
            first(
                public, "boards/", lambda b: any(t["predictionStatus"] != "ok" for t in b["trains"])
            ),
            change,
        )
        return
    elif name == "missing history":
        (export_dir / history).unlink()
        del manifest["files"][history]
        manifest["counts"]["files"] -= 1
        rewrite_manifest(public, manifest)
        return
    elif name == "orphan history":
        data = (export_dir / history).read_bytes()
        orphan = "history/2026-10-09_T99_1.json"
        (export_dir / orphan).write_bytes(data)
        manifest["files"][orphan] = dict(manifest["files"][history])
        manifest["counts"]["files"] += 1
        rewrite_manifest(public, manifest)
        return
    elif name == "counts":
        manifest["counts"]["trains"] += 1
        rewrite_manifest(public, manifest)
        return
    elif name == "records":
        manifest["files"][board]["records"] += 1
        rewrite_manifest(public, manifest)
        return
    elif name == "health not ok":
        edit(public, "health.json", _set(["status"], "degraded"))
        return
    elif name == "group without a board":

        def change(stations):
            stations[0]["boardingGroups"].append(
                dict(stations[0]["boardingGroups"][0], id="to-NOWHERE")
            )
            return stations

        edit(public, "stations.json", change)
        return
    (public / INDEX).write_bytes(encode(index) + b"\n")


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("unsupported index schema", "unsupported schemaVersion"),
        ("extra index key", "exactly the keys"),
        ("unsafe export name", "not an export directory name"),
        ("manifest hash", "SHA-256 is not the one index.json names"),
        ("stray file", "must hold only"),
        ("extra field", "Extra inputs are not permitted"),
        ("wrong type", "valid integer"),
        ("fields out of order", "fields out of order"),
        ("not compact", "compact form"),
        ("invalid JSON", "not valid JSON"),
        ("future observation", "after the replay time"),
        ("after the source snapshot", "after the source snapshot"),
        ("model block", "model block differs from model.json"),
        ("forecast without numbers", "an ok train without its forecast"),
        ("numbers without a forecast", "model numbers on a train without a forecast"),
        ("missing history", "a train's history is missing"),
        ("orphan history", "no train on any board"),
        ("counts", r"manifest counts differ from the files: \['trains'\]"),
        ("records", "manifest records differ"),
        ("health not ok", "not an ok answer"),
        ("group without a board", "listed in stations.json but missing"),
    ],
)
def test_the_offline_check_finds_each_kind_of_damage(published, name, message):
    check_public(published)
    damage(name, published)
    with pytest.raises(ExportError, match=message):
        check_public(published)


def test_command_line_check(published, capsys):
    assert cli(["check", str(published)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    damage("counts", published)
    assert cli(["check", str(published)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "counts differ" in out["error"]
    assert cli(["check", str(published.parent / "missing")]) == 1
