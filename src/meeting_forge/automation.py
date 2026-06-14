"""Modo automático opcional (F8): auto-aprobar y, opcionalmente, publicar con raíles de seguridad.

Desactivado por defecto. Cuando se activa, **solo** auto-aprueba los tipos de documento en la
allowlist (`AUTO_APPROVE_KINDS`, default `acta`), y la auto-publicación exige además
`AUTO_PUBLISH_ENABLED` + integración Git activada (con PRs borrador si `GIT_PR_DRAFT=true`).
Cada auto-aprobación queda marcada (`auto_approved=True`) y logueada para auditoría.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from .config import settings
from .generation.schemas import GeneratedDocument, GeneratedDocView, MeetingMetadata
from .validation import store


@dataclass
class AutoModeResult:
    """Resultado del modo automático (para logging/auditoría)."""

    auto_approved: list[str] = field(default_factory=list)
    published: bool = False
    pr_url: str = ""


def _to_views(docs: list[GeneratedDocument]) -> list[GeneratedDocView]:
    return [
        GeneratedDocView(
            filename=d.filename, kind=d.kind.value, markdown_content=d.markdown_content
        )
        for d in docs
    ]


def run_auto_mode(
    meeting_dir: Path,
    docs: list[GeneratedDocument],
    metadata: MeetingMetadata,
) -> AutoModeResult:
    """Aplica el modo automático si está activado. No-op si `AUTO_APPROVE_ENABLED=false`."""
    result = AutoModeResult()
    if not settings.auto_approve_enabled or not docs:
        return result

    views = _to_views(docs)
    state = store.initialize_pending(meeting_dir, views)
    approved = store.auto_approve(state, views, settings.auto_approve_kinds)
    store.save_state(meeting_dir, state)
    result.auto_approved = approved
    for name in approved:
        logger.info("Auto-aprobado [{m}]: {f} (kind en allowlist)", m=metadata.meeting_id, f=name)
    if not approved:
        return result

    if settings.auto_publish_enabled and settings.git_integration_enabled:
        from .git_integration import publisher

        try:
            pub = publisher.publish_meeting(meeting_dir, metadata, state, views)
            result.published = True
            result.pr_url = pub.pr_url or pub.compare_url
            logger.info(
                "Auto-publicado: rama {b} · {p}", b=pub.branch, p=result.pr_url or "(sin PR)"
            )
        except publisher.PublishError as exc:
            logger.error("Auto-publicación fallida: {e}", e=exc)

    return result
