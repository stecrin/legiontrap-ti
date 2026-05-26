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
