"""DTOs for the HTTP v2 supervisor protocol.

All DTOs are ``@dataclass(frozen=True, slots=True)`` so attributes cannot be
rebound and instances stay compact. Some fields contain mutable JSON objects,
so DTOs are not promised to be deeply immutable or hashable. Serialisation
helpers convert to JSON-native payloads; that form is the wire contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 2


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _to_iso(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class JobState(StrEnum):
    """Terminal states are listed in :data:`TERMINAL`."""

    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_JOB_STATES = frozenset(
    {
        JobState.COMPLETED,
        JobState.COMPLETED_WITH_ERRORS,
        JobState.CANCELLED,
        JobState.FAILED,
    }
)


class ItemState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_ITEM_STATES = frozenset(
    {ItemState.SUCCEEDED, ItemState.FAILED, ItemState.CANCELLED}
)


class JobKind(StrEnum):
    RECOGNITION = "recognition"
    PDF_OCR = "pdf_ocr"
    MINERU_PARSE = "mineru_parse"
    MODEL_DOWNLOAD = "model_download"
    SETTINGS_INSTALL = "settings_install"


class JobPriority(StrEnum):
    INTERACTIVE = "interactive"
    BACKGROUND = "background"


class OcrEngine(StrEnum):
    """Stable engine ids for the plain-text ``OCR`` pipeline.

    Mirrors the authoritative ``OcrEngineId`` enum in ``openapi.yaml``; the
    Backend default for an omitted selection is ``rapidocr``.
    """

    RAPIDOCR = "rapidocr"
    WINDOWS = "windows"
    PADDLEOCR = "paddleocr"


class JobCommandKind(StrEnum):
    CANCEL = "cancel"
    RETRY = "retry"
    FORGET = "forget"


class CancelMode(StrEnum):
    """The actual strength of cancellation the supervisor will apply."""

    QUEUED_ONLY = "queued_only"
    COOPERATIVE = "cooperative"
    FORCED = "forced"


class ResidencyKind(StrEnum):
    SOFT_TTL = "soft_ttl"
    PINNED = "pinned"
    IDLE = "idle"
    EVICTED = "evicted"


class RecognitionResourceKind(StrEnum):
    MODEL = "model"
    PROCESS = "process"


class EvictionReason(StrEnum):
    NONE = "none"
    TTL_EXPIRED = "ttl_expired"
    VRAM_PRESSURE = "vram_pressure"
    EXPLICIT_RELEASE = "explicit_release"
    SUPERVISOR_SHUTDOWN = "supervisor_shutdown"


class ProgressUnit(StrEnum):
    STEPS = "steps"
    ITEMS = "items"
    BYTES = "bytes"


class RuntimeComponentState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    INSTALLING = "installing"
    VERIFYING = "verifying"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeComponentDesiredState(StrEnum):
    READY = "ready"
    NOT_REQUIRED = "not_required"


class RuntimeComponentActualState(StrEnum):
    READY = "ready"
    MISSING = "missing"
    DRIFTED = "drifted"
    UNKNOWN = "unknown"


class RuntimeDriftReason(StrEnum):
    NONE = "none"
    MISSING = "missing"
    VERSION_MISMATCH = "version_mismatch"
    IDENTITY_MISMATCH = "identity_mismatch"
    INTEGRITY_FAILED = "integrity_failed"
    UNEXPECTED = "unexpected"


class RuntimeServiceState(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class RuntimeMaintenanceOperation(StrEnum):
    INSPECT = "inspect"
    ENSURE = "ensure"
    REPAIR = "repair"


class RuntimeMaintenanceCommandKind(StrEnum):
    CANCEL = "cancel"
    RETRY = "retry"


class RuntimeMaintenanceEventType(StrEnum):
    SNAPSHOT = "snapshot"
    PROGRESS = "progress"
    HEARTBEAT = "heartbeat"


class RuntimeOperationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeMaintenancePhase(StrEnum):
    VALIDATE_BINDING = "validate_binding"
    WAIT_FOR_LOCK = "wait_for_lock"
    PREPARE_RUNTIME = "prepare_runtime"
    INSTALL_PROFILE = "install_profile"
    INSTALL_BACKEND = "install_backend"
    VERIFY_RUNTIME = "verify_runtime"
    COMMIT_RUNTIME = "commit_runtime"


class RuntimeAccelerator(StrEnum):
    CPU = "cpu"
    NVIDIA_CUDA = "nvidia_cuda"


# ---------------------------------------------------------------------------
# Job DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JobItem:
    """A single input item inside a job (image, PDF page, MinerU file)."""

    item_id: str
    display_name: str
    state: ItemState
    attempt: int = 0
    error: str | None = None
    client_item_key: str | None = None
    ordinal: int = 0
    source_item_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


@dataclass(frozen=True, slots=True)
class JobSummary:
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    total: int = 0

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    """Typed progress; an omitted total means indeterminate progress."""

    unit: ProgressUnit
    current: int
    total: int | None = None
    estimated_remaining_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.current < 0:
            raise ValueError("progress current must be non-negative")
        if self.total is not None and self.total < 0:
            raise ValueError("progress total must be non-negative")
        if self.estimated_remaining_seconds is not None:
            if self.unit not in {ProgressUnit.ITEMS, ProgressUnit.BYTES}:
                raise ValueError("ETA requires items or bytes progress")
            if self.total is None or self.total <= 0:
                raise ValueError("ETA requires a positive real total")
            if self.estimated_remaining_seconds < 0:
                raise ValueError("ETA must be non-negative")

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "unit": self.unit.value,
            "current": self.current,
        }
        if self.total is not None:
            payload["total"] = self.total
        if self.estimated_remaining_seconds is not None:
            payload["estimated_remaining_seconds"] = self.estimated_remaining_seconds
        return payload


@dataclass(frozen=True, slots=True)
class StageEvent:
    """One ordered event in a job's event log."""

    sequence: int
    stage: str
    item_id: str | None
    timestamp: str = field(default_factory=_utcnow_iso)
    detail: dict[str, Any] | None = None
    progress: ProgressSnapshot | None = None
    message_code: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sequence": self.sequence,
            "stage": self.stage,
            "item_id": self.item_id,
            "timestamp": self.timestamp,
            "detail": self.detail or {},
        }
        if self.progress is not None:
            payload["progress"] = self.progress.to_payload()
        if self.message_code is not None:
            payload["message_code"] = self.message_code
        return payload


