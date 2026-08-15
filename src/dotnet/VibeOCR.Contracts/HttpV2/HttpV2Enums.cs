// HTTP v2 inference supervisor contract DTOs (.NET mirror of the Python
// vibeocr.protocol.v2 package). These types are the wire contract shared with
// PySide (Python) and, eventually, the WinUI front-end. They MUST stay in
// lock-step with packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts/.
//
// Wire conventions (see docs/protocol-v2-design.md in the repository):
//   * schema_version is always 2 on the wire.
//   * Field names are snake_case; the HttpV2JsonContext applies
//     JsonKnownNamingPolicy.SnakeCaseLower so PascalCase C# properties map
//     automatically (job_id, schema_version, progress_current, ...).
//   * Enums carry explicit [JsonStringEnumMemberName] on every member so the
//     wire string is unambiguous regardless of the context naming policy
//     (lowercase snake for state/kind/priority/mode; SCREAMING_SNAKE for
//     ErrorCode, which must NOT be lower-cased).
using System.Text.Json.Serialization;

namespace VibeOCR.Contracts.HttpV2;

/// <summary>Wire schema major version for the v2 protocol.</summary>
public static class HttpV2Schema
{
    public const int Version = 2;
}

[JsonConverter(typeof(JsonStringEnumConverter<JobState>))]
public enum JobState
{
    [JsonStringEnumMemberName("accepted")] Accepted,
    [JsonStringEnumMemberName("queued")] Queued,
    [JsonStringEnumMemberName("running")] Running,
    [JsonStringEnumMemberName("completed")] Completed,
    [JsonStringEnumMemberName("completed_with_errors")] CompletedWithErrors,
    [JsonStringEnumMemberName("cancel_requested")] CancelRequested,
    [JsonStringEnumMemberName("cancelled")] Cancelled,
    [JsonStringEnumMemberName("failed")] Failed,
}

[JsonConverter(typeof(JsonStringEnumConverter<ItemState>))]
public enum ItemState
{
    [JsonStringEnumMemberName("queued")] Queued,
    [JsonStringEnumMemberName("running")] Running,
    [JsonStringEnumMemberName("succeeded")] Succeeded,
    [JsonStringEnumMemberName("failed")] Failed,
    [JsonStringEnumMemberName("cancelled")] Cancelled,
}

[JsonConverter(typeof(JsonStringEnumConverter<JobKind>))]
public enum JobKind
{
    [JsonStringEnumMemberName("recognition")] Recognition,
    [JsonStringEnumMemberName("pdf_ocr")] PdfOcr,
    [JsonStringEnumMemberName("mineru_parse")] MineruParse,
    [JsonStringEnumMemberName("model_download")] ModelDownload,
    [JsonStringEnumMemberName("settings_install")] SettingsInstall,
}

[JsonConverter(typeof(JsonStringEnumConverter<JobPriority>))]
public enum JobPriority
{
    [JsonStringEnumMemberName("interactive")] Interactive,
    [JsonStringEnumMemberName("background")] Background,
}

/// <summary>
/// Stable engine ids for the plain-text OCR pipeline, mirroring the Python
/// OcrEngine enum and the authoritative OcrEngineId OpenAPI schema. The
/// Backend default for an omitted selection is rapidocr.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<OcrEngine>))]
public enum OcrEngine
{
    [JsonStringEnumMemberName("rapidocr")] RapidOcr,
    [JsonStringEnumMemberName("windows")] Windows,
    [JsonStringEnumMemberName("paddleocr")] PaddleOcr,
}

[JsonConverter(typeof(JsonStringEnumConverter<JobCommandKind>))]
public enum JobCommandKind
{
    [JsonStringEnumMemberName("cancel")] Cancel,
    [JsonStringEnumMemberName("retry")] Retry,
    [JsonStringEnumMemberName("forget")] Forget,
}

[JsonConverter(typeof(JsonStringEnumConverter<CancelMode>))]
public enum CancelMode
{
    [JsonStringEnumMemberName("queued_only")] QueuedOnly,
    [JsonStringEnumMemberName("cooperative")] Cooperative,
    [JsonStringEnumMemberName("forced")] Forced,
}

[JsonConverter(typeof(JsonStringEnumConverter<ResidencyKind>))]
public enum ResidencyKind
{
    [JsonStringEnumMemberName("soft_ttl")] SoftTtl,
    [JsonStringEnumMemberName("pinned")] Pinned,
    [JsonStringEnumMemberName("idle")] Idle,
    [JsonStringEnumMemberName("evicted")] Evicted,
}

[JsonConverter(typeof(JsonStringEnumConverter<EvictionReason>))]
public enum EvictionReason
{
    [JsonStringEnumMemberName("none")] None,
    [JsonStringEnumMemberName("ttl_expired")] TtlExpired,
    [JsonStringEnumMemberName("vram_pressure")] VramPressure,
    [JsonStringEnumMemberName("explicit_release")] ExplicitRelease,
    [JsonStringEnumMemberName("supervisor_shutdown")] SupervisorShutdown,
}

