"""Unit tests for uncertain-association filtering logic.

Pure Python — no database, no I/O.  Tests cover the decision-identification
logic used by list_uncertain_observations() and the valid/invalid analyst
decision values enforced by the review endpoint.

Coverage:
  Notes JSON parsing:
    - notes with decision="uncertain_association" is identified as uncertain
    - notes with decision="automatic_association" is not uncertain
    - notes with decision="existing_member" is not uncertain
    - NULL notes is not uncertain
    - malformed JSON notes is not uncertain
    - notes missing "decision" key is not uncertain
    - notes with decision as integer is not uncertain

  Review decision validation:
    - "analyst_confirmed" is a valid review decision
    - "analyst_denied" is a valid review decision
    - arbitrary strings are not valid review decisions
    - empty string is not a valid review decision
    - "uncertain_association" itself is not a valid review decision
"""

from __future__ import annotations

import json

import pytest

_VALID_REVIEW_DECISIONS = {"analyst_confirmed", "analyst_denied"}

_UNCERTAIN_ASSOCIATION = "uncertain_association"


def _is_uncertain_observation(notes: str | None) -> bool:
    """Mirror of the Python-side check in list_uncertain_observations()."""
    if notes is None:
        return False
    try:
        parsed = json.loads(notes)
        if not isinstance(parsed, dict):
            return False
    except (json.JSONDecodeError, TypeError):
        return False
    return parsed.get("decision") == _UNCERTAIN_ASSOCIATION


def _make_notes(decision: str, weighted_total: float = 0.65) -> str:
    return json.dumps(
        {
            "timing_similarity": 0.7,
            "sequence_similarity": 0.6,
            "weighted_total": weighted_total,
            "dimensions_used": 2,
            "threshold_applied": 0.6,
            "decision": decision,
        }
    )


# ---------------------------------------------------------------------------
# Notes JSON parsing
# ---------------------------------------------------------------------------


def test_uncertain_association_decision_is_identified():
    assert _is_uncertain_observation(_make_notes("uncertain_association")) is True


def test_automatic_association_decision_is_not_uncertain():
    assert _is_uncertain_observation(_make_notes("automatic_association")) is False


def test_existing_member_decision_is_not_uncertain():
    assert _is_uncertain_observation(_make_notes("existing_member")) is False


def test_null_notes_is_not_uncertain():
    assert _is_uncertain_observation(None) is False


def test_malformed_json_notes_is_not_uncertain():
    assert _is_uncertain_observation("{not valid json") is False


def test_empty_string_notes_is_not_uncertain():
    assert _is_uncertain_observation("") is False


def test_notes_without_decision_key_is_not_uncertain():
    notes = json.dumps({"weighted_total": 0.65, "threshold_applied": 0.6})
    assert _is_uncertain_observation(notes) is False


def test_notes_with_integer_decision_is_not_uncertain():
    notes = json.dumps({"decision": 1})
    assert _is_uncertain_observation(notes) is False


def test_notes_that_are_json_array_is_not_uncertain():
    assert _is_uncertain_observation(json.dumps([1, 2, 3])) is False


def test_notes_with_null_decision_is_not_uncertain():
    notes = json.dumps({"decision": None})
    assert _is_uncertain_observation(notes) is False


# ---------------------------------------------------------------------------
# Review decision validation
# ---------------------------------------------------------------------------


def test_analyst_confirmed_is_valid():
    assert "analyst_confirmed" in _VALID_REVIEW_DECISIONS


def test_analyst_denied_is_valid():
    assert "analyst_denied" in _VALID_REVIEW_DECISIONS


def test_exactly_two_valid_decisions():
    assert len(_VALID_REVIEW_DECISIONS) == 2


@pytest.mark.parametrize(
    "bad_decision",
    [
        "uncertain_association",
        "automatic_association",
        "accepted",
        "rejected",
        "confirmed",
        "denied",
        "",
        "ANALYST_CONFIRMED",
    ],
)
def test_invalid_decision_not_in_valid_set(bad_decision: str):
    assert bad_decision not in _VALID_REVIEW_DECISIONS


# ---------------------------------------------------------------------------
# Review JSON structure
# ---------------------------------------------------------------------------


def test_review_json_is_serializable():
    review = {
        "decision": "analyst_confirmed",
        "notes": "Confirmed by SOC team",
        "reviewed_at": "2026-05-27T12:00:00+00:00",
    }
    serialized = json.dumps(review)
    parsed = json.loads(serialized)
    assert parsed["decision"] == "analyst_confirmed"
    assert parsed["notes"] == "Confirmed by SOC team"


def test_review_json_with_null_notes_is_serializable():
    review = {
        "decision": "analyst_denied",
        "notes": None,
        "reviewed_at": "2026-05-27T12:00:00+00:00",
    }
    serialized = json.dumps(review)
    parsed = json.loads(serialized)
    assert parsed["notes"] is None
