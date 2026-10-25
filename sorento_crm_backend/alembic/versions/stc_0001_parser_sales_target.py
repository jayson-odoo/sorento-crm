"""Publish the sales target parser insert as a NEW `chatbot_semantic_parser` version, UNLABELLED
(lane SALES-TARGET-CHAT).

Base = the version whose template md5 starts with BASE_MD5 (production v63; the production-labelled
row first). The anchored section from `app.services.chatbot.prompt_inserts` is inserted before the
sales report section. No base, anchor not found exactly once, or the result already published: skip.
Never replaces a full text and never moves a label.

Revision ID: stc_0001_parser_sales_target
Revises: oihr_0010_so_remark_column
"""
from __future__ import annotations

import hashlib
import logging

from alembic import op
from sqlalchemy.orm import Session

revision = "stc_0001_parser_sales_target"
down_revision = "oihr_0010_so_remark_column"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"
#: Prefix of the md5 of production v63 (140,897 chars); compared with startswith.
BASE_MD5 = "0f3b48e6"
MARKER_KEY = "stc_0001_parser_sales_target"


def publish(bind) -> None:
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from app.services.ai_prompt_registry import PROMPT_KEYS
    from app.services.chatbot.prompt_inserts import insert_sales_target

    own = isinstance(bind, Session)
    session = bind if own else Session(bind=bind)
    try:
        rows = session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME).all()
        if not rows:
            logger.info("no %s versions, sales target insert skipped", PROMPT_NAME)
            return
        production = {
            r.version_id
            for r in session.query(AIPromptLabel).filter(
                AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production"
            )
        }
        matching = [
            r for r in rows if hashlib.md5((r.template or "").encode("utf-8")).hexdigest().startswith(BASE_MD5)
        ]
        if not matching:
            logger.info("no %s version with md5 %s, sales target insert skipped", PROMPT_NAME, BASE_MD5)
            return
        matching.sort(key=lambda r: (r.id not in production, -int(r.version)))
        base = matching[0]
        text = insert_sales_target(base.template)
        if text is None:
            logger.info("sales target insert not applicable to v%s, skipped", base.version)
            return
        if any(r.template == text for r in rows):
            logger.info("sales target prompt already published")
            return
        next_version = max(int(r.version) for r in rows) + 1
        session.add(
            AIPromptVersion(
                name=PROMPT_NAME,
                version=next_version,
                type="text",
                template=text,
                variables=list(PROMPT_KEYS[PROMPT_NAME].variables),
                config_json={MARKER_KEY: True},
                commit_message=(
                    f"SALES-TARGET-CHAT: sales target section inserted into v{base.version}. "
                    "Unlabelled, promote from the Prompts page."
                ),
            )
        )
        session.commit()
        logger.info("published sales target parser prompt as v%s, labels untouched", next_version)
    except Exception:
        session.rollback()
        raise
    finally:
        if not own:
            session.close()


def upgrade() -> None:
    publish(op.get_bind())


def downgrade() -> None:
    """Drop the unlabelled version this published. A labelled version is never touched."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

    session = Session(bind=op.get_bind())
    try:
        labelled = {r.version_id for r in session.query(AIPromptLabel).filter(AIPromptLabel.name == PROMPT_NAME)}
        for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME):
            if row.id not in labelled and (row.config_json or {}).get(MARKER_KEY):
                session.delete(row)
        session.commit()
    finally:
        session.close()
