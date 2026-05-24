from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# The plaintext password whose bcrypt hash is set in pytest.ini as DASH_PASS.
_PLAIN = "test-password-plain"


def test_login_success_returns_token():
    r = client.post("/api/login", data={"username": "admin", "password": _PLAIN})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


def test_login_wrong_password_returns_401():
    r = client.post("/api/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_wrong_username_returns_401():
    r = client.post("/api/login", data={"username": "notadmin", "password": _PLAIN})
    assert r.status_code == 401


def test_login_missing_fields_returns_422():
    r = client.post("/api/login")
    assert r.status_code == 422


def test_login_token_is_valid_jwt():
    """Token returned from login must be a decodable HS256 JWT with correct subject.

    NOTE: require_jwt_or_api_key exists in auth.py but is not yet wired to any
    route — each router has its own inline API-key-only check. End-to-end JWT
    acceptance by a protected endpoint is a T-05 wiring task.
    """
    import os

    from jose import jwt as jose_jwt

    login = client.post("/api/login", data={"username": "admin", "password": _PLAIN})
    assert login.status_code == 200
    token = login.json()["access_token"]

    secret = os.environ["JWT_SECRET"]
    payload = jose_jwt.decode(token, secret, algorithms=["HS256"])
    assert payload["sub"] == "admin"
    assert "exp" in payload
