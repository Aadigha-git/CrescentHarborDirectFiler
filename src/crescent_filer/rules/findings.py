from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleFinding:
    rule_id: str
    severity: str
    message: str
    field: str
    rejection_code: str | None = None
