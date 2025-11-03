# tests/test_privacy_and_auth.py

from fastapi.testclient import TestClient

from ui.backend.app.main import app

client = TestClient(app)


def test_bad_key_gets_401(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-xyz")
    # Recreate settings with new env
    from importlib import reload

    from ui.backend.app.core import config

    reload(config)

    r = client.get("/api/iocs/ufw.txt")  # no header
    assert r.status_code == 401

    r = client.get("/api/iocs/ufw.txt", headers={"x-api-key": "wrong"})
    assert r.status_code == 401


def test_privacy_mode_hashes_outputs(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-xyz")
    monkeypatch.setenv("PRIVACY_MODE", "true")
    monkeypatch.setenv("FEED_SALT", "testsalt")
    from importlib import reload

    from ui.backend.app.core import config

    reload(config)

    # you may want to inject a small fixture dataset here;
    # assuming your app has seed-on-boot or a tiny in-memory store.
    r = client.get("/api/iocs/ufw.txt", headers={"x-api-key": "secret-xyz"})
    assert r.status_code == 200
    text = r.text
    # raw IPs should not be visible (example)
    assert "1.2.3.4" not in text
    # but hashed markers should appear
    assert "ip-" in text
