"""Public CLI contract for the supported .NET lock update entrypoint."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/update_dotnet_locks.ps1"
PROJECTS = (
    "VibeOCR.Contracts.csproj",
    "VibeOCR.Runtime.Client.csproj",
    "VibeOCR.Contracts.Tests.csproj",
    "VibeOCR.Runtime.Client.Tests.csproj",
)


def test_dotnet_lock_update_entrypoint_supports_dry_run() -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")

    result = subprocess.run(
        [powershell, "-NoProfile", "-File", str(SCRIPT), "-WhatIf"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert all(project in result.stdout for project in PROJECTS)
