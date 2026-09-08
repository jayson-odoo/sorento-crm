"""Publish the chatbot parser prompt with a positional-reply guard, label unmoved.

Production turn `3114fc64-a2ef-4653-9618-f88aec724b78` (8 Sep 2026, switch-day suite, chain
mt-r0 "SRTWC85" product list, mt-r1 "2", mt-r2 "I want to talk to a human"): the parser's
RAW output for the bare reply "2", shown a `master_products` previous turn with 15 records,
was `message_type` business_query / `intent_hint` check_order / `domain_hint` order with
`entities` []. On 7 Sep (turn `b6892f83`, same carried state) the same reply was casual /
null / null, and the carry filled `master_products` correctly. The difference is
`GROWTH_R1_ADDENDUM`'s "A DELIVERY WORD PLUS A NAME IS AN ORDER ASK" section
(`app/services/chatbot_parser_prompt.py`): a bare number, seen next to nothing but the
previous turn's product list, was enough to bias the parse toward `check_order` /
`order`. The engine then hunted an ORDER for the picked product, missed, opened a member
offer to `customer_service`, and the next turn's human request hit the open-offer arm and
asked over all eight teams instead of routing straight to a human.

Owner ruling 8 Sep 2026 (relayed by the n8n switch lane): keep the `production` label where
it is, add a guard to that text, republish as new versions. This migration alone changes
nothing about how a turn is parsed until the owner moves the label; it only makes the fixed
text an existing, promotable version.

Same immutable-versions-plus-movable-labels split as migrations 475 / 480 / 487 / 490: each
text lands as the next `chatbot_semantic_parser` version with NO label. Idempotent, and safe
on a fresh database: ``seed_prompt_registry`` runs first so v1 and the ``production`` label
exist even on an install that never saw an earlier chatbot migration, and each publish is
skipped when a version already carries that template.

The insert logic lives in module-level ``publish(session)`` so it can be called outside
alembic (e.g. to publish against the shared dev database without an ``alembic upgrade``).

Revision ID: 493_chatbot_positional_guard
Revises: 492_mcp_tool_chatbot_domain
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "493_chatbot_positional_guard"
down_revision = "492_mcp_tool_chatbot_domain"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _full_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

    return SEMANTIC_PARSER_PROMPT


def _slim_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT_SLIM

    return SEMANTIC_PARSER_PROMPT_SLIM


def _publish_one(session: Session, template: str, tag: str) -> int | None:
    """Publish ``template`` as the next `chatbot_semantic_parser` version, unless a version
    already carries it. Returns the new version number, or None when already published.
    ``tag`` is only for the log line (``"full"`` or ``"slim"``)."""
    spec = PROMPT_KEYS[PROMPT_NAME]
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
            "chatbot parser positional-guard %s prompt already published as v%s; nothing to "
            "do",
            tag,
            existing.version,
        )
        return None
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
        "published chatbot parser positional-guard %s prompt as v%s (%s chars); production "
        "label left on the previous version, promote by moving it",
        tag,
        next_version,
        len(template),
    )
    return next_version


def publish(session: Session) -> dict[str, int | None]:
    """Publish BOTH the FULL and SLIM positional-guard prompt texts as new versions, each
    idempotent on template equality. Returns ``{"full": v|None, "slim": v|None}``; a
    second call on an already-published database returns both None."""
    return {
        "full": _publish_one(session, _full_text(), "full"),
        "slim": _publish_one(session, _slim_text(), "slim"),
    }


def upgrade() -> None:
    from app.services.ai_prompt_seed import seed_prompt_registry

    bind = op.get_bind()
    # v1 from the fallback plus the production label, if absent.
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
    """Drop the unlabelled positional-guard versions (FULL and SLIM).

    A version this migration published can stop being unlabelled: the owner may have since
    moved a label (e.g. `production`) onto it in the admin UI. `AIPromptLabel.version_id` is
    `ondelete="CASCADE"` (`app/models/ai_prompt.py`), so deleting a labelled version would
    silently delete the label row with it - a downgrade must never do that. Any version this
    migration published that now carries a label is therefore excluded from the delete; the
    label keeps pointing at it.
    """
    bind = op.get_bind()
    templates = [_full_text(), _slim_text()]
    session = Session(bind=bind)
    try:
        labelled_version_ids = {
            row[0]
            for row in (
                session.query(AIPromptLabel.version_id)
                .join(AIPromptVersion, AIPromptVersion.id == AIPromptLabel.version_id)
                .filter(AIPromptVersion.name == PROMPT_NAME)
                .all()
            )
        }
        query = session.query(AIPromptVersion).filter(
            AIPromptVersion.name == PROMPT_NAME,
            AIPromptVersion.template.in_(templates),
        )
        if labelled_version_ids:
            query = query.filter(AIPromptVersion.id.notin_(labelled_version_ids))
        query.delete(synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
