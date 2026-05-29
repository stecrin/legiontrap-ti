"""Actor-level stability aggregation — Phase 7 Group B4.

Pure computation: no database access, no I/O, no side effects.
Aggregates behavioral_stability_json from linked campaign rows into a
single actor-level stability view computed at request time.

No new data is stored as a result of calling aggregate_actor_stability().
No AI involvement.  No automatic actor or campaign mutation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

_DIMENSIONS = ("timing", "sequence", "protocol", "credential", "target")

_STATUS_OK = "ok"
_STATUS_NO_CAMPAIGNS = "no_linked_campaigns"
_STATUS_NO_DATA = "no_stability_data"
_STATUS_PARTIAL = "partial_data"


def _parse_stability(json_str: str | None) -> dict[str, Any] | None:
    """Parse a behavioral_stability_json string.  Returns None on failure."""
    if json_str is None:
        return None
    try:
        v = json.loads(json_str)
        return v if isinstance(v, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _dim_agg(values: list[float]) -> dict[str, float]:
    """Compute min/max/mean over a non-empty list of floats."""
    return {
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "mean": round(sum(values) / len(values), 6),
    }


def aggregate_actor_stability(
    campaign_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate stability data from linked campaign rows.

    campaign_rows — list from list_actor_campaign_stability():
      each row must contain: campaign_id, relationship_type, campaign_name,
      behavioral_stability_json (str | None), plus optional metadata fields.

    Returns a fully-derived stability dict.  No data is written anywhere.

    Campaigns with NULL behavioral_stability_json or stability status
    'insufficient_data' count toward campaigns_missing_stability and appear
    in contributors with composite_score=None.

    dimension_stability only includes dimensions where at least one campaign
    contributes a non-None score.  actor_composite_stability is None when no
    campaign has a usable composite_score.
    """
    now = datetime.now(UTC).isoformat()

    linked_campaign_count = len(campaign_rows)
    missing = 0
    contributors: list[dict[str, Any]] = []

    composite_scores: list[float] = []
    dim_scores: dict[str, list[float]] = {d: [] for d in _DIMENSIONS}

    for row in campaign_rows:
        stab = _parse_stability(row.get("behavioral_stability_json"))
        has_data = stab is not None and stab.get("status") != "insufficient_data"

        if not has_data:
            missing += 1
            contributors.append(
                {
                    "campaign_id": row["campaign_id"],
                    "campaign_name": row.get("campaign_name"),
                    "relationship_type": row.get("relationship_type"),
                    "composite_score": None,
                    "status": stab.get("status") if stab else "no_data",
                    "sample_count": stab.get("sample_count", 0) if stab else 0,
                    "last_computed": stab.get("calculated_at") if stab else None,
                }
            )
            continue

        composite = stab.get("composite_score")
        if composite is not None:
            composite_scores.append(composite)

        for dim in _DIMENSIONS:
            val = stab.get(f"{dim}_stability")
            if val is not None:
                dim_scores[dim].append(val)

        contributors.append(
            {
                "campaign_id": row["campaign_id"],
                "campaign_name": row.get("campaign_name"),
                "relationship_type": row.get("relationship_type"),
                "composite_score": composite,
                "status": stab.get("status", _STATUS_OK),
                "sample_count": stab.get("sample_count", 0),
                "last_computed": stab.get("calculated_at"),
            }
        )

    campaigns_with_stability = linked_campaign_count - missing

    if linked_campaign_count == 0:
        view_status = _STATUS_NO_CAMPAIGNS
    elif campaigns_with_stability == 0:
        view_status = _STATUS_NO_DATA
    elif missing > 0:
        view_status = _STATUS_PARTIAL
    else:
        view_status = _STATUS_OK

    actor_composite = _dim_agg(composite_scores) if composite_scores else None

    dimension_stability: dict[str, Any] = {}
    for dim in _DIMENSIONS:
        if dim_scores[dim]:
            dimension_stability[dim] = _dim_agg(dim_scores[dim])

    return {
        "linked_campaign_count": linked_campaign_count,
        "campaigns_with_stability": campaigns_with_stability,
        "campaigns_missing_stability": missing,
        "actor_composite_stability": actor_composite,
        "dimension_stability": dimension_stability if dimension_stability else None,
        "contributors": contributors,
        "status": view_status,
        "computed_at": now,
    }
