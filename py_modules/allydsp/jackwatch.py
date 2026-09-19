"""Pause the chain while headphones use the shared analog sink."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Optional

from . import dsp_runtime, hardware
from .log import logger


class JackWatcher:
    def __init__(self, interval: float = 3.0, on_change: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self.interval = interval
        self.on_change = on_change
        self.headphones: Optional[bool] = None
        self.paused = False
        self._task: Optional[asyncio.Task] = None

    def state(self) -> Dict[str, Any]:
        return {"headphones": self.headphones, "paused": self.paused}

    def start(self, should_run: Callable[[], bool]) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_event_loop().create_task(self.run(should_run))

    def cancel(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def run(self, should_run: Callable[[], bool]) -> None:
        while True:
            try:
                dump = await asyncio.to_thread(hardware.pw_dump)
                if dump:
                    hp = hardware.headphones_active(hardware.output_route(dump))
                    if hp != self.headphones:
                        self.headphones = hp
                        if hp:
                            if await asyncio.to_thread(dsp_runtime.is_active):
                                await asyncio.to_thread(dsp_runtime.stop)
                                self.paused = True
                                logger.info("headphones detected: chain paused")
                        elif self.paused:
                            self.paused = False
                            if should_run():
                                await asyncio.to_thread(dsp_runtime.start)
                                logger.info("headphones removed: chain resumed")
                        if self.on_change:
                            res = self.on_change(self.state())
                            if asyncio.iscoroutine(res):
                                await res
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("jack watcher: %s", e)
            await asyncio.sleep(self.interval)
