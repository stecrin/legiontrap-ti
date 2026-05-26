"""
Integration tests for GET /api/exports/attack-navigator and GET /api/exports/stix.

Tests exercise the full HTTP → router → repository → in-memory SQLite stack.
Schema is bootstrapped by tests/conftest.py; rows are reset per-test by
tests/integration/conftest.py (reset_db_rows fixture).
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import settings
from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_event(
    event_id: str,
    src_ip: str,
    event_type: str = "auth_failed",
    ts: str = "2026-01-01T00:00:00+00:00",
) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT OR IGNORE INTO raw_events (id, ts, ingested_at, source, raw_json) "
                "VALUES (:id, :ts, :ts, 'test', '{}')"
            ),
            {"id": event_id, "ts": ts},
        )
        conn.execute(
            text(
                "INSERT OR IGNORE INTO events (id, ts, src_ip, event_type) "
                "VALUES (:id, :ts, :src_ip, :event_type)"
            ),
            {"id": event_id, "ts": ts, "src_ip": src_ip, "event_type": event_type},
        )
        conn.execute(
            text(
                "INSERT INTO source_ips (ip, first_seen, last_seen, event_count, tags) "
                "VALUES (:ip, :ts, :ts, 1, NULL) "
                "ON CONFLICT(ip) DO UPDATE SET "
                "last_seen = excluded.last_seen, event_count = event_count + 1"
            ),
            {"ip": src_ip, "ts": ts},
        )
        conn.commit()


def _insert_source_ip(
    ip: str,
    event_count: int = 1,
    tags: list[str] | None = None,
    reputation_score: float | None = None,
    first_seen: str = "2026-01-01T00:00:00+00:00",
    last_seen: str = "2026-01-02T00:00:00+00:00",
) -> None:
    engine = get_engine()
    tags_json = json.dumps(tags) if tags else None
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT OR REPLACE INTO source_ips "
                "(ip, first_seen, last_seen, event_count, reputation_score, tags) "
                "VALUES (:ip, :first_seen, :last_seen, :event_count, :score, :tags)"
            ),
            {
                "ip": ip,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "event_count": event_count,
                "score": reputation_score,
                "tags": tags_json,
            },
        )
        conn.commit()


# ---------------------------------------------------------------------------
# ATT&CK Navigator — auth
# ---------------------------------------------------------------------------


def test_attack_navigator_requires_auth():
    r = client.get("/api/exports/attack-navigator")
    assert r.status_code == 401


def test_attack_navigator_rejects_wrong_key():
    r = client.get("/api/exports/attack-navigator", headers={"x-api-key": "wrong"})
    assert r.status_code == 401


def test_attack_navigator_accepts_api_key():
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# ATT&CK Navigator — response structure
# ---------------------------------------------------------------------------


def test_attack_navigator_returns_json():
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    assert r.headers["content-type"].startswith("application/json")
    data = r.json()
    assert isinstance(data, dict)


def test_attack_navigator_has_required_fields():
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    data = r.json()
    for key in ("name", "versions", "domain", "techniques", "gradient"):
        assert key in data, f"missing key: {key}"


def test_attack_navigator_domain_enterprise():
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    assert r.json()["domain"] == "enterprise-attack"


def test_attack_navigator_empty_db_returns_empty_techniques():
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    assert r.json()["techniques"] == []


def test_attack_navigator_with_events_returns_techniques():
    _insert_event("e-nav-1", "1.2.3.4", "auth_failed")
    _insert_event("e-nav-2", "1.2.3.5", "port_scan")
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    data = r.json()
    ids = {t["techniqueID"] for t in data["techniques"]}
    assert "T1110.001" in ids
    assert "T1046" in ids


def test_attack_navigator_score_equals_event_count():
    _insert_event("e-nav-3", "2.2.2.2", "auth_failed")
    _insert_event("e-nav-4", "2.2.2.3", "auth_failed")
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    techniques = r.json()["techniques"]
    t1110 = next((t for t in techniques if t["techniqueID"] == "T1110.001"), None)
    assert t1110 is not None
    assert t1110["score"] == 2


def test_attack_navigator_custom_layer_name():
    r = client.get(
        "/api/exports/attack-navigator",
        headers=HEADERS,
        params={"layer_name": "My Test Layer"},
    )
    assert r.json()["name"] == "My Test Layer"


def test_attack_navigator_unknown_event_type_excluded():
    _insert_event("e-nav-5", "3.3.3.3", "unknown")
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    ids = {t["techniqueID"] for t in r.json()["techniques"]}
    # 'unknown' has NULL attack_technique — must not appear
    assert all(i is not None for i in ids)


# ---------------------------------------------------------------------------
# ATT&CK Navigator — PRIVACY_MODE does not block it
# ---------------------------------------------------------------------------


def test_attack_navigator_not_blocked_by_privacy_mode(monkeypatch):
    monkeypatch.setattr(settings, "PRIVACY_MODE", True)
    r = client.get("/api/exports/attack-navigator", headers=HEADERS)
    assert r.status_code == 200
    monkeypatch.setattr(settings, "PRIVACY_MODE", False)


# ---------------------------------------------------------------------------
# STIX — auth
# ---------------------------------------------------------------------------


def test_stix_requires_auth():
    r = client.get("/api/exports/stix")
    assert r.status_code == 401


def test_stix_rejects_wrong_key():
    r = client.get("/api/exports/stix", headers={"x-api-key": "wrong"})
    assert r.status_code == 401


def test_stix_accepts_api_key():
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# STIX — PRIVACY_MODE blocks it
# ---------------------------------------------------------------------------


def test_stix_blocked_by_privacy_mode(monkeypatch):
    monkeypatch.setattr(settings, "PRIVACY_MODE", True)
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert r.status_code == 422
    assert "PRIVACY_MODE" in r.json()["detail"]
    monkeypatch.setattr(settings, "PRIVACY_MODE", False)


def test_stix_not_blocked_when_privacy_mode_off(monkeypatch):
    monkeypatch.setattr(settings, "PRIVACY_MODE", False)
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# STIX — response structure
# ---------------------------------------------------------------------------


def test_stix_returns_json():
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert r.headers["content-type"].startswith("application/json")
    assert isinstance(r.json(), dict)


def test_stix_bundle_type():
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert r.json()["type"] == "bundle"


def test_stix_bundle_has_id():
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert r.json()["id"].startswith("bundle--")


def test_stix_empty_db_returns_empty_bundle():
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert r.json()["objects"] == []


def test_stix_single_ip_produces_two_objects():
    _insert_source_ip("4.4.4.4", event_count=2, tags=["brute-force"])
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert len(r.json()["objects"]) == 2


def test_stix_objects_have_spec_version():
    _insert_source_ip("5.5.5.5", event_count=1)
    r = client.get("/api/exports/stix", headers=HEADERS)
    for obj in r.json()["objects"]:
        assert obj["spec_version"] == "2.1"


def test_stix_indicator_pattern_format():
    _insert_source_ip("6.6.6.6", event_count=1)
    r = client.get("/api/exports/stix", headers=HEADERS)
    indicators = [o for o in r.json()["objects"] if o["type"] == "indicator"]
    assert len(indicators) == 1
    assert indicators[0]["pattern"] == "[ipv4-addr:value = '6.6.6.6']"


def test_stix_deterministic_ids():
    _insert_source_ip("7.7.7.7", event_count=1)
    r1 = client.get("/api/exports/stix", headers=HEADERS)
    r2 = client.get("/api/exports/stix", headers=HEADERS)
    ids1 = {o["id"] for o in r1.json()["objects"]}
    ids2 = {o["id"] for o in r2.json()["objects"]}
    assert ids1 == ids2


# ---------------------------------------------------------------------------
# STIX — limit and min_event_count params
# ---------------------------------------------------------------------------


def test_stix_limit_caps_results():
    for i in range(5):
        _insert_source_ip(f"10.0.0.{i + 1}", event_count=2)
    r = client.get("/api/exports/stix", headers=HEADERS, params={"limit": 2})
    # 2 IPs × 2 objects each = 4
    assert len(r.json()["objects"]) == 4


def test_stix_limit_default_is_100():
    # Endpoint should accept the default without error
    r = client.get("/api/exports/stix", headers=HEADERS)
    assert r.status_code == 200


def test_stix_limit_max_1000_accepted():
    r = client.get("/api/exports/stix", headers=HEADERS, params={"limit": 1000})
    assert r.status_code == 200


def test_stix_limit_over_max_rejected():
    r = client.get("/api/exports/stix", headers=HEADERS, params={"limit": 1001})
    assert r.status_code == 422


def test_stix_limit_zero_rejected():
    r = client.get("/api/exports/stix", headers=HEADERS, params={"limit": 0})
    assert r.status_code == 422


def test_stix_min_event_count_filters_low_count_ips():
    _insert_source_ip("11.0.0.1", event_count=1)
    _insert_source_ip("11.0.0.2", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS, params={"min_event_count": 3})
    objects = r.json()["objects"]
    # Only 11.0.0.2 qualifies — 2 objects (ipv4-addr + indicator)
    assert len(objects) == 2
    ipv4 = next(o for o in objects if o["type"] == "ipv4-addr")
    assert ipv4["value"] == "11.0.0.2"


def test_stix_min_event_count_zero_rejected():
    r = client.get("/api/exports/stix", headers=HEADERS, params={"min_event_count": 0})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# STIX — Campaign SDOs and Relationship SDOs (Phase 4)
# ---------------------------------------------------------------------------


def _insert_campaign_with_member(
    campaign_id: str,
    ip: str,
    status: str = "active",
    name: str = "TEST-WOLF-1",
) -> None:
    """Insert a campaign and one member IP for export tests."""
    ts = "2025-06-01T12:00:00+00:00"
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO source_ips
                    (ip, first_seen, last_seen, event_count)
                VALUES (:ip, :ts, :ts, 5)
            """),
            {"ip": ip, "ts": ts},
        )
        conn.execute(
            text("""
                INSERT INTO campaigns
                    (id, name, status, confidence, first_seen, last_seen,
                     dormant_since, reactivation_count, member_ip_count,
                     attack_tactic_dist, top_target_ports, notes,
                     created_at, updated_at)
                VALUES
                    (:id, :name, :status, 0.85, :ts, :ts,
                     NULL, 0, 1, NULL, NULL, NULL, :ts, :ts)
            """),
            {"id": campaign_id, "name": name, "status": status, "ts": ts},
        )
        conn.execute(
            text("""
                INSERT INTO campaign_members
                    (campaign_id, source_ip, confidence, added_at, last_active)
                VALUES (:cid, :ip, 0.85, :ts, :ts)
            """),
            {"cid": campaign_id, "ip": ip, "ts": ts},
        )
        conn.commit()


