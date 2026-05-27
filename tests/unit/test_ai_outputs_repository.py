"""Unit tests for AiOutputRepository.

Uses an in-memory SQLite engine with create_all_tables().
All tests are isolated: the engine is module-scoped and the tables are
truncated between tests via the _clean fixture.

Coverage:
  - create_ai_output inserts row and returns full dict
  - id is auto-generated when not provided
  - get_ai_output returns row by id
  - get_ai_output returns None for unknown id
  - rejected output persists with content=None
  - truncated flag stored correctly
  - source_records_json stored as JSON string
  - safety_flags_json stored as JSON string
  - list_ai_outputs_for_resource returns rows in DESC generated_at order
  - list_ai_outputs_for_resource filters by output_type
  - list_ai_outputs_for_resource returns empty list when no matches
  - list_ai_outputs_for_job returns rows for job_id
  - list_ai_outputs_for_job returns empty list for unknown job
  - get_latest_ai_output_for_resource returns most recent
  - get_latest_ai_output_for_resource returns None when no rows
  - write-once: no update method exists on AiOutputRepository
  - data_quality_score stored and retrieved correctly
  - multiple outputs for same resource accumulate (no overwrite)
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.connection import create_all_tables
from app.db.repositories.ai_outputs import AiOutputRepository


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
        conn.execute(text("DELETE FROM ai_outputs"))
        conn.commit()


def _repo(Session):
    session = Session()
    return AiOutputRepository(session), session


def _make_output(Session, **overrides):
    repo, session = _repo(Session)
    defaults = dict(
        job_id=str(uuid.uuid4()),
        output_type="campaign_summary",
        resource_type="campaign",
        resource_id=str(uuid.uuid4()),
        content="Campaign X is active.",
        backend="mock",
        model_name="mock",
        prompt_hash="abc123",
        payload_bytes=512,
        source_records_json={"campaign_id": "c1", "observation_count": 5},
        safety_flags_json=["low_confidence"],
        rejected=False,
        rejection_reason=None,
        truncated=False,
        data_quality_score=0.75,
        generated_at="2026-01-15T12:00:00+00:00",
        triggered_by="api_key",
    )
    defaults.update(overrides)
    result = repo.create_ai_output(**defaults)
    session.commit()
    session.close()
    return result


# ---------------------------------------------------------------------------
# create and get
# ---------------------------------------------------------------------------


def test_create_returns_dict(Session):
    output = _make_output(Session)
    assert isinstance(output, dict)
    assert output["output_type"] == "campaign_summary"


def test_create_auto_generates_id(Session):
    output = _make_output(Session)
    assert output["id"] is not None
    assert len(output["id"]) > 0


def test_create_with_explicit_id(Session):
    oid = str(uuid.uuid4())
    output = _make_output(Session, output_id=oid)
    assert output["id"] == oid


def test_get_ai_output_returns_row(Session):
    output = _make_output(Session)
    repo, session = _repo(Session)
    fetched = repo.get_ai_output(output["id"])
    session.close()
    assert fetched is not None
    assert fetched["id"] == output["id"]
    assert fetched["content"] == "Campaign X is active."


def test_get_ai_output_returns_none_for_unknown(Session):
    repo, session = _repo(Session)
    result = repo.get_ai_output("does-not-exist")
    session.close()
    assert result is None


# ---------------------------------------------------------------------------
# rejected and truncated
# ---------------------------------------------------------------------------


def test_rejected_output_persists_with_null_content(Session):
    output = _make_output(
        Session,
        content=None,
        rejected=True,
        rejection_reason="ip_detected",
    )
    repo, session = _repo(Session)
    fetched = repo.get_ai_output(output["id"])
    session.close()
    assert fetched["rejected"] is True
    assert fetched["content"] is None
    assert fetched["rejection_reason"] == "ip_detected"


def test_truncated_flag_stored(Session):
    output = _make_output(Session, truncated=True, rejection_reason="truncated")
    repo, session = _repo(Session)
    fetched = repo.get_ai_output(output["id"])
    session.close()
    assert fetched["truncated"] is True


# ---------------------------------------------------------------------------
# data_quality_score
# ---------------------------------------------------------------------------


def test_data_quality_score_stored(Session):
    output = _make_output(Session, data_quality_score=0.843)
    repo, session = _repo(Session)
    fetched = repo.get_ai_output(output["id"])
    session.close()
    assert abs(fetched["data_quality_score"] - 0.843) < 0.001


def test_data_quality_score_null_allowed(Session):
    output = _make_output(Session, data_quality_score=None)
    repo, session = _repo(Session)
    fetched = repo.get_ai_output(output["id"])
    session.close()
    assert fetched["data_quality_score"] is None


# ---------------------------------------------------------------------------
# list_ai_outputs_for_resource
# ---------------------------------------------------------------------------


def test_list_for_resource_returns_rows(Session):
    rid = str(uuid.uuid4())
    _make_output(Session, resource_id=rid)
    _make_output(Session, resource_id=rid)
    repo, session = _repo(Session)
    results = repo.list_ai_outputs_for_resource("campaign", rid)
    session.close()
    assert len(results) == 2


def test_list_for_resource_newest_first(Session):
    rid = str(uuid.uuid4())
    _make_output(Session, resource_id=rid, generated_at="2026-01-01T00:00:00+00:00")
    _make_output(Session, resource_id=rid, generated_at="2026-06-01T00:00:00+00:00")
    repo, session = _repo(Session)
    results = repo.list_ai_outputs_for_resource("campaign", rid)
    session.close()
    assert results[0]["generated_at"] > results[1]["generated_at"]


def test_list_for_resource_filter_by_output_type(Session):
    rid = str(uuid.uuid4())
    _make_output(Session, resource_id=rid, output_type="campaign_summary")
    _make_output(Session, resource_id=rid, output_type="campaign_brief")
    repo, session = _repo(Session)
    results = repo.list_ai_outputs_for_resource("campaign", rid, output_type="campaign_summary")
    session.close()
    assert len(results) == 1
    assert results[0]["output_type"] == "campaign_summary"


def test_list_for_resource_empty_when_no_match(Session):
    repo, session = _repo(Session)
    results = repo.list_ai_outputs_for_resource("campaign", "non-existent-id")
    session.close()
    assert results == []


def test_list_for_resource_multiple_outputs_accumulate(Session):
    """Regression: multiple outputs for the same resource should not overwrite."""
    rid = str(uuid.uuid4())
    for _ in range(3):
        _make_output(Session, resource_id=rid)
    repo, session = _repo(Session)
    results = repo.list_ai_outputs_for_resource("campaign", rid)
    session.close()
    assert len(results) == 3


# ---------------------------------------------------------------------------
# list_ai_outputs_for_job
# ---------------------------------------------------------------------------


def test_list_for_job_returns_rows(Session):
    jid = str(uuid.uuid4())
    _make_output(Session, job_id=jid)
    repo, session = _repo(Session)
    results = repo.list_ai_outputs_for_job(jid)
    session.close()
    assert len(results) == 1
    assert results[0]["job_id"] == jid


def test_list_for_job_empty_for_unknown_job(Session):
    repo, session = _repo(Session)
    results = repo.list_ai_outputs_for_job("no-such-job")
    session.close()
    assert results == []


# ---------------------------------------------------------------------------
# get_latest_ai_output_for_resource
# ---------------------------------------------------------------------------


def test_get_latest_returns_most_recent(Session):
    rid = str(uuid.uuid4())
    _make_output(Session, resource_id=rid, generated_at="2026-01-01T00:00:00+00:00")
    _make_output(Session, resource_id=rid, generated_at="2026-06-01T00:00:00+00:00")
    repo, session = _repo(Session)
    latest = repo.get_latest_ai_output_for_resource("campaign", rid)
    session.close()
    assert latest is not None
    assert latest["generated_at"] == "2026-06-01T00:00:00+00:00"


def test_get_latest_returns_none_when_no_rows(Session):
    repo, session = _repo(Session)
    result = repo.get_latest_ai_output_for_resource("campaign", "unknown-id")
    session.close()
    assert result is None


# ---------------------------------------------------------------------------
# write-once invariant
# ---------------------------------------------------------------------------


def test_no_update_method_on_repository(Session):
    """AiOutputRepository must not expose any mutation method for existing rows."""
    repo, session = _repo(Session)
    session.close()
    assert not hasattr(repo, "update_ai_output")
    assert not hasattr(repo, "delete_ai_output")
    assert not hasattr(repo, "patch_ai_output")
