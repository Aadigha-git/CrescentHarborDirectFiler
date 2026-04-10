from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from crescent_filer.rules.checks import CUSTOM_CHECK_REGISTRY, get_path
from crescent_filer.rules.context import RulesContext
from crescent_filer.rules.findings import RuleFinding


@dataclass
class RulesEvaluationResult:
    rejections: list[RuleFinding] = field(default_factory=list)
    warnings: list[RuleFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.rejections) == 0


def _load_rules(rules_path: Path) -> list[dict[str, Any]]:
    with rules_path.open(encoding="utf-8") as f:
        doc = json.load(f)
    return list(doc.get("rules", []))


def _rule_passes(rule: dict[str, Any], manifest: dict[str, Any], ctx: RulesContext) -> tuple[bool, str]:
    rid = rule["id"]
    check = rule.get("check") or {}
    ctype = check.get("type")
    summary = rule.get("summary", rid)

    if ctype == "regex":
        path = rule.get("field", "")
        val = get_path(manifest, path)
        if val is None:
            return False, f"{summary} (missing value at {path})"
        pattern = check.get("pattern", "")
        if not re.fullmatch(pattern, str(val)):
            return False, summary
        return True, ""

    if ctype == "minValue":
        path = rule.get("field", "")
        val = get_path(manifest, path)
        min_v = check.get("value")
        if val is None or not isinstance(val, (int, float)):
            return False, f"{summary} (invalid value at {path})"
        if float(val) < float(min_v):
            return False, summary
        return True, ""

    if ctype == "maxValue":
        path = rule.get("field", "")
        val = get_path(manifest, path)
        max_v = check.get("value")
        if val is None or not isinstance(val, (int, float)):
            return False, f"{summary} (invalid value at {path})"
        if float(val) > float(max_v):
            return False, summary
        return True, ""

    if ctype == "minItems":
        path = rule.get("field", "")
        val = get_path(manifest, path)
        min_n = int(check.get("value", 0))
        if not isinstance(val, list) or len(val) < min_n:
            return False, summary
        return True, ""

    if ctype == "notEquals":
        forbidden = check.get("value")
        field_path = rule.get("field", "")
        if field_path.startswith("/containers/*/"):
            suffix = field_path.split("/containers/*/")[-1]
            for idx, c in enumerate(manifest.get("containers") or []):
                if c.get("type") != "REF":
                    continue
                v = c.get(suffix)
                if v == forbidden:
                    return False, f"{summary} (container index {idx})"
            return True, ""
        val = get_path(manifest, field_path)
        if val == forbidden:
            return False, summary
        return True, ""

    if ctype == "custom":
        name = check.get("name")
        fn = CUSTOM_CHECK_REGISTRY.get(name or "")
        if fn is None:
            return False, f"unknown custom check {name!r}"
        ok = bool(fn(manifest, ctx))
        if ok:
            return True, ""
        return False, summary

    return False, f"unsupported check type {ctype!r}"


def evaluate_rules(
    manifest: dict[str, Any],
    *,
    rules_path: Path,
    context: RulesContext | None = None,
) -> RulesEvaluationResult:
    ctx = context or RulesContext.utc_now()
    rules = _load_rules(rules_path)
    result = RulesEvaluationResult()
    for rule in rules:
        rid = rule["id"]
        sev = rule.get("severity", "reject")
        field = rule.get("field", "")
        code = rule.get("rejectionCode")
        ok, msg = _rule_passes(rule, manifest, ctx)
        if ok:
            continue
        finding = RuleFinding(
            rule_id=rid,
            severity=sev,
            message=msg,
            field=field,
            rejection_code=code,
        )
        if sev == "warning":
            result.warnings.append(finding)
        else:
            result.rejections.append(finding)
    return result
