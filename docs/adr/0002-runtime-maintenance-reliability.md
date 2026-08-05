# ADR-0002：Runtime 维护操作、重放与来源身份

- 状态：Accepted
- 日期：2026-08-05

## 背景

Protocol v2.2 已统一一次性 Runtime Host 的 JSON/NDJSON 控制面与 Supervisor ready 后的
HTTP 状态快照，但仍有以下缺口：

- Runtime Host 每次执行都生成新的 `operation_id`，重复 ensure/repair 不能证明是同一意图；
- cancel 仅靠前端终止进程，retry 只能重新发起全新调用，重复命令可能产生重复副作用；
- 安装事件只有当前进程内的单调 sequence，持久化状态只保留最后快照，断线后不能重放；
- HTTP 与 Runtime Host 的错误对象、category、retryable 与 retry-after 语义不一致；
- HTTP status 没有投影已经验证的 Backend source SHA、Runtime manifest digest 和 Protocol
  绑定身份；
- 前端把 `steps` 的 total 当作百分比，制造并不存在的完成率与 ETA；
- capability 只有字符串集合，不能表达协商结果、弃用、sunset 或 replacement；
- repair 只能重建整个 Runtime，状态也不能表达 desired 与 actual 的差异。

这些问题跨越 Protocol、Backend、Classic 与 Next。可靠性语义必须集中在同一个深 Module，
而不是分别由 stdio、HTTP 或 UI adapter 猜测。

## 决策

### 1. `RuntimeControl` 是唯一外部 seam

Backend 的 `RuntimeControl` Module 对 transport 只暴露两个 Interface：

1. `command(command) -> receipt`：提交 inspect/ensure/repair，或对既有 operation 发 cancel/retry；
2. `observe(operation_id, after_sequence) -> update`：读取原子快照与 cursor 之后的事件。

Python/.NET SDK 可在该 seam 上提供 `inspect`、`ensure`、`repair`、`cancel`、`retry`、
`observe` 便利方法，但它们不能各自拥有状态机。Module 内部隐藏 operation ledger、event
journal、锁、取消检查点、原子 Runtime 切换、来源身份、component drift、错误映射和
retention。

stdio JSON/NDJSON 与认证 HTTP 是 Adapter。Runtime 未 ready 时使用 stdio；Supervisor ready
后，状态与重放可使用 HTTP。调用方不因 lifecycle 改变业务语义。

### 2. operation 与 command 幂等

新的 start request 允许调用方提供 `operation_id`。省略时保留 v2.2 的服务端自动 UUID：

- `operation_id` 第一次出现时永久绑定规范化后的 operation intent、desired identity、profile
  与 component selection；
- 同一个 `operation_id` 和同一个 intent 重复提交时，返回已经持久化的 receipt、当前快照或
  原终态结果，不再次执行副作用；
- 同一个 `operation_id` 携带不同 intent 时，返回 `RUNTIME_OPERATION_ID_CONFLICT`；
- operation 的 terminal snapshot 不可逆，不允许从 succeeded/failed/cancelled 回到 running。

cancel/retry 使用独立、调用方提供的 `command_id`：

- 同一个 `command_id` 和同一个 payload 返回原 command result；
- 同一个 `command_id` 携带不同 payload 返回 `RUNTIME_COMMAND_ID_CONFLICT`；
- cancel 指定 `target_operation_id`，可选 `expected_sequence` 用于 compare-and-set；重复 cancel
  安全，`cancel_requested` 不等于 `cancelled`，只有 owned resources 已停止才发布 terminal；
- retry 只接受 failed/cancelled operation，指定新的 `operation_id` 并记录
  `source_operation_id`；重复 retry command 返回同一个新 operation，不能创建第二个 retry；
- retry 默认复用 source 的规范化 intent；调用方只能显式选择仍兼容的 profile/component，
  不能静默更换来源身份。

新的 stdio command/observe envelope 仍携带产品根、component lock 与 Runtime manifest 的现有
信任链参数，以便独立进程定位同一个 ledger 并验证调用上下文。旧 Backend 未声明新 capability
时，前端继续使用 v2.2 的进程终止与普通重试 fallback，不伪造幂等保证。

### 3. sequence cursor 与断线重放

每个 operation 有独立、从 1 开始、无重复且连续递增的 sequence。事件必须先 durable append，
再更新快照并投影到 Adapter；transport 只承诺 at-least-once delivery，客户端按
`(operation_id, sequence)` 去重。

`observe` 返回：

- 当前 `snapshot`；
- `after_sequence` 排他下界之后的 `events`；
- 本页 `through_sequence`、当前 `oldest_sequence` 与 `more`；
- terminal operation 的 `replay_expires_at`。