[JsonConverter(typeof(JsonStringEnumConverter<ProgressUnit>))]
public enum ProgressUnit
{
    [JsonStringEnumMemberName("steps")] Steps,
    [JsonStringEnumMemberName("items")] Items,
    [JsonStringEnumMemberName("bytes")] Bytes,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeComponentState>))]
public enum RuntimeComponentState
{
    [JsonStringEnumMemberName("not_required")] NotRequired,
    [JsonStringEnumMemberName("pending")] Pending,
    [JsonStringEnumMemberName("installing")] Installing,
    [JsonStringEnumMemberName("verifying")] Verifying,
    [JsonStringEnumMemberName("ready")] Ready,
    [JsonStringEnumMemberName("failed")] Failed,
    [JsonStringEnumMemberName("cancelled")] Cancelled,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeServiceState>))]
public enum RuntimeServiceState
{
    [JsonStringEnumMemberName("ready")] Ready,
    [JsonStringEnumMemberName("degraded")] Degraded,
    [JsonStringEnumMemberName("maintenance")] Maintenance,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeMaintenanceOperation>))]
public enum RuntimeMaintenanceOperation
{
    [JsonStringEnumMemberName("inspect")] Inspect,
    [JsonStringEnumMemberName("ensure")] Ensure,
    [JsonStringEnumMemberName("repair")] Repair,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeOperationState>))]
public enum RuntimeOperationState
{
    [JsonStringEnumMemberName("queued")] Queued,
    [JsonStringEnumMemberName("running")] Running,
    [JsonStringEnumMemberName("succeeded")] Succeeded,
    [JsonStringEnumMemberName("failed")] Failed,
    [JsonStringEnumMemberName("cancelled")] Cancelled,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeMaintenancePhase>))]
public enum RuntimeMaintenancePhase
{
    [JsonStringEnumMemberName("validate_binding")] ValidateBinding,
    [JsonStringEnumMemberName("wait_for_lock")] WaitForLock,
    [JsonStringEnumMemberName("prepare_runtime")] PrepareRuntime,
    [JsonStringEnumMemberName("install_profile")] InstallProfile,
    [JsonStringEnumMemberName("install_backend")] InstallBackend,
    [JsonStringEnumMemberName("verify_runtime")] VerifyRuntime,
    [JsonStringEnumMemberName("commit_runtime")] CommitRuntime,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeAccelerator>))]
public enum RuntimeAccelerator
{
    [JsonStringEnumMemberName("cpu")] Cpu,
    [JsonStringEnumMemberName("nvidia_cuda")] NvidiaCuda,
}

/// <summary>Typed error categories for the v2 protocol (errors.json categories).</summary>
[JsonConverter(typeof(JsonStringEnumConverter<ErrorCategory>))]
public enum ErrorCategory
{
    [JsonStringEnumMemberName("validation")] Validation = 0,
    [JsonStringEnumMemberName("auth")] Auth = 1,
    [JsonStringEnumMemberName("not_found")] NotFound = 2,
    [JsonStringEnumMemberName("conflict")] Conflict = 3,
    [JsonStringEnumMemberName("cancelled")] Cancelled = 4,
    [JsonStringEnumMemberName("oom")] Oom = 5,
    [JsonStringEnumMemberName("transient")] Transient = 6,
    [JsonStringEnumMemberName("backend_unavailable")] BackendUnavailable = 7,
    [JsonStringEnumMemberName("internal")] Internal = 8,
    [JsonStringEnumMemberName("capability")] Capability = 9,
    [JsonStringEnumMemberName("identity")] Identity = 10,
}

