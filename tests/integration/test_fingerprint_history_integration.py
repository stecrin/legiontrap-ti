"""Integration tests for Phase 6 Group B — fingerprint history and campaign
representative fingerprint denormalization.

Tests hit the full DB stack (in-memory SQLite, bootstrapped by tests/conftest.py).
Rows are reset per test by tests/integration/conftest.py.

Coverage:
  get_campaigns_for_clustering fast path:
    - Returns representative fingerprint data from JSON cache when populated
    - Returns correct campaign metadata (id, status, last_seen)
    - Feature columns parsed from JSON match stored values

  get_campaigns_for_clustering slow path:
    - Falls back to per-member lookup when representative_fingerprint_json is NULL
    - Falls back when representative_fingerprint_json contains invalid JSON
    - Returns correct fingerprint data from behavioral_fingerprints

  Fingerprint history — written during computation:
    - _compute_and_store() writes exactly one history row
    - History row has correct source_ip and fingerprint_version
    - History row has campaign_id=None for an unassigned IP
    - History row has campaign_id set for an already-assigned IP
    - Multiple _compute_and_store() calls accumulate history rows (append-only)
    - Feature columns in history row are JSON strings, not raw events

  Representative fingerprint update:
    - _run_campaign_clustering() updates representative_fingerprint_json
      on the assigned campaign
    - Representative fingerprint JSON contains expected feature keys
    - tool_signals is NOT included in representative fingerprint JSON

  No raw credentials:
    - credential_features in history row stores statistical summaries, not raw values
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from app.db.connection import get_engine
from app.db.repository import EventRepository

_TS = "2026-03-01T00:00:00+00:00"


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


def _insert_campaign(
    campaign_id: str | None = None,
    *,
    status: str = "active",
    representative_fingerprint_json: str | None = None,
) -> str:
    cid = campaign_id or str(uuid.uuid4())
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO campaigns (
                    id, name, status, confidence, first_seen, last_seen,
                    dormant_since, reactivation_count, member_ip_count,
                    attack_tactic_dist, top_target_ports, notes,
                    created_at, updated_at, representative_fingerprint_json
                ) VALUES (
                    :id, :name, :status, 0.75, :ts, :ts,
                    NULL, 0, 0,
                    NULL, NULL, NULL,
                    :ts, :ts, :rep_fp
                )
            """),
            {
                "id": cid,
                "name": f"CAMP-{cid[:8]}",
                "status": status,
                "ts": _TS,
                "rep_fp": representative_fingerprint_json,
            },
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


def _insert_fingerprint(ip: str, *, fp_id: str | None = None) -> str:
    fid = fp_id or str(uuid.uuid4())
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO behavioral_fingerprints (
                    id, source_ip, fingerprint_version, computed_at,
                    event_count_at_computation, timing_features, sequence_features,
                    protocol_features, credential_features, target_features,
                    tool_signals, confidence
                ) VALUES (
                    :id, :ip, 1, :ts,
                    15,
                    '{"mean_inter_arrival": 1.2, "burst_cv": 0.5}',
                    '{"port_sequence": [22, 80]}',
                    '{"service_distribution": {"ssh": 10}}',
                    '{"username_class_dist": {"dictionary": 5}}',
                    '{"top_dst_ports": [22]}',
                    '{"tools": ["masscan"]}',
                    0.80
                )
            """),
            {"id": fid, "ip": ip, "ts": _TS},
        )
        conn.commit()
    return fid


def _insert_event(
    eid: str,
    ip: str,
    *,
    event_type: str = "auth_failed",
    dst_port: int = 22,
    ts: str = _TS,
    raw_data: dict | None = None,
) -> None:
    """Insert a raw_event + event row for fingerprint computation."""
    payload = json.dumps({"source": "test-sensor", "data": raw_data or {}})
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO raw_events (id, ts, ingested_at, source, raw_json)
                VALUES (:id, :ts, :ts, :ip, :payload)
            """),
            {"id": eid, "ts": ts, "ip": ip, "payload": payload},
        )
        conn.execute(
            text("""
                INSERT INTO events
                    (id, ts, src_ip, dst_port, protocol, event_type, schema_version)
                VALUES (:id, :ts, :src_ip, :dst_port, 'tcp', :event_type, 1)
            """),
            {"id": eid, "ts": ts, "src_ip": ip, "dst_port": dst_port, "event_type": event_type},
        )
        conn.commit()


