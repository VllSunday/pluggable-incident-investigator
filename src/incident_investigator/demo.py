from __future__ import annotations

from incident_investigator.domain import (
    EvidenceItem,
    Hypothesis,
    IncidentEvent,
    ReflectionDecision,
    ReflectionOutcome,
)


class MetadataEvidenceProvider:
    """Safe startup provider; real providers replace this in connected mode."""

    name = "event_metadata"
    capabilities = frozenset({"event_metadata"})
    sources = None

    async def collect(self, incident: IncidentEvent, request: str):
        return [
            EvidenceItem(
                kind="event_metadata",
                source_uri=f"incident://{incident.incident_id}",
                summary=f"{request}: {incident.title}",
                attributes={
                    "source": incident.source.value,
                    "service": incident.service,
                    "metadata": incident.metadata,
                },
            )
        ]


class DemoInvestigationEngine:
    """Deterministic engine used only to validate installation and data flow."""

    async def generate_hypotheses(self, incident: IncidentEvent, evidence):
        del incident
        return [
            Hypothesis(
                statement="External diagnostic providers are required to establish root cause",
                confidence=0.1,
                supporting_evidence_ids=[item.evidence_id for item in evidence],
                required_checks=["configure source-specific evidence providers"],
            )
        ]

    async def reflect(self, incident: IncidentEvent, evidence, hypotheses):
        del incident, evidence, hypotheses
        return ReflectionDecision(
            outcome=ReflectionOutcome.ESCALATE,
            critique=(
                "Demo mode validates ingestion and orchestration but does not infer root cause"
            ),
        )

    async def propose_action(self, incident: IncidentEvent, evidence, hypotheses):
        del incident, evidence, hypotheses
        return None


class NoopRecoveryVerifier:
    async def verify(self, incident, action_result):
        del incident, action_result
        return False, "No recovery verifier is configured in demo mode"
