"""Unit tests for the AI backend abstraction layer.

Verifies:
  - Default backend is DisabledAIBackend (AI_BACKEND=none)
  - DisabledAIBackend raises AIDisabledError with a clear message
  - MockAIBackend returns configured responses without network calls
  - ClaudeAIBackend raises AIBackendError when anthropic is not installed
  - OllamaAIBackend raises the correct errors when httpx fails (monkeypatched)
  - get_ai_backend() factory selects the correct implementation
  - Settings validation rejects invalid AI_BACKEND values
  - No live network calls occur in any test
"""

from __future__ import annotations

import builtins

import pytest
from pydantic import ValidationError

from app.ai import (
    AIBackend,
    AIBackendError,
    AIBackendUnavailableError,
    AIDisabledError,
    ClaudeAIBackend,
    DisabledAIBackend,
    MockAIBackend,
    OllamaAIBackend,
    get_ai_backend,
)
from app.core.config import Settings, settings

_REQUIRED_FIELDS = {"API_KEY": "test-key", "FEED_SALT": "test-salt"}


# ---------------------------------------------------------------------------
# AIBackend ABC
# ---------------------------------------------------------------------------


def test_disabled_backend_is_ai_backend_instance():
    assert isinstance(DisabledAIBackend(), AIBackend)


def test_mock_backend_is_ai_backend_instance():
    assert isinstance(MockAIBackend(), AIBackend)


def test_claude_backend_is_ai_backend_instance():
    assert isinstance(ClaudeAIBackend(api_key="k", model="m"), AIBackend)


def test_ollama_backend_is_ai_backend_instance():
    assert isinstance(OllamaAIBackend(host="http://localhost:11434", model="llama3.2"), AIBackend)


# ---------------------------------------------------------------------------
# DisabledAIBackend
# ---------------------------------------------------------------------------


def test_disabled_backend_raises_ai_disabled_error():
    with pytest.raises(AIDisabledError):
        DisabledAIBackend().generate("any prompt")


def test_disabled_backend_error_message_mentions_enable():
    with pytest.raises(AIDisabledError, match="AI_BACKEND=claude or AI_BACKEND=ollama"):
        DisabledAIBackend().generate("prompt")


def test_disabled_backend_raises_regardless_of_prompt():
    backend = DisabledAIBackend()
    for prompt in ["", "hello", "x" * 1000]:
        with pytest.raises(AIDisabledError):
            backend.generate(prompt)


def test_disabled_backend_ai_disabled_error_is_ai_backend_error():
    """AIDisabledError is a subtype of AIError but callers may catch AIBackendError."""
    from app.ai import AIError

    with pytest.raises(AIError):
        DisabledAIBackend().generate("prompt")


# ---------------------------------------------------------------------------
# MockAIBackend
# ---------------------------------------------------------------------------


def test_mock_backend_returns_default_response():
    result = MockAIBackend().generate("any prompt")
    assert isinstance(result, str)
    assert len(result) > 0


def test_mock_backend_returns_configured_response():
    expected = "Campaign SWIFT-JACKAL-14 is actively scanning port 22."
    result = MockAIBackend(response=expected).generate("summarise campaign")
    assert result == expected


def test_mock_backend_returns_same_response_for_different_prompts():
    backend = MockAIBackend(response="fixed")
    assert backend.generate("prompt A") == "fixed"
    assert backend.generate("prompt B") == "fixed"


def test_mock_backend_does_not_raise():
    MockAIBackend().generate("test")


def test_mock_backend_empty_response_allowed():
    backend = MockAIBackend(response="")
    assert backend.generate("prompt") == ""


# ---------------------------------------------------------------------------
# ClaudeAIBackend — anthropic not installed
# ---------------------------------------------------------------------------


def test_claude_backend_can_be_instantiated():
    backend = ClaudeAIBackend(api_key="sk-test", model="claude-haiku-4-5-20251001")
    assert backend is not None


def test_claude_backend_raises_when_anthropic_missing(monkeypatch):
    """generate() raises AIBackendError with an install hint when anthropic is absent."""
    real_import = builtins.__import__

    def _block_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_anthropic)

    backend = ClaudeAIBackend(api_key="sk-test", model="claude-haiku-4-5-20251001")
    with pytest.raises(AIBackendError, match="anthropic package"):
        backend.generate("test prompt")


