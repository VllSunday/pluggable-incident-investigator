from __future__ import annotations

import pytest

from incident_investigator.settings import (
    Settings,
    configure_langsmith_environment,
)


def _required_environment(monkeypatch) -> None:
    monkeypatch.setenv("INVESTIGATOR_GITHUB_WEBHOOK_SECRET", "github-secret")
    monkeypatch.setenv("INVESTIGATOR_GITLAB_WEBHOOK_TOKEN", "gitlab-token")
    monkeypatch.setenv("INVESTIGATOR_ALERTMANAGER_WEBHOOK_TOKEN", "alertmanager-token")
    monkeypatch.setenv(
        "INVESTIGATOR_ADMIN_API_TOKEN", "admin-token-at-least-16-characters"
    )


def test_langsmith_settings_from_dotenv_names_are_exported(monkeypatch) -> None:
    _required_environment(monkeypatch)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "incident-test-project")

    settings = Settings(_env_file=None)
    configure_langsmith_environment(settings)

    assert settings.langsmith_tracing is True
    assert settings.langsmith_project == "incident-test-project"
    assert settings.langsmith_api_key is not None
    assert settings.langsmith_api_key.get_secret_value() == "test-langsmith-key"


def test_langsmith_tracing_fails_fast_without_api_key(monkeypatch) -> None:
    _required_environment(monkeypatch)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    settings = Settings(_env_file=None)

    with pytest.raises(RuntimeError, match="LANGSMITH_API_KEY"):
        configure_langsmith_environment(settings)
