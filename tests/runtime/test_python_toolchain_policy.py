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

    assert "pytest==9.0.3" in config["dependency-groups"]["dev"]
