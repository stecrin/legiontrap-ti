"""AI audit log repository — append-only writes for the ai_audit_log table.

All SQL lives here. No mutation methods are provided: audit records are
immutable historical evidence. There is no update_ai_audit_log() and
no delete_ai_audit_log().

Content is never stored here — only call metadata. This is enforced by
the schema (no content columns) and by design (callers pass byte counts,
not content strings).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "job_id": row[1],
        "output_id": row[2],
        "triggered_by": row[3],
        "backend": row[4],
        "model_name": row[5],
        "operation_type": row[6],
        "resource_type": row[7],
        "resource_id": row[8],
        "payload_bytes": row[9],
        "response_bytes": row[10],
        "latency_ms": row[11],
        "status": row[12],
        "error_type": row[13],
        "created_at": row[14],
    }


_SELECT_COLS = """
    SELECT id, job_id, output_id, triggered_by, backend, model_name,
           operation_type, resource_type, resource_id,
           payload_bytes, response_bytes, latency_ms,
           status, error_type, created_at
    FROM ai_audit_log
"""


class AiAuditLogRepository(RepositoryBase):
    def create_ai_audit_log(
        self,
        *,
        log_id: str | None = None,
        job_id: str | None = None,
        output_id: str | None = None,
        triggered_by: str | None = None,
        backend: str,
        model_name: str,
        operation_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload_bytes: int = 0,
        response_bytes: int = 0,
        latency_ms: int = 0,
        status: str,
        error_type: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """Insert an immutable ai_audit_log row and return it.

        This is the only write method. Content (prompt text, response text)
        is never accepted or stored — only metadata.
        """
        lid = log_id or str(uuid.uuid4())
        now = created_at or datetime.now(UTC).isoformat()
        self._session.execute(
            text("""
                INSERT INTO ai_audit_log (
                    id, job_id, output_id, triggered_by,
                    backend, model_name, operation_type,
                    resource_type, resource_id,
                    payload_bytes, response_bytes, latency_ms,
                    status, error_type, created_at
                ) VALUES (
                    :id, :job_id, :output_id, :triggered_by,
                    :backend, :model_name, :operation_type,
                    :resource_type, :resource_id,
                    :payload_bytes, :response_bytes, :latency_ms,
                    :status, :error_type, :created_at
                )
            """),
            {
                "id": lid,
                "job_id": job_id,
                "output_id": output_id,
                "triggered_by": triggered_by,
                "backend": backend,
                "model_name": model_name,
                "operation_type": operation_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "payload_bytes": payload_bytes,
                "response_bytes": response_bytes,
                "latency_ms": latency_ms,
                "status": status,
                "error_type": error_type,
                "created_at": now,
            },
        )
        return self.get_ai_audit_log(lid)  # type: ignore[return-value]

    def get_ai_audit_log(self, log_id: str) -> dict[str, Any] | None:
        """Return a single audit record by id, or None if not found."""
        row = self._session.execute(
            text(_SELECT_COLS + "WHERE id = :id"),
            {"id": log_id},
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def list_ai_audit_logs(
        self,
        *,
        limit: int = 50,
        triggered_by: str | None = None,
        backend: str | None = None,
        status: str | None = None,
        job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return audit records, newest first, with optional filters."""
        clauses = []
        params: dict[str, Any] = {"limit": limit}
        if triggered_by is not None:
            clauses.append("triggered_by = :triggered_by")
            params["triggered_by"] = triggered_by
        if backend is not None:
            clauses.append("backend = :backend")
            params["backend"] = backend
        if status is not None:
            clauses.append("status = :status")
            params["status"] = status
        if job_id is not None:
            clauses.append("job_id = :job_id")
            params["job_id"] = job_id
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._session.execute(
            text(_SELECT_COLS + f"{where} ORDER BY created_at DESC LIMIT :limit"),
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def list_ai_audit_logs_for_job(self, job_id: str) -> list[dict[str, Any]]:
        """Return all audit records for a given job_id, newest first."""
        return self.list_ai_audit_logs(job_id=job_id, limit=100)
