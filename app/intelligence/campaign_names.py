"""Deterministic campaign name generator.

Names are derived from the campaign UUID using a SHA-256 hash, so they are
stable once assigned — the same UUID always produces the same name.

Format: ADJECTIVE-ANIMAL-N  (e.g., SHADOW-CRANE-7)

30 adjectives × 30 animals × 90 numbers = 81,000 possible names, sufficient
for Phase 4 deployment scale.
"""

from __future__ import annotations

import hashlib

_ADJECTIVES: list[str] = [
    "shadow",
    "crimson",
    "silent",
    "amber",
    "frozen",
    "cobalt",
    "phantom",
    "scarlet",
    "hollow",
    "iron",
    "lunar",
    "obsidian",
    "silver",
    "dark",
    "hidden",
    "ancient",
    "midnight",
    "rapid",
    "steel",
    "veiled",
    "volatile",
    "carbon",
    "prism",
    "static",
    "titan",
    "nova",
    "void",
    "apex",
    "cipher",
    "delta",
]

_ANIMALS: list[str] = [
    "crane",
    "wolf",
    "raven",
    "fox",
    "hawk",
    "bear",
    "lynx",
    "viper",
    "eagle",
    "cobra",
    "mantis",
    "shark",
    "python",
    "falcon",
    "jaguar",
    "tiger",
    "osprey",
    "scorpion",
    "otter",
    "manta",
    "hornet",
    "panther",
    "kestrel",
    "beetle",
    "crow",
    "mongoose",
    "ferret",
    "wyvern",
    "hydra",
    "asp",
]


def generate_campaign_name(campaign_id: str) -> str:
    """Return a stable human-readable name for campaign_id.

    Uses the first 32 hex digits of SHA-256(campaign_id) to deterministically
    select an adjective, animal, and number.  Same input → same output always.
    """
    h = int(hashlib.sha256(campaign_id.encode()).hexdigest(), 16)
    adj = _ADJECTIVES[h % len(_ADJECTIVES)]
    animal = _ANIMALS[(h >> 8) % len(_ANIMALS)]
    number = (h >> 16) % 90 + 1
    return f"{adj.upper()}-{animal.upper()}-{number}"