@dataclass(frozen=True, slots=True)
class JobRef:
    """Returned immediately when a job is submitted."""

    job_id: str
    schema_version: int = SCHEMA_VERSION
    instance_id: str | None = None
    state: JobState = JobState.ACCEPTED
    items: tuple[JobItem, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "schema_version": self.schema_version,
            "instance_id": self.instance_id,
            "state": self.state.value,
            "items": [item.to_payload() for item in self.items],
        }


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    """Full status of a job at a point in time."""

    job_id: str
    kind: JobKind
    priority: JobPriority
    state: JobState
    schema_version: int = SCHEMA_VERSION
    instance_id: str | None = None
    created_at: str = field(default_factory=_utcnow_iso)
    started_at: str | None = None
    finished_at: str | None = None
    stage: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    items: tuple[JobItem, ...] = ()
    summary: JobSummary = field(default_factory=JobSummary)
    cancel_requested_at: str | None = None
    cancel_mode: CancelMode | None = None
    degraded: bool = False
    event_sequence: int = 0
    result_available: bool = False
    request_id: str | None = None
    source_job_id: str | None = None
    pipeline: PipelineSelection | None = None
    progress: ProgressSnapshot | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "kind": self.kind.value,
            "priority": self.priority.value,
            "state": self.state.value,
            "schema_version": self.schema_version,
            "instance_id": self.instance_id,
            "created_at": self.created_at,
            "started_at": _to_iso(self.started_at),
            "finished_at": _to_iso(self.finished_at),
            "stage": self.stage,
            "progress_current": self.progress_current,
            "progress_total": self.progress_total,
            "items": [it.to_payload() for it in self.items],
            "summary": self.summary.to_payload(),
            "cancel_requested_at": self.cancel_requested_at,
            "cancel_mode": self.cancel_mode.value if self.cancel_mode else None,
            "degraded": self.degraded,
            "event_sequence": self.event_sequence,
            "result_available": self.result_available,
            "request_id": self.request_id,
            "source_job_id": self.source_job_id,
            "pipeline": self.pipeline.to_payload() if self.pipeline else None,
        }
        if self.progress is not None:
            payload["progress"] = self.progress.to_payload()
        return payload


