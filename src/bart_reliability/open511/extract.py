"""Stream one agency's rows out of a large 511 regional GTFS archive into Parquet.

Regional files are big (stop_observations.txt is ~3 GB for one month), so rows are
read straight from the ZIP in blocks and filtered without extracting the archive.
Every column is kept as a string so identifiers are preserved exactly.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq


def _header(archive: zipfile.ZipFile, member: str) -> list[str]:
    with archive.open(member) as f:
        line = io.TextIOWrapper(f, encoding="utf-8-sig", newline="").readline()
    return [name.strip() for name in next(csv.reader([line]))]


def extract_subset(
    zip_path: Path,
    member: str,
    out_path: Path,
    column: str,
    equals: str | None = None,
    prefix: str | None = None,
    isin: set[str] | None = None,
) -> int:
    """Write rows of `member` whose `column` matches to out_path. Returns the row count.

    Exactly one of `equals`, `prefix`, or `isin` selects rows.
    """
    if sum(x is not None for x in (equals, prefix, isin)) != 1:
        raise ValueError("give exactly one of equals, prefix, isin")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f".{out_path.name}.tmp")
    rows = 0
    with zipfile.ZipFile(zip_path) as archive:
        names = _header(archive, member)
        if column not in names:
            raise ValueError(f"{member} has no column {column!r}")
        schema = pa.schema([(n, pa.string()) for n in names])
        with archive.open(member) as raw:
            reader = pacsv.open_csv(
                raw,
                # Names come from _header (BOM-safe); skip the file's own header row.
                read_options=pacsv.ReadOptions(
                    block_size=64 << 20, column_names=names, skip_rows=1
                ),
                convert_options=pacsv.ConvertOptions(
                    column_types={n: pa.string() for n in names},
                    strings_can_be_null=True,
                    quoted_strings_can_be_null=False,
                ),
            )
            with pq.ParquetWriter(tmp, schema, compression="zstd") as writer:
                for batch in reader:
                    values = batch.column(column)
                    if equals is not None:
                        mask = pc.equal(values, equals)
                    elif prefix is not None:
                        mask = pc.starts_with(values, prefix)
                    else:
                        mask = pc.is_in(values, value_set=pa.array(sorted(isin), pa.string()))
                    mask = pc.fill_null(mask, False)
                    selected = batch.filter(mask)
                    if selected.num_rows:
                        writer.write_batch(selected)
                        rows += selected.num_rows
    tmp.replace(out_path)
    return rows
