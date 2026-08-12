from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import aiosqlite

from incident_investigator.application.models import IncidentRecord, IncidentStatus
from incident_investigator.domain import IncidentEvent


class SqliteIncidentRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    correlation_id TEXT NOT NULL UNIQUE,
                    event_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    graph_status TEXT,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status, created_at)"
            )
            await db.commit()

    async def enqueue(self, event: IncidentEvent) -> tuple[IncidentRecord, bool]:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self._database_path) as db:
            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO incidents (
                    incident_id, correlation_id, event_json, status, state_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    str(event.incident_id),
                    event.correlation_id,
                    event.model_dump_json(),
                    IncidentStatus.QUEUED.value,
                    now,
                    now,
                ),
            )
            await db.commit()
            created = cursor.rowcount == 1

        record = await self.get_by_correlation_id(event.correlation_id)
        if record is None:
            raise RuntimeError("Incident enqueue succeeded but record could not be loaded")
        return record, created

    async def get(self, incident_id: UUID | str) -> IncidentRecord | None:
        return await self._fetch_one(
            "SELECT * FROM incidents WHERE incident_id = ?", (str(incident_id),)
        )

    async def get_by_correlation_id(self, correlation_id: str) -> IncidentRecord | None:
        return await self._fetch_one(
            "SELECT * FROM incidents WHERE correlation_id = ?", (correlation_id,)
        )

    async def list(self, limit: int = 100) -> Sequence[IncidentRecord]:
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
        return [self._to_record(row) for row in rows]

    async def claim_next(self) -> IncidentRecord | None:
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT * FROM incidents WHERE status = ? ORDER BY created_at LIMIT 1",
                (IncidentStatus.QUEUED.value,),
            )
            row = await cursor.fetchone()
            if row is None:
                await db.commit()
                return None
            now = datetime.now(UTC).isoformat()
            await db.execute(
                "UPDATE incidents SET status = ?, updated_at = ? WHERE incident_id = ?",
                (IncidentStatus.RUNNING.value, now, row["incident_id"]),
            )
            await db.commit()
        record = self._to_record(row)
        record.status = IncidentStatus.RUNNING
        record.updated_at = datetime.fromisoformat(now)
        return record

    async def update(
        self,
        incident_id: UUID | str,
        *,
        status: IncidentStatus,
        graph_status: str | None = None,
        state: dict | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self._database_path) as db:
            await db.execute(
                """
                UPDATE incidents
                SET status = ?, graph_status = ?, state_json = ?, error = ?, updated_at = ?
                WHERE incident_id = ?
                """,
                (
                    status.value,
                    graph_status,
                    json.dumps(state or {}, default=str),
                    error,
                    now,
                    str(incident_id),
                ),
            )
            await db.commit()

    async def recover_interrupted_runs(self) -> int:
        """Re-queue work interrupted by a process crash; approvals remain paused."""
        async with aiosqlite.connect(self._database_path) as db:
            cursor = await db.execute(
                "UPDATE incidents SET status = ? WHERE status = ?",
                (IncidentStatus.QUEUED.value, IncidentStatus.RUNNING.value),
            )
            await db.commit()
            return cursor.rowcount

    async def _fetch_one(self, query: str, params: tuple[str, ...]) -> IncidentRecord | None:
        async with aiosqlite.connect(self._database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
        return self._to_record(row) if row else None

    @staticmethod
    def _to_record(row: aiosqlite.Row) -> IncidentRecord:
        return IncidentRecord(
            incident_id=UUID(row["incident_id"]),
            correlation_id=row["correlation_id"],
            event=IncidentEvent.model_validate_json(row["event_json"]),
            status=IncidentStatus(row["status"]),
            graph_status=row["graph_status"],
            state=json.loads(row["state_json"]),
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

