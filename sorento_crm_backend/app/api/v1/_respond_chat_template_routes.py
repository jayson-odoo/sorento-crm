"""Reusable chat window-state + manual template-send endpoints.

Each entity that exposes a Respond.io chat panel (complaint, stock inquiry,
purchase request) mounts these two routes via ``build_chat_template_router``,
supplying a resolver that turns the entity id into a Respond.io send
identifier + internal respond_contact_id. Keeps the manual template flow
identical across panels (plan: PLAN-whatsapp-template-fallback.md).

The sub-router uses a fixed ``entity_id`` path segment and is mounted under
each entity's existing prefix (e.g. ``/complaints``), so the resulting paths
are ``/complaints/{entity_id}/conversation/window-state`` etc.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.services.error_handler import handle_validation_error

# (identifier, respond_contact_id) — identifier None means no linked contact.
ChatContactResolver = Callable[[Session, str], Tuple[Optional[str], Optional[str]]]


class TemplateMessageSendRequest(BaseModel):
    template_id: str = Field(..., min_length=1)
    params: dict[str, str] = Field(default_factory=dict)


def build_chat_template_router(
    *,
    business_table: str,
    resolver: ChatContactResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/{entity_id}/conversation/window-state")
    def window_state(
        entity_id: str,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user),
    ):
        identifier, respond_contact_id = resolver(db, entity_id)
        if not identifier:
            raise handle_validation_error(
                "No Respond.io contact linked; cannot check window state."
            )
        from app.services.respond_chat_template_service import get_window_state_for

        return get_window_state_for(
            db, identifier=identifier, respond_contact_id=respond_contact_id
        )

    @router.post("/{entity_id}/conversation/template-message")
    def template_message(
        entity_id: str,
        body: TemplateMessageSendRequest,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user),
    ):
        identifier, _ = resolver(db, entity_id)
        if not identifier:
            raise handle_validation_error(
                "No Respond.io contact linked; cannot send a template."
            )
        from app.services.respond_chat_template_service import send_manual_template_for

        result = send_manual_template_for(
            db,
            identifier=identifier,
            template_id=body.template_id,
            params=body.params,
            business_table=business_table,
            business_id=str(entity_id),
            created_by=str(current_user.get("id") or "") or None,
        )
        return {
            "ok": True,
            "template_name": result["template_name"],
            "rendered_body": result["rendered_body"],
        }

    return router
