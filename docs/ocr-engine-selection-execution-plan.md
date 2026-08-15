# 通用文本 OCR 引擎选择协议执行计划

> 状态：已实施于 `codex/ocr-engine-selection` 分支，等待 Draft PR 与正式 Release。本文只定义 `vibeocr-protocol` 仓库的可执行工作包，不代表功能已经发布。

## P0 落点说明（最终决策）

capability descriptor 的权威载体有两处：`openapi.yaml#components.schemas.CapabilityDescriptor`（HTTP `GET /v2/health` → `Health.capability_descriptors`）与 `runtime-host.schema.json#$defs.CapabilityDescriptor`（Runtime Host `RuntimeHostSuccess.capability_descriptors`）。两者均为 `additionalProperties: false` 的纯 lifecycle 元数据，不能承载结构化 payload，因此按 §2.2 的备选路径在同一 minor 版本为两个 `CapabilityDescriptor` 增加可选强类型字段 `ocr_engine_catalog`（`$ref` → `OcrEngineCatalog`），仅由 `name == "ocr.engine-selection.v1"` 的 descriptor 携带。

- 生命周期：descriptor 随 health/ready/Runtime Host ensure 响应一起产生与过期，无独立缓存语义。
- 消费者：Python `generated/wire_types.py`、`generated/runtime_host_types.py` 与 .NET `RuntimeWireTypes.g.cs`、`RuntimeHostWireTypes.g.cs` 的生成 record/enum；手写应用层（`dtos.PipelineSelection`、`HttpV2.PipelineSelection`）只消费 `engine` 字段，不解析目录。
- 生成器无需修改：`_python_wire_types` / `_csharp_wire_types` 原生遍历 `components.schemas` 与 `$defs`，自动产出 `OcrEngineId`/`OcrEngineAvailability` 枚举与 `OcrEngineDescriptor`/`OcrEngineCatalog` 类型。
- Backend 不得自定义 SDK 不认识的 JSON 分支：目录字段是权威 OpenAPI 的一部分，兼容门禁（`check_openapi_quality.py`）与 golden fixture 双向锁定。

## 1. 目标与边界

本仓负责把“通用文本 OCR 使用哪个引擎”定义成稳定、可生成、可协商的 Protocol v2 minor 接口，使 Backend、Classic 和 Next 不依赖私有字符串或未声明的 `options`。

本仓交付：

- 三个稳定引擎 ID：`rapidocr`、`windows`、`paddleocr`。
- OCR 请求中的显式引擎选择字段。
- 运行时可用引擎目录及不可用原因的结构化描述。
- 稳定错误码与兼容规则。
- Python/.NET 生成绑定、正式协议资产和契约测试。

本仓不负责：

- 引擎探测、模型加载、OCR 结果归一化或 PDF 处理。
- UI 文案、用户偏好或自动更新。
- RapidOCR、ONNX Runtime、WinRT、Paddle 或 PDF 依赖。

## 2. 外部接口决策

### 2.1 请求模型

在权威 OpenAPI 中新增 `OcrEngineId` 枚举，并在 `PipelineSelection` 增加可选的强类型 `engine` 字段。字段仅对通用文本 `OCR` pipeline 生效；其他 pipeline 携带该字段时由服务端返回稳定的请求错误，不静默忽略。

规则：

- 前端应始终显式发送用户当前选择。
- 字段缺失时由 Backend 使用服务端默认值；本项目默认约定为 `rapidocr`。
- 未知枚举值必须 fail closed，不回退到其他引擎。
- 不复用 MinerU 的 `backend` 选项，也不通过开放字典偷传引擎 ID。

### 2.2 能力与发现

新增 capability `ocr.engine-selection.v1`，并为 ready/runtime descriptor 定义 `OcrEngineCatalog`。实现阶段先复用现有 capability descriptor 载体；若该载体不能承载结构化 payload，则在同一 minor 版本中增加强类型 descriptor 字段，不另造非协议端点。

每个 `OcrEngineDescriptor` 至少包含：

