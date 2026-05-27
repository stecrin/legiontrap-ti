"""Background job executors for Phase 6 async AI operations.

Each function is designed to be called via FastAPI BackgroundTasks:
    background_tasks.add_task(run_campaign_summary_job, job_id)

Execution model:
  1. Open DB session, fetch job, verify it is in 'pending' state.
  2. Transition to 'running' via start_job(). If start_job returns False,
     another executor has already taken the job — return silently.
  3. Execute AI logic (read-only DB fetch → prompt build → AI call → validate).
  4. On success: write ai_outputs row, write audit log, complete_job().
  5. On any AI failure: write audit log, fail_job() with safe error summary.
  6. On unhandled exception: _force_fail() best-effort.

Deterministic-first invariants enforced here:
  - No writes to campaigns, fingerprints, events, or observations.
  - AI outputs are stored in ai_outputs; result_summary_json retained for polling.
  - AI audit records store metadata only — no prompt text, no response text.
  - get_ai_backend() is imported here so tests can monkeypatch
    'app.jobs.runner.get_ai_backend' without touching the router.
  - AI outputs are never used as prompt inputs (§3, §10 Rule 1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
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
            logger.debug("run_campaign_summary_job: job %s not in pending state, skipping", job_id)
            return
        job = repo.get_job(job_id)

    if job is None:
        logger.warning("run_campaign_summary_job: job %s not found after start", job_id)
        return

    campaign_id: str = job.get("resource_id") or ""
    triggered_by: str | None = job.get("triggered_by")

    # Fetch campaign data — read-only session.
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

    # Build prompt.
    prompt_data = build_campaign_summary_prompt(campaign, fingerprint, observations)
    user_prompt = prompt_data["user_prompt"]
    prompt_hash = _prompt_hash(user_prompt)
    payload_bytes = len(user_prompt.encode("utf-8"))
    data_quality_score = _compute_data_quality_score(campaign, fingerprint, observations)

    # Acquire backend — may raise AIBackendError if misconfigured.
    t0_call = time.monotonic()
    try:
        backend = get_ai_backend()
    except AIBackendError as exc:
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        _write_audit_log_safe(
            job_id=job_id,
            output_id=None,
            triggered_by=triggered_by,
            backend=settings.AI_BACKEND,
            model_name="unknown",
            operation_type="campaign_summary",
            resource_type="campaign",
            resource_id=campaign_id,
            payload_bytes=payload_bytes,
            response_bytes=0,
            latency_ms=call_latency_ms,
            status="failure",
            error_type="AIBackendError",
        )
        _fail_job_safe(job_id, str(exc))
        return

    # Call AI backend.
    try:
        raw_output = backend.generate(user_prompt)
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        response_bytes = len(raw_output.encode("utf-8"))
        call_status = "success"
        call_error_type = None
    except AIDisabledError as exc:
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        _write_audit_log_safe(
            job_id=job_id,
            output_id=None,
            triggered_by=triggered_by,
            backend=settings.AI_BACKEND,
            model_name=backend.model_name,
            operation_type="campaign_summary",
            resource_type="campaign",
            resource_id=campaign_id,
            payload_bytes=payload_bytes,
            response_bytes=0,
            latency_ms=call_latency_ms,
            status="disabled",
            error_type="AIDisabledError",
        )
        _fail_job_safe(job_id, str(exc))
        return
    except AIBackendUnavailableError as exc:
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        _write_audit_log_safe(
            job_id=job_id,
            output_id=None,
            triggered_by=triggered_by,
            backend=settings.AI_BACKEND,
            model_name=backend.model_name,
            operation_type="campaign_summary",
            resource_type="campaign",
            resource_id=campaign_id,
            payload_bytes=payload_bytes,
            response_bytes=0,
            latency_ms=call_latency_ms,
            status="unavailable",
            error_type="AIBackendUnavailableError",
        )
        _fail_job_safe(job_id, str(exc))
        return
    except AIBackendError as exc:
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        _write_audit_log_safe(
            job_id=job_id,
            output_id=None,
            triggered_by=triggered_by,
            backend=settings.AI_BACKEND,
            model_name=backend.model_name,
            operation_type="campaign_summary",
            resource_type="campaign",
            resource_id=campaign_id,
            payload_bytes=payload_bytes,
            response_bytes=0,
            latency_ms=call_latency_ms,
            status="failure",
            error_type="AIBackendError",
        )
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

    # Write ai_output BEFORE completing the job.
    output_id = str(uuid.uuid4())
    with get_session() as session:
        repo = EventRepository(session)
        repo.create_ai_output(
            output_id=output_id,
            job_id=job_id,
            output_type="campaign_summary",
            resource_type="campaign",
            resource_id=campaign_id,
            content=None if is_rejected else validated_text,
            backend=settings.AI_BACKEND,
            model_name=backend.model_name,
            prompt_hash=prompt_hash,
            payload_bytes=payload_bytes,
            source_records_json=prompt_data["source_records"],
            safety_flags_json=prompt_data["safety_flags"],
            rejected=is_rejected,
            rejection_reason=rejection_reason,
            truncated=is_truncated,
            data_quality_score=data_quality_score,
            generated_at=generated_at,
            triggered_by=triggered_by,
        )

    # Write audit log with output_id now known.
    _write_audit_log_safe(
        job_id=job_id,
        output_id=output_id,
        triggered_by=triggered_by,
        backend=settings.AI_BACKEND,
        model_name=backend.model_name,
        operation_type="campaign_summary",
        resource_type="campaign",
        resource_id=campaign_id,
        payload_bytes=payload_bytes,
        response_bytes=response_bytes,
        latency_ms=call_latency_ms,
        status=call_status,
        error_type=call_error_type,
    )

    with get_session() as session:
        repo = EventRepository(session)
        repo.complete_job(
            job_id,
            result_summary_json=result,
            backend_metadata_json=backend_meta,
            ai_output_id=output_id,
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

    triggered_by: str | None = job.get("triggered_by")

    # Parse max_campaigns from backend_metadata_json.
    max_campaigns = 10
    if job.get("backend_metadata_json"):
        try:
            meta = json.loads(job["backend_metadata_json"])
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
    user_prompt = prompt_data["user_prompt"]
    prompt_hash = _prompt_hash(user_prompt)
    payload_bytes = len(user_prompt.encode("utf-8"))
    data_quality_score = round(min(len(campaigns) / 10.0, 1.0), 3)

    t0_call = time.monotonic()
    try:
        backend = get_ai_backend()
    except AIBackendError as exc:
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        _write_audit_log_safe(
            job_id=job_id,
            output_id=None,
            triggered_by=triggered_by,
            backend=settings.AI_BACKEND,
            model_name="unknown",
            operation_type="campaign_brief",
            resource_type=None,
            resource_id=None,
            payload_bytes=payload_bytes,
            response_bytes=0,
            latency_ms=call_latency_ms,
            status="failure",
            error_type="AIBackendError",
        )
        _fail_job_safe(job_id, str(exc))
        return

    try:
        raw_output = backend.generate(user_prompt)
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        response_bytes = len(raw_output.encode("utf-8"))
        call_status = "success"
        call_error_type = None
    except AIDisabledError as exc:
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        _write_audit_log_safe(
            job_id=job_id,
            output_id=None,
            triggered_by=triggered_by,
            backend=settings.AI_BACKEND,
            model_name=backend.model_name,
            operation_type="campaign_brief",
            resource_type=None,
            resource_id=None,
            payload_bytes=payload_bytes,
            response_bytes=0,
            latency_ms=call_latency_ms,
            status="disabled",
            error_type="AIDisabledError",
        )
        _fail_job_safe(job_id, str(exc))
        return
    except AIBackendUnavailableError as exc:
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        _write_audit_log_safe(
            job_id=job_id,
            output_id=None,
            triggered_by=triggered_by,
            backend=settings.AI_BACKEND,
            model_name=backend.model_name,
            operation_type="campaign_brief",
            resource_type=None,
            resource_id=None,
            payload_bytes=payload_bytes,
            response_bytes=0,
            latency_ms=call_latency_ms,
            status="unavailable",
            error_type="AIBackendUnavailableError",
        )
        _fail_job_safe(job_id, str(exc))
        return
    except AIBackendError as exc:
        call_latency_ms = int((time.monotonic() - t0_call) * 1000)
        _write_audit_log_safe(
            job_id=job_id,
            output_id=None,
            triggered_by=triggered_by,
            backend=settings.AI_BACKEND,
            model_name=backend.model_name,
            operation_type="campaign_brief",
            resource_type=None,
            resource_id=None,
            payload_bytes=payload_bytes,
            response_bytes=0,
            latency_ms=call_latency_ms,
            status="failure",
            error_type="AIBackendError",
        )
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

    output_id = str(uuid.uuid4())
    with get_session() as session:
        repo = EventRepository(session)
        repo.create_ai_output(
            output_id=output_id,
            job_id=job_id,
            output_type="campaign_brief",
            resource_type=None,
            resource_id=None,
            content=None if is_rejected else validated_text,
            backend=settings.AI_BACKEND,
            model_name=backend.model_name,
            prompt_hash=prompt_hash,
            payload_bytes=payload_bytes,
            source_records_json=prompt_data["source_records"],
            safety_flags_json=None,
            rejected=is_rejected,
            rejection_reason=rejection_reason,
            truncated=is_truncated,
            data_quality_score=data_quality_score,
            generated_at=generated_at,
            triggered_by=triggered_by,
        )

    _write_audit_log_safe(
        job_id=job_id,
        output_id=output_id,
        triggered_by=triggered_by,
        backend=settings.AI_BACKEND,
        model_name=backend.model_name,
        operation_type="campaign_brief",
        resource_type=None,
        resource_id=None,
        payload_bytes=payload_bytes,
        response_bytes=response_bytes,
        latency_ms=call_latency_ms,
        status=call_status,
        error_type=call_error_type,
    )

    with get_session() as session:
        repo = EventRepository(session)
        repo.complete_job(
            job_id,
            result_summary_json=result,
            backend_metadata_json=backend_meta,
            ai_output_id=output_id,
        )


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------


def _prompt_hash(prompt_text: str) -> str:
    """Return SHA-256 hex digest of the prompt. No prompt content is stored."""
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def _compute_data_quality_score(
    campaign: dict,
    fingerprint: dict | None,
    observations: list,
) -> float:
    """Composite data quality score: confidence 40%, obs 30%, fp 20%, recency 10%."""
    confidence = float(campaign.get("confidence") or 0.5)
    obs_score = min(len(observations) / 10.0, 1.0)
    fp_score = 0.0
    if fingerprint:
        dims = [
            "timing_features",
            "sequence_features",
            "protocol_features",
            "credential_features",
            "target_features",
        ]
        present = sum(1 for d in dims if fingerprint.get(d))
        fp_score = present / 5.0
    recency = 1.0 if observations else 0.0
    score = confidence * 0.4 + obs_score * 0.3 + fp_score * 0.2 + recency * 0.1
    return round(score, 3)


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------


def _write_audit_log_safe(
    *,
    job_id: str | None,
    output_id: str | None,
    triggered_by: str | None,
    backend: str,
    model_name: str,
    operation_type: str,
    resource_type: str | None,
    resource_id: str | None,
    payload_bytes: int,
    response_bytes: int,
    latency_ms: int,
    status: str,
    error_type: str | None,
) -> None:
    """Write an AI audit record. Failures are logged but never propagated."""
    try:
        with get_session() as session:
            repo = EventRepository(session)
            repo.create_ai_audit_log(
                job_id=job_id,
                output_id=output_id,
                triggered_by=triggered_by,
                backend=backend,
                model_name=model_name,
                operation_type=operation_type,
                resource_type=resource_type,
                resource_id=resource_id,
                payload_bytes=payload_bytes,
                response_bytes=response_bytes,
                latency_ms=latency_ms,
                status=status,
                error_type=error_type,
            )
    except Exception:
        logger.exception("Failed to write AI audit log job_id=%s status=%s", job_id, status)


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