# ---------------------------------------------------------------------------
# Submission / observation / command DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PipelineSelection:
    """Frozen user-semantic pipeline selection for one logical job.

    ``engine`` is only valid for the plain-text ``OCR`` pipeline; the server
    rejects it for other pipelines with ``OCR_ENGINE_NOT_VALID_FOR_PIPELINE``
    and fails closed on unknown ids. Omitting it lets the server apply its own
    default engine (``rapidocr``). The field is absent from the wire payload
    when unset because the request schema does not accept an explicit null.
    """

    pipeline_id: str
    options_version: int = 1
    options: dict[str, Any] = field(default_factory=dict)
    engine: OcrEngine | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "pipeline_id": self.pipeline_id,
            "options_version": self.options_version,
            "options": self.options,
        }
        if self.engine is not None:
            payload["engine"] = self.engine.value
        return payload


@dataclass(frozen=True, slots=True)
class SubmitItem:
    """One logical input. ``source`` is a strict discriminated wire object."""

    client_item_key: str
    ordinal: int
    display_name: str
    source: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "client_item_key": self.client_item_key,
            "ordinal": self.ordinal,
            "display_name": self.display_name,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class SubmitRequest:
    """Versioned manifest submitted alongside multipart attachments."""

    request_id: str
    kind: JobKind
    priority: JobPriority
    pipeline: PipelineSelection
    items: tuple[SubmitItem, ...]
    schema_version: int = SCHEMA_VERSION
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "kind": self.kind.value,
            "priority": self.priority.value,
            "pipeline": self.pipeline.to_payload(),
            "items": [item.to_payload() for item in self.items],
            "parameters": self.parameters,
        }


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    """Typed terminal outcome delta for one item."""

    item_id: str
    state: ItemState
    attempt: int
    payload_type: str | None = None
    payload: dict[str, Any] | None = None
    error_code: str | None = None
    error_detail: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "state": self.state.value,
            "attempt": self.attempt,
            "payload_type": self.payload_type,
            "payload": self.payload,
            "error_code": self.error_code,
            "error_detail": self.error_detail or {},
        }


@dataclass(frozen=True, slots=True)
class JobUpdate:
    """Atomic snapshot + event/outcome delta at one sequence watermark."""

    snapshot: JobSnapshot
    events: tuple[StageEvent, ...]
    outcomes: tuple[ItemOutcome, ...]
    through_sequence: int
    more: bool = False
    schema_version: int = SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot": self.snapshot.to_payload(),
            "events": [event.to_payload() for event in self.events],
            "outcomes": [outcome.to_payload() for outcome in self.outcomes],
            "through_sequence": self.through_sequence,
            "more": self.more,
        }


@dataclass(frozen=True, slots=True)
class JobCommand:
    command_id: str
    kind: JobCommandKind
    job_id: str
    item_ids: tuple[str, ...] = ()
    priority_override: JobPriority | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "kind": self.kind.value,
            "job_id": self.job_id,
            "item_ids": list(self.item_ids),
            "priority_override": (
                self.priority_override.value if self.priority_override else None
            ),
        }


# ---------------------------------------------------------------------------
# Result DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResultEntry:
    """One stable-ordered result item in a job result set."""

    item_id: str
    display_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    payload_type: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "display_name": self.display_name,
            "payload": self.payload,
            "error_code": self.error_code,
            "payload_type": self.payload_type,
        }


# ---------------------------------------------------------------------------
# Residency DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PipelineSpec:
    """Per-pipeline residency override."""

    name: str
    ttl_seconds: int | None = None
    pinned: bool = False
    recognition_mode: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "ttl_seconds": self.ttl_seconds,
            "pinned": self.pinned,
        }
        if self.recognition_mode is not None:
            payload["recognition_mode"] = self.recognition_mode
        return payload