def test_claude_backend_stores_model():
    backend = ClaudeAIBackend(api_key="key", model="claude-sonnet-4-6")
    assert backend._model == "claude-sonnet-4-6"


def test_claude_backend_stores_timeout():
    backend = ClaudeAIBackend(api_key="key", model="m", timeout=15)
    assert backend._timeout == 15


# ---------------------------------------------------------------------------
# OllamaAIBackend — httpx is installed but we monkeypatch it
# ---------------------------------------------------------------------------


def test_ollama_backend_can_be_instantiated():
    backend = OllamaAIBackend(host="http://localhost:11434", model="llama3.2")
    assert backend is not None


def test_ollama_backend_strips_trailing_slash_from_host():
    backend = OllamaAIBackend(host="http://localhost:11434/", model="llama3.2")
    assert not backend._host.endswith("/")


def test_ollama_backend_raises_unavailable_on_connect_error(monkeypatch):
    import httpx

    def _connect_error(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "post", _connect_error)

    backend = OllamaAIBackend(host="http://localhost:11434", model="llama3.2")
    with pytest.raises(AIBackendUnavailableError, match="unreachable"):
        backend.generate("test prompt")


def test_ollama_backend_raises_backend_error_on_timeout(monkeypatch):
    import httpx

    def _timeout(*args, **kwargs):
        raise httpx.TimeoutException("Timed out")

    monkeypatch.setattr(httpx, "post", _timeout)

    backend = OllamaAIBackend(host="http://localhost:11434", model="llama3.2")
    with pytest.raises(AIBackendError, match="timed out"):
        backend.generate("test prompt")


def test_ollama_backend_raises_backend_error_on_http_error(monkeypatch):
    import httpx

    def _http_error(*args, **kwargs):
        response = httpx.Response(status_code=500)
        raise httpx.HTTPStatusError("server error", request=None, response=response)

    monkeypatch.setattr(httpx, "post", _http_error)

    backend = OllamaAIBackend(host="http://localhost:11434", model="llama3.2")
    with pytest.raises(AIBackendError, match="HTTP 500"):
        backend.generate("test prompt")


def test_ollama_backend_returns_response_field(monkeypatch):
    import httpx

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "Ollama says hello.", "done": True}

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse())

    backend = OllamaAIBackend(host="http://localhost:11434", model="llama3.2")
    result = backend.generate("prompt")
    assert result == "Ollama says hello."


def test_ollama_backend_raises_when_httpx_missing(monkeypatch):
    real_import = builtins.__import__

    def _block_httpx(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_httpx)

    backend = OllamaAIBackend(host="http://localhost:11434", model="llama3.2")
    with pytest.raises(AIBackendError, match="httpx package"):
        backend.generate("test prompt")


# ---------------------------------------------------------------------------
# get_ai_backend() factory
# ---------------------------------------------------------------------------


def test_get_ai_backend_default_returns_disabled():
    backend = get_ai_backend()
    assert isinstance(backend, DisabledAIBackend)


def test_get_ai_backend_default_settings_is_none():
    assert settings.AI_BACKEND == "none"


def test_get_ai_backend_none_backend_raises_on_generate():
    backend = get_ai_backend()
    with pytest.raises(AIDisabledError):
        backend.generate("prompt")


def test_get_ai_backend_ollama_returns_ollama_instance(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "ollama")
    backend = get_ai_backend()
    assert isinstance(backend, OllamaAIBackend)


def test_get_ai_backend_ollama_uses_ollama_host(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_HOST", "http://custom-host:11434")
    backend = get_ai_backend()
    assert "custom-host" in backend._host


def test_get_ai_backend_ollama_default_model(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "ollama")
    monkeypatch.setattr(settings, "AI_MODEL", None)
    backend = get_ai_backend()
    assert backend._model == "llama3.2"


def test_get_ai_backend_ollama_custom_model(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "ollama")
    monkeypatch.setattr(settings, "AI_MODEL", "mistral")
    backend = get_ai_backend()
    assert backend._model == "mistral"


def test_get_ai_backend_claude_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "claude")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    with pytest.raises(AIBackendError, match="ANTHROPIC_API_KEY"):
        get_ai_backend()


