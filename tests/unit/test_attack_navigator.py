"""
Unit tests for app/exports/attack_navigator.py.

Tests operate on plain Python dicts — no database, no HTTP layer.
"""

from __future__ import annotations

from app.exports.attack_navigator import build_navigator_layer


def _technique(
    technique="T1110.001",
    tactic="Credential Access",
    label="SSH Authentication Failure",
    event_count=10,
) -> dict:
    return {
        "attack_technique": technique,
        "attack_tactic": tactic,
        "label": label,
        "event_count": event_count,
    }


# --- Required structure ---------------------------------------------------


def test_required_top_level_keys():
    layer = build_navigator_layer([])
    for key in ("name", "versions", "domain", "techniques", "gradient", "metadata"):
        assert key in layer, f"missing key: {key}"


def test_versions_fields():
    layer = build_navigator_layer([])
    assert "attack" in layer["versions"]
    assert "navigator" in layer["versions"]
    assert "layer" in layer["versions"]


def test_domain_is_enterprise():
    layer = build_navigator_layer([])
    assert layer["domain"] == "enterprise-attack"


# --- Technique entries ----------------------------------------------------


def test_empty_techniques():
    layer = build_navigator_layer([])
    assert layer["techniques"] == []


def test_single_technique_id():
    layer = build_navigator_layer([_technique("T1046", "Discovery", "Port Scan", 5)])
    assert len(layer["techniques"]) == 1
    assert layer["techniques"][0]["techniqueID"] == "T1046"


def test_technique_score_equals_event_count():
    layer = build_navigator_layer([_technique(event_count=42)])
    assert layer["techniques"][0]["score"] == 42


def test_technique_tactic_slug():
    layer = build_navigator_layer([_technique(tactic="Credential Access")])
    assert layer["techniques"][0]["tactic"] == "credential-access"


def test_tactic_slug_discovery():
    layer = build_navigator_layer([_technique(technique="T1046", tactic="Discovery")])
    assert layer["techniques"][0]["tactic"] == "discovery"


def test_technique_comment_contains_count():
    layer = build_navigator_layer([_technique(event_count=7)])
    assert "7" in layer["techniques"][0]["comment"]


def test_technique_metadata_event_count():
    layer = build_navigator_layer([_technique(event_count=3)])
    meta = {m["name"]: m["value"] for m in layer["techniques"][0]["metadata"]}
    assert meta["event_count"] == "3"


def test_null_technique_excluded():
    rows = [
        _technique("T1046"),
        {"attack_technique": None, "attack_tactic": "Discovery", "label": "x", "event_count": 5},
    ]
    layer = build_navigator_layer(rows)
    assert len(layer["techniques"]) == 1
    assert layer["techniques"][0]["techniqueID"] == "T1046"


def test_missing_tactic_omitted_from_entry():
    rows = [{"attack_technique": "T1046", "attack_tactic": None, "label": "x", "event_count": 1}]
    layer = build_navigator_layer(rows)
    assert "tactic" not in layer["techniques"][0]


def test_multiple_techniques_all_present():
    rows = [
        _technique("T1110.001", event_count=20),
        _technique("T1046", tactic="Discovery", event_count=5),
        _technique("T1059", tactic="Execution", event_count=1),
    ]
    layer = build_navigator_layer(rows)
    ids = {t["techniqueID"] for t in layer["techniques"]}
    assert ids == {"T1110.001", "T1046", "T1059"}


# --- Gradient and scoring -------------------------------------------------


def test_gradient_max_value_equals_max_event_count():
    rows = [
        _technique(event_count=10),
        _technique("T1046", event_count=50),
        _technique("T1059", event_count=5),
    ]
    layer = build_navigator_layer(rows)
    assert layer["gradient"]["maxValue"] == 50


def test_gradient_min_value_is_zero():
    layer = build_navigator_layer([_technique(event_count=1)])
    assert layer["gradient"]["minValue"] == 0


def test_gradient_has_colors():
    layer = build_navigator_layer([])
    assert len(layer["gradient"]["colors"]) >= 2


# --- Layer naming ---------------------------------------------------------


def test_custom_layer_name():
    layer = build_navigator_layer([], layer_name="My Custom Layer")
    assert layer["name"] == "My Custom Layer"


def test_default_layer_name():
    layer = build_navigator_layer([])
    assert layer["name"] == "LegionTrap TI"


def test_custom_description():
    layer = build_navigator_layer([], description="My description")
    assert layer["description"] == "My description"


def test_default_description_is_generated():
    layer = build_navigator_layer([])
    assert "LegionTrap TI" in layer["description"]


# --- Metadata -------------------------------------------------------------


def test_metadata_contains_generated_at():
    layer = build_navigator_layer([])
    meta = {m["name"]: m["value"] for m in layer["metadata"]}
    assert "generated_at" in meta


def test_metadata_contains_source():
    layer = build_navigator_layer([])
    meta = {m["name"]: m["value"] for m in layer["metadata"]}
    assert meta["source"] == "LegionTrap TI"
