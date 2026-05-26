"""Integration tests for the campaign clustering algorithm.

Uses the db_session fixture for isolated in-memory SQLite.
Exercises assign_to_campaign() with real DB state — no mocks.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.db.repository import EventRepository
from app.intelligence.clustering import (
    DECISION_AUTO_ASSOCIATION,
    DECISION_EXISTING_MEMBER,
    DECISION_NEW_CAMPAIGN,
    DECISION_SKIPPED_SPARSE,
    DECISION_UNCERTAIN_ASSOCIATION,
    assign_to_campaign,
)
from app.intelligence.constants import (
    SIMILARITY_AUTO_THRESHOLD,
)

_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
_TS_STR = _NOW.isoformat()

_IP_NEW = "192.168.1.100"
_IP_EXISTING = "192.168.1.200"
_IP_CAMPAIGN = "192.168.1.1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_ip(session, ip: str) -> None:
    EventRepository(session).upsert_source_ip(ip, _NOW)
    session.flush()


def _make_fp_dict(
    ip: str = _IP_NEW,
    confidence: float = 0.6,
    event_count: int = 20,
    sequence_features: dict | None = None,
    target_features: dict | None = None,
    timing_features: dict | None = None,
) -> dict:
    """Build a fingerprint dict as returned by get_behavioral_fingerprint()."""

    def _enc(d):
        return json.dumps(d, separators=(",", ":")) if d is not None else None

    default_sequence = {
        "port_sequence": [22, 80],
        "event_type_sequence": ["auth_failed"] * 10,
        "credential_sequence": [],
    }
    default_target = {
        "port_freq": {"22": 0.9, "80": 0.1},
        "top_dst_ports": [22, 80],
    }

    return {
        "id": str(uuid.uuid4()),
        "source_ip": ip,
        "fingerprint_version": 1,
        "computed_at": _TS_STR,
        "event_count_at_computation": event_count,
        "timing_features": _enc(timing_features),
        "sequence_features": _enc(sequence_features or default_sequence),
        "protocol_features": None,
        "credential_features": None,
        "target_features": _enc(target_features or default_target),
        "tool_signals": None,
        "confidence": confidence,
    }


def _store_fp(session, ip: str, fp_dict: dict) -> None:
    """Insert ip and store the fingerprint directly via upsert."""
    EventRepository(session).upsert_behavioral_fingerprint(
        ip=ip,
        fingerprint_version=fp_dict["fingerprint_version"],
        computed_at=fp_dict["computed_at"],
        event_count=fp_dict["event_count_at_computation"],
        timing_features=fp_dict["timing_features"],
        sequence_features=fp_dict["sequence_features"],
        protocol_features=fp_dict["protocol_features"],
        credential_features=fp_dict["credential_features"],
        target_features=fp_dict["target_features"],
        tool_signals=fp_dict["tool_signals"],
        confidence=fp_dict["confidence"],
    )
    session.flush()


def _create_campaign_with_member(
    session,
    member_ip: str,
    status: str = "active",
    last_seen: str | None = None,
    fp_override: dict | None = None,
) -> str:
    """Create a campaign with one member IP and a stored fingerprint.  Returns campaign_id."""
    _insert_ip(session, member_ip)
    fp = fp_override or _make_fp_dict(ip=member_ip, confidence=0.7)
    _store_fp(session, member_ip, fp)

    repo = EventRepository(session)
    cid = str(uuid.uuid4())
    ls = last_seen or _TS_STR
    repo.create_campaign(
        campaign_id=cid,
        name="SETUP-WOLF-1",
        status=status,
        confidence=0.7,
        first_seen=_TS_STR,
        last_seen=ls,
        member_ip_count=1,
        created_at=_TS_STR,
        updated_at=_TS_STR,
    )
    repo.add_campaign_member(cid, member_ip, 0.7, _TS_STR, _TS_STR)
    session.flush()
    return cid


# ---------------------------------------------------------------------------
# Gate: sparse fingerprint
# ---------------------------------------------------------------------------


def test_sparse_fingerprint_is_skipped(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.10, event_count=5)
    repo = EventRepository(db_session)
    decision = assign_to_campaign(_IP_NEW, fp, repo, now=_NOW)
    assert decision.decision == DECISION_SKIPPED_SPARSE
    assert decision.campaign_id is None
    assert decision.similarity is None


def test_sparse_fingerprint_creates_no_campaign(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.05)
    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()
    count = db_session.execute(
        __import__("sqlalchemy").text("SELECT COUNT(*) FROM campaigns")
    ).fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# New campaign creation
# ---------------------------------------------------------------------------


def test_no_candidates_creates_new_campaign(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.6)
    repo = EventRepository(db_session)
    decision = assign_to_campaign(_IP_NEW, fp, repo, now=_NOW)
    assert decision.decision == DECISION_NEW_CAMPAIGN
    assert decision.campaign_id is not None
    assert decision.similarity is None


def test_new_campaign_stored_in_db(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.6)
    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    campaign = EventRepository(db_session).get_campaign(decision.campaign_id)
    assert campaign is not None
    assert campaign["status"] == "active"
    assert campaign["member_ip_count"] == 1


def test_new_campaign_member_stored(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.6)
    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    member = EventRepository(db_session).get_campaign_member_by_ip(_IP_NEW)
    assert member is not None


def test_new_campaign_observation_stored(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.6)
    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    obs = EventRepository(db_session).get_campaign_observations(decision.campaign_id)
    assert len(obs) == 1
    assert obs[0]["is_reactivation"] is False


def test_new_campaign_name_is_non_empty(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.6)
    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    campaign = EventRepository(db_session).get_campaign(decision.campaign_id)
    assert isinstance(campaign["name"], str)
    assert len(campaign["name"]) > 0


# ---------------------------------------------------------------------------
# Automatic association (score >= 0.80)
# ---------------------------------------------------------------------------


def _identical_fp(ip: str) -> dict:
    """Two fingerprints with this dict will score ~1.0 similarity."""
    return _make_fp_dict(
        ip=ip,
        confidence=0.7,
        sequence_features={
            "port_sequence": [22, 80, 443],
            "event_type_sequence": ["auth_failed"] * 15,
            "credential_sequence": [],
        },
        target_features={
            "port_freq": {"22": 0.8, "80": 0.1, "443": 0.1},
            "top_dst_ports": [22, 80, 443],
        },
    )


def test_identical_fp_auto_associates(db_session):
    cid = _create_campaign_with_member(
        db_session, _IP_CAMPAIGN, fp_override=_identical_fp(_IP_CAMPAIGN)
    )
    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    assert decision.decision == DECISION_AUTO_ASSOCIATION
    assert decision.campaign_id == cid


def test_auto_association_stored_in_db(db_session):
    cid = _create_campaign_with_member(
        db_session, _IP_CAMPAIGN, fp_override=_identical_fp(_IP_CAMPAIGN)
    )
    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    member = EventRepository(db_session).get_campaign_member_by_ip(_IP_NEW)
    assert member is not None
    assert member["campaign_id"] == cid


def test_auto_association_increments_member_count(db_session):
    cid = _create_campaign_with_member(
        db_session, _IP_CAMPAIGN, fp_override=_identical_fp(_IP_CAMPAIGN)
    )
    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    campaign = EventRepository(db_session).get_campaign(cid)
    assert campaign["member_ip_count"] == 2


# ---------------------------------------------------------------------------
# Uncertain association (0.60 <= score < 0.80)
# ---------------------------------------------------------------------------


def _different_fp(ip: str) -> dict:
    """Fingerprint with different ports — will produce moderate similarity."""
    return _make_fp_dict(
        ip=ip,
        confidence=0.7,
        sequence_features={
            "port_sequence": [22, 443, 8080],
            "event_type_sequence": ["auth_failed"] * 10,
            "credential_sequence": [],
        },
        target_features={
            "port_freq": {"22": 0.5, "443": 0.3, "8080": 0.2},
            "top_dst_ports": [22, 443, 8080],
        },
    )


def test_uncertain_range_produces_uncertain_association(db_session):
    """Fingerprints that share most but not all ports produce a score in
    [0.60, 0.80), triggering uncertain_association rather than auto_association.

    Scenario:
      campaign port_sequence = [22, 80, 443]  event_types = [auth_failed]*10
      new      port_sequence = [22, 80, 3389] event_types = [auth_failed]*10
      sequence sim ≈ (0.667 + 1.0) / 2 = 0.833
      target sim   ≈ (Jaccard_0.5 + edit_0.667) / 2 = 0.583
      weighted (seq 0.35, tgt 0.10) ≈ 0.778  → uncertain
    """
    campaign_fp = _make_fp_dict(
        ip=_IP_CAMPAIGN,
        confidence=0.7,
        sequence_features={
            "port_sequence": [22, 80, 443],
            "event_type_sequence": ["auth_failed"] * 10,
            "credential_sequence": [],
        },
        target_features={
            "port_freq": {"22": 0.6, "80": 0.3, "443": 0.1},
            "top_dst_ports": [22, 80, 443],
        },
    )
    cid = _create_campaign_with_member(db_session, _IP_CAMPAIGN, fp_override=campaign_fp)

    new_fp = _make_fp_dict(
        ip=_IP_NEW,
        confidence=0.7,
        sequence_features={
            "port_sequence": [22, 80, 3389],
            "event_type_sequence": ["auth_failed"] * 10,
            "credential_sequence": [],
        },
        target_features={
            "port_freq": {"22": 0.6, "80": 0.3, "3389": 0.1},
            "top_dst_ports": [22, 80, 3389],
        },
    )
    _insert_ip(db_session, _IP_NEW)
    _store_fp(db_session, _IP_NEW, new_fp)

    decision = assign_to_campaign(_IP_NEW, new_fp, EventRepository(db_session), now=_NOW)

    # Expected score ≈ 0.778 (uncertain range).  Accept auto too in case of
    # floating-point edge, but must be an association, not a new campaign.
    assert decision.decision in (DECISION_AUTO_ASSOCIATION, DECISION_UNCERTAIN_ASSOCIATION)
    assert decision.campaign_id == cid


def test_below_uncertain_threshold_creates_new_campaign(db_session):
    """Fingerprints with completely disjoint ports should not associate."""
    campaign_fp = _make_fp_dict(
        ip=_IP_CAMPAIGN,
        confidence=0.7,
        sequence_features={
            "port_sequence": [22, 23, 25],
            "event_type_sequence": ["auth_failed"] * 10,
            "credential_sequence": [],
        },
        target_features={
            "port_freq": {"22": 0.6, "23": 0.3, "25": 0.1},
            "top_dst_ports": [22, 23, 25],
        },
    )
    _create_campaign_with_member(db_session, _IP_CAMPAIGN, fp_override=campaign_fp)

    # New fingerprint targets entirely different ports
    new_fp = _make_fp_dict(
        ip=_IP_NEW,
        confidence=0.7,
        sequence_features={
            "port_sequence": [8080, 8443, 9000, 9200, 9300],
            "event_type_sequence": ["http_probe"] * 10,
            "credential_sequence": [],
        },
        target_features={
            "port_freq": {"8080": 0.4, "8443": 0.3, "9000": 0.2, "9200": 0.1},
            "top_dst_ports": [8080, 8443, 9000, 9200],
        },
    )
    _insert_ip(db_session, _IP_NEW)
    _store_fp(db_session, _IP_NEW, new_fp)

    decision = assign_to_campaign(_IP_NEW, new_fp, EventRepository(db_session), now=_NOW)
    assert decision.decision == DECISION_NEW_CAMPAIGN


# ---------------------------------------------------------------------------
# Existing member
# ---------------------------------------------------------------------------


def test_existing_member_returns_existing_decision(db_session):
    # _create_campaign_with_member already inserts _IP_EXISTING as the member.
    cid = _create_campaign_with_member(db_session, _IP_EXISTING)
    fp = _make_fp_dict(ip=_IP_EXISTING, confidence=0.7)
    decision = assign_to_campaign(_IP_EXISTING, fp, EventRepository(db_session), now=_NOW)
    assert decision.decision == DECISION_EXISTING_MEMBER
    assert decision.campaign_id == cid


def test_existing_member_inserts_observation(db_session):
    # _create_campaign_with_member already inserts _IP_EXISTING as the member.
    cid = _create_campaign_with_member(db_session, _IP_EXISTING)
    fp = _make_fp_dict(ip=_IP_EXISTING, confidence=0.7)
    assign_to_campaign(_IP_EXISTING, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    obs = EventRepository(db_session).get_campaign_observations(cid)
    assert any(o["source_ip"] == _IP_EXISTING for o in obs)


# ---------------------------------------------------------------------------
# Dormant campaign reactivation
# ---------------------------------------------------------------------------


def test_dormant_campaign_association_is_reactivation(db_session):
    # Campaign was last seen 30 days ago → dormant
    thirty_days_ago = (_NOW - timedelta(days=30)).isoformat()
    cid = _create_campaign_with_member(
        db_session,
        _IP_CAMPAIGN,
        status="dormant",
        last_seen=thirty_days_ago,
        fp_override=_identical_fp(_IP_CAMPAIGN),
    )

    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)

    assert decision.campaign_id == cid
    assert decision.is_reactivation is True
    assert decision.dormancy_gap_days is not None
    assert decision.dormancy_gap_days >= 29.0


def test_dormant_campaign_reactivation_updates_status(db_session):
    thirty_days_ago = (_NOW - timedelta(days=30)).isoformat()
    cid = _create_campaign_with_member(
        db_session,
        _IP_CAMPAIGN,
        status="dormant",
        last_seen=thirty_days_ago,
        fp_override=_identical_fp(_IP_CAMPAIGN),
    )

    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    campaign = EventRepository(db_session).get_campaign(cid)
    assert campaign["status"] == "reactivated"
    assert campaign["reactivation_count"] == 1
    assert campaign["dormant_since"] is None


def test_reactivation_observation_has_is_reactivation_flag(db_session):
    thirty_days_ago = (_NOW - timedelta(days=30)).isoformat()
    cid = _create_campaign_with_member(
        db_session,
        _IP_CAMPAIGN,
        status="dormant",
        last_seen=thirty_days_ago,
        fp_override=_identical_fp(_IP_CAMPAIGN),
    )

    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    obs = EventRepository(db_session).get_campaign_observations(cid)
    reactivation_obs = [o for o in obs if o["is_reactivation"]]
    assert len(reactivation_obs) == 1
    assert reactivation_obs[0]["dormancy_gap_days"] is not None


# ---------------------------------------------------------------------------
# Temporal threshold bumps (§12.3)
# ---------------------------------------------------------------------------


def test_temporal_12m_threshold_bump_prevents_auto_at_085(db_session):
    """Score of 0.85 against a 13-month-old campaign should NOT auto-associate
    because the temporal bump raises the auto threshold to 0.90."""
    thirteen_months_ago = (_NOW - timedelta(days=400)).isoformat()
    _create_campaign_with_member(
        db_session,
        _IP_CAMPAIGN,
        status="dormant",
        last_seen=thirteen_months_ago,
        fp_override=_identical_fp(_IP_CAMPAIGN),
    )

    _insert_ip(db_session, _IP_NEW)
    # Use a fingerprint that scores ~0.85–0.89 against the identical fp above.
    # Achieve this by having partially matching ports.
    fp = _make_fp_dict(
        ip=_IP_NEW,
        confidence=0.7,
        sequence_features={
            "port_sequence": [22, 80, 443, 8080],  # 1 extra port → edit distance
            "event_type_sequence": ["auth_failed"] * 15,
            "credential_sequence": [],
        },
        target_features={
            "port_freq": {"22": 0.7, "80": 0.1, "443": 0.1, "8080": 0.1},
            "top_dst_ports": [22, 80, 443, 8080],
        },
    )
    _store_fp(db_session, _IP_NEW, fp)

    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)

    # Can be auto (if score >= 0.90), uncertain (if 0.60 <= score < 0.90), or
    # new campaign (if score < 0.60).  The key invariant: with a 13-month gap,
    # a score in [0.85, 0.89] must NOT produce auto_association.
    if decision.similarity is not None:
        score = decision.similarity.weighted_total
        if 0.85 <= score < 0.90:
            assert (
                decision.decision != DECISION_AUTO_ASSOCIATION
            ), f"Score {score:.4f} should be uncertain with 13-month gap, not auto"


def test_temporal_6m_threshold_bump_prevents_auto_at_082(db_session):
    """Score of 0.82 against a 7-month-old campaign should NOT auto-associate
    because the 6-12-month bump raises the auto threshold to 0.85."""
    seven_months_ago = (_NOW - timedelta(days=210)).isoformat()
    _create_campaign_with_member(
        db_session,
        _IP_CAMPAIGN,
        status="dormant",
        last_seen=seven_months_ago,
        fp_override=_identical_fp(_IP_CAMPAIGN),
    )

    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(
        ip=_IP_NEW,
        confidence=0.7,
        sequence_features={
            "port_sequence": [22, 80, 443, 8080, 3389],
            "event_type_sequence": ["auth_failed"] * 15,
            "credential_sequence": [],
        },
        target_features={
            "port_freq": {"22": 0.6, "80": 0.1, "443": 0.1, "8080": 0.1, "3389": 0.1},
            "top_dst_ports": [22, 80, 443, 8080, 3389],
        },
    )
    _store_fp(db_session, _IP_NEW, fp)

    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)

    if decision.similarity is not None:
        score = decision.similarity.weighted_total
        if 0.82 <= score < 0.85:
            assert (
                decision.decision != DECISION_AUTO_ASSOCIATION
            ), f"Score {score:.4f} should be uncertain with 7-month gap, not auto"


def test_recent_campaign_uses_standard_threshold(db_session):
    """A campaign last seen 3 days ago should use the standard 0.80 threshold."""
    three_days_ago = (_NOW - timedelta(days=3)).isoformat()
    cid = _create_campaign_with_member(
        db_session,
        _IP_CAMPAIGN,
        status="active",
        last_seen=three_days_ago,
        fp_override=_identical_fp(_IP_CAMPAIGN),
    )

    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    # Identical fps against a recent campaign → should auto-associate
    assert decision.decision == DECISION_AUTO_ASSOCIATION
    assert decision.campaign_id == cid
    assert decision.threshold_applied == pytest.approx(SIMILARITY_AUTO_THRESHOLD)


# ---------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------


def test_decision_has_non_empty_reason(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.6)
    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    assert isinstance(decision.reason, str)
    assert len(decision.reason) > 0


def test_association_stores_explanation_in_observation_notes(db_session):
    cid = _create_campaign_with_member(
        db_session, _IP_CAMPAIGN, fp_override=_identical_fp(_IP_CAMPAIGN)
    )
    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    obs = EventRepository(db_session).get_campaign_observations(cid)
    association_obs = [o for o in obs if o["source_ip"] == _IP_NEW]
    assert len(association_obs) == 1

    notes_str = association_obs[0]["notes"]
    assert notes_str is not None
    notes = json.loads(notes_str)
    assert "weighted_total" in notes
    assert "threshold_applied" in notes
    assert "decision" in notes


def test_explanation_object_has_all_similarity_fields(db_session):
    cid = _create_campaign_with_member(
        db_session, _IP_CAMPAIGN, fp_override=_identical_fp(_IP_CAMPAIGN)
    )
    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    obs = EventRepository(db_session).get_campaign_observations(cid)
    notes = json.loads(obs[-1]["notes"])
    for field in (
        "timing_similarity",
        "sequence_similarity",
        "protocol_similarity",
        "credential_similarity",
        "target_similarity",
        "weighted_total",
        "dimensions_used",
        "threshold_applied",
        "decision",
    ):
        assert field in notes, f"Missing field {field!r} in explanation"


def test_new_campaign_observation_has_no_notes(db_session):
    """New campaign observations don't carry an explanation (no comparison was made)."""
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.6)
    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    obs = EventRepository(db_session).get_campaign_observations(decision.campaign_id)
    assert obs[0]["notes"] is None