def test_get_ai_backend_claude_with_key_returns_claude_instance(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "claude")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test-key")
    backend = get_ai_backend()
    assert isinstance(backend, ClaudeAIBackend)


def test_get_ai_backend_claude_default_model(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "claude")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "AI_MODEL", None)
    backend = get_ai_backend()
    assert backend._model == "claude-haiku-4-5-20251001"


def test_get_ai_backend_claude_custom_model(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "claude")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setattr(settings, "AI_MODEL", "claude-sonnet-4-6")
    backend = get_ai_backend()
    assert backend._model == "claude-sonnet-4-6"


def test_get_ai_backend_uses_configured_timeout(monkeypatch):
    monkeypatch.setattr(settings, "AI_BACKEND", "ollama")
    monkeypatch.setattr(settings, "AI_TIMEOUT_SECONDS", 45)
    backend = get_ai_backend()
    assert backend._timeout == 45


# ---------------------------------------------------------------------------
# Settings validation — AI_BACKEND field
# ---------------------------------------------------------------------------


def test_settings_ai_backend_default_is_none():
    assert settings.AI_BACKEND == "none"


def test_settings_accepts_none_backend():
    s = Settings(**{**_REQUIRED_FIELDS, "AI_BACKEND": "none"})
    assert s.AI_BACKEND == "none"


def test_settings_accepts_ollama_backend():
    s = Settings(**{**_REQUIRED_FIELDS, "AI_BACKEND": "ollama"})
    assert s.AI_BACKEND == "ollama"


def test_settings_accepts_claude_backend():
    s = Settings(**{**_REQUIRED_FIELDS, "AI_BACKEND": "claude"})
    assert s.AI_BACKEND == "claude"


def test_settings_normalizes_ai_backend_to_lowercase():
    s = Settings(**{**_REQUIRED_FIELDS, "AI_BACKEND": "NONE"})
    assert s.AI_BACKEND == "none"


def test_settings_normalizes_claude_uppercase():
    s = Settings(**{**_REQUIRED_FIELDS, "AI_BACKEND": "Claude"})
    assert s.AI_BACKEND == "claude"


def test_settings_rejects_invalid_ai_backend():
    with pytest.raises(ValidationError, match="AI_BACKEND"):
        Settings(**{**_REQUIRED_FIELDS, "AI_BACKEND": "openai"})


def test_settings_rejects_empty_ai_backend():
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, "AI_BACKEND": ""})


def test_settings_rejects_arbitrary_ai_backend():
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, "AI_BACKEND": "gpt4"})


# ---------------------------------------------------------------------------
# Settings validation — AI timeout and rate limit
# ---------------------------------------------------------------------------


def test_settings_ai_timeout_default():
    assert settings.AI_TIMEOUT_SECONDS == 30


def test_settings_ai_max_requests_default():
    assert settings.AI_MAX_REQUESTS_PER_MINUTE == 10


def test_settings_rejects_zero_timeout():
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, "AI_TIMEOUT_SECONDS": 0})


def test_settings_rejects_negative_timeout():
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, "AI_TIMEOUT_SECONDS": -1})


def test_settings_rejects_zero_rate_limit():
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, "AI_MAX_REQUESTS_PER_MINUTE": 0})


def test_settings_accepts_valid_timeout():
    s = Settings(**{**_REQUIRED_FIELDS, "AI_TIMEOUT_SECONDS": 60})
    assert s.AI_TIMEOUT_SECONDS == 60


# ---------------------------------------------------------------------------
# Settings — other AI fields
# ---------------------------------------------------------------------------


def test_settings_anthropic_api_key_defaults_to_none():
    assert settings.ANTHROPIC_API_KEY is None


def test_settings_ollama_host_has_default():
    assert settings.OLLAMA_HOST == "http://localhost:11434"


def test_settings_ai_model_defaults_to_none():
    assert settings.AI_MODEL is None
