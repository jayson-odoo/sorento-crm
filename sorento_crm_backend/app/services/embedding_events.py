"""Service-layer helpers to publish embedding events."""
from __future__ import annotations

import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.services.embedding_service import EmbeddingEventService

logger = logging.getLogger(__name__)


def publish_embedding_event(
    db: Session,
    *,
    source_type: str,
    source_id: str,
    event_type: str,
    source_key: Optional[str] = None,
    source_updated_at=None,
    changed_fields: Optional[list[str]] = None,
    payload: Optional[dict] = None,
    triggered_by: Optional[str] = None,
) -> None:
    try:
        EmbeddingEventService(db).queue_event(
            source_type=source_type,
            source_id=str(source_id),
            event_type=event_type,
            source_key=source_key,
            source_updated_at=source_updated_at,
            changed_fields=changed_fields or [],
            payload=payload or {},
            triggered_by=triggered_by,
        )
    except ValueError:
        # Non-semantic change, intentionally skipped.
        return
    except Exception:
        # Never block transactional writes for embedding side effects.
        logger.exception("Failed to publish embedding event for %s:%s", source_type, source_id)
