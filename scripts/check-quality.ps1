$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    python -m ruff check packages scripts tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    python -m ruff format --check packages scripts tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    python scripts/generate_runtime_protocol.py --check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    python scripts/check_openapi_quality.py `
        --baseline packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/baselines/openapi-2.0.0.yaml `
        --current packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/openapi.yaml
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    python -m pytest tests/contracts tests/runtime
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
