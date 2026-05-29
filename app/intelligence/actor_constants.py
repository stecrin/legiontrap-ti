"""Actor identity constants — Phase 7 Group B1.

Defines the closed relationship-type vocabulary for campaign_lineage and
valid lifecycle statuses for actor_profiles.

VALID_RELATIONSHIP_TYPES is the authoritative source.  ActorRepository and
the actors router both validate against this set.  The vocabulary is a data
contract: adding or removing types requires a coordinated migration (see
Phase 7 blueprint §13).

No AI imports.  No federation imports.  No automatic actor attribution.
"""

from __future__ import annotations

VALID_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "primary_campaign",
        "infrastructure_reuse",
        "tactic_match",
        "temporal_overlap",
    }
)

VALID_ACTOR_STATUSES: frozenset[str] = frozenset({"active", "archived"})
