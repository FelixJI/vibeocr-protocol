import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_release_package_smoke_script_exposes_a_safe_dry_run() -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is not available")

    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(ROOT / "scripts/smoke_release_packages.ps1"),
            "-ArtifactsDir",
            str(ROOT / "artifacts"),
            "-WhatIf",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "vibeocr_runtime_contracts-*.whl" in output
    assert "vibeocr_runtime_client-*.whl" in output
    assert "VibeOCR.Runtime.Contracts.*.nupkg" in output
    assert "VibeOCR.Runtime.Client.*.nupkg" in output
    assert "importlib.resources" in output
    assert "dotnet build" in output
    assert "using System;" in (ROOT / "scripts/smoke_release_packages.ps1").read_text(
        encoding="utf-8"
    )
