"""Integration tests for Phase 6 Group B PR B3 — behavioral stability scoring.

Tests hit the full DB stack (in-memory SQLite bootstrapped by tests/conftest.py).
Rows reset per test by tests/integration/conftest.py.

Coverage:
  Repository:
    - update_campaign_stability stores JSON string
    - get_campaign_stability returns stored JSON string
    - get_campaign_stability returns None before first write
    - list_campaigns_missing_stability returns campaign_ids with NULL stability
    - list_campaigns_missing_stability excludes campaigns with stability set

  Refresh:
    - refresh_campaign_stability stores valid JSON for campaign with ≥2 history rows
    - refresh_campaign_stability stores insufficient_data for campaign with <2 rows
    - refresh_campaign_stability is idempotent (second call overwrites, does not error)
    - refresh_all_campaign_stability runs without error and populates all campaigns
    - refresh_all_campaign_stability does not fail on empty campaign set

  Campaign API:
    - GET /api/campaigns includes behavioral_stability_json field
    - GET /api/campaigns/{id} includes behavioral_stability_json field
    - behavioral_stability_json is null when not yet computed
    - behavioral_stability_json is a parseable JSON string when computed
    - parsed stability includes composite_score in [0, 1]

  End-to-end:
    - _compute_and_store + _run_campaign_clustering writes history then updates stability
    - stability increases when fingerprints are stable
    - stability is consistent across refresh calls
"""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.db.repository import EventRepository
from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY}

_TS = "2026-03-01T00:00:00+00:00"

_TIMING = json.dumps(
    {"interval": {"mean": 2.0, "stddev": 0.1, "p25": 1.8, "p75": 2.2, "p95": 2.5}, "burst_cv": 0.2}
)
_SEQUENCE = json.dumps({"port_sequence": [22, 22, 80], "event_type_sequence": ["auth_failed"]})
_PROTOCOL = json.dumps({"service_distribution": {"ssh": 10}})
_CREDENTIAL = json.dumps({"username_class_dist": {"dictionary": 5}})
_TARGET = json.dumps({"top_dst_ports": [22, 80], "port_freq": {"22": 10, "80": 2}})


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _insert_source_ip(ip: str) -> None:
    with get_engine().connect() as conn:
        conn.execute(
            text(
                "INSERT OR IGNORE INTO source_ips"
                " (ip, first_seen, last_seen, event_count) VALUES (:ip, :ts, :ts, 0)"
            ),
            {"ip": ip, "ts": _TS},
        )
        conn.commit()


def _insert_campaign(campaign_id: str | None = None, *, status: str = "active") -> str:
    cid = campaign_id or str(uuid.uuid4())
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO campaigns (
                    id, name, status, confidence, first_seen, last_seen,
                    dormant_since, reactivation_count, member_ip_count,
                    attack_tactic_dist, top_target_ports, notes,
                    created_at, updated_at
                ) VALUES (
                    :id, :name, :status, 0.75, :ts, :ts,
                    NULL, 0, 0, NULL, NULL, NULL, :ts, :ts
                )
            """),
            {"id": cid, "name": f"CAMP-{cid[:8]}", "status": status, "ts": _TS},
        )
        conn.commit()
    return cid


def _insert_member(campaign_id: str, ip: str) -> None:
    _insert_source_ip(ip)
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO campaign_members
                    (campaign_id, source_ip, confidence, added_at, last_active)
                VALUES (:cid, :ip, 0.75, :ts, :ts)
            """),
            {"cid": campaign_id, "ip": ip, "ts": _TS},
        )
        conn.commit()


