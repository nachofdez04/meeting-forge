"""Comprobaciones de prerequisitos compartidas por el CLI (`check`) y la UI (UX-18).

Cada check devuelve un `CheckResult` con el estado, un detalle legible y —si falla— el remedio
accionable en una línea. Así el usuario descubre lo que falta ANTES de lanzar un run, no por un
error a mitad de proceso.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass

from .config import settings
from .git_integration.pr import is_gh_authenticated, is_gh_available


@dataclass
class CheckResult:
    """Resultado de una comprobación de prerequisito."""

    name: str
    ok: bool
    detail: str
    remedy: str = ""


def check_llm_key() -> CheckResult:
    """Comprueba la API key del proveedor LLM **activo** (ollama no necesita ninguna)."""
    provider = settings.llm_provider
    if provider == "ollama":
        return CheckResult("API key LLM", True, "no requerida (ollama)")
    key = settings.anthropic_api_key if provider == "anthropic" else settings.openai_api_key
    if key:
        return CheckResult("API key LLM", True, f"configurada ({provider})")
    var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
    return CheckResult(
        "API key LLM",
        False,
        f"falta la clave de {provider}",
        f"Define {var} en .env (o cambia LLM_PROVIDER)",
    )


def check_ffmpeg() -> CheckResult:
    """ffmpeg es necesario para transcribir (faster-whisper) y extraer audio de vídeos."""
    if shutil.which("ffmpeg"):
        return CheckResult("ffmpeg", True, "disponible")
    return CheckResult(
        "ffmpeg",
        False,
        "no encontrado",
        "Instálalo y añádelo al PATH (necesario para transcribir)",
    )


def check_gh() -> CheckResult:
    """gh CLI instalado y autenticado (solo relevante con la integración Git activada)."""
    if not is_gh_available(settings.gh_executable):
        return CheckResult(
            "gh CLI", False, "no disponible", "Instala GitHub CLI para crear Pull Requests"
        )
    if not is_gh_authenticated(settings.gh_executable):
        return CheckResult("gh CLI", False, "sin autenticar", "Ejecuta `gh auth login`")
    return CheckResult("gh CLI", True, "autenticado")


def check_rag_index(count: Callable[[], int] | None = None) -> CheckResult:
    """Comprueba que el índice RAG tiene chunks. `count` es inyectable para tests."""
    try:
        if count is None:
            from .rag.vector_store import ChromaVectorStore  # import perezoso (dependencia pesada)

            count = ChromaVectorStore().count
        n = count()
    except Exception as exc:
        return CheckResult(
            "Índice RAG", False, f"no accesible: {exc}", "Ejecuta `meeting-forge index`"
        )
    if n == 0:
        return CheckResult(
            "Índice RAG",
            False,
            "vacío",
            "Ejecuta `meeting-forge index` (o desactiva RAG en el panel)",
        )
    return CheckResult("Índice RAG", True, f"{n} chunks indexados")
