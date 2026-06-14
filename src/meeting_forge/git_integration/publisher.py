"""Orquestador de publicación: validation state → commit + PR en repo destino (Fase 4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from ..config import settings
from ..generation.schemas import GeneratedDocView, MeetingMetadata
from ..validation.schemas import MeetingValidationState
from ..validation.store import get_effective_content
from . import pr as pr_module
from . import repo as repo_module
from .schemas import PublishRequest, PublishResult
from .templates import build_branch_name, build_commit_message, build_pr_body, build_pr_title

_PUBLISH_FILENAME = "publish.json"


class PublishError(RuntimeError):
    """Error durante la publicación. Incluye contexto diagnóstico."""


def _build_request(
    metadata: MeetingMetadata,
    validation_state: MeetingValidationState,
    docs: list[GeneratedDocView],
) -> PublishRequest:
    """Construye el PublishRequest con los documentos aprobados y sus contenidos efectivos."""
    approved = {r.filename for r in validation_state.approved_records()}
    files: list[tuple[str, str]] = []
    for doc in docs:
        if doc.filename not in approved:
            continue
        content = get_effective_content(validation_state, doc.filename, doc.markdown_content)
        rel_path = f"{settings.git_docs_subdir}/{metadata.meeting_id}/{doc.kind}/{doc.filename}"
        files.append((rel_path, content))

    if not files:
        raise PublishError("No hay documentos aprobados para publicar.")

    branch = build_branch_name(
        prefix=settings.git_branch_prefix,
        meeting_id=metadata.meeting_id,
        date=metadata.date,
    )
    commit_msg = build_commit_message(
        title=metadata.title or metadata.meeting_id, n_docs=len(files)
    )
    pr_title = build_pr_title(
        meeting_title=metadata.title or metadata.meeting_id, n_docs=len(files)
    )
    pr_body = build_pr_body(
        meeting_id=metadata.meeting_id,
        date=metadata.date,
        files=[f for f, _ in files],
    )
    return PublishRequest(
        meeting_id=metadata.meeting_id,
        branch_name=branch,
        commit_message=commit_msg,
        pr_title=pr_title,
        pr_body=pr_body,
        docs_subdir=settings.git_docs_subdir,
        files=files,
    )


def publish_meeting(
    meeting_dir: Path,
    metadata: MeetingMetadata,
    validation_state: MeetingValidationState,
    docs: list[GeneratedDocView],
) -> PublishResult:
    """Publica los documentos aprobados en el repo destino y crea un PR.

    Pasos:
      1. Valida configuración y construye PublishRequest.
      2. Asegura el repo destino (clone o validación).
      3. Checkout base branch + pull.
      4. Crea rama de trabajo.
      5. Escribe archivos + commit.
      6. Push.
      7. Crea PR con gh.
      8. Escribe publish.json en meeting_dir.
    """
    if not settings.git_integration_enabled:
        raise PublishError(
            "La integración Git está desactivada. Actívala con GIT_INTEGRATION_ENABLED=true en .env"
        )
    if not settings.git_target_repo_path:
        raise PublishError(
            "No hay repositorio destino configurado. Define GIT_TARGET_REPO_PATH en .env"
        )

    target_repo = Path(settings.git_target_repo_path)
    request = _build_request(metadata, validation_state, docs)

    logger.info(
        "Publicando {n} docs de '{meeting}' en {repo}",
        n=len(request.files),
        meeting=metadata.meeting_id,
        repo=target_repo,
    )

    try:
        repo_module.ensure_repo(target_repo, remote=settings.git_target_remote)
        repo_module.ensure_clean(target_repo)
        repo_module.checkout_branch(target_repo, settings.git_base_branch)
        repo_module.pull(target_repo)
        repo_module.checkout_branch(target_repo, request.branch_name, base=settings.git_base_branch)
        written = repo_module.write_files(target_repo, request.files)
        commit_sha = repo_module.add_and_commit(target_repo, written, request.commit_message)
        logger.info("Commit creado: {sha}", sha=commit_sha)
        repo_module.push(target_repo, request.branch_name)
        logger.info("Push completado: {branch}", branch=request.branch_name)
    except repo_module.GitOperationError as exc:
        raise PublishError(f"Error en operación git: {exc}") from exc

    compare_url = ""
    try:
        pr_url = pr_module.create_pr(
            repo_path=target_repo,
            branch=request.branch_name,
            title=request.pr_title,
            body=request.pr_body,
            base=settings.git_base_branch,
            gh_executable=settings.gh_executable,
            draft=settings.git_pr_draft,
        )
        logger.info("PR creado: {url}", url=pr_url)
    except pr_module.PrCreationError as exc:
        logger.warning(
            "No se pudo crear el PR automáticamente: {e}. El commit y push sí se completaron.",
            e=exc,
        )
        pr_url = ""
        # F7: ofrece una URL de 'compare' para abrir el PR a mano cuando gh falla o no está.
        remote_url = repo_module.get_remote_url(target_repo)
        if remote_url:
            compare_url = (
                pr_module.build_compare_url(
                    remote_url, settings.git_base_branch, request.branch_name
                )
                or ""
            )
        if compare_url:
            logger.info("Abre el PR manualmente en: {u}", u=compare_url)

    result = PublishResult(
        branch=request.branch_name,
        commit_sha=commit_sha,
        pr_url=pr_url,
        published_at=datetime.now(tz=UTC),
        files=[f for f, _ in request.files],
        compare_url=compare_url,
    )
    _write_publish_result(meeting_dir, result)
    return result


def _write_publish_result(meeting_dir: Path, result: PublishResult) -> None:
    meeting_dir.mkdir(parents=True, exist_ok=True)
    (meeting_dir / _PUBLISH_FILENAME).write_text(result.model_dump_json(indent=2), encoding="utf-8")


def load_publish_result(meeting_dir: Path) -> PublishResult | None:
    """Lee publish.json si existe; devuelve None en caso contrario."""
    path = meeting_dir / _PUBLISH_FILENAME
    if not path.exists():
        return None
    try:
        return PublishResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("publish.json ilegible en {p}: {e}", p=path, e=exc)
        return None
