from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="INVESTIGATOR_",
        extra="ignore",
    )

    mode: Literal["demo", "fixture", "connected"] = "demo"
    data_dir: Path = Path("data")
    github_webhook_secret: str = Field(min_length=8)
    gitlab_webhook_token: str = Field(min_length=8)
    alertmanager_webhook_token: str = Field(min_length=8)
    admin_api_token: SecretStr = Field(min_length=16)
    worker_poll_seconds: float = Field(default=0.5, gt=0)
    operator_evidence_max_bytes: int = Field(default=1_000_000, ge=1024, le=10_000_000)
    github_api_token: SecretStr | None = None
    github_api_url: str = "https://api.github.com"
    gitlab_api_token: SecretStr | None = None
    gitlab_api_url: str = "https://gitlab.com/api/v4"
    prometheus_url: str | None = None
    prometheus_query_templates: dict[str, str] = Field(
        default_factory=lambda: {"target_health": "up{{job={service}}}"}
    )
    runtime_diagnostics_url: str | None = None
    runtime_control_token: SecretStr | None = None
    runtime_action_enabled: bool = False
    runtime_allowed_service: str = "runtime-demo"
    runtime_recovery_timeout_seconds: float = Field(default=45, gt=0, le=120)
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.4-mini"
    output_language: str = "ru"
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    telegram_language: str = "ru"
    dashboard_url: str | None = "http://127.0.0.1:8501"
    remediation_enabled: bool = False
    remediation_sandbox_image: str = "python:3.12-slim"
    remediation_check_profiles: dict[str, list[list[str]]] = Field(
        default_factory=lambda: {
            "python": [
                ["python", "-m", "pytest", "-q"],
                ["python", "-m", "ruff", "check", "."],
            ]
        }
    )

    @property
    def incidents_database_path(self) -> Path:
        return self.data_dir / "incidents.db"

    @property
    def checkpoints_database_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def remediation_workspace_path(self) -> Path:
        return self.data_dir / "remediations"

    @property
    def operator_evidence_path(self) -> Path:
        return self.data_dir / "operator-evidence"
