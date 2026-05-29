"""DB tests for WeightProfileRepository — Phase 7 Group A.

Tests hit a real in-memory SQLite database via the db_session fixture.

Coverage:
  - get_weight_profile returns None when no row exists
  - upsert_weight_profile inserts a new row
  - upsert_weight_profile updates an existing row (ON CONFLICT)
  - list_weight_profiles returns all profiles
  - weight values are persisted and retrieved correctly
  - adjustment_log_json is persisted and parsed as list
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

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


_DEFAULT_WEIGHTS = {
    "timing": 0.22,
    "sequence": 0.37,
    "protocol": 0.25,
    "credential": 0.09,
    "target": 0.07,
}

_LOG_ENTRY = {
    "observation_id": str(uuid.uuid4()),
    "review_decision": "analyst_confirmed",
    "reviewed_at": "2026-05-29T10:00:00+00:00",
    "dimension_adjustments": {
        "timing": 0.02,
        "sequence": 0.02,
        "protocol": 0.0,
        "credential": 0.0,
        "target": 0.0,
    },
    "weights_after": _DEFAULT_WEIGHTS,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_weight_profile_returns_none_when_absent(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    result = repo.get_weight_profile(cid)
    assert result is None


def test_upsert_creates_profile(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    now = datetime.now(UTC).isoformat()
    repo.upsert_weight_profile(
        campaign_id=cid,
        weights=_DEFAULT_WEIGHTS,
        review_count=3,
        confirmed_count=3,
        denied_count=0,
        adjustment_log=[_LOG_ENTRY],
        computed_at=now,
        updated_at=now,
    )
    db_session.flush()

    profile = repo.get_weight_profile(cid)
    assert profile is not None
    assert profile["campaign_id"] == cid
    assert profile["review_count"] == 3
    assert profile["confirmed_count"] == 3
    assert profile["denied_count"] == 0
    assert len(profile["adjustment_log"]) == 1
    assert profile["adjustment_log"][0]["observation_id"] == _LOG_ENTRY["observation_id"]


def test_upsert_updates_existing_profile(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    now = datetime.now(UTC).isoformat()

    repo.upsert_weight_profile(
        campaign_id=cid,
        weights=_DEFAULT_WEIGHTS,
        review_count=3,
        confirmed_count=3,
        denied_count=0,
        adjustment_log=[_LOG_ENTRY],
        computed_at=now,
        updated_at=now,
    )
    db_session.flush()

    new_weights = {k: round(v + 0.01, 4) for k, v in _DEFAULT_WEIGHTS.items()}
    total = sum(new_weights.values())
    new_weights = {k: round(v / total, 8) for k, v in new_weights.items()}

    repo.upsert_weight_profile(
        campaign_id=cid,
        weights=new_weights,
        review_count=5,
        confirmed_count=4,
        denied_count=1,
        adjustment_log=[_LOG_ENTRY, _LOG_ENTRY],
        computed_at=now,
        updated_at=now,
    )
    db_session.flush()

    profile = repo.get_weight_profile(cid)
    assert profile["review_count"] == 5
    assert profile["confirmed_count"] == 4
    assert len(profile["adjustment_log"]) == 2


def test_weights_persist_with_correct_values(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    now = datetime.now(UTC).isoformat()
    repo.upsert_weight_profile(
        campaign_id=cid,
        weights=_DEFAULT_WEIGHTS,
        review_count=3,
        confirmed_count=3,
        denied_count=0,
        adjustment_log=[],
        computed_at=now,
        updated_at=now,
    )
    db_session.flush()

    profile = repo.get_weight_profile(cid)
    w = profile["weights"]
    assert w["timing"] == pytest.approx(_DEFAULT_WEIGHTS["timing"])
    assert w["sequence"] == pytest.approx(_DEFAULT_WEIGHTS["sequence"])
    assert w["protocol"] == pytest.approx(_DEFAULT_WEIGHTS["protocol"])
    assert w["credential"] == pytest.approx(_DEFAULT_WEIGHTS["credential"])
    assert w["target"] == pytest.approx(_DEFAULT_WEIGHTS["target"])


def test_get_weight_profile_weights_only_returns_dict(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    now = datetime.now(UTC).isoformat()
    repo.upsert_weight_profile(
        campaign_id=cid,
        weights=_DEFAULT_WEIGHTS,
        review_count=3,
        confirmed_count=3,
        denied_count=0,
        adjustment_log=[],
        computed_at=now,
        updated_at=now,
    )
    db_session.flush()

    weights = repo.get_weight_profile_weights_only(cid)
    assert weights is not None
    assert set(weights.keys()) == {"timing", "sequence", "protocol", "credential", "target"}


def test_get_weight_profile_weights_only_returns_none_when_absent(db_session):
    cid = _create_campaign(db_session)
    repo = EventRepository(db_session)
    assert repo.get_weight_profile_weights_only(cid) is None


def test_list_weight_profiles_returns_all(db_session):
    repo = EventRepository(db_session)
    now = datetime.now(UTC).isoformat()

    cids = [_create_campaign(db_session) for _ in range(3)]
    for cid in cids:
        repo.upsert_weight_profile(
            campaign_id=cid,
            weights=_DEFAULT_WEIGHTS,
            review_count=3,
            confirmed_count=3,
            denied_count=0,
            adjustment_log=[],
            computed_at=now,
            updated_at=now,
        )
    db_session.flush()

    profiles = repo.list_weight_profiles()
    returned_cids = {p["campaign_id"] for p in profiles}
    assert set(cids).issubset(returned_cids)
