# Contributing

新功能、修复和问题反馈统一进入 [VibeOCR Next Issues](https://github.com/FelixJI/vibeocr-next/issues)，开发规则以 [Next CONTRIBUTING](https://github.com/FelixJI/vibeocr-next/blob/main/CONTRIBUTING.md) 为准。本仓仅保留历史源码和发布资产，不再承接新的业务开发；下列规则用于理解历史提交和维护记录。

## Protocol changes

Treat `packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/openapi.yaml`
as the formal HTTP contract. Edit source specifications and registries, then run:

```powershell
python scripts/generate_runtime_protocol.py
./scripts/check-quality.ps1
```

Do not hand-edit generated bindings or `schemas/errors.schema.json`. The
compatibility gate compares the current OpenAPI document with the committed v2
baseline. Requests remain strict; responses may add optional fields without a
major-version bump and clients must retain those fields.

For .NET dependency changes, update and validate all lock files together:

```powershell
./scripts/update_dotnet_locks.ps1 -WhatIf
./scripts/update_dotnet_locks.ps1
```

Release candidates are built by `scripts/build-release.ps1`. Validate the
resulting wheels and NuGet packages as consumers would install them:

```powershell
./scripts/smoke_release_packages.ps1 -ArtifactsDir artifacts
```

Application code should prefer `VibeOCR.Contracts.HttpV2` for the stable .NET
domain-facing records. `VibeOCR.Runtime.Contracts.Generated.Wire` is the
mechanically generated wire view and may change whenever the formal schema is
regenerated.

## Commits and changelog

Use Conventional Commit titles and squash merge pull requests so the final
commit is the release-note source of truth.

- Release notes include `feat`, `fix`, `perf`, `security`, `deps`,
  `build`, and `revert`.
- Repository-only maintenance types `docs`, `refactor`, `test`, `ci`,
  `style`, and `chore` are intentionally hidden.
- Choose the type that describes the actual change. Do not relabel maintenance
  work merely to make it appear in the changelog.
