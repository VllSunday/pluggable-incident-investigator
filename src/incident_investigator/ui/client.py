from __future__ import annotations

from contextlib import suppress
from typing import Any

import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INVESTIGATOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_url: str = "http://127.0.0.1:8000"
    admin_api_token: SecretStr = SecretStr("")


class DashboardAPIError(RuntimeError):
    """A safe, user-facing control-plane API failure."""


class IncidentAPIClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 70) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> IncidentAPIClient:
        settings = DashboardSettings()
        return cls(
            settings.api_url,
            settings.admin_api_token.get_secret_value(),
        )

    @property
    def configured(self) -> bool:
        return len(self.token) >= 16

    def list_incidents(self, limit: int = 100) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/incidents", params={"limit": limit})
        if not isinstance(payload, list):
            raise DashboardAPIError("The API returned an invalid incident list.")
        return payload

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/incidents/{incident_id}")
        if not isinstance(payload, dict):
            raise DashboardAPIError("The API returned an invalid incident record.")
        return payload

    def decide_approval(self, incident_id: str, *, approved: bool) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/api/incidents/{incident_id}/approval",
            json={"approved": approved},
        )
        if not isinstance(payload, dict):
            raise DashboardAPIError("The API returned an invalid approval result.")
        return payload

    def submit_text_evidence(
        self,
        incident_id: str,
        *,
        request_id: str,
        text: str,
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/api/incidents/{incident_id}/evidence",
            json={"request_id": request_id, "text": text},
        )
        if not isinstance(payload, dict):
            raise DashboardAPIError("The API returned an invalid evidence result.")
        return payload

    def submit_file_evidence(
        self,
        incident_id: str,
        *,
        request_id: str,
        filename: str,
        content: bytes,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/api/incidents/{incident_id}/evidence/file",
            data={"request_id": request_id},
            files={
                "file": (
                    filename,
                    content,
                    media_type or "text/plain",
                )
            },
        )
        if not isinstance(payload, dict):
            raise DashboardAPIError("The API returned an invalid evidence result.")
        return payload

    def decline_information_request(self, incident_id: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/api/incidents/{incident_id}/evidence/decline",
        )
        if not isinstance(payload, dict):
            raise DashboardAPIError("The API returned an invalid decline result.")
        return payload

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=self.timeout)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as error:
            raise DashboardAPIError("The control plane did not respond in time.") from error
        except httpx.HTTPStatusError as error:
            detail = ""
            with suppress(ValueError, AttributeError):
                detail = str(error.response.json().get("detail", ""))
            message = detail or f"Control plane returned HTTP {error.response.status_code}."
            raise DashboardAPIError(message) from error
        except (httpx.HTTPError, ValueError) as error:
            raise DashboardAPIError("Cannot reach the Incident Investigator API.") from error
