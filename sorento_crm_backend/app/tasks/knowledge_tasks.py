"""Read one uploaded document for the AI on the worker (AGENTIC-KNOWLEDGE P1).

Runs on the ``knowledge`` batch queue (``worker.QUEUES``), so a long OCR read never delays chatbot
media. The attachment row is the record: every outcome ends as ``done``, ``failed`` or ``unsupported`` on ``ai_read_status`` and
the task never re-raises. A restart of the Worker is needed after editing this file.
"""
from __future__ import annotations

import logging

from app.database import SessionLocal

logger = logging.getLogger(__name__)


def read_attachment_job(attachment_id: str) -> dict:
    from app.services import knowledge_service

    db = SessionLocal()
    try:
        knowledge_service.read_attachment(db, attachment_id)
        return {"attachment_id": attachment_id}
    except Exception:  # noqa: BLE001 - read_attachment records file problems itself
        logger.exception("knowledge read job crashed for %s", attachment_id)
        db.rollback()
        return {"attachment_id": attachment_id, "error": True}
    finally:
        db.close()
