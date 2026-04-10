from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class RulesContext:
    """Clock and amendment baseline for rules R-022–R-025."""

    transmit_time_utc: datetime
    original_manifest: dict[str, Any] | None = None
    last_amendment_sequence: int | None = None

    @classmethod
    def utc_now(cls) -> RulesContext:
        return cls(transmit_time_utc=datetime.now(timezone.utc))
