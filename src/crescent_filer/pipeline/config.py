from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def default_repo_root() -> Path:
    env = os.environ.get("CRESCENT_HARBOR_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


@dataclass
class FilerPipelineConfig:
    base_url: str
    filer_id: str
    shared_secret: str
    schema_path: Path
    rules_path: Path
    legal_name: str = "Case Study Filer LLC"
    contact_email: str = "filer@example.com"
    signer_name: str = "Alex Director"
    signer_title: str = "Director of Compliance"
    http_timeout: float = 60.0

    @classmethod
    def from_repo(
        cls,
        root: Path | None = None,
        *,
        base_url: str | None = None,
        filer_id: str | None = None,
        shared_secret: str | None = None,
        secrets_path: Path | None = None,
    ) -> FilerPipelineConfig:
        root = (root or default_repo_root()).resolve()
        schema_path = root / "schema" / "manifest.schema.json"
        rules_path = root / "rules" / "rules.json"
        base = base_url or os.environ.get("CRESCENT_BASE_URL", "http://127.0.0.1:8080")
        fid = filer_id or os.environ.get("CRESCENT_FILER_ID", "CHC100001")
        secret = shared_secret or os.environ.get("CRESCENT_SHARED_SECRET")
        if not secret:
            sec_path = secrets_path or Path(
                os.environ.get("CRESCENT_SECRETS_PATH", str(root / "mock-customs" / "secrets.json"))
            )
            with sec_path.open(encoding="utf-8") as f:
                secrets = json.load(f)
            secret = secrets[fid]
        return cls(
            base_url=base.rstrip("/"),
            filer_id=fid,
            shared_secret=secret,
            schema_path=schema_path,
            rules_path=rules_path,
        )


def load_config_from_env() -> FilerPipelineConfig:
    return FilerPipelineConfig.from_repo()
