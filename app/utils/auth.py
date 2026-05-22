# app/utils/auth.py
# -----------------------------------------------------------------------------
# JWT + password auth helpers for FastAPI dashboard
# -----------------------------------------------------------------------------
import os
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
from fastapi import Header, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()  # ensure .env is loaded when running via uvicorn directly

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Load credentials from env
DASH_USER = os.getenv("DASH_USER", "admin")
DASH_PASS = os.getenv("DASH_PASS", "change-me-please")
JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
JWT_EXPIRE_SECONDS = int(os.getenv("JWT_EXPIRE_SECONDS", "3600"))
JWT_ALGO = "HS256"


def verify_user(username: str, password: str) -> bool:
    """Check login credentials against .env values."""
    return username == DASH_USER and password == DASH_PASS


def create_access_token(data: dict) -> str:
    """Generate a signed JWT token."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(seconds=JWT_EXPIRE_SECONDS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)


def verify_token(token: str) -> dict | None:
    """Decode JWT token and validate expiration."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload
    except JWTError:
        return None


def require_jwt_or_api_key(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    """
    Accept EITHER:
      - API key via `x-api-key` header matching env API_KEY, OR
      - Bearer JWT via `Authorization: Bearer <token>` signed with JWT_SECRET.

    Returns a small dict describing the auth method if valid.
    Raises 401 if missing/invalid.
    """
    # 1) API KEY path
    env_key = os.getenv("API_KEY")
    if x_api_key and env_key and x_api_key == env_key:
        return {"auth": "api_key"}

    # 2) JWT path
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server misconfigured: missing JWT_SECRET",
            )
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            # Optional: manual exp check (python-jose normally enforces this if present)
            exp = payload.get("exp")
            if exp is not None:
                now_ts = datetime.now(UTC).timestamp()
                if now_ts > float(exp):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token expired",
                    )
            return {"auth": "jwt", "sub": payload.get("sub")}
        except JWTError as err:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            ) from err

    # Otherwise: no valid credentials found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid credentials",
    )
