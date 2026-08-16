from __future__ import annotations

import asyncio
import base64
import json
from importlib import resources

import pytest
from vibeocr.runtime_client.client import (
    MultipartAttachment,
    RuntimeClientError,
    RuntimeHttpClient,
    SupervisorClient,
    _parse_settings,
)
from vibeocr.runtime_client.mock_server import MockRuntimeServer
from vibeocr.runtime_client.process import ReadyEnvelope
from vibeocr.runtime_contracts import (
    CancelMode,
    ContractError,
    JobCommand,
    JobCommandKind,
    JobKind,
    JobPriority,
    PipelineSelection,
    SubmitItem,
    SubmitRequest,
)
from vibeocr.runtime_contracts.errors import ErrorCategories, ErrorCode, ErrorPayload
from vibeocr.runtime_contracts.generated.operations import operation_path


def _runtime_golden() -> dict:
    raw = (
        resources.files("vibeocr.runtime_contracts.golden")
        .joinpath("runtime-api.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(raw)


def _submit_request() -> SubmitRequest:
    return SubmitRequest(
        request_id="request-golden",
        kind=JobKind.RECOGNITION,
        priority=JobPriority.INTERACTIVE,
        pipeline=PipelineSelection(pipeline_id="OCR", options={}),
        items=(
            SubmitItem(
                client_item_key="item-0",
                ordinal=0,
                display_name="page.png",
                source={"type": "upload.v1", "attachment": "attachment-0"},
            ),
        ),
    )


def test_mock_serves_golden_health_and_typed_auth_error() -> None:
    golden = _runtime_golden()
    with MockRuntimeServer() as server:
        anonymous = RuntimeHttpClient(base_url=server.base_url)

        assert anonymous.health() == golden["health"]
        with pytest.raises(RuntimeClientError) as raised:
            anonymous.residency()

    assert raised.value.status_code == 401
    assert raised.value.code is ErrorCode.UNAUTHORIZED
    assert raised.value.detail == golden["unauthorized_error"]["detail"]


def test_runtime_client_error_preserves_retry_after_hint() -> None:
    error = RuntimeClientError.from_payload(
        ErrorPayload(
            schema_version=2,
            instance_id="sup-1",
            code=ErrorCode.BACKEND_UNAVAILABLE,
            message="busy",
            category=ErrorCategories.BACKEND_UNAVAILABLE,
            retryable=True,
            retry_after=5,
        )
    )

    assert error.retry_after == 5


def test_runtime_client_convenience_methods_bind_operation_and_command_ids() -> None:
    class RecordingClient(RuntimeHttpClient):
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def request_json(self, operation_id: str, **kwargs):
            self.calls.append((operation_id, kwargs))
            requested = kwargs.get("json_body", {})
            operation = requested.get("operation", "repair")
            operation_id_value = requested.get(
                "operation_id", requested.get("new_operation_id", "op-1")
            )
            return {
                "schema_version": 2,
                "operation_id": operation_id_value,
                "snapshot": {
                    "operation_id": operation_id_value,
                    "sequence": 1,
                    "operation": operation,
                    "operation_state": "running",
                    "phase": "install_profile",
                    "profile_id": "win-x64-cpu",
                    "updated_at": "2026-08-05T12:00:00Z",
                },
                "negotiated_capabilities": ["runtime.maintenance.v2"],
            }

    client = RecordingClient()
    client.ensure_runtime(
        operation_id="op-9",
        install_component_ids=("paddleocr-cpu", "mineru-cpu"),
        download_source_ids=("pypi-tuna", "hf-mirror"),
    )
    client.repair_runtime(operation_id="op-1", component_ids=("ocr_engine",))
    client.retry_runtime(
        "op-0",
        command_id="cmd-1",
        new_operation_id="op-1",
        expected_sequence=7,
        install_component_ids=(),
        download_source_ids=("pypi-official", "hf-official"),
    )

    assert client.calls[0] == (
        "startRuntimeMaintenance",
        {
            "json_body": {
                "operation": "ensure",
                "operation_id": "op-9",
                "install_component_ids": ["paddleocr-cpu", "mineru-cpu"],
                "download_source_ids": ["pypi-tuna", "hf-mirror"],
            },
            "timeout": 600.0,
        },
    )
    assert client.calls[1] == (
        "startRuntimeMaintenance",
        {
            "json_body": {
                "operation": "repair",
                "operation_id": "op-1",
                "component_ids": ["ocr_engine"],
            },
            "timeout": 600.0,
        },
    )
    assert client.calls[2][0] == "commandRuntimeMaintenance"
    assert client.calls[2][1]["json_body"] == {
        "command_id": "cmd-1",
        "command": "retry",
        "target_operation_id": "op-0",
        "new_operation_id": "op-1",
        "expected_sequence": 7,
        "install_component_ids": [],
        "download_source_ids": ["pypi-official", "hf-official"],
    }


def test_settings_parser_preserves_download_source_selection() -> None:
    payload = {
        "schema_version": 2,
        "residency": {"default_ttl_seconds": 300, "pipelines": []},
        "extra": {},
        "download_source_ids": ["pypi-tuna", "hf-mirror"],
    }

    parsed = _parse_settings(payload)

    assert parsed.download_source_ids == ("pypi-tuna", "hf-mirror")
    assert parsed.to_payload() == payload

    for invalid in ([], [""], ["pypi-tuna", "pypi-tuna"], [1]):
        with pytest.raises(RuntimeClientError):
            _parse_settings({**payload, "download_source_ids": invalid})


def test_runtime_client_observe_rejects_page_that_skips_requested_cursor() -> None:
    class GapClient(RuntimeHttpClient):
        def request_json(self, operation_id: str, **kwargs):
            del operation_id, kwargs
            snapshot = {
                "operation_id": "op-gap",
                "sequence": 3,
                "operation": "ensure",
                "operation_state": "running",
                "phase": "install_profile",
                "profile_id": "win-x64-cpu",
                "updated_at": "2026-08-05T12:00:00Z",
            }
            return {
                "schema_version": 2,
                "operation_id": "op-gap",
                "snapshot": snapshot,
                "events": [
                    {
                        "schema_version": 2,
                        "event_type": "snapshot",
                        "sequence": 3,
                        "operation": "ensure",
                        "snapshot": snapshot,
                        "message_code": "runtime.install.profile",
                    }
                ],
                "oldest_sequence": 1,
                "through_sequence": 3,
                "more": False,
                "replay_expires_at": None,
            }

    with pytest.raises(ContractError, match="does not follow cursor"):
        GapClient(base_url="http://127.0.0.1").observe_runtime_maintenance(
            "op-gap", after_sequence=1
        )


@pytest.mark.parametrize(
    ("response_operation_id", "more", "message"),
    [
        ("op-other", False, "operation_id mismatch"),
        ("op-empty", True, "cannot have more events"),
    ],
)
def test_runtime_client_observe_rejects_identity_mismatch_or_empty_more_page(
    response_operation_id: str,
    more: bool,
    message: str,
) -> None:
    class InvalidCursorClient(RuntimeHttpClient):
        def request_json(self, operation_id: str, **kwargs):
            del operation_id, kwargs
            return {
                "schema_version": 2,
                "operation_id": response_operation_id,
                "snapshot": {
                    "operation_id": response_operation_id,
                    "sequence": 1,
                    "operation": "ensure",
                    "operation_state": "running",
                    "phase": "install_profile",
                    "profile_id": "win-x64-cpu",
                    "updated_at": "2026-08-05T12:00:00Z",
                },
                "events": [],
                "oldest_sequence": 1,
                "through_sequence": 0,
                "more": more,
                "replay_expires_at": None,
            }

    with pytest.raises(ContractError, match=message):
        InvalidCursorClient(base_url="http://127.0.0.1").observe_runtime_maintenance(
            "op-empty"
        )


def test_async_runtime_client_revalidates_transport_observe_cursor() -> None:
    class WrongOperationTransport(RuntimeHttpClient):
        def request_json(self, operation_id: str, **kwargs):
            del operation_id, kwargs
            return {
                "schema_version": 2,
                "operation_id": "op-other",
                "snapshot": {
                    "operation_id": "op-other",
                    "sequence": 1,
                    "operation": "ensure",
                    "operation_state": "running",
                    "phase": "install_profile",
                    "profile_id": "win-x64-cpu",
                    "updated_at": "2026-08-05T12:00:00Z",
                },
                "events": [],
                "oldest_sequence": 1,
                "through_sequence": 0,
                "more": False,
                "replay_expires_at": None,
            }

    async def scenario() -> None:
        client = SupervisorClient(base_url="http://127.0.0.1", session_token="token")
        client._transport = WrongOperationTransport(base_url="http://127.0.0.1")
        async with client:
            await client.observe_runtime_maintenance("op-empty")

    with pytest.raises(ContractError, match="operation_id mismatch"):
        asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda health: health.pop("protocol_version"),
        lambda health: health.__setitem__("ready", "yes"),
    ],
    ids=("missing-required", "wrong-type"),
)
def test_runtime_client_rejects_response_schema_violations(mutation) -> None:
    with MockRuntimeServer() as server:
        mutation(server._golden["health"])
        client = RuntimeHttpClient(base_url=server.base_url)

        with pytest.raises(RuntimeClientError) as raised:
            client.health()

    assert raised.value.code is ErrorCode.ADAPTER_PROTOCOL_VIOLATION
    assert raised.value.status_code == 200
    assert raised.value.detail["operation_id"] == "getRuntimeHealth"
    assert raised.value.detail["reason"]


