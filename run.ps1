# Run the full scenario batch pipeline and write results.json (Format B).
# Requires: mock customs server (e.g. mock-customs\server.py) at CRESCENT_BASE_URL.
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $env:CRESCENT_HARBOR_ROOT) { $env:CRESCENT_HARBOR_ROOT = $Root }
$py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
& $py -m crescent_filer.pipeline.batch_runner @args
exit $LASTEXITCODE
