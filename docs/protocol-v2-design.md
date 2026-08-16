# HTTP v2 协议设计

## 单一事实源

正式 HTTP 合同是
`packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/openapi.yaml`。
`errors.json` 是错误码、分类和可重试性的注册表，`capabilities.json`、
`bootstrap.schema.json` 与 `runtime-host.schema.json` 分别定义能力名称、进程启动握手
和一次性 Runtime Host 控制面。生成脚本把这些来源投影为 Python 类型、C# wire 类型、
服务端校验元数据和独立错误 Schema。

生成产物不得独立演进。CI 运行 `generate_runtime_protocol.py --check`，以阻止规范与
语言绑定漂移。

## 兼容性方向

Protocol SDK 的 minor/package 版本不是 Runtime 的最低版本，Backend Release 内精确绑定的
Protocol wheel 也不是客户端 SDK 的版本上限。Backend 的精确绑定用于构建复现、资产证明和
离线安装闭包；客户端只按 Protocol major 和 capability 判断运行兼容性。

同一 major 必须同时支持 Backend 先发布和客户端先发布。兼容性取决于数据流方向：

- 服务端接收的既有请求必须保持双向兼容。改变必填性、类型、约束、枚举或
  `oneOf` / `anyOf` / `allOf` 分支都属于破坏性变更。新增可选请求字段只能承载由
  capability 保护的新行为；客户端在 Runtime 未声明该 capability 时必须省略该字段。
- 客户端接收的响应必须容忍新增可选字段，并原样保留未知字段。删除字段、把可选字段
  变为必填、改变既有字段的类型、约束、封闭枚举或组合分支仍属于破坏性变更。将封闭
  `enum` 一次性迁移为同类型的 `x-vibeocr-known-values` 属于兼容性修复，但必须保留全部
  旧值；该扩展只记录已知值，客户端仍须原样保留未知字符串。
- 新增 capability 不要求旧客户端升级。旧客户端保留未知字符串，但只有理解该能力时
  才能使用它。
- 新 SDK 可以先于实现该能力的 Backend 发布，但必须在 capability 缺失时隐藏、禁用或
  使用兼容 fallback；不得用 SDK minor 与 Backend 精确绑定版本的大小关系代替协商。
- 提高安全要求（例如公开操作改为需要认证）属于破坏性变更。

这些规则由 `scripts/check_openapi_quality.py` 执行。真正改变既有语义时，应发布新的
协议主版本，而不是放宽解析器来制造表面兼容。

## 维护状态与进度

- Runtime 尚未可启动时，由父进程拥有的一次性 Host 通过 stdio 通信。请求只有显式声明
  `accepted_event_streams=["ndjson.v1"]` 才会收到多行事件；未声明时继续只输出最终 JSON。
- Supervisor ready 后，`GET /v2/runtime/status` 是服务状态、Backend 版本、当前 profile、
  功能依赖分组及当前 maintenance snapshot 的权威快照。`health` 保持轻量探针，
  `runtime/residency` 继续只负责已加载 pipeline/显存信息。
- `ProgressSnapshot.total` 可省略；省略代表 indeterminate，客户端不得伪造百分比。
  `StageEvent` 与 `JobSnapshot` 的 typed progress 是可选扩展，旧字段继续保留。
- 原始安装日志不属于 wire contract。UI 使用稳定 `message_code`、功能 `component_id` 和
  可选脱敏 fallback，不能解析 pip 输出、索引 URL 或本地路径。

## OCR 引擎选择（ocr.engine-selection.v1）

通用文本 `OCR` pipeline 的引擎选择是强类型、可协商的 minor 扩展：

- 稳定引擎 ID 只有 `rapidocr`、`windows`、`paddleocr`，唯一事实源是 OpenAPI
  `OcrEngineId` 枚举；Python `dtos.OcrEngine`、生成 TypedDict/Literal 与 .NET
  `OcrEngine`/`OcrEngineId` 枚举全部由它投影，wire value 完全一致。
