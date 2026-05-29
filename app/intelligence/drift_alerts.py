"""Behavioral drift alert generation — Phase 7 Group A.

Reads campaigns.behavioral_stability_json and fires behavioral_alerts rows
when stability scores cross configured thresholds.

Alert generation rules (per §6.2 of Phase 7 blueprint):
  - composite_drift: fires when composite_score < DRIFT_ALERT_COMPOSITE_THRESHOLD
  - dimension_drift:  fires when any per-dimension score < the dimension threshold
  - No alert fires for campaigns with status="insufficient_data" in their
    stability JSON.

Deduplication:
  Before inserting, the job checks for an existing unacknowledged alert for
  the same (campaign_id, dimension) pair.  If one exists, no new alert is
  inserted.  Acknowledged alerts do not block new alerts — acknowledgement
  closes the deduplication gate.

Alerts are informational only.  No code path mutates campaigns, clustering
decisions, fingerprints, or weight profiles in response to an alert.

No AI imports.  No external calls.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from app.db.repository import EventRepository

logger = logging.getLogger(__name__)

_DIM_THRESHOLD_MAP = {
    "timing": "DRIFT_ALERT_TIMING_THRESHOLD",
    "sequence": "DRIFT_ALERT_SEQUENCE_THRESHOLD",
    "protocol": "DRIFT_ALERT_PROTOCOL_THRESHOLD",
    "credential": "DRIFT_ALERT_CREDENTIAL_THRESHOLD",
    "target": "DRIFT_ALERT_TARGET_THRESHOLD",
}

_DIM_STABILITY_KEY = {
    "timing": "timing_stability",
    "sequence": "sequence_stability",
    "protocol": "protocol_stability",
    "credential": "credential_stability",
    "target": "target_stability",
}


def _get_dim_threshold(dim: str) -> float:
    return float(getattr(settings, _DIM_THRESHOLD_MAP[dim]))


def check_campaign_drift_alerts(
    campaign_id: str,
    repo: EventRepository,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Check one campaign for drift and insert alerts as needed.

    Returns the list of newly created alert dicts (may be empty).
    Idempotent when called repeatedly with unchanged stability data.
    """
    if now is None:
        now = datetime.now(UTC)
    now_str = now.isoformat()

    campaign = repo.get_campaign(campaign_id)
    if campaign is None:
        return []

    stability_json = campaign.get("behavioral_stability_json")
    if not stability_json:
        return []

    try:
        stability = json.loads(stability_json)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(stability, dict):
        return []

    # Campaigns with insufficient data do not generate drift alerts.
    if stability.get("status") == "insufficient_data":
        return []

    snapshot = stability
    created_alerts: list[dict[str, Any]] = []

    # --- Composite drift check ---
    composite_score = stability.get("composite_score")
    composite_threshold = settings.DRIFT_ALERT_COMPOSITE_THRESHOLD
    if (
        isinstance(composite_score, int | float)
        and composite_score < composite_threshold
        and not repo.has_open_alert(campaign_id, None)
    ):
        created_alerts.append(
            repo.insert_alert(
                campaign_id=campaign_id,
                alert_type="composite_drift",
                dimension=None,
                threshold_configured=composite_threshold,
                observed_value=float(composite_score),
                stability_snapshot=snapshot,
                triggered_at=now_str,
            )
        )

    # --- Per-dimension drift checks ---
    for dim, stability_key in _DIM_STABILITY_KEY.items():
        dim_score = stability.get(stability_key)
        if dim_score is None or not isinstance(dim_score, int | float):
            continue
        dim_threshold = _get_dim_threshold(dim)
        if dim_score < dim_threshold and not repo.has_open_alert(campaign_id, dim):
            created_alerts.append(
                repo.insert_alert(
                    campaign_id=campaign_id,
                    alert_type="dimension_drift",
                    dimension=dim,
                    threshold_configured=dim_threshold,
                    observed_value=float(dim_score),
                    stability_snapshot=snapshot,
                    triggered_at=now_str,
                )
            )

    return created_alerts


def check_all_campaign_drift_alerts(
    repo: EventRepository,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Check all campaigns for drift and insert alerts as needed.

    Idempotent.  Per-campaign failures are logged but do not interrupt
    processing of remaining campaigns.
    """
    if now is None:
        now = datetime.now(UTC)

    campaign_ids = repo.list_all_campaign_ids()
    total_created = 0
    failed = 0

    for cid in campaign_ids:
        try:
            alerts = check_campaign_drift_alerts(cid, repo, now)
            total_created += len(alerts)
        except Exception:
            logger.exception("Drift alert check failed for campaign_id=%s", cid)
            failed += 1

    return {
        "campaigns_evaluated": len(campaign_ids),
        "alerts_created": total_created,
        "failed": failed,
        "checked_at": now.isoformat(),
    }
