"""Command-line entry point: bart-static-replay (export, verify, publish or check a static
historical replay)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bart_reliability.api.config import DEFAULT_API_CONFIG_PATH, ApiConfigError, load_api_config
from bart_reliability.static_replay.check import PUBLIC_ROOT, check_public, publish
from bart_reliability.static_replay.export import (
    DEFAULT_SPEC_PATH,
    ExportError,
    export_replay,
    load_export_spec,
    read_manifest,
    size_report,
    verify_export,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the local historical replay as static JSON files, verify or "
        "publish an export, or check the published replay offline."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="ask the local API everything and write the files")
    export.add_argument("--out", type=Path, help="output root (default: the spec's output_dir)")
    verify = sub.add_parser("verify", help="check an export against a freshly loaded API")
    verify.add_argument("export_dir", type=Path, nargs="?", help="default: the spec's export")
    pub = sub.add_parser("publish", help="verify an export, then copy it for the website")
    pub.add_argument("export_dir", type=Path, nargs="?", help="default: the spec's export")
    pub.add_argument("--public", type=Path, default=PUBLIC_ROOT, help=f"default: {PUBLIC_ROOT}")
    for p in (export, verify, pub):
        p.add_argument("--spec", type=Path, default=DEFAULT_SPEC_PATH)
        p.add_argument("--api-config", type=Path, default=DEFAULT_API_CONFIG_PATH)
    check = sub.add_parser("check", help="check the published replay offline (no warehouse)")
    check.add_argument("public", type=Path, nargs="?", default=PUBLIC_ROOT)
    args = parser.parse_args(argv)

    if args.command == "check":
        try:
            summary = check_public(args.public)
        except ExportError as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1
        print(json.dumps({"ok": True} | summary, indent=1))
        return 0

    try:
        spec = load_export_spec(args.spec)
        config = load_api_config(args.api_config)
    except (ExportError, ApiConfigError) as e:
        print(json.dumps({"error": str(e)}))
        return 2
    try:
        if args.command == "export":
            result = export_replay(config, spec, args.out)
            out_dir, parity = result.out_dir, result.parity
        else:
            out_dir = args.export_dir or spec.output_dir / spec.name
            parity = verify_export(out_dir, config, spec)
        manifest = read_manifest(out_dir)
        published = None
        if args.command == "publish" and parity.ok:
            published = publish(out_dir, args.public)
    except ExportError as e:
        print(json.dumps({"error": str(e)}))
        return 1
    summary = {
        "export": str(out_dir),
        "schemaVersion": manifest["schemaVersion"],
        "replay": manifest["replay"],
        "counts": manifest["counts"],
        "parity": parity.as_dict(),
        "sizes": size_report(out_dir, manifest),
    }
    if args.command == "publish":
        summary["published"] = {"to": str(args.public)} | (published or {"refused": True})
    print(json.dumps(summary, indent=1))
    return 0 if parity.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
