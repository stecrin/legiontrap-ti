"""Repository tests for Phase 7 Group A3 — sparse campaign surface.

Tests cover:
  - list_sparse_campaigns: returns only campaigns without representative fingerprint
  - list_sparse_campaigns: respects limit
  - get_campaign_observation_counts: correct counts when observations exist/absent
  - get_bulk_observation_counts: batch version matches per-campaign counts
  - list_campaigns_with_fingerprint_status: has_fingerprint field is correct
  - Campaign with fingerprint does not appear in sparse list
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.repository import EventRepository

_TS = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
_TS2 = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _ts(dt: datetime = _TS) -> str:
    return dt.isoformat()


def _create_campaign(
    session,
    *,
    status: str = "active",
    representative_fingerprint_json: str | None = None,
    first_seen: str | None = None,
    last_seen: str | None = None,
) -> str:
    cid = str(uuid.uuid4())
    repo = EventRepository(session)
    repo.create_campaign(
        campaign_id=cid,
        name=f"campaign-{cid[:8]}",
        status=status,
        confidence=0.7,
        first_seen=first_seen or _ts(_TS),
        last_seen=last_seen or _ts(_TS),
        member_ip_count=1,
        created_at=_ts(),
        updated_at=_ts(),
    )
    if representative_fingerprint_json is not None:
        session.execute(
            __import__("sqlalchemy").text(
                "UPDATE campaigns SET representative_fingerprint_json = :fp WHERE id = :id"
            ),
            {"fp": representative_fingerprint_json, "id": cid},
        )
    session.flush()
    return cid


def _add_observation(
    session,
    campaign_id: str,
    *,
    reviewed: bool = False,
) -> str:
    obs_id = str(uuid.uuid4())
    from sqlalchemy import text

    session.execute(
        text("""
            INSERT INTO campaign_observations
                (id, campaign_id, source_ip, observed_at, event_count,
                 is_reactivation, dormancy_gap_days, notes, analyst_review_json)
            VALUES
                (:id, :cid, :ip, :ts, 5, 0, NULL, NULL, :review)
        """),
        {
            "id": obs_id,
            "cid": campaign_id,
            "ip": "10.0.0.1",
            "ts": _ts(),
            "review": '{"decision":"analyst_confirmed"}' if reviewed else None,
        },
    )
    session.flush()
    return obs_id


# ---------------------------------------------------------------------------
# list_sparse_campaigns
# ---------------------------------------------------------------------------


def test_list_sparse_returns_campaigns_without_fingerprint(db_session):
    cid_sparse = _create_campaign(db_session, representative_fingerprint_json=None)
    cid_rich = _create_campaign(db_session, representative_fingerprint_json='{"x":1}')

    repo = EventRepository(db_session)
    sparse = repo.list_sparse_campaigns()
    ids = [c["id"] for c in sparse]

    assert cid_sparse in ids
    assert cid_rich not in ids


def test_list_sparse_has_fingerprint_false(db_session):
    _create_campaign(db_session, representative_fingerprint_json=None)
    repo = EventRepository(db_session)
    items = repo.list_sparse_campaigns()
    assert all(item["has_fingerprint"] is False for item in items)


def test_list_sparse_empty_when_all_have_fingerprint(db_session):
    _create_campaign(db_session, representative_fingerprint_json='{"x":1}')
    _create_campaign(db_session, representative_fingerprint_json='{"y":2}')
    repo = EventRepository(db_session)
    assert repo.list_sparse_campaigns() == []


def test_list_sparse_respects_limit(db_session):
    for _ in range(5):
        _create_campaign(db_session)
    repo = EventRepository(db_session)
    results = repo.list_sparse_campaigns(limit=2)
    assert len(results) == 2


def test_list_sparse_ordered_by_last_seen_desc(db_session):
    old_ts = "2026-01-01T00:00:00+00:00"
    new_ts = "2026-05-01T00:00:00+00:00"
    cid_old = _create_campaign(db_session, last_seen=old_ts)
    cid_new = _create_campaign(db_session, last_seen=new_ts)

    repo = EventRepository(db_session)
    items = repo.list_sparse_campaigns()
    ids = [c["id"] for c in items]
    assert ids.index(cid_new) < ids.index(cid_old)


def test_list_sparse_includes_all_statuses(db_session):
    cid_active = _create_campaign(db_session, status="active")
    cid_dormant = _create_campaign(db_session, status="dormant")
    cid_historical = _create_campaign(db_session, status="historical")

    repo = EventRepository(db_session)
    ids = [c["id"] for c in repo.list_sparse_campaigns()]
    assert cid_active in ids
    assert cid_dormant in ids
    assert cid_historical in ids


# ---------------------------------------------------------------------------
# get_campaign_observation_counts
# ---------------------------------------------------------------------------


def test_observation_counts_zero_when_no_observations(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    counts = repo.get_campaign_observation_counts(cid)
    assert counts["observation_count"] == 0
    assert counts["review_count"] == 0


def test_observation_counts_correct(db_session):
    cid = _create_campaign(db_session)
    _add_observation(db_session, cid, reviewed=True)
    _add_observation(db_session, cid, reviewed=False)
    _add_observation(db_session, cid, reviewed=True)

    repo = EventRepository(db_session)
    counts = repo.get_campaign_observation_counts(cid)
    assert counts["observation_count"] == 3
    assert counts["review_count"] == 2


def test_observation_counts_only_counts_own_campaign(db_session):
    cid1 = _create_campaign(db_session)
    cid2 = _create_campaign(db_session)
    _add_observation(db_session, cid1, reviewed=True)
    _add_observation(db_session, cid2, reviewed=False)

    repo = EventRepository(db_session)
    counts1 = repo.get_campaign_observation_counts(cid1)
    counts2 = repo.get_campaign_observation_counts(cid2)
    assert counts1["observation_count"] == 1
    assert counts2["observation_count"] == 1
    assert counts1["review_count"] == 1
    assert counts2["review_count"] == 0


# ---------------------------------------------------------------------------
# get_bulk_observation_counts
# ---------------------------------------------------------------------------


def test_bulk_observation_counts_empty_input(db_session):
    repo = EventRepository(db_session)
    result = repo.get_bulk_observation_counts([])
    assert result == {}


def test_bulk_observation_counts_matches_per_campaign(db_session):
    cid1 = _create_campaign(db_session)
    cid2 = _create_campaign(db_session)
    _add_observation(db_session, cid1, reviewed=True)
    _add_observation(db_session, cid1, reviewed=False)
    _add_observation(db_session, cid2)

    repo = EventRepository(db_session)
    bulk = repo.get_bulk_observation_counts([cid1, cid2])
    per1 = repo.get_campaign_observation_counts(cid1)
    per2 = repo.get_campaign_observation_counts(cid2)

    assert bulk[cid1] == per1
    assert bulk[cid2] == per2


def test_bulk_observation_counts_campaigns_without_observations(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    bulk = repo.get_bulk_observation_counts([cid])
    assert bulk[cid]["observation_count"] == 0
    assert bulk[cid]["review_count"] == 0


# ---------------------------------------------------------------------------
# list_campaigns_with_fingerprint_status
# ---------------------------------------------------------------------------


def test_list_campaigns_with_fingerprint_status_has_fingerprint_flag(db_session):
    cid_fp = _create_campaign(db_session, representative_fingerprint_json='{"x":1}')
    cid_no_fp = _create_campaign(db_session)

    repo = EventRepository(db_session)
    items = {c["id"]: c for c in repo.list_campaigns_with_fingerprint_status()}

    assert items[cid_fp]["has_fingerprint"] is True
    assert items[cid_no_fp]["has_fingerprint"] is False


def test_list_campaigns_with_fingerprint_status_respects_limit(db_session):
    for _ in range(5):
        _create_campaign(db_session)
    repo = EventRepository(db_session)
    items = repo.list_campaigns_with_fingerprint_status(limit=3)
    assert len(items) == 3
