"""Named constants for Phase 4 behavioral fingerprinting.

All thresholds and limits are defined here so they can be adjusted without
touching computation logic. Changing any value after production campaign data
is established requires a re-clustering pass (§12.2).
"""

from __future__ import annotations

# Schema version embedded in every fingerprint row.  Increment when the
# JSON field structure changes and old fingerprints need recomputation (§12.1).
FINGERPRINT_VERSION: int = 1

# Fingerprints with fewer events than this are stored but excluded from
# campaign clustering (§12.6).  Their confidence will be < 0.20.
MIN_EVENTS_FOR_CLUSTERING: int = 10

# Inactivity gap (seconds) that ends one session and starts the next (§3.3).
SESSION_GAP_SECONDS: int = 1800  # 30 minutes

# Maximum number of ports retained in sequence_features.port_sequence (Appendix).
TOP_PORT_SEQUENCE_N: int = 50

# Maximum number of ports retained in target_features.port_freq (Appendix).
TOP_PORT_FREQ_N: int = 20

# Maximum credential-sequence entries stored; limits JSON growth (Appendix).
MAX_CREDENTIAL_SEQUENCE: int = 50

# ---------------------------------------------------------------------------
# Campaign clustering weights (§3.2, §12.2)
# Must sum to 1.0.  Never hardcode these inline — changing weights retroactively
# requires re-clustering all historical fingerprints (§12.2).
# ---------------------------------------------------------------------------
WEIGHT_TIMING: float = 0.20
WEIGHT_SEQUENCE: float = 0.35
WEIGHT_PROTOCOL: float = 0.25
WEIGHT_CREDENTIAL: float = 0.10
WEIGHT_TARGET: float = 0.10

# ---------------------------------------------------------------------------
# Association decision thresholds (§8.2, §12.2)
# Launch defaults — calibrate after 30 days of campaign data.
# ---------------------------------------------------------------------------
SIMILARITY_AUTO_THRESHOLD: float = 0.80  # >= auto-associate
SIMILARITY_UNCERTAIN_LOW: float = 0.60  # [0.60, 0.80) → uncertain association

# ---------------------------------------------------------------------------
# Temporal recency threshold bumps (§12.3)
# Applied as a floor on the auto threshold when a campaign's last_seen is old.
# ---------------------------------------------------------------------------
TEMPORAL_THRESHOLD_6M: float = 0.85  # campaign last active 6–12 months ago
TEMPORAL_THRESHOLD_12M: float = 0.90  # campaign last active > 12 months ago

# ---------------------------------------------------------------------------
# Campaign status lifecycle boundaries in days (§3.6)
# ---------------------------------------------------------------------------
CAMPAIGN_ACTIVE_DAYS: int = 7
CAMPAIGN_DORMANT_DAYS: int = 90