- `id`：稳定 `OcrEngineId`。
- `availability`：`ready`、`preparation_required`、`unavailable`。
- `included_in_base`：是否随基础离线运行时提供。
- `reason_code`：不可用或待准备原因；UI 自行本地化，不从 Backend 接收展示文案。
- `required_component`：需要用户准备的运行时组件 ID，可空。

目录只表达能力与状态，不表达前端默认值。Classic/Next 的产品默认均设为 RapidOCR。

### 2.3 错误契约

新增或登记以下稳定 reason/error code：

- `ocr_engine_unknown`
- `ocr_engine_unavailable`
- `ocr_engine_preparation_required`
- `ocr_engine_not_valid_for_pipeline`
- `ocr_engine_language_unavailable`

错误 payload 必须保留 job/request 关联信息，并允许 Backend 返回当前可选的引擎 ID；是否切换由用户决定，前端不得据此自动降级。

### 2.4 兼容约束

- 这是 Protocol v2 minor-compatible 扩展，不提升 major。
- `engine` 保持 optional，以便旧客户端仍能向新 Backend 发起请求。
- 不为开发阶段旧配置或未发布实现增加迁移 DTO。
- Python 与 .NET 绑定必须由同一权威源生成，wire value 完全一致。

## 3. 分阶段工作包

### P0：确认现有 descriptor seam

修改前先追踪 ready envelope、runtime settings 和 installer result 中 capability descriptor 的权威 schema 与两个 SDK 消费路径。

产出：一段写入本文或相邻 ADR 的最终落点说明，明确 `OcrEngineCatalog` 的载体、生命周期和消费者。不得让 Backend 自定义一个 SDK 不认识的 JSON 分支。

验收：Python/.NET 均能从生成类型访问目录；若不能，P1 必须扩权威 OpenAPI。

### P1：修改权威协议源

主要入口：

- `packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/openapi.yaml`
- `packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/capabilities.json`

工作项：

1. 新增 `OcrEngineId`、`OcrEngineAvailability`、`OcrEngineDescriptor`、`OcrEngineCatalog`。
2. 为 `PipelineSelection` 增加 `engine`。
3. 把 `ocr.engine-selection.v1` 登记为可发布 capability。
4. 补充字段约束、nullable/required 语义和错误示例。
5. 更新 `docs/protocol-v2-design.md`；只有决策稳定后才新增 ADR。

验收：权威源中不存在第二套引擎 ID 列表；其他 pipeline 的字段合法性有明确文字与测试契约。

### P2：生成并审阅 SDK

只运行仓库生成器，不手改生成物：

```powershell
uv run python scripts/generate_runtime_protocol.py
```

重点审阅：

- Python enum、DTO、序列化与反序列化。
- `.NET` `VibeOCR.Contracts` 记录类型及 JSON enum wire value。
- schema/registry hash 或版本派生文件的一致性。
- 同一请求在 Python 与 .NET 中产生相同 JSON。

验收：重新运行生成器后工作树无二次差异。

### P3：补充契约测试

测试至少覆盖：

- 三个合法 ID 的 round-trip。
- 缺失 `engine` 的兼容反序列化。
- 未知 ID fail closed。
- engine catalog 三种 availability 状态。
- capability 注册表包含 `ocr.engine-selection.v1`。
- Python/.NET fixture 的 wire JSON 一致。
- 非 OCR pipeline 携带 engine 的约束有机器可执行验证；若 OpenAPI 无法表达条件约束，则将其登记为服务端 conformance case。

优先入口：

- `tests/contracts/v2/test_formal_protocol_spec.py`
- 对应 Python/.NET 生成契约测试目录

### P4：质量、正式资产与下游交接

执行仓库声明的完整入口，具体以 `.ci/project.json` 为准：

```powershell
uv sync --frozen --group dev
pwsh -File scripts/check-quality.ps1
pwsh -File scripts/build-release.ps1
```

交付给 Backend：

- 正式 Protocol Release 版本。
- Python wheel、.NET package、OpenAPI/registry 资产及 hash。
- capability 名称、字段语义、错误码和 cross-language fixture。

Backend 不得消费本仓源码 worktree 或未发布本地 wheel。

## 4. 文件级修改清单

