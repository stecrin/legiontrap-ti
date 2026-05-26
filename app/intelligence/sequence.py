"""Pure event sequence extraction and feature computation.

All functions are pure: no database access, no I/O, no side effects.
Input is a list of event dicts as returned by FingerprintRepository.get_events_for_fingerprint().

Each event dict has the shape:
    {
        "ts":         str,         # ISO-8601 timestamp
        "dst_port":   int | None,
        "event_type": str,
        "service":    str | None,
        "source":     str,         # sensor identifier, e.g. "cowrie"
        "raw_data":   dict,        # parsed from raw_events.raw_json["data"]
    }

Privacy invariants enforced by this module (tested in test_sequence_extraction.py):
  - Raw credential strings (usernames, passwords) are NEVER stored in output.
  - Source IP addresses are NEVER stored in any feature category.
  - Raw payload bytes are NEVER stored.

Infrastructure metadata (ASN, country) is intentionally absent from all
feature categories.  It is available on source_ips for informational lookup
but must not drive similarity scoring (§12.4).

Feature encoding follows the Appendix: Fingerprint Feature Encoding Reference.
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.intelligence.constants import (
    MAX_CREDENTIAL_SEQUENCE,
    SESSION_GAP_SECONDS,
    TOP_PORT_FREQ_N,
    TOP_PORT_SEQUENCE_N,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_epoch(ts: str) -> float:
    """Parse an ISO-8601 timestamp string to a UTC Unix epoch float."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC).timestamp()


def _parse_dt(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp string to a timezone-aware datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)


def _percentile(sorted_data: list[float], p: float) -> float:
    """Linear-interpolation percentile over a pre-sorted list."""
    n = len(sorted_data)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_data[0]
    idx = (n - 1) * p
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return sorted_data[lo] + (idx - lo) * (sorted_data[hi] - sorted_data[lo])


def _normalize_counts(counts: list[float]) -> list[float]:
    """Normalize a list of counts to sum to 1.0.  Returns zeros on empty input."""
    total = sum(counts)
    if total == 0.0:
        return counts
    return [c / total for c in counts]


# ---------------------------------------------------------------------------
# Session extraction
# ---------------------------------------------------------------------------


def extract_sessions(
    events: list[dict[str, Any]],
    gap_seconds: int = SESSION_GAP_SECONDS,
) -> list[list[dict[str, Any]]]:
    """Split events into sessions separated by inactivity gaps.

    Events are sorted chronologically before splitting.  A new session begins
    when the gap between consecutive events exceeds gap_seconds.

    Returns a list of sessions; each session is a list of event dicts.
    """
    if not events:
        return []

    sorted_events = sorted(events, key=lambda e: e["ts"])
    sessions: list[list[dict[str, Any]]] = [[sorted_events[0]]]

    for event in sorted_events[1:]:
        last_epoch = _parse_epoch(sessions[-1][-1]["ts"])
        curr_epoch = _parse_epoch(event["ts"])
        if curr_epoch - last_epoch > gap_seconds:
            sessions.append([event])
        else:
            sessions[-1].append(event)

    return sessions


# ---------------------------------------------------------------------------
# Timing features
# ---------------------------------------------------------------------------