- `PipelineSelection.engine` 是可选请求字段。客户端应始终显式发送用户当前选择；
  省略时由 Backend 应用服务端默认引擎（本项目约定 `rapidocr`）。未知值必须以
  `OCR_ENGINE_UNKNOWN` fail closed，不得静默回退到其他引擎。
- 该字段仅对 `pipeline_id == "OCR"` 合法。由于 `check_openapi_quality.py` 禁止对已
  发布请求 schema 追加 `allOf`/条件约束，此限制不写入 schema，而是登记为服务端
  conformance case：Backend 对其他 pipeline 返回 `OCR_ENGINE_NOT_VALID_FOR_PIPELINE`，
  不静默忽略。
- 运行时可用性目录 `OcrEngineCatalog` 挂在既有 capability descriptor 载体上：OpenAPI
  `CapabilityDescriptor` 与 runtime-host `$defs.CapabilityDescriptor` 均新增可选字段
  `ocr_engine_catalog`，仅 `ocr.engine-selection.v1` descriptor 携带。每个
  `OcrEngineDescriptor` 表达 `id`、`availability`（`ready` / `preparation_required` /
  `unavailable`）、`included_in_base`、`reason_code`（稳定机器可读原因，UI 自行本地化）
  与 `required_component`（对应 `runtime.component-repair.v1` 组件 ID，可空）。目录只
  表达能力与状态，不表达产品默认值或展示文案。
- 稳定错误码：`OCR_ENGINE_UNKNOWN`（validation/400）、
  `OCR_ENGINE_NOT_VALID_FOR_PIPELINE`（validation/400）、
  `OCR_ENGINE_UNAVAILABLE`（capability/426）、
  `OCR_ENGINE_PREPARATION_REQUIRED`（capability/428）、
  `OCR_ENGINE_LANGUAGE_UNAVAILABLE`（capability/426），全部不可重试。错误保持既有
  `Error` 形状与 job/request 关联；Backend 可通过开放的 `detail` 对象附带当前可选引擎
  ID，是否切换由用户决定，前端不得据此自动降级。
- 未来新增引擎 ID 属于对请求/响应封闭枚举的追加，会被兼容门禁拦截；届时必须先在六仓
  协调评估开放策略（`x-vibeocr-known-values` 或新 major），不得直接扩枚举。

## 下载源选择（runtime.download-sources.v1）

依赖安装源与模型下载源的用户选择是可协商的 minor 扩展，复用引擎选择的目录模式：

- 源目录 `DownloadSourceCatalog` 挂在既有 capability descriptor 载体上：OpenAPI
  `CapabilityDescriptor` 与 runtime-host `$defs.CapabilityDescriptor` 均新增可选字段
  `download_source_catalog`，仅 `runtime.download-sources.v1` descriptor 携带。每个
  `DownloadSourceDescriptor` 表达 `kind`（`package_index` / `model_registry`）、稳定
  `id` 与事实性 `endpoint` base URL；目录不携带展示文案、本地化或产品默认值，id 在
  整个目录内跨 kind 唯一（服务端 conformance case）。源清单由 Backend 发布声明，
  自定义源 URL 不在协议范围内。
- 选择统一为 `download_source_ids`（稳定 id 数组，`uniqueItems`）：
  - HTTP `SettingsSnapshot` 持久化用户偏好，Runtime 的模型下载与 HTTP 维护安装读取
    该设置；
  - runtime-host `RuntimeHostRequest` 与 retry 用的 `RuntimeMaintenanceCommandRequest`
    显式携带（Host 是一次性无状态 CLI）；observe 请求只读，不携带。
- 客户端应始终发送用户当前选择；省略时由服务端应用默认（官方源）。未知 id 必须以
  `DOWNLOAD_SOURCE_UNKNOWN`（validation/400，不可重试）fail closed，不得静默回退到
  其他源。Runtime 未声明该 capability 时客户端必须省略字段（旧端请求 schema 对未知
  字段封闭）。
