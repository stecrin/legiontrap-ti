"""Background fingerprint computation tasks.

Provides schedule_fingerprint_if_not_pending(), the only entry point called
from the ingest router.  All fingerprint computation runs asynchronously via
FastAPI BackgroundTasks — never in the synchronous ingest request path (§12.5).

Deduplication model (§12.5):
  A module-level set tracks IPs whose fingerprint tasks are pending or
  in-flight.  A threading.Lock makes the check-and-add atomic, which is
  correct for FastAPI's single-process BackgroundTasks execution model.

  This design is intentionally scoped to single-process deployments (the
  Phase 4 target environment with BackgroundTasks).  Multi-process worker
  deployments (Gunicorn with multiple uvicorn workers) would need a shared
  coordination store (Redis, DB advisory locks) — deferred to Phase 5/6
  when task volume justifies the operational overhead (§11: No async worker
  infrastructure unless task backlog is measured).
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

_pending: set[str] = set()
_pending_lock = threading.Lock()


def schedule_fingerprint_if_not_pending(ip: str, background_tasks: BackgroundTasks) -> None:
    """Enqueue a fingerprint computation task for ip unless one is already queued.

    Thread-safe: the check-and-add is atomic under _pending_lock.
    If an existing task is in-flight for this ip, the new request is silently
    dropped — the in-flight task will read all events committed so far when
    it executes.
    """
    with _pending_lock:
        if ip in _pending:
            return
        _pending.add(ip)
    background_tasks.add_task(_run_fingerprint_task, ip)


def _run_fingerprint_task(ip: str) -> None:
    """Execute fingerprint computation for ip in a background context.

    Failures are logged but do not propagate — a fingerprint failure must
    never surface as an ingest error to the sensor (§3.3 / §11).
    The ip is removed from _pending in the finally block regardless of outcome.
    """
    try:
        _compute_and_store(ip)
    except Exception:
        logger.exception("Fingerprint computation failed for ip=%s", ip)
    finally:
        with _pending_lock:
            _pending.discard(ip)


def _compute_and_store(ip: str) -> None:
    """Fetch events, compute fingerprint, write to behavioral_fingerprints."""
    from app.db.connection import get_session
    from app.db.repository import EventRepository
    from app.intelligence.constants import FINGERPRINT_VERSION
    from app.intelligence.fingerprint import build_fingerprint

    with get_session() as session:
        repo = EventRepository(session)
        events = repo.get_events_for_fingerprint(ip)
        if not events:
            return
        fp = build_fingerprint(events)
        repo.upsert_behavioral_fingerprint(
            ip=ip,
            fingerprint_version=FINGERPRINT_VERSION,
            computed_at=datetime.now(UTC).isoformat(),
            event_count=fp["event_count"],
            timing_features=fp["timing_features"],
            sequence_features=fp["sequence_features"],
            protocol_features=fp["protocol_features"],
            credential_features=fp["credential_features"],
            target_features=fp["target_features"],
            tool_signals=fp["tool_signals"],
            confidence=fp["confidence"],
        )
