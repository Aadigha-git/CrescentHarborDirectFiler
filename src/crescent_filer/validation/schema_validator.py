from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


@dataclass
class SchemaValidationResult:
    ok: bool
    errors: list[dict[str, str]] = field(default_factory=list)


def _error_code(message: str) -> str:
    if "Additional properties" in message:
        return "M-103"
    if "is a required property" in message:
        return "R-602"
    if "is not one of" in message or "is not valid" in message or "does not match" in message:
        return "M-102"
    return "M-102"


def validate_manifest_schema(
    manifest: dict[str, Any],
    *,
    schema_path: Path | None = None,
    schema: dict[str, Any] | None = None,
) -> SchemaValidationResult:
    if schema is None:
        if schema_path is None:
            raise ValueError("Provide schema_path or schema")
        with schema_path.open(encoding="utf-8") as f:
            schema = json.load(f)
    validator = Draft202012Validator(schema)
    errors: list[dict[str, str]] = []
    for err in validator.iter_errors(manifest):
        path = "/" + "/".join(str(p) for p in err.absolute_path) if err.absolute_path else "/"
        code = _error_code(err.message)
        errors.append({"code": code, "message": f"{path}: {err.message[:200]}"})
    return SchemaValidationResult(ok=len(errors) == 0, errors=errors[:50])
