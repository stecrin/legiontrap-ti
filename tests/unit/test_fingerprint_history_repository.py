"""Unit tests for FingerprintHistoryRepository.

Uses an in-memory SQLite engine with create_all_tables().
All tests are isolated: the engine is module-scoped and the table is
truncated between tests via the _clean fixture.

Coverage:
  - insert_fingerprint_history inserts row and returns full dict
  - id is auto-generated when not provided
  - explicit id is stored verbatim
  - get_fingerprint_history_entry returns row by id
  - get_fingerprint_history_entry returns None for unknown id
  - all fields stored correctly
  - nullable fields (fingerprint_id, campaign_id) may be None
  - feature columns may be None
  - list_fingerprint_history_for_ip returns records oldest first
  - list_fingerprint_history_for_ip respects limit
  - list_fingerprint_history_for_ip returns empty list for unknown ip
  - list_fingerprint_history_for_campaign returns records oldest first
  - list_fingerprint_history_for_campaign respects limit
  - list_fingerprint_history_for_campaign returns empty list for unknown id
  - count_fingerprint_history_for_ip returns correct count
  - count_fingerprint_history_for_ip returns 0 for unknown ip
  - write-once: no update method exists on FingerprintHistoryRepository
  - write-once: no delete method exists on FingerprintHistoryRepository
  - multiple history rows for same ip accumulate
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.connection import create_all_tables
from app.db.repositories.fingerprint_history import FingerprintHistoryRepository


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
        conn.execute(text("DELETE FROM fingerprint_history"))
        conn.commit()


def _repo(Session):
    s = Session()
    return FingerprintHistoryRepository(s), s


def _insert(Session, **overrides):
    repo, s = _repo(Session)
    kwargs = dict(
        source_ip="192.0.2.1",
        fingerprint_version=1,
        computed_at="2026-01-01T00:00:00+00:00",
        event_count_at_computation=10,
        confidence=0.75,
    )
    kwargs.update(overrides)
    row = repo.insert_fingerprint_history(**kwargs)
    s.commit()
    s.close()
    return row


# ---------------------------------------------------------------------------
# insert / get
# ---------------------------------------------------------------------------


def test_insert_returns_dict(Session):
    row = _insert(Session)
    assert isinstance(row, dict)


def test_auto_id(Session):
    row = _insert(Session)
    assert row["id"]
    assert len(row["id"]) == 36


def test_explicit_id(Session):
    hid = str(uuid.uuid4())
    row = _insert(Session, history_id=hid)
    assert row["id"] == hid


def test_get_by_id(Session):
    row = _insert(Session)
    repo, s = _repo(Session)
    fetched = repo.get_fingerprint_history_entry(row["id"])
    s.close()
    assert fetched is not None
    assert fetched["id"] == row["id"]


def test_get_unknown_returns_none(Session):
    repo, s = _repo(Session)
    result = repo.get_fingerprint_history_entry(str(uuid.uuid4()))
    s.close()
    assert result is None


# ---------------------------------------------------------------------------
# Field storage
# ---------------------------------------------------------------------------


def test_all_fields_stored(Session):
    fp_id = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    row = _insert(
        Session,
        fingerprint_id=fp_id,
        source_ip="10.0.0.1",
        campaign_id=cid,
        fingerprint_version=1,
        computed_at="2026-03-15T12:00:00+00:00",
        event_count_at_computation=42,
        confidence=0.88,
        timing_features='{"mean_inter_arrival": 1.5}',
        sequence_features='{"top_ports": [22, 80]}',
        protocol_features='{"tls_ratio": 0.4}',
        credential_features='{"unique_usernames": 3}',
        target_features='{"port_entropy": 2.1}',
    )
    assert row["fingerprint_id"] == fp_id
    assert row["source_ip"] == "10.0.0.1"
    assert row["campaign_id"] == cid
    assert row["fingerprint_version"] == 1
    assert row["computed_at"] == "2026-03-15T12:00:00+00:00"
    assert row["event_count_at_computation"] == 42
    assert row["confidence"] == pytest.approx(0.88)
    assert row["timing_features"] == '{"mean_inter_arrival": 1.5}'
    assert row["sequence_features"] == '{"top_ports": [22, 80]}'
    assert row["protocol_features"] == '{"tls_ratio": 0.4}'
    assert row["credential_features"] == '{"unique_usernames": 3}'
    assert row["target_features"] == '{"port_entropy": 2.1}'
    assert row["created_at"]


def test_nullable_fingerprint_id(Session):
    row = _insert(Session, fingerprint_id=None)
    assert row["fingerprint_id"] is None


def test_nullable_campaign_id(Session):
    row = _insert(Session, campaign_id=None)
    assert row["campaign_id"] is None


def test_nullable_feature_columns(Session):
    row = _insert(
        Session,
        timing_features=None,
        sequence_features=None,
        protocol_features=None,
        credential_features=None,
        target_features=None,
    )
    assert row["timing_features"] is None
    assert row["sequence_features"] is None
    assert row["protocol_features"] is None
    assert row["credential_features"] is None
    assert row["target_features"] is None


# ---------------------------------------------------------------------------
# list_fingerprint_history_for_ip
# ---------------------------------------------------------------------------


def test_list_for_ip_oldest_first(Session):
    ip = "10.1.1.1"
    _insert(Session, source_ip=ip, computed_at="2026-01-03T00:00:00+00:00")
    _insert(Session, source_ip=ip, computed_at="2026-01-01T00:00:00+00:00")
    _insert(Session, source_ip=ip, computed_at="2026-01-02T00:00:00+00:00")
    repo, s = _repo(Session)
    rows = repo.list_fingerprint_history_for_ip(ip)
    s.close()
    dates = [r["computed_at"] for r in rows]
    assert dates == sorted(dates)


def test_list_for_ip_respects_limit(Session):
    ip = "10.1.1.2"
    for i in range(5):
        _insert(Session, source_ip=ip, computed_at=f"2026-01-0{i+1}T00:00:00+00:00")
    repo, s = _repo(Session)
    rows = repo.list_fingerprint_history_for_ip(ip, limit=2)
    s.close()
    assert len(rows) == 2


def test_list_for_ip_unknown(Session):
    repo, s = _repo(Session)
    rows = repo.list_fingerprint_history_for_ip("192.168.255.255")
    s.close()
    assert rows == []


def test_list_for_ip_only_returns_that_ip(Session):
    _insert(Session, source_ip="10.2.0.1")
    _insert(Session, source_ip="10.2.0.2")
    repo, s = _repo(Session)
    rows = repo.list_fingerprint_history_for_ip("10.2.0.1")
    s.close()
    assert all(r["source_ip"] == "10.2.0.1" for r in rows)


# ---------------------------------------------------------------------------
# list_fingerprint_history_for_campaign
# ---------------------------------------------------------------------------


def test_list_for_campaign_oldest_first(Session):
    cid = str(uuid.uuid4())
    _insert(Session, campaign_id=cid, computed_at="2026-02-03T00:00:00+00:00")
    _insert(Session, campaign_id=cid, computed_at="2026-02-01T00:00:00+00:00")
    _insert(Session, campaign_id=cid, computed_at="2026-02-02T00:00:00+00:00")
    repo, s = _repo(Session)
    rows = repo.list_fingerprint_history_for_campaign(cid)
    s.close()
    dates = [r["computed_at"] for r in rows]
    assert dates == sorted(dates)


def test_list_for_campaign_respects_limit(Session):
    cid = str(uuid.uuid4())
    for i in range(5):
        _insert(Session, campaign_id=cid, computed_at=f"2026-02-0{i+1}T00:00:00+00:00")
    repo, s = _repo(Session)
    rows = repo.list_fingerprint_history_for_campaign(cid, limit=3)
    s.close()
    assert len(rows) == 3


def test_list_for_campaign_unknown(Session):
    repo, s = _repo(Session)
    rows = repo.list_fingerprint_history_for_campaign(str(uuid.uuid4()))
    s.close()
    assert rows == []


def test_list_for_campaign_excludes_other_campaigns(Session):
    cid_a = str(uuid.uuid4())
    cid_b = str(uuid.uuid4())
    _insert(Session, campaign_id=cid_a)
    _insert(Session, campaign_id=cid_b)
    repo, s = _repo(Session)
    rows = repo.list_fingerprint_history_for_campaign(cid_a)
    s.close()
    assert all(r["campaign_id"] == cid_a for r in rows)


# ---------------------------------------------------------------------------
# count_fingerprint_history_for_ip
# ---------------------------------------------------------------------------


def test_count_for_ip(Session):
    ip = "10.3.0.1"
    _insert(Session, source_ip=ip)
    _insert(Session, source_ip=ip)
    _insert(Session, source_ip=ip)
    repo, s = _repo(Session)
    count = repo.count_fingerprint_history_for_ip(ip)
    s.close()
    assert count == 3


def test_count_for_unknown_ip_returns_zero(Session):
    repo, s = _repo(Session)
    count = repo.count_fingerprint_history_for_ip("192.168.0.99")
    s.close()
    assert count == 0


def test_multiple_rows_accumulate(Session):
    ip = "10.3.0.2"
    for _ in range(4):
        _insert(Session, source_ip=ip)
    repo, s = _repo(Session)
    assert repo.count_fingerprint_history_for_ip(ip) == 4
    s.close()


# ---------------------------------------------------------------------------
# Write-once invariant
# ---------------------------------------------------------------------------


def test_no_update_method(Session):
    assert not hasattr(FingerprintHistoryRepository, "update_fingerprint_history")


def test_no_delete_method(Session):
    assert not hasattr(FingerprintHistoryRepository, "delete_fingerprint_history")
