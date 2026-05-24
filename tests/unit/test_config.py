"""Tests para Settings y configuración global."""

from meeting_forge.config import Settings, settings


def test_settings_defaults() -> None:
    """Los defaults deben coincidir con los declarados en Settings."""
    s = Settings()
    assert s.whisper_model_size == "medium"
    assert s.whisper_device == "auto"
    assert s.whisper_compute_type == "int8"
    assert s.llm_provider == "anthropic"
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.log_level == "INFO"


def test_settings_creates_data_directories() -> None:
    """model_post_init debe crear data/{raw,transcripts,outputs}."""
    assert settings.data_dir.exists()
    assert (settings.data_dir / "raw").exists()
    assert (settings.data_dir / "transcripts").exists()
    assert (settings.data_dir / "outputs").exists()


def test_settings_prompts_dir_path() -> None:
    """prompts_dir debe apuntar a la carpeta prompts/ del repo."""
    assert settings.prompts_dir.name == "prompts"
