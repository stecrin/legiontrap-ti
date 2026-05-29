"""DB tests for AlertRepository — Phase 7 Group A.

Tests hit a real in-memory SQLite database via the db_session fixture.

Coverage:
  - has_open_alert returns False when no alerts exist
  - insert_alert creates a row
  - has_open_alert returns True after insert
  - has_open_alert returns False for a different dimension
  - acknowledge_alert sets acknowledged_at
  - acknowledged alert does not block has_open_alert (returns False after ack)
  - list_alerts returns unacknowledged by default
  - list_alerts with include_acknowledged=True returns all
  - list_alerts filtered by campaign_id
  - get_alert returns None for unknown ID
  - NULL dimension (composite) vs named dimension are independent dedup buckets
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.repository import EventRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_campaign(session) -> str:
    cid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    EventRepository(session).create_campaign(
        campaign_id=cid,
        name="test-campaign",
        status="active",
        confidence=0.7,
        first_seen=now,
        last_seen=now,
        member_ip_count=1,
        created_at=now,
        updated_at=now,
    )
    session.flush()
    return cid


_SNAPSHOT = {"status": "ok", "composite_score": 0.40, "timing_stability": 0.30}


def _insert_alert(repo, cid: str, dimension: str | None = None) -> dict:
    return repo.insert_alert(
        campaign_id=cid,
        alert_type="composite_drift" if dimension is None else "dimension_drift",
        dimension=dimension,
        threshold_configured=0.65,
        observed_value=0.40,
        stability_snapshot=_SNAPSHOT,
    )


# ---------------------------------------------------------------------------
# has_open_alert
# ---------------------------------------------------------------------------


def test_has_open_alert_false_when_no_alerts(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    assert repo.has_open_alert(cid, None) is False
    assert repo.has_open_alert(cid, "timing") is False


def test_has_open_alert_true_after_insert_composite(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    _insert_alert(repo, cid, dimension=None)
    db_session.flush()
    assert repo.has_open_alert(cid, None) is True


def test_has_open_alert_true_after_insert_dimension(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    _insert_alert(repo, cid, dimension="timing")
    db_session.flush()
    assert repo.has_open_alert(cid, "timing") is True


def test_has_open_alert_false_for_different_dimension(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    _insert_alert(repo, cid, dimension="timing")
    db_session.flush()
    assert repo.has_open_alert(cid, "sequence") is False
    assert repo.has_open_alert(cid, None) is False


def test_has_open_alert_false_for_different_campaign(db_session):
    cid1 = _create_campaign(db_session)
    cid2 = _create_campaign(db_session)
    repo = EventRepository(db_session)
    _insert_alert(repo, cid1, dimension=None)
    db_session.flush()
    assert repo.has_open_alert(cid2, None) is False


# ---------------------------------------------------------------------------
# acknowledge_alert
# ---------------------------------------------------------------------------


def test_acknowledge_alert_sets_acknowledged_at(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    alert = _insert_alert(repo, cid)
    db_session.flush()

    updated = repo.acknowledge_alert(alert["id"], notes="looks like adaptation")
    assert updated is not None
    assert updated["acknowledged_at"] is not None
    assert updated["acknowledged_notes"] == "looks like adaptation"
    assert updated["acknowledged"] is True


def test_acknowledged_alert_does_not_block_open_check(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    alert = _insert_alert(repo, cid, dimension=None)
    db_session.flush()

    repo.acknowledge_alert(alert["id"])
    db_session.flush()

    # After acknowledgement, has_open_alert should return False
    assert repo.has_open_alert(cid, None) is False


def test_acknowledge_alert_returns_none_for_unknown_id(db_session):
    repo = EventRepository(db_session)
    result = repo.acknowledge_alert(str(uuid.uuid4()))
    assert result is None


# ---------------------------------------------------------------------------
# list_alerts
# ---------------------------------------------------------------------------


def test_list_alerts_returns_only_unacknowledged_by_default(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    open_alert = _insert_alert(repo, cid, dimension="timing")
    acked_alert = _insert_alert(repo, cid, dimension="sequence")
    db_session.flush()

    repo.acknowledge_alert(acked_alert["id"])
    db_session.flush()

    alerts = repo.list_alerts()
    alert_ids = {a["id"] for a in alerts}
    assert open_alert["id"] in alert_ids
    assert acked_alert["id"] not in alert_ids


def test_list_alerts_include_acknowledged_returns_all(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    open_alert = _insert_alert(repo, cid, dimension="timing")
    acked_alert = _insert_alert(repo, cid, dimension="sequence")
    db_session.flush()

    repo.acknowledge_alert(acked_alert["id"])
    db_session.flush()

    alerts = repo.list_alerts(include_acknowledged=True)
    alert_ids = {a["id"] for a in alerts}
    assert open_alert["id"] in alert_ids
    assert acked_alert["id"] in alert_ids


def test_list_alerts_filtered_by_campaign_id(db_session):
    cid1 = _create_campaign(db_session)
    cid2 = _create_campaign(db_session)
    repo = EventRepository(db_session)
    alert1 = _insert_alert(repo, cid1)
    alert2 = _insert_alert(repo, cid2)
    db_session.flush()

    alerts = repo.list_alerts(campaign_id=cid1)
    alert_ids = {a["id"] for a in alerts}
    assert alert1["id"] in alert_ids
    assert alert2["id"] not in alert_ids


# ---------------------------------------------------------------------------
# get_alert
# ---------------------------------------------------------------------------


def test_get_alert_returns_alert(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    alert = _insert_alert(repo, cid, dimension="protocol")
    db_session.flush()

    fetched = repo.get_alert(alert["id"])
    assert fetched is not None
    assert fetched["id"] == alert["id"]
    assert fetched["dimension"] == "protocol"


def test_get_alert_returns_none_for_unknown_id(db_session):
    repo = EventRepository(db_session)
    assert repo.get_alert(str(uuid.uuid4())) is None


# ---------------------------------------------------------------------------
# composite vs dimension independence
# ---------------------------------------------------------------------------


def test_composite_and_dimension_are_independent_dedup_buckets(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    _insert_alert(repo, cid, dimension=None)  # composite
    _insert_alert(repo, cid, dimension="timing")  # dimension
    db_session.flush()

    assert repo.has_open_alert(cid, None) is True
    assert repo.has_open_alert(cid, "timing") is True
    assert repo.has_open_alert(cid, "sequence") is False
