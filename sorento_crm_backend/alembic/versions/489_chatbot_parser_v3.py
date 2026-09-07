"""Publish parser prompt v3 as a NEW version, label unmoved (growth r1 slice B2).

v3 is the prompt that stops the parser CARRYING and makes it EXTRACT. It removes every
instruction that told the model to continue the previous domain or re-emit previous
entities (BARE ENTITY CONTINUATION, "keep the previous domain", the previous-state
re-emission) and adds three keys the deterministic dialogue rules read:
`answers_open_question`, `anaphora` and `topic_reset`. The text and the nine edits that
derive it from the SLIM prompt are in `app/services/chatbot_parser_prompt.py`.

**Published, NOT promoted**, exactly as migrations 475, 480 and 487 published theirs: the
new text lands as the next `chatbot_semantic_parser` version with NO label, so this
migration reaching production changes no customer's turn. Promotion is one label move in
the admin UI and it is the OWNER's step, gated on AC-952 (a 3 to 7 day shadow window at
branch parity 99%+ and reply parity 97%+ on turns with no open question) and on the
dialogue lane's console pass, which AC-991 says blocks promotion regardless of the shadow
numbers. Rolling back is the reverse label move.

Idempotent, and safe on a fresh database: `seed_prompt_registry` runs first so v1 and the
`production` label exist even on an install that never saw an earlier chatbot migration,
and the publish is skipped when a version already carries this template.

The insert logic lives in module-level ``publish(session)`` so it can be called outside
alembic (e.g. to publish against the shared dev database without an ``alembic upgrade``),
the same shape 487 uses.

Revision ID: 489_chatbot_parser_v3
Revises: 488_chatbot_focus_ttl
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_seed import seed_prompt_registry

revision = "489_chatbot_parser_v3"
down_revision = "488_chatbot_focus_ttl"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _v3_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT_V3

    return SEMANTIC_PARSER_PROMPT_V3


def publish(session: Session) -> int | None:
    """Publish v3 as the next version unless a version already carries it.

    Returns the new version number, or None when it was already published.
    """
    template = _v3_text()
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
            "chatbot parser v3 prompt already published as v%s; nothing to do",
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
        "published chatbot parser v3 (extract-only) as v%s (%s chars); every label left "
        "where it was, promote by moving one",
        next_version,
        len(template),
    )
    return next_version


def upgrade() -> None:
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
    """Drop the unlabelled v3 version.

    A version this migration published can stop being unlabelled: the owner may have since
    moved a label onto it. `AIPromptLabel.version_id` is `ondelete="CASCADE"`
    (`app/models/ai_prompt.py`), so deleting a labelled version would silently delete the
    label row with it, and a downgrade must never do that. Any version carrying a label is
    therefore left alone, which is the same rule 487's downgrade applies.
    """
    bind = op.get_bind()
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
            AIPromptVersion.template == _v3_text(),
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
