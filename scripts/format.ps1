$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    python -m ruff check --fix packages scripts tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    python -m ruff format packages scripts tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
