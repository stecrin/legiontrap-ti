"""Fingerprint similarity computation for campaign clustering (§8.1).

All functions are pure: no database access, no I/O, no side effects.
Inputs are parsed feature dicts (not raw JSON strings).

Similarity model per §8.1:
  continuous distributions → interval stat comparison (normalised distance)
  histograms (tod/dow)     → Jensen-Shannon divergence, inverted to [0,1]
  sequences (ports, KEX)   → normalised Levenshtein edit distance
  categorical/set features → Jaccard similarity

Null-dimension rule (§8.1):
  When either fingerprint has None for a dimension, that dimension contributes
  zero to BOTH the numerator and the denominator.  Sparse fingerprints are
  not penalised for having fewer features than a rich campaign fingerprint.

Infrastructure features (ASN, geography) are deliberately excluded per §12.4.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from app.intelligence.constants import (
    WEIGHT_CREDENTIAL,
    WEIGHT_PROTOCOL,
    WEIGHT_SEQUENCE,
    WEIGHT_TARGET,
    WEIGHT_TIMING,
)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SimilarityResult:
    """Per-dimension scores and the weighted total for one fingerprint pair."""

    timing_similarity: float | None
    sequence_similarity: float | None
    protocol_similarity: float | None
    credential_similarity: float | None
    target_similarity: float | None
    weighted_total: float
    dimensions_used: int  # count of non-null dimension pairs

    def as_dict(self) -> dict[str, Any]:
        return {
            "timing_similarity": self.timing_similarity,
            "sequence_similarity": self.sequence_similarity,
            "protocol_similarity": self.protocol_similarity,
            "credential_similarity": self.credential_similarity,
            "target_similarity": self.target_similarity,
            "weighted_total": round(self.weighted_total, 6),
            "dimensions_used": self.dimensions_used,
        }


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------


def _stat_sim(a: float, b: float) -> float:
    """Normalised similarity between two non-negative scalars.

    Formula: 1 - |a - b| / (max(a, b) + 1.0)
    The +1.0 guard prevents division by zero when both values are 0 and
    ensures the result stays in [0, 1].
    """
    return 1.0 - abs(a - b) / (max(a, b) + 1.0)


def _cv_sim(a: float, b: float) -> float:
    """Similarity for burst_cv values; differences > 1.0 saturate at 0."""
    return 1.0 - min(abs(a - b), 1.0)


def _levenshtein(a: list, b: list) -> int:
    """Standard Levenshtein distance over arbitrary list elements."""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def _normalized_edit_sim(a: list, b: list) -> float:
    """1 - edit_distance / max(len(a), len(b)).  Both empty → 1.0."""
    if not a and not b:
        return 1.0
    return 1.0 - _levenshtein(a, b) / max(len(a), len(b))


def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity |A∩B| / |A∪B|.  Both empty → 1.0."""
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def _kl_divergence(p: list[float], q: list[float]) -> float:
    """KL(P||Q) in bits (log base 2).  0·log(0/q) = 0 by convention."""
    total = 0.0
    for pi, qi in zip(p, q, strict=False):
        if pi > 0.0 and qi > 0.0:
            total += pi * math.log2(pi / qi)
    return total


def _jsd(p: list[float], q: list[float]) -> float:
    """Jensen-Shannon divergence in [0, 1] (log base 2).

    Returns 1.0 (maximum divergence) when lengths differ or input is empty.
    """
    if len(p) != len(q) or not p:
        return 1.0
    m = [(a + b) / 2.0 for a, b in zip(p, q, strict=False)]
    return (_kl_divergence(p, m) + _kl_divergence(q, m)) / 2.0


def _histogram_sim(p: list[float] | None, q: list[float] | None) -> float | None:
    """1 - JSD(p, q).  Returns None when either histogram is absent."""
    if p is None or q is None or len(p) != len(q):
        return None
    return 1.0 - _jsd(p, q)


def _dict_jaccard(a: dict[str, float], b: dict[str, float]) -> float:
    """Jaccard similarity over the key sets of two frequency dicts."""
    return _jaccard(set(a.keys()), set(b.keys()))


# ---------------------------------------------------------------------------
# Per-dimension similarity functions
# ---------------------------------------------------------------------------


