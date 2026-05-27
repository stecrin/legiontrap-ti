"""AI outputs repository — write-once CRUD for the ai_outputs table.

All SQL lives here. No mutation methods are provided: ai_outputs are
immutable historical records. Corrections create new rows; old rows are
never modified or deleted by application code.

Write-once invariant: create_ai_output() is the only write method.
There is no update_ai_output() and no delete_ai_output().
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "job_id": row[1],
        "output_type": row[2],
        "resource_type": row[3],
        "resource_id": row[4],
        "content": row[5],
        "backend": row[6],
        "model_name": row[7],
        "prompt_hash": row[8],
        "payload_bytes": row[9],
        "source_records_json": row[10],
        "safety_flags_json": row[11],
        "rejected": bool(row[12]),
        "rejection_reason": row[13],
        "truncated": bool(row[14]),
        "data_quality_score": row[15],
        "generated_at": row[16],
        "triggered_by": row[17],
    }


_SELECT_COLS = """
    SELECT id, job_id, output_type, resource_type, resource_id,
           content, backend, model_name, prompt_hash, payload_bytes,
           source_records_json, safety_flags_json, rejected,
           rejection_reason, truncated, data_quality_score,
           generated_at, triggered_by
    FROM ai_outputs
"""


class AiOutputRepository(RepositoryBase):
    def create_ai_output(
        self,
        *,
        output_id: str | None = None,
        job_id: str,
        output_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        content: str | None = None,
        backend: str,
        model_name: str,
        prompt_hash: str,
        payload_bytes: int,
        source_records_json: dict | list | str,
        safety_flags_json: list | str | None = None,
        rejected: bool = False,
        rejection_reason: str | None = None,
        truncated: bool = False,
        data_quality_score: float | None = None,
        generated_at: str | None = None,
        triggered_by: str | None = None,
    ) -> dict[str, Any]:
        """Insert an immutable ai_outputs row and return it.

        This is the only write method. There is no update path.
        """
        oid = output_id or str(uuid.uuid4())
        now = generated_at or datetime.now(UTC).isoformat()
        src_str = (
            json.dumps(source_records_json)
            if not isinstance(source_records_json, str)
            else source_records_json
        )
        flags_str = (
            json.dumps(safety_flags_json)
            if safety_flags_json is not None and not isinstance(safety_flags_json, str)
            else safety_flags_json
        )
        self._session.execute(
            text("""
                INSERT INTO ai_outputs (
                    id, job_id, output_type, resource_type, resource_id,
                    content, backend, model_name, prompt_hash, payload_bytes,
                    source_records_json, safety_flags_json, rejected,
                    rejection_reason, truncated, data_quality_score,
                    generated_at, triggered_by
                ) VALUES (
                    :id, :job_id, :output_type, :resource_type, :resource_id,
                    :content, :backend, :model_name, :prompt_hash, :payload_bytes,
                    :source_records_json, :safety_flags_json, :rejected,
                    :rejection_reason, :truncated, :data_quality_score,
                    :generated_at, :triggered_by
                )
            """),
            {
                "id": oid,
                "job_id": job_id,
                "output_type": output_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "content": content,
                "backend": backend,
                "model_name": model_name,
                "prompt_hash": prompt_hash,
                "payload_bytes": payload_bytes,
                "source_records_json": src_str,
                "safety_flags_json": flags_str,
                "rejected": 1 if rejected else 0,
                "rejection_reason": rejection_reason,
                "truncated": 1 if truncated else 0,
                "data_quality_score": data_quality_score,
                "generated_at": now,
                "triggered_by": triggered_by,
            },
        )
        return self.get_ai_output(oid)  # type: ignore[return-value]

    def get_ai_output(self, output_id: str) -> dict[str, Any] | None:
        """Return an ai_outputs row by id, or None if not found."""
        row = self._session.execute(
            text(_SELECT_COLS + "WHERE id = :id"),
            {"id": output_id},
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def list_ai_outputs_for_resource(
        self,
        resource_type: str,
        resource_id: str,
        *,
        output_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return ai_outputs for a resource, newest first.

        Optionally filtered by output_type (e.g. 'campaign_summary').
        """
        params: dict[str, Any] = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "limit": limit,
        }
        type_clause = ""
        if output_type is not None:
            type_clause = "AND output_type = :output_type"
            params["output_type"] = output_type
        rows = self._session.execute(
            text(
                _SELECT_COLS
                + "WHERE resource_type = :resource_type "
                + "AND resource_id = :resource_id "
                + type_clause
                + " ORDER BY generated_at DESC LIMIT :limit"
            ),
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def list_ai_outputs_for_job(self, job_id: str) -> list[dict[str, Any]]:
        """Return all ai_outputs produced by a given job, newest first."""
        rows = self._session.execute(
            text(_SELECT_COLS + "WHERE job_id = :job_id ORDER BY generated_at DESC"),
            {"job_id": job_id},
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_latest_ai_output_for_resource(
        self,
        resource_type: str,
        resource_id: str,
        output_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the most recently generated ai_output for a resource, or None."""
        results = self.list_ai_outputs_for_resource(
            resource_type, resource_id, output_type=output_type, limit=1
        )
        return results[0] if results else None
