"""Tests for campaign lifecycle transition repository methods and service function.

Uses the db_session fixture from tests/db/conftest.py for isolated in-memory
SQLite databases.  All timestamps are fixed so transitions are deterministic.

Lifecycle rules under test:
  active/reactivated → dormant    when last_seen  < now - CAMPAIGN_ACTIVE_DAYS  (7)
  dormant            → historical when dormant_since < now - CAMPAIGN_DORMANT_DAYS (90)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.db.repository import EventRepository
from app.intelligence.constants import CAMPAIGN_ACTIVE_DAYS, CAMPAIGN_DORMANT_DAYS
from app.intelligence.lifecycle import run_lifecycle_transitions

# Fixed evaluation point — all relative dates are anchored here.
_NOW = datetime(2026, 5, 26, 0, 0, 0, tzinfo=UTC)

# Computed cutoffs — used directly in repository-level tests so they reflect the
# actual thresholds rather than the unconditional present moment.
_ACTIVE_CUTOFF = (_NOW - timedelta(days=CAMPAIGN_ACTIVE_DAYS)).isoformat()
_HISTORICAL_CUTOFF = (_NOW - timedelta(days=CAMPAIGN_DORMANT_DAYS)).isoformat()

# Timestamps that are definitively old / definitively recent relative to the cutoffs.
_OLD_LAST_SEEN = (_NOW - timedelta(days=CAMPAIGN_ACTIVE_DAYS + 1)).isoformat()
_RECENT_LAST_SEEN = (_NOW - timedelta(days=CAMPAIGN_ACTIVE_DAYS - 1)).isoformat()
_OLD_DORMANT_SINCE = (_NOW - timedelta(days=CAMPAIGN_DORMANT_DAYS + 1)).isoformat()
_RECENT_DORMANT_SINCE = (_NOW - timedelta(days=CAMPAIGN_DORMANT_DAYS - 1)).isoformat()

# Boundary: exactly at the threshold — should NOT trigger (strict less-than).
_BOUNDARY_LAST_SEEN = _ACTIVE_CUTOFF
_BOUNDARY_DORMANT_SINCE = _HISTORICAL_CUTOFF

_BASE_TS = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_campaign(
    session,
    status: str = "active",
    last_seen: str = _OLD_LAST_SEEN,
    dormant_since: str | None = None,
) -> str:
    cid = str(uuid.uuid4())
    session.execute(
        text("""
            INSERT INTO campaigns
                (id, name, status, confidence, first_seen, last_seen,
                 dormant_since, reactivation_count, member_ip_count,
                 attack_tactic_dist, top_target_ports, notes,
                 created_at, updated_at)
            VALUES
                (:id, :name, :status, 0.7, :base_ts, :last_seen,
                 :dormant_since, 0, 0, NULL, NULL, NULL,
                 :base_ts, :base_ts)
        """),
        {
            "id": cid,
            "name": f"TEST-{cid[:8]}",
            "status": status,
            "base_ts": _BASE_TS,
            "last_seen": last_seen,
            "dormant_since": dormant_since,
        },
    )
    session.flush()
    return cid


def _get_status(session, cid: str) -> str:
    row = session.execute(
        text("SELECT status FROM campaigns WHERE id = :id"), {"id": cid}
    ).fetchone()
    return row[0]


def _get_dormant_since(session, cid: str) -> str | None:
    row = session.execute(
        text("SELECT dormant_since FROM campaigns WHERE id = :id"), {"id": cid}
    ).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Repository method: transition_active_to_dormant
# ---------------------------------------------------------------------------


def test_active_old_last_seen_becomes_dormant(db_session):
    cid = _insert_campaign(db_session, status="active", last_seen=_OLD_LAST_SEEN)
    repo = EventRepository(db_session)
    count = repo.transition_active_to_dormant(
        last_seen_cutoff=_NOW.isoformat(),
        dormant_since=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 1
    assert _get_status(db_session, cid) == "dormant"


def test_active_old_last_seen_dormant_since_set(db_session):
    cid = _insert_campaign(db_session, status="active", last_seen=_OLD_LAST_SEEN)
    now_str = _NOW.isoformat()
    EventRepository(db_session).transition_active_to_dormant(
        last_seen_cutoff=now_str,
        dormant_since=now_str,
        updated_at=now_str,
    )
    db_session.flush()
    assert _get_dormant_since(db_session, cid) == now_str


def test_active_recent_last_seen_stays_active(db_session):
    cid = _insert_campaign(db_session, status="active", last_seen=_RECENT_LAST_SEEN)
    count = EventRepository(db_session).transition_active_to_dormant(
        last_seen_cutoff=_ACTIVE_CUTOFF,
        dormant_since=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 0
    assert _get_status(db_session, cid) == "active"


def test_active_at_boundary_stays_active(db_session):
    """last_seen == cutoff is NOT transitioned (strictly less-than)."""
    cid = _insert_campaign(db_session, status="active", last_seen=_BOUNDARY_LAST_SEEN)
    count = EventRepository(db_session).transition_active_to_dormant(
        last_seen_cutoff=_BOUNDARY_LAST_SEEN,
        dormant_since=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 0
    assert _get_status(db_session, cid) == "active"


def test_reactivated_old_last_seen_becomes_dormant(db_session):
    cid = _insert_campaign(db_session, status="reactivated", last_seen=_OLD_LAST_SEEN)
    count = EventRepository(db_session).transition_active_to_dormant(
        last_seen_cutoff=_NOW.isoformat(),
        dormant_since=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 1
    assert _get_status(db_session, cid) == "dormant"


def test_reactivated_recent_last_seen_stays_reactivated(db_session):
    cid = _insert_campaign(db_session, status="reactivated", last_seen=_RECENT_LAST_SEEN)
    count = EventRepository(db_session).transition_active_to_dormant(
        last_seen_cutoff=_ACTIVE_CUTOFF,
        dormant_since=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 0
    assert _get_status(db_session, cid) == "reactivated"


def test_dormant_not_touched_by_active_to_dormant(db_session):
    """An already-dormant campaign must not have its dormant_since overwritten."""
    original_ds = _OLD_DORMANT_SINCE
    cid = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=original_ds,
    )
    EventRepository(db_session).transition_active_to_dormant(
        last_seen_cutoff=_NOW.isoformat(),
        dormant_since=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert _get_status(db_session, cid) == "dormant"
    assert _get_dormant_since(db_session, cid) == original_ds


def test_historical_not_touched_by_active_to_dormant(db_session):
    cid = _insert_campaign(db_session, status="historical", last_seen=_OLD_LAST_SEEN)
    count = EventRepository(db_session).transition_active_to_dormant(
        last_seen_cutoff=_NOW.isoformat(),
        dormant_since=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 0
    assert _get_status(db_session, cid) == "historical"


def test_active_to_dormant_returns_correct_count_multiple(db_session):
    _insert_campaign(db_session, status="active", last_seen=_OLD_LAST_SEEN)
    _insert_campaign(db_session, status="reactivated", last_seen=_OLD_LAST_SEEN)
    _insert_campaign(db_session, status="active", last_seen=_RECENT_LAST_SEEN)
    count = EventRepository(db_session).transition_active_to_dormant(
        last_seen_cutoff=_ACTIVE_CUTOFF,
        dormant_since=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 2


# ---------------------------------------------------------------------------
# Repository method: transition_dormant_to_historical
# ---------------------------------------------------------------------------


def test_dormant_old_dormant_since_becomes_historical(db_session):
    cid = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_OLD_DORMANT_SINCE,
    )
    count = EventRepository(db_session).transition_dormant_to_historical(
        dormant_since_cutoff=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 1
    assert _get_status(db_session, cid) == "historical"


def test_dormant_old_dormant_since_preserves_dormant_since(db_session):
    """dormant_since is kept on historical campaigns for audit trail."""
    cid = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_OLD_DORMANT_SINCE,
    )
    EventRepository(db_session).transition_dormant_to_historical(
        dormant_since_cutoff=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert _get_dormant_since(db_session, cid) == _OLD_DORMANT_SINCE


def test_dormant_recent_dormant_since_stays_dormant(db_session):
    cid = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_RECENT_DORMANT_SINCE,
    )
    count = EventRepository(db_session).transition_dormant_to_historical(
        dormant_since_cutoff=_HISTORICAL_CUTOFF,
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 0
    assert _get_status(db_session, cid) == "dormant"


def test_dormant_at_boundary_stays_dormant(db_session):
    """dormant_since == cutoff is NOT transitioned (strictly less-than)."""
    cid = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_BOUNDARY_DORMANT_SINCE,
    )
    count = EventRepository(db_session).transition_dormant_to_historical(
        dormant_since_cutoff=_BOUNDARY_DORMANT_SINCE,
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 0
    assert _get_status(db_session, cid) == "dormant"


def test_active_not_touched_by_dormant_to_historical(db_session):
    cid = _insert_campaign(db_session, status="active", last_seen=_OLD_LAST_SEEN)
    count = EventRepository(db_session).transition_dormant_to_historical(
        dormant_since_cutoff=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 0
    assert _get_status(db_session, cid) == "active"


def test_dormant_null_dormant_since_not_touched(db_session):
    """Dormant campaign with NULL dormant_since (data integrity edge case) is skipped."""
    cid = _insert_campaign(
        db_session, status="dormant", last_seen=_OLD_LAST_SEEN, dormant_since=None
    )
    count = EventRepository(db_session).transition_dormant_to_historical(
        dormant_since_cutoff=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 0
    assert _get_status(db_session, cid) == "dormant"


def test_dormant_to_historical_returns_correct_count_multiple(db_session):
    _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_OLD_DORMANT_SINCE,
    )
    _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_OLD_DORMANT_SINCE,
    )
    _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_RECENT_DORMANT_SINCE,
    )
    count = EventRepository(db_session).transition_dormant_to_historical(
        dormant_since_cutoff=_HISTORICAL_CUTOFF,
        updated_at=_NOW.isoformat(),
    )
    db_session.flush()
    assert count == 2


# ---------------------------------------------------------------------------
# Service function: run_lifecycle_transitions
# ---------------------------------------------------------------------------


def test_service_transitions_active_to_dormant(db_session):
    cid = _insert_campaign(db_session, status="active", last_seen=_OLD_LAST_SEEN)
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    assert result["active_to_dormant"] == 1
    assert _get_status(db_session, cid) == "dormant"


def test_service_transitions_dormant_to_historical(db_session):
    cid = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_OLD_DORMANT_SINCE,
    )
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    assert result["dormant_to_historical"] == 1
    assert _get_status(db_session, cid) == "historical"


def test_service_result_has_required_keys(db_session):
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    assert "active_to_dormant" in result
    assert "dormant_to_historical" in result
    assert "evaluated_at" in result


def test_service_evaluated_at_matches_now(db_session):
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    assert result["evaluated_at"] == _NOW.isoformat()


def test_service_returns_zero_when_no_campaigns(db_session):
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    assert result["active_to_dormant"] == 0
    assert result["dormant_to_historical"] == 0


def test_service_newly_dormanted_not_immediately_historical(db_session):
    """A campaign that goes active→dormant in one run must not go dormant→historical
    in the same run (its dormant_since is just set to now)."""
    cid = _insert_campaign(db_session, status="active", last_seen=_OLD_LAST_SEEN)
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    assert result["active_to_dormant"] == 1
    assert result["dormant_to_historical"] == 0
    assert _get_status(db_session, cid) == "dormant"


def test_service_reactivated_follows_active_rule(db_session):
    cid = _insert_campaign(db_session, status="reactivated", last_seen=_OLD_LAST_SEEN)
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    assert result["active_to_dormant"] == 1
    assert _get_status(db_session, cid) == "dormant"


def test_service_recent_active_stays_active(db_session):
    cid = _insert_campaign(db_session, status="active", last_seen=_RECENT_LAST_SEEN)
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    assert result["active_to_dormant"] == 0
    assert _get_status(db_session, cid) == "active"


def test_service_recent_dormant_stays_dormant(db_session):
    cid = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_RECENT_DORMANT_SINCE,
    )
    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    assert result["dormant_to_historical"] == 0
    assert _get_status(db_session, cid) == "dormant"


def test_service_historical_untouched_by_both_passes(db_session):
    cid = _insert_campaign(db_session, status="historical", last_seen=_OLD_LAST_SEEN)
    repo = EventRepository(db_session)
    run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    assert _get_status(db_session, cid) == "historical"


def test_service_idempotent_second_run(db_session):
    """Running the job twice in a row produces the same final state."""
    _insert_campaign(db_session, status="active", last_seen=_OLD_LAST_SEEN)
    repo = EventRepository(db_session)
    run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    result2 = run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()
    assert result2["active_to_dormant"] == 0
    assert result2["dormant_to_historical"] == 0


def test_service_mixed_batch(db_session):
    """All four statuses in one batch — only eligible ones transition."""
    cid_active_old = _insert_campaign(db_session, status="active", last_seen=_OLD_LAST_SEEN)
    cid_active_new = _insert_campaign(db_session, status="active", last_seen=_RECENT_LAST_SEEN)
    cid_dormant_old = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_OLD_DORMANT_SINCE,
    )
    cid_dormant_new = _insert_campaign(
        db_session,
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_RECENT_DORMANT_SINCE,
    )
    cid_historical = _insert_campaign(db_session, status="historical", last_seen=_OLD_LAST_SEEN)

    repo = EventRepository(db_session)
    result = run_lifecycle_transitions(repo, now=_NOW)
    db_session.flush()

    assert result["active_to_dormant"] == 1
    assert result["dormant_to_historical"] == 1

    assert _get_status(db_session, cid_active_old) == "dormant"
    assert _get_status(db_session, cid_active_new) == "active"
    assert _get_status(db_session, cid_dormant_old) == "historical"
    assert _get_status(db_session, cid_dormant_new) == "dormant"
    assert _get_status(db_session, cid_historical) == "historical"
