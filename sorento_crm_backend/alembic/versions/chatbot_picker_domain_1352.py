"""Publish the chatbot parser prompt for the picker domain judgement, label unmoved
(issue #1352).

Owner, 29 Sep 2026: "the parser reports, the engine judges". The open numbered question
block no longer tells the model to answer a pick "and NOTHING else: entities [],
domain_hint null, intent_hint null, order_status null, message_type casual"; it fills
every field as the message itself says, so "4 stock" arrives as a position AND the stock
domain and the engine decides where the answer goes (`turn/decide.names_its_own_domain`,
`turn/apply._answer_pending`). Also in this text: domain_in_message true means domain_hint
is never null; a typed option code is its position AND its entity ("Never emit BOTH"
retired); and "that list was closed the moment one product was picked" is gone in favour
of the sticky roster. Plan: documentation/plans/chatbot/PLAN-picker-domain-judgement-29sep.md.

A database that already ran `chatbot_top_selling_vocab_r6` holds the older body and that
migration will not run again, so this one publishes the current `SEMANTIC_PARSER_PROMPT`
as the next version after whatever the database holds. Idempotent the same way: a
database that runs the whole chain in one upgrade gets the current body from the first
publishing migration and this one finds it already published and does nothing. The
insert helper is repeated rather than imported, because a migration module must not
depend on another migration's module staying importable. Nothing a customer sees changes
until the owner moves the `production` label onto the new version.

PR #1353 fix round 2 (merge of main at merge_29sep_batch5): the body this publishes now
also carries the parser text main's #833 (attribute-first asks) added to
`SEMANTIC_PARSER_PROMPT`, which shipped with no publishing migration of its own. Round 2
itself changes no prompt text: the engine now derives the roster axis from the picked
option (`engine._with_the_picked_axis`), so the v48 body published on the hand-test
database from this PR's round 1 still exercises the fix.

Revision ID: chatbot_picker_domain_1352
Revises: merge_29sep_batch5
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "chatbot_picker_domain_1352"
down_revision = "merge_29sep_batch5"
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
        logger.info("chatbot parser picker domain judgement prompt already published as v%s", existing.version)
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
        "published chatbot parser picker domain judgement prompt as v%s (%s chars); production "
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
    """Nothing to drop: the earliest publishing migration that finds this body missing
    owns the row it writes (`chatbot_top_selling_vocab` on a database that runs the
    chain in one upgrade, this one on a database that was already past r6), and a
    version this upgrade published may by then carry the owner's `production` label,
    which a delete would cascade away (`AIPromptLabel.version_id` is `ondelete=CASCADE`).
    The label is moved back in the admin UI; the unlabelled row is harmless."""
