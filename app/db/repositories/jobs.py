"""Processing jobs repository — CRUD for the processing_jobs table.

All SQL lives here. State machine transitions enforce valid status progressions.
No business logic — callers (runner, analyze router, tasks) own that.

Status machine:
  pending  → running    (start_job)
  running  → completed  (complete_job)
  running  → failed     (fail_job)
  pending  → cancelled  (cancel_job)
  running  → cancelled  (cancel_job)

Invalid transitions are detected and return False; callers may log but must
not raise — a stale transition must never surface as an HTTP error.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase

# Valid status values
_VALID_STATUSES = frozenset({"pending", "running", "completed", "failed", "cancelled"})


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "job_type": row[1],
        "status": row[2],
        "created_at": row[3],
        "started_at": row[4],
        "completed_at": row[5],
        "failed_at": row[6],
        "triggered_by": row[7],
        "resource_type": row[8],
        "resource_id": row[9],
        "deduplication_key": row[10],
        "progress_percent": row[11],
        "result_summary_json": row[12],
        "error_message": row[13],
        "backend_metadata_json": row[14],
        "ai_output_id": row[15] if len(row) > 15 else None,
    }


class JobRepository(RepositoryBase):
    def create_job(
        self,
        *,
        job_id: str | None = None,
        job_type: str,
        triggered_by: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        deduplication_key: str | None = None,
        created_at: str | None = None,
        backend_metadata_json: dict | str | None = None,
    ) -> dict[str, Any]:
        """Insert a new processing_job row in 'pending' state and return it."""
        jid = job_id or str(uuid.uuid4())
        now = created_at or datetime.now(UTC).isoformat()
        meta_str = (
            json.dumps(backend_metadata_json)
            if isinstance(backend_metadata_json, dict)
            else backend_metadata_json
        )
        self._session.execute(
            text("""
                INSERT INTO processing_jobs (
                    id, job_type, status, created_at,
                    triggered_by, resource_type, resource_id,
                    deduplication_key, progress_percent,
                    backend_metadata_json
                ) VALUES (
                    :id, :job_type, 'pending', :created_at,
                    :triggered_by, :resource_type, :resource_id,
                    :deduplication_key, 0, :backend_metadata_json
                )
            """),
            {
                "id": jid,
                "job_type": job_type,
                "created_at": now,
                "triggered_by": triggered_by,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "deduplication_key": deduplication_key,
                "backend_metadata_json": meta_str,
            },
        )
        return self.get_job(jid)  # type: ignore[return-value]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Return full job row as dict, or None if not found."""
        row = self._session.execute(
            text("""
                SELECT id, job_type, status, created_at, started_at,
                       completed_at, failed_at, triggered_by,
                       resource_type, resource_id, deduplication_key,
                       progress_percent, result_summary_json,
                       error_message, backend_metadata_json, ai_output_id
                FROM processing_jobs WHERE id = :id
            """),
            {"id": job_id},
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def list_jobs(
        self,
        *,
        limit: int = 50,
        job_type: str | None = None,
        status: str | None = None,
        resource_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return jobs sorted by created_at DESC with optional filters."""
        clauses = []
        params: dict[str, Any] = {"limit": limit}
        if job_type is not None:
            clauses.append("job_type = :job_type")
            params["job_type"] = job_type
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        if resource_id is not None:
            clauses.append("resource_id = :resource_id")
            params["resource_id"] = resource_id
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._session.execute(
            text(f"""
                SELECT id, job_type, status, created_at, started_at,
                       completed_at, failed_at, triggered_by,
                       resource_type, resource_id, deduplication_key,
                       progress_percent, result_summary_json,
                       error_message, backend_metadata_json, ai_output_id
                FROM processing_jobs
                {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_active_job_by_dedup_key(self, dedup_key: str) -> dict[str, Any] | None:
        """Return a pending or running job with this deduplication_key, or None.

        Used before create_job to prevent duplicate work for the same resource.
        Callers should treat this as advisory; a small race window exists between
        check and insert in concurrent environments.
        """
        row = self._session.execute(
            text("""
                SELECT id, job_type, status, created_at, started_at,
                       completed_at, failed_at, triggered_by,
                       resource_type, resource_id, deduplication_key,
                       progress_percent, result_summary_json,
                       error_message, backend_metadata_json, ai_output_id
                FROM processing_jobs
                WHERE deduplication_key = :key
                  AND status IN ('pending', 'running')
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"key": dedup_key},
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def start_job(self, job_id: str, *, started_at: str | None = None) -> bool:
        """Transition job from 'pending' to 'running'.

        Returns True on success, False if job is not in 'pending' state.
        """
        now = started_at or datetime.now(UTC).isoformat()
        result = self._session.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'running', started_at = :started_at, progress_percent = 0
                WHERE id = :id AND status = 'pending'
            """),
            {"id": job_id, "started_at": now},
        )
        return result.rowcount > 0

    def complete_job(
        self,
        job_id: str,
        *,
        completed_at: str | None = None,
        result_summary_json: dict | str | None = None,
        backend_metadata_json: dict | str | None = None,
        ai_output_id: str | None = None,
    ) -> bool:
        """Transition job from 'running' to 'completed'.

        Returns True on success, False if job is not in 'running' state.
        ai_output_id links to the persisted ai_outputs row (set in PR A2+).
        """
        now = completed_at or datetime.now(UTC).isoformat()
        result_str = (
            json.dumps(result_summary_json)
            if isinstance(result_summary_json, dict)
            else result_summary_json
        )
        meta_str = (
            json.dumps(backend_metadata_json)
            if isinstance(backend_metadata_json, dict)
            else backend_metadata_json
        )
        result = self._session.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'completed',
                    completed_at = :completed_at,
                    progress_percent = 100,
                    result_summary_json = :result_summary_json,
                    backend_metadata_json = :backend_metadata_json,
                    ai_output_id = :ai_output_id
                WHERE id = :id AND status = 'running'
            """),
            {
                "id": job_id,
                "completed_at": now,
                "result_summary_json": result_str,
                "backend_metadata_json": meta_str,
                "ai_output_id": ai_output_id,
            },
        )
        return result.rowcount > 0

    def fail_job(
        self,
        job_id: str,
        *,
        failed_at: str | None = None,
        error_message: str | None = None,
        backend_metadata_json: dict | str | None = None,
    ) -> bool:
        """Transition job from 'running' to 'failed'.

        error_message must be a safe, user-visible summary. No stack traces.
        Returns True on success, False if job is not in 'running' state.
        """
        now = failed_at or datetime.now(UTC).isoformat()
        meta_str = (
            json.dumps(backend_metadata_json)
            if isinstance(backend_metadata_json, dict)
            else backend_metadata_json
        )
        result = self._session.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'failed',
                    failed_at = :failed_at,
                    error_message = :error_message,
                    backend_metadata_json = :backend_metadata_json
                WHERE id = :id AND status = 'running'
            """),
            {
                "id": job_id,
                "failed_at": now,
                "error_message": error_message,
                "backend_metadata_json": meta_str,
            },
        )
        return result.rowcount > 0

    def cancel_job(self, job_id: str, *, completed_at: str | None = None) -> bool:
        """Transition job from 'pending' or 'running' to 'cancelled'.

        Returns True on success, False if job is not in a cancellable state.
        """
        now = completed_at or datetime.now(UTC).isoformat()
        result = self._session.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'cancelled', completed_at = :completed_at
                WHERE id = :id AND status IN ('pending', 'running')
            """),
            {"id": job_id, "completed_at": now},
        )
        return result.rowcount > 0

    def update_progress(self, job_id: str, progress_percent: int) -> None:
        """Update progress_percent for a running job. Clamped to 0–100."""
        pct = max(0, min(100, progress_percent))
        self._session.execute(
            text("""
                UPDATE processing_jobs
                SET progress_percent = :pct
                WHERE id = :id AND status = 'running'
            """),
            {"id": job_id, "pct": pct},
        )

    def transition_stale_jobs_to_failed(
        self, timeout_seconds: int, *, now: str | None = None
    ) -> int:
        """Move 'running' jobs that have exceeded timeout to 'failed'.

        A job is stale when started_at is more than timeout_seconds ago.
        Returns count of rows updated.
        """
        from datetime import timedelta

        if now is None:
            cutoff_dt = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        else:
            now_dt = datetime.fromisoformat(now.replace("Z", "+00:00")).astimezone(UTC)
            cutoff_dt = now_dt - timedelta(seconds=timeout_seconds)
        cutoff = cutoff_dt.isoformat()
        result = self._session.execute(
            text("""
                UPDATE processing_jobs
                SET status = 'failed',
                    failed_at = :now,
                    error_message = 'Job timed out'
                WHERE status = 'running'
                  AND started_at IS NOT NULL
                  AND started_at < :cutoff
            """),
            {
                "now": now or datetime.now(UTC).isoformat(),
                "cutoff": cutoff,
            },
        )
        return result.rowcount
