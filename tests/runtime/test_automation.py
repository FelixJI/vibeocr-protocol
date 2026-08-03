from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.automation_core import Automation, AutomationError, SemVer


@pytest.fixture(autouse=True)
def _isolate_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GH_TOKEN",
        "GITHUB_REPOSITORY",
        "GITHUB_WORKFLOW",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_OUTPUT",
    ):
        monkeypatch.delenv(name, raising=False)


class FakeRunner:
    def __init__(self, root: Path, sha: str = "a" * 40) -> None:
        self.root = root
        self.sha = sha
        self.calls: list[list[str]] = []
        self.environments: list[dict[str, str]] = []
        self.tags = ""
        self.releases: list[dict[str, Any]] = []
        self.prs: list[dict[str, Any]] = []
        self.cached_diff = 0
        self.plan_changed = True

    def run(
        self,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del capture, check
        self.calls.append(argv)
        self.environments.append(env or {})
        stdout = ""
        returncode = 0
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            stdout = self.sha + "\n"
        elif argv[:3] == ["git", "rev-parse", "origin/main"]:
            stdout = self.sha + "\n"
        elif argv[:3] == ["git", "tag", "--list"]:
            stdout = self.tags
        elif argv[:3] == ["git", "rev-list", "-n"]:
            returncode = 1
        elif argv[:3] == ["git", "diff", "--cached"]:
            returncode = self.cached_diff
        elif argv[:3] == ["git", "diff", "--name-only"]:
            stdout = ".release/plan.json\n" if self.plan_changed else ""
        elif argv and argv[0] == "release-build":
            assert env is not None
            output = Path(env["AUTOMATION_ARTIFACTS_DIR"])
            output.mkdir(parents=True, exist_ok=True)
            for name in ("SBOM.spdx.json", "package.zip"):
                (output / name).write_text(name, encoding="utf-8")
        return subprocess.CompletedProcess(argv, returncode, stdout, "")

    def json(self, argv: list[str], *, env: dict[str, str] | None = None) -> Any:
        del env
        self.calls.append(argv)
        self.environments.append({})
        if argv[:3] == ["gh", "pr", "list"]:
            return self.prs
        if argv[:3] == ["gh", "api", "--paginate"]:
            return self.releases
        raise AssertionError(argv)


def _config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project": {"component": "sample", "repository": "owner/sample"},
        "ci": {
            "bootstrap": [["bootstrap"]],
            "quality": [["quality"]],
            "e2e": [["e2e"]],
            "release_build": [["release-build"]],
            "release_smoke": [["release-smoke"]],
        },
        "release": {
            "version_sources": [{"kind": "text", "path": "version.txt"}],
            "generated_commands": [["generate"]],
            "required_assets": [
                "SBOM.spdx.json",
                "package.zip",
            ],
            "mirrors": [],
        },
    }


def _automation(tmp_path: Path) -> tuple[Automation, FakeRunner]:
    (tmp_path / "version.txt").write_text("1.2.3\n", encoding="utf-8")
    runner = FakeRunner(tmp_path)
    return Automation(tmp_path, _config(), runner), runner


