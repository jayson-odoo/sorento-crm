"""Publish the chatbot parser prompt with the warehouse-arrival cue as a NEW version,
label unmoved (owner report, 7 Sep 2026).

"IBWB248什么时候会到仓库？", "when will IBWB248 arrive at the warehouse" and "bila IBWB248
sampai gudang" all parsed to `requested_attributes: ["estimated_arrival_date"]` instead of
`["warehouse_arrival_date"]`: the vocabulary line for `warehouse_arrival_date` carried no
cue at all, so `estimated_arrival_date` (which owned the bare word "arrival") matched
instead. `app/services/chatbot_parser_prompt.py` now gives `warehouse_arrival_date` its own
warehouse/CJK/Malay cue and narrows `estimated_arrival_date` to port ETA phrasing.

Prod's live `production` label is v1 = the FULL `SEMANTIC_PARSER_PROMPT` (S1b's SLIM prompt
has never been promoted there), so publishing only the SLIM text - as this migration first
did - never reaches prod. Both constants carry the same fix, so both are published: the FULL
prompt's fixed text as a new version (the one prod's admin actually promotes), and the SLIM
prompt's fixed text as a new version (matching the local/dev `production` label).

Same immutable-versions-plus-movable-labels split as migration 475: this lands each corrected
text as the next `chatbot_semantic_parser` version with NO label, so promoting is one label
move in the admin UI and rolling back is the reverse move.

Idempotent, and safe on a fresh database: ``seed_prompt_registry`` runs first so v1 and the
``production`` label exist even on an install that never saw an earlier chatbot migration, and
each publish is skipped when a version already carries that template.

The insert logic lives in module-level ``publish(session)`` so it can be called outside
alembic (e.g. to publish against the shared dev database without an ``alembic upgrade``).

Revision ID: 482_chatbot_warehouse_cue
Revises: 477_spo_alloc_container_number
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_seed import seed_prompt_registry

revision = "482_chatbot_warehouse_cue"
down_revision = "477_spo_alloc_container_number"
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
    """Publish ``template`` as the next `chatbot_semantic_parser` version, unless a
    version already carries it. Returns the new version number, or None when already
    published. ``tag`` is only for the log line (``"full"`` or ``"slim"``)."""
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
            "chatbot parser warehouse-cue %s prompt already published as v%s; nothing to do",
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
        "published chatbot parser warehouse-cue %s prompt as v%s (%s chars); production label "
        "left on the previous version, promote by moving it",
        tag,
        next_version,
        len(template),
    )
    return next_version


def publish(session: Session) -> dict[str, int | None]:
    """Publish BOTH the FULL and SLIM warehouse-cue prompt texts as new versions, each
    idempotent on template equality. Returns ``{"full": v|None, "slim": v|None}``; a
    second call on an already-published database returns both None."""
    return {
        "full": _publish_one(session, _full_text(), "full"),
        "slim": _publish_one(session, _slim_text(), "slim"),
    }


def upgrade() -> None:
    bind = op.get_bind()
    # v1 from the fallback (the live text) plus the production label, if absent.
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
    """Drop the unlabelled warehouse-cue versions (FULL and SLIM). The labelled one is
    never touched."""
    bind = op.get_bind()
    templates = [_full_text(), _slim_text()]
    session = Session(bind=bind)
    try:
        (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == PROMPT_NAME,
                AIPromptVersion.template.in_(templates),
            )
            .delete(synchronize_session=False)
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
