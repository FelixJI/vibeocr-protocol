"""Process-wide asyncio loop for synchronous Runtime Client façades."""

from __future__ import annotations

import asyncio
import threading
from typing import Any


class BackgroundLoop:
    """Drive Runtime Client coroutines from non-async worker threads."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, name="runtime-client-loop", daemon=True
        )
        self._thread.start()
        self._lock = threading.Lock()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def stop(self) -> None:
        if self._loop.is_closed():
            return
        if self._loop.is_running():
            shutdown = asyncio.run_coroutine_threadsafe(
                self._cancel_pending_tasks(), self._loop
            )
            try:
                shutdown.result(timeout=2.0)
            except TimeoutError:
                shutdown.cancel()
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)
        if not self._thread.is_alive():
            self._loop.close()

    async def _cancel_pending_tasks(self) -> None:
        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await self._loop.shutdown_asyncgens()

    def run(self, coroutine: Any, timeout: float | None = None) -> Any:
        with self._lock:
            completed = threading.Event()

            async def tracked() -> Any:
                try:
                    return await coroutine
                finally:
                    completed.set()

            future = asyncio.run_coroutine_threadsafe(tracked(), self._loop)
            try:
                return future.result(timeout=timeout)
            except TimeoutError:
                if not future.done():
                    future.cancel()
                    completed.wait(timeout=2.0)
                raise

    def iterate_stream(
        self, async_gen_factory: Any, timeout_per_item: float | None = None
    ):
        holder: dict[str, Any] = {}

        async def seed() -> None:
            holder["generator"] = async_gen_factory()

        self.run(seed())

        async def pull(generator: Any) -> tuple[Any, bool]:
            try:
                return await generator.__anext__(), False
            except StopAsyncIteration:
                return None, True

        generator = holder["generator"]
        try:
            while True:
                value, done = self.run(
                    pull(generator),
                    timeout=timeout_per_item,
                )
                if done:
                    return
                yield value
        finally:
            close = getattr(generator, "aclose", None)
            if close is not None:
                self.run(close())


_BACKGROUND_LOOP: BackgroundLoop | None = None
_BACKGROUND_LOOP_LOCK = threading.Lock()


def get_background_loop() -> BackgroundLoop:
    global _BACKGROUND_LOOP
    with _BACKGROUND_LOOP_LOCK:
        if _BACKGROUND_LOOP is None:
            _BACKGROUND_LOOP = BackgroundLoop()
        return _BACKGROUND_LOOP


def shutdown_background_loop() -> None:
    global _BACKGROUND_LOOP
    with _BACKGROUND_LOOP_LOCK:
        loop = _BACKGROUND_LOOP
        _BACKGROUND_LOOP = None
    if loop is not None:
        loop.stop()
