from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from incident_investigator.core.scm import (
    FileChange,
    PreparedChangeSpec,
    SourceControlProvider,
)
from incident_investigator.domain import ActionProposal, ActionResult, IncidentEvent


class RemediationBlockedError(RuntimeError):
    pass


class RemediationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    target_branch: str = Field(min_length=1)
    branch_name: str = Field(pattern=r"^incident-fix/[a-zA-Z0-9._-]+$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=10_000)
    unified_diff: str = Field(min_length=1, max_length=100_000)
    check_profile: str = Field(min_length=1)


class RemediationRequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repository: str
    source_revision: str
    target_branch: str
    branch_name: str
    title: str
    description: str
    check_profile: str


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: tuple[str, ...]
    exit_code: int
    output: str
    timed_out: bool = False


class RemediationReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approved: bool
    summary: str = Field(min_length=1)
    risks: tuple[str, ...] = ()


class RemediationFileSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    operation: str
    content_sha256: str
    previous_exists: bool


class RemediationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request: RemediationRequestSummary
    changes: tuple[RemediationFileSummary, ...]
    checks: tuple[CheckResult, ...]
    review: RemediationReview
    patch_sha256: str


class RemediationReviewer(Protocol):
    async def review(
        self,
        incident: IncidentEvent,
        request: RemediationRequest,
        changes: Sequence[FileChange],
        checks: Sequence[CheckResult],
    ) -> RemediationReview: ...


class SandboxRunner(Protocol):
    async def run_profile(self, profile: str, workspace: Path) -> Sequence[CheckResult]: ...


class RemediationPipeline:
    tool_name = "prepare_draft_change"

    def __init__(
        self,
        providers: Mapping[str, SourceControlProvider],
        sandbox: SandboxRunner,
        reviewer: RemediationReviewer,
        workspace_root: Path,
        *,
        forbidden_paths: tuple[str, ...] = (
            ".git/",
            ".env",
            ".github/workflows/",
            ".gitlab-ci.yml",
            "CODEOWNERS",
        ),
        max_changed_files: int = 12,
    ) -> None:
        self._providers = dict(providers)
        self._sandbox = sandbox
        self._reviewer = reviewer
        self._workspace_root = workspace_root
        self._forbidden_paths = forbidden_paths
        self._max_changed_files = max_changed_files

    async def stage(
        self, incident: IncidentEvent, proposal: ActionProposal
    ) -> ActionProposal:
        request = RemediationRequest.model_validate(proposal.arguments)
        self._validate_request(incident, request)
        self._validate_paths(_changed_paths(request.unified_diff))
        self._workspace_root.mkdir(parents=True, exist_ok=True)
        patch_sha256 = hashlib.sha256(request.unified_diff.encode()).hexdigest()
        patch_path = self._patch_path(incident)
        await asyncio.to_thread(
            patch_path.write_text, request.unified_diff, encoding="utf-8"
        )
        staged_arguments = {
            **_summarize_request(request).model_dump(mode="json"),
            "patch_sha256": patch_sha256,
        }
        return proposal.model_copy(update={"arguments": staged_arguments})

    async def prepare(
        self, incident: IncidentEvent, proposal: ActionProposal
    ) -> RemediationReport:
        request = await self._load_staged_request(incident, proposal)
        self._validate_request(incident, request)
        provider = self._provider(incident)
        paths = _changed_paths(request.unified_diff)
        self._validate_paths(paths)
        workspace = self._workspace_root / str(incident.incident_id)
        if workspace.exists():
            await _remove_workspace(workspace)
        try:
            await provider.materialize(
                request.repository,
                revision=request.source_revision,
                destination=workspace,
            )
        except Exception:
            await _remove_workspace(workspace)
            self._patch_path(incident).unlink(missing_ok=True)
            raise
        before = {path: _read_optional_text(workspace / path) for path in paths}
        try:
            await _apply_patch(workspace, request.unified_diff)
            changes = tuple(
                FileChange(
                    path=path,
                    content=_read_optional_text(workspace / path),
                    previous_exists=before[path] is not None,
                )
                for path in paths
            )
            if all(item.content == before[item.path] for item in changes):
                raise RemediationBlockedError("Patch produced no file changes")
            checks = tuple(await self._sandbox.run_profile(request.check_profile, workspace))
            if not checks:
                raise RemediationBlockedError("The selected check profile is empty")
            if any(item.exit_code != 0 or item.timed_out for item in checks):
                raise RemediationBlockedError("One or more sandbox checks failed")
            review = await self._reviewer.review(
                incident, request, changes, checks
            )
            if not review.approved:
                raise RemediationBlockedError(
                    f"Remediation critic rejected patch: {review.summary}"
                )
            return RemediationReport(
                request=_summarize_request(request),
                changes=tuple(_summarize_change(item) for item in changes),
                checks=checks,
                review=review,
                patch_sha256=hashlib.sha256(request.unified_diff.encode()).hexdigest(),
            )
        except Exception:
            await _remove_workspace(workspace)
            self._patch_path(incident).unlink(missing_ok=True)
            raise

    async def publish(
        self,
        incident: IncidentEvent,
        proposal: ActionProposal,
        report: RemediationReport,
    ) -> ActionResult:
        expected_arguments = {
            **report.request.model_dump(mode="json"),
            "patch_sha256": report.patch_sha256,
        }
        if proposal.arguments != expected_arguments:
            raise RemediationBlockedError("Prepared report does not match approved proposal")
        request = report.request
        provider = self._provider(incident)
        workspace = self._workspace_root / str(incident.incident_id)
        if not workspace.exists():
            raise RemediationBlockedError("Prepared remediation workspace is missing")
        changes = tuple(
            FileChange(
                path=item.path,
                content=_read_optional_text(workspace / item.path),
                previous_exists=item.previous_exists,
            )
            for item in report.changes
        )
        if tuple(_summarize_change(item) for item in changes) != report.changes:
            raise RemediationBlockedError(
                "Prepared files changed after review; approval is invalid"
            )
        result = await provider.publish_prepared_change(
            PreparedChangeSpec(
                repository=request.repository,
                source_revision=request.source_revision,
                target_branch=request.target_branch,
                branch_name=request.branch_name,
                title=request.title,
                description=_report_description(request.description, report),
                changes=changes,
            )
        )
        await _remove_workspace(self._workspace_root / str(incident.incident_id))
        self._patch_path(incident).unlink(missing_ok=True)
        return ActionResult(
            action_id=proposal.action_id,
            success=True,
            summary=f"Draft change request created: {result.url}",
            external_reference=result.url,
            details={
                "platform": result.platform.value,
                "change_request_id": result.external_id,
                "branch_name": result.branch_name,
                "patch_sha256": report.patch_sha256,
            },
        )

    async def discard(self, incident: IncidentEvent) -> None:
        await _remove_workspace(self._workspace_root / str(incident.incident_id))
        self._patch_path(incident).unlink(missing_ok=True)

    def _provider(self, incident: IncidentEvent) -> SourceControlProvider:
        try:
            return self._providers[incident.source.value]
        except KeyError as error:
            raise RemediationBlockedError(
                f"No remediation provider for '{incident.source.value}'"
            ) from error

    @staticmethod
    def _validate_request(
        incident: IncidentEvent, request: RemediationRequest
    ) -> None:
        if request.repository != incident.service:
            raise RemediationBlockedError("Remediation repository does not match incident")
        expected_revision = incident.metadata.get("head_sha") or incident.metadata.get("sha")
        if expected_revision and request.source_revision != expected_revision:
            raise RemediationBlockedError("Remediation revision does not match incident")
        expected_target = incident.metadata.get("target_branch")
        if expected_target and request.target_branch != expected_target:
            raise RemediationBlockedError("Remediation target branch does not match incident")
        allowed_profiles = incident.metadata.get("remediation_check_profiles")
        if allowed_profiles is not None and request.check_profile not in allowed_profiles:
            raise RemediationBlockedError("Remediation check profile is not allowed")
        expected_branch = f"incident-fix/{incident.external_id}"
        if request.branch_name != expected_branch:
            raise RemediationBlockedError(
                f"Remediation branch must be '{expected_branch}'"
            )

    def _validate_paths(self, paths: Sequence[str]) -> None:
        if len(paths) > self._max_changed_files:
            raise RemediationBlockedError("Patch changes too many files")
        for path in paths:
            if any(path == item or path.startswith(item) for item in self._forbidden_paths):
                raise RemediationBlockedError(f"Patch touches protected path '{path}'")

    def _patch_path(self, incident: IncidentEvent) -> Path:
        return self._workspace_root / f"{incident.incident_id}.patch"

    async def _load_staged_request(
        self, incident: IncidentEvent, proposal: ActionProposal
    ) -> RemediationRequest:
        arguments = dict(proposal.arguments)
        expected_hash = str(arguments.pop("patch_sha256", ""))
        summary = RemediationRequestSummary.model_validate(arguments)
        patch_path = self._patch_path(incident)
        try:
            unified_diff = await asyncio.to_thread(
                patch_path.read_text, encoding="utf-8"
            )
        except FileNotFoundError as error:
            raise RemediationBlockedError("Staged remediation patch is missing") from error
        actual_hash = hashlib.sha256(unified_diff.encode()).hexdigest()
        if not expected_hash or actual_hash != expected_hash:
            raise RemediationBlockedError("Staged remediation patch hash mismatch")
        request = RemediationRequest(
            **summary.model_dump(), unified_diff=unified_diff
        )
        self._validate_request(incident, request)
        return request


class DeterministicRemediationReviewer:
    async def review(
        self,
        incident: IncidentEvent,
        request: RemediationRequest,
        changes: Sequence[FileChange],
        checks: Sequence[CheckResult],
    ) -> RemediationReview:
        del incident, request
        if not changes or any(item.exit_code != 0 for item in checks):
            return RemediationReview(
                approved=False, summary="Patch or validation evidence is incomplete"
            )
        return RemediationReview(
            approved=True,
            summary="Patch is non-empty and every allowlisted sandbox check passed",
        )


_DIFF_PATH = re.compile(r"^(?:---|\+\+\+) (?:[ab]/)?(.+)$", re.MULTILINE)


def _changed_paths(diff: str) -> tuple[str, ...]:
    paths: list[str] = []
    for raw in _DIFF_PATH.findall(diff):
        if raw == "/dev/null":
            continue
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise RemediationBlockedError(f"Patch contains unsafe path '{raw}'")
        normalized = path.as_posix()
        if normalized not in paths:
            paths.append(normalized)
    if not paths:
        raise RemediationBlockedError("Patch contains no changed paths")
    return tuple(paths)


def _read_optional_text(path: Path) -> str | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise RemediationBlockedError(f"Patch target is not a regular file: {path.name}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise RemediationBlockedError("Binary file changes are not supported") from error


def _summarize_change(change: FileChange) -> RemediationFileSummary:
    if change.content is None:
        operation = "delete"
        digest_input = b"<deleted>"
    else:
        operation = "update" if change.previous_exists else "create"
        digest_input = change.content.encode()
    return RemediationFileSummary(
        path=change.path,
        operation=operation,
        content_sha256=hashlib.sha256(digest_input).hexdigest(),
        previous_exists=change.previous_exists,
    )


def _summarize_request(request: RemediationRequest) -> RemediationRequestSummary:
    return RemediationRequestSummary.model_validate(
        request.model_dump(exclude={"unified_diff"})
    )


async def _apply_patch(workspace: Path, diff: str) -> None:
    for check_only in (True, False):
        arguments = ["git", "apply", "--whitespace=error"]
        if check_only:
            arguments.append("--check")
        process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=workspace,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await process.communicate(diff.encode())
        if process.returncode != 0:
            message = output.decode(errors="replace")[-2000:]
            raise RemediationBlockedError(f"Patch validation failed: {message}")


async def _remove_workspace(path: Path) -> None:
    if not path.exists():
        return
    await asyncio.to_thread(_remove_tree, path)


def _remove_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path)


def _report_description(description: str, report: RemediationReport) -> str:
    checks = "\n".join(
        f"- `{ ' '.join(item.command) }`: exit {item.exit_code}" for item in report.checks
    )
    return (
        f"{description}\n\n"
        "## Automated safety report\n\n"
        f"Patch SHA-256: `{report.patch_sha256}`\n\n"
        f"Critic: {report.review.summary}\n\n"
        f"Checks:\n{checks}"
    )
