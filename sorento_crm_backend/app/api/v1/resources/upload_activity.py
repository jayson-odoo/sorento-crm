"""
Upload Activity feed endpoint.

GET /api/v1/resources/upload-activity?scope=me&since=<iso>&limit=<int>

Joins `attachments` (filtered by `uploaded_by = current_user` + `created_at >= since`)
with the latest `integration_log` row per attachment (business_table='attachments').
Groups by `attachments.upload_batch_id`:
- batch_id == NULL                       → one "single" session per attachment
- batch_id matches an `import_jobs.job_id` → "bulk_zip" session, surfaces import_job_id
- otherwise (multi-file modal)            → "multi" session keyed on the batch UUID

Returns response shape defined in `app.schemas.upload_activity`.
See docs/plans/PLAN-upload-activity-drawer.md §4.3.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.integration import IntegrationLog
from app.models.job import ImportJob
from app.models.resources import Attachment
from app.schemas.upload_activity import (
    LinkedEntity,
    SessionAggregate,
    UnlinkedReason,
    UploadActivityFile,
    UploadActivityResponse,
    UploadActivitySession,
)
from app.services.resources_service import AttachmentService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---- helpers --------------------------------------------------------------


def _parse_response_payload(raw: Optional[str]) -> dict:
    """integration_log.response_payload is TEXT — defensive JSON parse."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _file_status_from_log(
    log: Optional[IntegrationLog],
    linked: List[LinkedEntity],
) -> str:
    """Map integration_log.status + actual DB linkages to FE file status.

    Ground-truth precedence:
      - If any real linkages exist in DB → "linked" regardless of log state.
        Legacy n8n payloads frequently lack the v1 schema entirely; the row
        is still linked via product_attachments etc.
      - else fall back to the log's status / v1 outcome.
    """
    if linked:
        return "linked"
    if log is None:
        return "processing"
    s = (log.status or "").lower()
    if s == "success":
        payload = _parse_response_payload(log.response_payload)
        outcome = payload.get("outcome")
        if outcome == "unlinked":
            return "unlinked"
        if outcome == "failed":
            return "failed"
        return "linked"
    if s == "failed":
        return "failed"
    if s in ("pending", "processing", "sent"):
        return "processing"
    return "processing"


def _linked_entities_from_db(
    db: Session, attachment_id: str, *, log: Optional[IntegrationLog]
) -> List[LinkedEntity]:
    """
    Build the linked entity list from the canonical link tables — not from
    response_payload. The integration_log payload schema is unreliable in
    the wild; product_attachments / promotion_attachments / forms /
    inbound_shipments are the source of truth.

    `matched_by` defaults to "manual_or_n8n" because we can't tell which
    pipeline drew the line from the link tables alone.
    """
    service = AttachmentService(db)
    try:
        groups = service.get_linked_entities(attachment_id) or {}
    except Exception:  # noqa: BLE001
        return []

    out: List[LinkedEntity] = []
    for p in groups.get("linked_products") or []:
        out.append(
            LinkedEntity(
                entity_type="product",
                entity_id=str(p.get("id", "")),
                display_name=str(p.get("name") or p.get("id", "") or "product"),
                matched_by="manual_or_n8n",
            )
        )
    for pr in groups.get("linked_promotions") or []:
        out.append(
            LinkedEntity(
                entity_type="promotion",
                entity_id=str(pr.get("id", "")),
                display_name=str(pr.get("name") or pr.get("id", "") or "promotion"),
                matched_by="manual_or_n8n",
            )
        )
    form = groups.get("linked_form")
    if form:
        out.append(
            LinkedEntity(
                entity_type="form",
                entity_id=str(form.get("id", "")),
                display_name=str(form.get("name") or form.get("id", "") or "form"),
                matched_by="manual_or_n8n",
            )
        )
    for pl in groups.get("linked_packing_lists") or []:
        out.append(
            LinkedEntity(
                entity_type="packing_list",
                entity_id=str(pl.get("id", "")),
                display_name=str(pl.get("name") or pl.get("id", "") or "packing list"),
                matched_by="manual_or_n8n",
            )
        )
    return out


def _unlinked_reasons(log: Optional[IntegrationLog]) -> List[UnlinkedReason]:
    if log is None:
        return []
    payload = _parse_response_payload(log.response_payload)
    raw = payload.get("unlinked_reasons") or []
    out: List[UnlinkedReason] = []
    for item in raw:
        if isinstance(item, dict) and "reason" in item:
            out.append(UnlinkedReason(reason=str(item["reason"])))
    return out


def _summary(log: Optional[IntegrationLog], outcome_status: str) -> str:
    if log is None:
        return ""
    payload = _parse_response_payload(log.response_payload)
    return str(payload.get("summary") or "")


def _build_file(
    db: Session, attachment: Attachment, log: Optional[IntegrationLog]
) -> UploadActivityFile:
    linked = _linked_entities_from_db(db, str(attachment.id), log=log)
    file_status = _file_status_from_log(log, linked)
    return UploadActivityFile(
        client_id=str(attachment.id),
        attachment_id=str(attachment.id),
        filename=attachment.original_filename,
        status=file_status,  # type: ignore[arg-type]
        summary=_summary(log, file_status),
        linked=linked,
        unlinked_reasons=_unlinked_reasons(log),
        error_code=log.error_code if log else None,
        error_message=log.error_message if log else None,
        integration_log_id=str(log.id) if log else None,
        last_updated_at=(log.updated_at if log else attachment.created_at) or attachment.created_at,
    )