def compute_timing_features(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute timing-based behavioral features.

    Requires at least 2 events to produce interval statistics.  Returns None
    if the event list is too small to compute meaningful timing features.

    Encoding (Appendix):
        interval      — {"mean", "stddev", "p25", "p75", "p95"} in milliseconds
        tod_histogram — 24-element list of normalized hourly frequencies
        dow_histogram — 7-element list of normalized daily frequencies (Mon=0)
        burst_cv      — coefficient of variation of within-session intervals;
                        low value → metronomic automated tool (§6.2)
    """
    if len(events) < 2:
        return None

    sessions = extract_sessions(events)

    # Collect within-session inter-probe intervals (milliseconds)
    interval_ms: list[float] = []
    session_durations_s: list[float] = []

    for session in sessions:
        if len(session) < 2:
            continue
        epochs = [_parse_epoch(e["ts"]) for e in session]
        for i in range(len(epochs) - 1):
            gap = (epochs[i + 1] - epochs[i]) * 1000.0  # ms
            if gap >= 0:
                interval_ms.append(gap)
        duration = epochs[-1] - epochs[0]
        if duration >= 0:
            session_durations_s.append(duration)

    if not interval_ms:
        return None

    sorted_intervals = sorted(interval_ms)
    mean_iv = statistics.mean(interval_ms)
    stddev_iv = statistics.pstdev(interval_ms)  # population stddev over all observed intervals

    # Time-of-day histogram (24 UTC hour buckets)
    tod: list[float] = [0.0] * 24
    for e in events:
        tod[_parse_dt(e["ts"]).hour] += 1.0
    tod = _normalize_counts(tod)

    # Day-of-week histogram (0=Monday … 6=Sunday)
    dow: list[float] = [0.0] * 7
    for e in events:
        dow[_parse_dt(e["ts"]).weekday()] += 1.0
    dow = _normalize_counts(dow)

    # Burst coefficient of variation — low CV → metronomic tool
    burst_cv = stddev_iv / mean_iv if mean_iv > 0.0 else 0.0

    # Session duration stats (may be empty if no multi-event session)
    session_dur: dict[str, float] | None = None
    if session_durations_s:
        session_dur = {
            "mean": round(statistics.mean(session_durations_s), 3),
            "stddev": round(statistics.pstdev(session_durations_s), 3),
        }

    return {
        "interval": {
            "mean": round(mean_iv, 3),
            "stddev": round(stddev_iv, 3),
            "p25": round(_percentile(sorted_intervals, 0.25), 3),
            "p75": round(_percentile(sorted_intervals, 0.75), 3),
            "p95": round(_percentile(sorted_intervals, 0.95), 3),
        },
        "session_duration": session_dur,
        "tod_histogram": [round(v, 6) for v in tod],
        "dow_histogram": [round(v, 6) for v in dow],
        "burst_cv": round(burst_cv, 6),
    }


# ---------------------------------------------------------------------------
# Sequence features
# ---------------------------------------------------------------------------


def compute_sequence_features(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute behavioral sequence features.

    Extracts the ordered port probe sequence, event type sequence, and
    credential attempt sequence (patterns only — no raw credential values).

    Encoding (Appendix):
        port_sequence       — ordered array of dst_port integers, top-N (≤50)
        event_type_sequence — ordered array of event_type strings
        credential_sequence — array of {"username_pattern": str, "password_class": str}
    """
    sorted_events = sorted(events, key=lambda e: e["ts"])

    # Port probe sequence: ordered dst_port values (deduplicated while preserving first order)
    seen_ports: set[int] = set()
    port_sequence: list[int] = []
    for e in sorted_events:
        p = e.get("dst_port")
        if isinstance(p, int) and p not in seen_ports:
            seen_ports.add(p)
            port_sequence.append(p)
            if len(port_sequence) >= TOP_PORT_SEQUENCE_N:
                break

    # Event type sequence (ordered, all events)
    event_type_sequence = [e["event_type"] for e in sorted_events]

    # Credential sequence — patterns only, never raw values
    cred_sequence = _extract_credential_sequence(sorted_events)

    if not port_sequence and not cred_sequence:
        return None

    return {
        "port_sequence": port_sequence,
        "event_type_sequence": event_type_sequence,
        "credential_sequence": cred_sequence,
    }


# ---------------------------------------------------------------------------
# Protocol features
# ---------------------------------------------------------------------------


def compute_protocol_features(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute protocol-level behavioral features.

    Service distribution is always available (derived from events.service).
    SSH KEX ordering is extracted from raw_data when present (Cowrie sessions).
    TLS cipher ordering is extracted from raw_data when present (HTTP sensors).

    Encoding (Appendix):
        service_distribution  — {service: proportion} for observed services
        ssh_kex_ordering      — ordered list of KEX algorithm strings, or null
        tls_cipher_ordering   — ordered list of hex cipher IDs, or null
    """
    # Service distribution (service → proportion of events with that service)
    service_counts: Counter[str] = Counter()
    for e in events:
        svc = e.get("service")
        if svc:
            service_counts[svc] += 1

    if not service_counts and not events:
        return None

    total = sum(service_counts.values())
    service_dist = (
        {svc: round(cnt / total, 6) for svc, cnt in service_counts.most_common()}
        if total > 0
        else {}
    )

    # SSH KEX ordering — take from the first event that has it (tool-level signal)
    ssh_kex: list[str] | None = None
    for e in events:
        raw = e.get("raw_data") or {}
        kex = raw.get("kex_algs") or raw.get("kex_algorithms")
        if isinstance(kex, list) and all(isinstance(k, str) for k in kex):
            ssh_kex = kex
            break

    # TLS cipher ordering — take from the first event that has it
    tls_ciphers: list[str] | None = None
    for e in events:
        raw = e.get("raw_data") or {}
        ciphers = raw.get("tls_cipher_suites") or raw.get("ja3_ciphers")
        if isinstance(ciphers, list) and all(isinstance(c, str) for c in ciphers):
            tls_ciphers = ciphers
            break

    return {
        "service_distribution": service_dist,
        "ssh_kex_ordering": ssh_kex,
        "tls_cipher_ordering": tls_ciphers,
    }


# ---------------------------------------------------------------------------
# Credential features
# ---------------------------------------------------------------------------


# Username pattern categories — character class of the username string.
# Raw username values are never stored.
def _classify_username(username: str) -> str:
    if not username:
        return "empty"
    if "@" in username:
        return "email"
    if username.isdigit():
        return "numeric"
    if username.isalpha():
        return "alpha"
    if username.isalnum():
        return "alphanum"
    return "special"


# Password pattern categories — character class of the password string.
# Raw password values are never stored.
def _classify_password(password: str) -> str:
    if not password:
        return "empty"
    if password.isdigit():
        return "numeric"
    if password.isalpha():
        return "alpha"
    if password.isalnum():
        return "alphanum"
    return "special"


def _extract_credential_sequence(
    sorted_events: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return a credential sequence of pattern entries, no raw values."""
    sequence: list[dict[str, str]] = []
    for e in sorted_events:
        raw = e.get("raw_data") or {}
        username = raw.get("username")
        password = raw.get("password")
        if username is None and password is None:
            continue
        entry = {
            "username_pattern": _classify_username(str(username) if username is not None else ""),
            "password_class": _classify_password(str(password) if password is not None else ""),
        }
        sequence.append(entry)
        if len(sequence) >= MAX_CREDENTIAL_SEQUENCE:
            break
    return sequence


def compute_credential_features(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute credential-attack behavioral features.

    Only pattern statistics are stored — no raw usernames or passwords.

    Returns None when no events contain credential data (username or password
    fields absent from raw_data for all events).

    Encoding (Appendix / §3.1 Credential features):
        credential_count      — total credential pairs observed
        username_class_dist   — {pattern_class: proportion}
        password_length_mean  — mean password length (float)
        password_char_class   — {metric: ratio} character class proportions
        credential_sequence   — [{"username_pattern", "password_class"}, ...] (max 50)
    """
    cred_events = [
        e
        for e in events
        if (e.get("raw_data") or {}).get("username") is not None
        or (e.get("raw_data") or {}).get("password") is not None
    ]
    if not cred_events:
        return None

    username_classes: list[str] = []
    password_lengths: list[int] = []
    has_upper = has_lower = has_digit = has_special = 0

    for e in cred_events:
        raw = e.get("raw_data") or {}
        uname = raw.get("username")
        passwd = raw.get("password")

        if uname is not None:
            username_classes.append(_classify_username(str(uname)))

        if passwd is not None:
            pw = str(passwd)
            password_lengths.append(len(pw))
            if any(c.isupper() for c in pw):
                has_upper += 1
            if any(c.islower() for c in pw):
                has_lower += 1
            if any(c.isdigit() for c in pw):
                has_digit += 1
            if any(not c.isalnum() for c in pw):
                has_special += 1

    cred_count = len(cred_events)
    pw_count = len(password_lengths)

    # Username class distribution
    class_counts: Counter[str] = Counter(username_classes)
    total_u = sum(class_counts.values())
    username_class_dist = (
        {cls: round(cnt / total_u, 6) for cls, cnt in class_counts.most_common()}
        if total_u > 0
        else {}
    )

    # Password character class proportions
    pw_char_class: dict[str, float] = {}
    if pw_count > 0:
        pw_char_class = {
            "has_upper_ratio": round(has_upper / pw_count, 6),
            "has_lower_ratio": round(has_lower / pw_count, 6),
            "has_digit_ratio": round(has_digit / pw_count, 6),
            "has_special_ratio": round(has_special / pw_count, 6),
        }

    # Password length stats
    pw_length_mean = round(statistics.mean(password_lengths), 3) if password_lengths else None

    # Credential sequence (pattern-only)
    sorted_events = sorted(cred_events, key=lambda e: e["ts"])
    cred_sequence = _extract_credential_sequence(sorted_events)

    return {
        "credential_count": cred_count,
        "username_class_dist": username_class_dist,
        "password_length_mean": pw_length_mean,
        "password_char_class": pw_char_class,
        "credential_sequence": cred_sequence,
    }


# ---------------------------------------------------------------------------
# Target features
# ---------------------------------------------------------------------------


def compute_target_features(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute target selection behavioral features.

    Encoding (Appendix / §3.1 Target selection features):
        port_freq        — {port_str: proportion} for top-20 destination ports
        unique_port_count — total number of distinct ports targeted
        top_dst_ports    — ordered list of top-20 ports by frequency
        service_dist     — {service: proportion} (redundant with protocol_features
                           but retained here for clustering use)
    """
    port_counts: Counter[int] = Counter()
    for e in events:
        p = e.get("dst_port")
        if isinstance(p, int):
            port_counts[p] += 1

    if not port_counts:
        return None

    total = sum(port_counts.values())
    top_ports = port_counts.most_common(TOP_PORT_FREQ_N)

    port_freq = {str(p): round(cnt / total, 6) for p, cnt in top_ports}
    top_dst_ports = [p for p, _ in top_ports]

    return {
        "port_freq": port_freq,
        "unique_port_count": len(port_counts),
        "top_dst_ports": top_dst_ports,
    }


# ---------------------------------------------------------------------------
# Tool signals
# ---------------------------------------------------------------------------


def compute_tool_signals(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute tool-level behavioral signals.

    Source distribution reveals which sensor type observed the activity.
    Event type distribution encodes the attack methodology mix.
    Tool inferences are conservative: only string patterns, never binary
    hashes or payload fragments.

    Encoding (Appendix / §3.1):
        source_dist      — {source: proportion} (sensor types)
        event_type_dist  — {event_type: proportion}
        inferred_tools   — [{tool: str, confidence: float}] (heuristic guesses)
    """
    if not events:
        return None

    source_counts: Counter[str] = Counter(e.get("source", "unknown") for e in events)
    type_counts: Counter[str] = Counter(e["event_type"] for e in events)

    total = len(events)
    source_dist = {src: round(cnt / total, 6) for src, cnt in source_counts.most_common()}
    event_type_dist = {et: round(cnt / total, 6) for et, cnt in type_counts.most_common()}

    # Heuristic tool inference from source and event type patterns
    inferred = _infer_tools(source_dist, event_type_dist)

    return {
        "source_dist": source_dist,
        "event_type_dist": event_type_dist,
        "inferred_tools": inferred,
    }


def _infer_tools(
    source_dist: dict[str, float],
    event_type_dist: dict[str, float],
) -> list[dict[str, float]]:
    """Heuristic tool signature detection from observable source/type patterns."""
    inferred: list[dict[str, float]] = []

    # Cowrie-based SSH scanner: primary source is cowrie, heavy auth_failed
    cowrie_share = source_dist.get("cowrie", 0.0)
    auth_fail_share = event_type_dist.get("auth_failed", 0.0)
    if cowrie_share >= 0.5 and auth_fail_share >= 0.5:
        confidence = round(min(1.0, (cowrie_share + auth_fail_share) / 2), 3)
        inferred.append({"tool": "ssh_brute_force", "confidence": confidence})

    # Port scanner: heavy port_scan activity
    scan_share = event_type_dist.get("port_scan", 0.0)
    if scan_share >= 0.5:
        inferred.append({"tool": "port_scanner", "confidence": round(scan_share, 3)})

    # Web scanner: heavy http_probe activity
    http_share = event_type_dist.get("http_probe", 0.0)
    if http_share >= 0.4:
        inferred.append({"tool": "web_scanner", "confidence": round(http_share, 3)})

    return inferred


# ---------------------------------------------------------------------------
# Combined extraction
# ---------------------------------------------------------------------------


def extract_all_features(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute all six feature categories for the given event list.

    Each value is a dict (if computable) or None (if insufficient data).
    None values contribute nothing to fingerprint confidence and nothing
    to similarity scoring (§8.1 — null dimensions excluded from both
    numerator and denominator).

    Returns a dict with exactly these six keys:
        timing_features, sequence_features, protocol_features,
        credential_features, target_features, tool_signals
    """
    return {
        "timing_features": compute_timing_features(events),
        "sequence_features": compute_sequence_features(events),
        "protocol_features": compute_protocol_features(events),
        "credential_features": compute_credential_features(events),
        "target_features": compute_target_features(events),
        "tool_signals": compute_tool_signals(events),
    }
