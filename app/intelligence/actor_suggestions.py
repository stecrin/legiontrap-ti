"""Actor suggestion engine — Phase 7 Group B3.

Pure computation: no database access, no I/O, no side effects.
Advisory only — results are never written to any table automatically.

build_actor_suggestions() compares campaign representative fingerprints
pairwise and returns candidate pairs above a configurable similarity
threshold.  The operator decides whether to act on any suggestion.
"""

from __future__ import annotations

import itertools
from typing import Any

from app.intelligence.similarity import SimilarityResult, compute_weighted_similarity


def _derive_relationship_type(result: SimilarityResult) -> str:
    """Return an advisory relationship_type hint based on per-dimension scores.

    Heuristic thresholds (blueprint §7.4):
      sequence >= 0.85 AND timing >= 0.80  → primary_campaign
      timing   >= 0.80 AND sequence < 0.70 → infrastructure_reuse
      protocol >= 0.80                     → tactic_match
      otherwise                            → temporal_overlap

    This is a suggestion only — never used to write to any table.
    """
    ts = result.timing_similarity or 0.0
    ss = result.sequence_similarity or 0.0
    ps = result.protocol_similarity or 0.0

    if ss >= 0.85 and ts >= 0.80:
        return "primary_campaign"
    if ts >= 0.80 and ss < 0.70:
        return "infrastructure_reuse"
    if ps >= 0.80:
        return "tactic_match"
    return "temporal_overlap"


def _campaign_summary(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c["id"],
        "name": c["name"],
        "status": c["status"],
        "last_seen": c["last_seen"],
        "member_ip_count": c["member_ip_count"],
    }


def build_actor_suggestions(
    campaigns: list[dict[str, Any]],
    coattributed_pairs: set[frozenset[str]],
    *,
    min_score: float,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """Compute pairwise campaign similarity and return top suggestions.

    campaigns — list of campaign dicts from list_campaigns_for_suggestions().
      Each dict must contain: id, name, status, last_seen, member_ip_count
      and the feature columns accepted by compute_weighted_similarity().

    coattributed_pairs — frozenset pairs from get_coattributed_campaign_pairs().
      Any pair already linked under a common actor is skipped.

    Returns (suggestions, total_pairs_evaluated).
      suggestions: sorted by similarity_score DESC, capped at limit.
      total_pairs_evaluated: count of pairs scored (coattributed pairs excluded).

    This function never reads from or writes to any table.
    """
    suggestions: list[dict[str, Any]] = []
    total_evaluated = 0

    for c_a, c_b in itertools.combinations(campaigns, 2):
        pair = frozenset({c_a["id"], c_b["id"]})
        if pair in coattributed_pairs:
            continue

        total_evaluated += 1
        result = compute_weighted_similarity(c_a, c_b)

        if result.weighted_total < min_score:
            continue

        suggestions.append(
            {
                "campaign_a": _campaign_summary(c_a),
                "campaign_b": _campaign_summary(c_b),
                "similarity_score": result.weighted_total,
                "score_breakdown": result.as_dict(),
                "suggested_relationship_type": _derive_relationship_type(result),
            }
        )

    suggestions.sort(key=lambda x: x["similarity_score"], reverse=True)
    return suggestions[:limit], total_evaluated
