from __future__ import annotations

import hmac
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from incident_investigator.domain import IncidentEvent, IncidentKind, IncidentSource


class InvalidWebhookToken(ValueError):
    pass


class AlertmanagerEventAdapter:
    name = "alertmanager"

    def __init__(
        self, shared_token: str, *, allowed_actions: tuple[str, ...] = ()
    ) -> None:
        if not shared_token:
            raise ValueError("Alertmanager shared token must not be empty")
        self._shared_token = shared_token
        self._allowed_actions = allowed_actions

    def verify(self, body: bytes, headers: Mapping[str, str]) -> None:
        del body
        authorization = headers.get("authorization", "")
        bearer = (
            authorization.removeprefix("Bearer ")
            if authorization.startswith("Bearer ")
            else ""
        )
        supplied = headers.get("x-incident-token", "") or bearer
        if not hmac.compare_digest(supplied, self._shared_token):
            raise InvalidWebhookToken("Invalid Alertmanager webhook token")

    def normalize(self, payload: Mapping[str, Any]) -> list[IncidentEvent]:
        if payload.get("status") != "firing":
            return []

        raw_alerts = payload.get("alerts")
        if not isinstance(raw_alerts, list):
            raise ValueError("Alertmanager payload is missing alerts")

        incidents: list[IncidentEvent] = []
        for alert in raw_alerts:
            if not isinstance(alert, Mapping) or alert.get("status") != "firing":
                continue
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            if not isinstance(labels, Mapping) or not isinstance(annotations, Mapping):
                raise ValueError("Alert labels and annotations must be objects")

            fingerprint = str(alert.get("fingerprint", ""))
            if not fingerprint:
                raise ValueError("Alert fingerprint is required")
            service = str(labels.get("service") or labels.get("job") or "unknown-service")
            alert_name = str(labels.get("alertname", "unknown-alert"))
            generator_url = str(alert.get("generatorURL", ""))

            started_at = datetime.fromisoformat(
                str(alert["startsAt"]).replace("Z", "+00:00")
            )
            incidents.append(
                IncidentEvent(
                    source=IncidentSource.ALERTMANAGER,
                    kind=IncidentKind.RUNTIME_ALERT,
                    external_id=fingerprint,
                    service=service,
                    title=str(annotations.get("summary") or alert_name),
                    severity=str(labels.get("severity", "unknown")),
                    started_at=started_at,
                    correlation_id=(
                        f"alertmanager:{fingerprint}:{started_at.isoformat()}"
                    ),
                    evidence_refs=(generator_url,) if generator_url else (),
                    metadata={
                        "alertname": alert_name,
                        "labels": dict(labels),
                        "description": annotations.get("description"),
                        "group_key": payload.get("groupKey"),
                        "allowed_actions": list(self._allowed_actions),
                    },
                )
            )

        return incidents
