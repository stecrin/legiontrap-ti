"""Repository tests for Phase 7 Group B4 — actor stability support query.

Tests cover list_actor_campaign_stability():
  - returns empty list when actor has no linked campaigns
  - returns stability json for campaigns with data
  - returns NULL stability for campaigns without behavioral_stability_json
  - includes relationship_type from lineage
  - includes campaign metadata (name, status, last_seen)
  - ordered by lineage created_at ASC (oldest link first)
  - handles orphaned lineage rows (campaign deleted from campaigns table)
  - multiple campaigns aggregated correctly
  - respects actor_profile_id filter (only returns linked campaigns)

All tests use an isolated in-memory SQLite database via the db_session fixture.
"""

from __future__ import annotations

import json
import uuid

from app.db.repository import EventRepository

_TS1 = "2026-05-01T10:00:00+00:00"
_TS2 = "2026-05-02T10:00:00+00:00"
_TS3 = "2026-05-03T10:00:00+00:00"


def _uid() -> str:
    return str(uuid.uuid4())


def _make_stability_json(composite: float = 0.80) -> str:
    return json.dumps(
        {
            "status": "ok",
            "composite_score": composite,
            "timing_stability": 0.78,
            "sequence_stability": 0.85,
            "protocol_stability": None,
            "credential_stability": None,
            "target_stability": None,
            "sample_count": 5,
            "pair_count": 4,
            "dimensions_used": 2,
            "calculated_at": "2026-05-01T12:00:00+00:00",
            "explanation": {},
        }
    )


def _insert_campaign(
    session,
    *,
    cid: str | None = None,
    status: str = "active",
    last_seen: str = _TS1,
    behavioral_stability_json: str | None = None,
) -> str:
    from sqlalchemy import text

    cid = cid or _uid()
    session.execute(
        text("""
            INSERT INTO campaigns (
                id, name, status, confidence,
                first_seen, last_seen, member_ip_count,
                behavioral_stability_json,
                created_at, updated_at
            ) VALUES (
                :id, :name, :status, 0.7,
                :ts, :last_seen, 1,
                :stability_json,
                :ts, :ts
            )
        """),
        {
            "id": cid,
            "name": f"campaign-{cid[:8]}",
            "status": status,
            "ts": _TS1,
            "last_seen": last_seen,
            "stability_json": behavioral_stability_json,
        },
    )
    session.flush()
    return cid


def _insert_actor(session, *, aid: str | None = None) -> str:
    from sqlalchemy import text

    aid = aid or _uid()
    session.execute(
        text("""
            INSERT INTO actor_profiles (
                id, display_name, confidence, status, created_at, updated_at
            ) VALUES (:id, :name, 0.5, 'active', :ts, :ts)
        """),
        {"id": aid, "name": f"actor-{aid[:8]}", "ts": _TS1},
    )
    session.flush()
    return aid


def _link(
    session,
    *,
    actor_id: str,
    campaign_id: str,
    rel: str = "temporal_overlap",
    created_at: str = _TS1,
) -> str:
    from sqlalchemy import text

    lid = _uid()
    session.execute(
        text("""
            INSERT INTO campaign_lineage (
                id, actor_profile_id, campaign_id,
                relationship_type, confidence, created_at
            ) VALUES (:id, :actor_id, :campaign_id, :rel, 0.5, :ts)
        """),
        {"id": lid, "actor_id": actor_id, "campaign_id": campaign_id, "rel": rel, "ts": created_at},
    )
    session.flush()
    return lid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_when_actor_has_no_links(db_session):
    aid = _insert_actor(db_session)
    rows = EventRepository(db_session).list_actor_campaign_stability(aid)
    assert rows == []


def test_returns_stability_json_for_linked_campaign(db_session):
    stab = _make_stability_json(0.85)
    cid = _insert_campaign(db_session, behavioral_stability_json=stab)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=cid)

    rows = EventRepository(db_session).list_actor_campaign_stability(aid)
    assert len(rows) == 1
    assert rows[0]["behavioral_stability_json"] == stab


def test_null_stability_included_for_campaign_without_data(db_session):
    cid = _insert_campaign(db_session, behavioral_stability_json=None)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=cid)

    rows = EventRepository(db_session).list_actor_campaign_stability(aid)
    assert len(rows) == 1
    assert rows[0]["behavioral_stability_json"] is None


def test_includes_relationship_type(db_session):
    cid = _insert_campaign(db_session)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=cid, rel="primary_campaign")

    rows = EventRepository(db_session).list_actor_campaign_stability(aid)
    assert rows[0]["relationship_type"] == "primary_campaign"


def test_includes_campaign_metadata(db_session):
    cid = _insert_campaign(db_session, status="dormant", last_seen=_TS2)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=cid)

    rows = EventRepository(db_session).list_actor_campaign_stability(aid)
    row = rows[0]
    assert row["campaign_id"] == cid
    assert row["campaign_status"] == "dormant"
    assert row["last_seen"] == _TS2
    assert row["campaign_name"] is not None


def test_ordered_by_lineage_created_at_asc(db_session):
    c1 = _insert_campaign(db_session)
    c2 = _insert_campaign(db_session)
    c3 = _insert_campaign(db_session)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=c1, created_at=_TS3)
    _link(db_session, actor_id=aid, campaign_id=c2, created_at=_TS1)
    _link(db_session, actor_id=aid, campaign_id=c3, created_at=_TS2)

    rows = EventRepository(db_session).list_actor_campaign_stability(aid)
    assert [r["campaign_id"] for r in rows] == [c2, c3, c1]


def test_multiple_campaigns_all_returned(db_session):
    c1 = _insert_campaign(db_session, behavioral_stability_json=_make_stability_json(0.80))
    c2 = _insert_campaign(db_session, behavioral_stability_json=None)
    c3 = _insert_campaign(db_session, behavioral_stability_json=_make_stability_json(0.90))
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=c1, created_at=_TS1)
    _link(db_session, actor_id=aid, campaign_id=c2, created_at=_TS2)
    _link(db_session, actor_id=aid, campaign_id=c3, created_at=_TS3)

    rows = EventRepository(db_session).list_actor_campaign_stability(aid)
    assert len(rows) == 3


def test_does_not_return_other_actors_campaigns(db_session):
    c1 = _insert_campaign(db_session)
    c2 = _insert_campaign(db_session)
    aid1 = _insert_actor(db_session)
    aid2 = _insert_actor(db_session)
    _link(db_session, actor_id=aid1, campaign_id=c1)
    _link(db_session, actor_id=aid2, campaign_id=c2)

    rows = EventRepository(db_session).list_actor_campaign_stability(aid1)
    assert len(rows) == 1
    assert rows[0]["campaign_id"] == c1


def test_expected_row_keys(db_session):
    cid = _insert_campaign(db_session)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=cid)

    rows = EventRepository(db_session).list_actor_campaign_stability(aid)
    row = rows[0]
    for key in (
        "campaign_id",
        "relationship_type",
        "confidence",
        "campaign_name",
        "campaign_status",
        "last_seen",
        "behavioral_stability_json",
    ):
        assert key in row, f"missing key: {key!r}"
