#!/usr/bin/env bash
# Run the full scenario batch pipeline and write results.json (Format B).
# Requires: mock customs server reachable at CRESCENT_BASE_URL (default http://127.0.0.1:8080).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CRESCENT_HARBOR_ROOT="${CRESCENT_HARBOR_ROOT:-$ROOT}"
PYTHON="${PYTHON:-python3}"
exec "$PYTHON" -m crescent_filer.pipeline.batch_runner "$@"
