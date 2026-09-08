"""Publish the chatbot parser prompt with growth r1's addendum as NEW versions, label
unmoved (`PLAN-chatbot-growth-r1.md` Slice A, AC-905 / AC-907 / AC-908 / AC-910).

Slice A gave the tools three answers the parser has no words for: the SO-outstanding
bucket on the orders tool (`order_status = so_outstanding`), PO placed
(`crm_procurement_purchase_orders_placed_list`), and the SPO last receipt
(`crm_procurement_spo_allocations_last_receipt_list`). It also gave every list tool
`group_by` and `top_n`. Until the prompt names them, a WhatsApp customer cannot reach any
of it: the parser never emits the bucket, never emits the new domain, and never emits an
axis or a count.

`app/services/chatbot_parser_prompt.GROWTH_R1_ADDENDUM` is that text, appended to BOTH
bodies. This migration publishes both results, exactly the way `487_chatbot_warehouse_cue`
does and for the same measured reason: prod's live `production` label is on v1 = the FULL
`SEMANTIC_PARSER_PROMPT`, while the local / dev label sits on the SLIM one, so publishing
only one text reaches only one deployment.

Same immutable-versions-plus-movable-labels split as migration 475: each text lands as the
next `chatbot_semantic_parser` version with NO label. Promoting is one label move in the
admin UI and rolling back is the reverse move, so this migration changes what a customer
gets exactly nowhere until the owner decides.

Idempotent, and safe on a fresh database: ``seed_prompt_registry`` runs first so v1 and the
``production`` label exist even on an install that never saw an earlier chatbot migration,
and each publish is skipped when a version already carries that template.

The insert logic lives in module-level ``publish(session)`` so it can be called outside
alembic (e.g. to publish against the shared dev database without an ``alembic upgrade``).

Revision ID: 490_chatbot_parser_growth
Revises: 489_chatbot_crossdomain_ladder
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "490_chatbot_parser_growth"
down_revision = "489_chatbot_crossdomain_ladder"
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
            "chatbot parser growth-r1 %s prompt already published as v%s; nothing to do",
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
        "published chatbot parser growth-r1 %s prompt as v%s (%s chars); production label "
        "left on the previous version, promote by moving it",
        tag,
        next_version,
        len(template),
    )
    return next_version


def publish(session: Session) -> dict[str, int | None]:
    """Publish BOTH the FULL and SLIM growth-r1 prompt texts as new versions, each
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
    """Drop the unlabelled growth-r1 versions (FULL and SLIM).

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
