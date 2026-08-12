from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from incident_investigator.core.ports import NotificationSink


class BestEffortNotifier:
    def __init__(self, sinks: Sequence[NotificationSink] = ()) -> None:
        self._sinks = tuple(sinks)

    async def publish(self, event_name: str, payload: Mapping[str, Any]) -> list[str]:
        results = await asyncio.gather(
            *(sink.publish(event_name, payload) for sink in self._sinks),
            return_exceptions=True,
        )
        return [
            f"{self._sinks[index].name}:{type(result).__name__}:{result}"
            for index, result in enumerate(results)
            if isinstance(result, BaseException)
        ]

