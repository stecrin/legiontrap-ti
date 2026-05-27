"""Repository tests for CampaignRepository methods.

Uses the db_session fixture from tests/db/conftest.py for an isolated
in-memory SQLite database per test.  No HTTP, no application startup.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db.repository import EventRepository

_IP = "10.0.0.1"
_IP2 = "10.0.0.2"
_TS = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
_TS_STR = _TS.isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_source_ip(session, ip: str = _IP, ts: datetime = _TS) -> None:
    EventRepository(session).upsert_source_ip(ip, ts)
    session.flush()


def _insert_fingerprint(
    session,
    ip: str = _IP,
    confidence: float = 0.5,
    timing_features: str | None = None,
    sequence_features: str | None = None,
    target_features: str | None = None,
) -> None:
    EventRepository(session).upsert_behavioral_fingerprint(
        ip=ip,
        fingerprint_version=1,
        computed_at=_TS_STR,
        event_count=20,
        timing_features=timing_features,
        sequence_features=sequence_features,
        protocol_features=None,
        credential_features=None,
        target_features=target_features,
        tool_signals=None,
        confidence=confidence,
    )
    session.flush()


def _insert_campaign(
    session,
    campaign_id: str | None = None,
    status: str = "active",
    last_seen: str = _TS_STR,
) -> str:
    cid = campaign_id or str(uuid.uuid4())
    EventRepository(session).create_campaign(
        campaign_id=cid,
        name="TEST-WOLF-1",
        status=status,
        confidence=0.7,
        first_seen=_TS_STR,
        last_seen=last_seen,
        member_ip_count=0,
        created_at=_TS_STR,
        updated_at=_TS_STR,
    )
    session.flush()
    return cid


# ---------------------------------------------------------------------------
# create_campaign / get_campaign
# ---------------------------------------------------------------------------


def test_create_campaign_row_exists(db_session):
    cid = _insert_campaign(db_session)
    row = db_session.execute(
        text("SELECT id, name, status FROM campaigns WHERE id = :id"), {"id": cid}
    ).fetchone()
    assert row is not None
    assert row[0] == cid
    assert row[1] == "TEST-WOLF-1"
    assert row[2] == "active"


def test_get_campaign_returns_dict(db_session):
    cid = _insert_campaign(db_session)
    campaign = EventRepository(db_session).get_campaign(cid)
    assert campaign is not None
    assert isinstance(campaign, dict)
    assert campaign["id"] == cid


def test_get_campaign_unknown_returns_none(db_session):
    assert EventRepository(db_session).get_campaign(str(uuid.uuid4())) is None


def test_get_campaign_returned_keys(db_session):
    cid = _insert_campaign(db_session)
    campaign = EventRepository(db_session).get_campaign(cid)
    assert set(campaign.keys()) == {
        "id",
        "name",
        "status",
        "confidence",
        "first_seen",
        "last_seen",
        "dormant_since",
        "reactivation_count",
        "member_ip_count",
        "attack_tactic_dist",
        "top_target_ports",
        "notes",
        "created_at",
        "updated_at",
        "behavioral_stability_json",
    }


# ---------------------------------------------------------------------------
# add_campaign_member / get_campaign_member_by_ip
# ---------------------------------------------------------------------------


def test_add_campaign_member_row_exists(db_session):
    _insert_source_ip(db_session)
    cid = _insert_campaign(db_session)
    EventRepository(db_session).add_campaign_member(
        campaign_id=cid,
        source_ip=_IP,
        confidence=0.85,
        added_at=_TS_STR,
        last_active=_TS_STR,
    )
    db_session.flush()
    row = db_session.execute(
        text("SELECT campaign_id, source_ip FROM campaign_members WHERE source_ip = :ip"),
        {"ip": _IP},
    ).fetchone()
    assert row is not None
    assert row[0] == cid
    assert row[1] == _IP


def test_get_campaign_member_by_ip_returns_dict(db_session):
    _insert_source_ip(db_session)
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.add_campaign_member(cid, _IP, 0.85, _TS_STR, _TS_STR)
    db_session.flush()
    member = repo.get_campaign_member_by_ip(_IP)
    assert member is not None
    assert member["campaign_id"] == cid
    assert member["source_ip"] == _IP


def test_get_campaign_member_by_ip_unknown_returns_none(db_session):
    assert EventRepository(db_session).get_campaign_member_by_ip("1.2.3.4") is None


def test_get_campaign_member_confidence_stored(db_session):
    _insert_source_ip(db_session)
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.add_campaign_member(cid, _IP, 0.72, _TS_STR, _TS_STR)
    db_session.flush()
    member = repo.get_campaign_member_by_ip(_IP)
    assert abs(member["confidence"] - 0.72) < 1e-6


# ---------------------------------------------------------------------------
# update_campaign_member_last_active
# ---------------------------------------------------------------------------


def test_update_campaign_member_last_active(db_session):
    _insert_source_ip(db_session)
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.add_campaign_member(cid, _IP, 0.7, _TS_STR, _TS_STR)
    db_session.flush()

    new_ts = "2025-06-02T12:00:00+00:00"
    repo.update_campaign_member_last_active(cid, _IP, new_ts)
    db_session.flush()

    row = db_session.execute(
        text(
            "SELECT last_active FROM campaign_members WHERE campaign_id = :cid AND source_ip = :ip"
        ),
        {"cid": cid, "ip": _IP},
    ).fetchone()
    assert row[0] == new_ts


# ---------------------------------------------------------------------------
# insert_campaign_observation / get_campaign_observations
# ---------------------------------------------------------------------------


def test_insert_campaign_observation_creates_row(db_session):
    _insert_source_ip(db_session)
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.insert_campaign_observation(
        campaign_id=cid,
        source_ip=_IP,
        observed_at=_TS_STR,
        event_count=25,
        is_reactivation=False,
        dormancy_gap_days=None,
        notes=None,
    )
    db_session.flush()
    count = db_session.execute(
        text("SELECT COUNT(*) FROM campaign_observations WHERE campaign_id = :cid"),
        {"cid": cid},
    ).fetchone()[0]
    assert count == 1


def test_insert_campaign_observation_reactivation_flags(db_session):
    _insert_source_ip(db_session)
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.insert_campaign_observation(
        campaign_id=cid,
        source_ip=_IP,
        observed_at=_TS_STR,
        event_count=10,
        is_reactivation=True,
        dormancy_gap_days=45.5,
        notes='{"weighted_total":0.85}',
    )
    db_session.flush()

    obs = repo.get_campaign_observations(cid)
    assert len(obs) == 1
    assert obs[0]["is_reactivation"] is True
    assert abs(obs[0]["dormancy_gap_days"] - 45.5) < 1e-3
    assert obs[0]["notes"] == '{"weighted_total":0.85}'


def test_get_campaign_observations_ordered(db_session):
    _insert_source_ip(db_session)
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.insert_campaign_observation(cid, _IP, "2025-06-03T00:00:00+00:00", 5, False, None, None)
    repo.insert_campaign_observation(cid, _IP, "2025-06-01T00:00:00+00:00", 5, False, None, None)
    repo.insert_campaign_observation(cid, _IP, "2025-06-02T00:00:00+00:00", 5, False, None, None)
    db_session.flush()

    obs = repo.get_campaign_observations(cid)
    ts_list = [o["observed_at"] for o in obs]
    assert ts_list == sorted(ts_list)


# ---------------------------------------------------------------------------
# update_campaign_on_association
# ---------------------------------------------------------------------------


def test_update_campaign_on_association_increments_member_count(db_session):
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.update_campaign_on_association(
        campaign_id=cid,
        last_seen="2025-07-01T00:00:00+00:00",
        updated_at="2025-07-01T00:00:00+00:00",
        new_member_ip_count_delta=1,
        is_reactivation=False,
    )
    db_session.flush()
    c = repo.get_campaign(cid)
    assert c["member_ip_count"] == 1


def test_update_campaign_on_association_updates_last_seen(db_session):
    cid = _insert_campaign(db_session)
    new_ts = "2025-07-15T00:00:00+00:00"
    EventRepository(db_session).update_campaign_on_association(cid, new_ts, new_ts, 1, False)
    db_session.flush()
    c = EventRepository(db_session).get_campaign(cid)
    assert c["last_seen"] == new_ts


def test_update_campaign_on_association_reactivation_changes_status(db_session):
    cid = _insert_campaign(db_session, status="dormant")
    repo = EventRepository(db_session)
    repo.update_campaign_on_association(
        campaign_id=cid,
        last_seen=_TS_STR,
        updated_at=_TS_STR,
        new_member_ip_count_delta=1,
        is_reactivation=True,
    )
    db_session.flush()
    c = repo.get_campaign(cid)
    assert c["status"] == "reactivated"
    assert c["dormant_since"] is None
    assert c["reactivation_count"] == 1


def test_update_campaign_on_association_zero_delta_no_member_count_change(db_session):
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    # First add a member
    repo.update_campaign_on_association(cid, _TS_STR, _TS_STR, 1, False)
    db_session.flush()
    # Update without incrementing (existing member)
    repo.update_campaign_on_association(cid, _TS_STR, _TS_STR, 0, False)
    db_session.flush()
    c = repo.get_campaign(cid)
    assert c["member_ip_count"] == 1


# ---------------------------------------------------------------------------
# get_campaigns_for_clustering
# ---------------------------------------------------------------------------


def test_get_campaigns_for_clustering_empty_when_no_campaigns(db_session):
    results = EventRepository(db_session).get_campaigns_for_clustering()
    assert results == []


def test_get_campaigns_for_clustering_returns_active(db_session):
    _insert_source_ip(db_session)
    _insert_fingerprint(db_session)
    cid = _insert_campaign(db_session, status="active")
    repo = EventRepository(db_session)
    repo.add_campaign_member(cid, _IP, 0.8, _TS_STR, _TS_STR)
    db_session.flush()

    results = repo.get_campaigns_for_clustering()
    assert len(results) == 1
    assert results[0]["campaign_id"] == cid


def test_get_campaigns_for_clustering_includes_dormant(db_session):
    _insert_source_ip(db_session)
    _insert_fingerprint(db_session)
    cid = _insert_campaign(db_session, status="dormant")
    repo = EventRepository(db_session)
    repo.add_campaign_member(cid, _IP, 0.7, _TS_STR, _TS_STR)
    db_session.flush()

    results = repo.get_campaigns_for_clustering()
    assert any(r["campaign_id"] == cid for r in results)


def test_get_campaigns_for_clustering_excludes_historical(db_session):
    _insert_source_ip(db_session)
    _insert_fingerprint(db_session)
    cid = _insert_campaign(db_session, status="historical")
    repo = EventRepository(db_session)
    repo.add_campaign_member(cid, _IP, 0.7, _TS_STR, _TS_STR)
    db_session.flush()

    results = repo.get_campaigns_for_clustering()
    assert not any(r["campaign_id"] == cid for r in results)


def test_get_campaigns_for_clustering_excludes_campaign_without_fingerprint(db_session):
    _insert_source_ip(db_session)
    # No fingerprint inserted — campaign has a member but no fingerprint
    cid = _insert_campaign(db_session, status="active")
    repo = EventRepository(db_session)
    repo.add_campaign_member(cid, _IP, 0.7, _TS_STR, _TS_STR)
    db_session.flush()

    results = repo.get_campaigns_for_clustering()
    assert results == []


def test_get_campaigns_for_clustering_returned_keys(db_session):
    _insert_source_ip(db_session)
    _insert_fingerprint(db_session)
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.add_campaign_member(cid, _IP, 0.8, _TS_STR, _TS_STR)
    db_session.flush()

    results = repo.get_campaigns_for_clustering()
    assert len(results) == 1
    assert set(results[0].keys()) == {
        "campaign_id",
        "status",
        "last_seen",
        "timing_features",
        "sequence_features",
        "protocol_features",
        "credential_features",
        "target_features",
        "confidence",
    }


def test_get_campaigns_for_clustering_uses_most_recent_member(db_session):
    """When a campaign has two members, the fingerprint of the most-recently-
    active one is returned."""
    _insert_source_ip(db_session, _IP)
    _insert_source_ip(db_session, _IP2)

    target_tf = json.dumps({"port_freq": {"22": 1.0}, "top_dst_ports": [22]})
    _insert_fingerprint(db_session, _IP, confidence=0.5)
    _insert_fingerprint(db_session, _IP2, confidence=0.9, target_features=target_tf)

    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    # _IP added earlier, _IP2 is most recent
    repo.add_campaign_member(
        cid, _IP, 0.7, "2025-06-01T00:00:00+00:00", "2025-06-01T00:00:00+00:00"
    )
    repo.add_campaign_member(
        cid, _IP2, 0.9, "2025-06-05T00:00:00+00:00", "2025-06-05T00:00:00+00:00"
    )
    db_session.flush()

    results = repo.get_campaigns_for_clustering()
    assert len(results) == 1
    # Should return _IP2's fingerprint (most recently active)
    assert results[0]["confidence"] == pytest.approx(0.9)
    assert results[0]["target_features"] == target_tf
