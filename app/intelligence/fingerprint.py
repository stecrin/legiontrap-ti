"""Behavioral fingerprint builder.

Bridges the pure feature extraction in sequence.py and the database layer.
build_fingerprint() accepts the event list returned by the repository and
produces a dict whose keys map directly to behavioral_fingerprints columns.

Confidence model (§12.6):
  - event_count < MIN_EVENTS_FOR_CLUSTERING  →  confidence < 0.20 (sparse)
  - event_count >= MIN_EVENTS_FOR_CLUSTERING  →  confidence derived from
    event volume and feature completeness, in the range [0.20, 0.95]

Sparse fingerprints are computed and stored but must not enter campaign
clustering.  PR 4 gates clustering on confidence >= 0.20.
"""

from __future__ import annotations

import json
from typing import Any

from app.intelligence.constants import MIN_EVENTS_FOR_CLUSTERING
from app.intelligence.sequence import extract_all_features

# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------


def compute_confidence(
    event_count: int,
    populated_categories: int,
    total_categories: int,
) -> float:
    """Return a confidence score in [0.0, 0.95].

    Sparse fingerprints (below MIN_EVENTS_FOR_CLUSTERING) receive confidence
    strictly below 0.20, which the PR 4 clustering gate treats as
    "insufficient for clustering" (§12.6).

    For non-sparse fingerprints, confidence grows with both event volume
    (saturates at ~500 events) and feature completeness.
    """
    if event_count <= 0:
        return 0.0

    if event_count < MIN_EVENTS_FOR_CLUSTERING:
        # Linear ramp: 1 event → 0.019, 9 events → 0.171
        return round(event_count * (0.19 / MIN_EVENTS_FOR_CLUSTERING), 4)

    completeness = populated_categories / max(total_categories, 1)
    count_factor = min(1.0, event_count / 500.0)
    confidence = 0.3 * completeness + 0.5 * count_factor + 0.2
    return round(min(0.95, confidence), 4)


# ---------------------------------------------------------------------------
# Fingerprint builder
# ---------------------------------------------------------------------------


def build_fingerprint(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute a complete fingerprint from an event list.

    The returned dict maps directly to behavioral_fingerprints column names.
    Feature category values are JSON strings (or None when a category cannot
    be computed from the available data).

    Keys returned:
        event_count, confidence,
        timing_features, sequence_features, protocol_features,
        credential_features, target_features, tool_signals
    """
    event_count = len(events)
    raw_features = extract_all_features(events)

    populated = sum(1 for v in raw_features.values() if v is not None)
    total = len(raw_features)  # always 6
    confidence = compute_confidence(event_count, populated, total)

    def _to_json(val: Any) -> str | None:
        return json.dumps(val, separators=(",", ":")) if val is not None else None

    return {
        "event_count": event_count,
        "confidence": confidence,
        "timing_features": _to_json(raw_features["timing_features"]),
        "sequence_features": _to_json(raw_features["sequence_features"]),
        "protocol_features": _to_json(raw_features["protocol_features"]),
        "credential_features": _to_json(raw_features["credential_features"]),
        "target_features": _to_json(raw_features["target_features"]),
        "tool_signals": _to_json(raw_features["tool_signals"]),
    }
