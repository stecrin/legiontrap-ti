"""
STIX 2.1 bundle builder for LegionTrap TI.

Pure transformation module: receives plain Python dicts from the repository
layer and returns a STIX 2.1 bundle dict ready for JSON serialisation.

No FastAPI, SQLAlchemy, or settings imports.
No stix2 library dependency — plain Python dicts.

Object types produced:
  IPv4-Addr SCO       — network observable for each source IP
  Indicator SDO       — threat intelligence claim for each source IP
  Campaign SDO        — behavioral actor cluster (when campaign data provided)
  Relationship SDO    — "indicator indicates campaign" (when campaign data provided)

Design decisions:
- Deterministic IDs: uuid5 over a stable project namespace ensures the same
  IP or campaign always produces the same STIX object ID across exports.
- Custom properties: x_legiontrap_* prefix for non-standard fields.
- Privacy: Campaign SDOs contain no raw IP addresses; member IPs are only
  reachable via the existing Indicator objects. Relationship SDOs link
  object IDs, not raw IP values.
- Backward compatibility: campaigns and ip_campaign_map are optional;
  omitting them produces the same output as before Phase 4.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

# Stable project-specific UUID namespace for deterministic STIX ID generation.
# This value must never change — doing so would invalidate all previously
# generated STIX IDs for this deployment.
_STIX_NS = uuid.UUID("a7f3d4e5-1b2c-4d3e-8bdb-9a1f1e6b4c0f")

_SPEC_VERSION = "2.1"

# Maps LegionTrap tags to STIX open-vocabulary Indicator labels.
_TAG_TO_LABEL: dict[str, str] = {
    "brute-force": "malicious-activity",
    "malware": "malicious-activity",
    "command-exec": "malicious-activity",
    "auth-success": "malicious-activity",
    "scanner": "anomalous-activity",
}


def _stix_id(obj_type: str, key: str) -> str:
    """Return a deterministic STIX ID for the given object type and natural key."""
    return f"{obj_type}--{uuid.uuid5(_STIX_NS, f'{obj_type}:{key}')}"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _to_stix_ts(ts: str | None, fallback: str) -> str:
    """Normalise a stored timestamp string to STIX ISO-8601 format."""
    if not ts:
        return fallback
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except (ValueError, TypeError):
        return fallback


def _confidence(score: float | None) -> int:
    """Convert a 0.0–1.0 reputation score to a STIX 0–100 confidence integer."""
    if score is None:
        return 50
    return min(100, max(0, int(round(score * 100))))


def _labels(tags: list[str] | None) -> list[str]:
    """
    Derive STIX Indicator labels from LegionTrap tags.
    Anything touching a honeypot is at minimum malicious-activity.
    """
    if not tags:
        return ["malicious-activity"]
    mapped = {_TAG_TO_LABEL.get(t, "malicious-activity") for t in tags}
    return sorted(mapped)


def _build_campaign_sdo(campaign: dict, now: str) -> dict:
    """Build a STIX 2.1 Campaign SDO from a LegionTrap campaign record.

    No raw IP addresses are included — member IPs are only accessible
    via their respective Indicator objects.
    """
    first_seen = _to_stix_ts(campaign.get("first_seen"), now)
    last_seen = _to_stix_ts(campaign.get("last_seen"), None)
    campaign_stix_id = _stix_id("campaign", campaign["id"])
    obj: dict = {
        "type": "campaign",
        "spec_version": _SPEC_VERSION,
        "id": campaign_stix_id,
        "created": first_seen,
        "modified": last_seen or first_seen,
        "name": campaign["name"],
        "first_seen": first_seen,
        "confidence": _confidence(campaign.get("confidence")),
        "x_legiontrap_status": campaign.get("status"),
        "x_legiontrap_reactivation_count": campaign.get("reactivation_count", 0),
        "x_legiontrap_member_ip_count": campaign.get("member_ip_count", 0),
    }
    if last_seen:
        obj["last_seen"] = last_seen
    return obj


def _build_relationship_sdo(indicator_stix_id: str, campaign_stix_id: str, now: str) -> dict:
    """Build a STIX 2.1 Relationship SDO: indicator indicates campaign."""
    rel_key = f"indicates:{indicator_stix_id}:{campaign_stix_id}"
    return {
        "type": "relationship",
        "spec_version": _SPEC_VERSION,
        "id": _stix_id("relationship", rel_key),
        "created": now,
        "modified": now,
        "relationship_type": "indicates",
        "source_ref": indicator_stix_id,
        "target_ref": campaign_stix_id,
    }


def build_stix_bundle(
    ips: list[dict],
    campaigns: list[dict] | None = None,
    ip_campaign_map: dict[str, str] | None = None,
) -> dict:
    """
    Build a STIX 2.1 bundle from IP intelligence records and optional campaign data.

    ips records are expected to contain:
        ip              (str)              — IPv4 address
        first_seen      (str | None)       — ISO timestamp
        last_seen       (str | None)       — ISO timestamp
        event_count     (int)              — total observed events
        reputation_score (float | None)   — 0.0–1.0 heuristic score
        tags            (list[str] | None) — behavioural tag list

    campaigns (optional) — list of campaign dicts from get_campaigns_for_export().
    ip_campaign_map (optional) — {source_ip: campaign_id} from get_campaign_member_ip_map().
      When both are provided, Campaign SDOs and Relationship SDOs are added to the bundle.

    Returns a STIX 2.1 Bundle dict. Caller serialises with json.dumps().

    Deterministic IDs: the same IP or campaign always produces the same object IDs
    regardless of when or how many times the bundle is generated.
    """
    now = _now_iso()
    objects: list[dict] = []

    # Track indicator IDs built in this export for relationship linking.
    ip_to_indicator_id: dict[str, str] = {}

    for record in ips:
        ip = record.get("ip")
        if not ip:
            continue

        first_seen = _to_stix_ts(record.get("first_seen"), now)
        last_seen = _to_stix_ts(record.get("last_seen"), None)
        tags = record.get("tags") or []
        score = record.get("reputation_score")
        event_count = record.get("event_count") or 0

        indicator_id = _stix_id("indicator", ip)
        ip_to_indicator_id[ip] = indicator_id

        # IPv4-Addr SCO — the network observable
        ipv4_obj: dict = {
            "type": "ipv4-addr",
            "spec_version": _SPEC_VERSION,
            "id": _stix_id("ipv4-addr", ip),
            "value": ip,
        }

        # Indicator SDO — the threat intelligence claim
        indicator: dict = {
            "type": "indicator",
            "spec_version": _SPEC_VERSION,
            "id": indicator_id,
            "created": first_seen,
            "modified": last_seen or first_seen,
            "name": f"Malicious IP: {ip}",
            "description": (
                f"Observed {event_count} "
                f"event{'s' if event_count != 1 else ''} from this source "
                f"on LegionTrap TI sensors."
            ),
            "pattern": f"[ipv4-addr:value = '{ip}']",
            "pattern_type": "stix",
            "valid_from": first_seen,
            "labels": _labels(tags),
            "confidence": _confidence(score),
            "x_legiontrap_event_count": event_count,
        }

        if last_seen:
            indicator["valid_until"] = last_seen
        if tags:
            indicator["x_legiontrap_tags"] = tags
        if score is not None:
            indicator["x_legiontrap_reputation_score"] = score

        objects.append(ipv4_obj)
        objects.append(indicator)

    # Campaign SDOs — one per non-historical campaign.
    campaign_stix_ids: dict[str, str] = {}
    if campaigns:
        for campaign in campaigns:
            cid = campaign.get("id")
            if not cid:
                continue
            campaign_sdo = _build_campaign_sdo(campaign, now)
            campaign_stix_ids[cid] = campaign_sdo["id"]
            objects.append(campaign_sdo)

    # Relationship SDOs — "indicator indicates campaign" for IPs in this export.
    if ip_campaign_map and campaign_stix_ids:
        for ip, indicator_id in ip_to_indicator_id.items():
            legiontrap_campaign_id = ip_campaign_map.get(ip)
            if legiontrap_campaign_id is None:
                continue
            campaign_stix_id = campaign_stix_ids.get(legiontrap_campaign_id)
            if campaign_stix_id is None:
                continue
            objects.append(_build_relationship_sdo(indicator_id, campaign_stix_id, now))

    return {
        "type": "bundle",
        "id": _stix_id("bundle", "legiontrap-export"),
        "objects": objects,
    }
