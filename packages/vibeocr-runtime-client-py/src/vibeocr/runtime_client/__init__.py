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
    "RuntimeClientError",
    "RuntimeHttpClient",
    "RuntimeHttpResponse",
    "RuntimeHostResponse",
    "RuntimeHostValidationError",
    "SupervisorClient",
    "SyncSupervisorClient",
    "bind_operation_path",
    "get_background_loop",
    "parse_runtime_host_response",
    "shutdown_background_loop",
    "validate_runtime_host_response",
]
