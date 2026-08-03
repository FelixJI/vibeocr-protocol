[CmdletBinding()]
param(
    [string]$Version,
    [string]$ArtifactsDir = 'artifacts'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$projectFile = Join-Path $root 'packages/vibeocr-contracts-py/pyproject.toml'
$projectVersion = (
    python -c "import pathlib,tomllib; print(tomllib.loads(pathlib.Path(r'$projectFile').read_text(encoding='utf-8'))['project']['version'])"
).Trim()
if (-not $Version) {
    $Version = $projectVersion
} else {
    $Version = $Version.TrimStart('v')
}
if ($Version -ne $projectVersion) {
    throw "Release version '$Version' does not match project version '$projectVersion'"
}
$artifacts = if ([IO.Path]::IsPathRooted($ArtifactsDir)) {
    [IO.Path]::GetFullPath($ArtifactsDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $root $ArtifactsDir))
}
$build = Join-Path $root '.release-build'
if (Test-Path -LiteralPath $artifacts) {
    Remove-Item -LiteralPath $artifacts -Recurse -Force
}
if (Test-Path -LiteralPath $build) {
    Remove-Item -LiteralPath $build -Recurse -Force
}
New-Item -ItemType Directory -Path $artifacts, $build -Force | Out-Null
uv build --wheel (Join-Path $root 'packages/vibeocr-contracts-py') --out-dir $build
if ($LASTEXITCODE -ne 0) { throw 'contracts wheel build failed' }
uv build --wheel (Join-Path $root 'packages/vibeocr-runtime-client-py') --out-dir $build
if ($LASTEXITCODE -ne 0) { throw 'client wheel build failed' }
dotnet restore (Join-Path $root 'src/dotnet/VibeOCR.Runtime.Client/VibeOCR.Runtime.Client.csproj')
if ($LASTEXITCODE -ne 0) { throw 'NuGet restore failed' }
dotnet pack (Join-Path $root 'src/dotnet/VibeOCR.Contracts/VibeOCR.Contracts.csproj') -c Release --no-restore -o $build
if ($LASTEXITCODE -ne 0) { throw 'contracts NuGet pack failed' }
dotnet pack (Join-Path $root 'src/dotnet/VibeOCR.Runtime.Client/VibeOCR.Runtime.Client.csproj') -c Release --no-restore -o $build
if ($LASTEXITCODE -ne 0) { throw 'client NuGet pack failed' }
python (Join-Path $root 'scripts/build_protocol_release_assets.py') `
  --contracts-root (Join-Path $root 'packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts') `
  --version $Version --output-dir $artifacts
if ($LASTEXITCODE -ne 0) { throw 'Protocol archive build failed' }
Copy-Item -LiteralPath (Join-Path $build "vibeocr_runtime_contracts-$Version-py3-none-any.whl") -Destination $artifacts
Copy-Item -LiteralPath (Join-Path $build "vibeocr_runtime_client-$Version-py3-none-any.whl") -Destination $artifacts
Copy-Item -LiteralPath (Join-Path $build "VibeOCR.Runtime.Contracts.$Version.nupkg") -Destination $artifacts
Copy-Item -LiteralPath (Join-Path $build "VibeOCR.Runtime.Client.$Version.nupkg") -Destination $artifacts
python (Join-Path $root 'scripts/build_release_identity.py') `
  --output (Join-Path $artifacts 'build-identity.json') `
  --version $Version `
  --source-sha (git -C $root rev-parse HEAD).Trim() `
  --openapi (Join-Path $artifacts "vibeocr-runtime-openapi-$Version.yaml")
if ($LASTEXITCODE -ne 0) { throw 'Release identity build failed' }
python (Join-Path $root 'scripts/build_spdx_sbom.py') --artifacts-dir $artifacts `
  --repository-name FelixJI/vibeocr-protocol --version $Version
if ($LASTEXITCODE -ne 0) { throw 'SBOM build failed' }
