"""
Intelligence scoring and tagging for LegionTrap TI.

Pure functions — no database imports, no FastAPI, no external I/O.
Rules sourced from docs/PHASE_2_BLUEPRINT.md sections 10 and 11.
Thresholds and tag mappings are defined as module-level constants so they
can be adjusted without touching the calling code.
"""

from __future__ import annotations

# Maps normalized event_type → intelligence tag.
# Multiple event_types may map to the same tag (e.g., port_scan and http_probe → scanner).
_EVENT_TYPE_TO_TAG: dict[str, str] = {
    "auth_failed": "brute-force",
    "auth_success": "auth-success",
    "port_scan": "scanner",
    "http_probe": "scanner",
    "command_exec": "command-exec",
    "malware_upload": "malware",
}

# Scoring weight for each tag (additive, capped at 1.0).
_TAG_WEIGHTS: dict[str, float] = {
    "brute-force": 0.3,
    "scanner": 0.2,
    "command-exec": 0.3,
    "malware": 0.3,
}

# Event-count thresholds contribute to the base score independent of tags.
_COUNT_HIGH = 100
_COUNT_HIGH_WEIGHT = 0.3
_COUNT_MED = 10
_COUNT_MED_WEIGHT = 0.1


def compute_tags(current_tags: list[str], new_event_type: str) -> list[str]:
    """Return updated tag list after observing new_event_type.

    Tags are additive — existing tags are never removed.
    Returns a sorted list for deterministic output.
    If new_event_type maps to no tag, or the tag is already present,
    the original list is returned unchanged.
    """
    new_tag = _EVENT_TYPE_TO_TAG.get(new_event_type)
    if new_tag is None or new_tag in current_tags:
        return current_tags
    return sorted({*current_tags, new_tag})


def compute_reputation_score(tags: list[str], event_count: int) -> float:
    """Return heuristic reputation score in [0.0, 1.0].

    Scoring rules (from PHASE_2_BLUEPRINT.md section 10):
      - event_count >= 100  → +0.3
      - event_count >= 10   → +0.1
      - brute-force tag     → +0.3
      - scanner tag         → +0.2
      - command-exec tag    → +0.3
      - malware tag         → +0.3

    Score is capped at 1.0. Rules are additive; all matching conditions
    contribute. auth-success has no score contribution.
    """
    score = 0.0
    if event_count >= _COUNT_HIGH:
        score += _COUNT_HIGH_WEIGHT
    elif event_count >= _COUNT_MED:
        score += _COUNT_MED_WEIGHT
    for tag, weight in _TAG_WEIGHTS.items():
        if tag in tags:
            score += weight
    return min(score, 1.0)
