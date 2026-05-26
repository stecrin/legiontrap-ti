"""Campaign AI prompt builder — Phase 5 §7.

Builds structured (system_prompt, user_prompt) pairs for campaign summary generation.
Enforces Phase 5 §4 permitted-input rules: source IPs are never included in prompts.
Field sanitization is applied via app.ai.safety before embedding campaign data.

No AI calls are made here. No database writes. No external network access.
All functions are pure and side-effect-free.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.safety import sanitize_field

# ---------------------------------------------------------------------------
# System prompt (constant — never interpolated with user data)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = (
    "You are a threat intelligence analyst assistant. "
    "Summarize the following campaign record in 2-4 sentences for an operator brief. "
    "State what the campaign does, its current status, and any notable recurrence behavior. "
    "Do not infer or hypothesize beyond the data provided. "
    "Do not use information outside the provided data. "
    "Do not reference threat actor names, APT groups, or external threat intelligence databases. "
    "If the data is insufficient for a conclusion, say so explicitly. "
    "Use 'possible' or 'may indicate' for uncertain interpretations. "
    "Respond in plain prose. Do not use bullet points. 2-4 sentences only."
)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_LOW_CONFIDENCE_THRESHOLD: float = 0.50
_FIELD_MAX_LEN: int = 200


# ---------------------------------------------------------------------------
# Feature JSON parsers
# ---------------------------------------------------------------------------


def _parse_feature(json_str: str | None) -> dict | None:
    if not json_str:
        return None
    try:
        v = json.loads(json_str)
        return v if isinstance(v, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Per-dimension human-readable formatters
# ---------------------------------------------------------------------------


def _format_timing(features: dict | None) -> str:
    if not features:
        return "No data"
    parts: list[str] = []
    interval = features.get("interval") or {}
    mean = interval.get("mean")
    if mean is not None:
        parts.append(f"interval ~{float(mean):.1f}s avg")
    burst_cv = features.get("burst_cv")
    if burst_cv is not None and float(burst_cv) > 0.5:
        parts.append("burst activity present")
    tod = features.get("tod_histogram")
    if tod and len(tod) == 24:
        peak_hour = tod.index(max(tod))
        parts.append(f"peak hour {peak_hour:02d}:00 UTC")
    return ", ".join(parts) if parts else "No data"


def _format_sequence(features: dict | None) -> str:
    if not features:
        return "No data"
    parts: list[str] = []
    ps = features.get("port_sequence") or []
    if ps:
        parts.append(f"{len(ps)}-step port sequence")
    ets = features.get("event_type_sequence") or []
    unique_ets = len(set(ets)) if ets else 0
    if unique_ets:
        parts.append(f"{unique_ets} event type{'s' if unique_ets != 1 else ''}")
    return ", ".join(parts) if parts else "No data"


def _format_protocol(features: dict | None) -> str:
    if not features:
        return "No data"
    sd = features.get("service_distribution") or {}
    if not sd:
        return "No data"
    top = sorted(sd, key=lambda k: sd[k], reverse=True)[:3]
    return "primary services: " + ", ".join(str(s) for s in top)


def _format_credential(features: dict | None) -> str:
    if not features:
        return "No data"
    ucd = features.get("username_class_dist") or {}
    if not ucd:
        return "No data"
    top = sorted(ucd, key=lambda k: ucd[k], reverse=True)[:3]
    return "username class patterns: " + ", ".join(str(c) for c in top)


def _format_target(features: dict | None) -> str:
    if not features:
        return "No data"
    top_ports = features.get("top_dst_ports") or []
    if top_ports:
        return "primary ports: " + ", ".join(str(p) for p in top_ports[:5])
    pf = features.get("port_freq") or {}
    if pf:
        top = sorted(pf, key=lambda k: pf[k], reverse=True)[:5]
        return "primary ports: " + ", ".join(str(p) for p in top)
    return "No data"


# ---------------------------------------------------------------------------
# Campaign analytics formatters
# ---------------------------------------------------------------------------


def _format_tactic_dist(tactic_dist_json: str | None) -> str:
    if not tactic_dist_json:
        return "Not computed"
    try:
        dist = json.loads(tactic_dist_json)
        if not isinstance(dist, dict) or not dist:
            return "None observed"
        items = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:5]
        return "; ".join(f"{tactic} ({count})" for tactic, count in items)
    except (json.JSONDecodeError, TypeError):
        return "Not computed"


def _format_top_ports(top_ports_json: str | None) -> str:
    if not top_ports_json:
        return "Not computed"
    try:
        ports = json.loads(top_ports_json)
        if not isinstance(ports, list) or not ports:
            return "None observed"
        return ", ".join(str(r["port"]) for r in ports[:5] if "port" in r)
    except (json.JSONDecodeError, TypeError, KeyError):
        return "Not computed"


def _format_clustering_notes(notes_json: str | None) -> str | None:
    if not notes_json:
        return None
    try:
        notes = json.loads(notes_json)
        if not isinstance(notes, dict):
            return None
        decision = notes.get("decision", "")
        score = notes.get("weighted_total")
        dims = notes.get("dimensions_used")
        if decision:
            parts = [f"clustering decision: {decision}"]
            if score is not None:
                parts.append(f"similarity {float(score):.2f}")
            if dims is not None:
                parts.append(f"{dims} dimensions")
            return "; ".join(parts)
    except (json.JSONDecodeError, TypeError):
        pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_fingerprint_summary(fingerprint: dict[str, Any] | None) -> dict[str, str]:
    """Convert raw fingerprint feature JSON into brief human-readable dimension summaries.

    source_ip is explicitly excluded — this function only reads *_features keys.
    """
    if fingerprint is None:
        return {
            "timing": "Insufficient data",
            "sequence": "Insufficient data",
            "protocol": "Insufficient data",
            "credential": "Insufficient data",
            "target": "Insufficient data",
        }
    return {
        "timing": _format_timing(_parse_feature(fingerprint.get("timing_features"))),
        "sequence": _format_sequence(_parse_feature(fingerprint.get("sequence_features"))),
        "protocol": _format_protocol(_parse_feature(fingerprint.get("protocol_features"))),
        "credential": _format_credential(_parse_feature(fingerprint.get("credential_features"))),
        "target": _format_target(_parse_feature(fingerprint.get("target_features"))),
    }


def build_campaign_summary_prompt(
    campaign: dict[str, Any],
    fingerprint: dict[str, Any] | None,
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a campaign summary prompt pair for AI generation.

    Applies field sanitization to all text fields sourced from the campaign record.
    source_ip values from fingerprint and observations are never read or included.

    Returns a dict with keys:
        system_prompt    — constant threat intel analyst instruction
        user_prompt      — <data> block + operator brief instruction
        source_records   — {campaign_id, fingerprint_present, observation_count}
        safety_flags     — list of flag strings (e.g. "low_confidence", "no_fingerprint")
    """
    safety_flags: list[str] = []

    # Campaign scalar fields
    name = sanitize_field(str(campaign.get("name", "")), _FIELD_MAX_LEN)
    status = str(campaign.get("status", "unknown"))
    confidence = float(campaign.get("confidence", 0.0))
    confidence_pct = round(confidence * 100, 1)
    first_seen = str(campaign.get("first_seen", "unknown"))
    last_seen = str(campaign.get("last_seen", "unknown"))
    dormant_since = campaign.get("dormant_since")
    reactivation_count = int(campaign.get("reactivation_count", 0))
    member_ip_count = int(campaign.get("member_ip_count", 0))

    # Analytics JSON → readable text
    tactic_dist_text = _format_tactic_dist(campaign.get("attack_tactic_dist"))
    top_ports_text = _format_top_ports(campaign.get("top_target_ports"))

    # Clustering notes (sanitized)
    notes_summary = _format_clustering_notes(campaign.get("notes"))
    if notes_summary:
        notes_summary = sanitize_field(notes_summary, _FIELD_MAX_LEN)

    # Safety flags
    if confidence < _LOW_CONFIDENCE_THRESHOLD:
        safety_flags.append("low_confidence")

    if fingerprint is None:
        safety_flags.append("no_fingerprint")

    dim_summaries = format_fingerprint_summary(fingerprint)

    # Observation aggregates (no individual IPs)
    obs_count = len(observations)
    reactivation_obs = sum(1 for o in observations if o.get("is_reactivation"))

    # Assemble <data> block
    lines: list[str] = ["<data>"]
    lines.append(f"Campaign: {name}")
    lines.append(f"Status: {status}")
    lines.append(f"Confidence: {confidence_pct}%")
    lines.append(f"First observed: {first_seen}")
    lines.append(f"Last observed: {last_seen}")
    if dormant_since:
        lines.append(f"Dormant since: {dormant_since}")
    lines.append(f"Member IP count: {member_ip_count}")
    lines.append(f"Reactivation count: {reactivation_count}")
    lines.append(f"Attack tactics: {tactic_dist_text}")
    lines.append(f"Top target ports: {top_ports_text}")
    lines.append("Behavioral dimensions:")
    lines.append(f"  Timing: {dim_summaries['timing']}")
    lines.append(f"  Sequence: {dim_summaries['sequence']}")
    lines.append(f"  Protocol: {dim_summaries['protocol']}")
    lines.append(f"  Credential: {dim_summaries['credential']}")
    lines.append(f"  Target: {dim_summaries['target']}")
    lines.append(f"Recorded observations: {obs_count}")
    if reactivation_obs > 0:
        lines.append(f"Reactivation events: {reactivation_obs}")
    if notes_summary:
        lines.append(f"Clustering context: {notes_summary}")
    lines.append("</data>")

    if "low_confidence" in safety_flags:
        lines.append(
            f"\nNote: campaign confidence is {confidence_pct}% — treat this summary "
            "with appropriate caution and qualify uncertain claims."
        )

    data_block = "\n".join(lines)
    user_prompt = (
        f"{data_block}\n\n"
        "Summarize the above campaign for an operator brief in 2-4 plain prose sentences. "
        "Do not use bullet points."
    )

    return {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "source_records": {
            "campaign_id": str(campaign.get("id", "")),
            "fingerprint_present": fingerprint is not None,
            "observation_count": obs_count,
        },
        "safety_flags": safety_flags,
    }


