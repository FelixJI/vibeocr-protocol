# VibeOCR Protocol 领域上下文

## 术语

- **Runtime**：唯一、可替换的本地后端执行环境，物理位置固定为产品数据根下的 `runtime`。
- **Accelerator**：Runtime 的安装计划。Protocol v2 支持 `cpu` 与 `nvidia_cuda`；它不是目录名，也不表示多个 Runtime 并存。
- **Runtime Host**：后端发布的单一控制面可执行文件。它通过 Protocol v2 的一次性 JSON CLI 执行检查、安装、修复并返回启动契约。
- **Supervisor**：由 Runtime 中的 Python 启动的本机 HTTP 数据面，实现正式 OpenAPI。
- **Frontend**：Classic 或 Next。它选择 Accelerator 与可选安装组件范围（`runtime.component-selection.v1`）、调用 Runtime Host、持有 Supervisor 进程并通过生成的 HTTP 客户端访问数据面。

## 不变量

- 一个数据根同一时刻只有一个 Runtime 和一个已安装 Accelerator。
- Accelerator 切换以原子替换 Runtime 完成，不能在同一 Python 环境混装 CPU/GPU 框架。
- Runtime Host 请求、响应和错误由 `runtime-host.schema.json` 约束，并与 HTTP OpenAPI 共享 Protocol v2 版本和发布包。
- Supervisor HTTP 请求、响应和错误由 `openapi.yaml` 约束。
- Frontend 不解析依赖锁、不调用 pip、不推断 Runtime 路径。
- PaddleX、PaddleOCR 与 MinerU 原生管理各自模型的下载、缓存、更新与复用；Protocol
  只用 `model_registry` source id 表达用户的上游模型源偏好，不定义模型资产清单、文件级
  完整性、本地模型 binding，也不把模型文件生命周期转移给 VibeOCR。
- Runtime Host v2 已发布的 `launch.model_root` 仅作为 opaque legacy response 字段保留；
  Frontend 不读取其内部结构，Portable cache/config 落点由 Backend 通过 launch environment
  使用上游官方变量建立。
