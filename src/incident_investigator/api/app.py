from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from incident_investigator.adapters.events import (
    AlertmanagerEventAdapter,
    GitHubActionsEventAdapter,
    GitLabCIEventAdapter,
)
from incident_investigator.adapters.evidence import (
    GitHubCIEvidenceProvider,
    GitLabCIEvidenceProvider,
    PrometheusEvidenceProvider,
)
from incident_investigator.adapters.notifications import TelegramNotificationSink
from incident_investigator.adapters.remediation import DockerSandboxRunner
from incident_investigator.adapters.runtime_demo import (
    RuntimeConfigRollbackExecutor,
    RuntimeLogEvidenceProvider,
    RuntimeRecoveryVerifier,
)
from incident_investigator.adapters.scm import (
    GitHubSourceControlProvider,
    GitLabSourceControlProvider,
)
from incident_investigator.api.factory import create_app
from incident_investigator.application import InvestigationService
from incident_investigator.application.notifications import BestEffortNotifier
from incident_investigator.application.operator_input import OperatorEvidenceStore
from incident_investigator.application.repository import SqliteIncidentRepository
from incident_investigator.core.graph import GraphServices, build_investigation_graph
from incident_investigator.core.policy import ActionPolicy
from incident_investigator.core.remediation import RemediationPipeline
from incident_investigator.core.runtime import SafeActionRunner
from incident_investigator.demo import (
    DemoInvestigationEngine,
    MetadataEvidenceProvider,
    NoopRecoveryVerifier,
    RuntimeFixtureInvestigationEngine,
)
from incident_investigator.domain import IncidentEvent
from incident_investigator.engines import (
    OpenAIInvestigationEngine,
    OpenAIPatchRepairer,
    OpenAIRemediationReviewer,
)
from incident_investigator.settings import Settings, configure_langsmith_environment


class DeferredService:
    def __init__(self) -> None:
        self.service: InvestigationService | None = None

    def bind(self, service: InvestigationService) -> None:
        self.service = service

    def unbind(self) -> None:
        self.service = None

    def _get(self) -> InvestigationService:
        if self.service is None:
            raise RuntimeError("Application service is not ready")
        return self.service

    async def accept(self, incident: IncidentEvent) -> None:
        await self._get().accept(incident)

    async def list_incidents(self, limit: int = 100):
        return await self._get().list_incidents(limit)

    async def get_incident(self, incident_id):
        return await self._get().get_incident(incident_id)

    async def decide_approval(self, incident_id, *, approved: bool):
        return await self._get().decide_approval(incident_id, approved=approved)

    async def submit_evidence(self, incident_id, submission):
        return await self._get().submit_evidence(incident_id, submission)

    async def decline_information_request(self, incident_id):
        return await self._get().decline_information_request(incident_id)


settings = Settings()
configure_langsmith_environment(settings)
deferred_service = DeferredService()


