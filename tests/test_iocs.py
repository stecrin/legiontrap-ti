import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

client = TestClient(app)
H = {"x-api-key": "dev-123"}

_BASE_EVENTS = [
    {
        "ts": "2025-10-28T18:31:08+00:00",
        "source": "cowrie",
        "type": "auth_failed",
        "data": {"ip": "1.2.3.4"},
    },
    {
        "ts": "2025-10-28T18:31:09+00:00",
        "source": "cowrie",
        "type": "auth_failed",
        "data": {"ip": "5.6.7.8"},
    },
    {
        "ts": "2025-10-28T18:31:10+00:00",
        "source": "cowrie",
        "type": "auth_failed",
        "data": {"ip": "1.2.3.4"},
    },
]


@pytest.fixture(autouse=True)
def clean_db():
    yield
    from app.db.connection import get_engine

    with get_engine().connect() as conn:
        conn.execute(text("DELETE FROM behavioral_fingerprints"))
        conn.execute(text("DELETE FROM campaign_tags"))
        conn.execute(text("DELETE FROM campaign_observations"))
        conn.execute(text("DELETE FROM campaign_members"))
        conn.execute(text("DELETE FROM campaigns"))
        conn.execute(text("DELETE FROM events"))
        conn.execute(text("DELETE FROM raw_events"))
        conn.execute(text("DELETE FROM source_ips"))
        conn.commit()


@pytest.fixture
def seeded():
    events = [{**ev, "id": str(uuid.uuid4())} for ev in _BASE_EVENTS]
    r = client.post("/api/ingest", json={"events": events}, headers=H)
    assert r.status_code == 200


def test_iocs_unique_ips_in_pf_conf(seeded):
    r = client.get("/api/iocs/pf.conf", headers=H)
    assert r.status_code == 200
    assert "1.2.3.4" in r.text
    assert "5.6.7.8" in r.text
    assert any("block in quick from" in line for line in r.text.splitlines())


def test_iocs_unique_ips_in_ufw_txt(seeded):
    r = client.get("/api/iocs/ufw.txt", headers=H)
    assert r.status_code == 200
    assert "1.2.3.4" in r.text
    assert "5.6.7.8" in r.text
    assert any("deny from" in line for line in r.text.splitlines())
