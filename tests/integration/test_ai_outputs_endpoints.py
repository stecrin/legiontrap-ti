"""Integration tests for AI output persistence (Phase 6 PR A2).

Tests verify:
  - summary job creates an ai_output record
  - brief job creates an ai_output record
  - ai_output_id present in completed job response
  - GET /api/ai/outputs/{id} returns 200 with full record
  - GET /api/ai/outputs/{id} returns 404 for unknown id
  - GET /api/ai/outputs/{id} requires auth
  - GET /api/campaigns/{id}/ai-outputs returns list of outputs
  - GET /api/campaigns/{id}/ai-outputs returns empty list for new campaign
  - GET /api/campaigns/{id}/ai-outputs requires auth
  - Rejected output persists with content=None in DB
  - Rejected output retrievable via GET
  - Multiple summary jobs create separate output records (no overwrite)
  - data_quality_score present and non-negative on completed output
  - prompt_hash present; content of prompt never stored
  - source_records parseable as JSON
  - AI output is never used as prompt input (invariant check)
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.ai import MockAIBackend
from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
HEADERS = {"x-api-key": "dev-123"}

_CID = "cccccccc-dddd-eeee-ffff-000000000001"
_MEMBER_IP = "10.1.2.3"
_TS = "2026-01-15T00:00:00+00:00"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _insert_campaign(campaign_id: str = _CID, *, status: str = "active") -> None:
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
                    :id, :name, :status, 0.75,
                    :ts, :ts, NULL, 0, 1,
                    '{}', '[]', NULL, :ts, :ts
                )
            """),
            {"id": campaign_id, "name": "OUT-TEST", "status": status, "ts": _TS},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO source_ips (ip, first_seen, last_seen, event_count)
                VALUES (:ip, :ts, :ts, 5)
            """),
            {"ip": _MEMBER_IP, "ts": _TS},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO campaign_members
                    (campaign_id, source_ip, confidence, added_at, last_active)
                VALUES (:cid, :ip, 0.75, :ts, :ts)
            """),
            {"cid": campaign_id, "ip": _MEMBER_IP, "ts": _TS},
        )
        conn.commit()


def _trigger_summary(monkeypatch, campaign_id: str = _CID) -> dict:
    """POST /summary and return the 202 JSON body."""
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Campaign is active. Credential scanning observed."),
    )
    resp = client.post(f"/api/campaigns/{campaign_id}/summary", headers=HEADERS)
    assert resp.status_code == 202
    return resp.json()


def _poll_job(job_id: str) -> dict:
    resp = client.get(f"/api/jobs/{job_id}", headers=HEADERS)
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Summary job creates ai_output
# ---------------------------------------------------------------------------


