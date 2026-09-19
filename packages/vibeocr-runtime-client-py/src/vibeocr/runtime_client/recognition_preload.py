"""Explicit recognition-mode preload plan entry (``ocr.recognition-modes.v1``).

This helper is the client-side guard for ``POST /v2/runtime/preload``. It is a
pure function: it accepts the recognition modes the user wants to prepare plus
the capabilities and the recognition-mode catalog the caller already fetched,
validates them fail-closed against the *runtime-declared* lifecycle, and
returns the request plan for the existing generic transport. It never issues
a network request and does not replace server-side validation.

The check is deliberately driven by the runtime's own catalog, not by the
static constants of this package: a new Runtime that declares
``supports_preload`` may be preloaded, while an old Runtime without the
capability or with ``supports_preload=false`` is explicitly rejected instead
of silently letting the new constants speak for the old service.

Failure is always a :class:`RecognitionPreloadError` carrying a stable
:class:`~vibeocr.runtime_contracts.errors.ErrorCode` the caller can branch on:

* ``RECOGNITION_MODE_UNKNOWN`` — the caller passed a mode id that is not a
  stable recognition mode.
* ``RECOGNITION_MODE_LIFECYCLE_UNSUPPORTED`` — the runtime does not advertise
  ``ocr.recognition-modes.v1``, the catalog is missing or malformed, the
  requested mode is not listed, or its runtime-declared lifecycle does not
  support preload. No request is sent in any of these cases.

Legacy preload calls (``pipelines`` only) never need this helper; the generic
transport keeps working unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from vibeocr.runtime_contracts.contracts.pipelines import (
    RecognitionMode,
    get_recognition_mode_definition,
)
from vibeocr.runtime_contracts.errors import ErrorCode
from vibeocr.runtime_contracts.generated.capabilities import OCR_RECOGNITION_MODES_V1

_LIFECYCLE_KEYS = frozenset({"kind", "supports_preload"})


class RecognitionPreloadError(Exception):
    """Stable, judgeable preload-plan failure; never triggers a request."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _unsupported(message: str) -> RecognitionPreloadError:
    return RecognitionPreloadError(
        ErrorCode.RECOGNITION_MODE_LIFECYCLE_UNSUPPORTED, message
    )


@dataclass(frozen=True, slots=True)
class RecognitionPreloadPlan:
    """Deterministic legacy projection for one explicit preload request."""

    pipelines: tuple[str, ...]
    recognition_modes: tuple[str, ...]


def _requested_modes(
    recognition_modes: Iterable[str | RecognitionMode],
) -> list[RecognitionMode]:
    modes: list[RecognitionMode] = []
    for value in recognition_modes:
        if isinstance(value, RecognitionMode):
            mode = value
        else:
            try:
                mode = RecognitionMode(value)
            except ValueError as exc:
                raise RecognitionPreloadError(
                    ErrorCode.RECOGNITION_MODE_UNKNOWN,
                    f"unknown recognition mode id: {value!r}",
                ) from exc
        if mode not in modes:
            modes.append(mode)
    if not modes:
        raise RecognitionPreloadError(
            ErrorCode.VALIDATION_ERROR,
            "preload requires at least one recognition mode",
        )
    return modes


def _declared_preload_support(
    recognition_mode_catalog: Mapping[str, Any],
) -> dict[str, bool]:
    """Map listed mode ids to their runtime-declared preload support.

    Unknown future response fields and future mode kinds are tolerated; only
    the known ``supports_preload`` boolean is read.
    """
    if not isinstance(recognition_mode_catalog, Mapping):
        raise _unsupported("recognition_mode_catalog must be a JSON object")
    modes_raw = recognition_mode_catalog.get("modes")
    if not isinstance(modes_raw, list) or not modes_raw:
        raise _unsupported("recognition_mode_catalog modes must be a non-empty list")
    support: dict[str, bool] = {}
    for descriptor in modes_raw:
        if not isinstance(descriptor, Mapping):
            raise _unsupported("recognition mode descriptors must be JSON objects")
        mode_id = descriptor.get("id")
        if not isinstance(mode_id, str) or not mode_id:
            raise _unsupported("recognition mode descriptors must carry a string id")
        lifecycle = descriptor.get("lifecycle")
        if not isinstance(lifecycle, Mapping) or not _LIFECYCLE_KEYS.issubset(
            lifecycle
        ):
            raise _unsupported(
                "recognition mode descriptors must carry a lifecycle object with "
                "kind and supports_preload"
            )
        supports_preload = lifecycle["supports_preload"]
        if not isinstance(supports_preload, bool):
            raise _unsupported(
                f"recognition mode {mode_id!r} lifecycle supports_preload must be "
                "a boolean"
            )
        if mode_id in support:
            raise _unsupported(
                f"recognition_mode_catalog lists duplicate mode id: {mode_id!r}"
            )
        support[mode_id] = supports_preload
    return support


def build_recognition_preload_plan(
    recognition_modes: Iterable[str | RecognitionMode],
    *,
    capabilities: Iterable[str] | None,
    recognition_mode_catalog: Mapping[str, Any] | None,
) -> RecognitionPreloadPlan:
    """Build a preload request plan guarded by the runtime lifecycle catalog.

    ``capabilities`` and ``recognition_mode_catalog`` are the values the caller
    already obtained from the runtime health envelope / the
    ``ocr.recognition-modes.v1`` capability descriptor. Both must be provided
    and must prove preload support for every requested mode; otherwise the
    helper fails closed without any network access.
    """
    modes = _requested_modes(recognition_modes)
    advertised = set(capabilities) if capabilities is not None else set()
    if OCR_RECOGNITION_MODES_V1 not in advertised:
        raise _unsupported(
            f"the runtime does not advertise {OCR_RECOGNITION_MODES_V1}; refusing "
            "to preload without the runtime-declared lifecycle catalog"
        )
    if recognition_mode_catalog is None:
        raise _unsupported(
            f"the runtime advertises {OCR_RECOGNITION_MODES_V1} but the caller "
            "did not provide its recognition_mode_catalog"
        )
    support = _declared_preload_support(recognition_mode_catalog)
    for mode in modes:
        declared = support.get(mode.value)
        if declared is None:
            raise _unsupported(
                f"the recognition mode {mode.value!r} is not listed by the "
                "recognition_mode_catalog"
            )
        if not declared:
            raise _unsupported(
                f"the runtime declares that recognition mode {mode.value!r} does "
                "not support preload"
            )
    pipelines: list[str] = []
    for mode in modes:
        pipeline = get_recognition_mode_definition(mode).pipeline.value
        if pipeline not in pipelines:
            pipelines.append(pipeline)
    return RecognitionPreloadPlan(
        pipelines=tuple(pipelines),
        recognition_modes=tuple(mode.value for mode in modes),
    )


__all__ = [
    "RecognitionPreloadError",
    "RecognitionPreloadPlan",
    "build_recognition_preload_plan",
]
