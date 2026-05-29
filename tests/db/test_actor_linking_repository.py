"""Repository tests for Phase 7 Group B2 — campaign-to-actor linking.

Tests cover:
  - get_lineage_record: returns row or None
  - find_duplicate_lineage: detects existing (actor, campaign) pair
  - delete_lineage_record: hard-deletes, returns True/False
  - list_actor_campaigns_with_metadata: enriched with campaign fields
  - list_campaign_actors_with_metadata: enriched with actor fields
  - No automatic lineage creation
  - Invariants: no AI imports
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db.repository import EventRepository

_TS = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)


def _ts() -> str:
    return _TS.isoformat()


def _create_actor(session, *, display_name: str = "Test Actor") -> str:
    aid = str(uuid.uuid4())
    EventRepository(session).create_actor_profile(
        actor_id=aid,
        display_name=display_name,
        created_at=_ts(),
        updated_at=_ts(),
    )
    return aid


def _create_campaign(session, *, name: str | None = None, has_fingerprint: bool = False) -> str:
    cid = str(uuid.uuid4())
    now = _ts()
    session.execute(
        text("""
            INSERT INTO campaigns (id, name, status, confidence, first_seen, last_seen,
                member_ip_count, created_at, updated_at)
            VALUES (:id, :name, 'active', 0.7, :now, :now, 3, :now, :now)
        """),
        {"id": cid, "name": name or f"campaign-{cid[:8]}", "now": now},
    )
    if has_fingerprint:
        session.execute(
            text("UPDATE campaigns SET representative_fingerprint_json = :fp WHERE id = :id"),
            {"fp": '{"timing_features": null}', "id": cid},
        )
    session.flush()
    return cid


def _link(session, actor_id: str, campaign_id: str, rtype: str = "tactic_match") -> dict:
    return EventRepository(session).link_campaign_to_actor(
        actor_profile_id=actor_id,
        campaign_id=campaign_id,
        relationship_type=rtype,
    )


# ---------------------------------------------------------------------------
# get_lineage_record
# ---------------------------------------------------------------------------


def test_get_lineage_record_returns_row(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    lineage = _link(db_session, aid, cid)

    result = EventRepository(db_session).get_lineage_record(lineage["id"])
    assert result is not None
    assert result["id"] == lineage["id"]
    assert result["actor_profile_id"] == aid
    assert result["campaign_id"] == cid


def test_get_lineage_record_returns_none_for_unknown(db_session):
    result = EventRepository(db_session).get_lineage_record(str(uuid.uuid4()))
    assert result is None


# ---------------------------------------------------------------------------
# find_duplicate_lineage
# ---------------------------------------------------------------------------


def test_find_duplicate_lineage_returns_existing(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    lineage = _link(db_session, aid, cid, "primary_campaign")

    dup = EventRepository(db_session).find_duplicate_lineage(aid, cid)
    assert dup is not None
    assert dup["id"] == lineage["id"]


def test_find_duplicate_lineage_returns_none_when_no_link(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    result = EventRepository(db_session).find_duplicate_lineage(aid, cid)
    assert result is None


def test_find_duplicate_lineage_is_actor_campaign_pair_specific(db_session):
    aid1 = _create_actor(db_session)
    aid2 = _create_actor(db_session)
    cid = _create_campaign(db_session)

    _link(db_session, aid1, cid, "tactic_match")

    dup = EventRepository(db_session).find_duplicate_lineage(aid2, cid)
    assert dup is None


def test_find_duplicate_matches_regardless_of_relationship_type(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    _link(db_session, aid, cid, "infrastructure_reuse")

    dup = EventRepository(db_session).find_duplicate_lineage(aid, cid)
    assert dup is not None
    assert dup["relationship_type"] == "infrastructure_reuse"


# ---------------------------------------------------------------------------
# delete_lineage_record
# ---------------------------------------------------------------------------


def test_delete_lineage_returns_true_when_found(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    lineage = _link(db_session, aid, cid)

    result = EventRepository(db_session).delete_lineage_record(lineage["id"])
    assert result is True


def test_delete_lineage_returns_false_when_not_found(db_session):
    result = EventRepository(db_session).delete_lineage_record(str(uuid.uuid4()))
    assert result is False


def test_delete_lineage_removes_row(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    lineage = _link(db_session, aid, cid)
    EventRepository(db_session).delete_lineage_record(lineage["id"])

    remaining = EventRepository(db_session).get_lineage_record(lineage["id"])
    assert remaining is None


def test_delete_lineage_does_not_delete_campaign(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    lineage = _link(db_session, aid, cid)
    EventRepository(db_session).delete_lineage_record(lineage["id"])

    campaign = EventRepository(db_session).get_campaign(cid)
    assert campaign is not None


def test_delete_lineage_does_not_delete_actor(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    lineage = _link(db_session, aid, cid)
    EventRepository(db_session).delete_lineage_record(lineage["id"])

    actor = EventRepository(db_session).get_actor_profile(aid)
    assert actor is not None


# ---------------------------------------------------------------------------
# list_actor_campaigns_with_metadata
# ---------------------------------------------------------------------------


def test_list_actor_campaigns_returns_linked_campaigns(db_session):
    aid = _create_actor(db_session)
    cid1 = _create_campaign(db_session, name="camp-one")
    cid2 = _create_campaign(db_session, name="camp-two")

    repo = EventRepository(db_session)
    repo.link_campaign_to_actor(
        actor_profile_id=aid, campaign_id=cid1, relationship_type="primary_campaign"
    )
    repo.link_campaign_to_actor(
        actor_profile_id=aid, campaign_id=cid2, relationship_type="tactic_match"
    )

    items = repo.list_actor_campaigns_with_metadata(aid)
    campaign_ids = {i["campaign_id"] for i in items}
    assert cid1 in campaign_ids
    assert cid2 in campaign_ids


def test_list_actor_campaigns_includes_campaign_metadata(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session, name="named-camp", has_fingerprint=True)
    _link(db_session, aid, cid, "tactic_match")

    items = EventRepository(db_session).list_actor_campaigns_with_metadata(aid)
    assert len(items) == 1
    item = items[0]
    assert item["campaign_name"] == "named-camp"
    assert item["campaign_status"] == "active"
    assert item["campaign_last_seen"] is not None
    assert item["campaign_member_ip_count"] == 3
    assert item["campaign_has_fingerprint"] is True


def test_list_actor_campaigns_has_fingerprint_false_when_null(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session, has_fingerprint=False)
    _link(db_session, aid, cid)

    items = EventRepository(db_session).list_actor_campaigns_with_metadata(aid)
    assert items[0]["campaign_has_fingerprint"] is False


def test_list_actor_campaigns_includes_relationship_type(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    _link(db_session, aid, cid, "infrastructure_reuse")

    items = EventRepository(db_session).list_actor_campaigns_with_metadata(aid)
    assert items[0]["relationship_type"] == "infrastructure_reuse"


def test_list_actor_campaigns_empty_for_no_links(db_session):
    aid = _create_actor(db_session)
    items = EventRepository(db_session).list_actor_campaigns_with_metadata(aid)
    assert items == []


def test_list_actor_campaigns_only_returns_own_actor_links(db_session):
    aid1 = _create_actor(db_session)
    aid2 = _create_actor(db_session)
    cid = _create_campaign(db_session)

    _link(db_session, aid2, cid)

    items = EventRepository(db_session).list_actor_campaigns_with_metadata(aid1)
    assert items == []


def test_list_actor_campaigns_respects_limit(db_session):
    aid = _create_actor(db_session)
    for _ in range(5):
        cid = _create_campaign(db_session)
        _link(db_session, aid, cid)

    items = EventRepository(db_session).list_actor_campaigns_with_metadata(aid, limit=2)
    assert len(items) == 2


# ---------------------------------------------------------------------------
# list_campaign_actors_with_metadata
# ---------------------------------------------------------------------------


def test_list_campaign_actors_returns_linked_actors(db_session):
    aid1 = _create_actor(db_session, display_name="Actor One")
    aid2 = _create_actor(db_session, display_name="Actor Two")
    cid = _create_campaign(db_session)

    _link(db_session, aid1, cid, "tactic_match")
    _link(db_session, aid2, cid, "temporal_overlap")

    items = EventRepository(db_session).list_campaign_actors_with_metadata(cid)
    actor_ids = {i["actor_profile_id"] for i in items}
    assert aid1 in actor_ids
    assert aid2 in actor_ids


def test_list_campaign_actors_includes_actor_metadata(db_session):
    aid = _create_actor(db_session, display_name="Named Actor")
    cid = _create_campaign(db_session)
    _link(db_session, aid, cid, "primary_campaign")

    items = EventRepository(db_session).list_campaign_actors_with_metadata(cid)
    assert len(items) == 1
    item = items[0]
    assert item["actor_display_name"] == "Named Actor"
    assert item["actor_status"] == "active"
    assert item["actor_confidence"] == pytest.approx(0.5)


def test_list_campaign_actors_includes_relationship_type(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    _link(db_session, aid, cid, "temporal_overlap")

    items = EventRepository(db_session).list_campaign_actors_with_metadata(cid)
    assert items[0]["relationship_type"] == "temporal_overlap"


def test_list_campaign_actors_empty_for_no_links(db_session):
    cid = _create_campaign(db_session)
    items = EventRepository(db_session).list_campaign_actors_with_metadata(cid)
    assert items == []


def test_list_campaign_actors_only_returns_own_campaign_links(db_session):
    aid = _create_actor(db_session)
    cid1 = _create_campaign(db_session)
    cid2 = _create_campaign(db_session)

    _link(db_session, aid, cid2)

    items = EventRepository(db_session).list_campaign_actors_with_metadata(cid1)
    assert items == []


def test_list_campaign_actors_respects_limit(db_session):
    cid = _create_campaign(db_session)
    for _ in range(4):
        aid = _create_actor(db_session)
        _link(db_session, aid, cid)

    items = EventRepository(db_session).list_campaign_actors_with_metadata(cid, limit=2)
    assert len(items) == 2


# ---------------------------------------------------------------------------
# No automatic lineage creation
# ---------------------------------------------------------------------------


def test_creating_actor_and_campaign_does_not_create_lineage(db_session):
    _create_actor(db_session)
    _create_campaign(db_session)
    lineage = EventRepository(db_session).list_campaign_lineage()
    assert lineage == []


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_no_ai_imports_in_actor_repository():
    import importlib

    mod = importlib.import_module("app.db.repositories.actor")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content
