from __future__ import annotations

import json

import httpx

from incident_investigator.domain import EvidenceItem, IncidentEvent, IncidentSource


class PrometheusEvidenceProvider:
    name = "prometheus"
    capabilities = frozenset({"metrics", "service_health"})
    sources = frozenset({IncidentSource.ALERTMANAGER})

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        query_templates: dict[str, str] | None = None,
    ) -> None:
        self._client = client
        self._query_templates = query_templates or {
            "target_health": "up{{job={service}}}",
        }

    async def collect(self, incident: IncidentEvent, request: str):
        del request
        if incident.source is not IncidentSource.ALERTMANAGER:
            return []

        service_literal = json.dumps(incident.service)
        evidence: list[EvidenceItem] = []
        for name, template in self._query_templates.items():
            query = template.format(service=service_literal)
            response = await self._client.get(
                "/api/v1/query", params={"query": query, "timeout": "10s"}
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "success":
                raise RuntimeError(
                    f"Prometheus query failed: {payload.get('error', 'unknown error')}"
                )
            data = payload.get("data", {})
            evidence.append(
                EvidenceItem(
                    kind="metric_snapshot",
                    source_uri=f"prometheus://query/{name}",
                    summary=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    attributes={
                        "provider": "prometheus",
                        "query_name": name,
                        "query": query,
                        "warnings": payload.get("warnings", []),
                    },
                )
            )
        return evidence
