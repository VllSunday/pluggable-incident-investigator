from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from incident_investigator.adapters.remediation import DockerSandboxRunner


class FakeProcess:
    returncode = 0

    async def communicate(self):
        return b"API_KEY=super-secret-value\n1 passed", b""

    def kill(self) -> None:
        self.returncode = -9


@pytest.mark.asyncio
async def test_docker_sandbox_uses_hardening_flags_and_redacts_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: tuple[str, ...] = ()

    async def fake_subprocess(*arguments, **kwargs):
        nonlocal captured
        del kwargs
        captured = arguments
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    runner = DockerSandboxRunner(
        {"python": [["python", "-m", "pytest", "-q"]]},
        image="project-ci@sha256:trusted",
    )

    results = await runner.run_profile("python", tmp_path)

    assert "none" in captured
    assert "--read-only" in captured
    assert "ALL" in captured
    assert "no-new-privileges:true" in captured
    assert "super-secret-value" not in results[0].output
    assert "[REDACTED]" in results[0].output
