"""Integration tests: GeoIP enrichment through the ingest pipeline."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.utils.geoip as geoip_module
from app.db.connection import get_engine
from app.main import app
from app.utils.geoip import reset_reader_for_testing

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}

MMDB_AVAILABLE = geoip_module.CITY_DB_PATH.exists()

_PUBLIC_IP = "8.8.8.8"
_PRIVATE_IP = "192.168.1.1"


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
def reset_geoip_reader():
    reset_reader_for_testing()
    yield
    reset_reader_for_testing()


def test_ingest_succeeds_without_mmdb(monkeypatch, tmp_path):
    monkeypatch.setattr(geoip_module, "CITY_DB_PATH", tmp_path / "absent.mmdb")
    resp = _ingest("enrich-no-mmdb")
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1


def test_ingest_geo_null_without_mmdb(monkeypatch, tmp_path):
    monkeypatch.setattr(geoip_module, "CITY_DB_PATH", tmp_path / "absent.mmdb")
    _ingest("enrich-geo-null")
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT country_code FROM events WHERE id = 'enrich-geo-null'")
        ).fetchone()
    assert row is not None
    assert row[0] is None


def test_ingest_private_ip_accepted(monkeypatch, tmp_path):
    monkeypatch.setattr(geoip_module, "CITY_DB_PATH", tmp_path / "absent.mmdb")
    resp = _ingest("enrich-private", ip=_PRIVATE_IP)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1


@pytest.mark.skipif(not MMDB_AVAILABLE, reason="GeoLite2-City.mmdb not provisioned")
def test_ingest_populates_geo_when_mmdb_available():
    _ingest("enrich-geo-live")
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT country_code FROM events WHERE id = 'enrich-geo-live'")
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert len(row[0]) == 2
