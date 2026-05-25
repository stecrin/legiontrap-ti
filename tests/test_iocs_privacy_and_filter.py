import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

client = TestClient(app)
H = {"x-api-key": "dev-123"}


@pytest.fixture(autouse=True)
def clean_db():
    yield
    from app.db.connection import get_engine

    with get_engine().connect() as conn:
        conn.execute(text("DELETE FROM events"))
        conn.execute(text("DELETE FROM raw_events"))
        conn.execute(text("DELETE FROM source_ips"))
        conn.commit()


def _seed(event_dicts: list[dict]) -> None:
    events = [{**ev, "id": str(uuid.uuid4())} for ev in event_dicts]
    r = client.post("/api/ingest", json={"events": events}, headers=H)
    assert r.status_code == 200


def test_pf_conf_filters_non_public():
    _seed(
        [
            {
                "ts": "2025-10-28T18:31:08+00:00",
                "source": "cowrie",
                "type": "auth_failed",
                "data": {"ip": "8.8.8.8"},
            },
            {
                "ts": "2025-10-28T18:31:09+00:00",
                "source": "cowrie",
                "type": "auth_failed",
                "data": {"ip": "1.1.1.1"},
            },
            {
                "ts": "2025-10-28T18:31:10+00:00",
                "source": "cowrie",
                "type": "auth_failed",
                "data": {"ip": "10.0.0.1"},
            },
            {
                "ts": "2025-10-28T18:31:11+00:00",
                "source": "cowrie",
                "type": "auth_failed",
                "data": {"ip": "192.168.1.7"},
            },
        ]
    )

    r = client.get("/api/iocs/pf.conf", headers=H)
    assert r.status_code == 200
    body = r.text
    assert "8.8.8.8" in body
    assert "1.1.1.1" in body
    assert "10.0.0.1" not in body
    assert "192.168.1.7" not in body


def test_privacy_mode_masks_ips(monkeypatch):
    monkeypatch.setenv("PRIVACY_MODE", "on")
    _seed(
        [
            {
                "ts": "2025-10-28T18:31:08+00:00",
                "source": "cowrie",
                "type": "auth_failed",
                "data": {"ip": "8.8.8.8"},
            },
            {
                "ts": "2025-10-28T18:31:09+00:00",
                "source": "cowrie",
                "type": "auth_failed",
                "data": {"ip": "1.1.1.1"},
            },
        ]
    )

    r = client.get("/api/iocs/pf.conf", headers=H)
    assert r.status_code == 200
    body = r.text
    assert "ip-" in body
    assert "8.8.8.8" not in body
    assert "1.1.1.1" not in body