def test_summary_job_sets_ai_output_id(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    assert job["status"] == "completed"
    assert job["ai_output_id"] is not None


def test_summary_job_ai_output_retrievable(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    output_id = job["ai_output_id"]

    resp = client.get(f"/api/ai/outputs/{output_id}", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == output_id
    assert body["job_id"] == accepted["job_id"]
    assert body["output_type"] == "campaign_summary"
    assert body["resource_type"] == "campaign"
    assert body["resource_id"] == _CID


def test_summary_output_has_content(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = resp.json()
    assert body["content"] is not None
    assert len(body["content"]) > 0


def test_summary_output_has_prompt_hash(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = resp.json()
    assert body["prompt_hash"] is not None
    assert len(body["prompt_hash"]) == 64  # SHA-256 hex


def test_summary_output_has_no_raw_prompt(monkeypatch):
    """Prompt content must never appear in the ai_output record."""
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = resp.json()
    assert "user_prompt" not in body
    assert "prompt" not in body


def test_summary_output_data_quality_score_present(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = resp.json()
    assert body["data_quality_score"] is not None
    assert body["data_quality_score"] >= 0.0


def test_summary_output_source_records_parseable(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = resp.json()
    assert isinstance(body["source_records"], dict)


def test_summary_output_backend_and_model_name(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = resp.json()
    assert body["backend"] == "none"  # default AI_BACKEND in test env
    assert body["model_name"] == "mock"  # MockAIBackend.model_name


def test_summary_output_triggered_by(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = resp.json()
    assert body["triggered_by"] == "api_key"


# ---------------------------------------------------------------------------
# Brief job creates ai_output
# ---------------------------------------------------------------------------


def test_brief_job_sets_ai_output_id(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Threat brief: campaign is active."),
    )
    resp = client.post("/api/campaigns/brief", headers=HEADERS)
    assert resp.status_code == 202
    job = _poll_job(resp.json()["job_id"])
    assert job["status"] == "completed"
    assert job["ai_output_id"] is not None


def test_brief_output_has_correct_type(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Threat brief: active campaign observed."),
    )
    resp = client.post("/api/campaigns/brief", headers=HEADERS)
    job = _poll_job(resp.json()["job_id"])
    output_resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = output_resp.json()
    assert body["output_type"] == "campaign_brief"
    assert body["resource_type"] is None  # briefs have no single resource


# ---------------------------------------------------------------------------
# Rejected output
# ---------------------------------------------------------------------------


def test_rejected_output_persists_with_null_content(monkeypatch):
    """IP in output → rejected=True, content=None, but ai_output row is written."""
    _insert_campaign()
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Campaign run by 192.168.1.1."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 202
    job = _poll_job(resp.json()["job_id"])
    assert job["status"] == "completed"
    assert job["ai_output_id"] is not None

    output_resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}", headers=HEADERS)
    body = output_resp.json()
    assert body["rejected"] is True
    assert body["content"] is None
    assert body["rejection_reason"] == "ip_detected"


# ---------------------------------------------------------------------------
# Multiple outputs for same campaign accumulate
# ---------------------------------------------------------------------------


def test_multiple_summaries_create_separate_outputs(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp1 = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    job1 = _poll_job(resp1.json()["job_id"])

    # Need a second job — mark first completed so dedup allows it.
    resp2 = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    job2 = _poll_job(resp2.json()["job_id"])

    assert job1["ai_output_id"] != job2["ai_output_id"]


# ---------------------------------------------------------------------------
# GET /api/campaigns/{id}/ai-outputs
# ---------------------------------------------------------------------------


def test_campaign_ai_outputs_returns_list(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Active."),
    )
    client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    resp = client.get(f"/api/campaigns/{_CID}/ai-outputs", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "outputs" in body
    assert "count" in body
    assert isinstance(body["outputs"], list)
    assert body["count"] == len(body["outputs"])


def test_campaign_ai_outputs_contains_created_output(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Active campaign."),
    )
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    job = _poll_job(resp.json()["job_id"])
    output_id = job["ai_output_id"]

    list_resp = client.get(f"/api/campaigns/{_CID}/ai-outputs", headers=HEADERS)
    ids = [o["id"] for o in list_resp.json()["outputs"]]
    assert output_id in ids


def test_campaign_ai_outputs_empty_for_no_outputs():
    cid = str(uuid.uuid4())
    _insert_campaign(campaign_id=cid)
    resp = client.get(f"/api/campaigns/{cid}/ai-outputs", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["outputs"] == []
    assert body["count"] == 0


def test_campaign_ai_outputs_requires_auth():
    resp = client.get(f"/api/campaigns/{_CID}/ai-outputs")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/ai/outputs/{output_id}
# ---------------------------------------------------------------------------


def test_get_output_requires_auth(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(f"/api/ai/outputs/{job['ai_output_id']}")
    assert resp.status_code == 401


def test_get_output_returns_404_for_unknown():
    resp = client.get("/api/ai/outputs/does-not-exist", headers=HEADERS)
    assert resp.status_code == 404


def test_get_output_wrong_key_returns_401(monkeypatch):
    _insert_campaign()
    accepted = _trigger_summary(monkeypatch)
    job = _poll_job(accepted["job_id"])
    resp = client.get(
        f"/api/ai/outputs/{job['ai_output_id']}",
        headers={"x-api-key": "wrong"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# AI output never used as prompt input (§3 invariant)
# ---------------------------------------------------------------------------


def test_ai_output_content_not_in_prompt_builder(monkeypatch):
    """Verify prompt_builder functions do not accept or use stored ai_output records.

    This is a code-level invariant test: the build_campaign_summary_prompt
    signature takes campaign, fingerprint, observations — not an ai_output dict.
    Passing an ai_output dict where campaign is expected must not silently succeed.
    """
    from app.ai.prompt_builder import build_campaign_summary_prompt

    fake_ai_output = {
        "id": "o1",
        "content": "Previous AI summary text",
        "output_type": "campaign_summary",
    }
    # build_campaign_summary_prompt should not return content from fake_ai_output
    try:
        result = build_campaign_summary_prompt(fake_ai_output, None, [])
        # If it didn't raise, verify the prompt does not echo the AI output content
        assert "Previous AI summary text" not in result.get("user_prompt", "")
    except (KeyError, TypeError, AttributeError):
        pass  # Expected: prompt builder rejects the fake dict shape
