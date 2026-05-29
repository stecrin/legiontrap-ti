"""Unit tests for Phase 7 Group A — behavioral drift alert generation.

Tests cover:
  - composite alert fires when composite_score < threshold
  - composite alert does not fire when composite_score >= threshold
  - dimension alert fires when per-dimension score < threshold
  - no alert fires for campaigns with status="insufficient_data"
  - deduplication: second call with same open alert does not insert duplicate
  - acknowledged alert does not block a new alert
  - no campaign mutation from alerting
  - no AI imports, no actor table references
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

from app.intelligence.drift_alerts import check_campaign_drift_alerts

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_stability(
    status: str = "ok",
    composite: float = 0.80,
    timing: float | None = 0.80,
    sequence: float | None = 0.80,
    protocol: float | None = 0.80,
    credential: float | None = 0.80,
    target: float | None = 0.80,
) -> str:
    return json.dumps(
        {
            "status": status,
            "composite_score": composite,
            "timing_stability": timing,
            "sequence_stability": sequence,
            "protocol_stability": protocol,
            "credential_stability": credential,
            "target_stability": target,
            "sample_count": 5,
            "pair_count": 4,
            "dimensions_used": 5,
        }
    )


def _make_repo(
    campaign_id: str,
    stability_json: str | None,
    open_alerts: dict | None = None,
) -> MagicMock:
    """Build a mock repo for drift alert tests.

    open_alerts: dict mapping (campaign_id, dimension) → bool for has_open_alert.
    """
    repo = MagicMock()
    repo.get_campaign.return_value = {
        "id": campaign_id,
        "behavioral_stability_json": stability_json,
    }
    repo.has_open_alert.return_value = False
    if open_alerts:

        def _has_open(cid, dim):
            return open_alerts.get((cid, dim), False)

        repo.has_open_alert.side_effect = _has_open

    repo.insert_alert.side_effect = lambda **kwargs: {
        "id": str(uuid.uuid4()),
        **kwargs,
        "acknowledged_at": None,
        "acknowledged_notes": None,
    }
    return repo


# ---------------------------------------------------------------------------
# Composite alerts
# ---------------------------------------------------------------------------


def test_composite_alert_fires_below_threshold(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(composite=0.50)  # below 0.65
    repo = _make_repo(cid, stability)
    alerts = check_campaign_drift_alerts(cid, repo)
    composite_alerts = [a for a in alerts if a.get("alert_type") == "composite_drift"]
    assert len(composite_alerts) >= 1


def test_composite_alert_does_not_fire_above_threshold(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(composite=0.80)  # above 0.65
    repo = _make_repo(cid, stability)
    alerts = check_campaign_drift_alerts(cid, repo)
    composite_alerts = [a for a in alerts if a.get("alert_type") == "composite_drift"]
    assert len(composite_alerts) == 0


def test_composite_alert_at_threshold_does_not_fire(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(composite=0.65)  # exactly at threshold — should NOT fire
    repo = _make_repo(cid, stability)
    alerts = check_campaign_drift_alerts(cid, repo)
    composite_alerts = [a for a in alerts if a.get("alert_type") == "composite_drift"]
    assert len(composite_alerts) == 0


# ---------------------------------------------------------------------------
# Dimension alerts
# ---------------------------------------------------------------------------


def test_dimension_alert_fires_for_low_timing(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(composite=0.80, timing=0.40)  # timing below 0.60
    repo = _make_repo(cid, stability)
    alerts = check_campaign_drift_alerts(cid, repo)
    dim_alerts = [a for a in alerts if a.get("alert_type") == "dimension_drift"]
    timing_alerts = [a for a in dim_alerts if a.get("dimension") == "timing"]
    assert len(timing_alerts) >= 1


def test_null_dimension_score_does_not_fire(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(composite=0.80, timing=None)  # timing is null
    repo = _make_repo(cid, stability)
    alerts = check_campaign_drift_alerts(cid, repo)
    timing_alerts = [a for a in alerts if a.get("dimension") == "timing"]
    assert len(timing_alerts) == 0


# ---------------------------------------------------------------------------
# Insufficient data
# ---------------------------------------------------------------------------


def test_no_alert_for_insufficient_data_campaign(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(
        status="insufficient_data",
        composite=0.0,
        timing=None,
        sequence=None,
        protocol=None,
        credential=None,
        target=None,
    )
    repo = _make_repo(cid, stability)
    alerts = check_campaign_drift_alerts(cid, repo)
    assert alerts == []
    repo.insert_alert.assert_not_called()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_duplicate_open_alert_not_inserted(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(composite=0.40)  # low enough to trigger composite alert

    # Simulate existing open composite alert
    open_alerts = {(cid, None): True}
    repo = _make_repo(cid, stability, open_alerts=open_alerts)

    alerts = check_campaign_drift_alerts(cid, repo)
    composite_alerts = [a for a in alerts if a.get("alert_type") == "composite_drift"]
    assert len(composite_alerts) == 0
    # insert_alert may be called for other dimensions but not composite
    for c in repo.insert_alert.call_args_list:
        assert c.kwargs.get("alert_type") != "composite_drift"


def test_acknowledged_alert_does_not_block_new_alert(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(composite=0.40)

    # Acknowledged alerts do not block: has_open_alert returns False
    open_alerts = {(cid, None): False}
    repo = _make_repo(cid, stability, open_alerts=open_alerts)

    alerts = check_campaign_drift_alerts(cid, repo)
    composite_alerts = [a for a in alerts if a.get("alert_type") == "composite_drift"]
    assert len(composite_alerts) >= 1


# ---------------------------------------------------------------------------
# No campaign mutation
# ---------------------------------------------------------------------------


def test_alerting_does_not_mutate_campaign(monkeypatch):
    monkeypatch.setattr(
        "app.intelligence.drift_alerts.settings",
        MagicMock(
            DRIFT_ALERT_COMPOSITE_THRESHOLD=0.65,
            DRIFT_ALERT_TIMING_THRESHOLD=0.60,
            DRIFT_ALERT_SEQUENCE_THRESHOLD=0.55,
            DRIFT_ALERT_PROTOCOL_THRESHOLD=0.60,
            DRIFT_ALERT_CREDENTIAL_THRESHOLD=0.55,
            DRIFT_ALERT_TARGET_THRESHOLD=0.60,
        ),
    )
    cid = str(uuid.uuid4())
    stability = _make_stability(composite=0.40)
    repo = _make_repo(cid, stability)
    check_campaign_drift_alerts(cid, repo)

    # Must not call any campaign-mutating methods
    assert not repo.update_campaign_on_association.called
    assert not repo.update_campaign_stability.called
    assert not repo.create_campaign.called


# ---------------------------------------------------------------------------
# No campaign if not found
# ---------------------------------------------------------------------------


def test_no_alerts_for_unknown_campaign():
    cid = str(uuid.uuid4())
    repo = MagicMock()
    repo.get_campaign.return_value = None
    alerts = check_campaign_drift_alerts(cid, repo)
    assert alerts == []
    repo.insert_alert.assert_not_called()


def test_no_alerts_when_stability_json_null():
    cid = str(uuid.uuid4())
    repo = MagicMock()
    repo.get_campaign.return_value = {"id": cid, "behavioral_stability_json": None}
    alerts = check_campaign_drift_alerts(cid, repo)
    assert alerts == []
    repo.insert_alert.assert_not_called()


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_no_ai_imports_in_drift_alerts():
    import importlib

    mod = importlib.import_module("app.intelligence.drift_alerts")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content


def test_no_actor_table_references_in_drift_alerts():
    import importlib

    mod = importlib.import_module("app.intelligence.drift_alerts")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "actor_profiles" not in content
    assert "campaign_lineage" not in content
