from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from crescent_filer.builder.manifest_builder import build_from_scenario_dict, load_scenario_path
from crescent_filer.models.manifest import FilerInfo, FilerSignature
from crescent_filer.pipeline.config import FilerPipelineConfig
from crescent_filer.pipeline.runner import run_pipeline
from crescent_filer.rules.context import RulesContext
from datetime import datetime, timedelta


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def mock_customs_server(repo_root: Path):
    port = _free_port()
    env = os.environ.copy()
    env["CUSTOMS_PORT"] = str(port)
    env["CUSTOMS_SCHEMA_PATH"] = str(repo_root / "schema" / "manifest.schema.json")
    env["CUSTOMS_SECRETS_PATH"] = str(repo_root / "mock-customs" / "secrets.json")
    proc = subprocess.Popen(
        [sys.executable, str(repo_root / "mock-customs" / "server.py")],
        env=env,
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
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
        err = proc.stderr.read().decode() if proc.stderr else ""
        pytest.fail(f"mock server did not start: {err}")
    yield port
    proc.terminate()
    proc.wait(timeout=5)


def test_submit_and_poll_accepted(repo_root: Path, mock_customs_server: int) -> None:
    scenario = load_scenario_path(repo_root / "scenarios" / "01-aurora-borealis.json")
    filer = FilerInfo(filer_id="CHC100001", legal_name="Test Filer", contact_email="ops@example.com")
    sig = FilerSignature(signer_name="A", signer_title="B", signed_at_utc="2026-01-01T12:00:00Z")
    manifest = build_from_scenario_dict(scenario, filer=filer, filer_signature=sig, eta_offset_hours=48.0)
    eta = datetime.fromisoformat(manifest["arrival"]["eta"].replace("Z", "+00:00"))
    transmit = eta - timedelta(hours=48)
    ctx = RulesContext(transmit_time_utc=transmit)
    cfg = FilerPipelineConfig.from_repo(
        repo_root,
        base_url=f"http://127.0.0.1:{mock_customs_server}",
        filer_id="CHC100001",
        shared_secret="case-study-shared-secret-do-not-use-in-production-zX4qP9rL",
    )
    result = run_pipeline(manifest, cfg, rules_context=ctx, poll=True)
    assert result.submit is not None
    assert result.ack is not None
    assert result.ack.status == "ACCEPTED"
    assert not result.errors
