"""Repository tests for Phase 7 Group B3 — actor suggestion support queries.

Tests cover:
  list_campaigns_for_suggestions:
    - returns empty list when no eligible campaigns
    - excludes campaigns with NULL representative_fingerprint_json
    - excludes campaigns with status 'archived' or 'merged'
    - includes active, dormant, reactivated campaigns with fingerprints
    - parses fingerprint JSON and exposes feature columns
    - skips rows with unparseable fingerprint JSON
    - respects limit parameter
    - returns newest last_seen first

  get_coattributed_campaign_pairs:
    - returns empty set when campaign_lineage is empty
    - returns empty set when actors have only one campaign each
    - returns pairs for actors with two or more campaigns
    - pair is a frozenset (order-independent)
    - multiple actors each contribute independent pairs
    - same pair from two actors is deduplicated

All tests use an isolated in-memory SQLite database via the db_session fixture.
"""

from __future__ import annotations

import json
import uuid

from app.db.repository import EventRepository

_TS = "2026-05-01T12:00:00+00:00"
_TS2 = "2026-05-02T12:00:00+00:00"
_TS3 = "2026-05-03T12:00:00+00:00"


def _uid() -> str:
    return str(uuid.uuid4())


def _insert_campaign(
    session,
    *,
    cid: str | None = None,
    status: str = "active",
    last_seen: str = _TS,
    representative_fingerprint_json: str | None = None,
    member_ip_count: int = 1,
) -> str:
    from sqlalchemy import text

    cid = cid or _uid()
    session.execute(
        text("""
            INSERT INTO campaigns (
                id, name, status, confidence,
                first_seen, last_seen, member_ip_count,
                representative_fingerprint_json,
                created_at, updated_at
            ) VALUES (
                :id, :name, :status, 0.7,
                :ts, :last_seen, :member_ip_count,
                :fp_json,
                :ts, :ts
            )
        """),
        {
            "id": cid,
            "name": f"campaign-{cid[:8]}",
            "status": status,
            "ts": _TS,
            "last_seen": last_seen,
            "member_ip_count": member_ip_count,
            "fp_json": representative_fingerprint_json,
        },
    )
    session.flush()
    return cid


def _make_fingerprint_json(
    timing: str | None = None,
    sequence: str | None = None,
) -> str:
    """Build a minimal representative_fingerprint_json string."""
    return json.dumps(
        {
            "timing_features": timing,
            "sequence_features": sequence,
            "protocol_features": None,
            "credential_features": None,
            "target_features": None,
        }
    )


def _insert_actor(session, *, aid: str | None = None) -> str:
    aid = aid or _uid()
    now = _TS
    session.execute(
        __import__("sqlalchemy").text("""
            INSERT INTO actor_profiles (
                id, display_name, confidence, status, created_at, updated_at
            ) VALUES (:id, :name, 0.5, 'active', :now, :now)
        """),
        {"id": aid, "name": f"actor-{aid[:8]}", "now": now},
    )
    session.flush()
    return aid


def _link(session, *, actor_id: str, campaign_id: str) -> None:
    from sqlalchemy import text

    lid = _uid()
    session.execute(
        text("""
            INSERT INTO campaign_lineage (
                id, actor_profile_id, campaign_id,
                relationship_type, confidence, created_at
            ) VALUES (:id, :actor_id, :campaign_id, 'temporal_overlap', 0.5, :now)
        """),
        {"id": lid, "actor_id": actor_id, "campaign_id": campaign_id, "now": _TS},
    )
    session.flush()


# ---------------------------------------------------------------------------
# list_campaigns_for_suggestions
# ---------------------------------------------------------------------------


def test_list_campaigns_for_suggestions_empty(db_session):
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert items == []


def test_list_campaigns_for_suggestions_excludes_null_fingerprint(db_session):
    _insert_campaign(db_session, status="active", representative_fingerprint_json=None)
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert items == []


def test_list_campaigns_for_suggestions_excludes_archived(db_session):
    fp = _make_fingerprint_json()
    _insert_campaign(db_session, status="archived", representative_fingerprint_json=fp)
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert items == []


def test_list_campaigns_for_suggestions_includes_active(db_session):
    fp = _make_fingerprint_json()
    cid = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert len(items) == 1
    assert items[0]["id"] == cid


def test_list_campaigns_for_suggestions_includes_dormant(db_session):
    fp = _make_fingerprint_json()
    cid = _insert_campaign(db_session, status="dormant", representative_fingerprint_json=fp)
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert len(items) == 1
    assert items[0]["id"] == cid


def test_list_campaigns_for_suggestions_includes_reactivated(db_session):
    fp = _make_fingerprint_json()
    cid = _insert_campaign(db_session, status="reactivated", representative_fingerprint_json=fp)
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert len(items) == 1
    assert items[0]["id"] == cid


