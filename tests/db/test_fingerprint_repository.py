"""Repository tests for FingerprintRepository methods.

Uses the db_session fixture from tests/db/conftest.py for an isolated
in-memory SQLite database per test.  No HTTP, no application startup.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db.repository import EventRepository
from app.schemas.models import HoneypotEvent, RawEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IP = "203.0.113.10"
_TS = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


def _insert_event_for_ip(
    session,
    ip: str,
    ts: datetime,
    dst_port: int = 22,
    event_type: str = "auth_failed",
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Insert a raw_event + event row pair for ip and return the event id."""
    eid = str(uuid.uuid4())
    data: dict = {"ip": ip}
    if username is not None:
        data["username"] = username
    if password is not None:
        data["password"] = password

    raw = RawEvent(
        id=eid, ts=ts.isoformat(), source="cowrie", type="cowrie.login.failed", data=data
    )
    event = HoneypotEvent(
        id=eid,
        ts=ts,
        ingested_at=datetime.now(UTC),
        source="cowrie",
        event_type=event_type,
        src_ip=ip,
        dst_port=dst_port,
        service="ssh",
    )
    repo = EventRepository(session)
    repo.insert_raw_event(raw)
    repo.insert_event(event)
    repo.upsert_source_ip(ip, ts)
    return eid


@pytest.fixture
def with_source_ip(db_session):
    """Insert _IP into source_ips so behavioral_fingerprints FK is satisfied."""
    EventRepository(db_session).upsert_source_ip(_IP, _TS)
    db_session.flush()


