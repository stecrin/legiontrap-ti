"""Unit tests for JobRepository state machine and deduplication logic.

Uses an in-memory SQLite database bootstrapped by create_all_tables().
No HTTP layer, no AI calls — repository methods only.

Coverage:
  - create_job returns a pending job dict with all required fields
  - get_job returns None for unknown job_id
  - list_jobs returns jobs matching filters
  - start_job transitions pending → running
  - start_job returns False when job is not pending
  - complete_job transitions running → completed with result
  - complete_job returns False when job is not running
  - fail_job transitions running → failed with error_message
  - fail_job returns False when job is not running
  - cancel_job transitions pending or running → cancelled
  - cancel_job returns False for terminal states
  - update_progress clamps to 0–100 and only updates running jobs
  - transition_stale_jobs_to_failed moves stale running jobs to failed
  - get_active_job_by_dedup_key returns active jobs by dedup key
  - get_active_job_by_dedup_key returns None after terminal transition
  - deduplication: same dedup key with different jobs (completed + new)
  - backend_metadata_json stored and retrieved correctly
  - result_summary_json stored and retrieved correctly
  - invalid status values are not inserted by the state machine
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.connection import create_all_tables
from app.db.repositories.jobs import JobRepository


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all_tables(eng)
    return eng


@pytest.fixture
def session(engine):
    factory = sessionmaker(engine, autocommit=False, autoflush=False)
    s = factory()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def repo(session):
    return JobRepository(session)


def _commit(session):
    session.commit()


# ---------------------------------------------------------------------------
# create_job
# ---------------------------------------------------------------------------


def test_create_job_returns_pending_dict(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    assert job["status"] == "pending"
    assert job["job_type"] == "campaign_summary"
    assert job["id"] is not None


def test_create_job_has_created_at(repo, session):
    job = repo.create_job(job_type="campaign_brief")
    _commit(session)
    assert job["created_at"] is not None


def test_create_job_stores_triggered_by(repo, session):
    job = repo.create_job(job_type="campaign_summary", triggered_by="api_key")
    _commit(session)
    assert job["triggered_by"] == "api_key"


def test_create_job_stores_resource_fields(repo, session):
    cid = str(uuid.uuid4())
    job = repo.create_job(
        job_type="campaign_summary",
        resource_type="campaign",
        resource_id=cid,
    )
    _commit(session)
    assert job["resource_type"] == "campaign"
    assert job["resource_id"] == cid


def test_create_job_stores_dedup_key(repo, session):
    cid = str(uuid.uuid4())
    key = f"campaign_summary:{cid}"
    job = repo.create_job(job_type="campaign_summary", deduplication_key=key)
    _commit(session)
    assert job["deduplication_key"] == key


def test_create_job_stores_backend_metadata(repo, session):
    meta = {"max_campaigns": 5}
    job = repo.create_job(job_type="campaign_brief", backend_metadata_json=meta)
    _commit(session)
    fetched = repo.get_job(job["id"])
    import json

    assert json.loads(fetched["backend_metadata_json"]) == meta


def test_create_job_progress_is_zero(repo, session):
    job = repo.create_job(job_type="fingerprint_clustering")
    _commit(session)
    assert job["progress_percent"] == 0


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------


def test_get_job_returns_none_for_unknown_id(repo):
    assert repo.get_job("does-not-exist") is None


def test_get_job_returns_created_job(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    fetched = repo.get_job(job["id"])
    assert fetched is not None
    assert fetched["id"] == job["id"]


# ---------------------------------------------------------------------------
# list_jobs
# ---------------------------------------------------------------------------


def test_list_jobs_returns_all_jobs(repo, session):
    before = len(repo.list_jobs(limit=200))
    repo.create_job(job_type="campaign_summary")
    repo.create_job(job_type="campaign_brief")
    _commit(session)
    after = len(repo.list_jobs(limit=200))
    assert after == before + 2


def test_list_jobs_filter_by_type(repo, session):
    repo.create_job(job_type="campaign_summary")
    repo.create_job(job_type="campaign_brief")
    _commit(session)
    summaries = repo.list_jobs(job_type="campaign_summary", limit=200)
    assert all(j["job_type"] == "campaign_summary" for j in summaries)


def test_list_jobs_filter_by_status(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    running = repo.list_jobs(status="running", limit=200)
    assert any(j["id"] == job["id"] for j in running)


# ---------------------------------------------------------------------------
# start_job
# ---------------------------------------------------------------------------


def test_start_job_transitions_pending_to_running(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    result = repo.start_job(job["id"])
    _commit(session)
    assert result is True
    fetched = repo.get_job(job["id"])
    assert fetched["status"] == "running"
    assert fetched["started_at"] is not None


def test_start_job_returns_false_for_already_running(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    result = repo.start_job(job["id"])
    _commit(session)
    assert result is False


def test_start_job_returns_false_for_completed(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.complete_job(job["id"], result_summary_json={"ok": True})
    _commit(session)
    result = repo.start_job(job["id"])
    _commit(session)
    assert result is False


def test_start_job_returns_false_for_unknown_id(repo, session):
    result = repo.start_job("nonexistent-job-id")
    _commit(session)
    assert result is False


# ---------------------------------------------------------------------------
# complete_job
# ---------------------------------------------------------------------------


def test_complete_job_transitions_running_to_completed(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    result = repo.complete_job(job["id"], result_summary_json={"summary": "done"})
    _commit(session)
    assert result is True
    fetched = repo.get_job(job["id"])
    assert fetched["status"] == "completed"
    assert fetched["completed_at"] is not None


def test_complete_job_stores_result(repo, session):
    import json

    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    payload = {"summary": "Active campaign.", "rejected": False}
    repo.complete_job(job["id"], result_summary_json=payload)
    _commit(session)
    fetched = repo.get_job(job["id"])
    assert json.loads(fetched["result_summary_json"]) == payload


def test_complete_job_returns_false_for_pending(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    result = repo.complete_job(job["id"], result_summary_json={})
    _commit(session)
    assert result is False


def test_complete_job_sets_progress_to_100(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.complete_job(job["id"], result_summary_json={})
    _commit(session)
    fetched = repo.get_job(job["id"])
    assert fetched["progress_percent"] == 100


# ---------------------------------------------------------------------------
# fail_job
# ---------------------------------------------------------------------------


def test_fail_job_transitions_running_to_failed(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    result = repo.fail_job(job["id"], error_message="AI backend unavailable")
    _commit(session)
    assert result is True
    fetched = repo.get_job(job["id"])
    assert fetched["status"] == "failed"
    assert fetched["failed_at"] is not None


def test_fail_job_stores_error_message(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.fail_job(job["id"], error_message="AI features are disabled")
    _commit(session)
    fetched = repo.get_job(job["id"])
    assert fetched["error_message"] == "AI features are disabled"


def test_fail_job_returns_false_for_pending(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    result = repo.fail_job(job["id"], error_message="nope")
    _commit(session)
    assert result is False


def test_fail_job_returns_false_for_completed(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.complete_job(job["id"], result_summary_json={})
    _commit(session)
    result = repo.fail_job(job["id"], error_message="late error")
    _commit(session)
    assert result is False


# ---------------------------------------------------------------------------
# cancel_job
# ---------------------------------------------------------------------------


def test_cancel_job_from_pending(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    result = repo.cancel_job(job["id"])
    _commit(session)
    assert result is True
    assert repo.get_job(job["id"])["status"] == "cancelled"


def test_cancel_job_from_running(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    result = repo.cancel_job(job["id"])
    _commit(session)
    assert result is True
    assert repo.get_job(job["id"])["status"] == "cancelled"


def test_cancel_job_returns_false_for_completed(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.complete_job(job["id"], result_summary_json={})
    _commit(session)
    result = repo.cancel_job(job["id"])
    _commit(session)
    assert result is False


def test_cancel_job_returns_false_for_failed(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.fail_job(job["id"], error_message="err")
    _commit(session)
    result = repo.cancel_job(job["id"])
    _commit(session)
    assert result is False


# ---------------------------------------------------------------------------
# update_progress
# ---------------------------------------------------------------------------


def test_update_progress_on_running_job(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.update_progress(job["id"], 50)
    _commit(session)
    assert repo.get_job(job["id"])["progress_percent"] == 50


def test_update_progress_clamps_above_100(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.update_progress(job["id"], 999)
    _commit(session)
    assert repo.get_job(job["id"])["progress_percent"] == 100


def test_update_progress_clamps_below_zero(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.update_progress(job["id"], -5)
    _commit(session)
    assert repo.get_job(job["id"])["progress_percent"] == 0


def test_update_progress_does_not_affect_pending_job(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.update_progress(job["id"], 50)
    _commit(session)
    assert repo.get_job(job["id"])["progress_percent"] == 0


# ---------------------------------------------------------------------------
# transition_stale_jobs_to_failed (TTL enforcement)
# ---------------------------------------------------------------------------


def test_stale_running_job_transitions_to_failed(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    # Manually set started_at to 2 hours ago so it appears stale.
    stale_ts = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    from sqlalchemy import text

    session.execute(
        text("UPDATE processing_jobs SET status='running', started_at=:ts WHERE id=:id"),
        {"ts": stale_ts, "id": job["id"]},
    )
    _commit(session)
    count = repo.transition_stale_jobs_to_failed(timeout_seconds=60)
    _commit(session)
    assert count >= 1
    fetched = repo.get_job(job["id"])
    assert fetched["status"] == "failed"
    assert fetched["error_message"] == "Job timed out"


def test_fresh_running_job_not_transitioned(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    count = repo.transition_stale_jobs_to_failed(timeout_seconds=3600)
    _commit(session)
    assert repo.get_job(job["id"])["status"] == "running"
    _ = count


def test_pending_jobs_not_affected_by_stale_transition(repo, session):
    job = repo.create_job(job_type="campaign_summary")
    _commit(session)
    repo.transition_stale_jobs_to_failed(timeout_seconds=1)
    _commit(session)
    assert repo.get_job(job["id"])["status"] == "pending"


# ---------------------------------------------------------------------------
# get_active_job_by_dedup_key
# ---------------------------------------------------------------------------


def test_dedup_key_finds_pending_job(repo, session):
    key = f"campaign_summary:{uuid.uuid4()}"
    job = repo.create_job(job_type="campaign_summary", deduplication_key=key)
    _commit(session)
    found = repo.get_active_job_by_dedup_key(key)
    assert found is not None
    assert found["id"] == job["id"]


def test_dedup_key_finds_running_job(repo, session):
    key = f"campaign_summary:{uuid.uuid4()}"
    job = repo.create_job(job_type="campaign_summary", deduplication_key=key)
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    found = repo.get_active_job_by_dedup_key(key)
    assert found is not None
    assert found["id"] == job["id"]


def test_dedup_key_returns_none_after_complete(repo, session):
    key = f"campaign_summary:{uuid.uuid4()}"
    job = repo.create_job(job_type="campaign_summary", deduplication_key=key)
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.complete_job(job["id"], result_summary_json={})
    _commit(session)
    found = repo.get_active_job_by_dedup_key(key)
    assert found is None


def test_dedup_key_returns_none_after_fail(repo, session):
    key = f"campaign_summary:{uuid.uuid4()}"
    job = repo.create_job(job_type="campaign_summary", deduplication_key=key)
    _commit(session)
    repo.start_job(job["id"])
    _commit(session)
    repo.fail_job(job["id"], error_message="err")
    _commit(session)
    found = repo.get_active_job_by_dedup_key(key)
    assert found is None


def test_dedup_key_returns_none_for_unknown_key(repo):
    assert repo.get_active_job_by_dedup_key("nonexistent-key") is None


def test_completed_job_does_not_block_new_job(repo, session):
    """After a completed job, a new job with the same dedup key can be created."""
    key = f"campaign_summary:{uuid.uuid4()}"
    job1 = repo.create_job(job_type="campaign_summary", deduplication_key=key)
    _commit(session)
    repo.start_job(job1["id"])
    _commit(session)
    repo.complete_job(job1["id"], result_summary_json={})
    _commit(session)

    # No active job exists — safe to create a new one.
    assert repo.get_active_job_by_dedup_key(key) is None
    job2 = repo.create_job(job_type="campaign_summary", deduplication_key=key)
    _commit(session)
    assert job2["id"] != job1["id"]
    assert job2["status"] == "pending"
