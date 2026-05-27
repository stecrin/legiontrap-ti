"""Background fingerprint computation tasks — Phase 6 PR A1 refactor.

Provides schedule_fingerprint_if_not_pending(), the only entry point called
from the ingest router. All fingerprint computation runs asynchronously via
FastAPI BackgroundTasks — never in the synchronous ingest request path (§12.5).

Deduplication model (Phase 6):
  A processing_jobs row with deduplication_key='fingerprint:{ip}' replaces
  the module-level _pending set from Phase 4. The DB-backed approach survives
  process restarts: a pending/running fingerprint job persists across restarts,
  preventing duplicate recomputation after a crash or redeploy.

  Race condition: between the SELECT (no active job found) and the INSERT,
  another request could create a duplicate job. This is inherent in any
  optimistic check-then-insert pattern without a DB-level unique constraint.
  The consequence — two fingerprint computations for the same IP — is harmless
  because fingerprint computation is idempotent (upsert semantics). The
  previous threading.Lock was correct for single-process deployments; the DB
  check is correct for multi-process deployments.

Phase 6 Group B additions:
  - _compute_and_store() appends a fingerprint_history row on each computation.
  - _run_campaign_clustering() updates representative_fingerprint_json on the
    assigned campaign after a successful association.
  - _build_representative_fp_json() packages feature columns for the cache;
    tool_signals is excluded (§11.2).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)


def _build_representative_fp_json(fp: dict[str, Any]) -> str:
    """Serialize fingerprint feature columns to JSON for representative_fingerprint_json.

    tool_signals is excluded — it is not a stability-relevant dimension and
    may contain tool-name strings that could encode identifiable information
    across versions (§11.2).
    """
    return json.dumps(
        {
            "timing_features": fp.get("timing_features"),
            "sequence_features": fp.get("sequence_features"),
            "protocol_features": fp.get("protocol_features"),
            "credential_features": fp.get("credential_features"),
            "target_features": fp.get("target_features"),
            "confidence": fp.get("confidence"),
        }
    )


def schedule_fingerprint_if_not_pending(ip: str, background_tasks: BackgroundTasks) -> None:
    """Enqueue a fingerprint computation job for ip unless one is already active.

    Creates a processing_jobs row in 'pending' state before enqueuing the
    background task. If a pending or running job for this ip already exists
    (by deduplication_key), the new request is silently dropped.
    """
    from app.db.connection import get_session
    from app.db.repository import EventRepository

    dedup_key = f"fingerprint:{ip}"
    now = datetime.now(UTC).isoformat()
    job_id: str | None = None

    try:
        with get_session() as session:
            repo = EventRepository(session)
            existing = repo.get_active_job_by_dedup_key(dedup_key)
            if existing is not None:
                return
            job = repo.create_job(
                job_type="fingerprint_clustering",
                triggered_by="system:ingest",
                resource_type="ip",
                resource_id=ip,
                deduplication_key=dedup_key,
                created_at=now,
            )
            job_id = job["id"]
    except Exception:
        logger.exception("Failed to create fingerprint job for ip=%s", ip)
        return

    background_tasks.add_task(_run_fingerprint_task, ip, job_id)


def _run_fingerprint_task(ip: str, job_id: str) -> None:
    """Execute fingerprint computation for ip in a background context.

    Manages job lifecycle: pending → running → completed | failed.
    Failures are logged but do not propagate — a fingerprint failure must
    never surface as an ingest error to the sensor (§3.3 / §11).
    """
    from app.db.connection import get_session
    from app.db.repository import EventRepository

    try:
        with get_session() as session:
            repo = EventRepository(session)
            started = repo.start_job(job_id, started_at=datetime.now(UTC).isoformat())
            if not started:
                # Job was cancelled or already started by another executor.
                logger.debug("Fingerprint job %s not in pending state, skipping", job_id)
                return
        _compute_and_store(ip)
        with get_session() as session:
            repo = EventRepository(session)
            repo.complete_job(job_id, result_summary_json={"ip": ip, "outcome": "computed"})
    except Exception:
        logger.exception("Fingerprint computation failed for ip=%s job_id=%s", ip, job_id)
        try:
            with get_session() as session:
                repo = EventRepository(session)
                repo.fail_job(job_id, error_message="Fingerprint computation error")
        except Exception:
            logger.exception("Failed to record fingerprint job failure for job_id=%s", job_id)


def _compute_and_store(ip: str) -> None:
    """Fetch events, compute fingerprint, write to behavioral_fingerprints.

    Appends a fingerprint_history row in the same session as the upsert so
    the history write is atomic with the fingerprint update (§11.2, §11.3).

    After a successful fingerprint commit, triggers campaign clustering when
    the fingerprint meets the minimum confidence threshold (§12.6). The
    fingerprint session commits before clustering — a clustering failure
    cannot roll back the stored fingerprint.
    """
    from app.db.connection import get_session
    from app.db.repository import EventRepository
    from app.intelligence.constants import FINGERPRINT_VERSION
    from app.intelligence.fingerprint import build_fingerprint

    fp_confidence: float = 0.0

    with get_session() as session:
        repo = EventRepository(session)
        events = repo.get_events_for_fingerprint(ip)
        if not events:
            return
        fp = build_fingerprint(events)
        computed_at = datetime.now(UTC).isoformat()
        repo.upsert_behavioral_fingerprint(
            ip=ip,
            fingerprint_version=FINGERPRINT_VERSION,
            computed_at=computed_at,
            event_count=fp["event_count"],
            timing_features=fp["timing_features"],
            sequence_features=fp["sequence_features"],
            protocol_features=fp["protocol_features"],
            credential_features=fp["credential_features"],
            target_features=fp["target_features"],
            tool_signals=fp["tool_signals"],
            confidence=fp["confidence"],
        )
        stored = repo.get_behavioral_fingerprint(ip)
        member = repo.get_campaign_member_by_ip(ip)
        if stored is not None:
            repo.insert_fingerprint_history(
                fingerprint_id=stored["id"],
                source_ip=ip,
                campaign_id=member["campaign_id"] if member is not None else None,
                fingerprint_version=FINGERPRINT_VERSION,
                computed_at=computed_at,
                event_count_at_computation=fp["event_count"],
                confidence=fp["confidence"],
                timing_features=fp["timing_features"],
                sequence_features=fp["sequence_features"],
                protocol_features=fp["protocol_features"],
                credential_features=fp["credential_features"],
                target_features=fp["target_features"],
            )
        fp_confidence = fp["confidence"]

    if fp_confidence >= 0.20:
        _run_campaign_clustering(ip)


def _run_campaign_clustering(ip: str) -> None:
    """Run campaign assignment for ip in a fresh session.

    After assignment:
      - Updates representative_fingerprint_json on the campaign (fast-path cache, §13.2).
      - Triggers behavioral stability refresh for the assigned campaign in a
        separate failure domain — a stability failure must never mask a
        clustering success.

    Failures are logged but do not propagate — a clustering failure must
    never surface as a fingerprint-computation error (§3.3 / §11).
    """
    assigned_campaign_id: str | None = None

    try:
        from app.db.connection import get_session
        from app.db.repository import EventRepository
        from app.intelligence.clustering import assign_to_campaign

        with get_session() as session:
            repo = EventRepository(session)
            stored_fp = repo.get_behavioral_fingerprint(ip)
            if stored_fp is None:
                return
            decision = assign_to_campaign(ip, stored_fp, repo)
            if decision.campaign_id is not None:
                rep_fp_json = _build_representative_fp_json(stored_fp)
                repo.update_representative_fingerprint(decision.campaign_id, rep_fp_json)
                assigned_campaign_id = decision.campaign_id
    except Exception:
        logger.exception("Campaign clustering failed for ip=%s", ip)

    if assigned_campaign_id is not None:
        try:
            from app.intelligence.stability import refresh_campaign_stability

            refresh_campaign_stability(assigned_campaign_id)
        except Exception:
            logger.exception("Stability refresh failed for campaign_id=%s", assigned_campaign_id)
