"""Republish the chatbot parser prompt with the PO / SPO warehouse and sort vocabulary.

Lane PO-SPO-WAREHOUSE (owner rulings 29 Sep 2026, PR #1373;
`documentation/plans/chatbot/PLAN-po-spo-warehouse-29sep.md` M1): the word "SPO" is an SPO
allocation ask and never incoming (the OUTSTANDING block's own `"SPO" -> incoming` sentence
is corrected in the body), a short location token is a warehouse under the PO and SPO
domains too, and two new output keys, `sort_by` / `sort_dir`, carry the sort a customer
asks for ("latest PO for SRT79-SS", "SPO biggest quantity first at BRW"). All three live in
`PO_SPO_WAREHOUSE_ADDENDUM` plus the one in-body edit, so this publishes the current
`SEMANTIC_PARSER_PROMPT` as the next version after whatever the database holds.

Chains onto `merge_29sep_batch7` (#1374), the join main landed for the two heads it
carried when this lane branched (`eml_0002_seed_layouts` from #1350 and
`mem_0003_parser_history` from #1304). Nothing about the parent is read or changed here.

Idempotent the same way `chatbot_top_selling_vocab_r6` is: a database that runs the chain
in one upgrade gets the current body from the first publishing migration and this one finds
it already published and does nothing. The insert helper is repeated rather than imported,
because a migration module must not depend on another migration's module staying
importable. Nothing a customer sees changes until the owner moves the `production` label
onto the new version (the Chatbot Console's prompt version picker).

Revision ID: chatbot_po_spo_warehouse_vocab
Revises: merge_29sep_batch7
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "chatbot_po_spo_warehouse_vocab"
down_revision = "merge_29sep_batch7"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _full_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

    return SEMANTIC_PARSER_PROMPT


def publish(session: Session) -> int | None:
    """Publish the body as the next version unless one already carries it. Returns the
    new version number, or None when already published. Never moves a label."""
    template = _full_text()
    existing = (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.template == template)
        .first()
    )
    if existing is not None:
        logger.info("chatbot parser PO/SPO warehouse prompt already published as v%s", existing.version)
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
        "published chatbot parser PO/SPO warehouse prompt as v%s (%s chars); production "
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
    """Nothing to drop: the version this upgrade published carries the body the earlier
    publishing migrations' downgrades already look for, so the pair stays one owner of one
    row (the same reasoning as `chatbot_top_selling_vocab_r6`)."""
