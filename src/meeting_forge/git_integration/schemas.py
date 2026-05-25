"""Esquemas Pydantic para la publicación Git (Fase 4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PublishRequest(BaseModel):
    """Datos necesarios para publicar documentos en un repo Git."""

    meeting_id: str
    branch_name: str
    commit_message: str
    pr_title: str
    pr_body: str
    docs_subdir: str = Field(description="Subdirectorio dentro del repo destino")
    files: list[tuple[str, str]] = Field(
        description="Lista de (ruta_relativa_en_repo, contenido_markdown)"
    )


class PublishResult(BaseModel):
    """Resultado de una publicación exitosa."""

    branch: str
    commit_sha: str
    pr_url: str
    published_at: datetime
    files: list[str] = Field(description="Rutas relativas de archivos publicados en el repo")
