"""Integration tests for Phase 6 Group B PR B4 — uncertain association review queue.

Tests hit the full DB stack (in-memory SQLite bootstrapped by tests/conftest.py).
Rows reset per test by tests/integration/conftest.py.

Coverage:
  Repository — list_uncertain_observations:
    - returns empty list when no observations exist
    - returns uncertain observations (notes with decision=uncertain_association)
    - excludes non-uncertain observations (automatic_association, null notes)
    - filters by campaign_id when provided
    - excludes reviewed observations by default
    - includes reviewed observations when include_reviewed=True
    - respects limit parameter

  Repository — get_campaign_observation:
    - returns dict for existing observation
    - returns None for unknown observation_id

  Repository — annotate_campaign_observation:
    - writes analyst_review_json to the observation row
    - does not modify campaign membership
    - does not modify notes field
    - second call overwrites first review (idempotent)

  API — GET /api/campaigns/uncertain-associations:
    - returns 200 with items list
    - requires authentication (401 without key)
    - returns only pending observations by default
    - returns reviewed observations when include_reviewed=true
    - filters by campaign_id query param
    - items include expected keys

  API — POST /api/campaigns/uncertain-associations/{id}/review:
    - returns 200 with updated observation on success
    - requires authentication (401 without key)
    - returns 404 for unknown observation_id
    - returns 422 for invalid decision value
    - returns 422 for empty decision
    - analyst_confirmed decision persists
    - analyst_denied decision persists
    - reviewed observation no longer in default pending list
    - reviewed observation appears in include_reviewed=true list
    - does not mutate campaign member count

  No AI:
    - campaigns.py router does not import from app.ai
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine, get_session
from app.db.repository import EventRepository
from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY}

_TS = "2026-05-27T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers
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


def _insert_campaign(*, status: str = "active") -> str:
    cid = str(uuid.uuid4())
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
                    NULL, 0, 1, NULL, NULL, NULL, :ts, :ts
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


def _make_uncertain_notes(weighted_total: float = 0.65) -> str:
    return json.dumps(
        {
            "timing_similarity": 0.7,
            "sequence_similarity": 0.6,
            "protocol_similarity": 0.65,
            "credential_similarity": None,
            "target_similarity": 0.7,
            "weighted_total": weighted_total,
            "dimensions_used": 4,
            "threshold_applied": 0.6,
            "decision": "uncertain_association",
        },
        separators=(",", ":"),
    )


def _make_auto_notes() -> str:
    return json.dumps(
        {
            "weighted_total": 0.85,
            "threshold_applied": 0.8,
            "decision": "automatic_association",
        },
        separators=(",", ":"),
    )


def _insert_observation(
    campaign_id: str,
    source_ip: str,
    *,
    notes: str | None = None,
    observed_at: str = _TS,
) -> str:
    oid = str(uuid.uuid4())
    _insert_source_ip(source_ip)
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO campaign_observations
                    (id, campaign_id, source_ip, observed_at, event_count,
                     is_reactivation, dormancy_gap_days, notes)
                VALUES
                    (:id, :cid, :ip, :observed_at, 10, 0, NULL, :notes)
            """),
            {
                "id": oid,
                "cid": campaign_id,
                "ip": source_ip,
                "observed_at": observed_at,
                "notes": notes,
            },
        )
        conn.commit()
    return oid


# ---------------------------------------------------------------------------
# Repository — list_uncertain_observations
# ---------------------------------------------------------------------------


def test_list_uncertain_returns_empty_when_no_observations():
    cid = _insert_campaign()
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(campaign_id=cid)
    assert items == []


def test_list_uncertain_returns_uncertain_observation():
    cid = _insert_campaign()
    ip = f"10.10.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(campaign_id=cid)
    assert len(items) == 1
    assert items[0]["id"] == oid


def test_list_uncertain_excludes_automatic_association():
    cid = _insert_campaign()
    ip = f"10.11.{uuid.uuid4().int % 256}.1"
    _insert_observation(cid, ip, notes=_make_auto_notes())
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(campaign_id=cid)
    assert items == []


def test_list_uncertain_excludes_null_notes():
    cid = _insert_campaign()
    ip = f"10.12.{uuid.uuid4().int % 256}.1"
    _insert_observation(cid, ip, notes=None)
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(campaign_id=cid)
    assert items == []


