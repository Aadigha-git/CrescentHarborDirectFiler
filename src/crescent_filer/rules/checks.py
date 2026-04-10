from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import EmailStr, TypeAdapter

from crescent_filer.rules.context import RulesContext


def get_path(obj: Any, path: str) -> Any:
    if path == "/":
        return obj
    parts = [p for p in path.strip("/").split("/") if p]
    cur: Any = obj
    for p in parts:
        if p == "*":
            raise ValueError("wildcard path not supported in get_path")
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def imo_check_digit(imo: str) -> bool:
    if not imo.startswith("IMO") or len(imo) != 10:
        return False
    digits = imo[3:]
    if not digits.isdigit() or len(digits) != 7:
        return False
    weights = (7, 6, 5, 4, 3, 2)
    s = sum(int(digits[i]) * weights[i] for i in range(6))
    check = s % 10
    return check == int(digits[6])


def rfc5322_email(addr: str) -> bool:
    try:
        TypeAdapter(EmailStr).validate_python(addr)
        return True
    except Exception:
        return False


def vessel_type_terminal_consistent(manifest: dict[str, Any]) -> bool:
    v = manifest.get("vessel") or {}
    a = manifest.get("arrival") or {}
    vt = v.get("vesselType")
    term = a.get("terminal")
    if not vt or not term:
        return False
    if vt == "CONTAINER":
        return term in ("CH-A", "CH-B")
    if vt in ("BULK", "TANKER"):
        return term == "CH-C"
    if vt == "RORO":
        return term == "CH-D"
    if vt == "GENERAL":
        return True
    return False


def container_id_uniqueness(manifest: dict[str, Any]) -> bool:
    containers = manifest.get("containers") or []
    ids: list[str] = []
    for c in containers:
        cid = c.get("containerId")
        if cid in ids:
            return False
        ids.append(cid)
    return True


def ballast_exclusivity(manifest: dict[str, Any]) -> bool:
    containers = manifest.get("containers") or []
    types = [c.get("type") for c in containers]
    if "BALLAST" in types:
        return len(containers) == 1
    return True


def vin_list_matches_quantity(manifest: dict[str, Any]) -> bool:
    for c in manifest.get("containers") or []:
        if c.get("type") != "VEH":
            continue
        qty = c.get("quantity")
        vins = c.get("vins") or []
        if qty is None or len(vins) != int(qty):
            return False
    return True


def class7_requires_prior_auth(manifest: dict[str, Any]) -> bool:
    for c in manifest.get("containers") or []:
        if c.get("type") != "HAZ":
            continue
        if str(c.get("hazardClass")) == "7":
            ref = c.get("priorAuthorizationRef")
            if not ref or not str(ref).strip():
                return False
    return True


def hazmat_proportion_under_quarter(manifest: dict[str, Any]) -> bool:
    """
    R-014: Enforce only when every HAZ container includes grossWeightKg.
    Sum metric tons (kg/1000) must not exceed 25% of grossRegisterTons (case-study units).
    """
    vessel = manifest.get("vessel") or {}
    grt = vessel.get("grossRegisterTons")
    if grt is None:
        return True
    haz = [c for c in (manifest.get("containers") or []) if c.get("type") == "HAZ"]
    if not haz:
        return True
    if any("grossWeightKg" not in c for c in haz):
        return True
    total_tonnes = sum(float(c["grossWeightKg"]) for c in haz) / 1000.0
    limit = 0.25 * float(grt)
    return total_tonnes <= limit


def hazmat_presence_warning(manifest: dict[str, Any]) -> bool:
    """Return True if no warning needed; False triggers warning (engine inverts for warnings)."""
    for c in manifest.get("containers") or []:
        if c.get("type") == "HAZ":
            return False
    return True


