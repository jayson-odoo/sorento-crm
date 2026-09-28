"""Publish the chatbot parser prompt with the semantic escalation confirmation as a NEW
version, label unmoved (issue #1323).

`ai_prompt_registry.render()` reads the PUBLISHED row, not the Python constant, so the
new `ESCALATION_CONFIRMATION_ADDENDUM` (`escalation.is_escalation_confirmation` is the
ONE semantic verdict that the person agrees to be handed to a human, for every offer
shape, false whenever the message brings its own question; `is_affirmative` stays the
AFFIRMATION rule and is NOT that verdict) reaches a live turn only once a published
version carries it. The engine half (`turn/decide.py` accepts an escalation offer only
on that verdict) is live on deploy.

The body is `chatbot_rearch_s4`'s own formula (the constant plus the policy blocks
rendered from `chatbot_domains` / `chatbot_entity_kinds`), loaded from that revision,
never a second copy of it. Same immutable-versions-plus-movable-labels split as 475 and
`sa2_r9_open_question`: the text lands as the next `chatbot_semantic_parser` version
after whatever the database already holds, with NO label, so promoting is one label
move on the Prompts page and rolling back is the reverse move.

Idempotent, and safe on a fresh database: `seed_prompt_registry` runs first, and the
publish is skipped when a version already carries exactly this template.
`publish(bind)` is module-level so it can be called outside alembic.

Revision ID: chatbot_esc_confirm_1323
Revises: identity_0001_s0_model
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_seed import seed_prompt_registry

revision = "chatbot_esc_confirm_1323"
down_revision = "identity_0001_s0_model"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"

#: Stamped on the version this publishes, so `downgrade()` removes that row alone.
MARKER_KEY = "chatbot_esc_confirm_1323"


def _load_s4():
    """`chatbot_rearch_s4`, for its body formula (the same load `sa2_r9_open_question`
    does). Importing a revision file runs no DDL."""
    spec = importlib.util.spec_from_file_location(
        "_esc_confirm_1323_s4", Path(__file__).resolve().parent / "chatbot_rearch_s4.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publish(bind) -> None:
    seed_prompt_registry(bind)
    session = Session(bind=bind)
    try:
        template, blocks_hash = _load_s4()._body(session)
        existing = (
            session.query(AIPromptVersion)
            .filter(AIPromptVersion.name == PROMPT_NAME, AIPromptVersion.template == template)
            .first()
        )
        if existing is not None:
            logger.info(
                "chatbot parser escalation-confirmation prompt already published as v%s; "
                "nothing to do",
                existing.version,
            )
            return
        versions = (
            session.query(AIPromptVersion.version).filter(AIPromptVersion.name == PROMPT_NAME).all()
        )
        next_version = max((int(v[0]) for v in versions), default=0) + 1
        session.add(
            AIPromptVersion(
                name=PROMPT_NAME,
                version=next_version,
                type="text",
                template=template,
                variables=list(PROMPT_KEYS[PROMPT_NAME].variables),
                config_json={"blocks_hash": blocks_hash, MARKER_KEY: True},
                commit_message=(
                    "#1323: escalation.is_escalation_confirmation is the one semantic "
                    "verdict for a handover, for every offer shape; is_affirmative is not. "
                    "Unlabelled, promote from the Prompts page."
                ),
            )
        )
        session.commit()
        logger.info(
            "published chatbot parser escalation-confirmation prompt as v%s (%s chars); "
            "production label left where it was",
            next_version,
            len(template),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upgrade() -> None:
    publish(op.get_bind())


def downgrade() -> None:
    """Drop the unlabelled version this published. A labelled one is never touched."""
    session = Session(bind=op.get_bind())
    try:
        labelled = {
            row.version_id
            for row in session.query(AIPromptLabel).filter(AIPromptLabel.name == PROMPT_NAME)
        }
        for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME):
            if row.id not in labelled and (row.config_json or {}).get(MARKER_KEY):
                session.delete(row)
        session.commit()
    finally:
        session.close()