def test_list_uncertain_filters_by_campaign_id():
    cid1 = _insert_campaign()
    cid2 = _insert_campaign()
    ip1 = f"10.13.{uuid.uuid4().int % 256}.1"
    ip2 = f"10.13.{uuid.uuid4().int % 256}.2"
    _insert_observation(cid1, ip1, notes=_make_uncertain_notes())
    _insert_observation(cid2, ip2, notes=_make_uncertain_notes())
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(campaign_id=cid1)
    assert len(items) == 1
    assert items[0]["campaign_id"] == cid1


def test_list_uncertain_returns_across_all_campaigns_when_no_filter():
    cid1 = _insert_campaign()
    cid2 = _insert_campaign()
    ip1 = f"10.14.{uuid.uuid4().int % 256}.1"
    ip2 = f"10.14.{uuid.uuid4().int % 256}.2"
    _insert_observation(cid1, ip1, notes=_make_uncertain_notes())
    _insert_observation(cid2, ip2, notes=_make_uncertain_notes())
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations()
    cids = {i["campaign_id"] for i in items}
    assert cid1 in cids
    assert cid2 in cids


def test_list_uncertain_excludes_reviewed_by_default():
    cid = _insert_campaign()
    ip = f"10.15.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(oid, "analyst_confirmed", None, _TS)
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(campaign_id=cid)
    assert items == []


def test_list_uncertain_includes_reviewed_when_requested():
    cid = _insert_campaign()
    ip = f"10.16.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(oid, "analyst_confirmed", None, _TS)
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(
            campaign_id=cid, include_reviewed=True
        )
    assert len(items) == 1
    assert items[0]["id"] == oid


def test_list_uncertain_respects_limit():
    cid = _insert_campaign()
    for i in range(5):
        ip = f"10.17.{i}.1"
        _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(campaign_id=cid, limit=3)
    assert len(items) == 3


def test_list_uncertain_returned_keys():
    cid = _insert_campaign()
    ip = f"10.18.{uuid.uuid4().int % 256}.1"
    _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(campaign_id=cid)
    assert len(items) == 1
    assert set(items[0].keys()) == {
        "id",
        "campaign_id",
        "source_ip",
        "observed_at",
        "event_count",
        "is_reactivation",
        "dormancy_gap_days",
        "notes",
        "analyst_review_json",
    }


# ---------------------------------------------------------------------------
# Repository — get_campaign_observation
# ---------------------------------------------------------------------------


def test_get_campaign_observation_returns_dict():
    cid = _insert_campaign()
    ip = f"10.20.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        obs = EventRepository(session).get_campaign_observation(oid)
    assert obs is not None
    assert obs["id"] == oid
    assert obs["campaign_id"] == cid


def test_get_campaign_observation_returns_none_for_unknown():
    with get_session() as session:
        obs = EventRepository(session).get_campaign_observation(str(uuid.uuid4()))
    assert obs is None


def test_get_campaign_observation_analyst_review_json_initially_null():
    cid = _insert_campaign()
    ip = f"10.21.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        obs = EventRepository(session).get_campaign_observation(oid)
    assert obs["analyst_review_json"] is None


# ---------------------------------------------------------------------------
# Repository — annotate_campaign_observation
# ---------------------------------------------------------------------------


def test_annotate_writes_analyst_review_json():
    cid = _insert_campaign()
    ip = f"10.30.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(
            oid, "analyst_confirmed", "Confirmed by SOC", _TS
        )
    with get_session() as session:
        obs = EventRepository(session).get_campaign_observation(oid)
    assert obs["analyst_review_json"] is not None
    parsed = json.loads(obs["analyst_review_json"])
    assert parsed["decision"] == "analyst_confirmed"
    assert parsed["notes"] == "Confirmed by SOC"
    assert parsed["reviewed_at"] == _TS


def test_annotate_analyst_denied_persists():
    cid = _insert_campaign()
    ip = f"10.31.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(oid, "analyst_denied", None, _TS)
    with get_session() as session:
        obs = EventRepository(session).get_campaign_observation(oid)
    parsed = json.loads(obs["analyst_review_json"])
    assert parsed["decision"] == "analyst_denied"
    assert parsed["notes"] is None