def test_list_campaigns_for_suggestions_has_expected_fields(db_session):
    timing_json = json.dumps({"interval": {"mean": 60.0}})
    fp = _make_fingerprint_json(timing=timing_json)
    cid = _insert_campaign(
        db_session,
        status="active",
        representative_fingerprint_json=fp,
        member_ip_count=3,
    )
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == cid
    assert item["status"] == "active"
    assert item["member_ip_count"] == 3
    assert "timing_features" in item
    assert "sequence_features" in item
    assert "protocol_features" in item
    assert "credential_features" in item
    assert "target_features" in item


def test_list_campaigns_for_suggestions_feature_columns_match_fingerprint(db_session):
    timing_json = json.dumps({"interval": {"mean": 60.0}})
    fp = _make_fingerprint_json(timing=timing_json)
    _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert items[0]["timing_features"] == timing_json
    assert items[0]["sequence_features"] is None


def test_list_campaigns_for_suggestions_skips_unparseable_fingerprint(db_session):
    _insert_campaign(db_session, status="active", representative_fingerprint_json="not-valid-json")
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert items == []


def test_list_campaigns_for_suggestions_respects_limit(db_session):
    fp = _make_fingerprint_json()
    for _i in range(5):
        _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    items = EventRepository(db_session).list_campaigns_for_suggestions(limit=3)
    assert len(items) == 3


def test_list_campaigns_for_suggestions_newest_first(db_session):
    fp = _make_fingerprint_json()
    c1 = _insert_campaign(
        db_session, status="active", last_seen=_TS, representative_fingerprint_json=fp
    )
    c2 = _insert_campaign(
        db_session, status="active", last_seen=_TS3, representative_fingerprint_json=fp
    )
    c3 = _insert_campaign(
        db_session, status="active", last_seen=_TS2, representative_fingerprint_json=fp
    )
    items = EventRepository(db_session).list_campaigns_for_suggestions()
    assert [i["id"] for i in items] == [c2, c3, c1]


# ---------------------------------------------------------------------------
# get_coattributed_campaign_pairs
# ---------------------------------------------------------------------------


def test_get_coattributed_pairs_empty_lineage(db_session):
    pairs = EventRepository(db_session).get_coattributed_campaign_pairs()
    assert pairs == set()


def test_get_coattributed_pairs_single_campaign_per_actor(db_session):
    fp = _make_fingerprint_json()
    cid = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=cid)
    pairs = EventRepository(db_session).get_coattributed_campaign_pairs()
    assert pairs == set()


def test_get_coattributed_pairs_two_campaigns_under_same_actor(db_session):
    fp = _make_fingerprint_json()
    c1 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    c2 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=c1)
    _link(db_session, actor_id=aid, campaign_id=c2)
    pairs = EventRepository(db_session).get_coattributed_campaign_pairs()
    assert pairs == {frozenset({c1, c2})}


def test_get_coattributed_pairs_is_order_independent(db_session):
    fp = _make_fingerprint_json()
    c1 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    c2 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=c1)
    _link(db_session, actor_id=aid, campaign_id=c2)
    pairs = EventRepository(db_session).get_coattributed_campaign_pairs()
    assert frozenset({c1, c2}) in pairs
    assert frozenset({c2, c1}) in pairs  # same frozenset


def test_get_coattributed_pairs_three_campaigns_produce_three_pairs(db_session):
    fp = _make_fingerprint_json()
    c1 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    c2 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    c3 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    aid = _insert_actor(db_session)
    _link(db_session, actor_id=aid, campaign_id=c1)
    _link(db_session, actor_id=aid, campaign_id=c2)
    _link(db_session, actor_id=aid, campaign_id=c3)
    pairs = EventRepository(db_session).get_coattributed_campaign_pairs()
    assert pairs == {
        frozenset({c1, c2}),
        frozenset({c1, c3}),
        frozenset({c2, c3}),
    }


def test_get_coattributed_pairs_multiple_actors_independent(db_session):
    fp = _make_fingerprint_json()
    c1 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    c2 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    c3 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    c4 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    aid1 = _insert_actor(db_session)
    aid2 = _insert_actor(db_session)
    _link(db_session, actor_id=aid1, campaign_id=c1)
    _link(db_session, actor_id=aid1, campaign_id=c2)
    _link(db_session, actor_id=aid2, campaign_id=c3)
    _link(db_session, actor_id=aid2, campaign_id=c4)
    pairs = EventRepository(db_session).get_coattributed_campaign_pairs()
    assert pairs == {frozenset({c1, c2}), frozenset({c3, c4})}


def test_get_coattributed_pairs_deduplicates_same_pair_from_multiple_actors(db_session):
    fp = _make_fingerprint_json()
    c1 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    c2 = _insert_campaign(db_session, status="active", representative_fingerprint_json=fp)
    aid1 = _insert_actor(db_session)
    aid2 = _insert_actor(db_session)
    _link(db_session, actor_id=aid1, campaign_id=c1)
    _link(db_session, actor_id=aid1, campaign_id=c2)
    _link(db_session, actor_id=aid2, campaign_id=c1)
    _link(db_session, actor_id=aid2, campaign_id=c2)
    pairs = EventRepository(db_session).get_coattributed_campaign_pairs()
    assert pairs == {frozenset({c1, c2})}
