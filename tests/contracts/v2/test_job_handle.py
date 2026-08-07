from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from vibeocr.runtime_client.job_handle import JobHandle
from vibeocr.runtime_contracts import (
    ItemOutcome,
    ItemState,
    JobItem,
    JobKind,
    JobPriority,
    JobRef,
    JobSnapshot,
    JobState,
    JobUpdate,
)

if TYPE_CHECKING:
    from vibeocr.runtime_client.client import SupervisorClient


def test_job_handle_result_preserves_success_payload_type() -> None:
    item = JobItem(
        item_id="item-1",
        display_name="page.png",
        state=ItemState.SUCCEEDED,
    )
    update = JobUpdate(
        snapshot=JobSnapshot(
            job_id="job-1",
            kind=JobKind.RECOGNITION,
            priority=JobPriority.INTERACTIVE,
            state=JobState.COMPLETED,
            items=(item,),
        ),
        events=(),
        outcomes=(
            ItemOutcome(
                item_id="item-1",
                state=ItemState.SUCCEEDED,
                attempt=1,
                payload_type="ocr.v1",
                payload={"raw_text": "hello"},
            ),
        ),
        through_sequence=1,
    )

    class FakeClient:
        async def observe(self, job_id: str, *, after_sequence: int = 0) -> JobUpdate:
            assert job_id == "job-1"
            assert after_sequence == 0
            return update

    entries = asyncio.run(
        JobHandle(
            client=cast("SupervisorClient", FakeClient()),
            ref=JobRef(job_id="job-1", items=(item,)),
        ).result()
    )

    assert entries[0].payload_type == "ocr.v1"
    assert entries[0].payload == {"raw_text": "hello"}
