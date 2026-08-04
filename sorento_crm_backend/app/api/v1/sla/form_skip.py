"""Skip the next SLA stage - generic endpoint (UAC-form-sla-skip-stage.md).

POST /form/{source_entity_type}/{source_entity_id}/skip

One route serves every entity type. What a skip *means* comes from the per-entity
adapter (`form_skip_registry`); what it *does* comes from the stage's config
(`skip_event` / `skip_terminal_status`). A type with no registered adapter, a stage
with no `skip_event`, or an entity in a status the adapter refuses, all 422 before
anything is written.

The permission is deliberately NOT a route-level `require_permission` dependency:
it varies per entity type, so the service resolves it from the adapter. That keeps a
config row from ever being able to authorise an action.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services.form_sla_service import FORM_SLA_TYPES
from app.services.form_skip_registry import get_skip_adapter
from app.services.form_skip_service import FormSkipService
from app.services.handling_lock_service import assert_can_act_on_form

router = APIRouter()


class _SkipRequest(BaseModel):
    note: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional message appended to the contact's status update.",
    )


@router.post("/{source_entity_type}/{source_entity_id}/skip")
async def skip_form_stage(
    source_entity_type: str,
    source_entity_id: str,
    payload: _SkipRequest | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if source_entity_type not in FORM_SLA_TYPES:
        raise HTTPException(status_code=422, detail="Not a form SLA entity type.")
    if get_skip_adapter(source_entity_type) is None:
        raise HTTPException(
            status_code=422,
            detail=f"'{source_entity_type}' does not support this action.",
        )
    # Handling lock first, same as every other business CTA: an escalated form can only
    # be acted on by whoever holds it.
    assert_can_act_on_form(
        db, source_entity_id, current_user, source_entity_type=source_entity_type
    )
    return FormSkipService(db).skip(
        source_entity_type,
        source_entity_id,
        actor_user_id=current_user.get("id"),
        note=(payload.note if payload else None),
    )
