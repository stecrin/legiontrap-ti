"""Integration tests for POST /api/ingest audit logging."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
H = {"x-api-key": "dev-123"}


def _event(ip: str = "1.2.3.4") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "ts": "2025-10-28T18:31:08+00:00",
        "source": "cowrie",
        "type": "auth_failed",
        "data": {"ip": ip},
    }


def _ingest(events: list[dict]) -> dict:
    r = client.post("/api/ingest", json={"events": events}, headers=H)
    assert r.status_code == 200
    return r.json()


def _audit_rows() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT event_type, source_ip, detail FROM audit_log")).fetchall()
    return [{"event_type": r[0], "source_ip": r[1], "detail": r[2]} for r in rows]


def test_audit_row_written_after_ingest():
    _ingest([_event()])
    rows = _audit_rows()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "ingest"


def test_audit_detail_contains_batch_id():
    receipt = _ingest([_event()])
    rows = _audit_rows()
    detail = json.loads(rows[0]["detail"])
    assert detail["batch_id"] == receipt["batch_id"]


def test_audit_detail_accepted_rejected_duplicate():
    receipt = _ingest([_event()])
    rows = _audit_rows()
    detail = json.loads(rows[0]["detail"])
    assert detail["accepted"] == receipt["accepted"]
    assert detail["rejected"] == receipt["rejected"]
    assert detail["duplicate"] == receipt["duplicate"]


def test_audit_one_row_per_ingest_batch():
    _ingest([_event(), _event()])
    _ingest([_event()])
    rows = _audit_rows()
    assert len(rows) == 2
