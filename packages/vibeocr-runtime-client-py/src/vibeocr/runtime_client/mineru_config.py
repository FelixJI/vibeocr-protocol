"""Explicit MinerU 4 configuration construction entry (``ocr.mineru-config.v1``).

This helper is the client-side counterpart of the typed ``mineru`` request
block. It is a pure function: it accepts the typed :class:`MineruConfig` plus
the capabilities and catalog the caller already fetched, validates them
fail-closed, and returns a ready :class:`PipelineSelection` without issuing
any network request. It does not replace server-side validation.

Failure is always a :class:`MineruConfigError` carrying a stable
:class:`~vibeocr.runtime_contracts.errors.ErrorCode` the caller can branch on:

* ``MINERU_CONFIG_UNAVAILABLE`` — the capability is missing, the catalog is
  missing, or the catalog itself is malformed (unknown/duplicate tier ids,
  default tier not listed, empty or duplicated languages). No fallback to
  legacy options or the flash tier is ever performed here.
* ``MINERU_TIER_UNAVAILABLE`` — the requested tier is not listed or is
  declared ``unavailable``.
* ``MINERU_TIER_PREPARATION_REQUIRED`` — the tier is declared
  ``preparation_required``.
* ``VALIDATION_ERROR`` — the requested language is not in the catalog.

Old requests never need this helper or the new capability: constructing a
legacy ``PipelineSelection`` directly keeps working unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from vibeocr.runtime_contracts import (
    MineruConfig,
    MineruTier,
    PipelineSelection,
)
from vibeocr.runtime_contracts.errors import ErrorCode
from vibeocr.runtime_contracts.generated.capabilities import OCR_MINERU_CONFIG_V1

MINERU_TIER_AVAILABILITIES = frozenset({"ready", "preparation_required", "unavailable"})
_CATALOG_KEYS = frozenset({"default_tier", "tiers", "languages"})
_TIER_DESCRIPTOR_KEYS = frozenset({"id", "availability", "reason_code"})


class MineruConfigError(Exception):
    """Stable, judgeable construction failure; never triggers a request."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _unavailable(message: str) -> MineruConfigError:
    return MineruConfigError(ErrorCode.MINERU_CONFIG_UNAVAILABLE, message)


