"""Orchestrate WordPress draft export for approved runs; persist export journal."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from harness.models.run import PipelineRun
from harness.schemas.pipeline import RunStatus
from harness.schemas.wordpress_export import (
    WordPressExportAttempt,
    WordPressExportAttemptStatus,
    WordPressExportJournal,
)
from harness.services import brand_loader
from harness.services.approval_service import review_package_from_run
from harness.services.wordpress import (
    WordPressConfigError,
    create_draft_post,
    draft_payload_from_state,
    resolve_wordpress_credentials,
)

log = structlog.get_logger(__name__)


class WordPressExportServiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def load_export_journal(run: PipelineRun) -> WordPressExportJournal:
    if not run.wordpress_result_json:
        return WordPressExportJournal()
    try:
        data = json.loads(run.wordpress_result_json)
        return WordPressExportJournal.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        log.warning("wordpress.journal.parse_failed", run_id=str(run.id))
        return WordPressExportJournal()


def _save_journal(session: AsyncSession, run: PipelineRun, journal: WordPressExportJournal) -> None:
    run.wordpress_result_json = json.dumps(
        journal.model_dump(mode="json"),
        ensure_ascii=False,
    )
    run.touch()
    session.add(run)


async def export_approved_run_to_wordpress(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    force_new_draft: bool = False,
) -> WordPressExportAttempt:
    """
    If run is approved, create a draft post via WordPress REST and append journal entry.

    Does not publish. Duplicate guard: blocks when the last successful export exists unless
    force_new_draft is True.
    """
    run = await session.get(PipelineRun, run_id)
    if run is None:
        raise WordPressExportServiceError("not_found", "Run does not exist.")

    if run.status != RunStatus.APPROVED.value:
        raise WordPressExportServiceError(
            "not_approved",
            f"Only approved runs can be exported (current status: {run.status}).",
        )

    journal = load_export_journal(run)
    last_ok = journal.last_succeeded()
    if last_ok is not None and not force_new_draft:
        raise WordPressExportServiceError(
            "already_exported",
            "A WordPress draft was already created for this run. "
            "Use “Create another draft” if you intend to export again.",
        )

    brand = brand_loader.load_brand_config(run.brand_slug)
    pkg = review_package_from_run(run)

    now = datetime.now(timezone.utc)
    base_attempt = WordPressExportAttempt(
        run_id=run.id,
        brand_slug=run.brand_slug,
        status=WordPressExportAttemptStatus.FAILED,
        exported_at=now,
        wordpress_site_base=None,
        error_code=None,
        error_message=None,
    )

    try:
        creds = resolve_wordpress_credentials(brand)
        base_attempt = base_attempt.model_copy(
            update={"wordpress_site_base": creds.site_base},
        )
    except WordPressConfigError as e:
        attempt = base_attempt.model_copy(
            update={
                "status": WordPressExportAttemptStatus.SKIPPED,
                "error_code": "configuration_error",
                "error_message": str(e),
            },
        )
        journal.attempts.append(attempt)
        _save_journal(session, run, journal)
        await session.commit()
        await session.refresh(run)
        log.info("wordpress.export.skipped_config", run_id=str(run_id), reason="configuration")
        return attempt

    article = pkg.get("article_draft")
    if isinstance(article, dict):
        pass
    else:
        article = None
    metadata = pkg.get("metadata_package")
    if not isinstance(metadata, dict):
        metadata = None
    st = pkg.get("selected_topic")
    if not isinstance(st, dict):
        st = None

    payload = draft_payload_from_state(
        brand_slug=run.brand_slug,
        article=article,
        metadata=metadata,
        selected_topic=st,
    )

    result = await create_draft_post(creds, payload)

    if result.ok:
        attempt = base_attempt.model_copy(
            update={
                "status": WordPressExportAttemptStatus.SUCCEEDED,
                "wordpress_post_id": result.wordpress_post_id,
                "wordpress_post_url": result.wordpress_post_url,
                "http_status": result.http_status,
                "error_code": None,
                "error_message": None,
            },
        )
        log.info(
            "wordpress.export.succeeded",
            run_id=str(run_id),
            post_id=result.wordpress_post_id,
        )
    else:
        attempt = base_attempt.model_copy(
            update={
                "status": WordPressExportAttemptStatus.FAILED,
                "http_status": result.http_status,
                "error_code": "wordpress_reject",
                "error_message": result.error or "WordPress request failed.",
            },
        )
        log.warning(
            "wordpress.export.failed",
            run_id=str(run_id),
            http_status=result.http_status,
        )

    journal.attempts.append(attempt)
    _save_journal(session, run, journal)
    await session.commit()
    await session.refresh(run)
    return attempt


def parse_journal(run: PipelineRun) -> WordPressExportJournal:
    return load_export_journal(run)
