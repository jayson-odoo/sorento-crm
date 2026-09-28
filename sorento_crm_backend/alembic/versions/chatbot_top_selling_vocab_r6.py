"""Republish the chatbot parser prompt with the top selling round 6 words, label unmoved.

Fix lane round 6 on PR #1273 (owner retest of top selling round 5, 27 Sep 2026: "top 100
sold item" then "amount" answered the order list) grew `TOP_SELLING_ADDENDUM`: "top 100
sold item(s)", "most sold item", "top selling", "top 100 hot selling item", "highest
selling", "top sellers" are the ranking ask, and an answer to the bot's own ranking
question is never a new order ask. A database that already ran
`chatbot_top_selling_vocab_r5` (the owner's local stack, parser v39) holds the older body,
and that migration will not run again, so this one publishes the current
`SEMANTIC_PARSER_PROMPT` as the next version after whatever the database holds.

Idempotent the same way `chatbot_top_selling_vocab_r5` is: a database that runs the
chain in one upgrade (production) gets the current body from the first and this one
finds it already published and does nothing. The insert helper is repeated rather than
imported, because a migration module must not depend on another migration's module
staying importable. Nothing a customer sees changes until the owner moves the
`production` label onto the new version.

Revision ID: chatbot_top_selling_vocab_r6
Revises: chatbot_top_selling_vocab_r5
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "chatbot_top_selling_vocab_r6"
down_revision = "chatbot_top_selling_vocab_r5"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _full_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

    return SEMANTIC_PARSER_PROMPT


def publish(session: Session) -> int | None:
    """Publish the body as the next version unless one already carries it. Returns the
    new version number, or None when already published."""
    template = _full_text()
    existing = (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.template == template)
        .first()
    )
    if existing is not None:
        logger.info("chatbot parser top selling round 6 prompt already published as v%s", existing.version)
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == PROMPT_NAME).all()
    next_version = max((int(v[0]) for v in versions), default=0) + 1
    session.add(
        AIPromptVersion(
            name=PROMPT_NAME,
            version=next_version,
            type="text",
            template=template,
            variables=list(PROMPT_KEYS[PROMPT_NAME].variables),
        )
    )
    session.commit()
    logger.info(
        "published chatbot parser top selling round 6 prompt as v%s (%s chars); production "
        "label left where it was, promote by moving it",
        next_version,
        len(template),
    )
    return next_version


def upgrade() -> None:
    from app.services.ai_prompt_seed import seed_prompt_registry

    bind = op.get_bind()
    seed_prompt_registry(bind)
    session = Session(bind=bind)
    try:
        publish(session)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Nothing to drop: `chatbot_top_selling_vocab`'s downgrade removes the version
    carrying this same body (unless a label points at it), and a version this upgrade
    published is that body too. Dropping it here as well would leave that downgrade
    nothing to find, so the pair stays one owner of one row."""
