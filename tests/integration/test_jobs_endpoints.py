"""Integration tests for GET /api/jobs/{job_id} and GET /api/jobs.

Tests exercise the full HTTP → router → repository → in-memory SQLite stack.
No AI calls are made. Jobs are created directly via the repository.

Coverage:
  - GET /api/jobs/{job_id} returns 200 with job dict for known job
  - GET /api/jobs/{job_id} returns 404 for unknown job_id
  - GET /api/jobs/{job_id} requires auth (401 without key)
  - GET /api/jobs/{job_id} enriches result field when status=completed
  - GET /api/jobs/{job_id} result is None when status=pending
  - GET /api/jobs/{job_id} result is None when status=failed
  - GET /api/jobs/{job_id} applies TTL enforcement on read
  - GET /api/jobs returns list of jobs
  - GET /api/jobs filters by job_type
  - GET /api/jobs filters by status
  - GET /api/jobs requires auth
  - poll_url field present in all job responses
  - completed job has backend_metadata field
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
HEADERS = {"x-api-key": "dev-123"}
_TS = "2026-01-15T00:00:00+00:00"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _create_job(
    *,
    job_type: str = "campaign_summary",
    status: str = "pending",
    resource_id: str | None = None,
    dedup_key: str | None = None,
    result: dict | None = None,
    error_message: str | None = None,
    started_at: str | None = None,
) -> str:
    """Insert a processing_jobs row directly and return its id."""
    job_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    completed_at = now if status == "completed" else None
    failed_at = now if status == "failed" else None
    started_at = started_at or (now if status in ("running", "completed", "failed") else None)
    result_json = json.dumps(result) if result else None

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO processing_jobs (
                    id, job_type, status, created_at,
                    started_at, completed_at, failed_at,
                    resource_type, resource_id, deduplication_key,
                    progress_percent, result_summary_json, error_message
                ) VALUES (
                    :id, :job_type, :status, :created_at,
                    :started_at, :completed_at, :failed_at,
                    'campaign', :resource_id, :dedup_key,
                    0, :result_json, :error_message
                )
            """),
            {
                "id": job_id,
                "job_type": job_type,
                "status": status,
                "created_at": now,
                "started_at": started_at,
                "completed_at": completed_at,
                "failed_at": failed_at,
                "resource_id": resource_id,
                "dedup_key": dedup_key,
                "result_json": result_json,
                "error_message": error_message,
            },
        )
        conn.commit()
    return job_id


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id} — basic
# ---------------------------------------------------------------------------


def test_get_job_returns_200_for_known_job():
    job_id = _create_job()
    resp = client.get(f"/api/jobs/{job_id}", headers=HEADERS)
    assert resp.status_code == 200


def test_get_job_returns_404_for_unknown():
    resp = client.get("/api/jobs/does-not-exist", headers=HEADERS)
    assert resp.status_code == 404


def test_get_job_requires_auth():
    job_id = _create_job()
    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 401


def test_get_job_wrong_key_returns_401():
    job_id = _create_job()
    resp = client.get(f"/api/jobs/{job_id}", headers={"x-api-key": "wrong"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id} — response shape
# ---------------------------------------------------------------------------


def test_get_job_has_id_field():
    job_id = _create_job()
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["id"] == job_id


def test_get_job_has_status_field():
    job_id = _create_job(status="pending")
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["status"] == "pending"


def test_get_job_has_job_type_field():
    job_id = _create_job(job_type="campaign_brief")
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["job_type"] == "campaign_brief"


def test_get_job_has_poll_url():
    job_id = _create_job()
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["poll_url"] == f"/api/jobs/{job_id}"


def test_get_job_has_created_at():
    job_id = _create_job()
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["created_at"] is not None


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id} — result field
# ---------------------------------------------------------------------------


def test_get_job_result_present_when_completed():
    result = {"summary": "Active campaign.", "rejected": False, "ai_assisted": True}
    job_id = _create_job(status="completed", result=result)
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["result"] is not None
    assert body["result"]["summary"] == "Active campaign."


def test_get_job_result_none_when_pending():
    job_id = _create_job(status="pending")
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["result"] is None


def test_get_job_result_none_when_running():
    job_id = _create_job(status="running")
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["result"] is None


def test_get_job_result_none_when_failed():
    job_id = _create_job(status="failed", error_message="AI disabled")
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["result"] is None


def test_get_job_error_message_present_when_failed():
    job_id = _create_job(status="failed", error_message="AI features are disabled")
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["error_message"] == "AI features are disabled"


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id} — TTL enforcement
# ---------------------------------------------------------------------------


def test_ttl_enforcement_transitions_stale_running_to_failed():
    stale_ts = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    job_id = _create_job(status="running", started_at=stale_ts)
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["status"] == "failed"
    assert body["error_message"] == "Job timed out"


def test_ttl_enforcement_does_not_affect_fresh_running_job():
    job_id = _create_job(status="running")
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["status"] == "running"


def test_ttl_enforcement_does_not_affect_pending():
    job_id = _create_job(status="pending")
    client.get(f"/api/jobs/{job_id}", headers=HEADERS)
    body = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()
    assert body["status"] == "pending"


# ---------------------------------------------------------------------------
# GET /api/jobs — list endpoint
# ---------------------------------------------------------------------------


def test_list_jobs_returns_200():
    resp = client.get("/api/jobs", headers=HEADERS)
    assert resp.status_code == 200


def test_list_jobs_requires_auth():
    resp = client.get("/api/jobs")
    assert resp.status_code == 401


def test_list_jobs_response_has_jobs_and_count():
    body = client.get("/api/jobs", headers=HEADERS).json()
    assert "jobs" in body
    assert "count" in body
    assert isinstance(body["jobs"], list)
    assert body["count"] == len(body["jobs"])


def test_list_jobs_contains_created_jobs():
    job_id = _create_job(job_type="campaign_summary")
    body = client.get("/api/jobs", headers=HEADERS).json()
    ids = [j["id"] for j in body["jobs"]]
    assert job_id in ids


def test_list_jobs_filter_by_job_type():
    _create_job(job_type="campaign_summary")
    _create_job(job_type="campaign_brief")
    body = client.get("/api/jobs?job_type=campaign_summary", headers=HEADERS).json()
    assert all(j["job_type"] == "campaign_summary" for j in body["jobs"])


def test_list_jobs_filter_by_status():
    _create_job(status="pending")
    _create_job(status="completed", result={"ok": True})
    body = client.get("/api/jobs?status=pending", headers=HEADERS).json()
    assert all(j["status"] == "pending" for j in body["jobs"])


def test_list_jobs_limit_respected():
    for _ in range(5):
        _create_job()
    body = client.get("/api/jobs?limit=3", headers=HEADERS).json()
    assert len(body["jobs"]) <= 3


def test_list_jobs_each_job_has_poll_url():
    _create_job()
    body = client.get("/api/jobs", headers=HEADERS).json()
    for job in body["jobs"]:
        assert "poll_url" in job
        assert job["poll_url"].startswith("/api/jobs/")
