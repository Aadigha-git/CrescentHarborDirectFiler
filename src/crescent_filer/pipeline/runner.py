from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crescent_filer.client.http_client import CustomsHttpClient, SubmitResult
from crescent_filer.models.manifest import FilerInfo, FilerSignature
from crescent_filer.polling.ack_poller import AckPollResult, poll_until_terminal
from crescent_filer.pipeline.config import FilerPipelineConfig
from crescent_filer.rules.context import RulesContext
from crescent_filer.rules.engine import RulesEvaluationResult, evaluate_rules
from crescent_filer.validation.schema_validator import SchemaValidationResult, validate_manifest_schema


@dataclass
class PipelineResult:
    schema: SchemaValidationResult | None = None
    rules: RulesEvaluationResult | None = None
    submit: SubmitResult | None = None
    ack: AckPollResult | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        if self.errors:
            return False
        if self.schema and not self.schema.ok:
            return False
        if self.rules and not self.rules.ok:
            return False
        if self.ack and self.ack.status == "REJECTED":
            return False
        return True


def _filer_signature_now(cfg: FilerPipelineConfig, *, signed_at_utc: datetime | None = None) -> FilerSignature:
    at = signed_at_utc or datetime.now(timezone.utc)
    ts = at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return FilerSignature(
        signer_name=cfg.signer_name,
        signer_title=cfg.signer_title,
        signed_at_utc=ts,
    )


def load_manifest_or_scenario(
    path: Path,
    cfg: FilerPipelineConfig,
    *,
    reference_time_utc: datetime | None = None,
) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "manifestId" in raw and "filer" in raw:
        return raw
    from crescent_filer.builder.manifest_builder import build_from_scenario_dict

    filer = FilerInfo(
        filer_id=cfg.filer_id,
        legal_name=cfg.legal_name,
        contact_email=cfg.contact_email,
    )
    ref = reference_time_utc or datetime.now(timezone.utc)
    sig = _filer_signature_now(cfg, signed_at_utc=ref)
    return build_from_scenario_dict(raw, filer=filer, filer_signature=sig, reference_time_utc=ref)


def run_pipeline(
    manifest: dict[str, Any],
    cfg: FilerPipelineConfig,
    *,
    rules_context: RulesContext | None = None,
    poll: bool = True,
) -> PipelineResult:
    out = PipelineResult()
    out.schema = validate_manifest_schema(manifest, schema_path=cfg.schema_path)
    if not out.schema.ok:
        out.errors.extend(e["message"] for e in out.schema.errors)
        return out

    ctx = rules_context or RulesContext.utc_now()
    out.rules = evaluate_rules(manifest, rules_path=cfg.rules_path, context=ctx)
    if not out.rules.ok:
        out.errors.extend(f"{f.rule_id}: {f.message}" for f in out.rules.rejections)
        return out

    client = CustomsHttpClient(
        cfg.base_url,
        cfg.filer_id,
        cfg.shared_secret,
        timeout=cfg.http_timeout,
    )
    try:
        out.submit = client.submit_manifest(manifest)
    except Exception as exc:
        out.errors.append(str(exc))
        return out

    if poll:
        try:
            out.ack = poll_until_terminal(client, out.submit.receipt_id)
            if out.ack.status == "REJECTED":
                errs = out.ack.body.get("errors") or []
                for e in errs:
                    out.errors.append(f"{e.get('code')}: {e.get('message')}")
        except Exception as exc:
            out.errors.append(str(exc))
    return out