def test_runtime_client_preserves_unknown_response_fields() -> None:
    with MockRuntimeServer() as server:
        server._golden["health"]["future_optional_field"] = {"version": 3}
        client = RuntimeHttpClient(base_url=server.base_url)

        health = client.health()

    assert health["future_optional_field"] == {"version": 3}


def test_ready_envelope_preserves_future_capabilities() -> None:
    payload = {
        "ready": True,
        "pid": 1,
        "port": 2,
        "instance_id": "instance",
        "protocol_version": 2,
        "schema_version": 2,
        "ready_version": 1,
        "capabilities": ["ocr.recognition.v2", "future.feature.v3"],
    }

    ready = ReadyEnvelope.from_line(json.dumps(payload))

    assert ready.capabilities == ("ocr.recognition.v2", "future.feature.v3")


def test_multipart_submit_is_recorded_and_matches_manifest() -> None:
    golden = _runtime_golden()
    png = base64.b64decode(golden["png"]["content_base64"], validate=True)
    request = _submit_request()
    with MockRuntimeServer() as server:
        client = RuntimeHttpClient(
            base_url=server.base_url,
            session_token=server.session_token,
        )

        job_ref = client.submit_job(
            request.to_payload(),
            {
                "attachment-0": MultipartAttachment(
                    filename="page.png",
                    media_type="image/png",
                    content=png,
                )
            },
        )

        assert job_ref["schema_version"] == 2
        assert len(server.state.submissions) == 1
        submission = server.state.submissions[0]
        assert submission.manifest == request.to_payload()
        assert submission.attachments["attachment-0"].filename == "page.png"
        assert submission.attachments["attachment-0"].media_type == "image/png"
        assert submission.attachments["attachment-0"].content == png
        assert server.state.requests[-1].path == operation_path("submitJob")


