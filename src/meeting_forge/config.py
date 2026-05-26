"""Configuración global de la aplicación usando Pydantic Settings."""

from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator
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

    # --- RAG ---
    rag_enabled: bool = True
    docs_path: Path | None = None
    chromadb_path: Path = data_dir / "chromadb"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chroma_collection: str = "meeting_forge_docs"
    retrieval_top_k: int = 5
    retrieval_per_query_k: int = 3
    chunk_max_chars: int = 1500
    chunk_overlap_chars: int = 200
    transcript_query_chars: int = 500
    context_max_chars: int = 8000

    # --- Generation (Fase 2) ---
    generation_enabled: bool = True
    generation_modes: list[str] = ["adr-per-decision", "acta"]
    adr_prompt_version: str = "v1"
    generation_max_tokens: int = 4000

    @field_validator("generation_modes", mode="before")
    @classmethod
    def _parse_generation_modes(cls, v: object) -> list[str]:
        """Acepta CSV ("adr-per-decision,acta") o lista JSON ("[\\"adr-per-decision\\"]")."""
        if isinstance(v, list):
            return [str(item) for item in v]
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                result: list[str] = json.loads(v)
                return result
            return [item.strip() for item in v.split(",") if item.strip()]
        return []

    # --- Git Integration (Fase 4) ---
    git_integration_enabled: bool = False
    git_target_repo_path: Path | None = None
    git_target_remote: str | None = None
    git_docs_subdir: str = "docs/meetings"
    git_base_branch: str = "main"
    git_branch_prefix: str = "meeting-forge/"
    gh_executable: str = "gh"

    # --- Logging ---
    log_level: str = "INFO"

    def model_post_init(self, __context: Any) -> None:
        """Crea los directorios de datos si no existen."""
        for sub in ("raw", "transcripts", "outputs"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)
        self.chromadb_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