# ---------------------------------------------------------------------------
# Multi-campaign brief — system prompt and builder
# ---------------------------------------------------------------------------

BRIEF_SYSTEM_PROMPT: str = (
    "You are a threat intelligence analyst assistant. "
    "The following campaigns were recently active. "
    "Write a threat brief of 3-6 sentences covering: the most significant campaign, "
    "any shared behavioral patterns across campaigns, and any notable changes in actor behavior. "
    "Do not infer beyond the data provided. "
    "Do not reference threat actor names, APT groups, or external threat intelligence databases. "
    "If the data is insufficient for a conclusion, say so explicitly. "
    "Label any uncertain interpretation with 'possible' or 'may indicate'. "
    "Respond in plain prose. One paragraph maximum. Do not use bullet points."
)


def _format_campaign_block(campaign: dict[str, Any]) -> str:
    """Format a single campaign dict into a compact text block for the brief prompt.

    Source IPs are never read — only pre-aggregated fields are used.
    """
    name = sanitize_field(str(campaign.get("name", "")), _FIELD_MAX_LEN)
    status = str(campaign.get("status", "unknown"))
    confidence_pct = round(float(campaign.get("confidence", 0.0)) * 100, 1)
    last_seen = str(campaign.get("last_seen", "unknown"))
    member_count = int(campaign.get("member_ip_count", 0))
    reactivation_count = int(campaign.get("reactivation_count", 0))
    tactic_text = _format_tactic_dist(campaign.get("attack_tactic_dist"))
    ports_text = _format_top_ports(campaign.get("top_target_ports"))

    lines = [
        f"Campaign: {name}",
        f"Status: {status} | Confidence: {confidence_pct}% | Last seen: {last_seen}",
        f"Members: {member_count} | Reactivations: {reactivation_count}",
        f"Tactics: {tactic_text}",
        f"Ports: {ports_text}",
    ]
    return "\n".join(lines)


