# app/routers/auth_router.py
# -----------------------------------------------------------------------------
# /api/login endpoint — validates dashboard credentials and returns JWT token
# -----------------------------------------------------------------------------
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.limiter import limiter
from app.utils.auth import create_access_token, verify_user

router = APIRouter()


@router.post("/api/login")
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Authenticate dashboard user and return a JWT token."""
    if not verify_user(username, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token({"sub": username})
    return JSONResponse({"access_token": token, "token_type": "bearer"})