@dataclass(frozen=True, slots=True)
class ResidencyEntry:
    """State of one loaded model/child process."""

    pipeline: str
    kind: ResidencyKind
    recognition_mode: str | None = None
    resource_kind: RecognitionResourceKind | None = None
    resource_id: str | None = None
    active_leases: int = 0
    remaining_ttl_seconds: int | None = None
    estimated_vram_mb: int | None = None
    eviction_reason: EvictionReason = EvictionReason.NONE

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "pipeline": self.pipeline,
            "kind": self.kind.value,
            "active_leases": self.active_leases,
            "remaining_ttl_seconds": self.remaining_ttl_seconds,
            "estimated_vram_mb": self.estimated_vram_mb,
            "eviction_reason": self.eviction_reason.value,
        }
        if self.recognition_mode is not None:
            payload["recognition_mode"] = self.recognition_mode
        if self.resource_kind is not None:
            payload["resource_kind"] = self.resource_kind.value
        if self.resource_id is not None:
            payload["resource_id"] = self.resource_id
        return payload


@dataclass(frozen=True, slots=True)
class ResidencyStatus:
    schema_version: int = SCHEMA_VERSION
    default_ttl_seconds: int = 300
    entries: tuple[ResidencyEntry, ...] = ()
    pipelines: tuple[PipelineSpec, ...] = ()
    vram_total_mb: int | None = None
    vram_used_mb: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_ttl_seconds": self.default_ttl_seconds,
            "entries": [e.to_payload() for e in self.entries],
            "pipelines": [p.to_payload() for p in self.pipelines],
            "vram_total_mb": self.vram_total_mb,
            "vram_used_mb": self.vram_used_mb,
        }


