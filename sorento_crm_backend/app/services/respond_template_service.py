"""Respond.io WhatsApp template sync + per-use-case default configuration.

Sync pulls channels (``GET /v2/space/channel``) and per-channel WhatsApp
templates (``GET /v2/space/channel/{channelId}/template``) for every active
``respond_workspaces`` row, upserting into ``respond_channels`` /
``respond_message_templates`` and hard-deleting rows gone from the API.

Defaults: one row per use case (complaint / stock_inquiry / purchase_request /
sponsorship_form) selecting the approved template + positional param mapping
used by ``respond_messaging_service.send_text_or_template`` when the contact's
24h window is closed.

Plan: docs/plans/PLAN-whatsapp-template-fallback.md
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.respond_template import (
    TEMPLATE_DEFAULT_USE_CASES,
    RespondChannel,
    RespondMessageTemplate,
    RespondTemplateDefault,
)
from app.models.respond_workspace import RespondWorkspace
from app.services.error_handler import handle_not_found, handle_validation_error

logger = logging.getLogger(__name__)

# Variables resolvable per use case by respond_messaging_service.
PARAM_VARIABLES = (
    "contact_name",
    "assignee_name",
    "entity_number",
    "status",
    "due_date",
    "reason",
    "portal_url",
    "message",
)

_PARAM_RE = re.compile(r"\{\{(\d+)\}\}")


def _now() -> datetime:
    return datetime.utcnow()


def _body_text_of(components: List[dict]) -> str:
    for comp in components or []:
        if isinstance(comp, dict) and comp.get("type") == "body":
            return str(comp.get("text") or "")
    return ""


def _param_count_of(body_text: str) -> int:
    nums = [int(m) for m in _PARAM_RE.findall(body_text or "")]
    return max(nums) if nums else 0


def _client_for_workspace(workspace: RespondWorkspace):
    from app.services.integration_service import RespondClient
    from app.utils.field_encryption import decrypt_secret

    api_key: Optional[str] = None
    try:
        api_key = decrypt_secret(workspace.api_key_ciphertext)
    except ValueError:
        logger.warning(
            "respond_templates sync: cannot decrypt api key for workspace %s; using env key",
            workspace.space_id,
        )
    return RespondClient(api_key=api_key, base_url=workspace.base_url or None)


def sync_templates(db: Session) -> Dict[str, int]:
    """Sync channels + templates for all active workspaces.

    Upsert by natural keys; hard-delete template/channel rows missing from the
    API (defaults survive via ``ON DELETE SET NULL`` + name snapshot).
    """
    workspaces = (
        db.query(RespondWorkspace).filter(RespondWorkspace.is_active.is_(True)).all()
    )
    if not workspaces:
        raise handle_validation_error(
            "No active Respond.io workspace configured. Add one under Respond.io Workspaces first."
        )

    now = _now()
    channels_seen = 0
    synced = 0
    deleted = 0

    for ws in workspaces:
        client = _client_for_workspace(ws)
        api_channels = client.list_channels()

        existing_channels = {
            c.respond_channel_id: c
            for c in db.query(RespondChannel).filter(RespondChannel.workspace_id == ws.id).all()
        }
        api_channel_ids = set()

        for item in api_channels:
            try:
                rid = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            api_channel_ids.add(rid)
            channel = existing_channels.get(rid)
            if channel is None:
                channel = RespondChannel(workspace_id=ws.id, respond_channel_id=rid)
                db.add(channel)
                existing_channels[rid] = channel
            channel.name = item.get("name")
            channel.source = item.get("source")
            channel.synced_at = now
            channels_seen += 1

        # Hard-delete channels gone from the API (cascades their templates).
        for rid, channel in list(existing_channels.items()):
            if rid not in api_channel_ids:
                db.delete(channel)
                del existing_channels[rid]

        db.flush()

        for channel in existing_channels.values():
            try:
                api_templates = client.list_message_templates(channel.respond_channel_id)
            except Exception as e:  # non-WhatsApp channels have no template endpoint
                logger.info(
                    "respond_templates sync: channel %s (%s) has no templates (%s)",
                    channel.respond_channel_id,
                    channel.source,
                    e,
                )
                continue

            existing_templates = {
                t.respond_template_id: t
                for t in db.query(RespondMessageTemplate)
                .filter(RespondMessageTemplate.channel_id == channel.id)
                .all()
            }
            api_template_ids = set()

            for item in api_templates:
                try:
                    rid = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                api_template_ids.add(rid)
                row = existing_templates.get(rid)
                if row is None:
                    row = RespondMessageTemplate(
                        channel_id=channel.id, respond_template_id=rid
                    )
                    db.add(row)
                    existing_templates[rid] = row
                components = item.get("components") or []
                body_text = _body_text_of(components)
                row.name = str(item.get("name") or "")
                row.language_code = str(item.get("languageCode") or "en")
                row.category = item.get("category")
                row.status = str(item.get("status") or "pending")
                row.status_detail = item.get("statusDetail")
                row.meta_template_id = (
                    str(item.get("templateId")) if item.get("templateId") else None
                )
                row.namespace = item.get("namespace")
                row.components = components
                row.body_text = body_text
                row.param_count = _param_count_of(body_text)
                row.synced_at = now
                synced += 1

            for rid, row in existing_templates.items():
                if rid not in api_template_ids:
                    db.delete(row)
                    deleted += 1

    db.commit()
    return {"synced": synced, "deleted": deleted, "channels": channels_seen}


def list_templates(
    db: Session,
    *,
    page: int = 1,
    limit: int = 50,
    query: Optional[str] = None,
    status: Optional[str] = None,
    sort: str = "name",
    direction: str = "asc",
) -> Dict[str, Any]:
    q = db.query(RespondMessageTemplate).options(
        joinedload(RespondMessageTemplate.channel)
    )
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(
            RespondMessageTemplate.name.ilike(like)
            | RespondMessageTemplate.body_text.ilike(like)
        )
    if status and status != "all":
        q = q.filter(RespondMessageTemplate.status == status)

    sort_col = {
        "name": RespondMessageTemplate.name,
        "language_code": RespondMessageTemplate.language_code,
        "category": RespondMessageTemplate.category,
        "status": RespondMessageTemplate.status,
        "param_count": RespondMessageTemplate.param_count,
        "synced_at": RespondMessageTemplate.synced_at,
    }.get(sort, RespondMessageTemplate.name)
    q = q.order_by(sort_col.desc() if direction == "desc" else sort_col.asc())

    total = q.count()
    rows = q.offset(max(0, (page - 1)) * limit).limit(limit).all()
    return {
        "data": [serialize_template(t) for t in rows],
        "pagination": {"total": total, "page": page, "limit": limit},
    }


def serialize_template(t: RespondMessageTemplate) -> Dict[str, Any]:
    return {
        "id": str(t.id),
        "respond_template_id": str(t.respond_template_id),
        "name": t.name,
        "language": t.language_code,
        "category": t.category,
        "status": t.status,
        "body_text": t.body_text,
        "param_count": t.param_count,
        "channel_name": t.channel.name if t.channel else None,
        "synced_at": t.synced_at.isoformat() if t.synced_at else None,
    }


def _default_is_valid(row: Optional[RespondTemplateDefault]) -> bool:
    if row is None or row.template_id is None or row.template is None:
        return False
    if row.template.status != "approved":
        return False
    needed = {str(i + 1) for i in range(row.template.param_count)}
    return needed <= set((row.param_mapping or {}).keys())


def serialize_default(
    use_case: str, row: Optional[RespondTemplateDefault]
) -> Dict[str, Any]:
    template = row.template if row is not None else None
    template_name = None
    if template is not None:
        template_name = template.name
    elif row is not None and row.template_name_snapshot:
        template_name = row.template_name_snapshot
    return {
        "use_case": use_case,
        "template_id": str(row.template_id) if row and row.template_id else None,
        "template_name": template_name,
        "template_status": template.status if template else None,
        "param_mapping": dict(row.param_mapping or {}) if row else {},
        # True only when the template exists, is approved and fully mapped.
        "is_valid": _default_is_valid(row),
        # Template was set once but hard-deleted by a later sync.
        "template_removed": bool(
            row and row.template_id is None and row.template_name_snapshot
        ),
    }


def get_defaults(db: Session) -> List[Dict[str, Any]]:
    rows = {
        r.use_case: r
        for r in db.query(RespondTemplateDefault)
        .options(
            joinedload(RespondTemplateDefault.template).joinedload(
                RespondMessageTemplate.channel
            )
        )
        .all()
    }
    return [serialize_default(uc, rows.get(uc)) for uc in TEMPLATE_DEFAULT_USE_CASES]


def get_default_row(db: Session, use_case: str) -> Optional[RespondTemplateDefault]:
    return (
        db.query(RespondTemplateDefault)
        .options(
            joinedload(RespondTemplateDefault.template).joinedload(
                RespondMessageTemplate.channel
            )
        )
        .filter(RespondTemplateDefault.use_case == use_case)
        .first()
    )


def set_default(
    db: Session,
    use_case: str,
    *,
    template_id: str,
    param_mapping: Dict[str, str],
) -> Dict[str, Any]:
    if use_case not in TEMPLATE_DEFAULT_USE_CASES:
        raise handle_validation_error(f"Unknown use_case: {use_case}")

    template = (
        db.query(RespondMessageTemplate)
        .filter(RespondMessageTemplate.id == template_id)
        .first()
    )
    if template is None:
        raise handle_not_found("Template", template_id)
    if template.status != "approved":
        raise handle_validation_error(
            "Only approved templates can be set as default."
        )

    mapping = {str(k): str(v) for k, v in (param_mapping or {}).items()}
    needed = {str(i + 1) for i in range(template.param_count)}
    missing = sorted(needed - set(mapping.keys()), key=int)
    if missing:
        raise handle_validation_error(
            f"param_mapping must cover every template parameter; missing: {', '.join(missing)}"
        )
    invalid_vars = sorted({v for v in mapping.values() if v not in PARAM_VARIABLES})
    if invalid_vars:
        raise handle_validation_error(
            f"Unknown param variables: {', '.join(invalid_vars)}. Allowed: {', '.join(PARAM_VARIABLES)}"
        )
    # Drop mapping entries beyond the template's params (stale keys from a
    # previously-selected template).
    mapping = {k: v for k, v in mapping.items() if k in needed}

    row = (
        db.query(RespondTemplateDefault)
        .filter(RespondTemplateDefault.use_case == use_case)
        .first()
    )
    if row is None:
        row = RespondTemplateDefault(use_case=use_case)
        db.add(row)
    row.template_id = template.id
    row.template_name_snapshot = template.name
    row.param_mapping = mapping
    db.commit()
    return serialize_default(use_case, get_default_row(db, use_case))


def clear_default(db: Session, use_case: str) -> Dict[str, Any]:
    if use_case not in TEMPLATE_DEFAULT_USE_CASES:
        raise handle_validation_error(f"Unknown use_case: {use_case}")
    row = (
        db.query(RespondTemplateDefault)
        .filter(RespondTemplateDefault.use_case == use_case)
        .first()
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return serialize_default(use_case, None)


def run_respond_templates_sync(db: Session, task) -> Dict[str, Any]:
    """Scheduled-task handler (key: respond_templates_sync)."""
    return sync_templates(db)
