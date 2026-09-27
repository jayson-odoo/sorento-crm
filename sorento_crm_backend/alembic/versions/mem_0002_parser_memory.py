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
import importlib.util
import logging
from pathlib import Path

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

#: Stamped on the version this publishes, so `downgrade()` removes that row alone.
MARKER_KEY = "mem_0002_parser_memory"


def _load_s4():
    """`chatbot_rearch_s4`, for its body formula (the same load `chatbot_rearch_s12`
    and `sa2_r9_open_question` do). Importing a revision file runs no DDL."""
    spec = importlib.util.spec_from_file_location(
        "_mem_0002_s4", Path(__file__).resolve().parent / "chatbot_rearch_s4.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publish(session: Session) -> int | None:
    """Publish the memory-addendum prompt as the next `chatbot_semantic_parser`
    version, unless a version already carries this exact template. Returns the
    new version number, or `None` when already published.

    The body is `chatbot_rearch_s4`'s own formula (the constant plus the policy blocks
    rendered from `chatbot_domains` / `chatbot_entity_kinds`), as every parser publish
    since S4 is - a bare constant would lose the blocks the moment it was promoted.
    Merged over main's `sa2_r9_open_question`, which publishes by the same formula: in
    one combined upgrade both render the same merged constant, so that revision
    publishes it and this one finds it already there."""
    template, blocks_hash = _load_s4()._body(session)
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
            config_json={"blocks_hash": blocks_hash, MARKER_KEY: True},
            commit_message=(
                "Chatbot memory lane A: the memory addendum (history_question, "
                "profile_statements, the memory blocks). Unlabelled, promote from the "
                "Prompts page."
            ),
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
    """Drop the unlabelled version this published (by its marker), unless the owner
    has since moved a label (e.g. `production`) onto it - see `513_chatbot_parser_last_
    cost.py::downgrade` for why a labelled version is never deleted here. A version
    `sa2_r9_open_question` published first is that revision's to remove, not this one's."""
    session = Session(bind=op.get_bind())
    try:
        labelled = {
            row.version_id
            for row in session.query(AIPromptLabel)
            .join(AIPromptVersion, AIPromptVersion.id == AIPromptLabel.version_id)
            .filter(AIPromptVersion.name == PROMPT_NAME)
        }
        for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME):
            if row.id not in labelled and (row.config_json or {}).get(MARKER_KEY):
                session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