def build_brief_prompt(campaigns: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a multi-campaign threat brief prompt.

    Each campaign contributes a compact 5-line text block. Source IPs are
    never included. Field sanitization is applied to all string inputs.

    Returns a dict with keys:
        system_prompt    — constant analyst instruction
        user_prompt      — <campaigns> block + brief instruction
        source_records   — {campaign_ids: [...], campaign_count: N}
    """
    campaign_ids = [str(c.get("id", "")) for c in campaigns]

    if not campaigns:
        return {
            "system_prompt": BRIEF_SYSTEM_PROMPT,
            "user_prompt": "<campaigns>\n(No campaign data available.)\n</campaigns>",
            "source_records": {
                "campaign_ids": [],
                "campaign_count": 0,
            },
        }

    blocks = [_format_campaign_block(c) for c in campaigns]
    campaigns_section = "\n\n".join(blocks)

    user_prompt = (
        f"<campaigns>\n{campaigns_section}\n</campaigns>\n\n"
        "Write a threat brief of 3-6 sentences covering the most significant campaign, "
        "shared behavioral patterns, and any notable changes. "
        "Plain prose only. Do not use bullet points."
    )

    return {
        "system_prompt": BRIEF_SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "source_records": {
            "campaign_ids": campaign_ids,
            "campaign_count": len(campaigns),
        },
    }