def test_ci_runs_all_lanes_in_order_and_builds_release_once(tmp_path: Path) -> None:
    automation, runner = _automation(tmp_path)

    automation.ci(event="pull_request", source_sha=runner.sha)

    lane_calls = [call[0] for call in runner.calls if len(call) == 1]
    assert lane_calls == [
        "bootstrap",
        "quality",
        "e2e",
        "release-build",
        "release-smoke",
    ]
    report = json.loads(
        (tmp_path / "build/automation/report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "passed"
    assert [stage["name"] for stage in report["stages"]] == [
        "bootstrap",
        "quality",
        "e2e",
        "release_build",
        "release_smoke",
    ]
    assert not (tmp_path / "build/automation/release-candidate").exists()


def test_ci_activates_bootstrapped_project_environment(tmp_path: Path) -> None:
    automation, runner = _automation(tmp_path)
    scripts = tmp_path / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    scripts.mkdir(parents=True)

    automation.ci(event="pull_request", source_sha=runner.sha)

    quality_index = runner.calls.index(["quality"])
    environment = runner.environments[quality_index]
    assert environment["VIRTUAL_ENV"] == str(tmp_path / ".venv")
    assert environment["PATH"].split(os.pathsep)[0] == str(scripts)


def test_main_without_plan_emits_non_publishable_sentinel(tmp_path: Path) -> None:
    automation, runner = _automation(tmp_path)

    automation.ci(event="push", source_sha=runner.sha)

    candidate = tmp_path / "build/automation/release-candidate"
    state = json.loads((candidate / "release-state.json").read_text(encoding="utf-8"))
    assert state == {
        "publish": False,
        "reason": "no-pending-plan",
        "schema_version": 1,
        "source_sha": runner.sha,
    }
    assert {path.name for path in candidate.iterdir()} == {"release-state.json"}


def test_pending_main_wraps_the_smoke_tested_artifacts_without_rebuild(
    tmp_path: Path,
) -> None:
    automation, runner = _automation(tmp_path)
    plan = {
        "schema_version": 1,
        "state": "pending",
        "bump": "patch",
        "version": "1.2.3",
        "tag": "v1.2.3",
    }
    (tmp_path / ".release").mkdir()
    (tmp_path / ".release/plan.json").write_text(json.dumps(plan), encoding="utf-8")

    automation.ci(event="push", source_sha=runner.sha)

    assert sum(call == ["release-build"] for call in runner.calls) == 1
    candidate = tmp_path / "build/automation/release-candidate"
    manifest = json.loads((candidate / "release-manifest.json").read_text())
    assert manifest["source"] == {"sha": runner.sha}
    assert manifest["project"] == {
        "component": "sample",
        "repository": "owner/sample",
    }
    assert manifest["protocol"] is None
    assert set(manifest["artifacts"]) == {"SBOM.spdx.json", "package.zip"}


def test_stage_rejects_tampering_and_writes_multiline_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    automation, runner = _automation(tmp_path)
    (tmp_path / ".release").mkdir()
    (tmp_path / ".release/plan.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "pending",
                "version": "1.2.3",
                "tag": "v1.2.3",
            }
        ),
        encoding="utf-8",
    )
    automation.ci(event="push", source_sha=runner.sha)
    candidate = tmp_path / "build/automation/release-candidate"
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    automation.stage(candidate_dir=str(candidate), source_sha=runner.sha)

    content = output.read_text(encoding="utf-8")
    assert "publish=true\n" in content
    assert "checksums<<AUTOMATION_" in content
    assert "sbom<<AUTOMATION_" in content
    (candidate / "package.zip").write_text("tampered", encoding="utf-8")
    with pytest.raises(AutomationError, match="checksum mismatch"):
        automation.stage(candidate_dir=str(candidate), source_sha=runner.sha)


def test_publish_refuses_to_move_an_existing_stable_tag(tmp_path: Path) -> None:
    automation, runner = _automation(tmp_path)
    (tmp_path / ".release").mkdir()
    (tmp_path / ".release/plan.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "pending",
                "version": "1.2.3",
                "tag": "v1.2.3",
            }
        ),
        encoding="utf-8",
    )
    automation.ci(event="push", source_sha=runner.sha)
    candidate = tmp_path / "build/automation/release-candidate"
    automation._tag_sha = lambda _tag: "b" * 40  # type: ignore[method-assign]

    with pytest.raises(
        AutomationError,
        match="stable tags are immutable and this tag has another source",
    ):
        automation.publish(candidate_dir=str(candidate), source_sha=runner.sha)

    assert all(call[:2] != ["git", "tag"] for call in runner.calls)
    assert all(call[:2] != ["git", "push"] for call in runner.calls)


def test_prepare_uses_orphan_stable_tag_for_version_but_release_for_changelog(
    tmp_path: Path,
) -> None:
    automation, runner = _automation(tmp_path)
    runner.tags = "v1.2.3\nv2.0.0\nv3.0.0-rc.1\n"
    runner.releases = [
        {
            "id": 7,
            "tag_name": "v1.5.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": 8,
            "tag_name": "v9.0.0-rc.1",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-02-01T00:00:00Z",
        },
    ]
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    automation.prepare(bump="patch")

    plan = json.loads((tmp_path / ".release/plan.json").read_text(encoding="utf-8"))
    assert plan["baseline_version"] == "2.0.0"
    assert plan["version"] == "2.0.1"
    assert plan["changelog_base_tag"] == "v1.5.0"
    assert (tmp_path / "version.txt").read_text(encoding="utf-8").strip() == "2.0.1"
    generate_call = next(call for call in runner.calls if call == ["generate"])
    assert generate_call == ["generate"]
    generate_index = runner.calls.index(["generate"])
    assert (
        runner.environments[generate_index]["AUTOMATION_CHANGELOG_BASE_TAG"] == "v1.5.0"
    )


