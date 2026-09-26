"""Publish the chatbot parser prompt with the round 9 open-question contract as a NEW
version, label unmoved (PR #1247 round 9, issue #1293).

`ai_prompt_registry.render()` reads the PUBLISHED row, not the Python constant, so the
amended `STOCK_TASK_ADDENDUM` (every question the bot asks is one `Open question:`
object: pick_one, choose_brand, confirm, quantities, last_answer, how_many_to_show,
free; the parser answers it in `open_question_answer` with mode pick / yes / no / fill /
all / done / cancel and the positions it picked) reaches a live turn only once a
published version carries it. The strict schema key (`head/parser.py`) is live at once;
this text is what tells the model how to fill it.

The body is `chatbot_rearch_s4`'s own formula (the constant plus the policy blocks
rendered from `chatbot_domains` / `chatbot_entity_kinds`), loaded from that revision,
never a second copy of it. Same immutable-versions-plus-movable-labels split as 475: the
text lands as the next `chatbot_semantic_parser` version with NO label, so promoting is
one label move on the Prompts page and rolling back is the reverse move.

Idempotent, and safe on a fresh database: `seed_prompt_registry` runs first, and the
publish is skipped when a version already carries exactly this template.
`publish(bind)` is module-level so it can be called outside alembic.

Revision ID: sa2_r9_open_question
Revises: sales_0002_team_leader
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

revision = "sa2_r9_open_question"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"

#: Stamped on the version this publishes, so `downgrade()` removes that row alone.
MARKER_KEY = "sa2_r9_open_question"


def _load_s4():
    """`chatbot_rearch_s4`, for its body formula (the same load `chatbot_rearch_s12`
    does). Importing a revision file runs no DDL."""
    spec = importlib.util.spec_from_file_location(
        "_sa2_r9_s4", Path(__file__).resolve().parent / "chatbot_rearch_s4.py"
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
                "chatbot parser round 9 prompt already published as v%s; nothing to do",
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
                    "PR #1247 round 9: one open-question object for every question the "
                    "bot asks, answered in open_question_answer. Unlabelled, promote from "
                    "the Prompts page."
                ),
            )
        )
        session.commit()
        logger.info(
            "published chatbot parser round 9 prompt as v%s (%s chars); production label "
            "left where it was",
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