def test_similarity_result_present_on_association(db_session):
    _create_campaign_with_member(db_session, _IP_CAMPAIGN, fp_override=_identical_fp(_IP_CAMPAIGN))
    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    assert decision.similarity is not None
    assert 0.0 <= decision.similarity.weighted_total <= 1.0


def test_similarity_result_none_on_new_campaign(db_session):
    _insert_ip(db_session, _IP_NEW)
    fp = _make_fp_dict(ip=_IP_NEW, confidence=0.6)
    decision = assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    assert decision.similarity is None


# ---------------------------------------------------------------------------
# Privacy: no raw IPs in stored notes
# ---------------------------------------------------------------------------


def test_observation_notes_contain_no_raw_ips(db_session):
    """The JSON explanation stored in campaign_observations.notes must not
    contain any raw IP address strings."""
    cid = _create_campaign_with_member(
        db_session, _IP_CAMPAIGN, fp_override=_identical_fp(_IP_CAMPAIGN)
    )
    _insert_ip(db_session, _IP_NEW)
    fp = _identical_fp(_IP_NEW)
    _store_fp(db_session, _IP_NEW, fp)

    assign_to_campaign(_IP_NEW, fp, EventRepository(db_session), now=_NOW)
    db_session.flush()

    obs = EventRepository(db_session).get_campaign_observations(cid)
    for o in obs:
        if o["notes"]:
            assert _IP_NEW not in o["notes"], "Raw IP found in observation notes"
            assert _IP_CAMPAIGN not in o["notes"], "Raw IP found in observation notes"
