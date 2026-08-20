# 下载源选择执行计划（runtime.download-sources.v1）

已实施；本文记录 `runtime.download-sources.v1` 的决策与验收，先于 Draft PR 合入，
正式版本号由 release prepare 决定（登记 `introduced_in: "2.7.0"` 为预期目标）。

## P0 落点说明（最终决策）

- 目录权威载体与引擎选择一致：OpenAPI `CapabilityDescriptor` 与 runtime-host
  `$defs.CapabilityDescriptor` 均为 `additionalProperties: false` 的 lifecycle 元数据
  载体，在同一 minor 为两者追加可选强类型字段 `download_source_catalog`。
- 选择字段落到持久偏好与逐操作快照两层：HTTP `SettingsSnapshot` 保存默认偏好；HTTP
  maintenance start/retry 与 runtime-host request/retry 固化本次操作使用的 source ids。
  observe 请求只读不加字段，HTTP status 回显 requested/effective ids。
- 生成器补充开放 scalar alias 投影：Python 生成 `str` alias，C# 引用位置直接投影为
  `string`，避免生成一个不存在的封闭类型。
- 消费者是生成绑定与手写 DTO；前端在 capability 未声明时必须省略字段。

## 1. 目标与边界

交付物：`DownloadSourceKind/Descriptor/Catalog` schema、`download_source_ids`
可选请求字段（Settings、HTTP maintenance 与 Runtime Host envelopes）、
`DOWNLOAD_SOURCE_UNKNOWN` 错误码、capability 注册、
双语言生成绑定、golden fixtures 与双语言契约测试。

非目标：自定义源 URL、源的可用性探测与测速、镜像列表内容（Backend 发布声明）、
源变更触发的自动重装策略，以及 PaddleX/PaddleOCR/MinerU 原生模型下载器的 registry、
cache 或内部模型文件。

## 2. 外部接口决策

- 选择只能是目录内稳定 id；未知 id 以 `DOWNLOAD_SOURCE_UNKNOWN`
  （validation/400/不可重试）fail closed，不静默回退。
- 目录 id 跨 kind 全局唯一、一次选择每个 kind 至多一个 id 是服务端 conformance case；
  数组顺序没有优先级语义。
- 目录携带 opaque 事实性 `endpoint` base URL 供 Backend binding 与 wire 兼容；Frontend
  不展示或解析它，展示文案由产品本地化。
- 客户端发送用户当前选择；每个已发送 id 只覆盖所属 kind，未出现的 kind 使用 Backend
  为该 kind 声明的默认源；整个字段省略时所有 kind 使用 Backend 默认。
- Host 将生效源反映到 `launch.environment` 是指导性 conformance 建议，具体环境变量
  名不属于 wire contract。

## 3. 分阶段工作包

- P1 修改权威协议源：openapi.yaml、runtime-host.schema.json、capabilities.json、
  bootstrap.schema.json、errors.json。
- P2 运行 `uv run python scripts/generate_runtime_protocol.py`；验收 = 重跑无二次差异。
- P3 手写层与 golden：dtos.py Settings/maintenance source intent 与 status 回显、
  HttpV2Enums/HttpV2Records、golden 两个新 fixture 与 health 第三个 descriptor。
- P4 契约测试：`tests/contracts/v2/test_download_source_selection.py`、
  `tests/dotnet/VibeOCR.Contracts.Tests/DownloadSourceSelectionContractTests.cs`，
  同步错误注册表计数（34→35）。
- P5 文档：protocol-v2-design 章节、本计划、ADR-0001 修订说明。

## 4. 实施适配记录

- HTTP maintenance 增加逐 operation source intent/status，避免 Settings 在长操作期间
  改变导致同一 operation 换源。
- kind 由封闭 enum 改为开放 string；生成器新增 scalar alias 回归测试。
- 新 Backend 可发布 `package_index` 与 `model_registry`；客户端可编辑这两种已理解的 kind，
  并继续原样保存未来 unknown kind。`model_registry` 仅表达上游原生下载器的模型源偏好，
  不恢复 VibeOCR 自建模型资产下载、校验、修复或 binding。
- Settings/runtime status 的手写 Python parser 与 Python/.NET convenience client 同步
  新字段，避免 wire 已支持但稳定 client interface 丢值。

## 5. 验收标准

- [x] kind 是带 known-values 的开放响应字符串，旧客户端保留未知值。
- [x] `download_source_ids` 在 Settings、HTTP maintenance 与 Runtime Host envelope 可选，
      出现时非空、每个 kind 至多一个、未出现的 kind 使用其 Backend 默认，未知 id fail closed。
- [x] capability 四处注册（capabilities.json、generated、Health known-values、
      bootstrap known-values）。
- [x] `DOWNLOAD_SOURCE_UNKNOWN` 注册表与生成投影一致、fail closed。
- [x] golden 目录经 CapabilityDescriptor schema 校验，旧 descriptor wire 形状不变。
- [x] `check-quality.ps1` 全绿；两个 Release .NET 测试项目全绿。
- [ ] 正式 Release 资产由 release 流程产出（不在本 PR 范围）。
