"""Write raw snapshots atomically without ever overwriting an existing file."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def snapshot_path(output_dir: Path, feed_name: str, collected_at: datetime) -> Path:
    """Return <output_dir>/<feed>/<YYYY-MM-DD>/<HHMMSS>Z.pb for a UTC collection time."""
    if collected_at.utcoffset() is None or collected_at.utcoffset().total_seconds() != 0:
        raise ValueError("collected_at must be a timezone-aware UTC datetime")
    collected_at = collected_at.astimezone(UTC)
    day = collected_at.strftime("%Y-%m-%d")
    name = collected_at.strftime("%H%M%SZ.pb")
    return output_dir / feed_name / day / name


def save_snapshot(output_dir: Path, feed_name: str, collected_at: datetime, content: bytes) -> Path:
    """Save content and return its path.

    The bytes go to a hidden temp file in the same directory first, are flushed
    to disk, and are then hard-linked to the final name. Linking fails if the
    name already exists, so an earlier snapshot can never be replaced, and the
    final file only ever appears complete.

    Raises FileExistsError if a snapshot with this name already exists.
    """
    path = snapshot_path(output_dir, feed_name, collected_at)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.link(tmp_name, path)
    finally:
        os.unlink(tmp_name)

    _fsync_dir(path.parent)
    return path


def _fsync_dir(directory: Path) -> None:
    # Persist the new directory entry so the file survives a power loss.
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
