"""Tests de las comprobaciones de prerequisitos compartidas CLI/UI (UX-18)."""

from __future__ import annotations

import pytest

from meeting_forge import system_status
from meeting_forge.system_status import (
    check_ffmpeg,
    check_gh,
    check_llm_key,
    check_rag_index,
)


class TestCheckLlmKey:
    def test_ollama_needs_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_status.settings, "llm_provider", "ollama")
        result = check_llm_key()
        assert result.ok is True
        assert "ollama" in result.detail

    def test_anthropic_without_key_fails_with_remedy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_status.settings, "llm_provider", "anthropic")
        monkeypatch.setattr(system_status.settings, "anthropic_api_key", "")
        result = check_llm_key()
        assert result.ok is False
        assert "ANTHROPIC_API_KEY" in result.remedy

    def test_openai_with_key_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_status.settings, "llm_provider", "openai")
        monkeypatch.setattr(system_status.settings, "openai_api_key", "sk-test")
        assert check_llm_key().ok is True

    def test_active_provider_key_is_the_one_checked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Tener la clave del proveedor NO activo no cuenta.
        monkeypatch.setattr(system_status.settings, "llm_provider", "anthropic")
        monkeypatch.setattr(system_status.settings, "anthropic_api_key", "")
        monkeypatch.setattr(system_status.settings, "openai_api_key", "sk-test")
        assert check_llm_key().ok is False


class TestCheckFfmpeg:
    def test_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_status.shutil, "which", lambda _: "/usr/bin/ffmpeg")
        assert check_ffmpeg().ok is True

    def test_missing_has_remedy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_status.shutil, "which", lambda _: None)
        result = check_ffmpeg()
        assert result.ok is False
        assert result.remedy


class TestCheckGh:
    def test_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_status, "is_gh_available", lambda _: False)
        result = check_gh()
        assert result.ok is False
        assert "no disponible" in result.detail

    def test_installed_but_not_authenticated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_status, "is_gh_available", lambda _: True)
        monkeypatch.setattr(system_status, "is_gh_authenticated", lambda _: False)
        result = check_gh()
        assert result.ok is False
        assert "gh auth login" in result.remedy

    def test_authenticated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_status, "is_gh_available", lambda _: True)
        monkeypatch.setattr(system_status, "is_gh_authenticated", lambda _: True)
        assert check_gh().ok is True


class TestCheckRagIndex:
    def test_empty_index_fails(self) -> None:
        result = check_rag_index(count=lambda: 0)
        assert result.ok is False
        assert "meeting-forge index" in result.remedy

    def test_populated_index_ok(self) -> None:
        result = check_rag_index(count=lambda: 42)
        assert result.ok is True
        assert "42" in result.detail

    def test_inaccessible_store_fails_gracefully(self) -> None:
        def _boom() -> int:
            raise RuntimeError("chroma roto")

        result = check_rag_index(count=_boom)
        assert result.ok is False
        assert "chroma roto" in result.detail
