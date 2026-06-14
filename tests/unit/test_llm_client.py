"""Tests de utilidades puras del cliente LLM (sin red ni API keys)."""

from __future__ import annotations

import pytest

from meeting_forge.analysis import llm_client
from meeting_forge.analysis.llm_client import (
    OllamaProvider,
    _strip_markdown_fences,
    get_provider,
)


class TestGetProvider:
    def test_ollama_provider_selected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # B6: 'ollama' ya no lanza; devuelve un OllamaProvider (cliente compatible-OpenAI).
        monkeypatch.setattr(llm_client.settings, "llm_provider", "ollama")
        provider = get_provider()
        assert isinstance(provider, OllamaProvider)
        assert provider.model  # tomado de settings.ollama_model

    def test_unknown_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(llm_client.settings, "llm_provider", "desconocido")
        with pytest.raises(ValueError, match="Proveedor desconocido"):
            get_provider()


class TestStripMarkdownFences:
    def test_plain_json_unchanged(self) -> None:
        assert _strip_markdown_fences('{"a": 1}') == '{"a": 1}'

    def test_strips_json_fence(self) -> None:
        assert _strip_markdown_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_bare_fence(self) -> None:
        assert _strip_markdown_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_strips_with_surrounding_whitespace(self) -> None:
        assert _strip_markdown_fences('   ```json\n{"a": 1}\n```   ') == '{"a": 1}'


class _Transient(Exception):
    """Error transitorio de prueba para el helper de reintentos."""


class TestApiKeyValidation:
    def test_anthropic_requires_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(llm_client.settings, "anthropic_api_key", "")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            llm_client.AnthropicProvider()

    def test_openai_requires_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(llm_client.settings, "openai_api_key", "")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            llm_client.OpenAIProvider()


class TestWithRetries:
    def test_succeeds_after_transient_failures(self) -> None:
        attempts = {"n": 0}

        def _call() -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise _Transient("flaky")
            return "ok"

        result = llm_client._with_retries(_call, retries=3, base_delay=0.0, retryable=(_Transient,))
        assert result == "ok"
        assert attempts["n"] == 3

    def test_reraises_after_exhaustion(self) -> None:
        def _call() -> str:
            raise _Transient("always")

        with pytest.raises(_Transient):
            llm_client._with_retries(_call, retries=2, base_delay=0.0, retryable=(_Transient,))

    def test_does_not_retry_non_retryable(self) -> None:
        attempts = {"n": 0}

        def _call() -> str:
            attempts["n"] += 1
            raise ValueError("permanent")

        with pytest.raises(ValueError, match="permanent"):
            llm_client._with_retries(_call, retries=3, base_delay=0.0, retryable=(KeyError,))
        assert attempts["n"] == 1