def declared_value_total_matches_sum(manifest: dict[str, Any]) -> bool:
    total = manifest.get("declaredValueTotal")
    if total is None:
        return False
    s = Decimal(0)
    for c in manifest.get("containers") or []:
        dv = c.get("declaredValueUSD")
        if dv is None:
            return False
        rounded = Decimal(str(dv)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        s += rounded
    expected = Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return s == expected


def two_decimal_place_precision(manifest: dict[str, Any]) -> bool:
    """True if no warning; False if any container value has more than 2 decimal places."""
    for c in manifest.get("containers") or []:
        dv = c.get("declaredValueUSD")
        if dv is None:
            continue
        d = Decimal(str(dv))
        if d != d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
            return False
    return True


def exactly_one_master(manifest: dict[str, Any]) -> bool:
    crew = manifest.get("crew") or []
    masters = sum(1 for m in crew if m.get("role") == "MASTER")
    return masters == 1


def _parse_eta_date(manifest: dict[str, Any]) -> date | None:
    arrival = manifest.get("arrival") or {}
    eta = arrival.get("eta")
    if not eta or not isinstance(eta, str) or len(eta) < 10:
        return None
    try:
        return date.fromisoformat(eta[:10])
    except ValueError:
        return None


def crew_age_range(manifest: dict[str, Any]) -> bool:
    eta_d = _parse_eta_date(manifest)
    if eta_d is None:
        return False
    for m in manifest.get("crew") or []:
        dob_s = m.get("dateOfBirth")
        if not dob_s:
            return False
        try:
            dob = date.fromisoformat(str(dob_s)[:10])
        except ValueError:
            return False
        age = eta_d.year - dob.year - ((eta_d.month, eta_d.day) < (dob.month, dob.day))
        if age < 16 or age > 80:
            return False
    return True


def master_has_nationality(manifest: dict[str, Any]) -> bool:
    for m in manifest.get("crew") or []:
        if m.get("role") == "MASTER":
            nat = m.get("nationality")
            return bool(nat and str(nat).strip())
    return False


def filing_not_too_early(manifest: dict[str, Any], ctx: RulesContext) -> bool:
    eta = _eta_utc(manifest)
    if eta is None:
        return False
    earliest = eta - timedelta(hours=96)
    return ctx.transmit_time_utc >= earliest


def filing_not_too_late(manifest: dict[str, Any], ctx: RulesContext) -> bool:
    eta = _eta_utc(manifest)
    if eta is None:
        return False
    latest = eta - timedelta(hours=24)
    return ctx.transmit_time_utc <= latest


def _eta_utc(manifest: dict[str, Any]) -> datetime | None:
    arrival = manifest.get("arrival") or {}
    eta = arrival.get("eta")
    if not eta or not isinstance(eta, str):
        return None
    try:
        if eta.endswith("Z"):
            return datetime.fromisoformat(eta.replace("Z", "+00:00"))
        return datetime.fromisoformat(eta).astimezone(timezone.utc)
    except ValueError:
        return None


def amendment_invariants(manifest: dict[str, Any], ctx: RulesContext) -> bool:
    if "amendmentSequence" not in manifest:
        return True
    orig = ctx.original_manifest
    if orig is None:
        return False
    if manifest.get("manifestId") != orig.get("manifestId"):
        return False
    v0, v1 = orig.get("vessel") or {}, manifest.get("vessel") or {}
    a0, a1 = orig.get("arrival") or {}, manifest.get("arrival") or {}
    return v0.get("imoNumber") == v1.get("imoNumber") and a0.get("eta") == a1.get("eta")


def amendment_sequence_monotonic(manifest: dict[str, Any], ctx: RulesContext) -> bool:
    if "amendmentSequence" not in manifest:
        return True
    seq = manifest.get("amendmentSequence")
    if not isinstance(seq, int):
        return False
    last = ctx.last_amendment_sequence
    if last is None:
        return seq == 1
    return seq == last + 1


CUSTOM_CHECK_REGISTRY: dict[str, Any] = {
    "imoCheckDigit": lambda m, ctx: imo_check_digit((m.get("vessel") or {}).get("imoNumber", "")),
    "rfc5322EmailAddrSpec": lambda m, ctx: rfc5322_email((m.get("filer") or {}).get("contactEmail", "")),
    "vesselTypeTerminalConsistent": lambda m, ctx: vessel_type_terminal_consistent(m),
    "containerIdUniqueness": lambda m, ctx: container_id_uniqueness(m),
    "ballastExclusivity": lambda m, ctx: ballast_exclusivity(m),
    "vinListMatchesQuantity": lambda m, ctx: vin_list_matches_quantity(m),
    "class7RequiresPriorAuth": lambda m, ctx: class7_requires_prior_auth(m),
    "hazmatProportionUnderQuarter": lambda m, ctx: hazmat_proportion_under_quarter(m),
    "hazmatPresenceWarning": lambda m, ctx: hazmat_presence_warning(m),
    "declaredValueTotalMatchesSum": lambda m, ctx: declared_value_total_matches_sum(m),
    "twoDecimalPlacePrecision": lambda m, ctx: two_decimal_place_precision(m),
    "exactlyOneMaster": lambda m, ctx: exactly_one_master(m),
    "crewAgeRange": lambda m, ctx: crew_age_range(m),
    "masterHasNationality": lambda m, ctx: master_has_nationality(m),
    "filingNotTooEarly": lambda m, ctx: filing_not_too_early(m, ctx),
    "filingNotTooLate": lambda m, ctx: filing_not_too_late(m, ctx),
    "amendmentInvariants": lambda m, ctx: amendment_invariants(m, ctx),
    "amendmentSequenceMonotonic": lambda m, ctx: amendment_sequence_monotonic(m, ctx),
}
