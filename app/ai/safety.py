"""AI safety layer — field sanitization and output validation.

Enforces Phase 5 §9 safety rules:
  - Field sanitization: truncation + prompt injection pattern detection
  - IP address detection and redaction in prompts and AI outputs
  - Output validation: length limits, IP-in-output rejection
  - Byte budget check for prompt size control

All functions are pure, deterministic, and side-effect-free.
No database access, no network calls, no external dependencies.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Replacement text for fields that fail the injection scan.
REDACTED_FIELD = "[FIELD REDACTED — failed safety check]"

# Default maximum length per sanitized field (characters).
DEFAULT_FIELD_MAX_LEN: int = 200

# Regex patterns that suggest prompt injection attempts.
# Applied case-insensitively. Any match causes the entire field to be redacted.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(previous|prior|above|all)", re.IGNORECASE),
    re.compile(
        r"disregard\s+(previous|prior|above|all|the\s+(above|previous|prior))", re.IGNORECASE
    ),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"<\|", re.IGNORECASE),
    re.compile(r"\|\s*>", re.IGNORECASE),
    re.compile(r"prompt\s*injection", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"act\s+as\s+", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"forget\s+(your|all|previous|everything)", re.IGNORECASE),
    re.compile(r"override\s+(your|previous|prior)", re.IGNORECASE),
    re.compile(r"new\s+(instructions?|rules?|directives?)", re.IGNORECASE),
    re.compile(r"from\s+now\s+on\s+", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"###\s*instructions?", re.IGNORECASE),
]

# IPv4 pattern: four dot-separated 1-3 digit groups.
_IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# IPv6 pattern: at least two colon-separated hex groups (catches full and compressed forms).
_IPV6_PATTERN = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}\b"
    r"|"
    r"\b::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b"
)

_IP_PATTERN = re.compile(r"(?:" + _IPV4_PATTERN.pattern + r"|" + _IPV6_PATTERN.pattern + r")")


# ---------------------------------------------------------------------------
# Field sanitization
# ---------------------------------------------------------------------------


def sanitize_field(value: str, max_len: int = DEFAULT_FIELD_MAX_LEN) -> str:
    """Sanitize a single text field for inclusion in an AI prompt.

    Steps applied in order:
      1. Truncate to max_len characters.
      2. Scan for injection-like patterns; redact the entire field if found.

    Returns the sanitized string. Never raises.
    """
    if not value:
        return value

    truncated = value[:max_len]

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(truncated):
            return REDACTED_FIELD

    return truncated


# ---------------------------------------------------------------------------
# IP address detection and redaction
# ---------------------------------------------------------------------------


def contains_ip_pattern(text: str) -> bool:
    """Return True if text contains any IPv4 or IPv6 address-like pattern."""
    return bool(_IP_PATTERN.search(text))


def redact_ip_patterns(text: str) -> str:
    """Replace all IP address-like patterns in text with [IP REDACTED]."""
    return _IP_PATTERN.sub("[IP REDACTED]", text)


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------


def validate_ai_output(
    text: str,
    max_len: int = 1000,
) -> tuple[str | None, str | None]:
    """Validate AI-generated output text.

    Checks performed in order:
      1. Empty output → rejected.
      2. IP address present → rejected.
      3. Length exceeds max_len → truncated (text returned with reason).

    Returns:
        (text, None)            — output is valid and unmodified
        (truncated, "truncated") — output was cut to max_len but otherwise valid
        (None, "empty_response") — output was empty or whitespace-only
        (None, "ip_detected")   — output contained an IP address pattern
    """
    if not text or not text.strip():
        return None, "empty_response"

    if contains_ip_pattern(text):
        return None, "ip_detected"

    if len(text) > max_len:
        return text[:max_len], "truncated"

    return text, None


# ---------------------------------------------------------------------------
# Byte budget
# ---------------------------------------------------------------------------


def within_byte_budget(text: str, max_bytes: int) -> bool:
    """Return True if the UTF-8 byte length of text is within max_bytes."""
    return len(text.encode("utf-8")) <= max_bytes


def byte_length(text: str) -> int:
    """Return the UTF-8 byte length of text."""
    return len(text.encode("utf-8"))