def test_annotate_does_not_modify_notes_field():
    cid = _insert_campaign()
    ip = f"10.32.{uuid.uuid4().int % 256}.1"
    original_notes = _make_uncertain_notes()
    oid = _insert_observation(cid, ip, notes=original_notes)
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(
            oid, "analyst_confirmed", "Some note", _TS
        )
    with get_session() as session:
        obs = EventRepository(session).get_campaign_observation(oid)
    assert obs["notes"] == original_notes


def test_annotate_overwrites_previous_review():
    cid = _insert_campaign()
    ip = f"10.33.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    ts1 = "2026-05-27T10:00:00+00:00"
    ts2 = "2026-05-27T11:00:00+00:00"
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(
            oid, "analyst_confirmed", "First review", ts1
        )
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(
            oid, "analyst_denied", "Revised", ts2
        )
    with get_session() as session:
        obs = EventRepository(session).get_campaign_observation(oid)
    parsed = json.loads(obs["analyst_review_json"])
    assert parsed["decision"] == "analyst_denied"
    assert parsed["reviewed_at"] == ts2


def test_annotate_does_not_change_campaign_member_count():
    cid = _insert_campaign()
    ip = f"10.34.{uuid.uuid4().int % 256}.1"
    _insert_member(cid, ip)
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())

    with get_session() as session:
        before = EventRepository(session).get_campaign(cid)

    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(oid, "analyst_confirmed", None, _TS)

    with get_session() as session:
        after = EventRepository(session).get_campaign(cid)

    assert before["member_ip_count"] == after["member_ip_count"]


# ---------------------------------------------------------------------------
# API — GET /api/campaigns/uncertain-associations
# ---------------------------------------------------------------------------


def test_list_uncertain_api_returns_200():
    resp = client.get("/api/campaigns/uncertain-associations", headers=HEADERS)
    assert resp.status_code == 200


def test_list_uncertain_api_returns_items_and_count():
    resp = client.get("/api/campaigns/uncertain-associations", headers=HEADERS)
    body = resp.json()
    assert "items" in body
    assert "count" in body
    assert body["count"] == len(body["items"])


def test_list_uncertain_api_requires_auth():
    resp = client.get("/api/campaigns/uncertain-associations")
    assert resp.status_code == 401


def test_list_uncertain_api_returns_observation():
    cid = _insert_campaign()
    ip = f"10.40.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    resp = client.get("/api/campaigns/uncertain-associations", headers=HEADERS)
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["items"]]
    assert oid in ids


def test_list_uncertain_api_excludes_reviewed_by_default():
    cid = _insert_campaign()
    ip = f"10.41.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(oid, "analyst_confirmed", None, _TS)
    resp = client.get("/api/campaigns/uncertain-associations", headers=HEADERS)
    ids = [i["id"] for i in resp.json()["items"]]
    assert oid not in ids


def test_list_uncertain_api_includes_reviewed_when_flag_set():
    cid = _insert_campaign()
    ip = f"10.42.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    with get_session() as session:
        EventRepository(session).annotate_campaign_observation(oid, "analyst_denied", None, _TS)
    resp = client.get(
        "/api/campaigns/uncertain-associations?include_reviewed=true", headers=HEADERS
    )
    ids = [i["id"] for i in resp.json()["items"]]
    assert oid in ids


def test_list_uncertain_api_filters_by_campaign_id():
    cid1 = _insert_campaign()
    cid2 = _insert_campaign()
    ip1 = f"10.43.{uuid.uuid4().int % 256}.1"
    ip2 = f"10.43.{uuid.uuid4().int % 256}.2"
    oid1 = _insert_observation(cid1, ip1, notes=_make_uncertain_notes())
    oid2 = _insert_observation(cid2, ip2, notes=_make_uncertain_notes())
    resp = client.get(f"/api/campaigns/uncertain-associations?campaign_id={cid1}", headers=HEADERS)
    ids = [i["id"] for i in resp.json()["items"]]
    assert oid1 in ids
    assert oid2 not in ids


