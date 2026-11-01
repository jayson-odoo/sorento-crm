"""SUPPLIER-ASK: publish the span extractor prompt with the supplier type, unlabelled (1 Nov 2026).

The production-labelled `chatbot_span_extractor` text plus `span_extract.with_supplier_type`: one type line naming a
supplier (a company we buy from) after the customer line, and, on a prompt that asks for meanings, one sentence that
has a company name written in Chinese characters read by its pinyin, the form supplier records are kept in. The span
type is only a tie-break (`list_resolver`), so the Supplier rows resolve without it; this makes the span model name
supplier mentions and bridge a native-script name to its record. The production label stays where it is; the owner
moves it after the chatbot eval. Idempotent: the same template, or a version with this commit message, publishes
nothing. Downgrade removes only the unlabelled version this migration made.

Revision ID: sask_0002_span_supplier
Revises: sask_0001_supplier_kind
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "sask_0002_span_supplier"
down_revision = "sask_0001_supplier_kind"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

SPAN_PROMPT = "chatbot_span_extractor"
MESSAGE = "SUPPLIER-ASK: the span extractor prompt with the supplier type. Unlabelled; move the production label to try it."


def publish(session: Session) -> int | None:
    """The production span prompt with the supplier edit as the next UNLABELLED version; its number, or None when
    there is no production label, the edit does not apply, or this text is already published."""
    from app.models.ai_prompt import AIPromptVersion
    from app.services.chatbot.head.span_extract import with_supplier_type

    row = session.execute(
        sa.text(
            "SELECT v.template, v.variables FROM ai_prompt_versions v JOIN ai_prompt_labels l "
            "ON l.version_id = v.id WHERE l.name = :n AND l.label = 'production'"
        ),
        {"n": SPAN_PROMPT},
    ).first()
    if row is None:
        logger.warning("sask_0002: no production-labelled span prompt, nothing published")
        return None
    template = with_supplier_type(row[0] or "")
    if template is None:
        logger.warning("sask_0002: the production span prompt does not take the edit, nothing published")
        return None
    if session.query(AIPromptVersion.version).filter(
        AIPromptVersion.name == SPAN_PROMPT,
        (AIPromptVersion.template == template) | (AIPromptVersion.commit_message == MESSAGE),
    ).first():
        logger.info("sask_0002: this text is already published, nothing published")
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == SPAN_PROMPT).all()
    next_version = max((int(v[0]) for v in versions), default=0) + 1
    session.add(
        AIPromptVersion(
            name=SPAN_PROMPT, version=next_version, type="text", template=template,
            variables=list(row[1] or []), commit_message=MESSAGE,
        )
    )
    session.flush()
    logger.info("sask_0002: published chatbot_span_extractor v%s, label unmoved", next_version)
    return next_version


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        publish(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m "
            "AND id NOT IN (SELECT version_id FROM ai_prompt_labels)"
        ),
        {"n": SPAN_PROMPT, "m": MESSAGE},
    )
