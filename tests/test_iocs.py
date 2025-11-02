import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def sample_events():
    return [
        {"src_ip": "1.2.3.4", "dst_port": 22, "service": "ssh"},
        {"src_ip": "5.6.7.8", "dst_port": 80, "service": "http"},
        {"src_ip": "1.2.3.4", "dst_port": 8080, "service": "http-proxy"},
    ]


@pytest.fixture
def temp_events_file(tmp_path, sample_events, monkeypatch):
    f = tmp_path / "events.jsonl"
    with f.open("w") as fh:
        for evt in sample_events:
            fh.write(json.dumps(evt) + "\n")
    monkeypatch.setenv("EVENTS_FILE", str(f))
    return f


def test_iocs_unique_ips_enabled(temp_events_file):
    r = client.get("/api/iocs/pf.conf", headers={"x-api-key": "dev-123"})
    assert r.status_code == 200
    body = r.text.strip().splitlines()
    assert "1.2.3.4" in r.text and "5.6.7.8" in r.text
    assert any("block in quick from" in line for line in body)
