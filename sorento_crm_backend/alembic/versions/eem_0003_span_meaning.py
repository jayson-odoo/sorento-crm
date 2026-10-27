"""Publish the span extractor prompt v2 with the "meaning" instruction, unlabelled (ENTITY-EXTRACT-MATCH S3).

v2 is the production-labelled `chatbot_span_extractor` text plus one paragraph asking for a per-span plain English
"meaning" (sizes in millimetres). The production label stays where it is; the owner moves it on the copy to try
the semantic bridge. Idempotent: the same template, or a version with this commit message, publishes nothing.
Downgrade removes only the unlabelled version this migration made.

Revision ID: eem_0003_span_meaning
Revises: eem_0002_span_version_on_diet
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "eem_0003_span_meaning"
down_revision = "eem_0002_span_version_on_diet"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

SPAN_PROMPT = "chatbot_span_extractor"
MESSAGE = (
    "ENTITY-EXTRACT-MATCH S3: the span extractor prompt with a per-span plain English meaning. "
    "Unlabelled; move the production label to try it."
)
MEANING_PARAGRAPH = (
    "\n\nFor each span also give \"meaning\". When the span is written in a language other than English, or gives a "
    "measurement in a unit other than millimetres, \"meaning\" is the plain English form of the span, with any size "
    "in millimetres written as a number followed by mm. When the span is already English and needs no conversion, "
    "or you are not sure what it means, \"meaning\" is null. Never invent a meaning."
)


def publish_meaning_version(session: Session) -> int | None:
    """The production span prompt plus the meaning paragraph as the next UNLABELLED version; its number, or None
    when there is no production label or this text is already published."""
    from app.models.ai_prompt import AIPromptVersion

    row = session.execute(
        sa.text(
            "SELECT v.template, v.variables FROM ai_prompt_versions v JOIN ai_prompt_labels l "
            "ON l.version_id = v.id WHERE l.name = :n AND l.label = 'production'"
        ),
        {"n": SPAN_PROMPT},
    ).first()
    if row is None:
        logger.warning("eem_0003: no production-labelled span prompt, nothing published")
        return None
    template = (row[0] or "").rstrip() + MEANING_PARAGRAPH
    if session.query(AIPromptVersion.version).filter(
        AIPromptVersion.name == SPAN_PROMPT,
        (AIPromptVersion.template == template) | (AIPromptVersion.commit_message == MESSAGE),
    ).first():
        logger.info("eem_0003: this text is already published, nothing published")
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == SPAN_PROMPT).all()
    next_version = max((int(v[0]) for v in versions), default=0) + 1
    session.add(
        AIPromptVersion(
            name=SPAN_PROMPT,
            version=next_version,
            type="text",
            template=template,
            variables=list(row[1] or []),
            commit_message=MESSAGE,
        )
    )
    session.flush()
    logger.info("eem_0003: published chatbot_span_extractor v%s, label unmoved", next_version)
    return next_version


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        publish_meaning_version(session)
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
