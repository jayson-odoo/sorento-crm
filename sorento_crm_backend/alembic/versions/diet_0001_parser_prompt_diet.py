"""Publish the slimmer chatbot parser prompt as a NEW unlabelled version (PROMPT-RULES-DIET,
documentation/plans/chatbot/PLAN-prompt-rules-diet-26oct.md).

The production-labelled `chatbot_semantic_parser` text, list-free first when it is not yet, then the
measured wording edits of `app/services/chatbot_prompt_diet_edits.py` (129,651 chars to 102,402, owner ruling 26 Oct).
The label never moves; promoting is one label move in the Chatbot Console.

Idempotent: a version already carrying this exact template publishes nothing. An anchor missing or
found twice publishes nothing and logs why; the upgrade still succeeds.

Revision ID: diet_0001_parser_prompt_diet
Revises: stc_0003_opp_log_slug
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "diet_0001_parser_prompt_diet"
down_revision = "stc_0003_opp_log_slug"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"
MESSAGE = (
    "PROMPT-RULES-DIET: the list-free production parser text trimmed by measured wording edits "
    "(102,402 chars, owner ruling 26 Oct). Unlabelled, promote from the Chatbot Console."
)


def publish_on_production(session: Session) -> int | None:
    """The production-labelled text, edited, as a new UNLABELLED version; its number, or None when there
    is no production label, the edit does not apply, or this text is already published."""
    from app.models.ai_prompt import AIPromptVersion
    from app.services import chatbot_prompt_diet_edits as prompt_diet_edits

    row = session.execute(
        sa.text(
            "SELECT v.template, v.variables FROM ai_prompt_versions v JOIN ai_prompt_labels l "
            "ON l.version_id = v.id WHERE l.name = :n AND l.label = 'production'"
        ),
        {"n": PROMPT_NAME},
    ).first()
    if row is None:
        logger.warning("diet_0001: no production-labelled parser version, nothing published")
        return None
    template = prompt_diet_edits.build(row[0])
    if template is None:
        logger.warning("diet_0001: the production parser text does not take the edits (anchor missing or doubled), nothing published")
        return None
    if session.query(AIPromptVersion.version).filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.template == template).first():
        logger.info("diet_0001: this text is already published")
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == PROMPT_NAME).all()
    next_version = max((int(v[0]) for v in versions), default=0) + 1
    session.add(
        AIPromptVersion(
            name=PROMPT_NAME,
            version=next_version,
            type="text",
            template=template,
            variables=list(row[1] or ["current_date"]),
            config_json={"wording_edit": True},
            commit_message=MESSAGE,
        )
    )
    session.flush()
    logger.info("diet_0001: published chatbot_semantic_parser v%s, label unmoved", next_version)
    return next_version


def upgrade() -> None:
    session = Session(bind=op.get_bind())
    try:
        publish_on_production(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Drop only the unlabelled versions this migration published (its own commit message); a labelled one stays."""
    op.get_bind().execute(
        sa.text(
            "DELETE FROM ai_prompt_versions WHERE name = :n AND commit_message = :m "
            "AND id NOT IN (SELECT version_id FROM ai_prompt_labels)"
        ),
        {"n": PROMPT_NAME, "m": MESSAGE},
    )
