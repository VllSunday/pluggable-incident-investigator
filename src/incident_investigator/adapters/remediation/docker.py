from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from incident_investigator.core.remediation import (
    CheckResult,
    RemediationBlockedError,
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s]+"),
    re.compile(r"(?i)((?:token|password|secret|api[_-]?key)\s*[:=]\s*)[^\s]+"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
)


class DockerSandboxRunner:
    def __init__(
        self,
        profiles: Mapping[str, Sequence[Sequence[str]]],
        *,
        image: str,
        timeout_seconds: float = 180,
        max_output_characters: int = 12_000,
    ) -> None:
        self._profiles = {
            name: tuple(tuple(argument for argument in command) for command in commands)
            for name, commands in profiles.items()
        }
        self._image = image
        self._timeout_seconds = timeout_seconds
        self._max_output_characters = max_output_characters

    async def run_profile(self, profile: str, workspace: Path) -> Sequence[CheckResult]:
        commands = self._profiles.get(profile)
        if commands is None:
            raise RemediationBlockedError(f"Unknown sandbox check profile '{profile}'")
        results: list[CheckResult] = []
        for command in commands:
            result = await self._run(command, workspace)
            results.append(result)
            if result.exit_code != 0 or result.timed_out:
                break
        return results

    async def _run(self, command: tuple[str, ...], workspace: Path) -> CheckResult:
        docker_command = (
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", "128", "--memory", "768m", "--cpus", "1.0",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=128m",
            "--mount", f"type=bind,src={workspace.resolve()},dst=/workspace",
            "--workdir", "/workspace", self._image, *command,
        )
        process = await asyncio.create_subprocess_exec(
            *docker_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        timed_out = False
        try:
            output, _ = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout_seconds
            )
        except TimeoutError:
            timed_out = True
            process.kill()
            output, _ = await process.communicate()
        rendered = _redact(output.decode(errors="replace"))
        return CheckResult(
            command=command,
            exit_code=process.returncode if process.returncode is not None else -1,
            output=rendered[-self._max_output_characters :],
            timed_out=timed_out,
        )


def _redact(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]" if pattern.groups else "[REDACTED]", redacted)
    return redacted
