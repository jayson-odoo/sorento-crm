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


class ChatMessageSendRequest(BaseModel):
    text: str = Field(..., min_length=1)


def build_chat_template_router(
    *,
    business_table: str,
    resolver: ChatContactResolver,
    chat_use_case: Optional[str] = None,
    chat_use_case_resolver: Optional[Callable[[Session, str], str]] = None,
    context_builder: Optional[Callable[[Session, str], dict]] = None,
) -> APIRouter:
    """Reusable window-state + manual-template + smart-send routes for a chat panel.

    ``chat_use_case`` is the ``*_chat`` / ``conversation_chat`` template use case for
    the pure smart-send route. ``chat_use_case_resolver`` overrides it per entity
    (e.g. purchase_request vs sponsorship_form on a single mount). ``context_builder``
    supplies extra template context (portal_url / view_url) per entity.
    """
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

    @router.get("/{entity_id}/conversation/chat-template")
    def chat_template(
        entity_id: str,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user),
    ):
        """Describe the form's chat template so the composer can render it inline
        with a fill-in field for the message. DB-only (no Respond.io call)."""
        use_case = (
            chat_use_case_resolver(db, entity_id)
            if chat_use_case_resolver is not None
            else chat_use_case
        )
        if not use_case:
            return {"configured": False, "reason": "not_supported"}
        identifier, respond_contact_id = resolver(db, entity_id)
        if not identifier:
            return {"configured": False, "reason": "no_contact"}
        sender_name = (current_user.get("name") or "").strip() or "Customer Service"
        from app.services.respond_chat_template_service import get_chat_template_preview

        return get_chat_template_preview(
            db,
            identifier=identifier,
            respond_contact_id=respond_contact_id,
            chat_use_case=use_case,
            sender_name=sender_name,
            entity_id=str(entity_id),
            context_builder=context_builder,
        )

    @router.post("/{entity_id}/conversation/send-message")
    def send_message(
        entity_id: str,
        body: ChatMessageSendRequest,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user),
    ):
        """Pure smart chat send: in-window plain text, out-of-window ``*_chat``
        template with the sender's name. Never mutates the entity."""
        use_case = (
            chat_use_case_resolver(db, entity_id)
            if chat_use_case_resolver is not None
            else chat_use_case
        )
        if not use_case:
            raise handle_validation_error("Chat send not configured for this entity.")
        identifier, respond_contact_id = resolver(db, entity_id)
        if not identifier:
            raise handle_validation_error(
                "No Respond.io contact linked; cannot send a message."
            )
        sender_name = (current_user.get("name") or "").strip() or "Customer Service"
        from app.services.respond_chat_template_service import send_chat_message_for

        # Pass the context_builder callable through — send_chat_message_for invokes it
        # lazily + guarded, and ONLY on the out-of-window (template) path.
        return send_chat_message_for(
            db,
            identifier=identifier,
            respond_contact_id=respond_contact_id,
            text=body.text,
            chat_use_case=use_case,
            business_table=business_table,
            business_id=str(entity_id),
            sender_name=sender_name,
            created_by=str(current_user.get("id") or "") or None,
            context_builder=context_builder,
        )

    return router
