from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from crescent_filer.builder.ids import new_manifest_id
from crescent_filer.models.manifest import FilerInfo, FilerSignature, ScenarioInput


def _utc_eta_from_offset_hours(offset_hours: float, *, reference_time_utc: datetime) -> str:
    eta = reference_time_utc + timedelta(hours=offset_hours)
    return eta.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_vessel_name(name: str) -> str:
    """R-005 / §4.1: filer uppercases vessel name before submission."""
    return name.upper()


def build_from_scenario_dict(
    scenario: dict[str, Any],
    *,
    filer: FilerInfo,
    filer_signature: FilerSignature,
    manifest_id: str | None = None,
    eta: str | None = None,
    eta_offset_hours: float | None = None,
    reference_time_utc: datetime | None = None,
) -> dict[str, Any]:
    """
    Merge scenario fixture with filer identity, generated ids, ETA, and signature.
    Strips underscore-prefixed scenario keys. Uses `_etaOffsetHours` when `eta` not given.
    When ``reference_time_utc`` is set, ETA and filing-window rules should use the same instant
    as submission time (see scenarios/README.md).
    """
    ref = reference_time_utc or datetime.now(timezone.utc)
    raw = {k: v for k, v in scenario.items() if not k.startswith("_")}
    parsed = ScenarioInput.model_validate(raw)

    vessel = dict(parsed.vessel)
    vessel["name"] = _normalize_vessel_name(vessel["name"])

    arrival = dict(parsed.arrival)
    if eta is not None:
        arrival["eta"] = eta
    elif eta_offset_hours is not None:
        arrival["eta"] = _utc_eta_from_offset_hours(eta_offset_hours, reference_time_utc=ref)
    elif "_etaOffsetHours" in scenario:
        arrival["eta"] = _utc_eta_from_offset_hours(
            float(scenario["_etaOffsetHours"]),
            reference_time_utc=ref,
        )
    else:
        raise ValueError("Provide eta=, eta_offset_hours=, or scenario _etaOffsetHours")

    manifest: dict[str, Any] = {
        "manifestId": manifest_id or new_manifest_id(),
        "filer": filer.to_manifest_dict(),
        "vessel": vessel,
        "arrival": arrival,
        "containers": list(parsed.containers),
        "crew": list(parsed.crew),
        "declaredValueTotal": parsed.declared_value_total,
        "filerSignature": filer_signature.to_manifest_dict(),
    }
    if "amendmentSequence" in scenario:
        manifest["amendmentSequence"] = scenario["amendmentSequence"]
    return manifest


def load_scenario_path(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)