def test_complete_published_release_turns_old_pending_plan_into_sentinel(
    tmp_path: Path,
) -> None:
    automation, runner = _automation(tmp_path)
    (tmp_path / ".release").mkdir()
    (tmp_path / ".release/plan.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "pending",
                "version": "1.2.3",
                "tag": "v1.2.3",
            }
        ),
        encoding="utf-8",
    )
    release = {
        "assets": [
            {"name": name}
            for name in (
                "SBOM.spdx.json",
                "package.zip",
                "release-manifest.json",
                "SHA256SUMS",
            )
        ]
    }
    automation._published_release = lambda _tag: release  # type: ignore[method-assign]
    automation._tag_sha = lambda _tag: "b" * 40  # type: ignore[method-assign]
    automation._remote_manifest = lambda _tag: {  # type: ignore[method-assign]
        "release": {"tag": "v1.2.3", "version": "1.2.3"},
        "source": {"sha": "b" * 40},
        "project": {"component": "sample", "repository": "owner/sample"},
        "build_identity": None,
        "protocol": None,
    }
    automation._verify_remote_release_assets = (  # type: ignore[method-assign]
        lambda _tag, _assets, _identity: None
    )

    automation.ci(event="push", source_sha=runner.sha)

    state = json.loads(
        (tmp_path / "build/automation/release-candidate/release-state.json").read_text()
    )
    assert state["reason"] == "already-published"


def test_complete_release_rejects_different_build_or_protocol_identity(
    tmp_path: Path,
) -> None:
    automation, runner = _automation(tmp_path)
    (tmp_path / ".release").mkdir()
    (tmp_path / ".release/plan.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "pending",
                "version": "1.2.3",
                "tag": "v1.2.3",
            }
        ),
        encoding="utf-8",
    )
    automation._published_release = lambda _tag: {  # type: ignore[method-assign]
        "assets": [
            {"name": name}
            for name in (
                "SBOM.spdx.json",
                "package.zip",
                "release-manifest.json",
                "SHA256SUMS",
            )
        ]
    }
    automation._tag_sha = lambda _tag: runner.sha  # type: ignore[method-assign]
    automation._remote_manifest = lambda _tag: {  # type: ignore[method-assign]
        "release": {"tag": "v1.2.3", "version": "1.2.3"},
        "source": {"sha": runner.sha},
        "project": {"component": "sample", "repository": "owner/sample"},
        "build_identity": {"asset": "other.json"},
        "protocol": {"version": "9.0.0"},
    }

    with pytest.raises(AutomationError, match="manifest identity mismatch"):
        automation.ci(event="push", source_sha=runner.sha)


def test_incomplete_published_release_cannot_be_repaired_by_another_source(
    tmp_path: Path,
) -> None:
    automation, runner = _automation(tmp_path)
    (tmp_path / ".release").mkdir()
    (tmp_path / ".release/plan.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "pending",
                "version": "1.2.3",
                "tag": "v1.2.3",
            }
        ),
        encoding="utf-8",
    )
    automation._published_release = lambda _tag: {  # type: ignore[method-assign]
        "assets": [{"name": "release-manifest.json"}]
    }
    automation._tag_sha = lambda _tag: "b" * 40  # type: ignore[method-assign]
    automation._remote_manifest = lambda _tag: {  # type: ignore[method-assign]
        "release": {"tag": "v1.2.3", "version": "1.2.3"},
        "source": {"sha": "b" * 40},
        "project": {"component": "sample", "repository": "owner/sample"},
    }

    with pytest.raises(AutomationError, match="different source cannot repair"):
        automation.ci(event="push", source_sha=runner.sha)


