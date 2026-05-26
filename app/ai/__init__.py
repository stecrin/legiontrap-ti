"""app.ai — AI backend abstraction for Phase 5.

Public API exported here. Callers should import from app.ai, not app.ai.backend.

Example usage (future Phase 5 Group B PRs):

    from app.ai import get_ai_backend, AIDisabledError, MockAIBackend

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

__all__ = [
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
]
