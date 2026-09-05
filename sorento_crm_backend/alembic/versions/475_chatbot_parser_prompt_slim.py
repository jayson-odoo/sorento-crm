"""Publish the S1b slim chatbot parser prompt as a NEW version, label unmoved (AC-154).

The registry's model is immutable versions plus movable labels, and this migration uses
both halves deliberately:

* version 1 stays the LIVE 46,906-character system message and keeps the ``production``
  label, so deploying this changes nothing about how a turn is parsed;
* the 28,124-character S1b text lands as the next version with NO label.

Promoting is then one label move in the admin UI, and rolling back is the reverse move,
which is the whole point of the split (the owner promotes at the S1 promote, not here).

Idempotent, and safe on a fresh database: ``seed_prompt_registry`` runs first so v1 and
the ``production`` label exist even on an install that has never seen migration 258 seed
this key, and the publish is skipped when a version already carries the same template.

Revision ID: 475_chatbot_prompt_slim
Revises: 472_chatbot_turns
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_seed import seed_prompt_registry

revision = "475_chatbot_prompt_slim"
down_revision = "472_chatbot_turns"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _slim_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT_SLIM

    return SEMANTIC_PARSER_PROMPT_SLIM


def upgrade() -> None:
    bind = op.get_bind()
    # v1 from the fallback (the live text) plus the production label, if absent.
    seed_prompt_registry(bind)

    template = _slim_text()
    spec = PROMPT_KEYS[PROMPT_NAME]
    session = Session(bind=bind)
    try:
        existing = (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == PROMPT_NAME,
                AIPromptVersion.template == template,
            )
            .first()
        )
        if existing is not None:
            logger.info(
                "chatbot parser slim prompt already published as v%s; nothing to do",
                existing.version,
            )
            return
        versions = (
            session.query(AIPromptVersion.version)
            .filter(AIPromptVersion.name == PROMPT_NAME)
            .all()
        )
        next_version = max((int(v[0]) for v in versions), default=0) + 1
        session.add(
            AIPromptVersion(
                name=PROMPT_NAME,
                version=next_version,
                type="text",
                template=template,
                variables=list(spec.variables),
            )
        )
        session.commit()
        logger.info(
            "published chatbot parser slim prompt as v%s (%s chars); production label "
            "left on the previous version, promote by moving it",
            next_version,
            len(template),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Drop the unlabelled slim version. The labelled one is never touched."""
    bind = op.get_bind()
    template = _slim_text()
    session = Session(bind=bind)
    try:
        (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == PROMPT_NAME,
                AIPromptVersion.template == template,
            )
            .delete(synchronize_session=False)
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
