from __future__ import annotations

from pathlib import Path

from crescent_filer.builder.manifest_builder import build_from_scenario_dict, load_scenario_path
from crescent_filer.models.manifest import FilerInfo, FilerSignature
from crescent_filer.validation.schema_validator import validate_manifest_schema


def test_scenario_passes_schema(repo_root: Path) -> None:
    scenario = load_scenario_path(repo_root / "scenarios" / "01-aurora-borealis.json")
    filer = FilerInfo(filer_id="CHC100001", legal_name="Test", contact_email="t@example.com")
    sig = FilerSignature(signer_name="A", signer_title="B", signed_at_utc="2026-01-01T12:00:00Z")
    manifest = build_from_scenario_dict(scenario, filer=filer, filer_signature=sig, eta_offset_hours=48.0)
    res = validate_manifest_schema(manifest, schema_path=repo_root / "schema" / "manifest.schema.json")
    assert res.ok, res.errors
