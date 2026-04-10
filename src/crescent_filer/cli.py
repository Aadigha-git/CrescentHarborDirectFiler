from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from crescent_filer.pipeline.config import FilerPipelineConfig, default_repo_root
from crescent_filer.pipeline.batch_runner import batch_exit_code, run_batch_cli
from crescent_filer.pipeline.runner import load_manifest_or_scenario, run_pipeline
from crescent_filer.rules.context import RulesContext
from crescent_filer.rules.engine import evaluate_rules
from crescent_filer.validation.schema_validator import validate_manifest_schema

app = typer.Typer(no_args_is_help=True, help="Crescent Harbor Cargo Arrival Manifest filer CLI")


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(exists=True, readable=True, help="Manifest JSON or scenario JSON")],
    root: Annotated[Optional[Path], typer.Option(help="Repository root (schema/rules)")] = None,
) -> None:
    """Run JSON Schema and business rules; do not transmit."""
    cfg = FilerPipelineConfig.from_repo(root or default_repo_root())
    manifest = load_manifest_or_scenario(path, cfg)
    schema = validate_manifest_schema(manifest, schema_path=cfg.schema_path)
    if not schema.ok:
        typer.echo("Schema validation failed:", err=True)
        for e in schema.errors:
            typer.echo(f"  {e['code']}: {e['message']}", err=True)
        raise typer.Exit(code=1)
    rules = evaluate_rules(manifest, rules_path=cfg.rules_path, context=RulesContext.utc_now())
    for w in rules.warnings:
        typer.echo(f"WARNING {w.rule_id}: {w.message}")
    if not rules.ok:
        typer.echo("Rules rejected:", err=True)
        for f in rules.rejections:
            code = f.rejection_code or f.rule_id
            typer.echo(f"  {code} ({f.rule_id}): {f.message}", err=True)
        raise typer.Exit(code=1)
    typer.echo("OK: schema and rules passed.")


@app.command("submit")
def submit_cmd(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    root: Annotated[Optional[Path], typer.Option()] = None,
    no_poll: Annotated[bool, typer.Option("--no-poll", help="Stop after HTTP 202 RECEIVED")] = False,
    base_url: Annotated[Optional[str], typer.Option(envvar="CRESCENT_BASE_URL")] = None,
) -> None:
    """Validate, then POST manifest and optionally poll for final ack."""
    cfg = FilerPipelineConfig.from_repo(root or default_repo_root(), base_url=base_url)
    manifest = load_manifest_or_scenario(path, cfg)
    result = run_pipeline(manifest, cfg, poll=not no_poll)
    if result.submit:
        typer.echo(json.dumps(result.submit.raw, indent=2))
    if result.ack:
        typer.echo(json.dumps(result.ack.body, indent=2))
    if result.errors:
        for e in result.errors:
            typer.echo(e, err=True)
        raise typer.Exit(code=1)
    if not result.success:
        raise typer.Exit(code=1)
    typer.echo("Done.", err=False)


@app.command("run-scenarios")
def run_scenarios_cmd(
    root: Annotated[Optional[Path], typer.Option(help="Repository root")] = None,
    scenarios_dir: Annotated[Optional[Path], typer.Option(help="Directory of *.json scenarios")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Format B JSON path")] = None,
    base_url: Annotated[Optional[str], typer.Option(envvar="CRESCENT_BASE_URL")] = None,
    no_poll: Annotated[bool, typer.Option("--no-poll")] = False,
) -> None:
    """Run every scenario file: build → schema → rules → submit → poll; write results.json (Format B)."""
    report, out = run_batch_cli(
        root=root,
        scenarios_dir=scenarios_dir,
        output=output,
        base_url=base_url,
        poll=not no_poll,
    )
    typer.echo(f"Wrote {out}")
    code = batch_exit_code(report)
    if code != 0:
        raise typer.Exit(code=code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
