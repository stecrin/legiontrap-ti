"""Unit tests for AiAuditLogRepository.

Uses an in-memory SQLite engine with create_all_tables().
All tests are isolated: the engine is module-scoped and the table is
truncated between tests via the _clean fixture.

Coverage:
  - create_ai_audit_log inserts row and returns full dict
  - id is auto-generated when not provided
  - explicit id is stored verbatim
  - get_ai_audit_log returns row by id
  - get_ai_audit_log returns None for unknown id
  - all fields stored correctly (backend, model_name, bytes, latency, etc.)
  - status=success stored correctly
  - status=failure with error_type stored correctly
  - status=disabled stored correctly
  - status=unavailable stored correctly
  - status=rate_limited stored correctly
  - list_ai_audit_logs returns records newest first
  - list_ai_audit_logs filters by triggered_by
  - list_ai_audit_logs filters by backend
  - list_ai_audit_logs filters by status
  - list_ai_audit_logs filters by job_id
  - list_ai_audit_logs respects limit
  - list_ai_audit_logs returns empty list when no matches
  - list_ai_audit_logs_for_job returns records for job_id
  - list_ai_audit_logs_for_job returns empty list for unknown job
  - write-once: no update method exists on AiAuditLogRepository
  - write-once: no delete method exists on AiAuditLogRepository
  - job_id and output_id may be None
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.connection import create_all_tables
from app.db.repositories.ai_audit_log import AiAuditLogRepository


@pytest.fixture(scope="module")
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_all_tables(e)
    return e


@pytest.fixture(scope="module")
def Session(engine):
    return sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def _clean(engine):
    yield
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM ai_audit_log"))
        conn.commit()


def _repo(Session):
    s = Session()
    return AiAuditLogRepository(s), s


def _make_log(Session, **overrides):
    repo, s = _repo(Session)
    kwargs = dict(
        backend="mock",
        model_name="mock",
        operation_type="campaign_summary",
        status="success",
    )
    kwargs.update(overrides)
    log = repo.create_ai_audit_log(**kwargs)
    s.commit()
    s.close()
    return log


# ---------------------------------------------------------------------------
# create / get
# ---------------------------------------------------------------------------


def test_create_returns_dict(Session):
    log = _make_log(Session)
    assert isinstance(log, dict)


def test_auto_id(Session):
    log = _make_log(Session)
    assert log["id"]
    assert len(log["id"]) == 36  # UUID4


def test_explicit_id(Session):
    lid = str(uuid.uuid4())
    log = _make_log(Session, log_id=lid)
    assert log["id"] == lid


def test_get_by_id(Session):
    log = _make_log(Session)
    repo, s = _repo(Session)
    fetched = repo.get_ai_audit_log(log["id"])
    s.close()
    assert fetched is not None
    assert fetched["id"] == log["id"]


def test_get_unknown_returns_none(Session):
    repo, s = _repo(Session)
    result = repo.get_ai_audit_log(str(uuid.uuid4()))
    s.close()
    assert result is None


# ---------------------------------------------------------------------------
# Field storage
# ---------------------------------------------------------------------------


def test_all_fields_stored(Session):
    job_id = str(uuid.uuid4())
    output_id = str(uuid.uuid4())
    log = _make_log(
        Session,
        job_id=job_id,
        output_id=output_id,
        triggered_by="user:alice",
        backend="claude",
        model_name="claude-3-haiku",
        operation_type="campaign_brief",
        resource_type="campaign",
        resource_id="camp-001",
        payload_bytes=1024,
        response_bytes=512,
        latency_ms=350,
        status="success",
        error_type=None,
    )
    assert log["job_id"] == job_id
    assert log["output_id"] == output_id
    assert log["triggered_by"] == "user:alice"
    assert log["backend"] == "claude"
    assert log["model_name"] == "claude-3-haiku"
    assert log["operation_type"] == "campaign_brief"
    assert log["resource_type"] == "campaign"
    assert log["resource_id"] == "camp-001"
    assert log["payload_bytes"] == 1024
    assert log["response_bytes"] == 512
    assert log["latency_ms"] == 350
    assert log["status"] == "success"
    assert log["error_type"] is None
    assert log["created_at"]


def test_status_failure_with_error_type(Session):
    log = _make_log(
        Session,
        status="failure",
        error_type="AIBackendError",
        response_bytes=0,
    )
    assert log["status"] == "failure"
    assert log["error_type"] == "AIBackendError"


def test_status_disabled(Session):
    log = _make_log(Session, status="disabled", error_type="AIDisabledError")
    assert log["status"] == "disabled"
    assert log["error_type"] == "AIDisabledError"


def test_status_unavailable(Session):
    log = _make_log(Session, status="unavailable", error_type="AIBackendUnavailableError")
    assert log["status"] == "unavailable"


def test_status_rate_limited(Session):
    log = _make_log(Session, status="rate_limited", error_type="RateLimitExceeded")
    assert log["status"] == "rate_limited"
    assert log["error_type"] == "RateLimitExceeded"


def test_nullable_job_and_output_id(Session):
    log = _make_log(Session, job_id=None, output_id=None)
    assert log["job_id"] is None
    assert log["output_id"] is None


def test_default_bytes_and_latency(Session):
    log = _make_log(Session)
    assert log["payload_bytes"] == 0
    assert log["response_bytes"] == 0
    assert log["latency_ms"] == 0


# ---------------------------------------------------------------------------
# list_ai_audit_logs
# ---------------------------------------------------------------------------


def test_list_returns_newest_first(Session):
    _make_log(Session, created_at="2026-01-01T00:00:00+00:00", triggered_by="user:a")
    _make_log(Session, created_at="2026-01-03T00:00:00+00:00", triggered_by="user:a")
    _make_log(Session, created_at="2026-01-02T00:00:00+00:00", triggered_by="user:a")
    repo, s = _repo(Session)
    logs = repo.list_ai_audit_logs()
    s.close()
    dates = [lg["created_at"] for lg in logs]
    assert dates == sorted(dates, reverse=True)


def test_list_filter_triggered_by(Session):
    _make_log(Session, triggered_by="user:alice")
    _make_log(Session, triggered_by="user:bob")
    _make_log(Session, triggered_by="user:alice")
    repo, s = _repo(Session)
    logs = repo.list_ai_audit_logs(triggered_by="user:alice")
    s.close()
    assert len(logs) == 2
    assert all(lg["triggered_by"] == "user:alice" for lg in logs)


def test_list_filter_backend(Session):
    _make_log(Session, backend="claude", model_name="claude-3-haiku")
    _make_log(Session, backend="ollama", model_name="llama3")
    repo, s = _repo(Session)
    logs = repo.list_ai_audit_logs(backend="claude")
    s.close()
    assert len(logs) == 1
    assert logs[0]["backend"] == "claude"


def test_list_filter_status(Session):
    _make_log(Session, status="success")
    _make_log(Session, status="failure", error_type="AIBackendError")
    _make_log(Session, status="rate_limited", error_type="RateLimitExceeded")
    repo, s = _repo(Session)
    failures = repo.list_ai_audit_logs(status="failure")
    s.close()
    assert len(failures) == 1
    assert failures[0]["status"] == "failure"


def test_list_filter_job_id(Session):
    jid = str(uuid.uuid4())
    _make_log(Session, job_id=jid)
    _make_log(Session, job_id=str(uuid.uuid4()))
    repo, s = _repo(Session)
    logs = repo.list_ai_audit_logs(job_id=jid)
    s.close()
    assert len(logs) == 1
    assert logs[0]["job_id"] == jid


def test_list_respects_limit(Session):
    for _ in range(5):
        _make_log(Session)
    repo, s = _repo(Session)
    logs = repo.list_ai_audit_logs(limit=3)
    s.close()
    assert len(logs) == 3


def test_list_empty_no_match(Session):
    repo, s = _repo(Session)
    logs = repo.list_ai_audit_logs(triggered_by="nobody")
    s.close()
    assert logs == []


# ---------------------------------------------------------------------------
# list_ai_audit_logs_for_job
# ---------------------------------------------------------------------------


def test_list_for_job(Session):
    jid = str(uuid.uuid4())
    _make_log(Session, job_id=jid)
    _make_log(Session, job_id=jid)
    _make_log(Session, job_id=str(uuid.uuid4()))
    repo, s = _repo(Session)
    logs = repo.list_ai_audit_logs_for_job(jid)
    s.close()
    assert len(logs) == 2
    assert all(lg["job_id"] == jid for lg in logs)


def test_list_for_job_unknown(Session):
    repo, s = _repo(Session)
    logs = repo.list_ai_audit_logs_for_job(str(uuid.uuid4()))
    s.close()
    assert logs == []


# ---------------------------------------------------------------------------
# Write-once invariant
# ---------------------------------------------------------------------------


def test_no_update_method(Session):
    assert not hasattr(AiAuditLogRepository, "update_ai_audit_log")


def test_no_delete_method(Session):
    assert not hasattr(AiAuditLogRepository, "delete_ai_audit_log")
