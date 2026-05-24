"""Configuración global de la aplicación usando Pydantic Settings."""

from pathlib import Path
from typing import Any, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings cargadas desde variables de entorno y `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Paths ---
    project_root: Path = Path(__file__).parent.parent.parent
    data_dir: Path = project_root / "data"
    prompts_dir: Path = project_root / "prompts"

    # --- Whisper ---
    whisper_model_size: Literal["tiny", "base", "small", "medium", "large-v3"] = "medium"
    whisper_device: Literal["cpu", "cuda", "auto"] = "auto"
    whisper_compute_type: Literal["int8", "float16", "float32"] = "int8"

    # --- LLM Provider ---
    llm_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # --- Modelos ---
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o-2024-08-06"
    ollama_model: str = "llama3.1:8b"

    # --- Logging ---
    log_level: str = "INFO"

    def model_post_init(self, __context: Any) -> None:
        """Crea los directorios de datos si no existen."""
        for sub in ("raw", "transcripts", "outputs"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


settings = Settings()
