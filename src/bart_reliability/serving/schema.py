"""The committed bundle-metadata schema and the helpers that enforce it.

config/eta_model_bundle.schema.json is the single source of truth for the served feature
contract: names, types and order, the input domain, and the fallback policy. The code
reads those constants from it instead of repeating them.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "config" / "eta_model_bundle.schema.json"
METADATA_FILENAME = "bundle.json"


class SchemaError(ValueError):
    """Raised when a document does not satisfy the bundle-metadata schema."""


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(path.read_text())


def constant(schema: dict, name: str):
    """A top-level constant of the schema, e.g. 'features' or 'domain'."""
    return schema["properties"][name]["const"]


def canonical_json(value) -> str:
    """Key-sorted, compact JSON: equal documents give equal text and equal hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def bundle_id(metadata: dict) -> str:
    """SHA-256 of the canonical metadata without its own bundle_id."""
    body = {k: v for k, v in metadata.items() if k != "bundle_id"}
    return hashlib.sha256(canonical_json(body).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def validate(instance, schema: dict, path: str = "$") -> None:
    """Validate against the JSON Schema subset the bundle schema uses.

    Supports type, const, enum, properties, required, additionalProperties (false),
    items, minItems, maxItems, minLength, pattern, minimum and maximum. Raises
    SchemaError naming the first failing location.
    """

    def fail(message):
        raise SchemaError(f"{path}: {message}")

    if "const" in schema and canonical_json(instance) != canonical_json(schema["const"]):
        fail("does not equal the committed constant")
    if "enum" in schema and instance not in schema["enum"]:
        fail(f"{instance!r} is not one of {schema['enum']}")
    if "type" in schema and not _is_type(instance, schema["type"]):
        fail(f"expected {schema['type']}, got {type(instance).__name__}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                fail(f"missing required key {key!r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(instance) - set(props))
            if extra:
                fail(f"unexpected keys {extra}")
        for key, sub in props.items():
            if key in instance:
                validate(instance[key], sub, f"{path}.{key}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            fail(f"fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            fail(f"more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(instance):
                validate(item, schema["items"], f"{path}[{i}]")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            fail("string too short")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            fail(f"{instance!r} does not match {schema['pattern']}")
    if _is_type(instance, "number"):
        if "minimum" in schema and instance < schema["minimum"]:
            fail(f"below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            fail(f"above maximum {schema['maximum']}")
