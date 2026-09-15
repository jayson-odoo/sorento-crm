"""Publish the first re-architecture parser version, with the policy blocks in its body.

Chatbot turn re-architecture S4 (AC-1550). One NEW version of
``chatbot_semantic_parser``, UNLABELLED, whose body is the live production body with the
domain and entity-kind blocks rendered from ``chatbot_domains`` /
``chatbot_entity_kinds`` appended between two markers, and whose ``config_json`` carries
the sha256 of exactly those blocks.

The ``production`` label is NOT moved. That is the whole shape of this registry and the
reason the blocks are rendered at publish time rather than per turn: deploying this
changes nothing about how a live turn is parsed, and promoting it is one label move the
owner makes on the Prompts page once they have read the diff. AC-1552's staleness banner
compares ``config_json["blocks_hash"]`` against the rows as they stand today, so a domain
saved after this publish reads as "domain block out of date" instead of silently
rewriting a version somebody already graded.

Idempotent: a version already carrying today's hash is left alone.

Revision ID: chatbot_rearch_s4
Revises: chatbot_rearch_s0
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_seed import seed_prompt_registry
from app.services.chatbot_parser_prompt import (
    BLOCKS_BEGIN,
    BLOCKS_END,
    prompt_blocks_hash,
    render_prompt_blocks,
)

revision = "chatbot_rearch_s4"
down_revision = "chatbot_rearch_s0"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _body(session: Session) -> tuple[str, str]:
    """`(template, blocks_hash)` - the labelled body plus the rendered blocks.

    The base is whatever ``production`` points at today, so this publish ADDS the policy
    blocks to the prompt that is actually live rather than replacing it with a body
    nobody has graded.
    """
    blocks = render_prompt_blocks(session)
    label = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == PROMPT_NAME, AIPromptLabel.label == "production")
        .first()
    )
    base = ""
    if label is not None:
        current = (
            session.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).first()
        )
        base = (current.template or "") if current is not None else ""
    template = f"{base.rstrip()}\n\n{BLOCKS_BEGIN}\n{blocks}{BLOCKS_END}\n"
    return template, prompt_blocks_hash(session)


def upgrade() -> None:
    bind = op.get_bind()
    # v1 plus the production label, if this install has never seeded the key.
    seed_prompt_registry(bind)

    session = Session(bind=bind)
    try:
        template, blocks_hash = _body(session)
        already = [
            row
            for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME)
            if (row.config_json or {}).get("blocks_hash") == blocks_hash
        ]
        if already:
            logger.info(
                "chatbot parser policy blocks already published as v%s; nothing to do",
                already[0].version,
            )
            return

        versions = (
            session.query(AIPromptVersion.version)
            .filter(AIPromptVersion.name == PROMPT_NAME)
            .all()
        )
        next_version = max((int(v[0]) for v in versions), default=0) + 1
        spec = PROMPT_KEYS[PROMPT_NAME]
        session.add(
            AIPromptVersion(
                name=PROMPT_NAME,
                version=next_version,
                type="text",
                template=template,
                variables=list(spec.variables),
                config_json={"blocks_hash": blocks_hash},
                commit_message=(
                    "Turn re-architecture: domain and entity-kind blocks rendered from "
                    "chatbot_domains / chatbot_entity_kinds (AC-1550). Unlabelled - "
                    "promote from the Prompts page."
                ),
            )
        )
        session.commit()
        logger.info(
            "published chatbot parser policy blocks as v%s (%s chars, blocks_hash %s); "
            "production label left where it was",
            next_version,
            len(template),
            blocks_hash[:12],
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Drop the unlabelled version this published. A labelled one is never touched."""
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        labelled = {
            row.version_id
            for row in session.query(AIPromptLabel).filter(AIPromptLabel.name == PROMPT_NAME)
        }
        for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME):
            if row.id not in labelled and (row.config_json or {}).get("blocks_hash"):
                session.delete(row)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
