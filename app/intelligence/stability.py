"""Behavioral stability scoring from fingerprint history (§11.3).

Pure computation in compute_campaign_stability() — no database access, no I/O,
no side effects.  The refresh helpers call the DB via get_session()/EventRepository.

Stability model:
  Per-dimension stability = average pairwise similarity between consecutive
  fingerprint snapshots for a campaign, ordered oldest-first.  Uses the same
  domain-specific similarity functions as the clustering algorithm so the
  stability metric is semantically consistent with the clustering metric:
    timing      → timing_similarity()
    sequence    → sequence_similarity()
    protocol    → protocol_similarity()
    credential  → credential_similarity()
    target      → target_similarity()

  High average pairwise similarity = low drift = high stability.

  Composite stability = weighted average of per-dimension stabilities using
  the same dimension weights as compute_weighted_similarity():
    timing 20%, sequence 35%, protocol 25%, credential 10%, target 10%.

  Null-dimension rule (inherited from §8.1): dimensions where all history
  records have NULL feature values contribute zero to both numerator and
  denominator.  Sparse fingerprints are not penalised.

Insufficient-data handling:
  Fewer than MIN_HISTORY_RECORDS (2) records → status = "insufficient_data",
  all scores = None, composite_score = 0.0.  Cannot compute a change from
  a single snapshot.

No AI imports.  No learned embeddings.  No vector DB.  Deterministic only.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.intelligence.constants import (
    WEIGHT_CREDENTIAL,
    WEIGHT_PROTOCOL,
    WEIGHT_SEQUENCE,
    WEIGHT_TARGET,
    WEIGHT_TIMING,
)
from app.intelligence.similarity import (
    credential_similarity,
    protocol_similarity,
    sequence_similarity,
    target_similarity,
    timing_similarity,
)

logger = logging.getLogger(__name__)

_STATUS_OK = "ok"
_STATUS_INSUFFICIENT = "insufficient_data"

MIN_HISTORY_RECORDS: int = 2


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class StabilityResult:
    """Full stability assessment for one campaign from its fingerprint history."""

    status: str
    composite_score: float
    timing_stability: float | None
    sequence_stability: float | None
    protocol_stability: float | None
    credential_stability: float | None
    target_stability: float | None
    sample_count: int
    pair_count: int
    dimensions_used: int
    calculated_at: str
    explanation: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "composite_score": self.composite_score,
            "timing_stability": self.timing_stability,
            "sequence_stability": self.sequence_stability,
            "protocol_stability": self.protocol_stability,
            "credential_stability": self.credential_stability,
            "target_stability": self.target_stability,
            "sample_count": self.sample_count,
            "pair_count": self.pair_count,
            "dimensions_used": self.dimensions_used,
            "calculated_at": self.calculated_at,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def _parse_feature(s: str | None) -> dict | None:
    """Parse a JSON feature string to a dict, or None on failure / null input."""
    if s is None:
        return None
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def compute_campaign_stability(history: list[dict[str, Any]]) -> StabilityResult:
    """Compute behavioral stability from a list of fingerprint_history rows.

    history must be sorted oldest-first (as list_fingerprint_history_for_campaign()
    returns).  Returns StabilityResult with status="insufficient_data" when fewer
    than MIN_HISTORY_RECORDS rows are present.

    Scores are in [0.0, 1.0]:
      1.0 = perfectly stable (all consecutive pairs identical)
      0.0 = maximally unstable
    """
    now = datetime.now(UTC).isoformat()

    if len(history) < MIN_HISTORY_RECORDS:
        return StabilityResult(
            status=_STATUS_INSUFFICIENT,
            composite_score=0.0,
            timing_stability=None,
            sequence_stability=None,
            protocol_stability=None,
            credential_stability=None,
            target_stability=None,
            sample_count=len(history),
            pair_count=0,
            dimensions_used=0,
            calculated_at=now,
            explanation={
                "reason": f"Fewer than {MIN_HISTORY_RECORDS} history records available",
                "records_available": len(history),
            },
        )

    timing_sims: list[float] = []
    sequence_sims: list[float] = []
    protocol_sims: list[float] = []
    credential_sims: list[float] = []
    target_sims: list[float] = []

    pairs = list(zip(history[:-1], history[1:], strict=False))

    for a, b in pairs:
        ts = timing_similarity(
            _parse_feature(a.get("timing_features")),
            _parse_feature(b.get("timing_features")),
        )
        ss = sequence_similarity(
            _parse_feature(a.get("sequence_features")),
            _parse_feature(b.get("sequence_features")),
        )
        ps = protocol_similarity(
            _parse_feature(a.get("protocol_features")),
            _parse_feature(b.get("protocol_features")),
        )
        cs = credential_similarity(
            _parse_feature(a.get("credential_features")),
            _parse_feature(b.get("credential_features")),
        )
        tgs = target_similarity(
            _parse_feature(a.get("target_features")),
            _parse_feature(b.get("target_features")),
        )

        if ts is not None:
            timing_sims.append(ts)
        if ss is not None:
            sequence_sims.append(ss)
        if ps is not None:
            protocol_sims.append(ps)
        if cs is not None:
            credential_sims.append(cs)
        if tgs is not None:
            target_sims.append(tgs)

    timing_stability = round(_mean(timing_sims), 6) if timing_sims else None
    sequence_stability = round(_mean(sequence_sims), 6) if sequence_sims else None
    protocol_stability = round(_mean(protocol_sims), 6) if protocol_sims else None
    credential_stability = round(_mean(credential_sims), 6) if credential_sims else None
    target_stability = round(_mean(target_sims), 6) if target_sims else None

    _DIM_MAP: list[tuple[str, float | None, float, int]] = [
        ("timing", timing_stability, WEIGHT_TIMING, len(timing_sims)),
        ("sequence", sequence_stability, WEIGHT_SEQUENCE, len(sequence_sims)),
        ("protocol", protocol_stability, WEIGHT_PROTOCOL, len(protocol_sims)),
        ("credential", credential_stability, WEIGHT_CREDENTIAL, len(credential_sims)),
        ("target", target_stability, WEIGHT_TARGET, len(target_sims)),
    ]

    numerator = 0.0
    denominator = 0.0
    dimensions_used = 0
    explanation_dims: dict[str, Any] = {}

    for dim_name, dim_score, weight, pair_ct in _DIM_MAP:
        if dim_score is not None:
            numerator += weight * dim_score
            denominator += weight
            dimensions_used += 1
            explanation_dims[dim_name] = {
                "score": dim_score,
                "pair_count": pair_ct,
                "weight": weight,
            }
        else:
            explanation_dims[dim_name] = {
                "score": None,
                "pair_count": pair_ct,
                "weight": weight,
                "reason": "null_dimension",
            }

    composite = round(numerator / denominator, 6) if denominator > 0.0 else 0.0

    return StabilityResult(
        status=_STATUS_OK,
        composite_score=composite,
        timing_stability=timing_stability,
        sequence_stability=sequence_stability,
        protocol_stability=protocol_stability,
        credential_stability=credential_stability,
        target_stability=target_stability,
        sample_count=len(history),
        pair_count=len(pairs),
        dimensions_used=dimensions_used,
        calculated_at=now,
        explanation={"dimensions": explanation_dims},
    )


# ---------------------------------------------------------------------------
# Refresh helpers
# ---------------------------------------------------------------------------


def refresh_campaign_stability(campaign_id: str) -> None:
    """Recompute and persist behavioral stability for campaign_id.

    Idempotent: always overwrites the stored result with the latest computation
    from the current fingerprint_history.  Silently does nothing when the
    campaign_id is unknown (no rows updated).
    """
    from app.db.connection import get_session
    from app.db.repository import EventRepository

    with get_session() as session:
        repo = EventRepository(session)
        history = repo.list_fingerprint_history_for_campaign(campaign_id)
        result = compute_campaign_stability(history)
        repo.update_campaign_stability(campaign_id, json.dumps(result.as_dict()))


def refresh_all_campaign_stability() -> None:
    """Recompute and persist behavioral stability for every campaign.

    Idempotent.  Per-campaign failures are logged but do not interrupt the
    refresh of remaining campaigns.
    """
    from app.db.connection import get_session
    from app.db.repository import EventRepository

    with get_session() as session:
        repo = EventRepository(session)
        campaign_ids = repo.list_all_campaign_ids()

    for cid in campaign_ids:
        try:
            refresh_campaign_stability(cid)
        except Exception:
            logger.exception("Stability refresh failed for campaign_id=%s", cid)
