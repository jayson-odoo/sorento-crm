"""Publish the chatbot parser prompt with the memory addendum as a NEW version,
label unmoved (chatbot memory lane A, contract section 6.4/6.5/8 ruling 6).

`app/services/chatbot_parser_prompt.MEMORY_ADDENDUM` teaches the parser two new
OUTPUT keys (`message_type: "history_question"`, `profile_statement`) and how to
read the three memory blocks the S3 engine now assembles ("About this contact",
"Recent conversations", "Earlier in this conversation") - what they mean, the
reference-resolution order, and that memory never overrides the current message.
Until the prompt names them, the provider never emits either key.

Same shape as `513_chatbot_parser_last_cost.py`: the text lands as the next
`chatbot_semantic_parser` version with NO label move. Promoting is one label move
in the admin UI; this migration changes what a customer gets exactly nowhere
until the owner decides. The production label stays pinned throughout.

Idempotent, and safe on a fresh database: `seed_prompt_registry` runs first so v1
and the `production` label exist even on an install that never saw an earlier
chatbot migration, and the publish is skipped when a version already carries this
exact template.

Revision ID: mem_0002_parser_memory
Revises: mem_0001_frames_level
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "mem_0002_parser_memory"
down_revision = "mem_0001_frames_level"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _full_text() -> str:
    from app.services.chatbot_parser_prompt import SEMANTIC_PARSER_PROMPT

    return SEMANTIC_PARSER_PROMPT


def publish(session: Session) -> int | None:
    """Publish the memory-addendum prompt as the next `chatbot_semantic_parser`
    version, unless a version already carries this exact template. Returns the
    new version number, or `None` when already published."""
    template = _full_text()
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
            "chatbot parser memory prompt already published as v%s; nothing to do",
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
        "published chatbot parser memory prompt as v%s (%s chars); production "
        "label left on the previous version, promote by moving it",
        next_version,
        len(template),
    )
    return next_version


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
    """Drop the unlabelled memory-prompt version, unless the owner has since
    moved a label (e.g. `production`) onto it - see `513_chatbot_parser_last_
    cost.py::downgrade` for why a labelled version is never deleted here."""
    bind = op.get_bind()
    template = _full_text()
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
            AIPromptVersion.template == template,
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
