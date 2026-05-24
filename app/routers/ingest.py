"""
POST /api/ingest — event ingestion pipeline for LegionTrap TI.

Pipeline stages per INGESTION_PIPELINE.md:
  1. Authentication  — API key only (no JWT for machine-to-machine sensors)
  2. Validation      — Pydantic RawEvent model (handled by FastAPI request parsing)
  3. Normalization   — extract_src_ip, normalize_event_type, parse_timestamp
  4. Deduplication   — event_exists() check before every write
  5. Persistence     — insert_raw_event + insert_event + upsert_source_ip (atomic)
  6. JSONL replica   — best-effort append; never fails ingest on error
  7. Receipt         — IngestReceipt response

Transaction model: one SQLAlchemy session per batch. Each event is wrapped
in a SAVEPOINT so a duplicate PK (race condition after the dedup check) rolls
back only that event without poisoning the session.

No FastAPI dependency on JWT flow. No async database code.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.connection import get_session
from app.db.repository import EventRepository
from app.limiter import limiter
from app.schemas.models import (
    HoneypotEvent,
    IngestError,
    IngestReceipt,
    IngestRequest,
)
from app.utils.event_utils import extract_src_ip, normalize_event_type, parse_timestamp

router = APIRouter()


def _require_api_key(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> None:
    """API-key-only guard. JWT is not appropriate for sensor-to-platform ingest."""
    if x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def _append_jsonl(event: HoneypotEvent) -> None:
    """
    Append the normalised event to the JSONL replica file.

    Best-effort: any I/O error is silently swallowed. The database write is the
    authoritative action; the JSONL file is a backwards-compatible replica.
    Per INGESTION_PIPELINE.md: only append AFTER a successful DB commit.
    """
    try:
        path = Path(settings.EVENTS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")
    except Exception:
        pass


@router.post("/api/ingest", response_model=IngestReceipt)
@limiter.limit("1000/minute")
def ingest_events(
    request: Request,
    body: IngestRequest,
    _: None = Depends(_require_api_key),
) -> IngestReceipt:
    """
    Ingest a batch of raw sensor events.

    Accepts 1–500 events per request. Processes each event independently:
    - Validation failures (unparseable timestamp) → rejected, error recorded
    - Duplicate event IDs → counted as duplicate, silently skipped
    - Successful writes → raw_events + events + source_ips in one savepoint

    The entire batch is processed in a single database session. A per-event
    SAVEPOINT handles the rare race condition where event_exists() returns
    False but the INSERT fails with IntegrityError (concurrent ingest from
    another process). Non-IntegrityError database errors propagate as HTTP 500.
    """
    batch_id = str(uuid.uuid4())
    ingested_at = datetime.now(UTC)
    accepted = rejected = duplicate = 0
    errors: list[IngestError] = []

    with get_session() as session:
        repo = EventRepository(session)

        for i, raw in enumerate(body.events):
            # Stage 3a: timestamp (rejection condition — required for time-series)
            ts = parse_timestamp(raw.ts)
            if ts is None:
                rejected += 1
                errors.append(IngestError(index=i, reason=f"unparseable timestamp: {raw.ts!r}"))
                continue

            # Stage 3b: normalization
            event_type = normalize_event_type(raw.type, raw.source)
            src_ip = extract_src_ip(raw.model_dump())

            # Stage 4: deduplication (optimistic check; SAVEPOINT handles races)
            if repo.event_exists(raw.id):
                duplicate += 1
                continue

            # Stage 5: persistence — atomic per-event via SAVEPOINT
            sp = session.begin_nested()
            try:
                repo.insert_raw_event(raw)
                honeypot = HoneypotEvent(
                    id=raw.id,
                    ts=ts,
                    ingested_at=ingested_at,
                    source=raw.source,
                    event_type=event_type,
                    src_ip=src_ip,
                )
                repo.insert_event(honeypot)
                if src_ip:
                    repo.upsert_source_ip(src_ip, ts)
                sp.commit()
            except IntegrityError:
                # Race: another process inserted this ID between the check and write.
                sp.rollback()
                duplicate += 1
                continue

            # Stage 6: JSONL replica (best-effort; only after DB commit)
            _append_jsonl(honeypot)
            accepted += 1

    return IngestReceipt(
        batch_id=batch_id,
        accepted=accepted,
        rejected=rejected,
        duplicate=duplicate,
        errors=errors,
    )
