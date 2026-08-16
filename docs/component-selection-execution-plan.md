# 组件选择执行计划（runtime.component-selection.v1）

已实施；本文记录 `runtime.component-selection.v1` 的决策与验收，先于 Draft PR 合入，
正式版本号由 release prepare 决定（登记 `introduced_in: "2.7.0"` 为预期目标，与
`runtime.download-sources.v1` 同乘一个 minor）。

## P0 落点说明（最终决策）

- 目录权威载体沿用既有 seam：OpenAPI `CapabilityDescriptor` 与 runtime-host
  `$defs.CapabilityDescriptor` 追加可选强类型字段 `component_variant_catalog`。
- 安装范围走**新字段** `install_component_ids` 而非复用 `component_ids`：后者是
  ADR-0002 §9 的 repair 范围语义；旧端对 ensure+component_ids 会静默按默认集合安装，
  用户选择被忽略且不可检测。新字段受 capability 门控，旧端 `additionalProperties:
  false` 直接 fail closed，符合"新行为必须由 capability 保护的新可选请求字段承载"的
  兼容规则。
- 字段落在四个 envelope：runtime-host 请求、runtime-host retry、HTTP maintenance
  请求、HTTP maintenance retry；observe 只读不携带。
- 生成器无需修改；两侧绑定由脚本机械投影。

## 1. 目标与边界

交付物：`ComponentVariantDescriptor/Catalog` schema、`install_component_ids`
可选请求字段（四处 envelope）、`RUNTIME_COMPONENT_UNKNOWN` 错误码、capability
注册、双语言生成绑定、SDK `ensure_runtime` 参数、golden fixtures 与双语言契约测试。

非目标：引擎运行时可用性状态（沿用 `OcrEngineCatalog` 与 `/v2/runtime/status`）、
机器 GPU 可达性发现（与既有 `accelerator` 字段同等边界）、按组件的展示文案。

## 2. 外部接口决策

- UI 选择模型 = 既有 `accelerator`（全局，一个 Runtime 一个加速器，切换即原子替换）
  + `install_component_ids`（引擎×加速器变体经目录映射为组件 id）。
- 目录 `feature_id` 是 Backend 发布声明的开放稳定能力族字符串，仅作分组键，不进请求；
  conformance：纯文本 OCR 引擎复用 `OcrEngineId` wire 值；目录不列 base 组件；
  (feature_id, accelerator) 组合唯一。
- 显式列表 = 安装其依赖闭包并经 `requested/effective_component_ids` 如实上报；
  "全装" = 显式列出所选 accelerator 的全部目录 component id；省略 = 服务端默认集合。
- 未知 id 以 `RUNTIME_COMPONENT_UNKNOWN`（validation/400/不可重试）fail closed，
  不静默安装其他范围。

## 3. 分阶段工作包

- P1 权威协议源：openapi.yaml、runtime-host.schema.json、capabilities.json、
  bootstrap.schema.json、errors.json。
- P2 `uv run python scripts/generate_runtime_protocol.py`；验收 = 重跑无二次差异。
- P3 手写层与 golden：dtos.py（`RuntimeMaintenanceRequest` 与
  `RuntimeMaintenanceCommand`）、client.py 两个客户端的 `ensure_runtime`、
  HttpV2Enums/HttpV2Records、golden 两个新 fixture 与 health 第 4 个 descriptor。
- P4 契约测试：`tests/contracts/v2/test_component_selection.py`、
  `tests/dotnet/VibeOCR.Contracts.Tests/ComponentSelectionContractTests.cs`，
  错误注册表计数 35→36、`IsRetryable` switch、mock 客户端 ensure 请求体断言。
- P5 文档：protocol-v2-design 章节、ADR-0002 修订注、CONTEXT.md Frontend 职责、
  本计划。

## 4. 实施适配记录

- openapi 侧 `accelerator` 沿用既有内联枚举先例（生成投影为 Python `Literal` +
  C# `string`）；runtime-host 侧引用命名 `$defs.Accelerator`（生成强类型枚举）。

## 5. 验收标准

- [x] 变体三字段跨 OpenAPI/runtime-host/双语言生成绑定单一来源。
- [x] `install_component_ids` 在四个 envelope 可选；空数组显式表示不选可选重组件，省略表示 Backend 默认集合。
- [x] capability 四处注册（capabilities.json、generated、Health、bootstrap）。
- [x] `RUNTIME_COMPONENT_UNKNOWN` 注册表与生成投影一致、fail closed。
- [x] golden 目录经 CapabilityDescriptor schema 校验，旧 descriptor wire 形状不变。
- [x] `check-quality.ps1` 全绿；两个 Release .NET 测试项目全绿。
- [ ] 正式 Release 资产由 release 流程产出（不在本 PR 范围）。
