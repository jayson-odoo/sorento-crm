"""Publish the parser prompt with the S4 history words as a NEW version, label
unmoved, and seed the S4 reply templates (chatbot memory S4, PR #1304 round 4).

The owner's hand test of round 3 (28 Sep 2026): "what do i normally ask about" came
back `message_type: "clarification"` and got the clarify menu. `MEMORY_ADDENDUM` now
names the history question in any wording (with its hints null, never
"clarification"), how a bare number re-runs a line of the numbered history reply, and
`intent_hint: "commercial_request"` for a discount, credit or price-exception ask.

Same publish as `mem_0002_parser_memory` (the `chatbot_rearch_s4._body` formula: the
constant plus the rendered policy blocks), with its own marker so `downgrade()`
removes only what this published. On a database that runs both revisions in one
upgrade, `mem_0002` already renders today's constant, so this finds the text there
and publishes nothing. On a database already at `mem_0002` (the shared hand-test DB),
this is the version that carries the new words. Promoting it is one label move on the
Prompts page; the `production` label stays where it is.

`seed_prompt_registry` also seeds the new `chatbot_reply_*` S4 templates (and their
`.ms` / `.zh` keys) at v1 from their fallbacks, so the owner can edit them; it is
idempotent and touches no existing key.

Revision ID: mem_0003_parser_history
Revises: mem_0002_parser_memory
"""
import importlib.util
import logging
from pathlib import Path

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS

revision = "mem_0003_parser_history"
down_revision = "mem_0002_parser_memory"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"

#: Stamped on the version this publishes, so `downgrade()` removes that row alone.
MARKER_KEY = "mem_0003_parser_history"


def _load_s4():
    """`chatbot_rearch_s4`, for its body formula (the same load `mem_0002_parser_memory`
    does). Importing a revision file runs no DDL."""
    spec = importlib.util.spec_from_file_location(
        "_mem_0003_s4", Path(__file__).resolve().parent / "chatbot_rearch_s4.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publish(session: Session) -> int | None:
    """Publish the rendered prompt as the next `chatbot_semantic_parser` version,
    unless a version already carries this exact template. Returns the new version
    number, or `None` when already published."""
    template, blocks_hash = _load_s4()._body(session)
    spec = PROMPT_KEYS[PROMPT_NAME]
    existing = (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.template == template)
        .first()
    )
    if existing is not None:
        logger.info("chatbot parser history prompt already published as v%s; nothing to do", existing.version)
        return None
    versions = session.query(AIPromptVersion.version).filter(AIPromptVersion.name == PROMPT_NAME).all()
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
                "Chatbot memory S4: history_question in any wording, a bare number re-runs "
                "a history line, commercial_request. Unlabelled, promote from the Prompts page."
            ),
        )
    )
    session.commit()
    logger.info(
        "published chatbot parser history prompt as v%s (%s chars); production label left "
        "on the previous version, promote by moving it",
        next_version,
        len(template),
    )
    return next_version


def upgrade() -> None:
    from app.services.ai_prompt_seed import seed_prompt_registry

    bind = op.get_bind()
    # v1 plus the production label for every registered key that lacks one: the S4
    # reply templates, and the parser's own v1 on an install that never had it.
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
    """Drop the unlabelled version this published (by its marker), unless a label has
    since moved onto it. The seeded reply templates stay: dropping them would strip an
    edit the owner may have published on top (`515_chatbot_offer_declined_copy`)."""
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
