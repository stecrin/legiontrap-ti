"""Integration tests for AI audit logging and rate limiting (Phase 6 PR A3).

Coverage:
  Rate limiting (POST /api/campaigns/{id}/summary):
    - 429 returned when per-operator limit is exhausted
    - Retry-After: 60 header present on 429
    - 429 detail message references retry window
    - rate_limited audit record written after 429
    - First request under limit succeeds (202)
    - Dedup check short-circuits before rate limit check

  Rate limiting (POST /api/campaigns/brief):
    - 429 returned when per-operator limit is exhausted
    - Retry-After: 60 header present

  GET /api/admin/ai-audit:
    - 200 with {logs, count} shape
    - 401 without API key
    - 401 with wrong API key
    - 401 with JWT-only auth (admin endpoint rejects JWT)
    - Empty logs list when no records
    - Audit record created after successful summary job
    - Audit record has expected metadata fields
    - Audit record does NOT contain prompt text or response content
    - Filter by triggered_by
    - Filter by status
    - Filter by backend
    - limit query param respected
    - rate_limited audit records visible in audit log
    - Audit record created when AI job fails (status=disabled)
"""

from __future__ import annotations

import os
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

_CID = "ffff0000-1111-2222-3333-444444444444"
_MEMBER_IP = "10.9.8.7"
_TS = "2026-01-20T00:00:00+00:00"


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
                    :id, :name, :status, 0.70,
                    :ts, :ts, NULL, 0, 1,
                    '{}', '[]', NULL, :ts, :ts
                )
            """),
            {"id": campaign_id, "name": "AUDIT-TEST", "status": status, "ts": _TS},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO source_ips (ip, first_seen, last_seen, event_count)
                VALUES (:ip, :ts, :ts, 3)
            """),
            {"ip": _MEMBER_IP, "ts": _TS},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO campaign_members
                    (campaign_id, source_ip, confidence, added_at, last_active)
                VALUES (:cid, :ip, 0.70, :ts, :ts)
            """),
            {"cid": campaign_id, "ip": _MEMBER_IP, "ts": _TS},
        )
        conn.commit()


def _insert_recent_jobs(count: int, *, job_type: str = "campaign_summary") -> None:
    """Insert completed AI jobs with recent created_at to saturate rate limit."""
    from datetime import UTC, datetime

    engine = get_engine()
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        for _ in range(count):
            conn.execute(
                text("""
                    INSERT INTO processing_jobs (
                        id, job_type, status, created_at,
                        triggered_by, progress_percent
                    ) VALUES (
                        :id, :job_type, 'completed', :created_at,
                        'api_key', 100
                    )
                """),
                {"id": str(uuid.uuid4()), "job_type": job_type, "created_at": now},
            )
        conn.commit()


def _trigger_summary(monkeypatch, campaign_id: str = _CID) -> dict:
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Campaign is active. Credential scanning observed."),
    )
    resp = client.post(f"/api/campaigns/{campaign_id}/summary", headers=HEADERS)
    return resp


def _poll_job(job_id: str) -> dict:
    resp = client.get(f"/api/jobs/{job_id}", headers=HEADERS)
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Rate limiting — summary
# ---------------------------------------------------------------------------


def test_summary_succeeds_under_rate_limit(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 1)
    resp = _trigger_summary(monkeypatch)
    assert resp.status_code == 202


def test_summary_429_when_rate_limit_exhausted(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 1)
    _insert_recent_jobs(1, job_type="campaign_summary")
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 429


def test_summary_429_retry_after_header(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 1)
    _insert_recent_jobs(1, job_type="campaign_summary")
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "60"


def test_summary_429_detail_message(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 1)
    _insert_recent_jobs(1, job_type="campaign_summary")
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["detail"].lower()


def test_summary_rate_limit_writes_audit_record(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 1)
    _insert_recent_jobs(1, job_type="campaign_summary")
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 429
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    logs = audit_resp.json()["logs"]
    rate_limited = [lg for lg in logs if lg["status"] == "rate_limited"]
    assert len(rate_limited) >= 1
    assert rate_limited[0]["operation_type"] == "campaign_summary"


def test_summary_dedup_short_circuits_before_rate_limit(monkeypatch):
    """Existing active job returned immediately; rate limit is never evaluated."""
    _insert_campaign()
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 0)
    dedup_key = f"campaign_summary:{_CID}"
    # Insert a pending job with the dedup key directly.
    engine = get_engine()
    from datetime import UTC, datetime

    jid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO processing_jobs (
                    id, job_type, status, created_at,
                    triggered_by, resource_type, resource_id,
                    deduplication_key, progress_percent
                ) VALUES (
                    :id, 'campaign_summary', 'pending', :now,
                    'api_key', 'campaign', :cid, :dk, 0
                )
            """),
            {"id": jid, "now": now, "cid": _CID, "dk": dedup_key},
        )
        conn.commit()
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 202
    assert resp.json()["job_id"] == jid


