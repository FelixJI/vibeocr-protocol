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
from .sync_client import SyncSupervisorClient

__all__ = [
    "AsyncRuntimeTransport",
    "MultipartAttachment",
    "RuntimeClientError",
    "RuntimeHttpClient",
    "RuntimeHttpResponse",
    "SupervisorClient",
    "SyncSupervisorClient",
    "bind_operation_path",
    "get_background_loop",
    "shutdown_background_loop",
]
