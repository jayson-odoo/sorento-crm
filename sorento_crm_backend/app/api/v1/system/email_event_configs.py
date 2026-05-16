"""Email event configs admin API. List + toggle per-event kill switches."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models.email_outbox import EmailEventConfig
from app.schemas.email_outbox import EmailEventConfigResponse, EmailEventConfigUpdate
from app.services.email_event_registry import seed_event_configs
from app.services.error_handler import handle_internal_error

router = APIRouter()


def _to_response(row: EmailEventConfig) -> EmailEventConfigResponse:
    return EmailEventConfigResponse(
        event_key=row.event_key,
        display_name=row.display_name,
        description=row.description,
        enabled=bool(row.enabled),
        rate_per_window_override=row.rate_per_window_override,
        window_seconds_override=row.window_seconds_override,
        priority_override=row.priority_override,
        coalesce_window_seconds_override=row.coalesce_window_seconds_override,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/email-event-configs", response_model=list[EmailEventConfigResponse])
async def list_email_event_configs(
    current_user: dict = Depends(require_permission("system.email_event_configs.view")),
    db: Session = Depends(get_db),
):
    try:
        seed_event_configs(db)
        rows = db.query(EmailEventConfig).order_by(EmailEventConfig.event_key.asc()).all()
        return [_to_response(r) for r in rows]
    except HTTPException:
        raise
    except Exception as exc:
        raise handle_internal_error(str(exc))


@router.put("/email-event-configs/{event_key}", response_model=EmailEventConfigResponse)
async def update_email_event_config(
    event_key: str,
    payload: EmailEventConfigUpdate,
    current_user: dict = Depends(require_permission("system.email_event_configs.manage")),
    db: Session = Depends(get_db),
):
    row = db.query(EmailEventConfig).filter(EmailEventConfig.event_key == event_key).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown event_key (not in registry)")
    if payload.enabled is not None:
        row.enabled = bool(payload.enabled)
    if payload.rate_per_window_override is not None:
        row.rate_per_window_override = int(payload.rate_per_window_override) or None
    if payload.window_seconds_override is not None:
        row.window_seconds_override = int(payload.window_seconds_override) or None
    if payload.priority_override is not None:
        row.priority_override = int(payload.priority_override)
    if payload.coalesce_window_seconds_override is not None:
        row.coalesce_window_seconds_override = int(payload.coalesce_window_seconds_override) or None
    db.commit()
    db.refresh(row)
    return _to_response(row)