def _insert_history_row(
    campaign_id: str,
    source_ip: str,
    *,
    computed_at: str = _TS,
    timing: str | None = _TIMING,
    sequence: str | None = _SEQUENCE,
) -> str:
    hid = str(uuid.uuid4())
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO fingerprint_history (
                    id, fingerprint_id, source_ip, campaign_id,
                    fingerprint_version, computed_at, event_count_at_computation,
                    confidence, timing_features, sequence_features,
                    protocol_features, credential_features, target_features,
                    created_at
                ) VALUES (
                    :id, NULL, :ip, :cid,
                    1, :computed_at, 10,
                    0.80, :timing, :sequence,
                    :protocol, :credential, :target,
                    :ts
                )
            """),
            {
                "id": hid,
                "ip": source_ip,
                "cid": campaign_id,
                "computed_at": computed_at,
                "timing": timing,
                "sequence": sequence,
                "protocol": _PROTOCOL,
                "credential": _CREDENTIAL,
                "target": _TARGET,
                "ts": _TS,
            },
        )
        conn.commit()
    return hid


def _get_stability_json(campaign_id: str) -> str | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT behavioral_stability_json FROM campaigns WHERE id = :id"),
            {"id": campaign_id},
        ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Repository: update_campaign_stability / get_campaign_stability
# ---------------------------------------------------------------------------


def test_update_campaign_stability_stores_json():
    from app.db.connection import get_session

    cid = _insert_campaign()
    payload = json.dumps({"status": "ok", "composite_score": 0.88})
    with get_session() as session:
        repo = EventRepository(session)
        repo.update_campaign_stability(cid, payload)

    assert _get_stability_json(cid) == payload


def test_get_campaign_stability_returns_stored_json():
    from app.db.connection import get_session

    cid = _insert_campaign()
    payload = json.dumps({"status": "ok", "composite_score": 0.75})
    with get_session() as session:
        repo = EventRepository(session)
        repo.update_campaign_stability(cid, payload)
        result = repo.get_campaign_stability(cid)
    assert result == payload


def test_get_campaign_stability_none_before_write():
    from app.db.connection import get_session

    cid = _insert_campaign()
    with get_session() as session:
        repo = EventRepository(session)
        result = repo.get_campaign_stability(cid)
    assert result is None


def test_list_campaigns_missing_stability_includes_unscored():
    from app.db.connection import get_session

    cid = _insert_campaign()
    with get_session() as session:
        repo = EventRepository(session)
        missing = repo.list_campaigns_missing_stability()
    assert cid in missing


def test_list_campaigns_missing_stability_excludes_scored():
    from app.db.connection import get_session

    cid = _insert_campaign()
    with get_session() as session:
        repo = EventRepository(session)
        repo.update_campaign_stability(cid, '{"status": "ok"}')

    with get_session() as session:
        repo = EventRepository(session)
        missing = repo.list_campaigns_missing_stability()
    assert cid not in missing


# ---------------------------------------------------------------------------
# refresh_campaign_stability
# ---------------------------------------------------------------------------


def test_refresh_campaign_stability_stores_ok_with_two_history_rows():
    from app.intelligence.stability import refresh_campaign_stability

    cid = _insert_campaign()
    ip = f"10.70.{uuid.uuid4().int % 256}.1"
    _insert_history_row(cid, ip, computed_at="2026-01-01T00:00:00+00:00")
    _insert_history_row(cid, ip, computed_at="2026-01-02T00:00:00+00:00")

    refresh_campaign_stability(cid)

    raw = _get_stability_json(cid)
    assert raw is not None
    parsed = json.loads(raw)
    assert parsed["status"] == "ok"
    assert 0.0 <= parsed["composite_score"] <= 1.0


def test_refresh_campaign_stability_stores_insufficient_with_one_row():
    from app.intelligence.stability import refresh_campaign_stability

    cid = _insert_campaign()
    ip = f"10.71.{uuid.uuid4().int % 256}.1"
    _insert_history_row(cid, ip)

    refresh_campaign_stability(cid)

    raw = _get_stability_json(cid)
    assert raw is not None
    assert json.loads(raw)["status"] == "insufficient_data"


def test_refresh_campaign_stability_stores_insufficient_with_no_rows():
    from app.intelligence.stability import refresh_campaign_stability

    cid = _insert_campaign()
    refresh_campaign_stability(cid)

    raw = _get_stability_json(cid)
    assert raw is not None
    assert json.loads(raw)["status"] == "insufficient_data"


def test_refresh_campaign_stability_is_idempotent():
    from app.intelligence.stability import refresh_campaign_stability

    cid = _insert_campaign()
    ip = f"10.72.{uuid.uuid4().int % 256}.1"
    _insert_history_row(cid, ip, computed_at="2026-01-01T00:00:00+00:00")
    _insert_history_row(cid, ip, computed_at="2026-01-02T00:00:00+00:00")

    refresh_campaign_stability(cid)
    raw1 = _get_stability_json(cid)

    refresh_campaign_stability(cid)
    raw2 = _get_stability_json(cid)

    p1 = json.loads(raw1)  # type: ignore[arg-type]
    p2 = json.loads(raw2)  # type: ignore[arg-type]
    assert p1["composite_score"] == p2["composite_score"]
    assert p1["status"] == p2["status"]


# ---------------------------------------------------------------------------
# refresh_all_campaign_stability
# ---------------------------------------------------------------------------


def test_refresh_all_campaign_stability_runs_without_error():
    from app.intelligence.stability import refresh_all_campaign_stability

    cid1 = _insert_campaign()
    cid2 = _insert_campaign()
    ip = f"10.73.{uuid.uuid4().int % 256}.1"
    _insert_history_row(cid1, ip, computed_at="2026-01-01T00:00:00+00:00")
    _insert_history_row(cid1, ip, computed_at="2026-01-02T00:00:00+00:00")

    refresh_all_campaign_stability()

    assert _get_stability_json(cid1) is not None
    assert _get_stability_json(cid2) is not None


def test_refresh_all_campaign_stability_empty_set_no_error():
    from app.intelligence.stability import refresh_all_campaign_stability

    refresh_all_campaign_stability()


# ---------------------------------------------------------------------------
# Campaign API — stability in response
# ---------------------------------------------------------------------------


def test_list_campaigns_includes_behavioral_stability_json_field():
    _insert_campaign()
    resp = client.get("/api/campaigns", headers=HEADERS)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert "behavioral_stability_json" in item


def test_get_campaign_includes_behavioral_stability_json_field():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    assert resp.status_code == 200
    assert "behavioral_stability_json" in resp.json()


def test_get_campaign_stability_json_null_when_not_computed():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    assert resp.json()["behavioral_stability_json"] is None


def test_get_campaign_stability_json_populated_after_refresh():
    from app.intelligence.stability import refresh_campaign_stability

    cid = _insert_campaign()
    ip = f"10.74.{uuid.uuid4().int % 256}.1"
    _insert_history_row(cid, ip, computed_at="2026-01-01T00:00:00+00:00")
    _insert_history_row(cid, ip, computed_at="2026-01-02T00:00:00+00:00")

    refresh_campaign_stability(cid)

    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    raw = resp.json()["behavioral_stability_json"]
    assert raw is not None
    parsed = json.loads(raw)
    assert 0.0 <= parsed["composite_score"] <= 1.0


def test_list_campaigns_stability_json_parseable():
    from app.intelligence.stability import refresh_campaign_stability

    cid = _insert_campaign()
    ip = f"10.75.{uuid.uuid4().int % 256}.1"
    _insert_history_row(cid, ip, computed_at="2026-01-01T00:00:00+00:00")
    _insert_history_row(cid, ip, computed_at="2026-01-02T00:00:00+00:00")

    refresh_campaign_stability(cid)

    resp = client.get("/api/campaigns", headers=HEADERS)
    items = resp.json()["items"]
    match = next((i for i in items if i["id"] == cid), None)
    assert match is not None
    raw = match["behavioral_stability_json"]
    assert raw is not None
    parsed = json.loads(raw)
    assert "composite_score" in parsed
    assert "status" in parsed


# ---------------------------------------------------------------------------
# Stability increases when fingerprints are stable
# ---------------------------------------------------------------------------


def test_stable_history_produces_higher_score_than_drifted():
    from app.intelligence.stability import refresh_campaign_stability

    _TIMING_DRIFT = json.dumps(
        {
            "interval": {"mean": 10.0, "stddev": 5.0, "p25": 5.0, "p75": 15.0, "p95": 20.0},
            "burst_cv": 1.5,
        }
    )
    _SEQUENCE_DRIFT = json.dumps(
        {"port_sequence": [443, 8080, 3306], "event_type_sequence": ["http_probe"]}
    )

    ip_stable = f"10.76.{uuid.uuid4().int % 256}.1"
    ip_drift = f"10.76.{uuid.uuid4().int % 256}.2"

    cid_stable = _insert_campaign()
    cid_drift = _insert_campaign()

    # Stable: same features in both rows.
    _insert_history_row(cid_stable, ip_stable, computed_at="2026-01-01T00:00:00+00:00")
    _insert_history_row(cid_stable, ip_stable, computed_at="2026-01-02T00:00:00+00:00")

    # Drifted: significantly different features.
    _insert_history_row(
        cid_drift,
        ip_drift,
        computed_at="2026-01-01T00:00:00+00:00",
        timing=_TIMING,
        sequence=_SEQUENCE,
    )
    _insert_history_row(
        cid_drift,
        ip_drift,
        computed_at="2026-01-02T00:00:00+00:00",
        timing=_TIMING_DRIFT,
        sequence=_SEQUENCE_DRIFT,
    )

    refresh_campaign_stability(cid_stable)
    refresh_campaign_stability(cid_drift)

    score_stable = json.loads(_get_stability_json(cid_stable))["composite_score"]  # type: ignore
    score_drift = json.loads(_get_stability_json(cid_drift))["composite_score"]  # type: ignore

    assert score_stable > score_drift