def timing_similarity(
    t1: dict[str, Any] | None,
    t2: dict[str, Any] | None,
) -> float | None:
    """Similarity between two timing_features dicts (§8.1, Appendix).

    Returns None when either input is None — null dimension, excluded from
    the weighted total by the caller.

    Sub-components averaged:
      interval stats (mean, stddev, p25, p75, p95) → _stat_sim average
      tod_histogram (24 floats)                     → 1 - JSD
      dow_histogram (7 floats)                      → 1 - JSD
      burst_cv (float)                              → _cv_sim
    """
    if t1 is None or t2 is None:
        return None

    scores: list[float] = []

    i1 = t1.get("interval") or {}
    i2 = t2.get("interval") or {}
    if i1 and i2:
        stat_sims = [
            _stat_sim(float(i1.get(k, 0.0)), float(i2.get(k, 0.0)))
            for k in ("mean", "stddev", "p25", "p75", "p95")
        ]
        scores.append(sum(stat_sims) / len(stat_sims))

    tod_s = _histogram_sim(t1.get("tod_histogram"), t2.get("tod_histogram"))
    if tod_s is not None:
        scores.append(tod_s)

    dow_s = _histogram_sim(t1.get("dow_histogram"), t2.get("dow_histogram"))
    if dow_s is not None:
        scores.append(dow_s)

    cv1 = t1.get("burst_cv")
    cv2 = t2.get("burst_cv")
    if cv1 is not None and cv2 is not None:
        scores.append(_cv_sim(float(cv1), float(cv2)))

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 6)


def sequence_similarity(
    s1: dict[str, Any] | None,
    s2: dict[str, Any] | None,
) -> float | None:
    """Similarity between two sequence_features dicts (§8.1, Appendix).

    Returns None when either input is None.

    Sub-components averaged:
      port_sequence       → normalised edit distance
      event_type_sequence → normalised edit distance (capped at 50 entries)
      credential_sequence → normalised edit distance over pattern tuples
    """
    if s1 is None or s2 is None:
        return None

    scores: list[float] = []

    p1 = s1.get("port_sequence") or []
    p2 = s2.get("port_sequence") or []
    if p1 or p2:
        scores.append(_normalized_edit_sim(p1, p2))

    _MAX_ET = 50
    et1 = (s1.get("event_type_sequence") or [])[:_MAX_ET]
    et2 = (s2.get("event_type_sequence") or [])[:_MAX_ET]
    if et1 or et2:
        scores.append(_normalized_edit_sim(et1, et2))

    cred1 = s1.get("credential_sequence") or []
    cred2 = s2.get("credential_sequence") or []
    if cred1 or cred2:
        c1t = [(c.get("username_pattern", ""), c.get("password_class", "")) for c in cred1]
        c2t = [(c.get("username_pattern", ""), c.get("password_class", "")) for c in cred2]
        scores.append(_normalized_edit_sim(c1t, c2t))

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 6)


def protocol_similarity(
    p1: dict[str, Any] | None,
    p2: dict[str, Any] | None,
) -> float | None:
    """Similarity between two protocol_features dicts (§8.1, Appendix).

    Returns None when either input is None.

    Sub-components averaged:
      service_distribution → Jaccard on service key sets
      ssh_kex_ordering     → normalised edit distance (when both present)
      tls_cipher_ordering  → normalised edit distance (when both present)
    """
    if p1 is None or p2 is None:
        return None

    scores: list[float] = []

    sd1 = p1.get("service_distribution") or {}
    sd2 = p2.get("service_distribution") or {}
    if sd1 or sd2:
        scores.append(_dict_jaccard(sd1, sd2))

    kex1 = p1.get("ssh_kex_ordering")
    kex2 = p2.get("ssh_kex_ordering")
    if kex1 is not None and kex2 is not None:
        scores.append(_normalized_edit_sim(kex1, kex2))

    tls1 = p1.get("tls_cipher_ordering")
    tls2 = p2.get("tls_cipher_ordering")
    if tls1 is not None and tls2 is not None:
        scores.append(_normalized_edit_sim(tls1, tls2))

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 6)


def credential_similarity(
    c1: dict[str, Any] | None,
    c2: dict[str, Any] | None,
) -> float | None:
    """Similarity between two credential_features dicts (§8.1, Appendix).

    Returns None when either input is None.

    Sub-components averaged:
      username_class_dist  → Jaccard on class key sets
      password_char_class  → _stat_sim average over shared ratio keys
      credential_sequence  → normalised edit distance over pattern tuples
    """
    if c1 is None or c2 is None:
        return None

    scores: list[float] = []

    ud1 = c1.get("username_class_dist") or {}
    ud2 = c2.get("username_class_dist") or {}
    if ud1 or ud2:
        scores.append(_dict_jaccard(ud1, ud2))

    pcc1 = c1.get("password_char_class") or {}
    pcc2 = c2.get("password_char_class") or {}
    shared = set(pcc1.keys()) & set(pcc2.keys())
    if shared:
        pcc_sims = [_stat_sim(float(pcc1[k]), float(pcc2[k])) for k in shared]
        scores.append(sum(pcc_sims) / len(pcc_sims))

    cred1 = c1.get("credential_sequence") or []
    cred2 = c2.get("credential_sequence") or []
    if cred1 or cred2:
        c1t = [(c.get("username_pattern", ""), c.get("password_class", "")) for c in cred1]
        c2t = [(c.get("username_pattern", ""), c.get("password_class", "")) for c in cred2]
        scores.append(_normalized_edit_sim(c1t, c2t))

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 6)


