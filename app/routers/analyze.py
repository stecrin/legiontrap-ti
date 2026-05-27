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

Failure modes handled asynchronously (via job status):
  job.status=failed + error_message — AI disabled, backend unreachable,
                                       backend error, internal error

Deduplication (summary only):
  If a pending or running summary job already exists for the same
  campaign_id, the existing job_id is returned immediately with
  HTTP 202 and status='running'|'pending'.

Auth: require_jwt_or_api_key on all endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.connection import get_session
from app.db.repository import EventRepository
from app.jobs.runner import run_campaign_brief_job, run_campaign_summary_job
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(prefix="/api/campaigns", tags=["analyze"])


class BriefRequest(BaseModel):
    max_campaigns: int = Field(default=10, ge=1, le=25)


def _triggered_by(auth_info: dict) -> str:
    """Extract a safe operator identity string from the auth dependency result."""
    if auth_info.get("auth") == "jwt":
        sub = auth_info.get("sub") or "unknown"
        return f"user:{sub}"
    return "api_key"


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

        # Create a new job.
        job = repo.create_job(
            job_type="campaign_summary",
            triggered_by=triggered_by,
            resource_type="campaign",
            resource_id=campaign_id,
            deduplication_key=dedup_key,
            created_at=now,
        )

    background_tasks.add_task(run_campaign_summary_job, job["id"])
    return _accepted_response(job["id"], "pending", now)


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

    with get_session() as session:
        repo = EventRepository(session)
        # Store max_campaigns in backend_metadata_json so the runner can read it.
        job = repo.create_job(
            job_type="campaign_brief",
            triggered_by=triggered_by,
            resource_type=None,
            resource_id=None,
            deduplication_key=None,
            created_at=now,
            backend_metadata_json={"max_campaigns": body.max_campaigns},
        )

    background_tasks.add_task(run_campaign_brief_job, job["id"])
    return _accepted_response(job["id"], "pending", now)


def _accepted_response(job_id: str, job_status: str, accepted_at: str) -> dict:
    return {
        "job_id": job_id,
        "status": job_status,
        "poll_url": f"/api/jobs/{job_id}",
        "accepted_at": accepted_at,
    }
