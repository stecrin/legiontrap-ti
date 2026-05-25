"""Integration tests: ASN enrichment through the ingest pipeline.

Tests verify that:
- Ingest succeeds when GeoLite2-ASN.mmdb is absent (enrichment is best-effort)
- events.asn and events.asn_org are NULL when the mmdb is absent
- source_ips.asn and source_ips.asn_org are NULL when the mmdb is absent
- When the mmdb is present, asn fields are populated on first insert
  (guarded with skipif — requires operator to provision GeoLite2-ASN.mmdb)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.utils.asn as asn_module
from app.db.connection import get_engine
from app.main import app
from app.utils.asn import reset_asn_reader_for_testing

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}

ASN_DB_AVAILABLE = asn_module.ASN_DB_PATH.exists()

_PUBLIC_IP = "8.8.8.8"


def _event(event_id: str, ip: str = _PUBLIC_IP) -> dict:
    return {
        "id": event_id,
        "ts": "2025-10-28T18:31:08+00:00",
        "source": "cowrie",
        "type": "cowrie.login.failed",
        "data": {"ip": ip},
    }


def _ingest(event_id: str, ip: str = _PUBLIC_IP):
    return client.post(
        "/api/ingest",
        json={"events": [_event(event_id, ip)]},
        headers=HEADERS,
    )


@pytest.fixture(autouse=True)
def reset_asn_reader():
    reset_asn_reader_for_testing()
    yield
    reset_asn_reader_for_testing()


def test_ingest_succeeds_without_asn_mmdb(monkeypatch, tmp_path):
    """Ingest must succeed even if GeoLite2-ASN.mmdb is absent."""
    monkeypatch.setattr(asn_module, "ASN_DB_PATH", tmp_path / "absent.mmdb")
    resp = _ingest("asn-no-mmdb-01")
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1


def test_ingest_asn_null_in_events_without_mmdb(monkeypatch, tmp_path):
    """events.asn and events.asn_org are NULL when ASN mmdb is absent."""
    monkeypatch.setattr(asn_module, "ASN_DB_PATH", tmp_path / "absent.mmdb")
    _ingest("asn-null-events-01")
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT asn, asn_org FROM events WHERE id = 'asn-null-events-01'")
        ).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] is None


def test_ingest_asn_null_in_source_ips_without_mmdb(monkeypatch, tmp_path):
    """source_ips.asn and source_ips.asn_org are NULL when ASN mmdb is absent."""
    monkeypatch.setattr(asn_module, "ASN_DB_PATH", tmp_path / "absent.mmdb")
    _ingest("asn-null-source-01", ip=_PUBLIC_IP)
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT asn, asn_org FROM source_ips WHERE ip = :ip"),
            {"ip": _PUBLIC_IP},
        ).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] is None


@pytest.mark.skipif(not ASN_DB_AVAILABLE, reason="GeoLite2-ASN.mmdb not provisioned")
def test_ingest_populates_asn_in_events_when_mmdb_available():
    """events.asn and events.asn_org are populated when GeoLite2-ASN.mmdb is present."""
    _ingest("asn-live-events-01")
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT asn, asn_org FROM events WHERE id = 'asn-live-events-01'")
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert isinstance(row[0], int)
    assert row[1] is not None


@pytest.mark.skipif(not ASN_DB_AVAILABLE, reason="GeoLite2-ASN.mmdb not provisioned")
def test_ingest_populates_asn_in_source_ips_when_mmdb_available():
    """source_ips.asn and source_ips.asn_org are populated on first insert."""
    _ingest("asn-live-source-01", ip=_PUBLIC_IP)
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT asn, asn_org FROM source_ips WHERE ip = :ip"),
            {"ip": _PUBLIC_IP},
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert isinstance(row[0], int)
    assert row[1] is not None
