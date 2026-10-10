"""Emit one JSON object per log line."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path


class JsonFormatter(logging.Formatter):
    """Format records as JSON; structured data goes in extra={"fields": {...}}."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(log_file: Path | None, level: int = logging.INFO) -> None:
    """Send JSON logs to stdout and, if given, append them to log_file."""
    formatter = JsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
