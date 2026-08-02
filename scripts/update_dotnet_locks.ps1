[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$projects = @(
    "src/dotnet/VibeOCR.Contracts/VibeOCR.Contracts.csproj",
    "src/dotnet/VibeOCR.Runtime.Client/VibeOCR.Runtime.Client.csproj",
    "tests/dotnet/VibeOCR.Contracts.Tests/VibeOCR.Contracts.Tests.csproj",
    "tests/dotnet/VibeOCR.Runtime.Client.Tests/VibeOCR.Runtime.Client.Tests.csproj"
)

Push-Location $repoRoot
try {
    foreach ($project in $projects) {
        if ($PSCmdlet.ShouldProcess($project, "Update packages.lock.json")) {
            dotnet restore $project -p:UpdatePackageLocks=true
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }

    foreach ($project in $projects) {
        if ($PSCmdlet.ShouldProcess($project, "Validate locked restore")) {
            dotnet restore $project --locked-mode
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }
}
finally {
    Pop-Location
}
