from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.routers import events

# Routers
from app.routers.iocs_pf import router as iocs_pf_router
from app.routers.stats import router as stats_router

app = FastAPI()

# Include routers
app.include_router(iocs_pf_router)
app.include_router(stats_router)
app.include_router(events.router)


@app.get("/api/health")
def health():
    return JSONResponse({"status": "ok"})
