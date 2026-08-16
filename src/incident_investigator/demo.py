from __future__ import annotations

from incident_investigator.domain import (
    ActionProposal,
    EvidenceItem,
    Hypothesis,
    IncidentEvent,
    ReflectionDecision,
    ReflectionOutcome,
    RiskLevel,
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


class RuntimeFixtureInvestigationEngine:
    """Deterministic reasoning for the bundled runtime smoke test only."""

    async def generate_hypotheses(self, incident: IncidentEvent, evidence):
        supporting = [
            item.evidence_id
            for item in evidence
            if item.kind in {"application_log", "metric_snapshot"}
        ]
        kinds = {item.kind for item in evidence}
        verified = {"application_log", "metric_snapshot"}.issubset(kinds)
        return [
            Hypothesis(
                statement=(
                    "The active runtime override forces an unsafe error fraction, "
                    "causing the observed 5xx alert."
                ),
                confidence=0.99 if verified else 0.55,
                supporting_evidence_ids=supporting,
                required_checks=(
                    []
                    if verified
                    else ["Collect both application logs and Prometheus metrics."]
                ),
                verified=verified,
            )
        ]

    async def reflect(self, incident: IncidentEvent, evidence, hypotheses):
        del incident, evidence
        if any(item.verified for item in hypotheses):
            return ReflectionDecision(
                outcome=ReflectionOutcome.READY_FOR_ACTION,
                critique=(
                    "Application logs identify the runtime override and Prometheus "
                    "independently confirms the elevated error ratio."
                ),
            )
        return ReflectionDecision(
            outcome=ReflectionOutcome.GATHER_MORE,
            critique="The fixture requires independent log and metric evidence.",
            additional_evidence_requests=(
                "Collect application logs and Prometheus metrics for the incident window.",
            ),
        )

    async def propose_action(self, incident: IncidentEvent, evidence, hypotheses):
        del evidence
        if not any(item.verified for item in hypotheses):
            return None
        if "rollback_runtime_config" not in incident.metadata.get(
            "allowed_actions", []
        ):
            return None
        return ActionProposal(
            tool_name="rollback_runtime_config",
            description="Restore the bundled runtime fixture to its safe configuration.",
            arguments={
                "service": incident.service,
                "target_error_fraction": 0.0,
                "reason": "Logs and metrics confirm the unsafe runtime override.",
            },
            risk=RiskLevel.HIGH,
            idempotency_key=f"{incident.incident_id}:fixture-rollback",
            rollback_plan="Restore the previous synthetic error fraction.",
            expected_outcome="The service becomes healthy and the alert resolves.",
        )


class NoopRecoveryVerifier:
    async def verify(self, incident, action_result):
        del incident, action_result
        return False, "No recovery verifier is configured in demo mode"
