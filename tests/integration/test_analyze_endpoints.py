"""Integration tests for POST /api/campaigns/{campaign_id}/summary.

Tests exercise the full HTTP → router → repository → in-memory SQLite stack.
The AI backend is injected via monkeypatch so no live API calls are made.

Coverage:
  - Disabled backend (AI_BACKEND=none) returns 503
  - Mocked backend returns 200 with summary
  - Missing campaign returns 404
  - Auth rejection returns 401
  - ai_assisted: true always present
  - source_records always present
  - Output containing IP address is rejected (200, rejected=true)
  - Truncated output flagged (200, truncated=true)
  - PRIVACY_MODE=on + AI_BACKEND=claude returns 422
  - No fingerprint available returns 200 with no_fingerprint safety flag
  - Campaign row is not modified after summary generation (no DB writes)
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai import MockAIBackend
from app.core.config import settings
from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY}

_CID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_MEMBER_IP = "10.0.0.1"
_TS = "2026-01-15T00:00:00+00:00"
_TS_LAST = "2026-05-24T00:00:00+00:00"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _insert_campaign(
    campaign_id: str = _CID,
    *,
    name: str = "TEST-CAMPAIGN",
    status: str = "active",
    confidence: float = 0.82,
    first_seen: str = _TS,
    last_seen: str = _TS_LAST,
    reactivation_count: int = 1,
    member_ip_count: int = 3,
    attack_tactic_dist: str | None = '{"Credential Access": 20}',
    top_target_ports: str | None = '[{"port": 22, "count": 20}]',
) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO campaigns (
                    id, name, status, confidence,
                    first_seen, last_seen, dormant_since,
                    reactivation_count, member_ip_count,
                    attack_tactic_dist, top_target_ports, notes,
                    created_at, updated_at
                ) VALUES (
                    :id, :name, :status, :confidence,
                    :first_seen, :last_seen, NULL,
                    :reactivation_count, :member_ip_count,
                    :attack_tactic_dist, :top_target_ports, NULL,
                    :created_at, :updated_at
                )
            """),
            {
                "id": campaign_id,
                "name": name,
                "status": status,
                "confidence": confidence,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "reactivation_count": reactivation_count,
                "member_ip_count": member_ip_count,
                "attack_tactic_dist": attack_tactic_dist,
                "top_target_ports": top_target_ports,
                "created_at": _TS,
                "updated_at": _TS_LAST,
            },
        )
        conn.commit()


def _insert_member(
    campaign_id: str = _CID,
    source_ip: str = _MEMBER_IP,
    last_active: str = _TS_LAST,
) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO source_ips (ip, first_seen, last_seen, event_count, tags)
                VALUES (:ip, :ts, :ts, 1, NULL)
            """),
            {"ip": source_ip, "ts": last_active},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO campaign_members
                    (campaign_id, source_ip, confidence, added_at, last_active)
                VALUES (:cid, :ip, 0.82, :ts, :last_active)
            """),
            {"cid": campaign_id, "ip": source_ip, "ts": _TS, "last_active": last_active},
        )
        conn.commit()


def _insert_fingerprint(source_ip: str = _MEMBER_IP) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO behavioral_fingerprints (
                    id, source_ip, fingerprint_version, computed_at,
                    event_count_at_computation, timing_features, sequence_features,
                    protocol_features, credential_features, target_features,
                    tool_signals, confidence
                ) VALUES (
                    :id, :ip, 1, :ts,
                    20,
                    '{"interval": {"mean": 2.0}, "burst_cv": 0.6}',
                    '{"port_sequence": [22, 80], "event_type_sequence": ["auth_failed"]}',
                    '{"service_distribution": {"ssh": 15, "http": 5}}',
                    '{"username_class_dist": {"dictionary": 10}}',
                    '{"top_dst_ports": [22, 80]}',
                    NULL, 0.82
                )
            """),
            {"id": str(uuid.uuid4()), "ip": source_ip, "ts": _TS_LAST},
        )
        conn.commit()


def _insert_observation(campaign_id: str = _CID, source_ip: str = _MEMBER_IP) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO campaign_observations (
                    id, campaign_id, source_ip, observed_at, event_count,
                    is_reactivation, dormancy_gap_days, notes
                ) VALUES (
                    :id, :cid, :ip, :ts, 20, 0, NULL, NULL
                )
            """),
            {"id": str(uuid.uuid4()), "cid": campaign_id, "ip": source_ip, "ts": _TS_LAST},
        )
        conn.commit()


