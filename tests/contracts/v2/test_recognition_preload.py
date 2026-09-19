"""Contract tests for the explicit recognition-mode preload entry (A2).

``mineru_document`` reuses ``POST /v2/runtime/preload`` for first-time
preparation. The client-side guard is driven by the runtime-declared
lifecycle catalog (``ocr.recognition-modes.v1``), never by this package's
static constants, and rejects fail-closed without sending any request.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest
from vibeocr.runtime_client import (
    MineruConfigError,
    RecognitionPreloadError,
    build_mineru_pipeline_selection,
    build_recognition_preload_plan,
)
from vibeocr.runtime_client.client import RuntimeHttpClient
from vibeocr.runtime_client.mock_server import MockRuntimeServer
from vibeocr.runtime_contracts import MineruConfig, MineruTier
from vibeocr.runtime_contracts.errors import ErrorCode
from vibeocr.runtime_contracts.generated.capabilities import (
    OCR_MINERU_CONFIG_V1,
    OCR_RECOGNITION_MODES_V1,
)
from vibeocr.runtime_contracts.generated.operations import operation_path

ROOT = Path(__file__).resolve().parents[3]
V2 = ROOT / "packages/vibeocr-contracts-py/src/vibeocr/runtime_contracts"

CAPABILITIES = [OCR_RECOGNITION_MODES_V1, OCR_MINERU_CONFIG_V1]


def _runtime_golden() -> dict:
    raw = (
        resources.files("vibeocr.runtime_contracts.golden")
        .joinpath("runtime-api.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(raw)


def _recognition_mode_catalog() -> dict:
    descriptor = next(
        item
        for item in _runtime_golden()["health"]["capability_descriptors"]
        if item["name"] == OCR_RECOGNITION_MODES_V1
    )
    return json.loads(json.dumps(descriptor["recognition_mode_catalog"]))


def _mineru_config_catalog() -> dict:
    descriptor = next(
        item
        for item in _runtime_golden()["health"]["capability_descriptors"]
        if item["name"] == OCR_MINERU_CONFIG_V1
    )
    return json.loads(json.dumps(descriptor["mineru_config_catalog"]))


def _tier(catalog: dict, tier_id: str) -> dict:
    return next(item for item in catalog["tiers"] if item["id"] == tier_id)


def test_plan_projects_mineru_preload_to_the_frozen_request_shape() -> None:
    plan = build_recognition_preload_plan(
        ["mineru_document"],
        capabilities=CAPABILITIES,
        recognition_mode_catalog=_recognition_mode_catalog(),
    )
    assert plan.pipelines == ("MinerU",)
    assert plan.recognition_modes == ("mineru_document",)

    combined = build_recognition_preload_plan(
        ["paddle_table", "mineru_document", "paddle_text", "paddle_table"],
        capabilities=CAPABILITIES,
        recognition_mode_catalog=_recognition_mode_catalog(),
    )
    assert combined.pipelines == ("TABLE_RECOGNITION", "MinerU", "OCR")
    assert combined.recognition_modes == (
        "paddle_table",
        "mineru_document",
        "paddle_text",
    )


def test_plan_flows_through_the_generic_transport_unchanged() -> None:
    plan = build_recognition_preload_plan(
        ["mineru_document"],
        capabilities=CAPABILITIES,
        recognition_mode_catalog=_recognition_mode_catalog(),
    )
    with MockRuntimeServer() as server:
        client = RuntimeHttpClient(
            base_url=server.base_url,
            session_token=server.session_token,
        )
        status = client.preload(
            plan.pipelines, recognition_modes=plan.recognition_modes
        )
        assert status["schema_version"] == 2
        request = next(
            item
            for item in server.state.requests
            if item.path == operation_path("preloadRuntime")
        )

    assert request.json() == {
        "pipelines": ["MinerU"],
        "recognition_modes": ["mineru_document"],
    }


def test_plan_fails_closed_without_capability_or_catalog() -> None:
    catalog = _recognition_mode_catalog()
    for capabilities, provided_catalog in (
        (["ocr.recognition.v2"], catalog),
        (None, catalog),
        (CAPABILITIES, None),
    ):
        with pytest.raises(RecognitionPreloadError) as excinfo:
            build_recognition_preload_plan(
                ["mineru_document"],
                capabilities=capabilities,
                recognition_mode_catalog=provided_catalog,
            )
        assert excinfo.value.code is ErrorCode.RECOGNITION_MODE_LIFECYCLE_UNSUPPORTED


def test_old_runtime_declaration_keeps_explicit_rejection() -> None:
    # A pre-2.8.1 runtime catalog declares mineru_document without preload
    # support. The guard must reject on that runtime's own declaration
    # instead of letting this package's new constants speak for it.
    catalog = _recognition_mode_catalog()
    mineru = next(item for item in catalog["modes"] if item["id"] == "mineru_document")
    assert mineru["lifecycle"]["supports_preload"] is True
    old_catalog = json.loads(json.dumps(catalog))
    old_mineru = next(
        item for item in old_catalog["modes"] if item["id"] == "mineru_document"
    )
    old_mineru["lifecycle"]["supports_preload"] = False

    with MockRuntimeServer() as server:
        client = RuntimeHttpClient(
            base_url=server.base_url,
            session_token=server.session_token,
        )
        with pytest.raises(RecognitionPreloadError) as excinfo:
            build_recognition_preload_plan(
                ["mineru_document"],
                capabilities=CAPABILITIES,
                recognition_mode_catalog=old_catalog,
            )
        assert client.health()["protocol_version"] == 2

    assert excinfo.value.code is ErrorCode.RECOGNITION_MODE_LIFECYCLE_UNSUPPORTED
    # Fail-closed means zero preload requests: only the explicit health probe
    # above reached the server.
    assert [item.path for item in server.state.requests] == [
        operation_path("getRuntimeHealth")
    ]


def test_plan_rejects_unknown_and_unlisted_modes() -> None:
    catalog = _recognition_mode_catalog()
    with pytest.raises(RecognitionPreloadError) as excinfo:
        build_recognition_preload_plan(
            ["turbo_text"],
            capabilities=CAPABILITIES,
            recognition_mode_catalog=catalog,
        )
    assert excinfo.value.code is ErrorCode.RECOGNITION_MODE_UNKNOWN

    unlisted = json.loads(json.dumps(catalog))
    unlisted["modes"] = [
        item for item in unlisted["modes"] if item["id"] != "mineru_document"
    ]
    with pytest.raises(RecognitionPreloadError) as excinfo:
        build_recognition_preload_plan(
            ["mineru_document"],
            capabilities=CAPABILITIES,
            recognition_mode_catalog=unlisted,
        )
    assert excinfo.value.code is ErrorCode.RECOGNITION_MODE_LIFECYCLE_UNSUPPORTED

    with pytest.raises(RecognitionPreloadError) as excinfo:
        build_recognition_preload_plan(
            [],
            capabilities=CAPABILITIES,
            recognition_mode_catalog=catalog,
        )
    assert excinfo.value.code is ErrorCode.VALIDATION_ERROR


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.pop("modes"),
        lambda c: c.update({"modes": []}),
        lambda c: c.update({"modes": [{"id": "mineru_document"}]}),
        lambda c: c["modes"][0].pop("lifecycle"),
        lambda c: c["modes"][0]["lifecycle"].pop("supports_preload"),
        lambda c: c["modes"][0]["lifecycle"].update({"supports_preload": "yes"}),
        lambda c: c["modes"].append(dict(c["modes"][0])),
        lambda c: c["modes"][0].pop("id"),
    ],
)
def test_plan_rejects_malformed_catalogs(mutate) -> None:
    catalog = _recognition_mode_catalog()
    mutate(catalog)
    with pytest.raises(RecognitionPreloadError) as excinfo:
        build_recognition_preload_plan(
            ["mineru_document"],
            capabilities=CAPABILITIES,
            recognition_mode_catalog=catalog,
        )
    assert excinfo.value.code is ErrorCode.RECOGNITION_MODE_LIFECYCLE_UNSUPPORTED


def test_plan_accepts_future_optional_response_fields() -> None:
    catalog = _recognition_mode_catalog()
    catalog["future_hint"] = {"value": 1}
    mineru = next(item for item in catalog["modes"] if item["id"] == "mineru_document")
    mineru["future_hint"] = ["supported"]
    mineru["lifecycle"]["future_hint"] = 7
    plan = build_recognition_preload_plan(
        ["mineru_document"],
        capabilities=CAPABILITIES + ["future.feature.v3"],
        recognition_mode_catalog=catalog,
    )
    assert plan.pipelines == ("MinerU",)


def test_preparation_rejects_before_and_builds_after_refreshed_catalog() -> None:
    # The full A2 story: the typed helper keeps rejecting a preparation-
    # required tier; after the caller preloads and re-reads the refreshed
    # catalog (standard now ready), the same typed request constructs.
    before = _mineru_config_catalog()
    assert _tier(before, "standard")["availability"] == "preparation_required"
    with pytest.raises(MineruConfigError) as excinfo:
        build_mineru_pipeline_selection(
            MineruConfig(tier=MineruTier.STANDARD),
            capabilities=CAPABILITIES,
            mineru_config_catalog=before,
        )
    assert excinfo.value.code is ErrorCode.MINERU_TIER_PREPARATION_REQUIRED

    preload_plan = build_recognition_preload_plan(
        ["mineru_document"],
        capabilities=CAPABILITIES,
        recognition_mode_catalog=_recognition_mode_catalog(),
    )
    assert preload_plan.recognition_modes == ("mineru_document",)

    refreshed = json.loads(json.dumps(before))
    _tier(refreshed, "standard")["availability"] = "ready"
    selection = build_mineru_pipeline_selection(
        MineruConfig(tier=MineruTier.STANDARD),
        capabilities=CAPABILITIES,
        mineru_config_catalog=refreshed,
    )
    assert selection.mineru is not None
    assert selection.mineru.tier is MineruTier.STANDARD


def test_mineru_preload_declaration_is_published_consistently() -> None:
    golden = _runtime_golden()["health"]
    descriptor = next(
        item
        for item in golden["capability_descriptors"]
        if item["name"] == OCR_RECOGNITION_MODES_V1
    )
    mineru = next(
        item
        for item in descriptor["recognition_mode_catalog"]["modes"]
        if item["id"] == "mineru_document"
    )
    # Preload support is the only lifecycle change; pinning stays rejected.
    assert mineru["lifecycle"] == {
        "kind": "process_keep_alive",
        "supports_preload": True,
        "supports_ttl": True,
        "supports_pinning": False,
        "supports_release": True,
    }

    # ocr.mineru-config.v1 shipped with the official 2.8.1 release.
    mineru_config = next(
        item
        for item in golden["capability_descriptors"]
        if item["name"] == OCR_MINERU_CONFIG_V1
    )
    assert mineru_config["introduced_in"] == "2.8.1"
    registry = json.loads((V2 / "capabilities.json").read_text(encoding="utf-8"))
    assert registry["definitions"][OCR_MINERU_CONFIG_V1]["introduced_in"] == "2.8.1"
