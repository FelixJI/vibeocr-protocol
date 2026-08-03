[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ArtifactsDir = 'artifacts'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$artifactPath = if ([IO.Path]::IsPathRooted($ArtifactsDir)) {
    [IO.Path]::GetFullPath($ArtifactsDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $root $ArtifactsDir))
}

$patterns = @(
    'vibeocr_runtime_contracts-*.whl',
    'vibeocr_runtime_client-*.whl',
    'VibeOCR.Runtime.Contracts.*.nupkg',
    'VibeOCR.Runtime.Client.*.nupkg'
)

if ($WhatIfPreference) {
    Write-Host "Would resolve exactly one artifact for each pattern in ${artifactPath}:"
    $patterns | ForEach-Object { Write-Host "  $_" }
    Write-Host 'Would create an isolated Python environment, install both wheels, and verify importlib.resources.'
    Write-Host 'Would create a temporary .NET project, restore both local NuGet packages, and run dotnet build.'
    return
}

if (-not (Test-Path -LiteralPath $artifactPath -PathType Container)) {
    throw "Artifacts directory does not exist: $artifactPath"
}

function Get-SingleArtifact([string]$Pattern) {
    $matches = @(Get-ChildItem -LiteralPath $artifactPath -File -Filter $Pattern)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one '$Pattern' artifact, found $($matches.Count)"
    }
    return $matches[0]
}

$contractsWheel = Get-SingleArtifact $patterns[0]
$clientWheel = Get-SingleArtifact $patterns[1]
$contractsNuGet = Get-SingleArtifact $patterns[2]
$clientNuGet = Get-SingleArtifact $patterns[3]
$version = (Get-Content -LiteralPath (Join-Path $root 'version.txt') -Raw).Trim()

if ($contractsNuGet.Name -ne "VibeOCR.Runtime.Contracts.$version.nupkg" -or
    $clientNuGet.Name -ne "VibeOCR.Runtime.Client.$version.nupkg") {
    throw "NuGet artifact names do not match repository version $version"
}

$systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
)
$smokeRoot = Join-Path $systemTemp "vibeocr-release-smoke-$([guid]::NewGuid().ToString('N'))"
$smokeRoot = [IO.Path]::GetFullPath($smokeRoot)
if (-not $smokeRoot.StartsWith("$systemTemp$([IO.Path]::DirectorySeparatorChar)", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use unsafe temporary path: $smokeRoot"
}

try {
    New-Item -ItemType Directory -Path $smokeRoot | Out-Null

    $pythonEnv = Join-Path $smokeRoot 'python'
    python -m venv $pythonEnv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed' }
    $python = Join-Path $pythonEnv 'Scripts/python.exe'
    & $python -m pip install --disable-pip-version-check $contractsWheel.FullName $clientWheel.FullName
    if ($LASTEXITCODE -ne 0) { throw 'Python wheel installation failed' }
    & $python -c "from importlib.resources import files; import vibeocr.runtime_client; root = files('vibeocr.runtime_contracts'); assert root.joinpath('openapi.yaml').is_file(); assert root.joinpath('schemas/errors.schema.json').is_file()"
    if ($LASTEXITCODE -ne 0) { throw 'Python package import/resource smoke failed' }

    $dotnetRoot = Join-Path $smokeRoot 'dotnet'
    New-Item -ItemType Directory -Path $dotnetRoot | Out-Null
    $project = Join-Path $dotnetRoot 'PackageSmoke.csproj'
    $program = Join-Path $dotnetRoot 'Program.cs'
    @"
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="VibeOCR.Runtime.Contracts" Version="$version" />
    <PackageReference Include="VibeOCR.Runtime.Client" Version="$version" />
  </ItemGroup>
</Project>
"@ | Set-Content -LiteralPath $project -Encoding utf8
    @'
using System;
using VibeOCR.Contracts.HttpV2;
using VibeOCR.Runtime.Client;

Console.WriteLine(typeof(JobSnapshot).Assembly.FullName);
Console.WriteLine(typeof(RuntimeHttpClient).Assembly.FullName);
'@ | Set-Content -LiteralPath $program -Encoding utf8

    dotnet restore $project --source $artifactPath --ignore-failed-sources
    if ($LASTEXITCODE -ne 0) { throw 'NuGet package restore smoke failed' }
    dotnet build $project --no-restore
    if ($LASTEXITCODE -ne 0) { throw '.NET package compile smoke failed' }
} finally {
    if (Test-Path -LiteralPath $smokeRoot) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force
    }
}
