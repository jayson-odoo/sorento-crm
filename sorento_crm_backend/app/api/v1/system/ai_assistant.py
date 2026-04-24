"""System AI assistant config and chat endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.ai_assistant import (
    AIAssistantConfigResponse,
    AIAssistantConfigUpdate,
    AIAssistantConversationResponse,
    AIAssistantMessageCreate,
    AIAssistantMessageResponse,
)
from app.services.ai_assistant_service import AIAssistantChatService, AIAssistantConfigService

router = APIRouter()


@router.get("/ai-assistant/config", response_model=AIAssistantConfigResponse)
def get_ai_assistant_config(
    _user: dict = Depends(require_permission("system.ai_assistant_settings.view")),
    db: Session = Depends(get_db),
):
    svc = AIAssistantConfigService(db)
    row = svc.get()
    return AIAssistantConfigResponse(**svc.to_response_dict(row))


@router.put("/ai-assistant/config", response_model=AIAssistantConfigResponse)
def update_ai_assistant_config(
    payload: AIAssistantConfigUpdate,
    user: dict = Depends(require_permission("system.ai_assistant_settings.edit")),
    db: Session = Depends(get_db),
):
    svc = AIAssistantConfigService(db)
    row = svc.update(payload, user_id=str(user["id"]))
    return AIAssistantConfigResponse(**svc.to_response_dict(row))


@router.get("/ai-assistant/tools", response_model=list[str])
def list_ai_assistant_tools(
    _user: dict = Depends(require_permission("system.ai_assistant_settings.view")),
    db: Session = Depends(get_db),
):
    chat = AIAssistantChatService(db)
    return chat.list_mcp_tools()


@router.get("/ai-assistant/conversations", response_model=list[AIAssistantConversationResponse])
def list_ai_assistant_conversations(
    user: dict = Depends(require_permission("system.ai_assistant_chat.use")),
    db: Session = Depends(get_db),
):
    chat = AIAssistantChatService(db)
    rows = chat.list_conversations(str(user["id"]))
    return [
        AIAssistantConversationResponse(
            id=str(r.id),
            title=r.title,
            created_at=r.created_at,
            updated_at=r.updated_at,
            messages=[],
        )
        for r in rows
    ]


@router.get("/ai-assistant/conversations/{conversation_id}/messages", response_model=list[AIAssistantMessageResponse])
def list_ai_assistant_messages(
    conversation_id: str,
    user: dict = Depends(require_permission("system.ai_assistant_chat.use")),
    db: Session = Depends(get_db),
):
    chat = AIAssistantChatService(db)
    rows = chat.list_messages(conversation_id, str(user["id"]))
    return [
        AIAssistantMessageResponse(
            id=str(r.id),
            role=r.role,
            content=r.content,
            metadata_json=r.metadata_json or {},
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/ai-assistant/chat", response_model=AIAssistantConversationResponse)
def send_ai_assistant_message(
    payload: AIAssistantMessageCreate,
    user: dict = Depends(require_permission("system.ai_assistant_chat.use")),
    db: Session = Depends(get_db),
):
    chat = AIAssistantChatService(db)
    conv, _ = chat.respond(user_id=str(user["id"]), conversation_id=payload.conversation_id, message=payload.message)
    rows = chat.list_messages(str(conv.id), str(user["id"]))
    return AIAssistantConversationResponse(
        id=str(conv.id),
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            AIAssistantMessageResponse(
                id=str(r.id),
                role=r.role,
                content=r.content,
                metadata_json=r.metadata_json or {},
                created_at=r.created_at,
            )
            for r in rows
        ],
    )
