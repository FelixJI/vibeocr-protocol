[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$artifacts = Join-Path $root 'artifacts'
$build = Join-Path $root '.release-build'
if (Test-Path -LiteralPath $artifacts) {
    Remove-Item -LiteralPath $artifacts -Recurse -Force
}
if (Test-Path -LiteralPath $build) {
    Remove-Item -LiteralPath $build -Recurse -Force
}
New-Item -ItemType Directory -Path $artifacts, $build -Force | Out-Null
python -m pip install build==1.5.0 hatchling==1.27.0
python -m build --wheel --no-isolation (Join-Path $root 'packages/vibeocr-contracts-py') --outdir $build
if ($LASTEXITCODE -ne 0) { throw 'contracts wheel build failed' }
python -m build --wheel --no-isolation (Join-Path $root 'packages/vibeocr-runtime-client-py') --outdir $build
if ($LASTEXITCODE -ne 0) { throw 'client wheel build failed' }
dotnet restore (Join-Path $root 'src/dotnet/VibeOCR.Runtime.Client/VibeOCR.Runtime.Client.csproj')
if ($LASTEXITCODE -ne 0) { throw 'NuGet restore failed' }
dotnet pack (Join-Path $root 'src/dotnet/VibeOCR.Contracts/VibeOCR.Contracts.csproj') -c Release --no-restore -o $build
if ($LASTEXITCODE -ne 0) { throw 'contracts NuGet pack failed' }
dotnet pack (Join-Path $root 'src/dotnet/VibeOCR.Runtime.Client/VibeOCR.Runtime.Client.csproj') -c Release --no-restore -o $build
if ($LASTEXITCODE -ne 0) { throw 'client NuGet pack failed' }
python (Join-Path $root 'scripts/build_protocol_release_assets.py') `
  --contracts-root (Join-Path $root 'packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts') `
  --version 2.0.0 --output-dir $artifacts
if ($LASTEXITCODE -ne 0) { throw 'Protocol archive build failed' }
Copy-Item -LiteralPath (Join-Path $build 'vibeocr_runtime_contracts-2.0.0-py3-none-any.whl') -Destination $artifacts
Copy-Item -LiteralPath (Join-Path $build 'vibeocr_runtime_client-2.0.0-py3-none-any.whl') -Destination $artifacts
Copy-Item -LiteralPath (Join-Path $build 'VibeOCR.Runtime.Contracts.2.0.0.nupkg') -Destination $artifacts
Copy-Item -LiteralPath (Join-Path $build 'VibeOCR.Runtime.Client.2.0.0.nupkg') -Destination $artifacts
python (Join-Path $root 'scripts/build_spdx_sbom.py') --artifacts-dir $artifacts `
  --repository-name FelixJI/vibeocr-protocol --version 2.0.0
if ($LASTEXITCODE -ne 0) { throw 'SBOM build failed' }
$inputs = Get-ChildItem -LiteralPath $artifacts -File | ForEach-Object {
    @('--artifact', $_.FullName)
}
$arguments = @(
    (Join-Path $root 'scripts/build_protocol_release_manifest.py'),
    '--protocol-version', '2.0.0',
    '--source-commit', (git -C $root rev-parse HEAD).Trim(),
    '--build-workflow', 'github.com/FelixJI/vibeocr-protocol/.github/workflows/release.yml',
    '--output-dir', $artifacts
) + $inputs
python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Protocol manifest build failed' }
python (Join-Path $root 'scripts/build_release_checksums.py') $artifacts
if ($LASTEXITCODE -ne 0) { throw 'checksum build failed' }
