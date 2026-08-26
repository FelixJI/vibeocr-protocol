# VibeOCR Protocol 领域上下文

## 术语

- **Runtime**：唯一、可替换的本地后端执行环境，物理位置固定为产品数据根下的 `runtime`。
- **Accelerator**：Runtime 的安装计划。Protocol v2 支持 `cpu` 与 `nvidia_cuda`；它不是目录名，也不表示多个 Runtime 并存。
- **Runtime Host**：后端发布的单一控制面可执行文件。它通过 Protocol v2 的一次性 JSON CLI 执行检查、安装、修复并返回启动契约。
- **Supervisor**：由 Runtime 中的 Python 启动的本机 HTTP 数据面，实现正式 OpenAPI。
- **Frontend**：Classic 或 Next。它选择 Accelerator 与可选安装组件范围（`runtime.component-selection.v1`）、调用 Runtime Host、持有 Supervisor 进程并通过生成的 HTTP 客户端访问数据面。
- **Recognition Mode（识别模式）**：面向用户的稳定识别能力。它明确绑定一个 Execution Pipeline、纯文本模式下的 OCR Engine、能力来源、当前可用性、可用选项和资源生命周期；Frontend 以它作为选择与展示单位。
- **Execution Pipeline（执行管道）**：Supervisor 内部的任务路由标识。它是 Protocol v2 的兼容执行字段，不等同于产品功能名；同一个 `OCR` 管道可承载 RapidOCR、Windows OCR 与 PaddleOCR 三种识别模式。
- **OCR Engine**：仅用于纯文本 `OCR` 执行管道的实现选择，稳定值为 `rapidocr`、`windows`、`paddleocr`。它与 Recognition Mode 的映射固定，不能被静默回退。
- **Base Runtime（基础运行时）**：产品随附并可直接运行 RapidOCR 的最小 Backend 环境。基础运行时就绪不要求用户选择 CPU/GPU，也不等于所有高级组件已安装。
- **Advanced Component（高级组件）**：PaddleOCR 模型能力或 MinerU 等可选安装范围；缺失只影响绑定它的 Recognition Mode，不应阻塞 RapidOCR 基础能力。
- **Model Residency（模型驻留）**：Paddle 模型的预加载、TTL、固定和释放语义。只有声明该生命周期的 Recognition Mode 才能展示这些控制。
- **Process Keep-alive（进程保活）**：MinerU 子进程的 TTL 与释放语义；它不是模型预加载或模型驻留，也不表示 Supervisor 本身常驻。

## 不变量

- 一个数据根同一时刻只有一个 Runtime 和一个已安装 Accelerator。
- Accelerator 切换以原子替换 Runtime 完成，不能在同一 Python 环境混装 CPU/GPU 框架。
- Runtime Host 请求、响应和错误由 `runtime-host.schema.json` 约束，并与 HTTP OpenAPI 共享 Protocol v2 版本和发布包。
- Supervisor HTTP 请求、响应和错误由 `openapi.yaml` 约束。
- Frontend 不解析依赖锁、不调用 pip、不推断 Runtime 路径。
- Frontend 不把 Execution Pipeline 直接包装成产品模式，也不从名称猜测安装或生命周期能力；它消费 `ocr.recognition-modes.v1` 目录，并只展示目录明确声明支持的控制。
- Recognition Mode 到 `pipeline_id + engine` 的映射在 Protocol v2 minor 内保持不变。旧执行字段继续发送以兼容既有 Backend；新生命周期字段必须由 capability 保护，且与旧字段不一致时 fail closed。
- RapidOCR 与 Windows OCR 的生命周期是 `unmanaged`，没有用户可操作的预加载、TTL、固定或释放；Paddle 模式是 `model_residency`；MinerU 是 `process_keep_alive`。
- PaddleX、PaddleOCR 与 MinerU 原生管理各自模型的下载、缓存、更新与复用；Protocol
  只用 `model_registry` source id 表达用户的上游模型源偏好，不定义模型资产清单、文件级
  完整性、本地模型 binding，也不把模型文件生命周期转移给 VibeOCR。
- Runtime Host v2 已发布的 `launch.model_root` 仅作为 opaque legacy response 字段保留；
  Frontend 不读取其内部结构，Portable cache/config 落点由 Backend 通过 launch environment
  使用上游官方变量建立。
