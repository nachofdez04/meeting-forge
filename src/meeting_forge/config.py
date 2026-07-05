"""Configuración global de la aplicación usando Pydantic Settings."""

import sys
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import field_validator, model_validator
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
    # Idioma del audio (None = autodetección de faster-whisper)
    whisper_language: str | None = None
    # Texto que condiciona el vocabulario de Whisper (UX-1): términos técnicos y nombres propios
    # del proyecto que Whisper suele transcribir mal. Se combina con `data/glossary.txt` (un
    # término por línea, `#` comenta) y con el vocabulario puntual pasado por la UI/CLI.
    whisper_initial_prompt: str = ""
    # Preprocesado opcional del audio con ffmpeg (mono + 16 kHz + loudnorm) antes de transcribir · F9
    audio_preprocess_enabled: bool = False
    # Diarización opcional de hablantes con pyannote.audio (M7). Desactivada por defecto: requiere el
    # grupo `diarization` (uv sync --group diarization) y un token de Hugging Face con la licencia del
    # modelo aceptada. Tolerante a fallos: si algo falla, se transcribe sin speakers.
    diarization_enabled: bool = False
    huggingface_token: str = ""
    diarization_model: str = "pyannote/speaker-diarization-3.1"

    # --- LLM Provider ---
    llm_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    # Reintentos ante errores transitorios del LLM (rate limit, timeout, 5xx) · F12
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0

    # --- Modelos ---
    # claude-sonnet-4-20250514 se retiró el 2026-06-15; el reemplazo drop-in es claude-sonnet-4-6
    # (mismo nivel de coste). Mantén el ID sincronizado con la tabla de precios de observability.py.
    anthropic_model: str = "claude-sonnet-4-6"
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
    # Umbral mínimo de score [0,1] para conservar un chunk recuperado (0.0 = sin filtro) · M2/F6.
    # El score ya está clampeado a [0,1] en el vector store (B8); subirlo descarta chunks poco afines.
    retrieval_min_score: float = 0.0
    chunk_max_chars: int = 1500
    chunk_overlap_chars: int = 200
    transcript_query_chars: int = 500
    context_max_chars: int = 8000
    # Búsqueda entre reuniones (UX-8): indexa cada reunión procesada en una colección separada.
    search_index_enabled: bool = True
    # Memoria RAG (UX-9): indexa las actas/ADRs aprobados en el corpus para que las reuniones
    # futuras puedan citarlos. Se ejecuta como paso best-effort tras publicar/auto-aprobar.
    rag_index_generated_docs: bool = True

    # --- Generation (Fase 2) ---
    generation_enabled: bool = True
    generation_modes: list[str] = ["adr-per-decision", "acta"]
    adr_prompt_version: str = "v1"
    generation_max_tokens: int = 4000
    # Documentos existentes a actualizar en los modos roadmap-update / technical-doc-update (F5).
    # Si se definen y existen, el pipeline propone un diff sobre ellos; si no, crea uno nuevo.
    roadmap_path: Path | None = None
    tech_doc_path: Path | None = None

    # --- Automatización opcional (Fase C · F8) ---
    # Desactivado por defecto: con HITL el usuario aprueba a mano. Si se activa, solo se auto-aprueban
    # los tipos en `auto_approve_kinds` (default: solo actas, que son determinísticas).
    auto_approve_enabled: bool = False
    auto_approve_kinds: list[str] = ["acta"]
    auto_publish_enabled: bool = False

    @model_validator(mode="after")
    def _derive_dependent_paths(self) -> "Settings":
        """Recalcula los paths derivados cuando su base se sobreescribe por entorno.

        Los defaults a nivel de clase (`data_dir = project_root / "data"`, etc.) se evalúan una
        sola vez con los valores por defecto: si el usuario define PROJECT_ROOT o DATA_DIR, los
        derivados no explícitamente configurados deben seguir a su base (si no, Chroma escribiría
        fuera del data_dir configurado).
        """
        explicit = self.model_fields_set
        if "data_dir" not in explicit:
            self.data_dir = self.project_root / "data"
        if "prompts_dir" not in explicit:
            self.prompts_dir = self.project_root / "prompts"
        if "chromadb_path" not in explicit:
            self.chromadb_path = self.data_dir / "chromadb"
        return self

    @field_validator("generation_modes", "auto_approve_kinds", mode="before")
    @classmethod
    def _parse_csv_or_json_list(cls, v: object) -> list[str]:
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
    git_pr_draft: bool = False  # crea los PR como borrador (raíl para el modo automático · F8)

    # --- Logging ---
    log_level: str = "INFO"


settings = Settings()

_logging_configured = False


def configure_logging() -> None:
    """Aplica `settings.log_level` a loguru. Idempotente (no duplica handlers).

    loguru no se configura solo: su handler por defecto emite todo a `stderr` ignorando
    `LOG_LEVEL`. Los entrypoints (CLI, pipeline, UI) llaman a esta función para que la variable
    de entorno tenga efecto real.
    """
    global _logging_configured
    if _logging_configured:
        return
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level.upper())
    _logging_configured = True


def ensure_data_dirs() -> None:
    """Crea los directorios de datos/índice si no existen.

    Se invoca explícitamente desde los entrypoints (CLI/pipeline) en lugar de en `model_post_init`,
    para que **importar el paquete no tenga efectos en el sistema de ficheros** (TD2).
    """
    for sub in ("raw", "transcripts", "outputs"):
        (settings.data_dir / sub).mkdir(parents=True, exist_ok=True)
    settings.chromadb_path.mkdir(parents=True, exist_ok=True)