@dataclass(frozen=True, slots=True)
class RuntimeSourceIdentity:
    backend_version: str
    backend_source_sha: str
    runtime_manifest_sha256: str
    protocol_version: str
    protocol_manifest_sha256: str

    def to_payload(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceRequest:
    """HTTP runtime maintenance start request.

    ``install_component_ids`` is the manual install scope for ``ensure``
    (``runtime.component-selection.v1``): ``None`` omits the field and selects
    the Backend default, while an empty tuple explicitly selects no optional
    components. ``download_source_ids`` snapshots the source preference for
    the operation so later settings changes cannot alter an in-flight install.
    """

    operation: RuntimeMaintenanceOperation
    operation_id: str | None = None
    profile_id: str | None = None
    component_ids: tuple[str, ...] = ()
    install_component_ids: tuple[str, ...] | None = None
    download_source_ids: tuple[str, ...] | None = None
    required_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.download_source_ids is not None and not self.download_source_ids:
            raise ValueError("download_source_ids must be non-empty when provided")
        if self.operation is not RuntimeMaintenanceOperation.ENSURE and (
            self.install_component_ids is not None
            or self.download_source_ids is not None
        ):
            raise ValueError(
                "install_component_ids and download_source_ids require ensure"
            )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"operation": self.operation.value}
        if self.operation_id is not None:
            payload["operation_id"] = self.operation_id
        if self.profile_id is not None:
            payload["profile_id"] = self.profile_id
        if self.component_ids:
            payload["component_ids"] = list(self.component_ids)
        if self.install_component_ids is not None:
            payload["install_component_ids"] = list(self.install_component_ids)
        if self.download_source_ids is not None:
            payload["download_source_ids"] = list(self.download_source_ids)
        if self.required_capabilities:
            payload["required_capabilities"] = list(self.required_capabilities)
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceCommand:
    command_id: str
    command: RuntimeMaintenanceCommandKind
    target_operation_id: str
    new_operation_id: str | None = None
    expected_sequence: int | None = None
    install_component_ids: tuple[str, ...] | None = None
    download_source_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if (
            self.command is RuntimeMaintenanceCommandKind.RETRY
            and self.new_operation_id is None
        ):
            raise ValueError("retry requires new_operation_id")
        if self.download_source_ids is not None and not self.download_source_ids:
            raise ValueError("download_source_ids must be non-empty when provided")
        if self.command is not RuntimeMaintenanceCommandKind.RETRY and (
            self.install_component_ids is not None
            or self.download_source_ids is not None
        ):
            raise ValueError(
                "install_component_ids and download_source_ids require retry"
            )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "command_id": self.command_id,
            "command": self.command.value,
            "target_operation_id": self.target_operation_id,
        }
        if self.new_operation_id is not None:
            payload["new_operation_id"] = self.new_operation_id
        if self.expected_sequence is not None:
            payload["expected_sequence"] = self.expected_sequence
        if self.install_component_ids is not None:
            payload["install_component_ids"] = list(self.install_component_ids)
        if self.download_source_ids is not None:
            payload["download_source_ids"] = list(self.download_source_ids)
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeComponentStatus:
    component_id: str
    display_name: str
    state: RuntimeComponentState
    version: str | None = None
    desired_state: RuntimeComponentDesiredState | None = None
    desired_version: str | None = None
    actual_state: RuntimeComponentActualState | None = None
    actual_version: str | None = None
    drift_reason: RuntimeDriftReason | None = None
    repairable: bool | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "component_id": self.component_id,
            "display_name": self.display_name,
            "state": self.state.value,
            "version": self.version,
        }
        optional = {
            "desired_state": (
                self.desired_state.value if self.desired_state is not None else None
            ),
            "desired_version": self.desired_version,
            "actual_state": (
                self.actual_state.value if self.actual_state is not None else None
            ),
            "actual_version": self.actual_version,
            "drift_reason": (
                self.drift_reason.value if self.drift_reason is not None else None
            ),
            "repairable": self.repairable,
        }
        payload.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeProfileStatus:
    profile_id: str
    accelerator: RuntimeAccelerator
    components: tuple[RuntimeComponentStatus, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "accelerator": self.accelerator.value,
            "components": [component.to_payload() for component in self.components],
        }


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceStatus:
    operation_id: str
    sequence: int
    operation: RuntimeMaintenanceOperation
    operation_state: RuntimeOperationState
    phase: RuntimeMaintenancePhase
    profile_id: str
    updated_at: str = field(default_factory=_utcnow_iso)
    source_operation_id: str | None = None
    component_id: str | None = None
    progress: ProgressSnapshot | None = None
    message_code: str | None = None
    requested_component_ids: tuple[str, ...] = ()
    effective_component_ids: tuple[str, ...] = ()
    requested_download_source_ids: tuple[str, ...] = ()
    effective_download_source_ids: tuple[str, ...] = ()
    source: RuntimeSourceIdentity | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "operation_id": self.operation_id,
            "source_operation_id": self.source_operation_id,
            "sequence": self.sequence,
            "operation": self.operation.value,
            "operation_state": self.operation_state.value,
            "phase": self.phase.value,
            "profile_id": self.profile_id,
            "component_id": self.component_id,
            "updated_at": self.updated_at,
            "progress": self.progress.to_payload() if self.progress else None,
            "message_code": self.message_code,
        }
        if self.requested_component_ids:
            payload["requested_component_ids"] = list(self.requested_component_ids)
        if self.effective_component_ids:
            payload["effective_component_ids"] = list(self.effective_component_ids)
        if self.requested_download_source_ids:
            payload["requested_download_source_ids"] = list(
                self.requested_download_source_ids
            )
        if self.effective_download_source_ids:
            payload["effective_download_source_ids"] = list(
                self.effective_download_source_ids
            )
        if self.source is not None:
            payload["source"] = self.source.to_payload()
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceReceipt:
    operation_id: str
    snapshot: RuntimeMaintenanceStatus
    negotiated_capabilities: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "snapshot": self.snapshot.to_payload(),
            "negotiated_capabilities": list(self.negotiated_capabilities),
        }


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceEvent:
    sequence: int
    event_type: RuntimeMaintenanceEventType
    operation: RuntimeMaintenanceOperation
    snapshot: RuntimeMaintenanceStatus
    message_code: str
    message_args: dict[str, str] = field(default_factory=dict)
    fallback_message: str | None = None
    schema_version: int = SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_type": self.event_type.value,
            "sequence": self.sequence,
            "operation": self.operation.value,
            "snapshot": self.snapshot.to_payload(),
            "message_code": self.message_code,
            "message_args": dict(self.message_args),
        }
        if self.fallback_message is not None:
            payload["fallback_message"] = self.fallback_message
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeMaintenanceUpdate:
    operation_id: str
    snapshot: RuntimeMaintenanceStatus
    events: tuple[RuntimeMaintenanceEvent, ...]
    oldest_sequence: int
    through_sequence: int
    more: bool
    replay_expires_at: str | None
    schema_version: int = SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "snapshot": self.snapshot.to_payload(),
            "events": [event.to_payload() for event in self.events],
            "oldest_sequence": self.oldest_sequence,
            "through_sequence": self.through_sequence,
            "more": self.more,
            "replay_expires_at": self.replay_expires_at,
        }


