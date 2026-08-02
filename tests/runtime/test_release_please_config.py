import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_CHANGELOG_SECTIONS = [
    {"type": "feat", "section": "Features"},
    {"type": "fix", "section": "Bug Fixes"},
    {"type": "perf", "section": "Performance Improvements"},
    {"type": "security", "section": "Security"},
    {"type": "deps", "section": "Dependencies"},
    {"type": "build", "section": "Build and Packaging"},
    {"type": "revert", "section": "Reverts"},
    {"type": "docs", "section": "Documentation", "hidden": True},
    {"type": "refactor", "section": "Code Refactoring", "hidden": True},
    {"type": "test", "section": "Tests", "hidden": True},
    {"type": "ci", "section": "Continuous Integration", "hidden": True},
    {"type": "style", "section": "Styles", "hidden": True},
    {"type": "chore", "section": "Miscellaneous Chores", "hidden": True},
]


def test_release_please_uses_the_shared_changelog_filter() -> None:
    config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )

    assert config["changelog-sections"] == EXPECTED_CHANGELOG_SECTIONS


def test_manual_release_passes_requested_version_to_manifest_cli() -> None:
    workflow = (ROOT / ".github/workflows/release-please.yml").read_text(
        encoding="utf-8"
    )
    manual_job = workflow.split("  draft-release:", maxsplit=1)[0]

    assert "release-please@17.6.0 release-pr" in manual_job
    assert '--release-as="${{ steps.version.outputs.next }}"' in manual_job
    assert "--config-file=release-please-config.json" in manual_job
    assert "--manifest-file=.release-please-manifest.json" in manual_job
    assert "googleapis/release-please-action" not in manual_job


def test_release_please_updates_the_formal_openapi_version() -> None:
    config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )
    extra_files = config["packages"]["."]["extra-files"]

    assert {
        "type": "json",
        "path": "packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/openapi.yaml",
        "jsonpath": "$.info.version",
    } in extra_files


def test_manual_release_syncs_lock_and_generated_files_to_the_release_pr() -> None:
    workflow = (ROOT / ".github/workflows/release-please.yml").read_text(
        encoding="utf-8"
    )
    manual_job = workflow.split("  draft-release:", maxsplit=1)[0]

    create_release_pr = "release-please@17.6.0 release-pr"
    synchronize = "Synchronize Release PR lock and generated files"

    assert manual_job.index(create_release_pr) < manual_job.index(synchronize)
    assert 'label "autorelease: pending"' in manual_job
    assert "uv lock" in manual_job
    assert "uv sync --locked --group dev" in manual_job
    assert "python scripts/generate_runtime_protocol.py" in manual_job
    assert "git diff --name-only" in manual_job
    assert "Unexpected generated file" in manual_job
    assert 'git push origin "HEAD:refs/heads/${release_branch}"' in manual_job
