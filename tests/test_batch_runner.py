from __future__ import annotations

from pathlib import Path

import pytest

from crescent_filer.client.http_client import SubmitResult
from crescent_filer.pipeline.batch_runner import classify_outcome, run_scenarios_batch
from crescent_filer.pipeline.config import FilerPipelineConfig
from crescent_filer.pipeline.runner import PipelineResult
from crescent_filer.polling.ack_poller import AckPollResult
from crescent_filer.rules.engine import RulesEvaluationResult
from crescent_filer.rules.findings import RuleFinding
from crescent_filer.validation.schema_validator import SchemaValidationResult


def test_classify_rejected_by_schema() -> None:
    r = PipelineResult(schema=SchemaValidationResult(ok=False, errors=[{"code": "M-102", "message": "x"}]))
    assert classify_outcome(r) == "rejected_by_schema"


def test_classify_rejected_by_rules() -> None:
    r = PipelineResult(
        schema=SchemaValidationResult(ok=True, errors=[]),
        rules=RulesEvaluationResult(
            rejections=[RuleFinding("R-001", "reject", "bad", "/manifestId")],
        ),
    )
    assert classify_outcome(r) == "rejected_by_rules"


def test_classify_accepted() -> None:
    r = PipelineResult(
        schema=SchemaValidationResult(ok=True, errors=[]),
        rules=RulesEvaluationResult(),
        submit=SubmitResult(receipt_id="R1", manifest_id="M1", status="RECEIVED", raw={}),
        ack=AckPollResult(status="ACCEPTED", body={"status": "ACCEPTED"}),
    )
    assert classify_outcome(r) == "accepted"


def test_classify_rejected_by_authority() -> None:
    r = PipelineResult(
        schema=SchemaValidationResult(ok=True, errors=[]),
        rules=RulesEvaluationResult(),
        submit=SubmitResult(receipt_id="R1", manifest_id="M1", status="RECEIVED", raw={}),
        ack=AckPollResult(status="REJECTED", body={"status": "REJECTED", "errors": []}),
    )
    assert classify_outcome(r) == "rejected_by_authority"


def test_classify_submit_failed() -> None:
    r = PipelineResult(
        schema=SchemaValidationResult(ok=True, errors=[]),
        rules=RulesEvaluationResult(),
        errors=["connection refused"],
    )
    assert classify_outcome(r) == "error"


@pytest.fixture(scope="module")
def mock_customs_server(repo_root: Path):
    import os
    import socket
    import subprocess
    import sys
    import time

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    env = os.environ.copy()
    env["CUSTOMS_PORT"] = str(port)
    env["CUSTOMS_SCHEMA_PATH"] = str(repo_root / "schema" / "manifest.schema.json")
    env["CUSTOMS_SECRETS_PATH"] = str(repo_root / "mock-customs" / "secrets.json")
    proc = subprocess.Popen(
        [sys.executable, str(repo_root / "mock-customs" / "server.py")],
        env=env,
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 15
    ok = False
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                ok = True
                break
        except OSError:
            time.sleep(0.1)
    if not ok:
        proc.terminate()
        pytest.fail("mock server did not start")
    yield port
    proc.terminate()
    proc.wait(timeout=5)


def test_run_scenarios_batch_dynamic_outcomes(repo_root: Path, mock_customs_server: int, tmp_path: Path) -> None:
    cfg = FilerPipelineConfig.from_repo(
        repo_root,
        base_url=f"http://127.0.0.1:{mock_customs_server}",
        filer_id="CHC100001",
        shared_secret="case-study-shared-secret-do-not-use-in-production-zX4qP9rL",
    )
    report = run_scenarios_batch(cfg, scenarios_dir=repo_root / "scenarios", poll=True)
    results = report["results"]
    assert len(results) >= 1
    allowed = {
        "accepted",
        "rejected_by_rules",
        "rejected_by_schema",
        "rejected_by_authority",
        "error",
    }
    for row in results:
        assert row["outcome"] in allowed
        assert "file" in row
    json_files = sorted((repo_root / "scenarios").glob("*.json"))
    assert len(results) == len(json_files)