active operation 的全部事件必须可重放。terminal operation 在 `replay_expires_at` 之前不得
丢弃事件；实现可以在该时刻之后压缩或删除。cursor 早于 `oldest_sequence - 1` 时返回
`RUNTIME_CURSOR_EXPIRED`，同时提供当前 snapshot 与 oldest sequence，客户端从新 watermark
继续，不能把缺口当作连续历史。

### 4. 统一错误 taxonomy

HTTP 错误注册表继续是 canonical taxonomy。Runtime Host 的 legacy lowercase `code` 保留，
并增加 optional `canonical_code`、`category`、`retry_after`、`message_code` 与 `detail`。
HTTP `Error` 增加同语义的 optional `retry_after`（整数秒）；存在时响应同时发送标准
`Retry-After` header。

新增 operation/cursor/capability/identity 相关 canonical code，并使用稳定 category：

- validation：请求或 component selection 无效；
- capability：required capability 不可用；
- not_found：operation 不存在或 replay 已过保留期；
- conflict：operation/command id 冲突、状态不允许 cancel/retry；
- identity：desired 与已验证来源不匹配；
- cancelled：operation 已真实取消；
- transient/backend_unavailable/internal：沿用现有语义。

`retryable` 由 registry 决定，Adapter 不得自行改写。`retry_after` 只能在 `retryable=true` 时
出现；UI 根据 canonical code/category 决定自动等待、允许手动 retry 或要求更新，绝不解析
traceback、pip 输出或自由文本。

### 5. 来源身份是状态的一部分

新增 `RuntimeSourceIdentity`，只投影 Backend Release/manifest 已经验证的事实：

- `backend_version`；
- `backend_source_sha`；
- `runtime_manifest_sha256`；
- `protocol_version`；
- `protocol_manifest_sha256`。

Runtime Host state、operation snapshot 与 HTTP runtime status 均可携带该结构。SHA-256 只核对
对应边界的实际字节集合，不能替代 Release、tag、component lock、attestation 或精确资产集合
验证。

### 6. 真实 progress、百分比与 ETA

保留 `ProgressSnapshot.unit=steps|items|bytes`。增加 optional
`estimated_remaining_seconds`，并遵守：

- `steps` 即使有 total 也只显示 `n/m 步`，`IsProgressIndeterminate=true`，不显示百分比或 ETA；
- `items`/`bytes` 只有在 total 来自执行计划或输入资产的真实、稳定总量时才可显示百分比；
- ETA 只有在 `items`/`bytes`、真实 total、单调 current 和实际吞吐样本同时存在时发送；
- pip/uv 等黑盒安装阶段没有可信总量，继续发送 heartbeat 与 indeterminate progress；
- Python/runtime archive 解包可以使用实际成员数或未压缩字节数报告 determinate progress。

### 7. capability negotiation 与 deprecation

保留 `capabilities: string[]` 作为 v2 兼容探测面，并在 registry、health、Runtime Host receipt 中
增加 optional `capability_descriptors`：

```text
CapabilityDescriptor {
  name,
  lifecycle: active | deprecated,
  introduced_in,
  deprecated_in?,
  sunset_at?,
  replacement?
}
```

request 可带 `required_capabilities`；服务端返回 `negotiated_capabilities`。required 项缺失时
fail closed，不执行 operation。只有 manifest 或 health 已声明 negotiation capability 的客户端
才发送这些新字段。

deprecated capability 在 Protocol v2 内仍必须被识别；metadata 只发出迁移信号，不能在同一
major 中静默删除行为。`sunset_at` 是最早移除时间，不是自动关闭开关，`replacement` 必须指向
已发布 capability。

本扩展使用：

- `runtime.maintenance.v2`：operation/command 幂等、journal、replay 与统一错误；
- `runtime.component-repair.v1`：component selection 与 desired/actual drift；
- `runtime.capability-metadata.v1`：descriptor 与 required/negotiated capability；
- `runtime.events.sse.v1`、`runtime.events.ndjson.v1`：ready 后的可选 HTTP stream。

v2.2 的 `runtime.maintenance.v1`、`task.progress.v1` 与 `ndjson.v1` 保留。

### 8. ready 后可选 SSE/HTTP NDJSON

认证 HTTP 增加 operation observe 资源，并为同一事件定义可选 stream：

- JSON page：`GET /v2/runtime/operations/{operation_id}/observe?after_sequence=N`；
- SSE：`GET /v2/runtime/operations/{operation_id}/events`，`Accept: text/event-stream`，支持
  `Last-Event-ID`；
