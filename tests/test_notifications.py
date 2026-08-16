from __future__ import annotations

import json

import httpx
import pytest

from incident_investigator.adapters.notifications import TelegramNotificationSink
from incident_investigator.application.notifications import BestEffortNotifier


@pytest.mark.asyncio
async def test_telegram_sink_sends_operational_message() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        base_url="https://api.telegram.test/bot-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        sink = TelegramNotificationSink(
            client,
            chat_id="123",
            dashboard_url="http://dashboard.test",
            language="en",
        )
        await sink.publish(
            "incident.received",
            {
                "incident": {"service": "payments", "title": "High error rate"},
                "status": "queued",
            },
        )

    assert "What you need to do: Nothing yet" in captured["text"]
    assert "http://dashboard.test" in captured["text"]


@pytest.mark.asyncio
async def test_telegram_sink_includes_created_change_request_url() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        base_url="https://api.telegram.test/bot-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        sink = TelegramNotificationSink(
            client,
            chat_id="123",
            dashboard_url="http://dashboard.test",
            language="en",
        )
        await sink.publish(
            "draft_pr.created",
            {
                "incident": {"service": "payments", "title": "CI failed"},
                "status": "completed",
                "action_result": {
                    "external_reference": "https://github.test/pull/42"
                },
            },
        )

    assert "https://github.test/pull/42" in captured["text"]
    assert "not merged automatically" in captured["text"]


@pytest.mark.asyncio
async def test_telegram_escalation_explains_manual_next_step_in_russian() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        base_url="https://api.telegram.test/bot-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        sink = TelegramNotificationSink(
            client,
            chat_id="123",
            dashboard_url="http://dashboard.test",
            language="ru",
        )
        await sink.publish(
            "investigation.completed",
            {
                "incident": {"service": "payments", "title": "High error rate"},
                "status": "escalated",
                "graph_status": "escalated",
            },
        )

    assert "Нужна ручная проверка" in captured["text"]
    assert "Что делать:" in captured["text"]
    assert "Изменений не внесено" in captured["text"]


@pytest.mark.asyncio
async def test_telegram_input_request_includes_the_agents_exact_question() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        base_url="https://api.telegram.test/bot-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        sink = TelegramNotificationSink(
            client,
            chat_id="123",
            dashboard_url="http://dashboard.test",
            language="ru",
        )
        await sink.publish(
            "input.required",
            {
                "incident": {"service": "payments", "title": "High error rate"},
                "status": "awaiting_input",
                "information_request": {
                    "question": "Приложите логи payments за 12:20–12:25 UTC."
                },
            },
        )

    assert "Агенту нужны данные" in captured["text"]
    assert "Приложите логи payments" in captured["text"]
    assert "Изменений не внесено" in captured["text"]


class FailingSink:
    name = "failing"

    async def publish(self, event_name, payload) -> None:
        del event_name, payload
        raise ConnectionError("notification endpoint unavailable")


@pytest.mark.asyncio
async def test_notification_failure_does_not_escape_best_effort_boundary() -> None:
    errors = await BestEffortNotifier([FailingSink()]).publish("test", {})

    assert len(errors) == 1
    assert errors[0].startswith("failing:ConnectionError")