@dataclass(frozen=True, slots=True)
class RuntimeStatusSnapshot:
    instance_id: str
    service_state: RuntimeServiceState
    backend_version: str
    profile: RuntimeProfileStatus
    maintenance: RuntimeMaintenanceStatus | None = None
    source: RuntimeSourceIdentity | None = None
    schema_version: int = SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "instance_id": self.instance_id,
            "service_state": self.service_state.value,
            "backend_version": self.backend_version,
            "profile": self.profile.to_payload(),
            "maintenance": self.maintenance.to_payload() if self.maintenance else None,
        }
        if self.source is not None:
            payload["source"] = self.source.to_payload()
        return payload


# ---------------------------------------------------------------------------
# Settings DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SettingsSnapshot:
    """Backend settings snapshot/exchange. Transport-neutral.

    ``download_source_ids`` persists the user's download source selection
    (``runtime.download-sources.v1``): the runtime applies it to model
    downloads and HTTP maintenance installs. The field is absent from the
    wire payload when empty and must be omitted when the runtime does not
    declare the capability; unknown ids fail closed server-side.
    """

    schema_version: int = SCHEMA_VERSION
    default_ttl_seconds: int = 300
    pipelines: tuple[PipelineSpec, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)
    download_source_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "residency": {
                "default_ttl_seconds": self.default_ttl_seconds,
                "pipelines": [p.to_payload() for p in self.pipelines],
            },
            "extra": self.extra,
        }
        if self.download_source_ids:
            payload["download_source_ids"] = list(self.download_source_ids)
        return payload


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def new_job_id() -> str:
    """Generate a fresh job id (stringified UUID4)."""
    return str(uuid4())


@dataclass(frozen=True, slots=True)
class UnknownJobError:
    """Marker used by long-poll callers to distinguish 404 from transient gaps."""

    job_id: str

    def to_payload(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "unknown": True}


__all__ = [
    "SCHEMA_VERSION",
    "TERMINAL_ITEM_STATES",
    "TERMINAL_JOB_STATES",
    "CancelMode",
    "EvictionReason",
    "ItemOutcome",
    "ItemState",
    "JobCommand",
    "JobCommandKind",
    "JobItem",
    "JobKind",
    "JobPriority",
    "JobRef",
    "JobSnapshot",
    "JobState",
    "JobSummary",
    "JobUpdate",
    "OcrEngine",
    "PipelineSelection",
    "PipelineSpec",
    "ProgressSnapshot",
    "ProgressUnit",
    "RecognitionResourceKind",
    "ResidencyEntry",
    "ResidencyKind",
    "ResidencyStatus",
    "ResultEntry",
    "RuntimeAccelerator",
    "RuntimeComponentState",
    "RuntimeComponentStatus",
    "RuntimeMaintenanceOperation",
    "RuntimeMaintenancePhase",
    "RuntimeMaintenanceStatus",
    "RuntimeOperationState",
    "RuntimeProfileStatus",
    "RuntimeServiceState",
    "RuntimeStatusSnapshot",
    "SettingsSnapshot",
    "StageEvent",
    "SubmitItem",
    "SubmitRequest",
    "UnknownJobError",
    "new_job_id",
]
