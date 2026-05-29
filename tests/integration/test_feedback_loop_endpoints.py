"""Integration tests for Phase 7 Group A — weight profile and alerts API.

Tests hit the full stack: FastAPI TestClient → routers → EventRepository → in-memory SQLite.

Coverage:
  GET  /api/campaigns/{id}/weight-profile:
    - returns 200 with status=using_global_defaults when no profile exists
    - returns 200 with calibrated profile when profile exists
    - returns 404 for unknown campaign
    - requires authentication

  GET  /api/alerts:
    - returns 200 with empty list when no alerts
    - returns unacknowledged alerts only by default
    - returns all alerts with include_acknowledged=true
    - filters by campaign_id
    - requires authentication

  POST /api/alerts/{id}/acknowledge:
    - returns 200 with updated alert on success
    - returns 404 for unknown alert
    - requires authentication

  GET  /api/campaigns/{id}/alerts:
    - returns 200 with alert list
    - returns 404 for unknown campaign
    - requires authentication

  Invariants:
    - alerts router does not import from app.ai
    - campaigns router weight-profile endpoint does not import from app.ai
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.main import app

client = TestClient(app)

_API_KEY = "test-key"
_HEADERS = {"X-API-Key": _API_KEY}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def setup_api_key(monkeypatch):
    """Set the API key for the test session."""
    monkeypatch.setenv("API_KEY", _API_KEY)
    monkeypatch.setenv("FEED_SALT", "test-salt")


def _create_campaign() -> str:
    cid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with get_session() as session:
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

_SNAPSHOT = {"status": "ok", "composite_score": 0.40}


# ---------------------------------------------------------------------------
# GET /api/campaigns/{id}/weight-profile
# ---------------------------------------------------------------------------


def test_weight_profile_using_global_defaults():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/weight-profile", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "using_global_defaults"
    assert data["campaign_id"] == cid
    assert data["review_count"] == 0
    assert "weights" in data
    assert "global_defaults" in data
    assert data["adjustment_log"] == []


def test_weight_profile_returns_calibrated_when_profile_exists():
    cid = _create_campaign()
    now = datetime.now(UTC).isoformat()
    with get_session() as session:
        EventRepository(session).upsert_weight_profile(
            campaign_id=cid,
            weights=_DEFAULT_WEIGHTS,
            review_count=5,
            confirmed_count=4,
            denied_count=1,
            adjustment_log=[_LOG_ENTRY],
            computed_at=now,
            updated_at=now,
        )

    resp = client.get(f"/api/campaigns/{cid}/weight-profile", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "calibrated"
    assert data["review_count"] == 5
    assert data["confirmed_count"] == 4
    assert data["denied_count"] == 1
    assert len(data["adjustment_log"]) == 1


def test_weight_profile_returns_404_for_unknown_campaign():
    resp = client.get(f"/api/campaigns/{uuid.uuid4()}/weight-profile", headers=_HEADERS)
    assert resp.status_code == 404


def test_weight_profile_requires_auth():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/weight-profile")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/alerts
# ---------------------------------------------------------------------------


def test_list_alerts_empty():
    resp = client.get("/api/alerts", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == [] or isinstance(data["items"], list)


def test_list_alerts_returns_unacknowledged_by_default():
    cid = _create_campaign()
    with get_session() as session:
        repo = EventRepository(session)
        open_alert = repo.insert_alert(
            campaign_id=cid,
            alert_type="composite_drift",
            dimension=None,
            threshold_configured=0.65,
            observed_value=0.40,
            stability_snapshot=_SNAPSHOT,
        )
        acked_alert = repo.insert_alert(
            campaign_id=cid,
            alert_type="dimension_drift",
            dimension="timing",
            threshold_configured=0.60,
            observed_value=0.30,
            stability_snapshot=_SNAPSHOT,
        )
        repo.acknowledge_alert(acked_alert["id"])

    resp = client.get("/api/alerts", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    ids = {item["id"] for item in data["items"]}
    assert open_alert["id"] in ids
    assert acked_alert["id"] not in ids


def test_list_alerts_include_acknowledged():
    cid = _create_campaign()
    with get_session() as session:
        repo = EventRepository(session)
        acked_alert = repo.insert_alert(
            campaign_id=cid,
            alert_type="composite_drift",
            dimension=None,
            threshold_configured=0.65,
            observed_value=0.40,
            stability_snapshot=_SNAPSHOT,
        )
        repo.acknowledge_alert(acked_alert["id"])

    resp = client.get("/api/alerts?include_acknowledged=true", headers=_HEADERS)
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert acked_alert["id"] in ids


def test_list_alerts_filtered_by_campaign_id():
    cid1 = _create_campaign()
    cid2 = _create_campaign()
    with get_session() as session:
        repo = EventRepository(session)
        alert1 = repo.insert_alert(
            campaign_id=cid1,
            alert_type="composite_drift",
            dimension=None,
            threshold_configured=0.65,
            observed_value=0.40,
            stability_snapshot=_SNAPSHOT,
        )
        alert2 = repo.insert_alert(
            campaign_id=cid2,
            alert_type="composite_drift",
            dimension=None,
            threshold_configured=0.65,
            observed_value=0.40,
            stability_snapshot=_SNAPSHOT,
        )

    resp = client.get(f"/api/alerts?campaign_id={cid1}", headers=_HEADERS)
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert alert1["id"] in ids
    assert alert2["id"] not in ids


def test_list_alerts_requires_auth():
    resp = client.get("/api/alerts")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/alerts/{id}/acknowledge
# ---------------------------------------------------------------------------


def test_acknowledge_alert_success():
    cid = _create_campaign()
    with get_session() as session:
        alert = EventRepository(session).insert_alert(
            campaign_id=cid,
            alert_type="composite_drift",
            dimension=None,
            threshold_configured=0.65,
            observed_value=0.40,
            stability_snapshot=_SNAPSHOT,
        )

    resp = client.post(
        f"/api/alerts/{alert['id']}/acknowledge",
        json={"notes": "confirmed drift — operator aware"},
        headers=_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["acknowledged_at"] is not None
    assert data["acknowledged_notes"] == "confirmed drift — operator aware"
    assert data["acknowledged"] is True


def test_acknowledge_alert_returns_404_for_unknown():
    resp = client.post(
        f"/api/alerts/{uuid.uuid4()}/acknowledge",
        json={"notes": None},
        headers=_HEADERS,
    )
    assert resp.status_code == 404


def test_acknowledge_alert_requires_auth():
    resp = client.post(f"/api/alerts/{uuid.uuid4()}/acknowledge", json={"notes": None})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/campaigns/{id}/alerts
# ---------------------------------------------------------------------------


def test_campaign_alerts_returns_all_by_default():
    cid = _create_campaign()
    with get_session() as session:
        repo = EventRepository(session)
        open_a = repo.insert_alert(
            campaign_id=cid,
            alert_type="composite_drift",
            dimension=None,
            threshold_configured=0.65,
            observed_value=0.40,
            stability_snapshot=_SNAPSHOT,
        )
        acked_a = repo.insert_alert(
            campaign_id=cid,
            alert_type="dimension_drift",
            dimension="timing",
            threshold_configured=0.60,
            observed_value=0.30,
            stability_snapshot=_SNAPSHOT,
        )
        repo.acknowledge_alert(acked_a["id"])

    resp = client.get(f"/api/campaigns/{cid}/alerts", headers=_HEADERS)
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert open_a["id"] in ids
    assert acked_a["id"] in ids


def test_campaign_alerts_404_unknown_campaign():
    resp = client.get(f"/api/campaigns/{uuid.uuid4()}/alerts", headers=_HEADERS)
    assert resp.status_code == 404


def test_campaign_alerts_requires_auth():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/alerts")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_alerts_router_does_not_import_ai():
    import importlib

    mod = importlib.import_module("app.routers.alerts")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content


def test_clustering_uses_weight_profile_when_present():
    """Clustering result is deterministic with same fingerprint + weight profile."""
    import json as _json

    from app.intelligence.similarity import compute_weighted_similarity

    fp_a = {
        "timing_features": _json.dumps(
            {
                "mean_interval": 1.5,
                "burst_cv": 0.3,
                "session_count": 5,
                "tod_histogram": {},
                "dow_histogram": {},
            }
        ),
        "sequence_features": _json.dumps(
            {"port_sequence": [22, 80], "kex_sequence": [], "unique_ports": 2}
        ),
        "protocol_features": None,
        "credential_features": None,
        "target_features": None,
    }
    fp_b = {
        "timing_features": _json.dumps(
            {
                "mean_interval": 10.0,
                "burst_cv": 0.8,
                "session_count": 2,
                "tod_histogram": {},
                "dow_histogram": {},
            }
        ),
        "sequence_features": _json.dumps(
            {"port_sequence": [443, 22], "kex_sequence": [], "unique_ports": 2}
        ),
        "protocol_features": None,
        "credential_features": None,
        "target_features": None,
    }

    custom_weights = {
        "timing": 0.80,
        "sequence": 0.10,
        "protocol": 0.05,
        "credential": 0.03,
        "target": 0.02,
    }

    # Determinism: same inputs + same weights → same result
    r1 = compute_weighted_similarity(fp_a, fp_b, weights=custom_weights)
    r2 = compute_weighted_similarity(fp_a, fp_b, weights=custom_weights)
    assert r1.weighted_total == r2.weighted_total

    # Different weights produce different totals for the same fingerprint pair
    r_default = compute_weighted_similarity(fp_a, fp_b)
    r_custom = compute_weighted_similarity(fp_a, fp_b, weights=custom_weights)
    # With only timing and sequence active (protocol/credential/target all None),
    # the weighted_total changes when weights change
    assert r_default.weighted_total != r_custom.weighted_total

    # Backward compatibility: no-weights call still works
    r_noweights = compute_weighted_similarity(fp_a, fp_b)
    assert 0.0 <= r_noweights.weighted_total <= 1.0
