"""Idempotent seed for the AI prompt registry.

Extracted from the alembic migration so it can be unit-tested against sqlite and
re-run safely (JOIN-based set-to-correct-value, per the backfill rule — running
it twice never spawns duplicate versions or labels).

Seeds each of the 9 PROMPT_KEYS at version 1 from its hardcoded fallback, with a
``production`` label → v1. If ``ai_assistant_configs.system_prompt`` holds a
non-empty custom value, it is seeded as ``agent_system`` v2 and ``production``
points at v2 (UAC A6 — preserve the admin's prior prompt, no silent loss).
"""
from __future__ import annotations

import logging

from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

logger = logging.getLogger(__name__)


def _get_version(session: Session, name: str, version: int) -> AIPromptVersion | None:
    return (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == name, AIPromptVersion.version == version)
        .first()
    )


def _ensure_version(
    session: Session, name: str, version: int, template: str, variables: list[str]
) -> AIPromptVersion:
    row = _get_version(session, name, version)
    if row is None:
        row = AIPromptVersion(
            name=name,
            version=version,
            type="text",
            template=template,
            variables=list(variables),
        )
        session.add(row)
        session.flush()
    return row


def _ensure_label(session: Session, name: str, label: str, version_id: str) -> None:
    row = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == name, AIPromptLabel.label == label)
        .first()
    )
    if row is None:
        session.add(AIPromptLabel(name=name, label=label, version_id=version_id))
        session.flush()


def _set_label(session: Session, name: str, label: str, version_id: str) -> None:
    row = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == name, AIPromptLabel.label == label)
        .first()
    )
    if row is None:
        session.add(AIPromptLabel(name=name, label=label, version_id=version_id))
    else:
        row.version_id = version_id
    session.flush()


def _existing_custom_system_prompt(session: Session) -> str:
    """The admin's pre-existing ``ai_assistant_configs.system_prompt`` (plain
    text), or '' if none / empty. Lazy import avoids a heavy import at module
    load and any circular import through the chat service."""
    try:
        from app.models.ai_assistant import AIAssistantConfig
        from app.services.ai_assistant_service import _html_to_text
    except Exception:  # pragma: no cover - defensive
        return ""
    cfg = (
        session.query(AIAssistantConfig)
        .order_by(AIAssistantConfig.created_at.asc())
        .first()
    )
    if cfg is None:
        return ""
    return _html_to_text(cfg.system_prompt or "").strip()


def seed_prompt_registry(bind: Connection) -> None:
    """Idempotent seed. Safe to run repeatedly."""
    session = Session(bind=bind)
    try:
        # 1) Every key at v1 from its fallback, with a production label → v1.
        for name, spec in PROMPT_KEYS.items():
            v1 = _ensure_version(session, name, 1, spec.fallback(), list(spec.variables))
            _ensure_label(session, name, "production", v1.id)

        # 2) A6: preserve a pre-existing custom agent_system prompt as v2 and
        # point production at v2.
        custom = _existing_custom_system_prompt(session)
        if custom:
            v2 = _get_version(session, "agent_system", 2)
            if v2 is None:
                v2 = _ensure_version(
                    session,
                    "agent_system",
                    2,
                    custom,
                    list(PROMPT_KEYS["agent_system"].variables),
                )
            _set_label(session, "agent_system", "production", v2.id)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