def _aggregate(files: List[UploadActivityFile]) -> SessionAggregate:
    return SessionAggregate(
        total=len(files),
        uploading=sum(1 for f in files if f.status == "uploading"),
        processing=sum(1 for f in files if f.status == "processing"),
        linked=sum(1 for f in files if f.status == "linked"),
        unlinked=sum(1 for f in files if f.status == "unlinked"),
        failed=sum(1 for f in files if f.status == "failed"),
    )


def _session_status(agg: SessionAggregate) -> str:
    if agg.uploading > 0:
        return "uploading"
    if agg.processing > 0:
        return "processing"
    if agg.total and agg.failed == agg.total:
        return "failed"
    if agg.unlinked > 0 or agg.failed > 0:
        return "partial"
    return "linked"


def _needs_action(files: List[UploadActivityFile]) -> bool:
    return any(f.status in ("failed", "unlinked") for f in files)


# ---- route ----------------------------------------------------------------


@router.get("", response_model=UploadActivityResponse, summary="Upload-activity drawer feed")
def get_upload_activity(
    scope: str = Query("me", pattern="^me$", description="Only 'me' is supported"),
    since: Optional[datetime] = Query(
        None,
        description="ISO-8601 cutoff. Default = now - 7 days.",
    ),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadActivityResponse:
    """
    Aggregator for the Upload Activity drawer (top-nav icon).

    See docs/plans/PLAN-upload-activity-drawer.md §3 for the decision log.
    """
    user_id = str(current_user["id"])
    cutoff = since or (datetime.utcnow() - timedelta(days=7))

    # ---- pull user's recent attachments ------------------------------------
    attachments: List[Attachment] = (
        db.query(Attachment)
        .filter(
            and_(
                Attachment.uploaded_by == user_id,
                Attachment.created_at >= cutoff,
                Attachment.is_deleted.is_(False),
            )
        )
        .order_by(desc(Attachment.created_at))
        .limit(limit * 50)  # over-fetch to allow grouping into <= `limit` sessions
        .all()
    )
    if not attachments:
        return UploadActivityResponse(sessions=[])

    attachment_ids = [str(a.id) for a in attachments]

    # ---- pull latest integration_log per attachment ------------------------
    logs: List[IntegrationLog] = (
        db.query(IntegrationLog)
        .filter(
            and_(
                IntegrationLog.business_table == "attachments",
                IntegrationLog.business_id.in_(attachment_ids),
            )
        )
        .order_by(IntegrationLog.business_id, desc(IntegrationLog.created_at))
        .all()
    )
    # Keep latest per business_id only.
    latest_log_by_attachment: Dict[str, IntegrationLog] = {}
    for log in logs:
        bid = str(log.business_id)
        if bid not in latest_log_by_attachment:
            latest_log_by_attachment[bid] = log

    # ---- pull import_jobs touched by the user in the window ---------------
    import_jobs: List[ImportJob] = (
        db.query(ImportJob)
        .filter(
            and_(
                ImportJob.user_id == user_id,
                ImportJob.job_type == "attachment_bulk_import",
                ImportJob.created_at >= cutoff,
            )
        )
        .all()
    )
    import_jobs_by_job_id: Dict[str, ImportJob] = {str(j.job_id): j for j in import_jobs}

    # ---- group attachments by upload_batch_id ------------------------------
    by_batch: Dict[str, List[Attachment]] = {}
    singles: List[Attachment] = []
    for a in attachments:
        batch = (a.upload_batch_id or "").strip()
        if not batch:
            singles.append(a)
            continue
        by_batch.setdefault(batch, []).append(a)

    sessions: List[UploadActivitySession] = []

    # multi / bulk_zip sessions
    for batch_id, members in by_batch.items():
        members_sorted = sorted(members, key=lambda x: x.created_at)
        files = [
            _build_file(db, m, latest_log_by_attachment.get(str(m.id))) for m in members_sorted
        ]
        agg = _aggregate(files)
        import_job = import_jobs_by_job_id.get(batch_id)
        is_bulk = import_job is not None
        title = (
            (import_job.filename or "Bulk ZIP")
            if is_bulk
            else f"{len(files)} files"
        )
        started_at = members_sorted[0].created_at
        # `finished_at` only when no in-flight rows AND all logs settled.
        any_in_flight = agg.uploading + agg.processing > 0
        finished_at: Optional[datetime] = None
        if not any_in_flight:
            last_log_updated = [
                latest_log_by_attachment[str(m.id)].updated_at
                for m in members_sorted
                if str(m.id) in latest_log_by_attachment
            ]
            finished_at = max(last_log_updated) if last_log_updated else members_sorted[-1].created_at

        sessions.append(
            UploadActivitySession(
                session_id=batch_id,
                session_type="bulk_zip" if is_bulk else "multi",
                title=title,
                started_at=started_at,
                finished_at=finished_at,
                status=_session_status(agg),  # type: ignore[arg-type]
                aggregate=agg,
                files=files,
                import_job_id=batch_id if is_bulk else None,
                needs_action=_needs_action(files),
            )
        )

    # single sessions (one per attachment)
    for a in singles:
        log = latest_log_by_attachment.get(str(a.id))
        f = _build_file(db, a, log)
        agg = _aggregate([f])
        sessions.append(
            UploadActivitySession(
                session_id=str(a.id),  # no batch — key on attachment_id
                session_type="single",
                title=a.original_filename,
                started_at=a.created_at,
                finished_at=(log.updated_at if log and f.status in ("linked", "unlinked", "failed") else None),
                status=_session_status(agg),  # type: ignore[arg-type]
                aggregate=agg,
                files=[f],
                import_job_id=None,
                needs_action=_needs_action([f]),
            )
        )

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    sessions = sessions[:limit]

    return UploadActivityResponse(sessions=sessions)