# ---------------------------------------------------------------------------
# Rate limiting — brief
# ---------------------------------------------------------------------------


def test_brief_429_when_rate_limit_exhausted(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 1)
    _insert_recent_jobs(1, job_type="campaign_brief")
    resp = client.post("/api/campaigns/brief", headers=HEADERS)
    assert resp.status_code == 429


def test_brief_429_retry_after_header(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 1)
    _insert_recent_jobs(1, job_type="campaign_brief")
    resp = client.post("/api/campaigns/brief", headers=HEADERS)
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "60"


# ---------------------------------------------------------------------------
# GET /api/admin/ai-audit — auth
# ---------------------------------------------------------------------------


def test_audit_list_requires_api_key():
    resp = client.get("/api/admin/ai-audit")
    assert resp.status_code == 401


def test_audit_list_rejects_wrong_api_key():
    resp = client.get("/api/admin/ai-audit", headers={"x-api-key": "wrong"})
    assert resp.status_code == 401


def test_audit_list_rejects_jwt_only():
    from jose import jwt as jose_jwt

    secret = os.getenv("JWT_SECRET", "test-secret")
    token = jose_jwt.encode({"sub": "admin"}, secret, algorithm="HS256")
    resp = client.get(
        "/api/admin/ai-audit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/ai-audit — response shape
# ---------------------------------------------------------------------------


def test_audit_list_returns_200():
    resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    assert resp.status_code == 200


def test_audit_list_response_shape():
    resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    body = resp.json()
    assert "logs" in body
    assert "count" in body
    assert isinstance(body["logs"], list)
    assert isinstance(body["count"], int)


def test_audit_list_empty_initially():
    resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# GET /api/admin/ai-audit — records after AI job
# ---------------------------------------------------------------------------


def test_audit_record_created_after_summary_job(monkeypatch):
    _insert_campaign()
    resp = _trigger_summary(monkeypatch)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    _poll_job(job_id)
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    logs = audit_resp.json()["logs"]
    assert len(logs) >= 1
    matching = [lg for lg in logs if lg.get("job_id") == job_id]
    assert len(matching) == 1


def test_audit_record_fields_on_success(monkeypatch):
    _insert_campaign()
    resp = _trigger_summary(monkeypatch)
    job_id = resp.json()["job_id"]
    _poll_job(job_id)
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    record = next(lg for lg in audit_resp.json()["logs"] if lg.get("job_id") == job_id)
    assert record["status"] == "success"
    assert record["operation_type"] == "campaign_summary"
    assert record["backend"] == settings.AI_BACKEND
    assert record["model_name"] == "mock"
    assert record["triggered_by"] == "api_key"
    assert record["payload_bytes"] > 0
    assert record["response_bytes"] > 0
    assert record["latency_ms"] >= 0
    assert record["created_at"]


def test_audit_record_has_no_content_fields(monkeypatch):
    """Audit records must never contain prompt text or response content."""
    _insert_campaign()
    resp = _trigger_summary(monkeypatch)
    job_id = resp.json()["job_id"]
    _poll_job(job_id)
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    record = next(lg for lg in audit_resp.json()["logs"] if lg.get("job_id") == job_id)
    # These fields must not exist in the response.
    for forbidden in ("content", "prompt", "response", "text", "summary"):
        assert forbidden not in record, f"Forbidden field '{forbidden}' found in audit record"


def test_audit_record_has_output_id_on_success(monkeypatch):
    _insert_campaign()
    resp = _trigger_summary(monkeypatch)
    job_id = resp.json()["job_id"]
    _poll_job(job_id)
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    record = next(lg for lg in audit_resp.json()["logs"] if lg.get("job_id") == job_id)
    assert record["output_id"] is not None


def test_audit_record_created_after_brief_job(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(
        "app.jobs.runner.get_ai_backend",
        lambda: MockAIBackend("Threat brief summary here."),
    )
    resp = client.post("/api/campaigns/brief", headers=HEADERS)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    _poll_job(job_id)
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    logs = audit_resp.json()["logs"]
    matching = [lg for lg in logs if lg.get("job_id") == job_id]
    assert len(matching) == 1
    assert matching[0]["operation_type"] == "campaign_brief"


def test_audit_record_created_when_ai_disabled(monkeypatch):
    from app.ai import AIDisabledError

    _insert_campaign()

    class _DisabledBackend:
        model_name = "none"

        def generate(self, prompt):
            raise AIDisabledError("AI is disabled")

    monkeypatch.setattr("app.jobs.runner.get_ai_backend", lambda: _DisabledBackend())
    resp = client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    job = _poll_job(job_id)
    assert job["status"] == "failed"
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS)
    logs = audit_resp.json()["logs"]
    matching = [lg for lg in logs if lg.get("job_id") == job_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "disabled"
    assert matching[0]["error_type"] == "AIDisabledError"


# ---------------------------------------------------------------------------
# GET /api/admin/ai-audit — filters
# ---------------------------------------------------------------------------


def test_audit_filter_by_triggered_by(monkeypatch):
    _insert_campaign()
    resp = _trigger_summary(monkeypatch)
    _poll_job(resp.json()["job_id"])
    audit_resp = client.get(
        "/api/admin/ai-audit", headers=HEADERS, params={"triggered_by": "api_key"}
    )
    logs = audit_resp.json()["logs"]
    assert len(logs) >= 1
    assert all(lg["triggered_by"] == "api_key" for lg in logs)


def test_audit_filter_by_status_success(monkeypatch):
    _insert_campaign()
    resp = _trigger_summary(monkeypatch)
    _poll_job(resp.json()["job_id"])
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS, params={"status": "success"})
    logs = audit_resp.json()["logs"]
    assert len(logs) >= 1
    assert all(lg["status"] == "success" for lg in logs)


def test_audit_filter_by_backend(monkeypatch):
    _insert_campaign()
    resp = _trigger_summary(monkeypatch)
    _poll_job(resp.json()["job_id"])
    audit_resp = client.get(
        "/api/admin/ai-audit",
        headers=HEADERS,
        params={"backend": settings.AI_BACKEND},
    )
    logs = audit_resp.json()["logs"]
    assert len(logs) >= 1
    assert all(lg["backend"] == settings.AI_BACKEND for lg in logs)


def test_audit_filter_no_match_returns_empty():
    audit_resp = client.get(
        "/api/admin/ai-audit",
        headers=HEADERS,
        params={"triggered_by": "nobody-ever"},
    )
    body = audit_resp.json()
    assert body["logs"] == []
    assert body["count"] == 0


def test_audit_limit_param(monkeypatch):
    _insert_campaign()
    # Create 3 audit records.
    for _ in range(3):
        resp = _trigger_summary(monkeypatch)
        _poll_job(resp.json()["job_id"])
    audit_resp = client.get("/api/admin/ai-audit", headers=HEADERS, params={"limit": 2})
    body = audit_resp.json()
    assert len(body["logs"]) == 2
    assert body["count"] == 2


def test_audit_rate_limited_records_visible(monkeypatch):
    _insert_campaign()
    monkeypatch.setattr(settings, "AI_MAX_REQUESTS_PER_MINUTE", 1)
    _insert_recent_jobs(1, job_type="campaign_summary")
    client.post(f"/api/campaigns/{_CID}/summary", headers=HEADERS)
    audit_resp = client.get(
        "/api/admin/ai-audit",
        headers=HEADERS,
        params={"status": "rate_limited"},
    )
    logs = audit_resp.json()["logs"]
    assert len(logs) >= 1
    assert logs[0]["status"] == "rate_limited"
    assert logs[0]["error_type"] == "RateLimitExceeded"