def test_list_uncertain_api_item_has_expected_keys():
    cid = _insert_campaign()
    ip = f"10.44.{uuid.uuid4().int % 256}.1"
    _insert_observation(cid, ip, notes=_make_uncertain_notes())
    resp = client.get("/api/campaigns/uncertain-associations", headers=HEADERS)
    item = resp.json()["items"][0]
    for key in (
        "id",
        "campaign_id",
        "source_ip",
        "observed_at",
        "event_count",
        "notes",
        "analyst_review_json",
    ):
        assert key in item, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# API — POST /api/campaigns/uncertain-associations/{id}/review
# ---------------------------------------------------------------------------


def test_review_returns_200_on_success():
    cid = _insert_campaign()
    ip = f"10.50.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    resp = client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "analyst_confirmed"},
        headers=HEADERS,
    )
    assert resp.status_code == 200


def test_review_requires_auth():
    oid = str(uuid.uuid4())
    resp = client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "analyst_confirmed"},
    )
    assert resp.status_code == 401


def test_review_returns_404_for_unknown_observation():
    oid = str(uuid.uuid4())
    resp = client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "analyst_confirmed"},
        headers=HEADERS,
    )
    assert resp.status_code == 404


def test_review_returns_422_for_invalid_decision():
    cid = _insert_campaign()
    ip = f"10.51.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    resp = client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "accepted"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_review_returns_422_for_empty_decision():
    cid = _insert_campaign()
    ip = f"10.52.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    resp = client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": ""},
        headers=HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("decision", ["analyst_confirmed", "analyst_denied"])
def test_review_decision_persists(decision: str):
    cid = _insert_campaign()
    ip = f"10.53.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    resp = client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": decision, "notes": "test note"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["analyst_review_json"] is not None
    parsed = json.loads(body["analyst_review_json"])
    assert parsed["decision"] == decision
    assert parsed["notes"] == "test note"


def test_review_response_contains_observation_fields():
    cid = _insert_campaign()
    ip = f"10.54.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    resp = client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "analyst_confirmed"},
        headers=HEADERS,
    )
    body = resp.json()
    assert body["id"] == oid
    assert body["campaign_id"] == cid


def test_reviewed_observation_removed_from_pending_list():
    cid = _insert_campaign()
    ip = f"10.55.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "analyst_confirmed"},
        headers=HEADERS,
    )
    resp = client.get("/api/campaigns/uncertain-associations", headers=HEADERS)
    ids = [i["id"] for i in resp.json()["items"]]
    assert oid not in ids


def test_reviewed_observation_appears_in_include_reviewed_list():
    cid = _insert_campaign()
    ip = f"10.56.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "analyst_denied"},
        headers=HEADERS,
    )
    resp = client.get(
        "/api/campaigns/uncertain-associations?include_reviewed=true", headers=HEADERS
    )
    ids = [i["id"] for i in resp.json()["items"]]
    assert oid in ids


def test_review_does_not_mutate_campaign_member_count():
    cid = _insert_campaign()
    ip = f"10.57.{uuid.uuid4().int % 256}.1"
    _insert_member(cid, ip)
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())

    before = client.get(f"/api/campaigns/{cid}", headers=HEADERS).json()["member_ip_count"]

    client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "analyst_confirmed"},
        headers=HEADERS,
    )

    after = client.get(f"/api/campaigns/{cid}", headers=HEADERS).json()["member_ip_count"]
    assert before == after


def test_review_with_null_notes_body_field():
    cid = _insert_campaign()
    ip = f"10.58.{uuid.uuid4().int % 256}.1"
    oid = _insert_observation(cid, ip, notes=_make_uncertain_notes())
    resp = client.post(
        f"/api/campaigns/uncertain-associations/{oid}/review",
        json={"decision": "analyst_denied", "notes": None},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    parsed = json.loads(resp.json()["analyst_review_json"])
    assert parsed["notes"] is None


# ---------------------------------------------------------------------------
# No AI imports
# ---------------------------------------------------------------------------


def test_campaigns_router_has_no_ai_imports():
    import importlib
    import sys

    if "app.routers.campaigns" in sys.modules:
        mod = sys.modules["app.routers.campaigns"]
    else:
        mod = importlib.import_module("app.routers.campaigns")

    source = mod.__file__
    assert source is not None
    with open(source) as f:
        content = f.read()
    assert "app.ai" not in content
    assert "from app.ai" not in content
    assert "import app.ai" not in content