def _validate_catalog(catalog: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate known fields; ignore future optional response fields."""
    if not isinstance(catalog, Mapping):
        raise _unavailable("mineru_config_catalog must be a JSON object")
    missing_keys = sorted(_CATALOG_KEYS.difference(catalog))
    if missing_keys:
        raise _unavailable(
            "mineru_config_catalog must contain "
            f"{sorted(_CATALOG_KEYS)}; missing={missing_keys}"
        )
    tiers_raw = catalog["tiers"]
    languages_raw = catalog["languages"]
    if not isinstance(tiers_raw, list) or not tiers_raw:
        raise _unavailable("mineru_config_catalog tiers must be a non-empty list")
    if not isinstance(languages_raw, list) or not languages_raw:
        raise _unavailable("mineru_config_catalog languages must be a non-empty list")
    try:
        default_tier = MineruTier(catalog["default_tier"])
    except ValueError as exc:
        raise _unavailable(
            f"mineru_config_catalog default_tier is not a stable tier id: "
            f"{catalog['default_tier']!r}"
        ) from exc
    tiers: dict[str, dict[str, Any]] = {}
    for descriptor in tiers_raw:
        if not isinstance(descriptor, Mapping):
            raise _unavailable("mineru tier descriptors must be JSON objects")
        missing = sorted(_TIER_DESCRIPTOR_KEYS.difference(descriptor))
        if missing:
            raise _unavailable(
                "mineru tier descriptors must contain "
                f"{sorted(_TIER_DESCRIPTOR_KEYS)}; missing={missing}"
            )
        tier_id = descriptor["id"]
        try:
            tier = MineruTier(tier_id)
        except ValueError as exc:
            raise _unavailable(
                f"mineru_config_catalog lists an unknown tier id: {tier_id!r}"
            ) from exc
        if tier.value in tiers:
            raise _unavailable(
                f"mineru_config_catalog lists duplicate tier id: {tier.value!r}"
            )
        availability = descriptor["availability"]
        if (
            not isinstance(availability, str)
            or availability not in MINERU_TIER_AVAILABILITIES
        ):
            raise _unavailable(
                f"mineru tier {tier.value!r} has an unknown availability: "
                f"{availability!r}"
            )
        reason_code = descriptor["reason_code"]
        if reason_code is not None and (
            not isinstance(reason_code, str) or not reason_code
        ):
            raise _unavailable(
                f"mineru tier {tier.value!r} reason_code must be null or a "
                "non-empty string"
            )
        tiers[tier.value] = dict(descriptor)
    if default_tier.value not in tiers:
        raise _unavailable(
            "mineru_config_catalog default_tier is not listed in tiers: "
            f"{default_tier.value!r}"
        )
    languages: list[str] = []
    for language in languages_raw:
        if not isinstance(language, str) or not language:
            raise _unavailable(
                "mineru_config_catalog languages must be non-empty strings"
            )
        languages.append(language)
    if len(languages) != len(set(languages)):
        raise _unavailable("mineru_config_catalog languages contain duplicates")
    return tiers


def build_mineru_pipeline_selection(
    config: MineruConfig,
    *,
    capabilities: Iterable[str] | None,
    mineru_config_catalog: Mapping[str, Any] | None,
) -> PipelineSelection:
    """Build a ``kind=mineru_parse`` selection guarded by capability + catalog.

    ``capabilities`` and ``mineru_config_catalog`` are the values the caller
    already obtained from the runtime health envelope / the
    ``ocr.mineru-config.v1`` capability descriptor. Both must be provided and
    consistent; otherwise the helper fails closed without any network access
    and without falling back to legacy options or the flash tier.
    """
    if not isinstance(config, MineruConfig):
        raise MineruConfigError(
            ErrorCode.VALIDATION_ERROR,
            f"config must be a MineruConfig instance, got {type(config).__name__}",
        )
    advertised = set(capabilities) if capabilities is not None else set()
    if OCR_MINERU_CONFIG_V1 not in advertised:
        raise _unavailable(
            f"the runtime does not advertise {OCR_MINERU_CONFIG_V1}; refusing "
            "to send the typed mineru config without falling back to legacy "
            "options or the flash tier"
        )
    if mineru_config_catalog is None:
        raise _unavailable(
            f"the runtime advertises {OCR_MINERU_CONFIG_V1} but the caller "
            "did not provide its mineru_config_catalog"
        )
    tiers = _validate_catalog(mineru_config_catalog)
    descriptor = tiers.get(config.tier.value)
    if descriptor is None:
        raise MineruConfigError(
            ErrorCode.MINERU_TIER_UNAVAILABLE,
            f"the mineru tier {config.tier.value!r} is not listed by the "
            "mineru_config_catalog",
        )
    availability = descriptor["availability"]
    if availability == "unavailable":
        raise MineruConfigError(
            ErrorCode.MINERU_TIER_UNAVAILABLE,
            f"the mineru tier {config.tier.value!r} cannot run in this runtime",
        )
    if availability == "preparation_required":
        raise MineruConfigError(
            ErrorCode.MINERU_TIER_PREPARATION_REQUIRED,
            f"the mineru tier {config.tier.value!r} requires user preparation "
            "before use",
        )
    if config.language not in mineru_config_catalog["languages"]:
        raise MineruConfigError(
            ErrorCode.VALIDATION_ERROR,
            f"the mineru language {config.language!r} is not listed by the "
            "mineru_config_catalog",
        )
    return PipelineSelection(
        pipeline_id="MinerU",
        options_version=1,
        options={},
        engine=None,
        mineru=config,
    )


__all__ = [
    "MINERU_TIER_AVAILABILITIES",
    "MineruConfigError",
    "build_mineru_pipeline_selection",
]