def test_unchanged_old_plan_never_creates_a_new_candidate(tmp_path: Path) -> None:
    automation, runner = _automation(tmp_path)
    runner.plan_changed = False
    (tmp_path / ".release").mkdir()
    (tmp_path / ".release/plan.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "pending",
                "version": "1.2.3",
                "tag": "v1.2.3",
            }
        ),
        encoding="utf-8",
    )

    automation.ci(event="push", source_sha=runner.sha)

    state = json.loads(
        (tmp_path / "build/automation/release-candidate/release-state.json").read_text()
    )
    assert state["reason"] == "plan-unchanged"


def test_changelog_footer_overrides_and_dependency_scope(tmp_path: Path) -> None:
    automation, runner = _automation(tmp_path)
    commits = (
        "a" * 40
        + "\x1fchore(deps): upgrade sdk\x1f\x1e"
        + "b" * 40
        + "\x1fdocs: operator guide\x1fChangelog: include\x1e"
        + "c" * 40
        + "\x1ffeat: hidden feature\x1fChangelog: skip\x1e"
    )
    original = runner.run

    def with_log(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["git", "log"]:
            return subprocess.CompletedProcess(argv, 0, commits, "")
        return original(argv, env=env, capture=capture, check=check)

    runner.run = with_log  # type: ignore[method-assign]
    notes = automation._release_notes(SemVer(1, 2, 4), "v1.2.3")
    assert "### Dependencies" in notes and "upgrade sdk" in notes
    assert "operator guide" in notes
    assert "hidden feature" not in notes


def test_open_release_pr_with_a_different_bump_fails_closed(tmp_path: Path) -> None:
    automation, runner = _automation(tmp_path)
    runner.prs = [
        {
            "number": 12,
            "headRefName": "automation/release",
            "title": "chore(release): 1.2.4",
        }
    ]

    def show_existing(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if argv[:2] == ["git", "show"]:
            return subprocess.CompletedProcess(
                argv, 0, json.dumps({"bump": "minor"}), ""
            )
        return FakeRunner.run(runner, argv, env=env, capture=capture, check=check)

    runner.run = show_existing  # type: ignore[method-assign]
    with pytest.raises(AutomationError, match="refusing patch"):
        automation.prepare(bump="patch")


def test_semver_rejects_prerelease_and_bumps_stably() -> None:
    assert str(SemVer.parse("2.3.4").bump("minor")) == "2.4.0"
    assert str(SemVer.parse_project("0.1.0-preview.4").bump("minor")) == "0.2.0"
    with pytest.raises(AutomationError, match="stable SemVer"):
        SemVer.parse("2.3.4-rc.1")


def test_version_adapters_read_prerelease_python_yaml_and_derived_uv_lock(
    tmp_path: Path,
) -> None:
    (tmp_path / "version.py").write_text(
        'try:\n    __version__ = "0.1.0-preview.4"\n', encoding="utf-8"
    )
    (tmp_path / "openapi.yaml").write_text(
        'info:\n  version: "0.1.0-preview.4"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "sample"\nversion = "0.1.0-preview.4"\n',
        encoding="utf-8",
    )
    config = _config()
    config["release"]["version_sources"] = [
        {"kind": "python", "path": "version.py", "key": "__version__"},
        {"kind": "yaml", "path": "openapi.yaml", "key": "info.version"},
        {
            "kind": "uv-lock",
            "path": "uv.lock",
            "key": "sample",
            "derived": True,
        },
    ]
    automation = Automation(tmp_path, config, FakeRunner(tmp_path))

    assert automation.current_version() == SemVer(0, 1, 0)
    automation._replace_version(
        config["release"]["version_sources"][0], SemVer(0, 2, 0)
    )
    automation._replace_version(
        config["release"]["version_sources"][1], SemVer(0, 2, 0)
    )
    assert '    __version__ = "0.2.0"' in (tmp_path / "version.py").read_text(
        encoding="utf-8"
    )
    assert 'version: "0.2.0"' in (tmp_path / "openapi.yaml").read_text(encoding="utf-8")
    with pytest.raises(AutomationError, match="derived"):
        automation._replace_version(
            config["release"]["version_sources"][2], SemVer(0, 2, 0)
        )


def test_cli_help_exposes_only_the_stable_command_families() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [os.sys.executable, "scripts/automation.py", "--help"],
        cwd=root,
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    assert "{ci,release}" in result.stdout