| 类型 | 入口 | 计划变更 |
|---|---|---|
| 权威 schema | `packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/openapi.yaml` | enum、请求字段、descriptor、错误 payload |
| capability registry | `packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/capabilities.json` | 登记 `ocr.engine-selection.v1` |
| 生成器 | `scripts/generate_runtime_protocol.py` | 仅在现有生成器不能生成新增结构时调整 |
| Python 绑定 | 生成输出 | 由生成器更新，不手改 |
| .NET 绑定 | `src/dotnet/VibeOCR.Contracts/HttpV2/HttpV2Records.cs` 等生成输出 | 由生成器更新，不手改 |
| 契约测试 | `tests/contracts/v2/` | round-trip、兼容、capability、跨语言 fixture |
| 设计文档 | `docs/protocol-v2-design.md`、必要时 `docs/adr/` | 记录稳定 seam 与兼容理由 |

## 实施适配记录（相对本计划的调整）

以下调整在实施中确定，均保持计划的外部接口意图不变：

1. **错误码命名遵循注册表惯例。** `errors.json` 的 code 是 SCREAMING_SNAKE 且直接生成 Python `RuntimeErrorCode` StrEnum 与 C# `RuntimeErrorCode` 枚举成员名，小写 `ocr_engine_unknown` 无法作为合法 C# 标识符风格落地。五个稳定错误码登记为 `OCR_ENGINE_UNKNOWN`、`OCR_ENGINE_UNAVAILABLE`、`OCR_ENGINE_PREPARATION_REQUIRED`、`OCR_ENGINE_NOT_VALID_FOR_PIPELINE`、`OCR_ENGINE_LANGUAGE_UNAVAILABLE`。计划 §2.2 中的 `reason_code` 是 `OcrEngineDescriptor` 的独立字段（稳定机器可读原因 ID，非封闭枚举），与错误注册表 code 是两个概念，两者并存。
2. **非 OCR pipeline 约束登记为服务端 conformance case。** OpenAPI 3.1 技术上可用 `allOf`/`if`/`then` 表达"仅 OCR pipeline 可携带 engine"，但 `scripts/check_openapi_quality.py` 将对已发布请求 schema 追加任何 `allOf` 约束判定为破坏性变更（收紧请求校验可能拒绝既有合法请求）。因此该约束按 P3 预设备选路径落地：`PipelineSelection.description` 写明承诺 + `OCR_ENGINE_NOT_VALID_FOR_PIPELINE` 稳定错误码 + 契约测试锁定，不修改已发布 schema 的约束结构。
3. **生成器未修改。** 现有 `generate_runtime_protocol.py` 原生支持新增 enum/nullable/$ref 结构，`.ci/project.json` 的 `generated_commands` 保持不变。
4. **`OCR_ENGINE_PREPARATION_REQUIRED` 使用 428**（Precondition Required），`OCR_ENGINE_UNAVAILABLE`/`OCR_ENGINE_LANGUAGE_UNAVAILABLE` 跟随 `RUNTIME_CAPABILITY_UNAVAILABLE` 的 426 惯例；三个错误均通过开放 `detail` 对象附带可选引擎 ID，不为共享 `Error` schema 增加第二个类型化字段。

## 5. 验收标准

- [x] OpenAPI 是引擎 ID、请求字段和 descriptor 的唯一事实源。
- [x] Python/.NET SDK 均提供强类型 API，不需要前端拼接字典。
- [x] 未知或不可用引擎具有稳定错误语义，不发生静默回退。
- [x] `ocr.engine-selection.v1` 可被 Backend ready/runtime 状态声明。
- [x] 生成器幂等，所有正式契约测试通过。
- [ ] 真实 release build 产出可供 Backend 锁定的正式资产（由 release prepare/build 流程与云端门禁完成，不在本 PR）。
- [x] Draft PR 仅包含本仓协议工作，不夹带 Backend 或前端实现。

## 6. PR 与依赖关系

本仓是四仓链路的第一个 Draft PR。PR 可先保持 Draft 供 Backend 并行开发，但 Backend 合并/发布前必须锁定本仓正式 Release。PR 不负责合并、打 tag 或发布；这些动作需另行授权并通过仓库完整云端门禁。
