# vibeocr-protocol

VibeOCR 本地 Runtime 的协议单一事实源，包含 HTTP v2 OpenAPI、Bootstrap
协议、错误注册表、JSON Schema、golden fixtures，以及 Python/.NET 合同与客户端。
当前组件版本为 `2.0.0`。

## 权威来源与兼容策略

正式 HTTP 合同位于
`packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/openapi.yaml`。错误负载、
生成绑定和独立 Schema 均由该规范或对应注册表生成，不应手工修改 `generated/`
和 `schemas/errors.schema.json`。

- 请求采用严格校验：未知字段、未知枚举或收窄后的非法值会被拒绝。
- 响应采用向前兼容读取：已知必填字段和类型仍会校验，未知可选字段会保留。
- 未识别的 capability 字符串会被保留，调用方应按自己理解的能力进行协商。
- 错误码的 `category` 与 `retryable` 由 `errors.json` 注册表决定，线上的重复字段
  必须与注册表一致。

完整设计约束见 [HTTP v2 协议设计](docs/protocol-v2-design.md)。

## 本地验证

要求 Python 3.13、uv 0.9.21 和 .NET SDK 10.0.302。标准门禁：

```powershell
uv sync --locked --group dev
./scripts/check-quality.ps1
dotnet test tests/dotnet/VibeOCR.Contracts.Tests/VibeOCR.Contracts.Tests.csproj -c Release
dotnet test tests/dotnet/VibeOCR.Runtime.Client.Tests/VibeOCR.Runtime.Client.Tests.csproj -c Release
```

修改 OpenAPI、错误注册表或 Bootstrap 协议后，重新生成并检查差异：

```powershell
python scripts/generate_runtime_protocol.py
python scripts/generate_runtime_protocol.py --check
```

更多开发与发布命令见 [CONTRIBUTING.md](CONTRIBUTING.md)。
