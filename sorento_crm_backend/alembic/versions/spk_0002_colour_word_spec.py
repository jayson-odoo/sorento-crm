"""The parser prompt's round 9 words, as a NEW `chatbot_semantic_parser` version with the
production label unmoved (fix round 9 on PR #833).

Owner hand test, 28 Sep 2026 (console :3083): "any pnk water closet?" was read as the
product type "pnk water closet", so the reply said a product type back instead of a
colour. Which word is a colour cannot be decided in code without a hand-kept word list
(`chatbot/head/grounding.py` binds only what the specification registry holds, and
"pink" is none of its choices), so the prompt says it: a colour or finish word said on its
own, misspelt or not on the list, is a finish specification with the word spelt right.
The same addendum says a domain word alone ("cert?") keeps the subject of the ask before
it; the code carries it either way (`turn_runtime.with_carried_entities`).

Body: `chatbot_rearch_s4`'s formula, exactly as `spk_0001_specification_kind` publishes
it (the constant, ending in `SPECIFICATION_ADDENDUM`, plus the registry-rendered policy
blocks). No label: promoting is one label move on the Prompts page. Idempotent: skipped
when the newest version already carries exactly this template (a fresh database, where
spk_0001 already published the current words, publishes nothing here).

Revision ID: spk_0002_colour_word_spec
Revises: spk_0001_specification_kind
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from alembic import op
from sqlalchemy.orm import Session

revision = "spk_0002_colour_word_spec"
down_revision = "spk_0001_specification_kind"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"
#: Stamped on the version this publishes, so `downgrade()` removes that row alone.
MARKER_KEY = "spk_0002_colour_word_spec"


def _load_spk_0001():
    spec = importlib.util.spec_from_file_location(
        "_spk_0002_spk_0001", Path(__file__).resolve().parent / "spk_0001_specification_kind.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publish(bind) -> None:
    from app.models.ai_prompt import AIPromptVersion
    from app.services.ai_prompt_registry import PROMPT_KEYS
    from app.services.ai_prompt_seed import seed_prompt_registry

    spk_0001 = _load_spk_0001()
    seed_prompt_registry(bind)
    spk_0001.insert_kind(bind)
    session = Session(bind=bind)
    try:
        template, blocks_hash = spk_0001._load_s4()._body(session)
        latest = (
            session.query(AIPromptVersion)
            .filter(AIPromptVersion.name == PROMPT_NAME)
            .order_by(AIPromptVersion.version.desc())
            .first()
        )
        if latest is not None and latest.template == template:
            logger.info("chatbot parser round 9 prompt already published as v%s", latest.version)
            return
        next_version = (int(latest.version) if latest is not None else 0) + 1
        session.add(
            AIPromptVersion(
                name=PROMPT_NAME,
                version=next_version,
                type="text",
                template=template,
                variables=list(PROMPT_KEYS[PROMPT_NAME].variables),
                config_json={"blocks_hash": blocks_hash, MARKER_KEY: True},
                commit_message=(
                    "PR #833 fix round 9: a colour word on its own, misspelt or not on the "
                    "list, is a finish specification. Unlabelled, promote from the Prompts page."
                ),
            )
        )
        session.commit()
        logger.info(
            "published chatbot parser round 9 prompt as v%s (%s chars); production label left where it was",
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
    """Drop the unlabelled version this published. A labelled version is never touched."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

    session = Session(bind=op.get_bind())
    try:
        labelled = {row.version_id for row in session.query(AIPromptLabel).filter(AIPromptLabel.name == PROMPT_NAME)}
        for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME):
            if row.id not in labelled and (row.config_json or {}).get(MARKER_KEY):
                session.delete(row)
        session.commit()
    finally:
        session.close()
