# tests/test_privacy_and_auth.py
from importlib import reload

from fastapi.testclient import TestClient

from app.main import app


def test_bad_key_gets_401(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-xyz")

    from app.core import config

    reload(config)

    client = TestClient(app)

    # Missing or wrong API key should fail
    r = client.get("/api/iocs/ufw.txt")  # no header
    assert r.status_code == 401


def test_privacy_mode_hashes_outputs(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-xyz")
    monkeypatch.setenv("PRIVACY_MODE", "true")
    monkeypatch.setenv("FEED_SALT", "testsalt")

    from app.core import config

    reload(config)

    # reload router after env change
    from app.routers import iocs_pf

    reload(iocs_pf)

    client = TestClient(app)

    # Now the app sees the new env vars
    r = client.get("/api/iocs/ufw.txt", headers={"x-api-key": "secret-xyz"})
    assert r.status_code == 200
    text = r.text
    # raw IPs should not be visible
    assert "1.2.3.4" not in text
    # but hashed markers should appear
    assert "ip-" in text
