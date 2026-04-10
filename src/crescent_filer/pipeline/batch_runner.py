from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from crescent_filer.pipeline.config import FilerPipelineConfig, default_repo_root
from crescent_filer.pipeline.runner import PipelineResult, load_manifest_or_scenario, run_pipeline
from crescent_filer.rules.context import RulesContext

Outcome = Literal[
    "accepted",
    "rejected_by_rules",
    "rejected_by_schema",
    "rejected_by_authority",
    "error",
]


def classify_outcome(result: PipelineResult) -> Outcome:
    """Derive outcome from pipeline state only (no filename heuristics)."""
    if result.schema is not None and not result.schema.ok:
        return "rejected_by_schema"
    if result.rules is not None and not result.rules.ok:
        return "rejected_by_rules"
    if result.submit is None:
        return "error"
    if result.ack is None:
        return "error"
    st = result.ack.status
    if st == "ACCEPTED":
        return "accepted"
    if st == "REJECTED":
        return "rejected_by_authority"
    return "error"


def _list_scenario_files(scenarios_dir: Path) -> list[Path]:
    if not scenarios_dir.is_dir():
        raise FileNotFoundError(f"Scenarios directory not found: {scenarios_dir}")
    files = sorted(p for p in scenarios_dir.glob("*.json") if p.is_file())
    return files


def _is_scenario_shape(doc: dict[str, Any]) -> bool:
    """Treat as scenario input if it has cargo/vessel shape (excludes stray JSON)."""
    return isinstance(doc.get("vessel"), dict) and isinstance(doc.get("arrival"), dict)


@dataclass
class ScenarioRow:
    file: str
    scenarioId: str | None
    outcome: Outcome
    manifestId: str | None
    receiptId: str | None
    schemaErrors: list[dict[str, str]]
    ruleRejections: list[dict[str, str]]
    ruleWarnings: list[dict[str, str]]
    authorityErrors: list[dict[str, str]]
    errors: list[str]


def run_scenarios_batch(
    cfg: FilerPipelineConfig,
    *,
    scenarios_dir: Path | None = None,
    poll: bool = True,
) -> dict[str, Any]:
    """
    For each ``*.json`` in ``scenarios_dir``: builder → schema → rules → POST → poll.
    Returns a Format B report dict (see scenarios/README.md).
    """
    root = cfg.schema_path.parent.parent
    sdir = scenarios_dir or (root / "scenarios")
    rows: list[ScenarioRow] = []
    for path in _list_scenario_files(sdir):
        raw_preview: dict[str, Any] | None = None
        try:
            raw_preview = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            rows.append(
                ScenarioRow(
                    file=path.name,
                    scenarioId=None,
                    outcome="error",
                    manifestId=None,
                    receiptId=None,
                    schemaErrors=[],
                    ruleRejections=[],
                    ruleWarnings=[],
                    authorityErrors=[],
                    errors=[f"invalid JSON: {exc}"],
                )
            )
            continue

        scenario_id = raw_preview.get("_scenarioId") if isinstance(raw_preview.get("_scenarioId"), str) else None
        if not _is_scenario_shape(raw_preview):
            rows.append(
                ScenarioRow(
                    file=path.name,
                    scenarioId=scenario_id,
                    outcome="error",
                    manifestId=None,
                    receiptId=None,
                    schemaErrors=[],
                    ruleRejections=[],
                    ruleWarnings=[],
                    authorityErrors=[],
                    errors=["skipped: JSON does not look like a scenario (missing vessel/arrival)"],
                )
            )
            continue

        ref = datetime.now(timezone.utc)
        try:
            manifest = load_manifest_or_scenario(path, cfg, reference_time_utc=ref)
        except Exception as exc:
            rows.append(
                ScenarioRow(
                    file=path.name,
                    scenarioId=scenario_id,
                    outcome="error",
                    manifestId=None,
                    receiptId=None,
                    schemaErrors=[],
                    ruleRejections=[],
                    ruleWarnings=[],
                    authorityErrors=[],
                    errors=[f"builder failed: {exc}"],
                )
            )
            continue

        ctx = RulesContext(transmit_time_utc=ref)
        result = run_pipeline(manifest, cfg, rules_context=ctx, poll=poll)
        outcome = classify_outcome(result)

        schema_errs = list(result.schema.errors) if result.schema else []
        rule_rej = [
            {
                "ruleId": f.rule_id,
                "message": f.message,
                "rejectionCode": f.rejection_code or "",
                "field": f.field,
            }
            for f in (result.rules.rejections if result.rules else [])
        ]
        rule_warn = [
            {"ruleId": f.rule_id, "message": f.message, "field": f.field}
            for f in (result.rules.warnings if result.rules else [])
        ]
        auth_errs: list[dict[str, str]] = []
        if result.ack and result.ack.body.get("errors"):
            for e in result.ack.body.get("errors") or []:
                if isinstance(e, dict):
                    auth_errs.append(
                        {
                            "code": str(e.get("code", "")),
                            "message": str(e.get("message", "")),
                        }
                    )

        mid = manifest.get("manifestId") if isinstance(manifest.get("manifestId"), str) else None
        rid = result.submit.receipt_id if result.submit else None

        rows.append(
            ScenarioRow(
                file=path.name,
                scenarioId=scenario_id,
                outcome=outcome,
                manifestId=mid,
                receiptId=rid,
                schemaErrors=schema_errs,
                ruleRejections=rule_rej,
                ruleWarnings=rule_warn,
                authorityErrors=auth_errs,
                errors=list(result.errors),
            )
        )

    report: dict[str, Any] = {
        "reportFormat": "B",
        "generatedAtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run": {
            "baseUrl": cfg.base_url,
            "scenariosDir": str(sdir.resolve()),
            "filerId": cfg.filer_id,
        },
        "results": [asdict(r) for r in rows],
    }
    return report


def write_results_json(report: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_batch_cli(
    *,
    root: Path | None = None,
    scenarios_dir: Path | None = None,
    output: Path | None = None,
    base_url: str | None = None,
    poll: bool = True,
) -> tuple[dict[str, Any], Path]:
    root_res = (root or default_repo_root()).resolve()
    cfg = FilerPipelineConfig.from_repo(root_res, base_url=base_url)
    out = (output or (root_res / "results.json")).resolve()
    sdir = scenarios_dir.resolve() if scenarios_dir else None
    report = run_scenarios_batch(cfg, scenarios_dir=sdir, poll=poll)
    write_results_json(report, out)
    return report, out


def batch_exit_code(report: dict[str, Any]) -> int:
    outcomes = [r["outcome"] for r in report["results"]]
    return 1 if "error" in outcomes else 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run all scenario JSON files through the full filer pipeline.")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (default: CRESCENT_HARBOR_ROOT or cwd)",
    )
    parser.add_argument(
        "--scenarios-dir",
        type=Path,
        default=None,
        help="Directory of scenario *.json files (default: <root>/scenarios)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write Format B JSON here (default: <root>/results.json)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Override CRESCENT_BASE_URL / default mock URL",
    )
    parser.add_argument(
        "--no-poll",
        action="store_true",
        help="Submit only (no GET /v3/acks polling); outcomes may be incomplete",
    )
    args = parser.parse_args(argv)

    report, out = run_batch_cli(
        root=args.root,
        scenarios_dir=args.scenarios_dir,
        output=args.output,
        base_url=args.base_url,
        poll=not args.no_poll,
    )
    print(f"Wrote {out}", file=sys.stderr)
    return batch_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
