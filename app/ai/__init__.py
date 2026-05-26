"""app.ai — AI backend abstraction for Phase 5.

Public API exported here. Callers should import from app.ai, not submodules.

Example usage:

    from app.ai import get_ai_backend, AIDisabledError, MockAIBackend
    from app.ai import build_campaign_summary_prompt, sanitize_field

    # Production use:
    backend = get_ai_backend()
    text = backend.generate(prompt)

    # Test use:
    backend = MockAIBackend(response="Campaign X is active.")
    text = backend.generate(prompt)
"""

from app.ai.backend import (
    AIBackend,
    AIBackendError,
    AIBackendUnavailableError,
    AIDisabledError,
    AIError,
    ClaudeAIBackend,
    DisabledAIBackend,
    MockAIBackend,
    OllamaAIBackend,
    get_ai_backend,
)
from app.ai.prompt_builder import (
    BRIEF_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_brief_prompt,
    build_campaign_summary_prompt,
    format_fingerprint_summary,
)
from app.ai.safety import (
    REDACTED_FIELD,
    byte_length,
    contains_ip_pattern,
    redact_ip_patterns,
    sanitize_field,
    validate_ai_output,
    within_byte_budget,
)

__all__ = [
    # Backend
    "AIBackend",
    "AIError",
    "AIDisabledError",
    "AIBackendError",
    "AIBackendUnavailableError",
    "DisabledAIBackend",
    "MockAIBackend",
    "ClaudeAIBackend",
    "OllamaAIBackend",
    "get_ai_backend",
    # Prompt builder
    "SYSTEM_PROMPT",
    "BRIEF_SYSTEM_PROMPT",
    "build_campaign_summary_prompt",
    "build_brief_prompt",
    "format_fingerprint_summary",
    # Safety
    "REDACTED_FIELD",
    "sanitize_field",
    "contains_ip_pattern",
    "redact_ip_patterns",
    "validate_ai_output",
    "within_byte_budget",
    "byte_length",
]
