"""Repository tests for Phase 7 Group B1 — actor identity foundation.

Tests cover:
  - create_actor_profile: creates and returns row with correct fields
  - get_actor_profile: returns row or None
  - list_actor_profiles: ordering, status filter, limit
  - update_actor_profile: partial update, notes sentinel, nonexistent ID
  - link_campaign_to_actor: valid types accepted, invalid types raise ValueError
  - link_campaign_to_actor: no automatic lineage creation
  - list_campaign_lineage: filter by actor_profile_id, campaign_id
  - Invariants: no AI imports, no automatic actor writes
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.db.repository import EventRepository
from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

_TS = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)


def _ts(dt: datetime = _TS) -> str:
    return dt.isoformat()


def _create_actor(session, *, display_name: str = "Test Actor", status: str = "active") -> str:
    aid = str(uuid.uuid4())
    EventRepository(session).create_actor_profile(
        actor_id=aid,
        display_name=display_name,
        status=status,
        created_at=_ts(),
        updated_at=_ts(),
    )
    return aid


def _create_campaign(session) -> str:
    from sqlalchemy import text

    cid = str(uuid.uuid4())
    now = _ts()
    session.execute(
        text("""
            INSERT INTO campaigns (id, name, status, confidence, first_seen, last_seen,
                member_ip_count, created_at, updated_at)
            VALUES (:id, :name, 'active', 0.7, :now, :now, 1, :now, :now)
        """),
        {"id": cid, "name": f"campaign-{cid[:8]}", "now": now},
    )
    session.flush()
    return cid


# ---------------------------------------------------------------------------
# create_actor_profile
# ---------------------------------------------------------------------------


def test_create_actor_returns_dict(db_session):
    repo = EventRepository(db_session)
    actor = repo.create_actor_profile(display_name="Alpha Actor")
    assert isinstance(actor, dict)
    assert actor["display_name"] == "Alpha Actor"
    assert actor["id"] is not None


def test_create_actor_defaults(db_session):
    repo = EventRepository(db_session)
    actor = repo.create_actor_profile(display_name="Beta Actor")
    assert actor["status"] == "active"
    assert actor["confidence"] == 0.5
    assert actor["notes"] is None


def test_create_actor_custom_fields(db_session):
    repo = EventRepository(db_session)
    actor = repo.create_actor_profile(
        display_name="Gamma Actor",
        confidence=0.8,
        status="archived",
        notes="test notes",
    )
    assert actor["confidence"] == 0.8
    assert actor["status"] == "archived"
    assert actor["notes"] == "test notes"


def test_create_actor_timestamps_present(db_session):
    repo = EventRepository(db_session)
    actor = repo.create_actor_profile(display_name="Delta Actor")
    assert actor["created_at"] is not None
    assert actor["updated_at"] is not None


# ---------------------------------------------------------------------------
# get_actor_profile
# ---------------------------------------------------------------------------


def test_get_actor_returns_row(db_session):
    aid = _create_actor(db_session, display_name="Get Test")
    actor = EventRepository(db_session).get_actor_profile(aid)
    assert actor is not None
    assert actor["id"] == aid
    assert actor["display_name"] == "Get Test"


def test_get_actor_returns_none_for_missing(db_session):
    result = EventRepository(db_session).get_actor_profile(str(uuid.uuid4()))
    assert result is None


# ---------------------------------------------------------------------------
# list_actor_profiles
# ---------------------------------------------------------------------------


def test_list_actors_returns_all(db_session):
    for i in range(3):
        _create_actor(db_session, display_name=f"Actor {i}")
    items = EventRepository(db_session).list_actor_profiles()
    assert len(items) >= 3


def test_list_actors_ordered_newest_first(db_session):

    older = (datetime(2026, 1, 1, tzinfo=UTC)).isoformat()
    newer = (datetime(2026, 5, 1, tzinfo=UTC)).isoformat()

    repo = EventRepository(db_session)
    repo.create_actor_profile(display_name="Older", created_at=older, updated_at=older)
    repo.create_actor_profile(display_name="Newer", created_at=newer, updated_at=newer)

    items = repo.list_actor_profiles()
    names = [i["display_name"] for i in items]
    assert names.index("Newer") < names.index("Older")


def test_list_actors_status_filter(db_session):
    _create_actor(db_session, display_name="Active One", status="active")
    _create_actor(db_session, display_name="Archived One", status="archived")

    repo = EventRepository(db_session)
    active = repo.list_actor_profiles(status="active")
    archived = repo.list_actor_profiles(status="archived")

    assert all(a["status"] == "active" for a in active)
    assert all(a["status"] == "archived" for a in archived)


def test_list_actors_respects_limit(db_session):
    for i in range(5):
        _create_actor(db_session, display_name=f"Limit Actor {i}")
    items = EventRepository(db_session).list_actor_profiles(limit=2)
    assert len(items) == 2


def test_list_actors_empty(db_session):
    items = EventRepository(db_session).list_actor_profiles()
    assert items == []


# ---------------------------------------------------------------------------
# update_actor_profile
# ---------------------------------------------------------------------------


def test_update_display_name(db_session):
    aid = _create_actor(db_session, display_name="Before")
    updated = EventRepository(db_session).update_actor_profile(aid, display_name="After")
    assert updated["display_name"] == "After"


def test_update_confidence(db_session):
    aid = _create_actor(db_session)
    updated = EventRepository(db_session).update_actor_profile(aid, confidence=0.9)
    assert updated["confidence"] == pytest.approx(0.9)


def test_update_status_to_archived(db_session):
    aid = _create_actor(db_session, status="active")
    updated = EventRepository(db_session).update_actor_profile(aid, status="archived")
    assert updated["status"] == "archived"


def test_update_notes_to_value(db_session):
    aid = _create_actor(db_session)
    updated = EventRepository(db_session).update_actor_profile(aid, notes="new note")
    assert updated["notes"] == "new note"


def test_update_notes_to_none_clears_field(db_session):
    repo = EventRepository(db_session)
    actor = repo.create_actor_profile(display_name="Notes Actor", notes="old note")
    updated = repo.update_actor_profile(actor["id"], notes=None)
    assert updated["notes"] is None


def test_update_omitting_notes_leaves_value(db_session):
    repo = EventRepository(db_session)
    actor = repo.create_actor_profile(display_name="Notes Persist", notes="kept")
    updated = repo.update_actor_profile(actor["id"], confidence=0.7)
    assert updated["notes"] == "kept"


def test_update_nonexistent_actor_returns_none(db_session):
    result = EventRepository(db_session).update_actor_profile(
        str(uuid.uuid4()), display_name="Ghost"
    )
    assert result is None


def test_update_updates_updated_at(db_session):
    aid = _create_actor(db_session)
    old = EventRepository(db_session).get_actor_profile(aid)
    updated = EventRepository(db_session).update_actor_profile(aid, display_name="New Name")
    assert updated["updated_at"] >= old["updated_at"]


# ---------------------------------------------------------------------------
# link_campaign_to_actor — valid relationship types
# ---------------------------------------------------------------------------


def test_link_all_valid_relationship_types(db_session):
    repo = EventRepository(db_session)
    for rtype in sorted(VALID_RELATIONSHIP_TYPES):
        aid = _create_actor(db_session)
        cid = _create_campaign(db_session)
        lineage = repo.link_campaign_to_actor(
            actor_profile_id=aid,
            campaign_id=cid,
            relationship_type=rtype,
        )
        assert lineage["relationship_type"] == rtype


def test_link_primary_campaign(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    lineage = EventRepository(db_session).link_campaign_to_actor(
        actor_profile_id=aid,
        campaign_id=cid,
        relationship_type="primary_campaign",
    )
    assert lineage["actor_profile_id"] == aid
    assert lineage["campaign_id"] == cid
    assert lineage["relationship_type"] == "primary_campaign"
    assert lineage["id"] is not None


def test_link_returns_lineage_with_confidence(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    lineage = EventRepository(db_session).link_campaign_to_actor(
        actor_profile_id=aid,
        campaign_id=cid,
        relationship_type="tactic_match",
        confidence=0.8,
    )
    assert lineage["confidence"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# link_campaign_to_actor — invalid relationship types
# ---------------------------------------------------------------------------


def test_link_invalid_relationship_type_raises_value_error(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    with pytest.raises(ValueError, match="Invalid relationship_type"):
        EventRepository(db_session).link_campaign_to_actor(
            actor_profile_id=aid,
            campaign_id=cid,
            relationship_type="made_up_type",
        )


def test_link_empty_string_raises_value_error(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    with pytest.raises(ValueError):
        EventRepository(db_session).link_campaign_to_actor(
            actor_profile_id=aid,
            campaign_id=cid,
            relationship_type="",
        )


def test_link_open_string_raises_value_error(db_session):
    aid = _create_actor(db_session)
    cid = _create_campaign(db_session)
    with pytest.raises(ValueError):
        EventRepository(db_session).link_campaign_to_actor(
            actor_profile_id=aid,
            campaign_id=cid,
            relationship_type="related",
        )


# ---------------------------------------------------------------------------
# list_campaign_lineage
# ---------------------------------------------------------------------------


def test_list_lineage_by_actor(db_session):
    aid1 = _create_actor(db_session)
    aid2 = _create_actor(db_session)
    cid1 = _create_campaign(db_session)
    cid2 = _create_campaign(db_session)

    repo = EventRepository(db_session)
    repo.link_campaign_to_actor(
        actor_profile_id=aid1, campaign_id=cid1, relationship_type="primary_campaign"
    )
    repo.link_campaign_to_actor(
        actor_profile_id=aid2, campaign_id=cid2, relationship_type="tactic_match"
    )

    items = repo.list_campaign_lineage(actor_profile_id=aid1)
    assert len(items) == 1
    assert items[0]["actor_profile_id"] == aid1
    assert items[0]["campaign_id"] == cid1


def test_list_lineage_by_campaign(db_session):
    aid1 = _create_actor(db_session)
    aid2 = _create_actor(db_session)
    cid = _create_campaign(db_session)

    repo = EventRepository(db_session)
    repo.link_campaign_to_actor(
        actor_profile_id=aid1, campaign_id=cid, relationship_type="tactic_match"
    )
    repo.link_campaign_to_actor(
        actor_profile_id=aid2, campaign_id=cid, relationship_type="temporal_overlap"
    )

    items = repo.list_campaign_lineage(campaign_id=cid)
    actor_ids = {i["actor_profile_id"] for i in items}
    assert aid1 in actor_ids
    assert aid2 in actor_ids


def test_list_lineage_no_filter_returns_all(db_session):
    aid = _create_actor(db_session)
    for _ in range(3):
        cid = _create_campaign(db_session)
        EventRepository(db_session).link_campaign_to_actor(
            actor_profile_id=aid, campaign_id=cid, relationship_type="infrastructure_reuse"
        )

    items = EventRepository(db_session).list_campaign_lineage()
    assert len(items) >= 3


def test_list_lineage_respects_limit(db_session):
    aid = _create_actor(db_session)
    for _ in range(5):
        cid = _create_campaign(db_session)
        EventRepository(db_session).link_campaign_to_actor(
            actor_profile_id=aid, campaign_id=cid, relationship_type="tactic_match"
        )

    items = EventRepository(db_session).list_campaign_lineage(limit=2)
    assert len(items) == 2


def test_no_automatic_lineage_creation(db_session):
    _create_actor(db_session)
    _create_campaign(db_session)
    items = EventRepository(db_session).list_campaign_lineage()
    assert items == []


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


def test_no_ai_imports_in_actor_constants():
    import importlib

    mod = importlib.import_module("app.intelligence.actor_constants")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content
