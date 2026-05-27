"""AI output retrieval endpoints — Phase 6 PR A2.

GET /api/ai/outputs/{output_id}
  Retrieve a single AI output record by ID.

GET /api/campaigns/{campaign_id}/ai-outputs
  List all AI output records for a campaign, newest first.

Rules:
  - Auth required on all endpoints.
  - Read-only: no generation, no mutation, no delete.
  - AI outputs are never fed back into the prompt builder (§3, §10 Rule 1).
  - Prompt content is never stored or exposed; only prompt_hash.
  - source_records_json is visible for provenance and audit.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(tags=["ai_outputs"])


def _enrich_output(output: dict) -> dict:
    """Parse JSON string fields into structured objects for API consumers."""
    enriched = dict(output)
    for field in ("source_records_json", "safety_flags_json"):
        raw = enriched.get(field)
        key = field.replace("_json", "")
        if raw:
            try:
                enriched[key] = json.loads(raw)
            except (ValueError, TypeError):
                enriched[key] = None
        else:
            enriched[key] = None
        enriched.pop(field, None)
    return enriched


@router.get("/api/ai/outputs/{output_id}")
def get_ai_output(
    output_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return a single AI output record by ID.

    Returns 404 when the output_id is unknown. Never triggers AI generation.
    """
    with get_session() as session:
        repo = EventRepository(session)
        output = repo.get_ai_output(output_id)

    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AI output {output_id!r} not found",
        )
    return _enrich_output(output)


@router.get("/api/campaigns/{campaign_id}/ai-outputs")
def list_campaign_ai_outputs(
    campaign_id: str,
    output_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(require_jwt_or_api_key),
):
    """List AI output records for a campaign, newest first.

    Optionally filtered by output_type (e.g. 'campaign_summary').
    Returns an empty list when the campaign has no outputs — never 404.
    """
    with get_session() as session:
        repo = EventRepository(session)
        outputs = repo.list_ai_outputs_for_resource(
            "campaign",
            campaign_id,
            output_type=output_type,
            limit=limit,
        )

    return {
        "campaign_id": campaign_id,
        "outputs": [_enrich_output(o) for o in outputs],
        "count": len(outputs),
    }
