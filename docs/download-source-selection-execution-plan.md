# 下载源选择执行计划（runtime.download-sources.v1）

已实施；本文记录 `runtime.download-sources.v1` 的决策与验收，先于 Draft PR 合入，
正式版本号由 release prepare 决定（登记 `introduced_in: "2.7.0"` 为预期目标）。

## P0 落点说明（最终决策）

- 目录权威载体与引擎选择一致：OpenAPI `CapabilityDescriptor` 与 runtime-host
  `$defs.CapabilityDescriptor` 均为 `additionalProperties: false` 的 lifecycle 元数据
  载体，在同一 minor 为两者追加可选强类型字段 `download_source_catalog`。
- 选择字段落到两条通道：HTTP `SettingsSnapshot`（持久偏好，Backend 的模型下载与维护
  安装读取）与 runtime-host `RuntimeHostRequest` / `RuntimeMaintenanceCommandRequest`
  （一次性无状态 CLI，retry 支持换源）。observe 请求只读不加字段。
- 生成器无需修改；`scripts/generate_runtime_protocol.py` 机械投影两侧绑定。
- 消费者是生成绑定与手写 DTO；前端在 capability 未声明时必须省略字段。

## 1. 目标与边界

交付物：`DownloadSourceKind/Descriptor/Catalog` schema、`download_source_ids`
可选请求字段（三处 envelope）、`DOWNLOAD_SOURCE_UNKNOWN` 错误码、capability 注册、
双语言生成绑定、golden fixtures 与双语言契约测试。

非目标：自定义源 URL、源的可用性探测与测速、镜像列表内容（Backend 发布声明）、
源变更触发的自动重装策略。

## 2. 外部接口决策

- 选择只能是目录内稳定 id；未知 id 以 `DOWNLOAD_SOURCE_UNKNOWN`
  （validation/400/不可重试）fail closed，不静默回退。
- 目录 id 跨 kind 全局唯一是服务端 conformance case（schema 仅约束 uniqueItems 的
  对象级唯一，id 级唯一由实现与测试锁定，不对已发布 schema 追加条件约束）。
- 目录携带事实性 `endpoint` base URL 供前端渲染；不携带展示文案、本地化或产品默认。
- 客户端应始终发送用户当前选择；省略即服务端默认（官方源）。
- Host 将生效源反映到 `launch.environment` 是指导性 conformance 建议，具体环境变量
  名不属于 wire contract。

## 3. 分阶段工作包

- P1 修改权威协议源：openapi.yaml、runtime-host.schema.json、capabilities.json、
  bootstrap.schema.json、errors.json。
- P2 运行 `uv run python scripts/generate_runtime_protocol.py`；验收 = 重跑无二次差异。
- P3 手写层与 golden：dtos.py `SettingsSnapshot.download_source_ids`（空省略）、
  HttpV2Enums/HttpV2Records、golden 两个新 fixture 与 health 第三个 descriptor。
- P4 契约测试：`tests/contracts/v2/test_download_source_selection.py`、
  `tests/dotnet/VibeOCR.Contracts.Tests/DownloadSourceSelectionContractTests.cs`，
  同步错误注册表计数（34→35）。
- P5 文档：protocol-v2-design 章节、本计划、ADR-0001 修订说明。

## 4. 实施适配记录

- （无相对本计划的调整；错误码采用 SCREAMING_SNAKE，沿用引擎选择先例。）

## 5. 验收标准

- [x] kind 枚举跨 OpenAPI/runtime-host/双语言生成绑定单一来源。
- [x] `download_source_ids` 在三处 envelope 可选、空省略、严格数组（uniqueItems、
      minLength 1）。
- [x] capability 四处注册（capabilities.json、generated、Health known-values、
      bootstrap known-values）。
- [x] `DOWNLOAD_SOURCE_UNKNOWN` 注册表与生成投影一致、fail closed。
- [x] golden 目录经 CapabilityDescriptor schema 校验，旧 descriptor wire 形状不变。
- [x] `check-quality.ps1` 全绿；两个 Release .NET 测试项目全绿。
- [ ] 正式 Release 资产由 release 流程产出（不在本 PR 范围）。