def test_mock_serves_golden_ndjson_and_png() -> None:
    golden = _runtime_golden()
    with MockRuntimeServer() as server:
        client = RuntimeHttpClient(
            base_url=server.base_url,
            session_token=server.session_token,
        )

        progress = client.load_pdf_session("session / golden")
        render = client.render_pdf_page("session / golden", page=0, size=64)

    assert progress == golden["ndjson_progress_lines"]
    assert render.media_type == golden["png"]["media_type"]
    assert render.body == base64.b64decode(
        golden["png"]["content_base64"], validate=True
    )
    assert "%2F" in server.state.requests[0].path


def test_async_supervisor_client_preserves_existing_submit_and_settings_api() -> None:
    request = _submit_request()

    async def scenario(server: MockRuntimeServer) -> None:
        async with SupervisorClient(
            base_url=server.base_url,
            session_token=server.session_token,
            instance_id="sup-golden",
        ) as client:
            health = await client.health()
            job_ref = await client.submit(
                request,
                {"attachment-0": ("image/png", b"png")},
            )
            settings = await client.get_settings()
            observed = await client.observe(job_ref.job_id)
            cancellation = await client.command(
                JobCommand(
                    command_id="command-golden",
                    kind=JobCommandKind.CANCEL,
                    job_id=job_ref.job_id,
                )
            )
            residency = await client.residency()
            released = await client.release_idle()
            preloaded = await client.preload(("OCR",))
            updated_settings = await client.put_settings(settings)
            exported = await client.export_ocr(
                raw_text="text",
                markdown_text="text",
                html_text="<p>text</p>",
                output_path="result.md",
                fmt="markdown",
            )
            decoded = await client.decode_qrcode(b"png")
            generated = await client.generate_qrcode("hello")

        assert health["protocol_version"] == 2
        assert job_ref.schema_version == 2
        assert observed.schema_version == 2
        assert cancellation is CancelMode.COOPERATIVE
        assert residency.schema_version == 2
        assert released == residency
        assert preloaded == residency
        assert settings.schema_version == 2
        assert updated_settings == settings
        assert exported["output_path"] == "result.md"
        assert decoded == []
        assert generated == _runtime_golden()["png"]["content_base64"]

    with MockRuntimeServer() as server:
        asyncio.run(scenario(server))


def test_async_supervisor_client_requires_context_manager() -> None:
    async def scenario(server: MockRuntimeServer) -> None:
        client = SupervisorClient(
            base_url=server.base_url,
            session_token=server.session_token,
        )
        with pytest.raises(RuntimeError, match="async context manager"):
            await client.health()

    with MockRuntimeServer() as server:
        asyncio.run(scenario(server))