/// <summary>
/// Typed error codes for the v2 protocol. SCREAMING_SNAKE wire strings are
/// pinned per-member so they are NOT affected by the context snake_case policy.
/// Keep in lock-step with errors.json and Python ErrorCode.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<HttpV2ErrorCode>))]
public enum HttpV2ErrorCode
{
    [JsonStringEnumMemberName("VALIDATION_ERROR")] ValidationError,
    [JsonStringEnumMemberName("QUOTA_EXCEEDED")] QuotaExceeded,
    [JsonStringEnumMemberName("UNAUTHORIZED")] Unauthorized,
    [JsonStringEnumMemberName("FORBIDDEN_LOOPBACK")] ForbiddenLoopback,
    [JsonStringEnumMemberName("JOB_NOT_FOUND")] JobNotFound,
    [JsonStringEnumMemberName("RESOURCE_NOT_FOUND")] ResourceNotFound,
    [JsonStringEnumMemberName("JOB_NOT_CANCELLABLE")] JobNotCancellable,
    [JsonStringEnumMemberName("JOB_NOT_RETRYABLE")] JobNotRetryable,
    [JsonStringEnumMemberName("INPUT_EXPIRED")] InputExpired,
    [JsonStringEnumMemberName("PIN_CAPACITY_CONFLICT")] PinCapacityConflict,
    [JsonStringEnumMemberName("SUPERVISOR_DRAINING")] SupervisorDraining,
    [JsonStringEnumMemberName("CANCELLED")] Cancelled,
    [JsonStringEnumMemberName("OUT_OF_MEMORY")] OutOfMemory,
    [JsonStringEnumMemberName("TRANSIENT_BACKEND")] TransientBackend,
    [JsonStringEnumMemberName("BACKEND_UNAVAILABLE")] BackendUnavailable,
    [JsonStringEnumMemberName("ADAPTER_PROTOCOL_VIOLATION")] AdapterProtocolViolation,
    [JsonStringEnumMemberName("PROTOCOL_MISMATCH")] ProtocolMismatch,
    [JsonStringEnumMemberName("INTERNAL_ERROR")] InternalError,
    [JsonStringEnumMemberName("RUNTIME_OPERATION_NOT_FOUND")] RuntimeOperationNotFound,
    [JsonStringEnumMemberName("RUNTIME_OPERATION_ID_CONFLICT")] RuntimeOperationIdConflict,
    [JsonStringEnumMemberName("RUNTIME_COMMAND_ID_CONFLICT")] RuntimeCommandIdConflict,
    [JsonStringEnumMemberName("RUNTIME_OPERATION_NOT_CANCELLABLE")] RuntimeOperationNotCancellable,
    [JsonStringEnumMemberName("RUNTIME_OPERATION_NOT_RETRYABLE")] RuntimeOperationNotRetryable,
    [JsonStringEnumMemberName("RUNTIME_CURSOR_EXPIRED")] RuntimeCursorExpired,
    [JsonStringEnumMemberName("RUNTIME_CAPABILITY_UNAVAILABLE")] RuntimeCapabilityUnavailable,
    [JsonStringEnumMemberName("RUNTIME_IDENTITY_MISMATCH")] RuntimeIdentityMismatch,
    [JsonStringEnumMemberName("RUNTIME_BUSY")] RuntimeBusy,
    [JsonStringEnumMemberName("RUNTIME_INSTALL_FAILED")] RuntimeInstallFailed,
    [JsonStringEnumMemberName("RUNTIME_IO_ERROR")] RuntimeIoError,
    [JsonStringEnumMemberName("OCR_ENGINE_UNKNOWN")] OcrEngineUnknown,
    [JsonStringEnumMemberName("OCR_ENGINE_UNAVAILABLE")] OcrEngineUnavailable,
    [JsonStringEnumMemberName("OCR_ENGINE_PREPARATION_REQUIRED")] OcrEnginePreparationRequired,
    [JsonStringEnumMemberName("OCR_ENGINE_NOT_VALID_FOR_PIPELINE")] OcrEngineNotValidForPipeline,
    [JsonStringEnumMemberName("OCR_ENGINE_LANGUAGE_UNAVAILABLE")] OcrEngineLanguageUnavailable,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeMaintenanceCommandKind>))]
public enum RuntimeMaintenanceCommandKind
{
    [JsonStringEnumMemberName("cancel")] Cancel,
    [JsonStringEnumMemberName("retry")] Retry,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeMaintenanceEventType>))]
public enum RuntimeMaintenanceEventType
{
    [JsonStringEnumMemberName("snapshot")] Snapshot,
    [JsonStringEnumMemberName("progress")] Progress,
    [JsonStringEnumMemberName("heartbeat")] Heartbeat,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeComponentDesiredState>))]
public enum RuntimeComponentDesiredState
{
    [JsonStringEnumMemberName("ready")] Ready,
    [JsonStringEnumMemberName("not_required")] NotRequired,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeComponentActualState>))]
public enum RuntimeComponentActualState
{
    [JsonStringEnumMemberName("ready")] Ready,
    [JsonStringEnumMemberName("missing")] Missing,
    [JsonStringEnumMemberName("drifted")] Drifted,
    [JsonStringEnumMemberName("unknown")] Unknown,
}

[JsonConverter(typeof(JsonStringEnumConverter<RuntimeDriftReason>))]
public enum RuntimeDriftReason
{
    [JsonStringEnumMemberName("none")] None,
    [JsonStringEnumMemberName("missing")] Missing,
    [JsonStringEnumMemberName("version_mismatch")] VersionMismatch,
    [JsonStringEnumMemberName("identity_mismatch")] IdentityMismatch,
    [JsonStringEnumMemberName("integrity_failed")] IntegrityFailed,
    [JsonStringEnumMemberName("unexpected")] Unexpected,
}
