from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class TelegramNotificationSink:
    name = "telegram"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        chat_id: str,
        dashboard_url: str | None = None,
        language: str = "ru",
    ) -> None:
        self._client = client
        self._chat_id = chat_id
        self._dashboard_url = dashboard_url
        self._language = language if language in {"ru", "en"} else "ru"

    async def publish(self, event_name: str, payload: Mapping[str, Any]) -> None:
        incident = payload.get("incident", {})
        if not isinstance(incident, Mapping):
            incident = {}
        service = incident.get("service", "unknown service")
        title = incident.get("title", "Incident update")
        status = payload.get("status", event_name)
        graph_status = payload.get("graph_status")
        information_request = payload.get("information_request")
        request_question = (
            str(information_request.get("question"))
            if isinstance(information_request, Mapping)
            and information_request.get("question")
            else None
        )
        action_result = payload.get("action_result")
        reference = (
            str(action_result.get("external_reference"))
            if isinstance(action_result, Mapping)
            and action_result.get("external_reference")
            else None
        )
        text = self._message(
            event_name=event_name,
            service=str(service),
            title=str(title),
            status=str(status),
            graph_status=str(graph_status or ""),
            reference=reference,
            request_question=request_question,
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

    def _message(
        self,
        *,
        event_name: str,
        service: str,
        title: str,
        status: str,
        graph_status: str,
        reference: str | None,
        request_question: str | None,
    ) -> str:
        if self._language == "en":
            return self._message_en(
                event_name, service, title, status, graph_status, reference,
                request_question,
            )
        return self._message_ru(
            event_name, service, title, status, graph_status, reference,
            request_question,
        )

    def _message_ru(
        self,
        event_name: str,
        service: str,
        title: str,
        status: str,
        graph_status: str,
        reference: str | None,
        request_question: str | None,
    ) -> str:
        del graph_status
        if event_name == "incident.received":
            heading = "🔎 Новый инцидент"
            result = "Агент начал собирать доказательства и проверять гипотезы."
            next_step = "Пока ничего — дождитесь итогового уведомления."
            safety = "Изменений не внесено."
        elif event_name == "approval.required":
            heading = "🟠 Требуется ваше решение"
            result = "Исправление подготовлено и прошло sandbox-проверки."
            next_step = "Откройте dashboard, проверьте блок 05 и разрешите или отклоните действие."
            safety = "Без вашего решения ветка или PR/MR не будут опубликованы."
        elif event_name == "input.required":
            heading = "📎 Агенту нужны данные"
            result = "Расследование безопасно приостановлено на том же этапе."
            next_step = request_question or "Откройте dashboard и ответьте на запрос агента."
            safety = "Изменений не внесено. Не отправляйте пароли и токены."
        elif event_name == "draft_pr.created":
            heading = "✅ Черновик изменения создан"
            result = "Агент создал отдельную ветку и draft PR/MR."
            next_step = "Проверьте diff и результаты CI, затем примите решение о merge вручную."
            safety = "Автоматического merge нет."
        elif status == "escalated":
            heading = "🟠 Нужна ручная проверка"
            result = (
                "Агент завершил расследование, но безопасного автоматического "
                "действия недостаточно."
            )
            next_step = (
                "Откройте dashboard: начните с блока «Что делать сейчас», "
                "затем проверьте разделы 02–04."
            )
            safety = "Изменений не внесено."
        elif status == "failed":
            heading = "🔴 Ошибка расследования"
            result = "Расследование не удалось завершить."
            next_step = "Откройте dashboard и проверьте системные ошибки и подключения."
            safety = "Изменений не внесено."
        else:
            heading = "✅ Расследование завершено"
            result = "Итог расследования сохранён."
            next_step = "Откройте dashboard и проверьте результат и восстановление сервиса."
            safety = "Критические действия выполняются только через Human-in-the-Loop."
        return self._compose(
            heading, service, title, result, next_step, safety, reference,
            labels=(
                "Сервис", "Что произошло", "Результат", "Что делать",
                "Безопасность", "Dashboard", "Изменение",
            ),
        )

    def _message_en(
        self,
        event_name: str,
        service: str,
        title: str,
        status: str,
        graph_status: str,
        reference: str | None,
        request_question: str | None,
    ) -> str:
        del graph_status
        if event_name == "incident.received":
            heading = "🔎 New incident"
            result = "The agent started collecting evidence and checking hypotheses."
            next_step = "Nothing yet — wait for the final notification."
            safety = "No changes were made."
        elif event_name == "approval.required":
            heading = "🟠 Your decision is required"
            result = "A fix is prepared and passed the sandbox checks."
            next_step = "Open the dashboard, review section 05, then allow or reject the action."
            safety = "No branch or PR/MR is published without your decision."
        elif event_name == "input.required":
            heading = "📎 The agent needs evidence"
            result = "The investigation is safely paused at the same checkpoint."
            next_step = request_question or "Open the dashboard and answer the agent's request."
            safety = "No changes were made. Do not send passwords or tokens."
        elif event_name == "draft_pr.created":
            heading = "✅ Draft change created"
            result = "The agent created a separate branch and a draft PR/MR."
            next_step = "Review the diff and CI results, then decide on merge manually."
            safety = "The change was not merged automatically."
        elif status == "escalated":
            heading = "🟠 Manual review needed"
            result = (
                "The investigation finished without enough evidence for a safe "
                "automatic action."
            )
            next_step = (
                "Open the dashboard: start with ‘What to do now’, then review "
                "sections 02–04."
            )
            safety = "No changes were made."
        elif status == "failed":
            heading = "🔴 Investigation failed"
            result = "The investigation could not be completed."
            next_step = "Open the dashboard and review system errors and connections."
            safety = "No changes were made."
        else:
            heading = "✅ Investigation completed"
            result = "The investigation outcome was saved."
            next_step = "Open the dashboard and verify the outcome and service recovery."
            safety = "Critical actions always require Human-in-the-Loop."
        return self._compose(
            heading, service, title, result, next_step, safety, reference,
            labels=(
                "Service", "What happened", "Result", "What you need to do",
                "Safety", "Dashboard", "Change",
            ),
        )

    def _compose(
        self,
        heading: str,
        service: str,
        title: str,
        result: str,
        next_step: str,
        safety: str,
        reference: str | None,
        *,
        labels: tuple[str, str, str, str, str, str, str],
    ) -> str:
        (
            service_label,
            happened_label,
            result_label,
            next_label,
            safety_label,
            dashboard_label,
            change_label,
        ) = labels
        lines = [
            heading,
            f"{service_label}: {service}",
            f"{happened_label}: {title}",
            f"{result_label}: {result}",
            f"{next_label}: {next_step}",
            f"{safety_label}: {safety}",
        ]
        if self._dashboard_url:
            lines.append(f"{dashboard_label}: {self._dashboard_url}")
        if reference:
            lines.append(f"{change_label}: {reference}")
        return "\n".join(lines)
