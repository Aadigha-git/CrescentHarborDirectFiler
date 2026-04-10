from __future__ import annotations

import uuid


def new_manifest_id() -> str:
    """§3.4: UUIDv4 without hyphens, uppercased."""
    return uuid.uuid4().hex.upper()
