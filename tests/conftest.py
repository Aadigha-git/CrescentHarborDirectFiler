from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    os.environ.setdefault("CRESCENT_HARBOR_ROOT", str(root))
    return root