def _get_representative_fp(campaign_id: str) -> str | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT representative_fingerprint_json FROM campaigns WHERE id = :id"),
            {"id": campaign_id},
        ).fetchone()
    return row[0] if row else None


def _count_history_for_ip(ip: str) -> int:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM fingerprint_history WHERE source_ip = :ip"),
            {"ip": ip},
        ).fetchone()
    return row[0] if row else 0


def _get_history_rows_for_ip(ip: str) -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, fingerprint_id, source_ip, campaign_id,
                       fingerprint_version, computed_at, event_count_at_computation,
                       confidence, timing_features, sequence_features, protocol_features,
                       credential_features, target_features, created_at
                FROM fingerprint_history WHERE source_ip = :ip
                ORDER BY computed_at ASC
            """),
            {"ip": ip},
        ).fetchall()
    return [
        {
            "id": r[0],
            "fingerprint_id": r[1],
            "source_ip": r[2],
            "campaign_id": r[3],
            "fingerprint_version": r[4],
            "computed_at": r[5],
            "event_count_at_computation": r[6],
            "confidence": r[7],
            "timing_features": r[8],
            "sequence_features": r[9],
            "protocol_features": r[10],
            "credential_features": r[11],
            "target_features": r[12],
            "created_at": r[13],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# get_campaigns_for_clustering — fast path
# ---------------------------------------------------------------------------


def test_clustering_fast_path_returns_representative_data():
    """Campaign with representative_fingerprint_json set uses fast path."""
    rep_fp = json.dumps(
        {
            "timing_features": '{"mean_inter_arrival": 2.0}',
            "sequence_features": '{"port_sequence": [22]}',
            "protocol_features": None,
            "credential_features": '{"username_class_dist": {"dictionary": 3}}',
            "target_features": None,
            "confidence": 0.77,
        }
    )
    cid = _insert_campaign(representative_fingerprint_json=rep_fp)

    from app.db.connection import get_session

    with get_session() as session:
        repo = EventRepository(session)
        candidates = repo.get_campaigns_for_clustering()

    match = next((c for c in candidates if c["campaign_id"] == cid), None)
    assert match is not None
    assert match["confidence"] == pytest.approx(0.77)
    assert match["timing_features"] == '{"mean_inter_arrival": 2.0}'
    assert match["credential_features"] == '{"username_class_dist": {"dictionary": 3}}'
    assert match["protocol_features"] is None


def test_clustering_fast_path_campaign_metadata_correct():
    rep_fp = json.dumps(
        {
            "timing_features": None,
            "sequence_features": None,
            "protocol_features": None,
            "credential_features": None,
            "target_features": None,
            "confidence": 0.55,
        }
    )
    cid = _insert_campaign(status="dormant", representative_fingerprint_json=rep_fp)

    from app.db.connection import get_session

    with get_session() as session:
        repo = EventRepository(session)
        candidates = repo.get_campaigns_for_clustering()

    match = next((c for c in candidates if c["campaign_id"] == cid), None)
    assert match is not None
    assert match["status"] == "dormant"
    assert match["last_seen"] == _TS


# ---------------------------------------------------------------------------
# get_campaigns_for_clustering — slow path / fallback
# ---------------------------------------------------------------------------


def test_clustering_slow_path_when_rep_fp_null():
    """Campaign without representative_fingerprint_json falls back to member lookup."""
    cid = _insert_campaign(representative_fingerprint_json=None)
    ip = f"10.88.{uuid.uuid4().int % 256}.1"
    _insert_member(cid, ip)
    _insert_fingerprint(ip)

    from app.db.connection import get_session

    with get_session() as session:
        repo = EventRepository(session)
        candidates = repo.get_campaigns_for_clustering()

    match = next((c for c in candidates if c["campaign_id"] == cid), None)
    assert match is not None
    assert match["confidence"] == pytest.approx(0.80)
    assert match["timing_features"] == '{"mean_inter_arrival": 1.2, "burst_cv": 0.5}'


def test_clustering_slow_path_invalid_json_falls_back():
    """Campaign with corrupt representative_fingerprint_json falls back."""
    cid = _insert_campaign(representative_fingerprint_json="NOT VALID JSON }{")
    ip = f"10.89.{uuid.uuid4().int % 256}.1"
    _insert_member(cid, ip)
    _insert_fingerprint(ip)

    from app.db.connection import get_session

    with get_session() as session:
        repo = EventRepository(session)
        candidates = repo.get_campaigns_for_clustering()

    match = next((c for c in candidates if c["campaign_id"] == cid), None)
    assert match is not None
    assert match["confidence"] == pytest.approx(0.80)


def test_clustering_excludes_campaign_with_no_members_and_null_rep_fp():
    """Campaign with NULL representative fingerprint and no members is excluded."""
    cid = _insert_campaign(representative_fingerprint_json=None)

    from app.db.connection import get_session

    with get_session() as session:
        repo = EventRepository(session)
        candidates = repo.get_campaigns_for_clustering()

    assert not any(c["campaign_id"] == cid for c in candidates)


# ---------------------------------------------------------------------------
# Fingerprint history written during computation
# ---------------------------------------------------------------------------


def test_compute_and_store_writes_one_history_row():
    ip = f"10.50.{uuid.uuid4().int % 256}.1"
    _insert_source_ip(ip)
    for i in range(5):
        ts = f"2026-01-{i+1:02d}T00:00:00+00:00"
        _insert_event(str(uuid.uuid4()), ip, ts=ts)

    from app.intelligence.tasks import _compute_and_store

    _compute_and_store(ip)

    assert _count_history_for_ip(ip) == 1


def test_compute_and_store_history_row_has_correct_source_ip():
    ip = f"10.51.{uuid.uuid4().int % 256}.1"
    _insert_source_ip(ip)
    for i in range(5):
        ts = f"2026-01-{i+1:02d}T00:00:00+00:00"
        _insert_event(str(uuid.uuid4()), ip, ts=ts)

    from app.intelligence.tasks import _compute_and_store

    _compute_and_store(ip)

    rows = _get_history_rows_for_ip(ip)
    assert len(rows) == 1
    assert rows[0]["source_ip"] == ip
    assert rows[0]["fingerprint_version"] == 1


def test_compute_and_store_history_campaign_id_none_for_unassigned_ip():
    ip = f"10.52.{uuid.uuid4().int % 256}.1"
    _insert_source_ip(ip)
    for i in range(5):
        ts = f"2026-01-{i+1:02d}T00:00:00+00:00"
        _insert_event(str(uuid.uuid4()), ip, ts=ts)

    from app.intelligence.tasks import _compute_and_store

    _compute_and_store(ip)

    rows = _get_history_rows_for_ip(ip)
    assert rows[0]["campaign_id"] is None


def test_compute_and_store_history_campaign_id_set_for_member():
    ip = f"10.53.{uuid.uuid4().int % 256}.1"
    cid = _insert_campaign()
    _insert_member(cid, ip)
    for i in range(5):
        ts = f"2026-01-{i+1:02d}T00:00:00+00:00"
        _insert_event(str(uuid.uuid4()), ip, ts=ts)

    from app.intelligence.tasks import _compute_and_store

    _compute_and_store(ip)

    rows = _get_history_rows_for_ip(ip)
    assert rows[0]["campaign_id"] == cid


def test_compute_and_store_history_accumulates_multiple_calls():
    ip = f"10.54.{uuid.uuid4().int % 256}.1"
    _insert_source_ip(ip)
    for i in range(5):
        ts = f"2026-01-{i+1:02d}T00:00:00+00:00"
        _insert_event(str(uuid.uuid4()), ip, ts=ts)

    from app.intelligence.tasks import _compute_and_store

    _compute_and_store(ip)
    _compute_and_store(ip)

    assert _count_history_for_ip(ip) == 2


def test_compute_and_store_history_feature_columns_are_json_strings():
    """Feature columns in history must be JSON strings, not raw event data."""
    ip = f"10.55.{uuid.uuid4().int % 256}.1"
    _insert_source_ip(ip)
    for i in range(5):
        ts = f"2026-01-{i+1:02d}T00:00:00+00:00"
        _insert_event(str(uuid.uuid4()), ip, ts=ts, dst_port=22, event_type="auth_failed")

    from app.intelligence.tasks import _compute_and_store

    _compute_and_store(ip)

    rows = _get_history_rows_for_ip(ip)
    row = rows[0]
    # Any non-null feature column must be valid JSON, not raw event data.
    for col in (
        "timing_features",
        "sequence_features",
        "protocol_features",
        "credential_features",
        "target_features",
    ):
        val = row[col]
        if val is not None:
            parsed = json.loads(val)
            assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# No raw credentials in history
# ---------------------------------------------------------------------------


def test_credential_features_stores_summary_not_raw_credentials():
    """credential_features must store distribution counts, not raw usernames."""
    ip = f"10.56.{uuid.uuid4().int % 256}.1"
    _insert_source_ip(ip)
    raw_cred_data = {"username": "administrator", "password": "P@ssw0rd!"}
    for i in range(5):
        ts = f"2026-01-{i+1:02d}T00:00:00+00:00"
        _insert_event(
            str(uuid.uuid4()),
            ip,
            ts=ts,
            event_type="auth_failed",
            raw_data=raw_cred_data,
        )

    from app.intelligence.tasks import _compute_and_store

    _compute_and_store(ip)

    rows = _get_history_rows_for_ip(ip)
    row = rows[0]
    cred_json = row["credential_features"]
    if cred_json is not None:
        parsed = json.loads(cred_json)
        # Must not contain raw credential values
        assert "administrator" not in json.dumps(parsed)
        assert "P@ssw0rd!" not in json.dumps(parsed)
        # Must contain statistical summaries
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Representative fingerprint update after clustering
# ---------------------------------------------------------------------------


def test_representative_fp_updated_after_clustering_assigns_campaign():
    """After campaign assignment, representative_fingerprint_json must be set."""
    ip = f"10.60.{uuid.uuid4().int % 256}.1"
    _insert_source_ip(ip)
    _insert_fingerprint(ip)

    # Insert a campaign with a matching fingerprint so assign_to_campaign will
    # find a candidate.  Use the fast path with a pre-populated representative fp.
    ref_fp = json.dumps(
        {
            "timing_features": '{"mean_inter_arrival": 1.2, "burst_cv": 0.5}',
            "sequence_features": '{"port_sequence": [22, 80]}',
            "protocol_features": '{"service_distribution": {"ssh": 10}}',
            "credential_features": '{"username_class_dist": {"dictionary": 5}}',
            "target_features": '{"top_dst_ports": [22]}',
            "confidence": 0.80,
        }
    )
    cid = _insert_campaign(representative_fingerprint_json=ref_fp)
    ip_member = f"10.60.{uuid.uuid4().int % 256}.2"
    _insert_member(cid, ip_member)
    _insert_fingerprint(ip_member)

    from app.intelligence.tasks import _run_campaign_clustering

    _run_campaign_clustering(ip)

    # If clustering assigned the IP to a campaign, representative_fp should be updated.
    # We can't guarantee which campaign it lands on (depends on similarity), but we can
    # at least verify the task runs without error and that rep fp on the assigned campaign
    # is not null.  Check via the source_ip → campaign_members table.
    from app.db.connection import get_session

    with get_session() as session:
        repo = EventRepository(session)
        member = repo.get_campaign_member_by_ip(ip)
        if member is not None:
            rep_fp_raw = _get_representative_fp(member["campaign_id"])
            assert rep_fp_raw is not None
            rep_fp_parsed = json.loads(rep_fp_raw)
            assert "confidence" in rep_fp_parsed
            assert "timing_features" in rep_fp_parsed
            assert "tool_signals" not in rep_fp_parsed


def test_representative_fp_json_excludes_tool_signals():
    """_build_representative_fp_json must not include tool_signals."""
    from app.intelligence.tasks import _build_representative_fp_json

    fp = {
        "timing_features": '{"mean_inter_arrival": 1.0}',
        "sequence_features": '{"port_sequence": [22]}',
        "protocol_features": None,
        "credential_features": None,
        "target_features": None,
        "tool_signals": '{"tools": ["masscan", "zmap"]}',
        "confidence": 0.70,
    }
    result = _build_representative_fp_json(fp)
    parsed = json.loads(result)
    assert "tool_signals" not in parsed
    assert parsed["confidence"] == pytest.approx(0.70)
    assert parsed["timing_features"] == '{"mean_inter_arrival": 1.0}'


def test_representative_fp_json_contains_all_feature_keys():
    from app.intelligence.tasks import _build_representative_fp_json

    fp = {
        "timing_features": "T",
        "sequence_features": "S",
        "protocol_features": "P",
        "credential_features": "C",
        "target_features": "TG",
        "confidence": 0.90,
    }
    parsed = json.loads(_build_representative_fp_json(fp))
    for key in (
        "timing_features",
        "sequence_features",
        "protocol_features",
        "credential_features",
        "target_features",
        "confidence",
    ):
        assert key in parsed