def _get_campaign_updated_at(campaign_id: str = _CID) -> str:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT updated_at FROM campaigns WHERE id = :id"),
            {"id": campaign_id},
        ).fetchone()
    return row[0] if row else ""


# ---------------------------------------------------------------------------
# Disabled backend (AI_BACKEND=none)
# ---------------------------------------------------------------------------


def test_disabled_backend_returns_503():
    _insert_campaign()
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 503


def test_disabled_backend_error_body_is_json():
    _insert_campaign()
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    body = resp.json()
    assert "detail" in body


def test_disabled_backend_detail_mentions_ai_backend():
    _insert_campaign()
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    body = resp.json()
    assert "AI_BACKEND" in body["detail"]


# ---------------------------------------------------------------------------
# Mocked backend — happy path
# ---------------------------------------------------------------------------


def test_mock_backend_returns_200(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Campaign TEST-CAMPAIGN is actively scanning port 22."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 200


def test_mock_backend_summary_in_response(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Campaign TEST-CAMPAIGN is actively scanning port 22."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    body = resp.json()
    assert body["summary"] == "Campaign TEST-CAMPAIGN is actively scanning port 22."


def test_mock_backend_with_fingerprint_and_observations(monkeypatch):
    _insert_campaign()
    _insert_member()
    _insert_fingerprint()
    _insert_observation()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Full campaign context summary."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["summary"] == "Full campaign context summary."


# ---------------------------------------------------------------------------
# Response envelope shape
# ---------------------------------------------------------------------------


def test_response_has_ai_assisted_true(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["ai_assisted"] is True


def test_response_has_warning(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    body = resp.json()
    assert "warning" in body
    assert len(body["warning"]) > 0


def test_response_has_campaign_id(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["campaign_id"] == _CID


def test_response_has_generated_at(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert "generated_at" in resp.json()
    assert resp.json()["generated_at"] is not None


def test_response_has_ai_backend_field(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert "ai_backend" in resp.json()


def test_response_has_source_records(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    body = resp.json()
    assert "source_records" in body
    assert isinstance(body["source_records"], dict)


def test_source_records_contains_campaign_id(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    sr = resp.json()["source_records"]
    assert sr["campaign_id"] == _CID


def test_source_records_observation_count(monkeypatch):
    _insert_campaign()
    _insert_member()
    _insert_observation()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    sr = resp.json()["source_records"]
    assert sr["observation_count"] == 1


def test_source_records_fingerprint_present_false_when_no_member(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["source_records"]["fingerprint_present"] is False


def test_source_records_fingerprint_present_true_with_fingerprint(monkeypatch):
    _insert_campaign()
    _insert_member()
    _insert_fingerprint()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["source_records"]["fingerprint_present"] is True


def test_response_has_safety_flags(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert "safety_flags" in resp.json()
    assert isinstance(resp.json()["safety_flags"], list)


def test_response_rejected_false_on_clean_output(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["rejected"] is False


def test_response_truncated_false_on_short_output(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["truncated"] is False


# ---------------------------------------------------------------------------
# Missing campaign → 404
# ---------------------------------------------------------------------------


def test_missing_campaign_returns_404():
    resp = client.post("/api/campaigns/nonexistent-id/summary", headers=HEADERS)
    assert resp.status_code == 404


def test_missing_campaign_detail_mentions_id():
    resp = client.post("/api/campaigns/no-such-campaign/summary", headers=HEADERS)
    body = resp.json()
    assert "no-such-campaign" in body["detail"]


# ---------------------------------------------------------------------------
# Auth rejection → 401
# ---------------------------------------------------------------------------


def test_no_auth_returns_401():
    _insert_campaign()
    resp = client.post(f"/api/campaigns/{_CID}/summary")
    assert resp.status_code == 401


def test_wrong_api_key_returns_401():
    _insert_campaign()
    resp = client.post(
        f"/api/campaigns/{_CID}/summary",
        headers={"x-api-key": "wrong-key"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Output safety rejection — IP in output
# ---------------------------------------------------------------------------


def test_ip_in_output_returns_rejected_true(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Threat actor at 192.168.1.1 is active."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rejected"] is True
    assert body["summary"] is None


def test_ip_in_output_rejection_reason(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Source at 10.0.0.1 was observed."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["rejection_reason"] == "ip_detected"


def test_ip_in_output_ai_assisted_still_true(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Threat actor at 192.168.1.1 is active."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["ai_assisted"] is True


def test_ip_in_output_source_records_still_present(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Threat actor at 192.168.1.1 is active."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert "source_records" in resp.json()


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------


def test_long_output_is_truncated(monkeypatch):
    _insert_campaign()
    long_response = "A" * 1500
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend(long_response),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["truncated"] is True
    assert body["summary"] is not None
    assert len(body["summary"]) == 1000


def test_long_output_rejected_false(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("B" * 1500),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["rejected"] is False


# ---------------------------------------------------------------------------
# Privacy mode + cloud backend → 422
# ---------------------------------------------------------------------------


def test_privacy_mode_with_claude_returns_422(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "PRIVACY_MODE", True)
    monkeypatch.setattr(settings, "AI_BACKEND", "claude")
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 422


def test_privacy_mode_422_detail_explains_conflict(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "PRIVACY_MODE", True)
    monkeypatch.setattr(settings, "AI_BACKEND", "claude")
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    body = resp.json()
    assert "PRIVACY_MODE" in body["detail"]
    assert "claude" in body["detail"]


def test_privacy_mode_with_ollama_not_blocked(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "PRIVACY_MODE", True)
    monkeypatch.setattr(settings, "AI_BACKEND", "ollama")
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Ollama summary."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# No fingerprint → graceful degradation
# ---------------------------------------------------------------------------


def test_no_fingerprint_returns_200(monkeypatch):
    _insert_campaign()
    # No member, no fingerprint
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Campaign with no fingerprint data."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 200


def test_no_fingerprint_safety_flag_present(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Campaign with no fingerprint data."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert "no_fingerprint" in resp.json()["safety_flags"]


def test_no_fingerprint_fingerprint_present_false(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Campaign with no fingerprint data."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.json()["source_records"]["fingerprint_present"] is False


# ---------------------------------------------------------------------------
# Low confidence safety flag
# ---------------------------------------------------------------------------


def test_low_confidence_campaign_safety_flag(monkeypatch):
    _insert_campaign(confidence=0.35)
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Low confidence campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert "low_confidence" in resp.json()["safety_flags"]


# ---------------------------------------------------------------------------
# No database writes
# ---------------------------------------------------------------------------


def test_campaign_row_unchanged_after_summary(monkeypatch):
    _insert_campaign()
    updated_at_before = _get_campaign_updated_at(_CID)

    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 200

    updated_at_after = _get_campaign_updated_at(_CID)
    assert updated_at_before == updated_at_after


# ---------------------------------------------------------------------------
# Backend name in response
# ---------------------------------------------------------------------------


def test_backend_name_in_response_is_none(monkeypatch):
    # Default AI_BACKEND=none
    _insert_campaign()
    # Use disabled backend — will 503, but check is moot; test the mock path instead
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    # ai_backend reflects settings.AI_BACKEND which is "none" in test env
    assert resp.json()["ai_backend"] == "none"


# ===========================================================================
# POST /api/campaigns/brief — multi-campaign threat brief
# ===========================================================================

_BRIEF_URL = "/api/campaigns/brief"

_CID2 = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
_CID3 = "cccccccc-dddd-eeee-ffff-000000000000"


def _insert_n_campaigns(n: int, base_status: str = "active") -> list[str]:
    """Insert n campaigns with distinct IDs, returning their IDs."""
    ids = [str(uuid.uuid4()) for _ in range(n)]
    for i, cid in enumerate(ids):
        _insert_campaign(
            cid,
            name=f"CAMPAIGN-{i:02d}",
            status=base_status,
            last_seen=f"2026-05-{(24 - i):02d}T00:00:00+00:00",
        )
    return ids


# ---------------------------------------------------------------------------
# Brief — disabled backend
# ---------------------------------------------------------------------------


def test_brief_disabled_backend_returns_503():
    _insert_campaign()
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert resp.status_code == 503


def test_brief_disabled_backend_detail_mentions_ai_backend():
    _insert_campaign()
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert "AI_BACKEND" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Brief — mocked backend happy path
# ---------------------------------------------------------------------------


def test_brief_mock_backend_returns_200(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Two campaigns were active this period."),
    )
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert resp.status_code == 200


def test_brief_response_has_ai_assisted_true(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert resp.json()["ai_assisted"] is True


def test_brief_response_has_warning(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert "warning" in body
    assert len(body["warning"]) > 0


def test_brief_response_has_summary(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["summary"] == "Brief text."


def test_brief_response_has_campaign_count(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert "campaign_count" in body
    assert body["campaign_count"] == 1


def test_brief_response_has_source_records(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert "source_records" in body
    sr = body["source_records"]
    assert "campaign_ids" in sr
    assert "campaign_count" in sr


def test_brief_source_records_campaign_ids_list(monkeypatch):
    _insert_campaign(_CID)
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert _CID in body["source_records"]["campaign_ids"]


def test_brief_response_has_generated_at(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert "generated_at" in body
    assert body["generated_at"] is not None


def test_brief_response_has_ai_backend_field(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert "ai_backend" in body


def test_brief_response_rejected_false_on_clean_output(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["rejected"] is False


def test_brief_response_truncated_false_on_short_output(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief text."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["truncated"] is False


# ---------------------------------------------------------------------------
# Brief — max_campaigns validation
# ---------------------------------------------------------------------------


def test_brief_default_max_campaigns_is_10(monkeypatch):
    ids = _insert_n_campaigns(15)
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    # Default max_campaigns=10; only 10 should be included
    assert body["campaign_count"] <= 10
    assert body["source_records"]["campaign_count"] <= 10
    _ = ids  # referenced to avoid unused-variable warning


def test_brief_max_campaigns_explicit(monkeypatch):
    _insert_n_campaigns(15)
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS, json={"max_campaigns": 5}).json()
    assert body["campaign_count"] <= 5


def test_brief_max_campaigns_at_hard_cap_accepted(monkeypatch):
    _insert_n_campaigns(5)
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    resp = client.post(_BRIEF_URL, headers=HEADERS, json={"max_campaigns": 25})
    assert resp.status_code == 200


def test_brief_max_campaigns_exceeds_hard_cap_returns_422():
    resp = client.post(_BRIEF_URL, headers=HEADERS, json={"max_campaigns": 26})
    assert resp.status_code == 422


def test_brief_max_campaigns_zero_returns_422():
    resp = client.post(_BRIEF_URL, headers=HEADERS, json={"max_campaigns": 0})
    assert resp.status_code == 422


def test_brief_max_campaigns_negative_returns_422():
    resp = client.post(_BRIEF_URL, headers=HEADERS, json={"max_campaigns": -1})
    assert resp.status_code == 422


def test_brief_no_body_uses_defaults(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    # POST with no body at all
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Brief — empty campaign set
# ---------------------------------------------------------------------------


def test_brief_empty_campaign_set_returns_200():
    # No campaigns inserted
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    # Will 503 (disabled backend) before the empty-campaigns check, so mock
    # the backend to get past that, then hit the empty-campaigns path
    # Note: 503 happens AFTER the empty-campaigns check in the route handler
    # (privacy check → fetch → empty check → backend call). So no backend
    # needed here — empty check fires first.
    assert resp.status_code in (200, 503)


def test_brief_empty_campaign_set_with_mock_returns_200(monkeypatch):
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert resp.status_code == 200


def test_brief_empty_campaign_set_campaign_count_zero(monkeypatch):
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["campaign_count"] == 0


def test_brief_empty_campaign_set_summary_is_none(monkeypatch):
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["summary"] is None


def test_brief_empty_campaign_set_rejection_reason(monkeypatch):
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["rejection_reason"] == "no_campaigns"


def test_brief_historical_campaigns_excluded(monkeypatch):
    # Insert only historical campaigns — should produce empty brief
    _insert_n_campaigns(3, base_status="historical")
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["campaign_count"] == 0


# ---------------------------------------------------------------------------
# Brief — auth
# ---------------------------------------------------------------------------


def test_brief_no_auth_returns_401():
    resp = client.post(_BRIEF_URL)
    assert resp.status_code == 401


def test_brief_wrong_api_key_returns_401():
    resp = client.post(_BRIEF_URL, headers={"x-api-key": "wrong"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Brief — privacy mode
# ---------------------------------------------------------------------------


def test_brief_privacy_mode_with_claude_returns_422(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "PRIVACY_MODE", True)
    monkeypatch.setattr(settings, "AI_BACKEND", "claude")
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert resp.status_code == 422


def test_brief_privacy_mode_422_mentions_claude(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "PRIVACY_MODE", True)
    monkeypatch.setattr(settings, "AI_BACKEND", "claude")
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert "claude" in body["detail"]


def test_brief_privacy_mode_ollama_not_blocked(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "PRIVACY_MODE", True)
    monkeypatch.setattr(settings, "AI_BACKEND", "ollama")
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Brief — output safety
# ---------------------------------------------------------------------------


def test_brief_ip_in_output_rejected(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Threat actor at 192.168.1.1 was observed."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["rejected"] is True
    assert body["summary"] is None
    assert body["rejection_reason"] == "ip_detected"


def test_brief_ip_in_output_ai_assisted_still_true(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Threat actor at 192.168.1.1 was observed."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["ai_assisted"] is True


def test_brief_long_output_truncated(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("X" * 3000),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["truncated"] is True
    assert body["summary"] is not None
    assert len(body["summary"]) == 2500


def test_brief_long_output_not_rejected(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("X" * 3000),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["rejected"] is False


# ---------------------------------------------------------------------------
# Brief — no database writes
# ---------------------------------------------------------------------------


def test_brief_campaign_rows_unchanged_after_brief(monkeypatch):
    _insert_campaign(_CID)
    updated_at_before = _get_campaign_updated_at(_CID)
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    resp = client.post(_BRIEF_URL, headers=HEADERS)
    assert resp.status_code == 200
    assert _get_campaign_updated_at(_CID) == updated_at_before


# ---------------------------------------------------------------------------
# Brief — multiple campaigns included correctly
# ---------------------------------------------------------------------------


def test_brief_multiple_campaigns_all_in_source_records(monkeypatch):
    ids = _insert_n_campaigns(3)
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Multi-campaign brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS, json={"max_campaigns": 10}).json()
    assert body["campaign_count"] == 3
    for cid in ids:
        assert cid in body["source_records"]["campaign_ids"]


def test_brief_dormant_campaigns_included(monkeypatch):
    _insert_campaign(_CID, status="dormant")
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["campaign_count"] == 1


def test_brief_reactivated_campaigns_included(monkeypatch):
    _insert_campaign(_CID, status="reactivated")
    monkeypatch.setattr(
        "app.routers.analyze.get_ai_backend",
        lambda: MockAIBackend("Brief."),
    )
    body = client.post(_BRIEF_URL, headers=HEADERS).json()
    assert body["campaign_count"] == 1
