from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import quote

import httpx

from incident_investigator.domain import EvidenceItem, IncidentEvent, IncidentSource

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s]+"),
    re.compile(r"(?i)((?:token|password|secret|api[_-]?key)\s*[:=]\s*)[^\s]+"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
)


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _excerpt(value: str, max_characters: int) -> str:
    cleaned = redact_sensitive_text(value)
    if len(cleaned) <= max_characters:
        return cleaned
    half = max_characters // 2
    return f"{cleaned[:half]}\n... [TRUNCATED] ...\n{cleaned[-half:]}"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode(errors="replace")).hexdigest()


class GitHubCIEvidenceProvider:
    name = "github_ci"
    capabilities = frozenset({"ci_jobs", "ci_logs", "commit_diff"})
    sources = frozenset({IncidentSource.GITHUB_ACTIONS})

    def __init__(self, client: httpx.AsyncClient, *, max_log_characters: int = 12_000) -> None:
        self._client = client
        self._max_log_characters = max_log_characters

    async def collect(self, incident: IncidentEvent, request: str):
        del request
        if incident.source is not IncidentSource.GITHUB_ACTIONS:
            return []

        run_id = incident.external_id
        repository = incident.service
        response = await self._client.get(f"/repos/{repository}/actions/runs/{run_id}/jobs")
        response.raise_for_status()
        jobs = response.json().get("jobs", [])
        evidence: list[EvidenceItem] = []
        for job in jobs:
            if job.get("conclusion") not in {"failure", "timed_out", "cancelled"}:
                continue
            job_id = str(job["id"])
            log_response = await self._client.get(
                f"/repos/{repository}/actions/jobs/{job_id}/logs"
            )
            log_response.raise_for_status()
            raw_log = log_response.text
            evidence.append(
                EvidenceItem(
                    kind="ci_job_log",
                    source_uri=str(job.get("html_url") or f"github://job/{job_id}"),
                    summary=_excerpt(raw_log, self._max_log_characters),
                    content_hash=_hash(raw_log),
                    attributes={
                        "platform": "github",
                        "job_id": job_id,
                        "job_name": job.get("name"),
                        "conclusion": job.get("conclusion"),
                    },
                )
            )

        sha = incident.metadata.get("head_sha")
        if sha:
            commit_response = await self._client.get(f"/repos/{repository}/commits/{sha}")
            commit_response.raise_for_status()
            commit = commit_response.json()
            patches = "\n\n".join(
                f"--- {item.get('filename')}\n{item.get('patch', '[binary or unavailable]')}"
                for item in commit.get("files", [])
            )
            evidence.append(
                EvidenceItem(
                    kind="commit_diff",
                    source_uri=str(commit.get("html_url") or f"github://commit/{sha}"),
                    summary=_excerpt(patches, self._max_log_characters),
                    content_hash=_hash(patches),
                    attributes={"platform": "github", "sha": sha},
                )
            )
        return evidence


class GitLabCIEvidenceProvider:
    name = "gitlab_ci"
    capabilities = frozenset({"ci_jobs", "ci_logs", "commit_diff"})
    sources = frozenset({IncidentSource.GITLAB_CI})

    def __init__(self, client: httpx.AsyncClient, *, max_log_characters: int = 12_000) -> None:
        self._client = client
        self._max_log_characters = max_log_characters

    async def collect(self, incident: IncidentEvent, request: str):
        del request
        if incident.source is not IncidentSource.GITLAB_CI:
            return []

        project = quote(incident.service, safe="")
        pipeline_id = incident.external_id
        response = await self._client.get(
            f"/projects/{project}/pipelines/{pipeline_id}/jobs",
            params={"scope": "failed", "include_retried": "true"},
        )
        response.raise_for_status()
        evidence: list[EvidenceItem] = []
        for job in response.json():
            job_id = str(job["id"])
            trace_response = await self._client.get(f"/projects/{project}/jobs/{job_id}/trace")
            trace_response.raise_for_status()
            raw_log = trace_response.text
            evidence.append(
                EvidenceItem(
                    kind="ci_job_log",
                    source_uri=str(job.get("web_url") or f"gitlab://job/{job_id}"),
                    summary=_excerpt(raw_log, self._max_log_characters),
                    content_hash=_hash(raw_log),
                    attributes={
                        "platform": "gitlab",
                        "job_id": job_id,
                        "job_name": job.get("name"),
                        "status": job.get("status"),
                    },
                )
            )

        sha = incident.metadata.get("sha")
        if sha:
            diff_response = await self._client.get(
                f"/projects/{project}/repository/commits/{sha}/diff"
            )
            diff_response.raise_for_status()
            diffs: list[dict[str, Any]] = diff_response.json()
            patches = "\n\n".join(
                f"--- {item.get('new_path')}\n{item.get('diff', '[unavailable]')}" for item in diffs
            )
            evidence.append(
                EvidenceItem(
                    kind="commit_diff",
                    source_uri=f"gitlab://{incident.service}/commit/{sha}",
                    summary=_excerpt(patches, self._max_log_characters),
                    content_hash=_hash(patches),
                    attributes={"platform": "gitlab", "sha": sha},
                )
            )
        return evidence
