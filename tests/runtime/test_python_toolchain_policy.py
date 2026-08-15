import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_python_version_pin_matches_the_workspace_runtime() -> None:
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.13"

    for project in (
        ROOT / "packages/vibeocr-contracts-py/pyproject.toml",
        ROOT / "packages/vibeocr-runtime-client-py/pyproject.toml",
    ):
        config = tomllib.loads(project.read_text(encoding="utf-8"))
        assert config["project"]["requires-python"] == ">=3.13,<3.14"


def test_pytest_pin_includes_the_first_patched_release() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pytest==9.1.1" in config["dependency-groups"]["dev"]


def test_uv_lock_matches_workspace_project_versions() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_versions = {
        package["name"]: package["version"]
        for package in lock["package"]
        if package["name"].startswith("vibeocr-runtime-")
    }

    for project in (
        ROOT / "packages/vibeocr-contracts-py/pyproject.toml",
        ROOT / "packages/vibeocr-runtime-client-py/pyproject.toml",
    ):
        config = tomllib.loads(project.read_text(encoding="utf-8"))
        assert (
            locked_versions[config["project"]["name"]] == config["project"]["version"]
        )


def test_ci_stops_after_a_failed_native_command() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python scripts/automation.py ci" in workflow
    assert "check-quality.ps1" not in workflow