def target_similarity(
    t1: dict[str, Any] | None,
    t2: dict[str, Any] | None,
) -> float | None:
    """Similarity between two target_features dicts (§8.1, Appendix).

    Returns None when either input is None.

    Sub-components averaged:
      port_freq     → Jaccard on top-10 port key sets (Appendix)
      top_dst_ports → normalised edit distance on ordered list
    """
    if t1 is None or t2 is None:
        return None

    scores: list[float] = []

    pf1 = t1.get("port_freq") or {}
    pf2 = t2.get("port_freq") or {}
    if pf1 or pf2:
        top10_1 = set(sorted(pf1, key=lambda k: pf1[k], reverse=True)[:10])
        top10_2 = set(sorted(pf2, key=lambda k: pf2[k], reverse=True)[:10])
        scores.append(_jaccard(top10_1, top10_2))

    td1 = t1.get("top_dst_ports") or []
    td2 = t2.get("top_dst_ports") or []
    if td1 or td2:
        scores.append(_normalized_edit_sim(td1, td2))

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 6)


# ---------------------------------------------------------------------------
# Weighted aggregation
# ---------------------------------------------------------------------------


def compute_weighted_similarity(
    fp1: dict[str, Any],
    fp2: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
) -> SimilarityResult:
    """Weighted fingerprint similarity per §8.1 and §3.2.

    fp1 and fp2 are behavioral_fingerprint dicts whose feature columns are
    stored JSON strings (or None).  Parsing happens here.

    Null dimensions contribute zero to both numerator and denominator so that
    sparse fingerprints are not artificially penalised (§8.1).

    Infrastructure features (ASN, geography) are intentionally absent from
    the similarity computation per §12.4.

    weights, if provided, must be a dict with keys:
      timing, sequence, protocol, credential, target
    Values must be positive and sum to ~1.0.  When None, global constants are
    used.  Same fingerprints + same weights = same result (deterministic).
    """

    def _parse(s: str | None) -> dict | None:
        if s is None:
            return None
        try:
            v = json.loads(s)
            return v if isinstance(v, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    ts = timing_similarity(_parse(fp1.get("timing_features")), _parse(fp2.get("timing_features")))
    ss = sequence_similarity(
        _parse(fp1.get("sequence_features")), _parse(fp2.get("sequence_features"))
    )
    ps = protocol_similarity(
        _parse(fp1.get("protocol_features")), _parse(fp2.get("protocol_features"))
    )
    cs = credential_similarity(
        _parse(fp1.get("credential_features")), _parse(fp2.get("credential_features"))
    )
    tgs = target_similarity(_parse(fp1.get("target_features")), _parse(fp2.get("target_features")))

    _w = weights or {}
    _WEIGHTS: dict[str, tuple[float | None, float]] = {
        "timing": (ts, _w.get("timing", WEIGHT_TIMING)),
        "sequence": (ss, _w.get("sequence", WEIGHT_SEQUENCE)),
        "protocol": (ps, _w.get("protocol", WEIGHT_PROTOCOL)),
        "credential": (cs, _w.get("credential", WEIGHT_CREDENTIAL)),
        "target": (tgs, _w.get("target", WEIGHT_TARGET)),
    }

    numerator = 0.0
    denominator = 0.0
    dimensions_used = 0
    for _dim, (sim, weight) in _WEIGHTS.items():
        if sim is not None:
            numerator += weight * sim
            denominator += weight
            dimensions_used += 1

    weighted_total = numerator / denominator if denominator > 0.0 else 0.0

    return SimilarityResult(
        timing_similarity=ts,
        sequence_similarity=ss,
        protocol_similarity=ps,
        credential_similarity=cs,
        target_similarity=tgs,
        weighted_total=round(weighted_total, 6),
        dimensions_used=dimensions_used,
    )
