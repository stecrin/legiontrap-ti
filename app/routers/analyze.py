"""AI analysis endpoints — Phase 6 PR A1 async refactor.

POST /api/campaigns/{campaign_id}/summary
  Enqueues an AI summary job and returns 202 Accepted with job_id.

POST /api/campaigns/brief
  Enqueues an AI brief job and returns 202 Accepted with job_id.

Both endpoints return immediately. Poll GET /api/jobs/{job_id} for status
and result. The 202 Accepted contract is permanent: callers must not rely
on blocking behaviour.

Failure modes that still raise at POST time (before job creation):
  422 — PRIVACY_MODE=on with AI_BACKEND=claude
  404 — campaign not found (summary only)
  401 — missing or invalid credentials
  422 — invalid request body
  429 — per-operator AI rate limit exceeded (AI_MAX_REQUESTS_PER_MINUTE)

Failure modes handled asynchronously (via job status):
  job.status=failed + error_message — AI disabled, backend unreachable,
                                       backend error, internal error

Deduplication (summary only):
  If a pending or running summary job already exists for the same
  campaign_id, the existing job_id is returned immediately with
  HTTP 202 and status='running'|'pending'.

Rate limiting:
  DB-backed, using the processing_jobs table. Counts campaign_summary and
  campaign_brief jobs created by the same operator in the last 60 seconds.
  Limit is AI_MAX_REQUESTS_PER_MINUTE (default 10). Rate-limited requests
  are written to ai_audit_log with status='rate_limited' in a separate
  session so the record commits even though an HTTPException is raised.

Auth: require_jwt_or_api_key on all endpoints.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.db.connection import get_session
from app.db.repository import EventRepository
from app.jobs.runner import run_campaign_brief_job, run_campaign_summary_job
from app.utils.auth import require_jwt_or_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/campaigns", tags=["analyze"])


class BriefRequest(BaseModel):
    max_campaigns: int = Field(default=10, ge=1, le=25)
    time_window_start: str | None = None
    time_window_end: str | None = None

    @model_validator(mode="after")
    def _check_time_window(self) -> BriefRequest:
        start = self.time_window_start
        end = self.time_window_end
        if (start is None) != (end is None):
            raise ValueError("Both time_window_start and time_window_end must be provided together")
        if start is not None and end is not None:
            try:
                dt_start = datetime.fromisoformat(start)
                dt_end = datetime.fromisoformat(end)
            except ValueError as exc:
                raise ValueError(
                    "time_window_start and time_window_end must be valid ISO 8601 strings"
                ) from exc
            if dt_start >= dt_end:
                raise ValueError("time_window_start must be before time_window_end")
        return self


def _triggered_by(auth_info: dict) -> str:
    """Extract a safe operator identity string from the auth dependency result."""
    if auth_info.get("auth") == "jwt":
        sub = auth_info.get("sub") or "unknown"
        return f"user:{sub}"
    return "api_key"


def _write_rate_limit_audit_safe(
    *,
    triggered_by: str | None,
    operation_type: str,
    resource_type: str | None,
    resource_id: str | None,
) -> None:
    """Write a rate_limited ai_audit_log record in a separate session.

    Uses a separate get_session() call so this write commits independently
    of the HTTPException that immediately follows — exceptions in the same
    session block trigger rollback, which would swallow the audit record.
    """
    try:
        with get_session() as session:
            repo = EventRepository(session)
            repo.create_ai_audit_log(
                triggered_by=triggered_by,
                backend=settings.AI_BACKEND,
                model_name="unknown",
                operation_type=operation_type,
                resource_type=resource_type,
                resource_id=resource_id,
                payload_bytes=0,
                response_bytes=0,
                latency_ms=0,
                status="rate_limited",
                error_type="RateLimitExceeded",
            )
    except Exception:
        logger.exception("Failed to write rate_limited audit log triggered_by=%s", triggered_by)


@router.post("/{campaign_id}/summary", status_code=status.HTTP_202_ACCEPTED)
def campaign_summary(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    auth_info: dict = Depends(require_jwt_or_api_key),
):
    """Enqueue an AI summary job for a single campaign. Returns 202 Accepted.

    Poll GET /api/jobs/{job_id} for status. When status=completed, the
    'result' field contains the AI summary envelope.

    If a pending/running job already exists for this campaign, the existing
    job_id is returned instead of creating a duplicate.
    """
    # Privacy conflict check — still raised at POST time (§5 §7.4).
    if settings.PRIVACY_MODE and settings.AI_BACKEND == "claude":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "AI_BACKEND=claude is not permitted when PRIVACY_MODE is enabled. "
                "Use AI_BACKEND=ollama for local inference in privacy mode, "
                "or set AI_BACKEND=none to disable AI features."
            ),
        )

    triggered_by = _triggered_by(auth_info)
    dedup_key = f"campaign_summary:{campaign_id}"
    now = datetime.now(UTC).isoformat()

    rate_limited = False
    job = None

    with get_session() as session:
        repo = EventRepository(session)

        # Campaign existence check — fast fail before job creation.
        campaign = repo.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {campaign_id!r} not found",
            )

        # Deduplication: return existing active job if one exists.
        existing = repo.get_active_job_by_dedup_key(dedup_key)
        if existing is not None:
            return _accepted_response(existing["id"], existing["status"], now)

        # Rate limit: count AI jobs created by this operator in the last 60s.
        cutoff = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
        if (
            repo.count_recent_ai_jobs(triggered_by, since=cutoff)
            >= settings.AI_MAX_REQUESTS_PER_MINUTE
        ):
            rate_limited = True
        else:
            job = repo.create_job(
                job_type="campaign_summary",
                triggered_by=triggered_by,
                resource_type="campaign",
                resource_id=campaign_id,
                deduplication_key=dedup_key,
                created_at=now,
            )

    if rate_limited:
        _write_rate_limit_audit_safe(
            triggered_by=triggered_by,
            operation_type="campaign_summary",
            resource_type="campaign",
            resource_id=campaign_id,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI rate limit exceeded. Try again in 60 seconds.",
            headers={"Retry-After": "60"},
        )

    background_tasks.add_task(run_campaign_summary_job, job["id"])  # type: ignore[union-attr]
    return _accepted_response(job["id"], "pending", now)  # type: ignore[index]


@router.post("/brief", status_code=status.HTTP_202_ACCEPTED)
def campaign_brief(
    background_tasks: BackgroundTasks,
    body: BriefRequest = Body(default=BriefRequest()),
    auth_info: dict = Depends(require_jwt_or_api_key),
):
    """Enqueue an AI multi-campaign threat brief job. Returns 202 Accepted.

    Poll GET /api/jobs/{job_id} for status. When status=completed, the
    'result' field contains the AI brief envelope.
    """
    if settings.PRIVACY_MODE and settings.AI_BACKEND == "claude":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "AI_BACKEND=claude is not permitted when PRIVACY_MODE is enabled. "
                "Use AI_BACKEND=ollama for local inference in privacy mode, "
                "or set AI_BACKEND=none to disable AI features."
            ),
        )

    triggered_by = _triggered_by(auth_info)
    now = datetime.now(UTC).isoformat()

    rate_limited = False
    job = None

    with get_session() as session:
        repo = EventRepository(session)
        # Rate limit: count AI jobs created by this operator in the last 60s.
        cutoff = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
        if (
            repo.count_recent_ai_jobs(triggered_by, since=cutoff)
            >= settings.AI_MAX_REQUESTS_PER_MINUTE
        ):
            rate_limited = True
        else:
            # Store params in backend_metadata_json so the runner can read them.
            meta: dict = {"max_campaigns": body.max_campaigns}
            if body.time_window_start is not None:
                meta["time_window_start"] = body.time_window_start
                meta["time_window_end"] = body.time_window_end
            job = repo.create_job(
                job_type="campaign_brief",
                triggered_by=triggered_by,
                resource_type=None,
                resource_id=None,
                deduplication_key=None,
                created_at=now,
                backend_metadata_json=meta,
            )

    if rate_limited:
        _write_rate_limit_audit_safe(
            triggered_by=triggered_by,
            operation_type="campaign_brief",
            resource_type=None,
            resource_id=None,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI rate limit exceeded. Try again in 60 seconds.",
            headers={"Retry-After": "60"},
        )

    background_tasks.add_task(run_campaign_brief_job, job["id"])  # type: ignore[union-attr]
    return _accepted_response(job["id"], "pending", now)  # type: ignore[index]


def _accepted_response(job_id: str, job_status: str, accepted_at: str) -> dict:
    return {
        "job_id": job_id,
        "status": job_status,
        "poll_url": f"/api/jobs/{job_id}",
        "accepted_at": accepted_at,
    }
