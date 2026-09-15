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

Idempotent: a version whose FULL rendered template (instruction block plus policy
blocks) already matches today's is left alone - not just a `blocks_hash` match, since
this migration's own instruction paragraph below can change without the policy tables
moving at all (16 Sep 2026 amendment, AC-1317: the `continuation` output key).

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

# Amended 16 Sep 2026 (AC-1317): the parser gains a `continuation` output key
# (`head/parser.py`'s schema) - `turn/apply.py::_is_continuation` now reads that key
# only, having retired the old free-text `user_goal` word-list match. One instruction
# paragraph, marked the same way the policy blocks are, so it is easy to find and drop
# once the schema itself is the only place this is documented.
OUTPUT_KEYS_BEGIN = "<<<CHATBOT OUTPUT KEYS>>>"
OUTPUT_KEYS_END = "<<<END CHATBOT OUTPUT KEYS>>>"
CONTINUATION_INSTRUCTION = (
    'Emit an additional boolean key "continuation" on every response: true when the '
    "current message asks for MORE of the set the previous answer counted or listed "
    '(e.g. "more", "next", "lagi", "show more"), false otherwise.\n'
)

logger = logging.getLogger("alembic.runtime.migration")

PROMPT_NAME = "chatbot_semantic_parser"


def _body(session: Session) -> tuple[str, str]:
    """`(template, blocks_hash)` - the labelled body plus the output-keys instruction
    plus the rendered policy blocks.

    The base is whatever ``production`` points at today, so this publish ADDS to the
    prompt that is actually live rather than replacing it with a body nobody has
    graded. Any OUTPUT KEYS / POLICY BLOCKS section the base already carries (from a
    PRIOR run of this same migration having been promoted to production) is stripped
    first, so re-running never nests one inside another.
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
    for begin, end in ((OUTPUT_KEYS_BEGIN, OUTPUT_KEYS_END), (BLOCKS_BEGIN, BLOCKS_END)):
        if begin in base and end in base:
            head, _, tail = base.partition(begin)
            _, _, tail = tail.partition(end)
            base = head.rstrip() + tail
    template = (
        f"{base.rstrip()}\n\n{OUTPUT_KEYS_BEGIN}\n{CONTINUATION_INSTRUCTION}{OUTPUT_KEYS_END}\n"
        f"\n{BLOCKS_BEGIN}\n{blocks}{BLOCKS_END}\n"
    )
    return template, prompt_blocks_hash(session)


def upgrade() -> None:
    bind = op.get_bind()
    # v1 plus the production label, if this install has never seeded the key.
    seed_prompt_registry(bind)

    session = Session(bind=bind)
    try:
        template, blocks_hash = _body(session)
        # `blocks_hash` alone under-counts: it covers the POLICY BLOCKS, not the output
        # keys instruction above them, so a change to the instruction with the policy
        # tables untouched must still republish. Full-template equality is the correct
        # "nothing would change" check for both.
        already = [
            row
            for row in session.query(AIPromptVersion).filter(AIPromptVersion.name == PROMPT_NAME)
            if (row.config_json or {}).get("blocks_hash") == blocks_hash and row.template == template
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