- Host 应把生效源反映到 `launch.environment`（例如 pip index 或模型 registry 的环境
  变量）；变量名与下载实现仍是 Backend 细节，不属于 wire contract。
- 未来向 `DownloadSourceKind` 封闭枚举追加值会被兼容门禁拦截；届时必须先在六仓协调
  评估开放策略，不得直接扩枚举。

## 组件选择（runtime.component-selection.v1）

离线引擎依赖（如 paddleOCR、MinerU）的手动安装范围选择是可协商的 minor 扩展：

- 变体目录 `ComponentVariantCatalog` 挂在既有 capability descriptor 载体上：OpenAPI
  `CapabilityDescriptor` 与 runtime-host `$defs.CapabilityDescriptor` 均新增可选字段
  `component_variant_catalog`，仅 `runtime.component-selection.v1` descriptor 携带。
  每个 `ComponentVariantDescriptor` 表达 `engine_id`（Backend 发布声明的稳定分组 id，
  不进请求；纯文本 OCR 引擎应复用 `OcrEngineId` wire 值）、`accelerator`
  （cpu/nvidia_cuda，须与目标 Runtime 一致）与 `component_id`
  （`runtime.component-repair.v1` 组件 id）。目录只列可选安装变体，不列 base runtime
  组件；(engine_id, accelerator) 组合唯一是服务端 conformance case。
- 选择是 capability 保护的新可选字段 `install_component_ids`（稳定组件 id 数组），
  落在四个 envelope：runtime-host `RuntimeHostRequest` 与 retry 用的
  `RuntimeMaintenanceCommandRequest`、HTTP `RuntimeMaintenanceRequest` 与
  `RuntimeMaintenanceCommandRequest`。它不复用既有 `component_ids`——后者保留
  repair 范围语义；旧端对 ensure+未知行为静默按默认全装，违背用户意图且不可检测，
  新字段让旧端 fail closed。
- 语义：显式列表 = 手动选择安装范围，Backend 安装其依赖闭包（base + 共享依赖 +
  所选），并沿用 maintenance snapshot 的 `requested_component_ids` /
  `effective_component_ids` 如实上报（requested 回显安装选择，effective 为闭包）；
  "全装" = 显式列出所选 accelerator 的全部目录 component id；省略 = 服务端默认集合
  （现状：整 profile）。Runtime 未声明该 capability 时客户端必须省略字段。未知 id
  必须以 `RUNTIME_COMPONENT_UNKNOWN`（validation/400，不可重试）fail closed，不得
  静默安装其他范围。
- 引擎可用性状态不在此目录重复表达：就绪状态沿用 `OcrEngineCatalog`（OCR 引擎）与
  `GET /v2/runtime/status` 的组件 desired/actual 状态。

## 错误合同

HTTP v2 错误对象固定包含八个字段：`schema_version`、`instance_id`、`code`、
`message`、`category`、`retryable`、`detail` 和 `job_id`。可空字段也必须在线上出现。
解析器验证 schema 版本与字段类型，并将 `code` 同错误注册表交叉检查；发送方不得让
`category` 或 `retryable` 与注册表冲突。

## .NET 类型边界

`VibeOCR.Contracts.HttpV2` 是面向应用的稳定类型层。请求 DTO 拒绝未知成员；响应 DTO
忽略未知成员以支持协议的可加性演进。
`VibeOCR.Runtime.Contracts.Generated.Wire` 是 OpenAPI 的机械投影，主要用于验证 wire
形状与生成一致性。当前两个类型族并存，后续若要统一，必须先提供迁移期并验证所有
消费者，不能直接删除公开类型。

## 发布不变量

Release Please 同步 Python、NuGet、仓库清单、`version.txt` 与 OpenAPI
`info.version`。发布工作流在上传前安装两个 wheel、读取打包资源，并通过临时项目从
本地源还原和编译两个 NuGet 包，避免“构建成功但消费者无法安装”的发布。
