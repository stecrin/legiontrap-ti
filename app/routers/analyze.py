"""AI analysis endpoints — Phase 5 §10 PR 5.

POST /api/campaigns/{campaign_id}/summary
  Operator-triggered AI summary for a single campaign.
  Auth: require_jwt_or_api_key.
  No AI output persistence. No database writes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai import (
    AIBackendError,
    AIBackendUnavailableError,
    AIDisabledError,
    get_ai_backend,
)
from app.ai.prompt_builder import build_campaign_summary_prompt
from app.ai.safety import validate_ai_output
from app.core.config import settings
from app.db.connection import get_session
from app.db.repository import EventRepository
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(prefix="/api/campaigns", tags=["analyze"])

_SUMMARY_WARNING = (
    "This analysis is AI-assisted. All factual claims are derived from "
    "deterministic campaign data. Attribution language is inferential, not asserted."
)

_MAX_SUMMARY_LEN = 1000
_MAX_OBSERVATIONS = 10


@router.post("/{campaign_id}/summary")
def campaign_summary(
    campaign_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Generate an AI-assisted natural-language summary for a single campaign.

    Fetches campaign record, the representative behavioral fingerprint (most-
    recently-active member), and the last 10 observations. Builds a structured
    prompt and calls the configured AI backend. Validates output via the safety
    layer. Never persists AI output and never writes to the database.

    Failure modes (§9):
      503 — AI disabled or backend unreachable / errored
      422 — PRIVACY_MODE=on with AI_BACKEND=claude
      404 — campaign not found
      401 — missing or invalid credentials
      200 + rejected=true — output failed safety validation
    """
    # §5 Privacy conflict: external cloud backend forbidden in PRIVACY_MODE
    if settings.PRIVACY_MODE and settings.AI_BACKEND == "claude":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "AI_BACKEND=claude is not permitted when PRIVACY_MODE is enabled. "
                "Use AI_BACKEND=ollama for local inference in privacy mode, "
                "or set AI_BACKEND=none to disable AI features."
            ),
        )

    # Fetch campaign and related context — read-only session
    with get_session() as session:
        repo = EventRepository(session)

        campaign = repo.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {campaign_id!r} not found",
            )

        # Fingerprint: most-recently-active member IP (get_campaign_members orders DESC)
        members = repo.get_campaign_members(campaign_id)
        fingerprint = None
        if members:
            fingerprint = repo.get_behavioral_fingerprint(members[0]["source_ip"])

        # Observations: last _MAX_OBSERVATIONS only
        all_obs = repo.get_campaign_observations(campaign_id)
        observations = all_obs[-_MAX_OBSERVATIONS:]

    # Build structured prompt — source IPs are excluded by prompt_builder
    prompt_data = build_campaign_summary_prompt(campaign, fingerprint, observations)

    # Call the configured AI backend
    try:
        backend = get_ai_backend()
        raw_output = backend.generate(prompt_data["user_prompt"])
    except AIDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AIBackendUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AIBackendError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    # Validate AI output through the safety layer (§9)
    validated_text, rejection_reason = validate_ai_output(raw_output, max_len=_MAX_SUMMARY_LEN)
    generated_at = datetime.now(UTC).isoformat()

    is_rejected = rejection_reason in ("ip_detected", "empty_response")
    is_truncated = rejection_reason == "truncated"

    return {
        "ai_assisted": True,
        "ai_backend": settings.AI_BACKEND,
        "generated_at": generated_at,
        "warning": _SUMMARY_WARNING,
        "campaign_id": campaign_id,
        "summary": None if is_rejected else validated_text,
        "source_records": prompt_data["source_records"],
        "safety_flags": prompt_data["safety_flags"],
        "rejected": is_rejected,
        "rejection_reason": rejection_reason,
        "truncated": is_truncated,
    }
