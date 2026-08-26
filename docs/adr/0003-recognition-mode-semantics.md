# ADR-0003：以识别模式分离产品语义、执行路由与资源生命周期

- 状态：Accepted
- 日期：2026-08-26

## 背景

Protocol v2 最初把 `OCR`、`PP-StructureV3`、`MinerU` 等 execution pipeline 同时用于任务
路由、界面命名、安装提示和驻留控制。后来纯文本 `OCR` 又增加 RapidOCR、Windows OCR 与
PaddleOCR 三个 engine，单个 `OCR` 标识已经无法回答这些产品问题：

- 基础 Runtime 是否已经能完成截图文字识别；
- 当前选择是否需要安装 Paddle/MinerU 高级组件；
- “预加载/驻留”控制的是 Paddle 模型、MinerU 子进程，还是不可管理的内部缓存；
- 同一项选择应发送哪个 `pipeline_id + engine`，支持哪些 options。

如果四个仓库继续各自从 pipeline 名、组件或 profile 推断这些事实，就会出现首次启动强制
CPU/GPU 选择、RapidOCR 已内置却提示下载、把所有识别能力都描述为支持预加载等矛盾行为。

## 决策

新增 capability `ocr.recognition-modes.v1` 和 `RecognitionModeCatalog`，以稳定
`RecognitionModeId` 作为 Frontend 的产品选择与展示单位。每个目录项完整声明：

- `family`：text、document 或 specialized；
- 固定的 legacy `pipeline_id` 与可选 `engine` 投影；
- `provisioning`、当前 `availability`、稳定 `reason_code` 与 `required_component`；
- `supported_options`；
- `lifecycle.kind` 及 preload、TTL、pinning、release 四项能力。

首批模式为 `rapid_text`、`windows_text`、`paddle_text`、`paddle_structure`、
`paddle_document_vl`、`mineru_document`、`paddle_table`、`paddle_formula`。其中：

- RapidOCR 来自 `base_runtime`，Windows OCR 来自 `operating_system`，两者生命周期均为
  `unmanaged`，不向用户暴露预加载、TTL、固定或释放；
- Paddle 模式来自 `advanced_component`，生命周期为 `model_residency`，支持上述四项控制；
- MinerU 来自 `advanced_component`，生命周期为 `process_keep_alive`，只支持 TTL 与释放。

Protocol v2 的作业请求继续使用现有 `pipeline_id + engine`，不增加一份冗余的
`recognition_mode` 作业字段。Frontend 从目录做确定性投影，Backend 仍以执行字段路由。
生命周期接口增加 capability-gated 的模式字段；为保持旧请求兼容，preload 同时保留 required
legacy `pipelines`，Backend 对新旧字段映射不一致的请求 fail closed。驻留状态增加具体模式、
资源类型与资源标识，避免把模型和子进程混为一谈。

基础 Runtime 的“已安装/完整”与 Supervisor 的“当前可连接/可服务”保持不同事实。Frontend
进入工作台以实际 HTTP ready 为准；高级模式缺组件只降低对应目录项的 availability，不阻塞
`rapid_text`。

## 结果

- Protocol 成为识别产品语义的唯一事实源；Classic 与 Next 不再维护互相漂移的 pipeline 菜单。
- Backend 需要一个 Recognition Mode registry/resolver，在 catalog、作业路由、安装提示与生命
  周期操作之间复用同一映射。
- Runtime residency controller 只管理声明可控的模型或子进程；executor 内部缓存不冒充公共驻留。
- 新字段由 capability 保护，旧 Frontend 与旧 Backend 仍可按 Protocol v2 legacy 字段互操作。
- 新增模式或改变既有映射需要协议演进与兼容评审，不能通过 UI 改名静默改变语义。

## 放弃的方案

- 继续把 pipeline 当产品模式：无法区分同属 `OCR` 的三个 engine，也无法准确描述生命周期。
- 把 engine 直接提升为所有 UI 选择：文档、表格、公式模式并不是 OCR engine，概念会再次混杂。
- 在作业请求同时发送 `recognition_mode` 与 `pipeline_id + engine`：形成两个执行事实源，增加不一致
  状态；选择目录只负责确定性投影即可。
- 把所有缓存都纳入统一“预加载/驻留”：RapidOCR/Windows 的内部缓存、Paddle 模型和 MinerU
  子进程具有不同所有权和释放语义，统一承诺会误导用户。

## 验收

- Protocol schema、golden、Python/.NET 类型与生成绑定包含同一模式目录和生命周期字段；
- Backend 对模式目录、执行投影、组件可用性与生命周期操作使用同一 registry；
- Classic/Next 以稳定模式 ID 展示清晰名称，RapidOCR 基础路径不触发高级组件选择；
- 只有 Paddle 模式出现模型预加载/TTL/固定/释放，MinerU 明确标为进程保活，RapidOCR 与
  Windows OCR 不出现这些控制；
- legacy 请求保持兼容，映射不一致和不支持的生命周期操作 fail closed。
