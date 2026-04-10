from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from crescent_filer.builder.manifest_builder import build_from_scenario_dict, load_scenario_path
from crescent_filer.models.manifest import FilerInfo, FilerSignature
from crescent_filer.rules.context import RulesContext
from crescent_filer.rules.engine import evaluate_rules


def test_scenario_passes_rules_with_filing_window(repo_root: Path) -> None:
    scenario = load_scenario_path(repo_root / "scenarios" / "01-aurora-borealis.json")
    filer = FilerInfo(filer_id="CHC100001", legal_name="Test", contact_email="t@example.com")
    sig = FilerSignature(signer_name="A", signer_title="B", signed_at_utc="2026-01-01T12:00:00Z")
    manifest = build_from_scenario_dict(scenario, filer=filer, filer_signature=sig, eta_offset_hours=48.0)
    eta = datetime.fromisoformat(manifest["arrival"]["eta"].replace("Z", "+00:00"))
    transmit = eta - timedelta(hours=48)
    ctx = RulesContext(transmit_time_utc=transmit)
    res = evaluate_rules(manifest, rules_path=repo_root / "rules" / "rules.json", context=ctx)
    assert res.ok, [f.message for f in res.rejections]
