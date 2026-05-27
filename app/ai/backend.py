"""AI backend abstraction layer for Phase 5.

Provides a uniform generate(prompt) → str interface over multiple AI backends.
The active backend is selected at startup via the AI_BACKEND setting:

  AI_BACKEND=none    → DisabledAIBackend (default; raises AIDisabledError)
  AI_BACKEND=ollama  → OllamaAIBackend (local inference; no data leaves system)
  AI_BACKEND=claude  → ClaudeAIBackend (cloud; requires ANTHROPIC_API_KEY)

Rules enforced here (Phase 5 §3, §12):
  - No AI backend is ever called from the ingest path.
  - No AI backend writes to the database.
  - No AI backend calls external URLs except the configured AI endpoint.
  - External SDK imports (anthropic, httpx) are lazy so startup is never
    blocked by a missing optional dependency.

MockAIBackend is provided for dependency injection in tests. It must never be
instantiated in production code.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AIError(Exception):
    """Base class for all AI backend errors."""


class AIDisabledError(AIError):
    """Raised when AI_BACKEND=none and generate() is called."""


class AIBackendError(AIError):
    """Raised on backend configuration, connectivity, or runtime failures."""


class AIBackendUnavailableError(AIBackendError):
    """Raised when the configured backend is reachable but currently offline.

    Distinct from AIBackendError so callers can return HTTP 503 vs HTTP 500.
    """


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class AIBackend(abc.ABC):
    """Uniform interface for all AI backends.

    Subclasses must implement generate(). All implementations must be
    stateless with respect to the database — they read a prompt string
    and return a response string, with no side effects.
    """

    @property
    def model_name(self) -> str:
        """The specific model identifier used by this backend instance."""
        return "unknown"

    @abc.abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a response for the given prompt.

        Raises:
            AIDisabledError: if AI features are disabled (DisabledAIBackend).
            AIBackendUnavailableError: if the backend is offline.
            AIBackendError: for all other backend failures.
        """


# ---------------------------------------------------------------------------
# DisabledAIBackend
# ---------------------------------------------------------------------------


class DisabledAIBackend(AIBackend):
    """Backend used when AI_BACKEND=none.

    generate() always raises AIDisabledError with a clear message. This is
    the default backend and the safe fallback for misconfigured deployments.
    """

    @property
    def model_name(self) -> str:
        return "none"

    def generate(self, prompt: str) -> str:
        raise AIDisabledError(
            "AI features are disabled. " "Set AI_BACKEND=claude or AI_BACKEND=ollama to enable."
        )


# ---------------------------------------------------------------------------
# MockAIBackend (tests only)
# ---------------------------------------------------------------------------


class MockAIBackend(AIBackend):
    """Deterministic AI backend for dependency injection in tests.

    Returns a fixed response string on every generate() call.
    Never makes network calls. Must not be used in production code.
    """

    def __init__(self, response: str = "Mock AI response.") -> None:
        self._response = response

    @property
    def model_name(self) -> str:
        return "mock"

    def generate(self, prompt: str) -> str:
        return self._response


# ---------------------------------------------------------------------------
# OllamaAIBackend
# ---------------------------------------------------------------------------


class OllamaAIBackend(AIBackend):
    """Backend for local Ollama inference.

    Calls the Ollama REST API at OLLAMA_HOST. No data leaves the system.
    httpx is imported lazily so startup is not blocked if httpx is absent.
    """

    def __init__(self, host: str, model: str, timeout: int = 30) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, prompt: str) -> str:
        try:
            import httpx
        except ImportError as exc:
            raise AIBackendError("httpx package is not installed. Run: pip install httpx") from exc

        url = f"{self._host}/api/generate"
        try:
            response = httpx.post(
                url,
                json={"model": self._model, "prompt": prompt, "stream": False},
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()["response"]
        except httpx.ConnectError as exc:
            raise AIBackendUnavailableError(
                f"Ollama unreachable at {self._host}. "
                "Ensure Ollama is running and OLLAMA_HOST is correct."
            ) from exc
        except httpx.TimeoutException as exc:
            raise AIBackendError(f"Ollama request timed out after {self._timeout}s.") from exc
        except httpx.HTTPStatusError as exc:
            raise AIBackendError(f"Ollama returned HTTP {exc.response.status_code}.") from exc


# ---------------------------------------------------------------------------
# ClaudeAIBackend
# ---------------------------------------------------------------------------


class ClaudeAIBackend(AIBackend):
    """Backend for Anthropic Claude API (cloud).

    anthropic SDK is imported lazily so startup is not blocked if the package
    is absent. All requests to this backend send data to Anthropic's servers;
    use DisabledAIBackend or OllamaAIBackend when PRIVACY_MODE=on.
    """

    def __init__(self, api_key: str, model: str, timeout: int = 30) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, prompt: str) -> str:
        try:
            import anthropic
        except ImportError as exc:
            raise AIBackendError(
                "anthropic package is not installed. Run: pip install anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
                timeout=self._timeout,
            )
            return message.content[0].text
        except anthropic.APITimeoutError as exc:
            raise AIBackendError(f"Claude API timed out after {self._timeout}s.") from exc
        except anthropic.APIConnectionError as exc:
            raise AIBackendUnavailableError(
                "Claude API unreachable. Check network connectivity."
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise AIBackendError(
                "Claude API authentication failed. Check ANTHROPIC_API_KEY."
            ) from exc
        except anthropic.APIError as exc:
            raise AIBackendError(f"Claude API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_ai_backend() -> AIBackend:
    """Create and return the configured AI backend instance.

    Reads AI_BACKEND from settings. Raises AIBackendError if the configuration
    is insufficient for the chosen backend (e.g. AI_BACKEND=claude with no key).

    Returns:
        DisabledAIBackend  when AI_BACKEND=none (default)
        OllamaAIBackend    when AI_BACKEND=ollama
        ClaudeAIBackend    when AI_BACKEND=claude
    """
    from app.core.config import settings

    backend = settings.AI_BACKEND

    if backend == "none":
        return DisabledAIBackend()

    if backend == "claude":
        if not settings.ANTHROPIC_API_KEY:
            raise AIBackendError(
                "AI_BACKEND=claude requires ANTHROPIC_API_KEY to be set in the environment."
            )
        model = settings.AI_MODEL or "claude-haiku-4-5-20251001"
        return ClaudeAIBackend(
            api_key=settings.ANTHROPIC_API_KEY,
            model=model,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )

    if backend == "ollama":
        model = settings.AI_MODEL or "llama3.2"
        return OllamaAIBackend(
            host=settings.OLLAMA_HOST,
            model=model,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )

    # Unreachable when settings validation is working; defensive fallback.
    raise AIBackendError(f"Unrecognized AI_BACKEND: {backend!r}. Must be none, claude, or ollama.")
