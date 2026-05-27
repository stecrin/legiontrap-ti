"""Background job executors for Phase 6 async AI operations.

Each function is designed to be called via FastAPI BackgroundTasks:
    background_tasks.add_task(run_campaign_summary_job, job_id)

Execution model:
  1. Open DB session, fetch job, verify it is in 'pending' state.
  2. Transition to 'running' via start_job(). If start_job returns False,
     another executor has already taken the job — return silently.
  3. Execute AI logic (read-only DB fetch → prompt build → AI call → validate).
  4. On success: complete_job() with result_summary_json.
  5. On any exception: fail_job() with a safe error summary. Stack traces
     are logged but never stored in the job record.

Deterministic-first invariants enforced here:
  - No writes to campaigns, fingerprints, events, or observations.
  - AI output is stored only in processing_jobs.result_summary_json (A1).
    PR A2 will introduce the ai_outputs table.
  - get_ai_backend() is imported here so tests can monkeypatch
    'app.jobs.runner.get_ai_backend' without touching the router.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from app.ai import (
    AIBackendError,
    AIBackendUnavailableError,
    AIDisabledError,
    get_ai_backend,
)
from app.ai.prompt_builder import build_brief_prompt, build_campaign_summary_prompt
from app.ai.safety import validate_ai_output
from app.core.config import settings
from app.db.connection import get_session
from app.db.repository import EventRepository

logger = logging.getLogger(__name__)

_SUMMARY_WARNING = (
    "This analysis is AI-assisted. All factual claims are derived from "
    "deterministic campaign data. Attribution language is inferential, not asserted."
)

_MAX_SUMMARY_LEN = 1000
_MAX_BRIEF_LEN = 2500
_MAX_OBSERVATIONS = 10
_BRIEF_STATUSES = {"active", "dormant", "reactivated"}


def run_campaign_summary_job(job_id: str) -> None:
    """Execute an AI summary job for a single campaign.

    Called as a FastAPI BackgroundTask. Manages full job lifecycle:
    pending → running → completed | failed.

    Failures are logged but never propagated — a job failure must not
    surface as an unhandled exception in the BackgroundTasks worker.
    """
    try:
        _execute_summary(job_id)
    except Exception:
        logger.exception("Unhandled exception in run_campaign_summary_job job_id=%s", job_id)
        _force_fail(job_id, "Internal error during job execution")


def run_campaign_brief_job(job_id: str) -> None:
    """Execute an AI brief job for multiple campaigns.

    Called as a FastAPI BackgroundTask. Manages full job lifecycle:
    pending → running → completed | failed.
    """
    try:
        _execute_brief(job_id)
    except Exception:
        logger.exception("Unhandled exception in run_campaign_brief_job job_id=%s", job_id)
        _force_fail(job_id, "Internal error during job execution")


# ---------------------------------------------------------------------------
# Internal execution logic
# ---------------------------------------------------------------------------


def _execute_summary(job_id: str) -> None:
    started_at = datetime.now(UTC).isoformat()
    t0 = time.monotonic()

    with get_session() as session:
        repo = EventRepository(session)
        started = repo.start_job(job_id, started_at=started_at)
        if not started:
            # Another executor already took this job, or it was cancelled.
            logger.debug("run_campaign_summary_job: job %s not in pending state, skipping", job_id)
            return
        job = repo.get_job(job_id)

    if job is None:
        logger.warning("run_campaign_summary_job: job %s not found after start", job_id)
        return

    campaign_id: str = job.get("resource_id") or ""

    # Fetch campaign data — read-only session, separate from job lifecycle session.
    with get_session() as session:
        repo = EventRepository(session)
        campaign = repo.get_campaign(campaign_id)
        if campaign is None:
            _fail_job_safe(job_id, f"Campaign {campaign_id!r} not found")
            return
        members = repo.get_campaign_members(campaign_id)
        fingerprint = None
        if members:
            fingerprint = repo.get_behavioral_fingerprint(members[0]["source_ip"])
        all_obs = repo.get_campaign_observations(campaign_id)
        observations = all_obs[-_MAX_OBSERVATIONS:]

    # Build prompt and call AI backend.
    prompt_data = build_campaign_summary_prompt(campaign, fingerprint, observations)

    try:
        backend = get_ai_backend()
        raw_output = backend.generate(prompt_data["user_prompt"])
    except AIDisabledError as exc:
        _fail_job_safe(job_id, str(exc))
        return
    except AIBackendUnavailableError as exc:
        _fail_job_safe(job_id, str(exc))
        return
    except AIBackendError as exc:
        _fail_job_safe(job_id, str(exc))
        return

    validated_text, rejection_reason = validate_ai_output(raw_output, max_len=_MAX_SUMMARY_LEN)
    generated_at = datetime.now(UTC).isoformat()
    latency_ms = int((time.monotonic() - t0) * 1000)

    is_rejected = rejection_reason in ("ip_detected", "empty_response")
    is_truncated = rejection_reason == "truncated"

    result = {
        "ai_assisted": True,
        "ai_backend": settings.AI_BACKEND,
        "generated_at": generated_at,
        "warning": _SUMMARY_WARNING,
        "campaign_id": campaign_id,
        "summary": None if is_rejected else validated_text,
        "source_records": prompt_data["source_records"],
        "safety_flags": prompt_data["safety_flags"],
        "rejected": is_rejected,
        "rejection_reason": rejection_reason,
        "truncated": is_truncated,
    }
    backend_meta = {"ai_backend": settings.AI_BACKEND, "latency_ms": latency_ms}

    with get_session() as session:
        repo = EventRepository(session)
        repo.complete_job(
            job_id,
            result_summary_json=result,
            backend_metadata_json=backend_meta,
        )


def _execute_brief(job_id: str) -> None:
    started_at = datetime.now(UTC).isoformat()
    t0 = time.monotonic()

    with get_session() as session:
        repo = EventRepository(session)
        started = repo.start_job(job_id, started_at=started_at)
        if not started:
            logger.debug("run_campaign_brief_job: job %s not in pending state, skipping", job_id)
            return
        job = repo.get_job(job_id)

    if job is None:
        return

    # Parse max_campaigns from backend_metadata_json (stored by analyze router).
    max_campaigns = 10
    if job.get("backend_metadata_json"):
        import json as _json

        try:
            meta = _json.loads(job["backend_metadata_json"])
            max_campaigns = int(meta.get("max_campaigns", 10))
        except (ValueError, TypeError, KeyError):
            pass

    # Fetch campaigns — read-only session.
    with get_session() as session:
        repo = EventRepository(session)
        all_campaigns = repo.list_campaigns(limit=max_campaigns * 4)

    campaigns = [c for c in all_campaigns if c.get("status") in _BRIEF_STATUSES][:max_campaigns]

    generated_at = datetime.now(UTC).isoformat()
    latency_ms = int((time.monotonic() - t0) * 1000)

    if not campaigns:
        result = {
            "ai_assisted": True,
            "ai_backend": settings.AI_BACKEND,
            "generated_at": generated_at,
            "warning": _SUMMARY_WARNING,
            "summary": None,
            "campaign_count": 0,
            "source_records": {"campaign_ids": [], "campaign_count": 0},
            "rejected": False,
            "rejection_reason": "no_campaigns",
            "truncated": False,
        }
        with get_session() as session:
            repo = EventRepository(session)
            repo.complete_job(
                job_id,
                result_summary_json=result,
                backend_metadata_json={"ai_backend": settings.AI_BACKEND, "latency_ms": latency_ms},
            )
        return

    prompt_data = build_brief_prompt(campaigns)

    try:
        backend = get_ai_backend()
        raw_output = backend.generate(prompt_data["user_prompt"])
    except AIDisabledError as exc:
        _fail_job_safe(job_id, str(exc))
        return
    except AIBackendUnavailableError as exc:
        _fail_job_safe(job_id, str(exc))
        return
    except AIBackendError as exc:
        _fail_job_safe(job_id, str(exc))
        return

    validated_text, rejection_reason = validate_ai_output(raw_output, max_len=_MAX_BRIEF_LEN)
    generated_at = datetime.now(UTC).isoformat()
    latency_ms = int((time.monotonic() - t0) * 1000)

    is_rejected = rejection_reason in ("ip_detected", "empty_response")
    is_truncated = rejection_reason == "truncated"

    result = {
        "ai_assisted": True,
        "ai_backend": settings.AI_BACKEND,
        "generated_at": generated_at,
        "warning": _SUMMARY_WARNING,
        "summary": None if is_rejected else validated_text,
        "campaign_count": len(campaigns),
        "source_records": prompt_data["source_records"],
        "rejected": is_rejected,
        "rejection_reason": rejection_reason,
        "truncated": is_truncated,
    }
    backend_meta = {"ai_backend": settings.AI_BACKEND, "latency_ms": latency_ms}

    with get_session() as session:
        repo = EventRepository(session)
        repo.complete_job(
            job_id,
            result_summary_json=result,
            backend_metadata_json=backend_meta,
        )


# ---------------------------------------------------------------------------
# Failure helpers
# ---------------------------------------------------------------------------


def _fail_job_safe(job_id: str, error_message: str) -> None:
    """Transition job to failed with a safe error message. No stack traces."""
    try:
        with get_session() as session:
            repo = EventRepository(session)
            repo.fail_job(job_id, error_message=error_message)
    except Exception:
        logger.exception("Failed to record job failure for job_id=%s", job_id)


def _force_fail(job_id: str, error_message: str) -> None:
    """Best-effort fail for unhandled exception paths. Does not raise."""
    try:
        with get_session() as session:
            repo = EventRepository(session)
            job = repo.get_job(job_id)
            if job and job["status"] == "running":
                repo.fail_job(job_id, error_message=error_message)
            elif job and job["status"] == "pending":
                repo.start_job(job_id)
                repo.fail_job(job_id, error_message=error_message)
    except Exception:
        logger.exception("_force_fail could not update job_id=%s", job_id)