def test_stix_campaign_sdo_present_when_campaign_exists():
    """A non-historical campaign produces a campaign SDO in the bundle."""
    import uuid

    cid = str(uuid.uuid4())
    _insert_campaign_with_member(cid, "20.0.0.1")
    _insert_source_ip("20.0.0.1", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    objects = r.json()["objects"]
    campaigns = [o for o in objects if o["type"] == "campaign"]
    assert len(campaigns) == 1
    assert campaigns[0]["id"].startswith("campaign--")
    assert campaigns[0]["name"] == "TEST-WOLF-1"


def test_stix_campaign_sdo_has_required_fields():
    import uuid

    cid = str(uuid.uuid4())
    _insert_campaign_with_member(cid, "20.0.0.2")
    _insert_source_ip("20.0.0.2", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    campaign_obj = next(o for o in r.json()["objects"] if o["type"] == "campaign")
    for field in ("type", "spec_version", "id", "created", "modified", "name", "first_seen"):
        assert field in campaign_obj, f"Missing field: {field}"
    assert campaign_obj["spec_version"] == "2.1"


def test_stix_campaign_sdo_has_legiontrap_custom_properties():
    import uuid

    cid = str(uuid.uuid4())
    _insert_campaign_with_member(cid, "20.0.0.3")
    _insert_source_ip("20.0.0.3", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    campaign_obj = next(o for o in r.json()["objects"] if o["type"] == "campaign")
    assert "x_legiontrap_status" in campaign_obj
    assert campaign_obj["x_legiontrap_status"] == "active"
    assert "x_legiontrap_member_ip_count" in campaign_obj
    assert "x_legiontrap_reactivation_count" in campaign_obj


def test_stix_campaign_sdo_contains_no_raw_ips():
    """Campaign SDO must not expose member IP addresses."""
    import uuid

    cid = str(uuid.uuid4())
    member_ip = "20.0.0.4"
    _insert_campaign_with_member(cid, member_ip)
    _insert_source_ip(member_ip, event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    campaign_obj = next(o for o in r.json()["objects"] if o["type"] == "campaign")
    campaign_str = json.dumps(campaign_obj)
    assert member_ip not in campaign_str


def test_stix_relationship_sdo_present_for_campaign_member():
    """An IP that is a campaign member produces a relationship SDO."""
    import uuid

    cid = str(uuid.uuid4())
    _insert_campaign_with_member(cid, "21.0.0.1")
    _insert_source_ip("21.0.0.1", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    objects = r.json()["objects"]
    relationships = [o for o in objects if o["type"] == "relationship"]
    assert len(relationships) == 1
    rel = relationships[0]
    assert rel["relationship_type"] == "indicates"
    assert rel["source_ref"].startswith("indicator--")
    assert rel["target_ref"].startswith("campaign--")


def test_stix_relationship_links_correct_indicator_and_campaign():
    """Relationship source_ref must match the indicator ID for the member IP."""
    import uuid

    from app.exports.stix import _stix_id

    cid = str(uuid.uuid4())
    member_ip = "21.0.0.2"
    _insert_campaign_with_member(cid, member_ip)
    _insert_source_ip(member_ip, event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    objects = r.json()["objects"]
    rel = next(o for o in objects if o["type"] == "relationship")
    expected_indicator_id = _stix_id("indicator", member_ip)
    assert rel["source_ref"] == expected_indicator_id


def test_stix_no_relationship_for_non_member_ip():
    """An IP that is not a campaign member must not produce a relationship SDO."""
    _insert_source_ip("22.0.0.1", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    objects = r.json()["objects"]
    relationships = [o for o in objects if o["type"] == "relationship"]
    assert relationships == []


def test_stix_historical_campaign_excluded_from_export():
    """Campaigns with status 'historical' must not produce campaign SDOs."""
    import uuid

    cid = str(uuid.uuid4())
    _insert_campaign_with_member(cid, "23.0.0.1", status="historical")
    _insert_source_ip("23.0.0.1", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    objects = r.json()["objects"]
    campaigns = [o for o in objects if o["type"] == "campaign"]
    relationships = [o for o in objects if o["type"] == "relationship"]
    assert campaigns == []
    assert relationships == []


def test_stix_dormant_campaign_included_in_export():
    """Dormant campaigns should still appear in STIX output."""
    import uuid

    cid = str(uuid.uuid4())
    _insert_campaign_with_member(cid, "24.0.0.1", status="dormant")
    _insert_source_ip("24.0.0.1", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    campaigns = [o for o in r.json()["objects"] if o["type"] == "campaign"]
    assert len(campaigns) == 1
    assert campaigns[0]["x_legiontrap_status"] == "dormant"


def test_stix_campaign_sdo_deterministic_id():
    """The same campaign always produces the same STIX object ID."""
    import uuid

    cid = str(uuid.uuid4())
    _insert_campaign_with_member(cid, "25.0.0.1")
    _insert_source_ip("25.0.0.1", event_count=5)
    r1 = client.get("/api/exports/stix", headers=HEADERS)
    r2 = client.get("/api/exports/stix", headers=HEADERS)
    ids1 = {o["id"] for o in r1.json()["objects"] if o["type"] == "campaign"}
    ids2 = {o["id"] for o in r2.json()["objects"] if o["type"] == "campaign"}
    assert ids1 == ids2


def test_stix_no_campaign_or_relationship_when_no_campaigns():
    """Bundle without any campaigns contains no campaign or relationship objects."""
    _insert_source_ip("26.0.0.1", event_count=5)
    r = client.get("/api/exports/stix", headers=HEADERS)
    objects = r.json()["objects"]
    assert not any(o["type"] in ("campaign", "relationship") for o in objects)
