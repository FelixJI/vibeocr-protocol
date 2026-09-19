"""Thin transports for the VibeOCR Runtime Protocol."""

from .background_loop import get_background_loop, shutdown_background_loop
from .client import (
    AsyncRuntimeTransport,
    MultipartAttachment,
    RuntimeClientError,
    RuntimeHttpClient,
    RuntimeHttpResponse,
    SupervisorClient,
    bind_operation_path,
)
from .mineru_config import (
    MineruConfigError,
    build_mineru_pipeline_selection,
)
from .recognition_preload import (
    RecognitionPreloadError,
    RecognitionPreloadPlan,
    build_recognition_preload_plan,
)
from .runtime_host import (
    RuntimeHostResponse,
    RuntimeHostValidationError,
    parse_runtime_host_response,
    validate_runtime_host_response,
)
from .sync_client import SyncSupervisorClient

__all__ = [
    "AsyncRuntimeTransport",
    "MultipartAttachment",
    "MineruConfigError",
    "RecognitionPreloadError",
    "RecognitionPreloadPlan",
    "RuntimeClientError",
    "RuntimeHttpClient",
    "RuntimeHttpResponse",
    "RuntimeHostResponse",
    "RuntimeHostValidationError",
    "SupervisorClient",
    "SyncSupervisorClient",
    "bind_operation_path",
    "build_mineru_pipeline_selection",
    "build_recognition_preload_plan",
    "get_background_loop",
    "parse_runtime_host_response",
    "shutdown_background_loop",
    "validate_runtime_host_response",
]
