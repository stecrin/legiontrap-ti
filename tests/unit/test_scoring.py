"""Unit tests for app/utils/scoring.py — pure functions, no database required."""

import pytest

from app.utils.scoring import compute_reputation_score, compute_tags


class TestComputeTags:
    def test_auth_failed_adds_brute_force(self):
        assert "brute-force" in compute_tags([], "auth_failed")

    def test_auth_success_adds_auth_success(self):
        assert "auth-success" in compute_tags([], "auth_success")

    def test_port_scan_adds_scanner(self):
        assert "scanner" in compute_tags([], "port_scan")

    def test_http_probe_adds_scanner(self):
        assert "scanner" in compute_tags([], "http_probe")

    def test_command_exec_adds_command_exec(self):
        assert "command-exec" in compute_tags([], "command_exec")

    def test_malware_upload_adds_malware(self):
        assert "malware" in compute_tags([], "malware_upload")

    def test_unknown_event_type_returns_unchanged(self):
        current = ["brute-force"]
        result = compute_tags(current, "unknown")
        assert result == current

    def test_unmapped_normalized_type_returns_unchanged(self):
        current = ["scanner"]
        result = compute_tags(current, "some_custom_sensor_type")
        assert result == current

    def test_existing_tag_not_duplicated(self):
        result = compute_tags(["brute-force"], "auth_failed")
        assert result.count("brute-force") == 1

    def test_tags_are_additive_existing_preserved(self):
        result = compute_tags(["brute-force"], "port_scan")
        assert "brute-force" in result
        assert "scanner" in result

    def test_result_is_sorted(self):
        result = compute_tags([], "port_scan")
        assert result == sorted(result)

    def test_multi_type_same_tag_no_duplicate(self):
        tags_after_scan = compute_tags([], "port_scan")
        tags_after_probe = compute_tags(tags_after_scan, "http_probe")
        assert tags_after_probe.count("scanner") == 1


class TestComputeReputationScore:
    def test_zero_for_no_events_no_tags(self):
        assert compute_reputation_score([], 0) == pytest.approx(0.0)

    def test_zero_for_single_event_no_tags(self):
        assert compute_reputation_score([], 1) == pytest.approx(0.0)

    def test_low_event_count_adds_point_one(self):
        assert compute_reputation_score([], 10) == pytest.approx(0.1)

    def test_high_event_count_adds_point_three(self):
        assert compute_reputation_score([], 100) == pytest.approx(0.3)

    def test_brute_force_tag_weight(self):
        assert compute_reputation_score(["brute-force"], 0) == pytest.approx(0.3)

    def test_scanner_tag_weight(self):
        assert compute_reputation_score(["scanner"], 0) == pytest.approx(0.2)

    def test_command_exec_tag_weight(self):
        assert compute_reputation_score(["command-exec"], 0) == pytest.approx(0.3)

    def test_malware_tag_weight(self):
        assert compute_reputation_score(["malware"], 0) == pytest.approx(0.3)

    def test_auth_success_tag_no_contribution(self):
        assert compute_reputation_score(["auth-success"], 0) == pytest.approx(0.0)

    def test_brute_force_and_high_count(self):
        score = compute_reputation_score(["brute-force"], 100)
        assert score == pytest.approx(0.6)

    def test_score_meets_exit_criterion(self):
        # Blueprint exit criterion: 100+ auth_failed events → score >= 0.4
        tags = compute_tags([], "auth_failed")
        score = compute_reputation_score(tags, 100)
        assert score >= 0.4

    def test_score_capped_at_1(self):
        all_tags = ["brute-force", "scanner", "command-exec", "malware"]
        score = compute_reputation_score(all_tags, 100)
        assert score == pytest.approx(1.0)

    def test_score_below_1_without_all_tags(self):
        score = compute_reputation_score(["brute-force"], 5)
        assert 0.0 < score < 1.0
