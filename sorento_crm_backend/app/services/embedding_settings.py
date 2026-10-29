"""Which embedder the lookup lists use, and which model the records-search vectors were built with
(LOOKUP-EMBED-CENTRAL, AC-LEC-3). Both live on `system_settings`."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import SystemSetting

DEFAULT_EMBEDDER = ("openai", "text-embedding-3-small")
EMBEDDER_PROMPT_KEY = "chatbot_lookup_embedder"


def resolve_embedder(db: Session) -> tuple[str, str]:
    """(provider, model): the setting when both are set, else the production label of prompt key
    `chatbot_lookup_embedder`, else OpenAI `text-embedding-3-small`."""
    from app.services import ai_prompt_registry

    row = db.query(SystemSetting.embedding_provider, SystemSetting.embedding_model).first()
    if row is not None and row[0] and row[1]:
        return row[0], row[1]
    provider, model = ai_prompt_registry.agent_model(db, EMBEDDER_PROMPT_KEY)
    if provider and model:
        return provider, model
    return DEFAULT_EMBEDDER


def records_search_model(db: Session) -> str:
    """The model the records-search vectors were built with (written by the guard only)."""
    row = db.query(SystemSetting.embedding_records_search_model).first()
    return (row[0] if row else None) or DEFAULT_EMBEDDER[1]
