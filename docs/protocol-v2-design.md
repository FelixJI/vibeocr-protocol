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

兼容性取决于数据流方向：

- 服务端接收的请求必须严格。新增必填参数、收窄类型或约束、减少 `oneOf` / `anyOf`
  分支，以及增加 `allOf` 约束都属于破坏性变更。
- 客户端接收的响应必须容忍新增可选字段，并原样保留未知字段。删除字段、把可选字段
  变为必填、扩大响应类型范围仍属于破坏性变更。
- 新增 capability 不要求旧客户端升级。旧客户端保留未知字符串，但只有理解该能力时
  才能使用它。
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
