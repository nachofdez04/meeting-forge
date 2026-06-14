"""Tests para Settings y configuración global."""

from pathlib import Path

import pytest

from meeting_forge.config import Settings, ensure_data_dirs, settings


def test_settings_defaults() -> None:
    """Los defaults deben coincidir con los declarados en Settings."""
    s = Settings()
    assert s.whisper_model_size == "medium"
    assert s.whisper_device == "auto"
    assert s.whisper_compute_type == "int8"
    assert s.llm_provider == "anthropic"
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.log_level == "INFO"
    # TD2: instanciar Settings no debe tener efectos en el sistema de ficheros.
    assert s.whisper_language is None


def test_ensure_data_dirs_creates_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ensure_data_dirs() crea data/{raw,transcripts,outputs} + chromadb (TD2)."""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "chromadb_path", tmp_path / "data" / "chromadb")
    ensure_data_dirs()
    assert (tmp_path / "data" / "raw").exists()
    assert (tmp_path / "data" / "transcripts").exists()
    assert (tmp_path / "data" / "outputs").exists()
    assert (tmp_path / "data" / "chromadb").exists()


def test_settings_prompts_dir_path() -> None:
    """prompts_dir debe apuntar a la carpeta prompts/ del repo."""
    assert settings.prompts_dir.name == "prompts"
