# app/main.py
# -----------------------------------------------------------------------------
# Main FastAPI entrypoint for LegionTrap Threat Intelligence Platform
# -----------------------------------------------------------------------------
# Responsibilities:
#   - Initialize FastAPI app
#   - Register routers for all feature modules (IOCs, stats, events, auth)
#   - Provide a simple /api/health check
#   - Configure global middleware (e.g., CORS)
# -----------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.limiter import limiter

# --- Import routers ----------------------------------------------------------
# Routers handle modular API sections of the app.
# Keeping them separated ensures clarity and scalability.
from app.routers import (
    auth_router,  # Login & JWT auth
    events,  # Event listing endpoint
)
from app.routers.admin import router as admin_router  # POST /api/admin/*
from app.routers.analyze import router as analyze_router  # POST /api/campaigns/*/summary
from app.routers.campaigns import router as campaigns_router  # GET /api/campaigns/*
from app.routers.exports import router as exports_router  # GET /api/exports/*
from app.routers.ingest import router as ingest_router  # POST /api/ingest
from app.routers.intelligence import router as intelligence_router  # GET /api/intelligence/*
from app.routers.iocs_pf import router as iocs_pf_router  # pf.conf generator
from app.routers.jobs import router as jobs_router  # GET /api/jobs/*
from app.routers.stats import router as stats_router  # Stats & counters

# --- Create FastAPI instance -------------------------------------------------
app = FastAPI(
    title="LegionTrap TI",
    version="0.2.2",
    description="Honeypot threat intelligence dashboard backend",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Global Middleware -------------------------------------------------------
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register Routers --------------------------------------------------------
# Each router encapsulates a specific domain of functionality.
# Prefixes help keep the API structure clean and RESTful.
app.include_router(admin_router)  # /api/admin/*
app.include_router(auth_router.router)  # /api/login
app.include_router(ingest_router)  # /api/ingest
app.include_router(intelligence_router)  # /api/intelligence/*
app.include_router(campaigns_router)  # /api/campaigns/*
app.include_router(analyze_router)  # /api/campaigns/*/summary|brief
app.include_router(jobs_router)  # /api/jobs/*
app.include_router(exports_router)  # /api/exports/*
app.include_router(iocs_pf_router, prefix="/api/iocs")  # pf.conf generator
app.include_router(stats_router)  # /api/stats
app.include_router(events.router)  # /api/events


# --- Health Check ------------------------------------------------------------
# Provides a lightweight endpoint for CI/CD and uptime monitoring.
@app.get("/api/health")
def health():
    """
    Basic health check endpoint to verify server status.
    Returns 200 OK if the app is running.
    """
    return JSONResponse({"status": "ok", "message": "LegionTrap TI backend running"})
