from __future__ import annotations

import hmac
import json
from collections.abc import Sequence
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status

from incident_investigator.adapters.events import (
    AlertmanagerEventAdapter,
    GitHubActionsEventAdapter,
    GitLabCIEventAdapter,
)
from incident_investigator.adapters.events.alertmanager import InvalidWebhookToken
from incident_investigator.adapters.events.github import InvalidWebhookSignature
from incident_investigator.adapters.events.gitlab import InvalidGitLabWebhookToken
from incident_investigator.application import IncidentRecord
from incident_investigator.application.operator_input import OperatorEvidenceSubmission
from incident_investigator.application.service import (
    IncidentNotFoundError,
    InvalidIncidentStateError,
)
from incident_investigator.domain import IncidentEvent


class IncidentSink(Protocol):
    async def accept(self, incident: IncidentEvent) -> None: ...


class IncidentControlPlane(Protocol):
    async def list_incidents(self, limit: int = 100) -> Sequence[IncidentRecord]: ...

    async def get_incident(self, incident_id: UUID | str) -> IncidentRecord: ...

    async def decide_approval(
        self, incident_id: UUID | str, *, approved: bool
    ) -> IncidentRecord: ...

    async def submit_evidence(
        self, incident_id: UUID | str, submission: OperatorEvidenceSubmission
    ) -> IncidentRecord: ...

    async def decline_information_request(
        self, incident_id: UUID | str
    ) -> IncidentRecord: ...


def create_app(
    *,
    github_adapter: GitHubActionsEventAdapter,
    gitlab_adapter: GitLabCIEventAdapter,
    alertmanager_adapter: AlertmanagerEventAdapter,
    incident_sink: IncidentSink,
    control_plane: IncidentControlPlane | None = None,
    admin_api_token: str,
    operator_evidence_max_bytes: int = 1_000_000,
    lifespan: Any = None,
) -> FastAPI:
    if len(admin_api_token) < 16:
        raise ValueError("Admin API token must contain at least 16 characters")
    app = FastAPI(
        title="Incident Investigator API",
        version="0.1.0",
        lifespan=lifespan,
    )

    async def ingest(request: Request, adapter) -> dict[str, object]:
        body = await request.body()
        try:
            adapter.verify(body, request.headers)
        except (
            InvalidWebhookSignature,
            InvalidGitLabWebhookToken,
            InvalidWebhookToken,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)
            ) from error

        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("Webhook body must be a JSON object")
            incidents = adapter.normalize(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error

        for incident in incidents:
            await incident_sink.accept(incident)

        return {
            "accepted": len(incidents),
            "incident_ids": [str(item.incident_id) for item in incidents],
        }

    def verify_admin(request: Request) -> None:
        authorization = request.headers.get("authorization", "")
        supplied = (
            authorization.removeprefix("Bearer ")
            if authorization.startswith("Bearer ")
            else ""
        )
        if not hmac.compare_digest(supplied, admin_api_token):
            raise HTTPException(status_code=401, detail="Invalid admin API token")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
    async def github_webhook(request: Request) -> dict[str, object]:
        return await ingest(request, github_adapter)

    @app.post("/webhooks/alertmanager", status_code=status.HTTP_202_ACCEPTED)
    async def alertmanager_webhook(request: Request) -> dict[str, object]:
        return await ingest(request, alertmanager_adapter)

    @app.post("/webhooks/gitlab", status_code=status.HTTP_202_ACCEPTED)
    async def gitlab_webhook(request: Request) -> dict[str, object]:
        return await ingest(request, gitlab_adapter)

    if control_plane is not None:

        @app.get("/api/incidents")
        async def list_incidents(
            request: Request, limit: int = 100
        ) -> list[dict[str, object]]:
            verify_admin(request)
            records = await control_plane.list_incidents(min(max(limit, 1), 500))
            return [record.model_dump(mode="json") for record in records]

        @app.get("/api/incidents/{incident_id}")
        async def get_incident(
            incident_id: UUID, request: Request
        ) -> dict[str, object]:
            verify_admin(request)
            try:
                record = await control_plane.get_incident(incident_id)
            except IncidentNotFoundError as error:
                raise HTTPException(status_code=404, detail="Incident not found") from error
            return record.model_dump(mode="json")

        @app.post("/api/incidents/{incident_id}/approval")
        async def decide_approval(
            incident_id: UUID, request: Request, decision: dict[str, bool]
        ) -> dict[str, object]:
            verify_admin(request)
            if "approved" not in decision:
                raise HTTPException(status_code=422, detail="'approved' is required")
            try:
                record = await control_plane.decide_approval(
                    incident_id, approved=decision["approved"]
                )
            except IncidentNotFoundError as error:
                raise HTTPException(status_code=404, detail="Incident not found") from error
            except InvalidIncidentStateError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            return record.model_dump(mode="json")

        @app.post("/api/incidents/{incident_id}/evidence")
        async def submit_text_evidence(
            incident_id: UUID,
            request: Request,
            submission: OperatorEvidenceSubmission,
        ) -> dict[str, object]:
            verify_admin(request)
            try:
                record = await control_plane.submit_evidence(
                    incident_id, submission
                )
            except IncidentNotFoundError as error:
                raise HTTPException(status_code=404, detail="Incident not found") from error
            except InvalidIncidentStateError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            return record.model_dump(mode="json")

        @app.post("/api/incidents/{incident_id}/evidence/file")
        async def submit_file_evidence(
            incident_id: UUID,
            request: Request,
            request_id: Annotated[UUID, Form()],
            file: Annotated[UploadFile, File()],
        ) -> dict[str, object]:
            verify_admin(request)
            filename = file.filename or "operator-evidence.txt"
            suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if suffix not in {"txt", "log", "json", "yaml", "yml"}:
                raise HTTPException(
                    status_code=415,
                    detail="Only .txt, .log, .json, .yaml and .yml files are accepted",
                )
            content = await file.read(operator_evidence_max_bytes + 1)
            if len(content) > operator_evidence_max_bytes:
                raise HTTPException(status_code=413, detail="Evidence file is too large")
            if b"\x00" in content:
                raise HTTPException(status_code=415, detail="Binary files are not accepted")
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise HTTPException(
                    status_code=415, detail="Evidence file must use UTF-8 encoding"
                ) from error
            try:
                record = await control_plane.submit_evidence(
                    incident_id,
                    OperatorEvidenceSubmission(
                        request_id=request_id,
                        text=text,
                        source_name=filename,
                        media_type=file.content_type or "text/plain",
                    ),
                )
            except IncidentNotFoundError as error:
                raise HTTPException(status_code=404, detail="Incident not found") from error
            except InvalidIncidentStateError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            return record.model_dump(mode="json")

        @app.post("/api/incidents/{incident_id}/evidence/decline")
        async def decline_evidence_request(
            incident_id: UUID, request: Request
        ) -> dict[str, object]:
            verify_admin(request)
            try:
                record = await control_plane.decline_information_request(incident_id)
            except IncidentNotFoundError as error:
                raise HTTPException(status_code=404, detail="Incident not found") from error
            except InvalidIncidentStateError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            return record.model_dump(mode="json")

    return app
