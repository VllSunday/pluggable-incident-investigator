from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class TelegramNotificationSink:
    name = "telegram"

    def __init__(self, client: httpx.AsyncClient, *, chat_id: str) -> None:
        self._client = client
        self._chat_id = chat_id

    async def publish(self, event_name: str, payload: Mapping[str, Any]) -> None:
        incident = payload.get("incident", {})
        if not isinstance(incident, Mapping):
            incident = {}
        service = incident.get("service", "unknown service")
        title = incident.get("title", "Incident update")
        status = payload.get("status", event_name)
        action_result = payload.get("action_result")
        reference = ""
        if isinstance(action_result, Mapping) and action_result.get("external_reference"):
            reference = f"\nChange: {action_result['external_reference']}"
        text = (
            f"Incident Investigator\n"
            f"Event: {event_name}\n"
            f"Service: {service}\n"
            f"Status: {status}\n"
            f"Summary: {title}{reference}"
        )
        response = await self._client.post(
            "/sendMessage",
            json={
                "chat_id": self._chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )
        response.raise_for_status()
