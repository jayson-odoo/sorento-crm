"""IT-Support ticket intake from MCP / n8n.

Single-shot draft flow. Caller posts the user's complaint (either
``original_message`` for server-side LLM extraction, or pre-drafted
``title`` + fields). Server creates a DRAFT ticket and returns a
``draft_url`` the caller surfaces to the user. The user opens that URL —
in-app for AI-assistant calls, public portal token URL for WhatsApp
calls — reviews the preview, then clicks Submit / Edit / Cancel on a
real ticket page. Explicit confirmation is therefore deterministic
(button click), not an LLM-driven multi-turn handshake.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models.access import RespondContact
from app.models.tickets import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
)
from app.models.user import User
from app.schemas.tickets import (
    ITSupportTicketCreateRequest,
    ITSupportTicketCreateResponse,
    ITSupportTicketDraftPreview,
)
from app.services import tickets_service
from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.llm_provider import get_provider
from app.services.ticket_draft_token_service import mint_draft_token

logger = logging.getLogger(__name__)


_DRAFT_SYSTEM_PROMPT = (
    "You are an IT-support ticket intake assistant. The user has just described a "
    "problem they want logged with the IT admin team. Your job is to extract a "
    "structured ticket from their message.\n\n"
    "Rules:\n"
    "- title: <= 80 chars, action-oriented, written in third person (e.g. 'Login "
    "broken on Safari', not 'I can't log in'). Strip filler.\n"
    "- priority: choose ONE of low | medium | high | urgent. Use 'urgent' only "
    "for total outages or security incidents; 'high' for blocked workflows; "
    "'medium' is the default; 'low' for cosmetic / minor.\n"
    "- category: choose ONE of bug | feature | question | other. Default to 'bug' "
    "if it sounds like something is broken; 'question' for how-to; 'feature' for "
    "requests; 'other' otherwise.\n"
    "- description_html: clean HTML paragraphs summarizing what the user said, "
    "what they tried, what they expect to happen. Wrap each paragraph in <p>. "
    "Keep the user's original wording where useful, but trim noise.\n"
    "- description_text: a plain-text version of description_html (same content, "
    "no tags).\n\n"
    "Return ONLY a JSON object with keys: title, priority, category, "
    "description_html, description_text. No prose, no fences."
)


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _parse_preview_json(content: str) -> dict[str, Any]:
    raw = _strip_code_fences(content or "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _build_in_app_url(ticket_id: str) -> str:
    base = (settings.frontend_base_url or "http://localhost:3000").rstrip("/")
    return f"{base}/ticket-management/tickets/{ticket_id}"


def _build_portal_url(token: str) -> str:
    base = (settings.frontend_base_url or "http://localhost:3000").rstrip("/")
    return f"{base}/portal/ticket-draft/{token}"


class TicketIntakeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def submit(
        self,
        payload: ITSupportTicketCreateRequest,
        *,
        actor_user_id_fallback: Optional[str] = None,
    ) -> ITSupportTicketCreateResponse:
        self._apply_channel_defaults(payload, actor_user_id_fallback)
        self._validate_channel_fields(payload)

        preview = (
            self._preview_from_caller_draft(payload)
            if payload.title
            else self._draft_via_llm(payload.original_message or "")
        )

        if payload.source_channel == "ai_assistant":
            user = (
                self.db.query(User)
                .filter(User.id == str(payload.actor_user_id))
                .first()
            )
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="actor_user_id does not match any user.",
                )
            raised_by = str(user.id)
            raised_by_kind = "user"
            actor_user_id = str(user.id)
            respond_contact_id = None
        else:
            contact = (
                self.db.query(RespondContact)
                .filter(RespondContact.id == str(payload.respond_contact_id))
                .first()
            )
            if not contact:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="respond_contact_id does not match any respond contact.",
                )
            raised_by = str(contact.id)
            raised_by_kind = "respond_contact"
            actor_user_id = None
            respond_contact_id = str(contact.id)

        ticket = tickets_service.create_ticket_from_mcp(
            self.db,
            title=preview.title,
            priority=preview.priority,
            category=preview.category,
            description_html=preview.description_html,
            description_text=preview.description_text,
            source_channel=payload.source_channel,
            raised_by=raised_by,
            raised_by_kind=raised_by_kind,
            actor_user_id=actor_user_id,
            source_conversation_id=payload.source_conversation_id,
            source_message_id=payload.source_message_id,
            source_space_id=payload.source_space_id,
            respond_contact_id=respond_contact_id,
        )

        if payload.source_channel == "ai_assistant":
            draft_url = _build_in_app_url(str(ticket.id))
            portal_token = None
        else:
            portal_token = mint_draft_token(str(ticket.id))
            draft_url = _build_portal_url(portal_token)

        return ITSupportTicketCreateResponse(
            status="draft_created",
            ticket_id=str(ticket.id),
            ticket_number=ticket.ticket_number,
            draft_url=draft_url,
            portal_token=portal_token,
            preview=preview,
            ticket=tickets_service.ticket_to_response(self.db, ticket),
        )

    # ---------- channel defaults / validation ----------

    @staticmethod
    def _apply_channel_defaults(
        payload: ITSupportTicketCreateRequest,
        actor_user_id_fallback: Optional[str],
    ) -> None:
        if not payload.source_channel:
            payload.source_channel = "ai_assistant"
        if payload.source_channel == "ai_assistant" and not payload.actor_user_id:
            payload.actor_user_id = actor_user_id_fallback

    @staticmethod
    def _validate_channel_fields(payload: ITSupportTicketCreateRequest) -> None:
        if payload.source_channel == "ai_assistant" and not payload.actor_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="actor_user_id is required when source_channel='ai_assistant'",
            )
        if payload.source_channel == "whatsapp_respond":
            if not payload.respond_contact_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="respond_contact_id is required when source_channel='whatsapp_respond'",
                )
            if not payload.source_conversation_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="source_conversation_id is required when source_channel='whatsapp_respond'",
                )

    # ---------- caller-drafted preview shortcut ----------

    @staticmethod
    def _preview_from_caller_draft(
        payload: ITSupportTicketCreateRequest,
    ) -> ITSupportTicketDraftPreview:
        title = (payload.title or "").strip()[:200] or "IT support ticket"
        priority = (payload.priority or "medium").strip().lower()
        if priority not in TICKET_PRIORITIES:
            priority = "medium"
        category = (payload.category or "bug").strip().lower()
        if category not in TICKET_CATEGORIES:
            category = "bug"
        description_text = (
            payload.description_text
            or payload.description
            or payload.original_message
            or title
        )
        description_html = (
            payload.description_html
            or f"<p>{description_text}</p>"
        )
        return ITSupportTicketDraftPreview(
            title=title,
            priority=priority,
            category=category,
            description_html=description_html,
            description_text=description_text,
        )

    # ---------- LLM ----------

    def _draft_via_llm(self, original_message: str) -> ITSupportTicketDraftPreview:
        cfg = AIAssistantConfigService(self.db).get()
        api_key = cfg.api_key_ciphertext or settings.openai_api_key
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM provider is not configured for ticket intake.",
            )
        provider = get_provider(cfg.provider, api_key, cfg.model)
        try:
            result = provider.chat(
                [
                    {"role": "system", "content": _DRAFT_SYSTEM_PROMPT},
                    {"role": "user", "content": original_message.strip()},
                ],
                temperature=0.0,
                model=cfg.model,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Ticket intake LLM call failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to draft ticket: {e}",
            ) from e

        try:
            data = _parse_preview_json(result.content or "")
        except Exception as e:  # noqa: BLE001
            logger.warning("Ticket intake LLM returned non-JSON: %s", result.content[:500])
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Ticket draft response was not valid JSON.",
            ) from e

        return ITSupportTicketDraftPreview(
            title=str(data.get("title") or original_message[:80]).strip()[:200],
            priority=str(data.get("priority") or "medium").strip().lower(),
            category=str(data.get("category") or "bug").strip().lower(),
            description_html=str(data.get("description_html") or f"<p>{original_message}</p>"),
            description_text=str(
                data.get("description_text") or original_message
            ),
        )
