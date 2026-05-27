"""Async job execution module — Phase 6 PR A1.

Public API for background task functions that execute processing_jobs.
Routers enqueue these functions via FastAPI BackgroundTasks.

Migration path: when BackgroundTasks proves insufficient under load,
replace the executor (Celery workers, asyncio worker pool) without
changing the job_id-based API contract or this module's public surface.
"""

from app.jobs.runner import run_campaign_brief_job, run_campaign_summary_job

__all__ = ["run_campaign_summary_job", "run_campaign_brief_job"]
