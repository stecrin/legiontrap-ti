"""Processing jobs polling API — Phase 6 PR A1.

GET /api/jobs/{job_id}    — return job status and result when completed
GET /api/jobs             — list recent jobs (filtered by type/status)

Auth: require_jwt_or_api_key on all endpoints.

The result field is only present when status=completed. It contains the
parsed JSON from processing_jobs.result_summary_json.

TTL enforcement: stale 'running' jobs are transitioned to 'failed' on
GET /api/jobs/{job_id} when their started_at is older than
AI_TIMEOUT_SECONDS * 2. This prevents ghost records from accumulating
after process restarts.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import settings
from app.db.connection import get_session
from app.db.repository import EventRepository
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_TTL_SECONDS_MULTIPLIER = 2


def _enrich_job(job: dict) -> dict:
    """Add derived fields to a job dict before returning it to callers."""
    enriched = dict(job)
    enriched["poll_url"] = f"/api/jobs/{job['id']}"

    # Parse result_summary_json into a structured 'result' field.
    raw_result = enriched.pop("result_summary_json", None)
    if raw_result and enriched.get("status") == "completed":
        try:
            enriched["result"] = json.loads(raw_result)
        except (ValueError, TypeError):
            enriched["result"] = None
    else:
        enriched["result"] = None

    # Parse backend_metadata_json into a structured field.
    raw_meta = enriched.pop("backend_metadata_json", None)
    if raw_meta:
        try:
            enriched["backend_metadata"] = json.loads(raw_meta)
        except (ValueError, TypeError):
            enriched["backend_metadata"] = None
    else:
        enriched["backend_metadata"] = None

    return enriched


@router.get("/{job_id}")
def get_job(
    job_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return job status, metadata, and result (when completed).

    Applies TTL enforcement on read: a 'running' job whose started_at
    exceeds AI_TIMEOUT_SECONDS * 2 is transitioned to 'failed' before
    the response is built.
    """
    timeout = settings.AI_TIMEOUT_SECONDS * _TTL_SECONDS_MULTIPLIER

    with get_session() as session:
        repo = EventRepository(session)

        # TTL enforcement: stale running jobs → failed.
        repo.transition_stale_jobs_to_failed(timeout)

        job = repo.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id!r} not found",
            )

    return _enrich_job(job)


@router.get("")
def list_jobs(
    job_type: str | None = Query(default=None),
    job_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(require_jwt_or_api_key),
):
    """List recent processing jobs with optional type and status filters."""
    with get_session() as session:
        repo = EventRepository(session)
        jobs = repo.list_jobs(limit=limit, job_type=job_type, status=job_status)

    return {"jobs": [_enrich_job(j) for j in jobs], "count": len(jobs)}
