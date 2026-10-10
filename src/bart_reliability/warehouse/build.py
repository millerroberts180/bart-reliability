"""Build data/warehouse/bart.duckdb from scratch, replacing it atomically."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import duckdb

from bart_reliability.warehouse.quality import create_quality_views, join_quality
from bart_reliability.warehouse.realtime import create_enriched_view, create_realtime_view
from bart_reliability.warehouse.static_gtfs import StaticLoadResult, load_static


@dataclass(frozen=True)
class BuildResult:
    db_path: Path
    static: StaticLoadResult
    parquet_files: int
    quality: dict


def build_warehouse(gtfs_zip: Path, processed_dir: Path, db_path: Path) -> BuildResult:
    """Load static GTFS and create the real-time views in a fresh database.

    The database is built under a temporary name and renamed into place only if
    every step succeeds. Reruns therefore never duplicate rows, and a failed
    build (e.g. a malformed archive) leaves the previous warehouse untouched.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_name(f".{db_path.name}.building")
    _remove_db(tmp)

    con = duckdb.connect(str(tmp))
    try:
        static = load_static(con, gtfs_zip)
        parquet_files = create_realtime_view(con, processed_dir)
        create_enriched_view(con)
        create_quality_views(con)
        quality = join_quality(con)
        con.execute("CHECKPOINT")
    except BaseException:
        con.close()
        _remove_db(tmp)
        raise
    con.close()
    os.replace(tmp, db_path)
    return BuildResult(db_path, static, parquet_files, quality)


def _remove_db(path: Path) -> None:
    for p in (path, path.with_name(path.name + ".wal")):
        p.unlink(missing_ok=True)
