"""Named constants for Phase 4 behavioral fingerprinting.

All thresholds and limits are defined here so they can be adjusted without
touching computation logic. Changing any value after production campaign data
is established requires a re-clustering pass (§12.2).

Configurable values (weights, thresholds, lifecycle days) are sourced from
app.core.config.settings so they can be overridden via environment variables.
Non-configurable structural constants (schema version, sequence caps, etc.)
remain hardcoded here.
"""

from __future__ import annotations

from app.core.config import settings

# Schema version embedded in every fingerprint row.  Increment when the
# JSON field structure changes and old fingerprints need recomputation (§12.1).
FINGERPRINT_VERSION: int = 1

# Inactivity gap (seconds) that ends one session and starts the next (§3.3).
SESSION_GAP_SECONDS: int = 1800  # 30 minutes

# Maximum number of ports retained in sequence_features.port_sequence (Appendix).
TOP_PORT_SEQUENCE_N: int = 50

# Maximum number of ports retained in target_features.port_freq (Appendix).
TOP_PORT_FREQ_N: int = 20

# Maximum credential-sequence entries stored; limits JSON growth (Appendix).
MAX_CREDENTIAL_SEQUENCE: int = 50

# ---------------------------------------------------------------------------
# Campaign clustering weights (§3.2, §12.2) — configurable via settings
# Must sum to 1.0.  Changing weights retroactively requires re-clustering (§12.2).
# ---------------------------------------------------------------------------
WEIGHT_TIMING: float = settings.WEIGHT_TIMING
WEIGHT_SEQUENCE: float = settings.WEIGHT_SEQUENCE
WEIGHT_PROTOCOL: float = settings.WEIGHT_PROTOCOL
WEIGHT_CREDENTIAL: float = settings.WEIGHT_CREDENTIAL
WEIGHT_TARGET: float = settings.WEIGHT_TARGET

# ---------------------------------------------------------------------------
# Association decision thresholds (§8.2, §12.2) — configurable via settings
# ---------------------------------------------------------------------------
SIMILARITY_AUTO_THRESHOLD: float = settings.SIMILARITY_AUTO_THRESHOLD
SIMILARITY_UNCERTAIN_LOW: float = settings.SIMILARITY_UNCERTAIN_LOW

# ---------------------------------------------------------------------------
# Temporal recency threshold bumps (§12.3) — configurable via settings
# Applied as a floor on the auto threshold when a campaign's last_seen is old.
# ---------------------------------------------------------------------------
TEMPORAL_THRESHOLD_6M: float = settings.TEMPORAL_THRESHOLD_6M
TEMPORAL_THRESHOLD_12M: float = settings.TEMPORAL_THRESHOLD_12M

# ---------------------------------------------------------------------------
# Fingerprint clustering gate (§12.6) — configurable via settings
# ---------------------------------------------------------------------------
MIN_EVENTS_FOR_CLUSTERING: int = settings.MIN_EVENTS_FOR_CLUSTERING

# ---------------------------------------------------------------------------
# Campaign status lifecycle boundaries in days (§3.6) — configurable via settings
# ---------------------------------------------------------------------------
CAMPAIGN_ACTIVE_DAYS: int = settings.CAMPAIGN_ACTIVE_DAYS
CAMPAIGN_DORMANT_DAYS: int = settings.CAMPAIGN_DORMANT_DAYS
