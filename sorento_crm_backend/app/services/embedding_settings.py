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


#: The only sources that are embedded and searched (LOOKUP-EMBED-CENTRAL). Everything else is answered from SQL.
RECORD_KEEP_SET = frozenset({"attachment", "promotion", "certificate", "form", "product_spec", "project"})
#: Sources whose filtered reads get an index of their own (the rest rely on an iterative scan of the keep-set index).
HOT_FILTERED_SOURCES = ("attachment", "product_spec")


def provider_for_model(model: str) -> str:
    return "gemini" if str(model).startswith("gemini") else "openai"


def embed_search_texts(texts: list[str], model: str, *, timeout: float | None = None) -> list[list[float]]:
    """Embed `texts` with the records-search `model` through the one embedding client (query side of every
    reader). OpenAI uses the settings key; Gemini uses the AI assistant config's key."""
    from app.services import embedding_client

    provider = provider_for_model(model)
    api_key = None
    if provider == "gemini":
        from app.database import SessionLocal
        from app.services import llm_provider
        from app.services.ai_assistant_service import AIAssistantConfigService

        with SessionLocal() as s:
            api_key = llm_provider.resolve_api_key(AIAssistantConfigService(s).get(), "gemini")
    return embedding_client.embed_texts(texts, provider, model, api_key=api_key, timeout=timeout)