- NDJSON：同一路径，`Accept: application/x-ndjson`，使用 `after_sequence`。

stream 先重放 cursor 之后的 durable events，再等待 live events；terminal event 发出后正常
结束。heartbeat 不推进业务状态但有自己的 sequence。SSE/NDJSON 都经过现有 loopback + bearer
token middleware；没有新端口、token 或 owner。

不支持对应 capability 时，客户端使用 JSON observe/status 轮询。stdio 的首次安装继续使用
显式协商的 NDJSON；旧请求未 opt-in 时仍只输出一个最终 JSON。

### 9. component desired/actual drift 与 repair

稳定 component id 不变。component status 保留 v2.2 `state`，并增加 optional：

- `desired_state=ready|not_required`、`desired_version`；
- `actual_state=ready|missing|drifted|unknown`、`actual_version`；
- `drift_reason=none|missing|version_mismatch|identity_mismatch|integrity_failed|unexpected`；
- `repairable`。

Backend 依据已验证 manifest descriptor、installed distribution metadata、import probe 与安装 marker
计算 actual；Frontend 不读取 requirements lock。

repair request 可带稳定、去重的 `component_ids`。省略时修复全部 drifted component。Module 根据
共享依赖计算 effective repair scope，并在 snapshot 中分别报告 requested/effective component ids。
当前 profile 使用单一 hash-locked dependency graph，因此实现可以为修复一个 component 扩大到
依赖闭包或整个 profile 的原子重建；必须如实报告 effective scope，不能声称未触及共享依赖。

repair 只在存在可修复 drift 时执行；已 in-sync 的幂等 repair 返回现有 ready 状态，不重建。

## 兼容与迁移

1. Protocol 先发布新的 v2 minor；新增 request envelope、路由、capability 与 response optional
   字段，不改变 v2.2 legacy request/result。
2. Backend 绑定正式 Protocol Release，并同时投影 v1 最后 snapshot 与 v2 journal/update。
3. Classic/Next 只有在已验证 Backend manifest 声明新 capability 时才发送 operation/command/cursor
   字段；否则维持 v2.2 fallback。
4. 新前端必须容忍旧 Backend；旧前端必须继续消费新 Backend 的 legacy 单 JSON 与 v1 NDJSON。
5. SSE 与 HTTP NDJSON 都是 optional Adapter，不成为 Runtime ready 的 required capability。

## 测试 seam 与验收

Interface 同时是测试面：

- Protocol：Runtime Host/OpenAPI schema、Python/.NET stable records、parser、golden、compatibility；
- Backend：`RuntimeControl.command/observe`，生产 filesystem 与 in-memory store Adapter，stdio/HTTP
  Adapter 等价；
- Classic/Next：各自 RuntimeHost/RuntimeControl client 与共享状态 projection；
- package/release：正式 Protocol 绑定、frozen installer、真实 frontend package smoke。

纵向 TDD 必须覆盖：

- 相同 operation id 同 intent 不重复执行，异 intent 冲突；
- 重复 cancel/retry command 返回同一结果，retry 只创建一个新 operation；
- cancel requested、资源停止、terminal cancelled 的顺序；
- sequence 连续、重复事件去重、断线 cursor 重放、cursor expired 与 terminal retention；
- 错误 registry、Runtime Host alias、HTTP payload/header 的 taxonomy/retryable/retry_after 一致；
- 来源身份来自已验证 manifest，identity mismatch fail closed；
- archive 使用真实 items/bytes total，pip 阶段无百分比/ETA；
- required capability、deprecated metadata、replacement 与旧客户端兼容；
- SSE/NDJSON replay/live/terminal/认证/断连；
- component missing/version/integrity drift、无 drift 幂等 repair、requested/effective scope；
- Classic/Next 对 steps 永不显示百分比/ETA，对 bytes/items 才显示，并正确投影错误、来源与 drift。

## 放弃的方案

- 把每种操作和 transport 暴露为独立业务 Interface：会把相同状态机复制到四仓，形成 shallow
  module 与 shotgun surgery。
- 通用事件溯源平台、effect outbox 与任意 reducer：本轮只需要 bounded maintenance journal；
  引入通用框架的复杂度与当前需求不成比例。
- retry 让同一 operation 从终态回到 running：破坏终态不可逆和旧 snapshot 语义；采用链接的新
  operation。
- 把 steps 当百分比，或从 pip 日志估算 ETA：数据不真实，会误导 UI。
- 把 Backend source SHA 或 manifest digest 描述为业务权威：它们只是已验证 Release 绑定中的来源
  身份字段。
