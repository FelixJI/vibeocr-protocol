from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_only_canonical_workflows_remain() -> None:
    assert {path.name for path in (ROOT / ".github/workflows").glob("*.yml")} == {
        "ci.yml",
        "cd.yml",
    }
    assert not (ROOT / ".release-please-manifest.json").exists()
    assert not (ROOT / "release-please-config.json").exists()


def test_ci_contract_uses_the_single_deep_interface() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pull_request:" in workflow and "branches: [main]" in workflow
    assert "  required:" in workflow and "    name: required" in workflow
    assert "python-version-file: .python-version" in workflow
    assert 'version: "0.11.16"' in workflow
    assert "actions/setup-dotnet@26b0ec14cb23fa6904739307f278c14f94c95bf1" in workflow
    assert "if: hashFiles('global.json') != ''" in workflow
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "format('ci-run-{0}', github.run_id)" in workflow
    assert "--source-sha '${{ github.sha }}'" in workflow
    assert workflow.count("python scripts/automation.py") == 1
    assert "name: release-candidate" in workflow


def test_cd_contract_downloads_exact_run_then_stages_attests_and_publishes() -> None:
    workflow = (ROOT / ".github/workflows/cd.yml").read_text(encoding="utf-8")
    publish_job = workflow.split("\n  publish:\n", maxsplit=1)[1]
    publish_permissions = publish_job.split("\n    permissions:\n", maxsplit=1)[
        1
    ].split("\n    steps:\n", maxsplit=1)[0]
    publish_checkout = publish_job.split("- uses: actions/checkout@", maxsplit=1)[
        1
    ].split("- uses: actions/setup-python@", maxsplit=1)[0]
    download = workflow.index("name: Download exact CI candidate")
    stage = workflow.index("name: Stage release")
    attest = workflow.index("name: Attest release provenance")
    publish = workflow.index("name: Publish and reconcile release")
    assert download < stage < attest < publish
    assert "run-id: ${{ github.event.workflow_run.id }}" in workflow
    assert "github.event.workflow_run.event == 'push'" in workflow
    assert "GH_TOKEN: ${{ secrets.RELEASE_TOKEN }}" in workflow
    assert {
        line.strip() for line in publish_permissions.splitlines() if line.strip()
    } == {
        "actions: read",
        "attestations: write",
        "contents: write",
        "id-token: write",
    }
    assert "ref: ${{ github.event.workflow_run.head_sha }}" in publish_checkout
    assert "fetch-depth: 0" in publish_checkout
    assert "persist-credentials: true" in publish_checkout
    assert "persist-credentials: false" not in publish_checkout
    assert "token:" not in publish_checkout
    assert "draft" not in workflow.lower()
    assert "concurrency:" not in workflow
    assert workflow.count("python scripts/automation.py") == 3


def test_project_config_declares_ordered_ci_lanes_and_optional_protocol_identity() -> (
    None
):
    config = json.loads((ROOT / ".ci/project.json").read_text(encoding="utf-8"))
    assert list(config["ci"]) == [
        "bootstrap",
        "quality",
        "e2e",
        "release_build",
        "release_smoke",
    ]
    assert config["project"]["protocol_compatibility"] == {
        "supported_majors": [2],
        "minor_compatible": True,
    }
    assert config["release"]["identity_asset"] == "build-identity.json"
