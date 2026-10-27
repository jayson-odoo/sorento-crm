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

from app.services.chatbot.head.span_extract import MEANING_PARAGRAPH

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
EMBEDDER_PROMPT = "chatbot_lookup_embedder"
EMBEDDER_MESSAGE = "ENTITY-EXTRACT-MATCH S3: the lookup embedder prompt key (label only: provider and model)."


def seed_embedder_prompt(session: Session) -> None:
    """`chatbot_lookup_embedder` v1 from its code fallback with a production label whose provider and model are
    unset (OpenAI text-embedding-3-small), so the AI prompt settings model control works; an existing label is
    left alone and nothing moves."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services.ai_prompt_registry import PROMPT_KEYS

    if session.query(AIPromptLabel).filter(AIPromptLabel.name == EMBEDDER_PROMPT, AIPromptLabel.label == "production").first():
        return
    spec = PROMPT_KEYS[EMBEDDER_PROMPT]
    version = session.query(AIPromptVersion).filter(AIPromptVersion.name == EMBEDDER_PROMPT, AIPromptVersion.version == 1).first()
    if version is None:
        version = AIPromptVersion(
            name=EMBEDDER_PROMPT, version=1, type="text", template=spec.fallback(), variables=list(spec.variables),
            commit_message=EMBEDDER_MESSAGE,
        )
        session.add(version)
        session.flush()
    session.add(AIPromptLabel(name=EMBEDDER_PROMPT, label="production", version_id=version.id))
    session.flush()


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
        seed_embedder_prompt(session)
        publish_meaning_version(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt_labels WHERE name = :n AND provider IS NULL AND model IS NULL AND version_id IN "
            "(SELECT id FROM ai_prompt_versions WHERE name = :n AND commit_message = :m)"
        ),
        {"n": EMBEDDER_PROMPT, "m": EMBEDDER_MESSAGE},
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m "
            "AND id NOT IN (SELECT version_id FROM ai_prompt_labels)"
        ),
        {"n": EMBEDDER_PROMPT, "m": EMBEDDER_MESSAGE},
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m "
            "AND id NOT IN (SELECT version_id FROM ai_prompt_labels)"
        ),
        {"n": SPAN_PROMPT, "m": MESSAGE},
    )
