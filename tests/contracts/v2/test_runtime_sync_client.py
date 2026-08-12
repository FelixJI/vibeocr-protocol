from __future__ import annotations

import asyncio
import base64
import threading

import pytest
import vibeocr.runtime_client as runtime_client
from vibeocr.runtime_client.background_loop import (
    BackgroundLoop,
    get_background_loop,
    shutdown_background_loop,
)
from vibeocr.runtime_client.mock_server import MockRuntimeServer
from vibeocr.runtime_client.sync_client import SyncSupervisorClient
from vibeocr.runtime_contracts import (
    CancelMode,
    JobCommand,
    JobCommandKind,
    JobKind,
    JobPriority,
    PipelineSelection,
    SubmitItem,
    SubmitRequest,
)
from vibeocr.runtime_contracts.generated.operations import operation_path


def test_runtime_client_exports_the_supported_synchronous_interface() -> None:
    assert runtime_client.SyncSupervisorClient is SyncSupervisorClient
    assert runtime_client.get_background_loop is get_background_loop
    assert runtime_client.shutdown_background_loop is shutdown_background_loop
    assert not hasattr(runtime_client, "BackgroundLoop")


def test_background_loop_runs_coroutines_and_restarts_after_shutdown() -> None:
    async def identify_loop() -> int:
        return id(asyncio.get_running_loop())

    shutdown_background_loop()
    try:
        first = get_background_loop()
        assert first.run(identify_loop()) == first.run(identify_loop())

        shutdown_background_loop()
        assert first._loop.is_closed()

        second = get_background_loop()
        assert second is not first
        assert second.run(identify_loop()) == second.run(identify_loop())
    finally:
        shutdown_background_loop()


def test_background_loop_cancels_timed_out_coroutines_and_closes() -> None:
    cancelled = threading.Event()

    async def wait_forever() -> None:
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    loop = BackgroundLoop()
    try:
        with pytest.raises(TimeoutError):
            loop.run(wait_forever(), timeout=0.01)
        assert cancelled.wait(timeout=1.0)
    finally:
        loop.stop()

    assert loop._loop.is_closed()


def test_background_loop_closes_stream_after_item_timeout() -> None:
    closed = threading.Event()

    async def stalled_stream():
        try:
            await asyncio.Future()
            yield "unreachable"
        finally:
            closed.set()

    loop = BackgroundLoop()
    try:
        stream = loop.iterate_stream(stalled_stream, timeout_per_item=0.01)
        with pytest.raises(TimeoutError):
            next(stream)
        assert closed.wait(timeout=1.0)
    finally:
        loop.stop()

    assert loop._loop.is_closed()


def test_sync_supervisor_client_uses_the_runtime_job_interface() -> None:
    request = SubmitRequest(
        request_id="request-sync",
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

    shutdown_background_loop()
    try:
        with MockRuntimeServer() as server:
            client = SyncSupervisorClient(
                base_url=server.base_url,
                session_token=server.session_token,
                instance_id="sup-sync",
            )
            client.start()
            job_ref = client.submit(
                request,
                {"attachment-0": ("image/png", b"png")},
            )
            update = client.observe(job_ref.job_id)
            result = client.command(
                JobCommand(
                    command_id="command-sync",
                    kind=JobCommandKind.CANCEL,
                    job_id=job_ref.job_id,
                )
            )
            exported = client.export_ocr(
                raw_text="text",
                markdown_text="text",
                html_text="<p>text</p>",
                raw_blocks=[{"text": "block"}],
                output_path="result.md",
                fmt="markdown",
                overwrite=True,
            )
            decoded = client.decode_qrcode(b"png")
            generated = client.generate_qrcode("hello", options={"scale": 2})
            client.close()
            client.close()

        assert job_ref.schema_version == 2
        assert update.schema_version == 2
        assert result is CancelMode.COOPERATIVE
        assert exported["output_path"] == "result.md"
        assert decoded == []
        assert generated

        def request_json(operation_id: str) -> dict:
            path = operation_path(operation_id)
            return next(
                request.json()
                for request in server.state.requests
                if request.path == path
            )

        assert request_json("exportOcr") == {
            "raw_text": "text",
            "markdown_text": "text",
            "html_text": "<p>text</p>",
            "raw_blocks": [{"text": "block"}],
            "output_path": "result.md",
            "format": "markdown",
            "overwrite": True,
        }
        assert request_json("decodeQrCode") == {
            "image": base64.b64encode(b"png").decode("ascii")
        }
        assert request_json("generateQrCode") == {
            "data": "hello",
            "format": "qrcode",
            "options": {"scale": 2},
        }
    finally:
        shutdown_background_loop()
