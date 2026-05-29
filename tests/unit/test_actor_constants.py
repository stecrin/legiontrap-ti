"""Unit tests for Phase 7 Group B1 — actor identity constants.

Tests cover:
  - VALID_RELATIONSHIP_TYPES is a frozenset
  - All four required types are present
  - No extra types are silently present
  - VALID_ACTOR_STATUSES contains expected values
  - Module contains no AI or federation imports
"""

from __future__ import annotations

import importlib


def test_valid_relationship_types_is_frozenset():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    assert isinstance(VALID_RELATIONSHIP_TYPES, frozenset)


def test_valid_relationship_types_contains_all_required():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    required = {"primary_campaign", "infrastructure_reuse", "tactic_match", "temporal_overlap"}
    assert required == VALID_RELATIONSHIP_TYPES


def test_primary_campaign_in_vocabulary():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    assert "primary_campaign" in VALID_RELATIONSHIP_TYPES


def test_infrastructure_reuse_in_vocabulary():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    assert "infrastructure_reuse" in VALID_RELATIONSHIP_TYPES


def test_tactic_match_in_vocabulary():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    assert "tactic_match" in VALID_RELATIONSHIP_TYPES


def test_temporal_overlap_in_vocabulary():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    assert "temporal_overlap" in VALID_RELATIONSHIP_TYPES


def test_open_string_not_in_vocabulary():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    assert "related_campaign" not in VALID_RELATIONSHIP_TYPES
    assert "unknown" not in VALID_RELATIONSHIP_TYPES
    assert "" not in VALID_RELATIONSHIP_TYPES


def test_valid_relationship_types_is_immutable():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    try:
        VALID_RELATIONSHIP_TYPES.add("new_type")  # type: ignore[attr-defined]
        raise AssertionError("frozenset.add should have raised AttributeError")
    except AttributeError:
        pass


def test_valid_actor_statuses_is_frozenset():
    from app.intelligence.actor_constants import VALID_ACTOR_STATUSES

    assert isinstance(VALID_ACTOR_STATUSES, frozenset)


def test_valid_actor_statuses_contains_active_and_archived():
    from app.intelligence.actor_constants import VALID_ACTOR_STATUSES

    assert "active" in VALID_ACTOR_STATUSES
    assert "archived" in VALID_ACTOR_STATUSES


def test_valid_actor_statuses_no_extra_values():
    from app.intelligence.actor_constants import VALID_ACTOR_STATUSES

    assert {"active", "archived"} == VALID_ACTOR_STATUSES


def test_no_ai_imports_in_actor_constants():
    mod = importlib.import_module("app.intelligence.actor_constants")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content


def test_no_federation_imports_in_actor_constants():
    mod = importlib.import_module("app.intelligence.actor_constants")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.routers.federation" not in content
    assert "import federation" not in content