@asynccontextmanager
async def lifespan(app):
    del app
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    async with AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(str(settings.checkpoints_database_path))
        )
        evidence_providers = [MetadataEvidenceProvider()]
        action_executors = {}
        recovery_verifier = NoopRecoveryVerifier()
        remediation_providers = {}
        if settings.github_api_token is not None:
            github_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=settings.github_api_url,
                    follow_redirects=True,
                    timeout=20,
                    headers={
                        "Authorization": (
                            f"Bearer {settings.github_api_token.get_secret_value()}"
                        ),
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2026-03-10",
                    },
                )
            )
            evidence_providers.append(GitHubCIEvidenceProvider(github_client))
            remediation_providers["github_actions"] = GitHubSourceControlProvider(
                github_client
            )
        if settings.gitlab_api_token is not None:
            gitlab_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=settings.gitlab_api_url,
                    timeout=20,
                    headers={
                        "PRIVATE-TOKEN": settings.gitlab_api_token.get_secret_value()
                    },
                )
            )
            evidence_providers.append(GitLabCIEvidenceProvider(gitlab_client))
            remediation_providers["gitlab_ci"] = GitLabSourceControlProvider(
                gitlab_client
            )
        if settings.prometheus_url is not None:
            prometheus_client = await stack.enter_async_context(
                httpx.AsyncClient(base_url=settings.prometheus_url, timeout=15)
            )
            evidence_providers.append(
                PrometheusEvidenceProvider(
                    prometheus_client,
                    query_templates=settings.prometheus_query_templates,
                )
            )
            if settings.runtime_diagnostics_url is not None:
                runtime_headers = {}
                if settings.runtime_control_token is not None:
                    runtime_headers["Authorization"] = (
                        f"Bearer {settings.runtime_control_token.get_secret_value()}"
                    )
                runtime_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        base_url=settings.runtime_diagnostics_url,
                        headers=runtime_headers,
                        timeout=15,
                    )
                )
                evidence_providers.append(RuntimeLogEvidenceProvider(runtime_client))
                if settings.runtime_action_enabled:
                    if settings.runtime_control_token is None:
                        raise RuntimeError(
                            "Runtime actions require INVESTIGATOR_RUNTIME_CONTROL_TOKEN"
                        )
                    executor = RuntimeConfigRollbackExecutor(
                        runtime_client,
                        allowed_service=settings.runtime_allowed_service,
                    )
                    action_executors[executor.name] = executor
                    recovery_verifier = RuntimeRecoveryVerifier(
                        runtime_client,
                        prometheus_client,
                        timeout_seconds=settings.runtime_recovery_timeout_seconds,
                    )
        notification_sinks = []
        if settings.telegram_bot_token and settings.telegram_chat_id:
            telegram_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    base_url=(
                        "https://api.telegram.org/bot"
                        f"{settings.telegram_bot_token.get_secret_value()}"
                    ),
                    timeout=10,
                )
            )
            notification_sinks.append(
                TelegramNotificationSink(
                    telegram_client,
                    chat_id=settings.telegram_chat_id,
                    dashboard_url=settings.dashboard_url,
                    language=settings.telegram_language,
                )
            )

        if settings.mode == "connected":
            if settings.openai_api_key is None:
                raise RuntimeError(
                    "INVESTIGATOR_OPENAI_API_KEY is required in connected mode"
                )
            llm_client = wrap_openai(
                AsyncOpenAI(
                    api_key=settings.openai_api_key.get_secret_value(),
                    timeout=45,
                    max_retries=2,
                )
            )
            engine = OpenAIInvestigationEngine(
                llm_client,
                model=settings.openai_model,
                output_language=settings.output_language,
            )
            remediation_reviewer = OpenAIRemediationReviewer(
                llm_client, model=settings.openai_model
            )
            remediation_repairer = OpenAIPatchRepairer(
                llm_client, model=settings.openai_model
            )
        elif settings.mode == "fixture":
            engine = RuntimeFixtureInvestigationEngine()
            remediation_reviewer = None
            remediation_repairer = None
        else:
            engine = DemoInvestigationEngine()
            remediation_reviewer = None
            remediation_repairer = None

        remediation_pipeline = None
        if settings.remediation_enabled:
            if remediation_reviewer is None:
                raise RuntimeError("Remediation requires connected mode")
            if not remediation_providers:
                raise RuntimeError("Remediation requires a GitHub or GitLab API token")
            remediation_pipeline = RemediationPipeline(
                remediation_providers,
                DockerSandboxRunner(
                    settings.remediation_check_profiles,
                    image=settings.remediation_sandbox_image,
                ),
                remediation_reviewer,
                settings.remediation_workspace_path,
                repairer=remediation_repairer,
            )

        graph = build_investigation_graph(
            GraphServices(
                evidence_providers=tuple(evidence_providers),
                engine=engine,
                policy=ActionPolicy(
                    always_require_approval_tools=frozenset(
                        {"prepare_draft_change", "rollback_runtime_config"}
                    )
                ),
                action_runner=SafeActionRunner(action_executors),
                recovery_verifier=recovery_verifier,
                remediation_pipeline=remediation_pipeline,
            ),
            checkpointer=checkpointer,
        )
        service = InvestigationService(
            SqliteIncidentRepository(settings.incidents_database_path),
            graph,
            poll_interval_seconds=settings.worker_poll_seconds,
            notifier=BestEffortNotifier(notification_sinks),
            operator_evidence_store=OperatorEvidenceStore(
                settings.operator_evidence_path
            ),
        )
        deferred_service.bind(service)
        await service.start()
        try:
            yield
        finally:
            await service.stop()
            deferred_service.unbind()


remediation_profiles = (
    tuple(settings.remediation_check_profiles) if settings.remediation_enabled else ()
)

app = create_app(
    github_adapter=GitHubActionsEventAdapter(
        settings.github_webhook_secret,
        remediation_profiles=remediation_profiles,
    ),
    gitlab_adapter=GitLabCIEventAdapter(
        settings.gitlab_webhook_token,
        remediation_profiles=remediation_profiles,
    ),
    alertmanager_adapter=AlertmanagerEventAdapter(
        settings.alertmanager_webhook_token,
        allowed_actions=(
            ("rollback_runtime_config",) if settings.runtime_action_enabled else ()
        ),
    ),
    incident_sink=deferred_service,
    control_plane=deferred_service,
    admin_api_token=settings.admin_api_token.get_secret_value(),
    operator_evidence_max_bytes=settings.operator_evidence_max_bytes,
    lifespan=lifespan,
)
