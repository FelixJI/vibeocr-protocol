# ADR-0001：以 Runtime Host 控制单一 Runtime

- 状态：Accepted
- 日期：2026-08-02

## 背景

Classic 与 Next 分别拼装 Runtime Installer 参数、profile 名和返回 DTO，导致 CPU/GPU 选择、实际安装环境和 Supervisor 启动可能不一致。内容哈希和 profile 同时进入目录还放大了 Windows 路径长度与升级清理问题。

## 决策

采用两个协议边界：

1. Runtime Host 是 Protocol v2 的一次性 JSON/NDJSON CLI 控制面，负责 `inspect`、`ensure`、`repair`，管理唯一 `data/runtime`。旧请求仍只输出一个最终 JSON；调用方显式协商 `ndjson.v1` 后，Host 才在最终结果前输出进度、快照与 heartbeat 事件。
2. Supervisor HTTP v2 是长生命周期数据面，继续由 OpenAPI 和生成客户端约束；启动后的 Runtime/service/profile/component/maintenance 快照由认证的 `GET /v2/runtime/status` 提供。

CPU/GPU 对外建模为 Accelerator。具体 CUDA 版本、包索引和锁文件属于 Backend 发布实现，不进入 Frontend 契约。显式 Accelerator 在安装成功后成为 Host 偏好；请求未指定时先使用该偏好，再使用产品绑定默认值。

> 修订（2026-08-20，`runtime.download-sources.v1`）：用户选择依赖安装源与上游模型源偏好是 capability 保护字段（目录 + `download_source_ids`）；源目录仍由 Backend 发布声明。PaddleX、PaddleOCR 与 MinerU 的模型下载、缓存、校验和更新归上游原生下载器所有；`model_registry` 只让 Frontend 选择稳定 source id，由 Backend 浅映射为上游官方配置。锁文件、CUDA 版本与具体依赖下载实现继续留在 Backend。

Runtime Host EXE 本身不内嵌完整 Python、推理框架或模型。Frontend 产品携带 Backend
release-bound standalone Python 与 Base Runtime Pack，基础功能可离线激活；高级依赖按
Backend lock 在客户机安装。模型由 PaddleX/PaddleOCR/MinerU 原生下载器管理，不进入
Backend lock 或 Protocol。Frontend 仍持有 Supervisor 子进程，确保窗口退出、Job Object
与崩溃清理只有一个 owner。

## 备选方案

- 完整后端单 EXE：拒绝。体积、GPU 原生依赖、杀毒扫描、解压启动和差分更新成本过高。
- Frontend 直接管理 Python：拒绝。会在 Python/.NET 中复制安装状态机并绕过协议。
- Runtime Host 常驻 HTTP：暂不采用。控制操作低频且先于数据面启动，额外端口、鉴权和守护生命周期没有收益。

## 结果

- 切换 Accelerator 会替换当前 Runtime，需要重新下载/安装不共享的框架。
- 模型和下载缓存独立于 Runtime，可跨切换复用。
- Runtime Host Schema 与 HTTP OpenAPI 使用同一个 Protocol v2 版本、发布清单和生成门禁；传输可以独立扩展，但不能分别发布出互不匹配的版本。
- UI 只消费稳定的功能分组、阶段、message code 和 typed progress，不解析包管理器 stdout、requirements lock 或任意传递依赖。