def _fp_params(ip: str = _IP, event_count: int = 15, confidence: float = 0.5) -> dict:
    return {
        "ip": ip,
        "fingerprint_version": 1,
        "computed_at": datetime.now(UTC).isoformat(),
        "event_count": event_count,
        "timing_features": '{"interval":{"mean":1000,"stddev":0,"p25":1000,"p75":1000,"p95":1000}}',
        "sequence_features": (
            '{"port_sequence":[22],"event_type_sequence":["auth_failed"]'
            ',"credential_sequence":[]}'
        ),
        "protocol_features": None,
        "credential_features": None,
        "target_features": '{"port_freq":{"22":1.0},"unique_port_count":1,"top_dst_ports":[22]}',
        "tool_signals": None,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# get_events_for_fingerprint
# ---------------------------------------------------------------------------


def test_get_events_for_fingerprint_empty_when_no_events(db_session):
    repo = EventRepository(db_session)
    events = repo.get_events_for_fingerprint("1.2.3.4")
    assert events == []


def test_get_events_for_fingerprint_returns_events_for_ip(db_session):
    _insert_event_for_ip(db_session, _IP, _TS)
    db_session.flush()
    repo = EventRepository(db_session)
    events = repo.get_events_for_fingerprint(_IP)
    assert len(events) == 1


def test_get_events_for_fingerprint_only_for_target_ip(db_session):
    _insert_event_for_ip(db_session, _IP, _TS)
    _insert_event_for_ip(db_session, "10.0.0.1", _TS)
    db_session.flush()
    repo = EventRepository(db_session)
    events = repo.get_events_for_fingerprint(_IP)
    assert len(events) == 1


def test_get_events_for_fingerprint_event_dict_keys(db_session):
    _insert_event_for_ip(db_session, _IP, _TS)
    db_session.flush()
    repo = EventRepository(db_session)
    events = repo.get_events_for_fingerprint(_IP)
    assert len(events) == 1
    e = events[0]
    assert set(e.keys()) == {"ts", "dst_port", "event_type", "service", "source", "raw_data"}


def test_get_events_for_fingerprint_raw_data_is_dict(db_session):
    _insert_event_for_ip(db_session, _IP, _TS, username="admin", password="pass")
    db_session.flush()
    repo = EventRepository(db_session)
    events = repo.get_events_for_fingerprint(_IP)
    assert isinstance(events[0]["raw_data"], dict)


def test_get_events_for_fingerprint_ordered_chronologically(db_session):
    from datetime import timedelta

    t1 = _TS
    t2 = _TS + timedelta(minutes=5)
    t3 = _TS + timedelta(minutes=10)
    _insert_event_for_ip(db_session, _IP, t3)
    _insert_event_for_ip(db_session, _IP, t1)
    _insert_event_for_ip(db_session, _IP, t2)
    db_session.flush()
    repo = EventRepository(db_session)
    events = repo.get_events_for_fingerprint(_IP)
    ts_list = [e["ts"] for e in events]
    assert ts_list == sorted(ts_list)


def test_get_events_for_fingerprint_no_source_ip_in_returned_dicts(db_session):
    """The returned event dicts must not contain a src_ip key — only raw_data may
    have an ip field (from the sensor), and that's the sensor-reported IP,
    not added by the repository layer."""
    _insert_event_for_ip(db_session, _IP, _TS)
    db_session.flush()
    repo = EventRepository(db_session)
    events = repo.get_events_for_fingerprint(_IP)
    for e in events:
        # Top-level dict must have no src_ip key
        assert "src_ip" not in e


# ---------------------------------------------------------------------------
# upsert_behavioral_fingerprint
# ---------------------------------------------------------------------------


def test_upsert_fingerprint_creates_row(db_session, with_source_ip):
    repo = EventRepository(db_session)
    repo.upsert_behavioral_fingerprint(**_fp_params())
    db_session.flush()

    row = db_session.execute(
        text("SELECT source_ip, confidence FROM behavioral_fingerprints WHERE source_ip = :ip"),
        {"ip": _IP},
    ).fetchone()
    assert row is not None
    assert row[0] == _IP


def test_upsert_fingerprint_stores_confidence(db_session, with_source_ip):
    repo = EventRepository(db_session)
    repo.upsert_behavioral_fingerprint(**_fp_params(confidence=0.72))
    db_session.flush()

    row = db_session.execute(
        text("SELECT confidence FROM behavioral_fingerprints WHERE source_ip = :ip"),
        {"ip": _IP},
    ).fetchone()
    assert abs(row[0] - 0.72) < 1e-6


def test_upsert_fingerprint_updates_on_recomputation(db_session, with_source_ip):
    repo = EventRepository(db_session)
    repo.upsert_behavioral_fingerprint(**_fp_params(event_count=10, confidence=0.3))
    db_session.flush()
    repo.upsert_behavioral_fingerprint(**_fp_params(event_count=50, confidence=0.7))
    db_session.flush()

    rows = db_session.execute(
        text("SELECT COUNT(*) FROM behavioral_fingerprints WHERE source_ip = :ip"),
        {"ip": _IP},
    ).fetchone()
    assert rows[0] == 1  # still one row

    row = db_session.execute(
        text(
            "SELECT event_count_at_computation, confidence "
            "FROM behavioral_fingerprints WHERE source_ip = :ip"
        ),
        {"ip": _IP},
    ).fetchone()
    assert row[0] == 50
    assert abs(row[1] - 0.7) < 1e-6


def test_upsert_fingerprint_preserves_id_on_update(db_session, with_source_ip):
    repo = EventRepository(db_session)
    repo.upsert_behavioral_fingerprint(**_fp_params())
    db_session.flush()

    original_id = db_session.execute(
        text("SELECT id FROM behavioral_fingerprints WHERE source_ip = :ip"),
        {"ip": _IP},
    ).fetchone()[0]

    repo.upsert_behavioral_fingerprint(**_fp_params(event_count=99))
    db_session.flush()

    updated_id = db_session.execute(
        text("SELECT id FROM behavioral_fingerprints WHERE source_ip = :ip"),
        {"ip": _IP},
    ).fetchone()[0]
    assert original_id == updated_id


def test_upsert_fingerprint_null_features_accepted(db_session, with_source_ip):
    repo = EventRepository(db_session)
    params = _fp_params()
    params["timing_features"] = None
    params["sequence_features"] = None
    repo.upsert_behavioral_fingerprint(**params)
    db_session.flush()

    row = db_session.execute(
        text(
            "SELECT timing_features, sequence_features "
            "FROM behavioral_fingerprints WHERE source_ip = :ip"
        ),
        {"ip": _IP},
    ).fetchone()
    assert row[0] is None
    assert row[1] is None


# ---------------------------------------------------------------------------
# get_behavioral_fingerprint
# ---------------------------------------------------------------------------


def test_get_fingerprint_returns_none_for_unknown_ip(db_session):
    repo = EventRepository(db_session)
    assert repo.get_behavioral_fingerprint("1.2.3.4") is None


def test_get_fingerprint_returns_dict_after_upsert(db_session, with_source_ip):
    repo = EventRepository(db_session)
    repo.upsert_behavioral_fingerprint(**_fp_params())
    db_session.flush()

    fp = repo.get_behavioral_fingerprint(_IP)
    assert fp is not None
    assert isinstance(fp, dict)


def test_get_fingerprint_returned_keys(db_session, with_source_ip):
    repo = EventRepository(db_session)
    repo.upsert_behavioral_fingerprint(**_fp_params())
    db_session.flush()

    fp = repo.get_behavioral_fingerprint(_IP)
    assert set(fp.keys()) == {
        "id",
        "source_ip",
        "fingerprint_version",
        "computed_at",
        "event_count_at_computation",
        "timing_features",
        "sequence_features",
        "protocol_features",
        "credential_features",
        "target_features",
        "tool_signals",
        "confidence",
    }


def test_get_fingerprint_source_ip_matches(db_session, with_source_ip):
    repo = EventRepository(db_session)
    repo.upsert_behavioral_fingerprint(**_fp_params())
    db_session.flush()

    fp = repo.get_behavioral_fingerprint(_IP)
    assert fp["source_ip"] == _IP


def test_get_fingerprint_feature_json_is_parseable(db_session, with_source_ip):
    repo = EventRepository(db_session)
    repo.upsert_behavioral_fingerprint(**_fp_params())
    db_session.flush()

    fp = repo.get_behavioral_fingerprint(_IP)
    for key in ("timing_features", "target_features", "sequence_features"):
        val = fp[key]
        if val is not None:
            parsed = json.loads(val)
            assert isinstance(parsed, dict)
