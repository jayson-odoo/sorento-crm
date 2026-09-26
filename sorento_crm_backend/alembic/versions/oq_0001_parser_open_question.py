"""Publish the chatbot parser prompt with the open question contract as a NEW version,
label unmoved (issue #1293, PLAN-chatbot-open-question-object.md W1).

The owner, 26 Sep 2026: "I want to say 'the first one I need two' ... not too much hard
coding, hard routing." Every question the bot asks is now stated to the parser as one
`Open question: {...}` object (`app/services/chatbot/turn/question.py`), and the prompt's
"THE OPEN QUESTION AND open_question_answer" section is the contract the parser answers
it by: pick / yes / no over a list or a confirm, fill / all / done / cancel over the stock
quantities, ordinals and numbers in English, Malay and Chinese. PR #1247 rounds 4 to 8
edited the same addendum and left the publish to a hand step; this revision carries the
publish with the deploy.

`ai_prompt_registry.render()` reads the PUBLISHED row, never the Python constant (the
fallback is used only when no DB row exists at all), so the new text reaches a turn only
from a published version. Published through `chatbot_rearch_s4.publish_policy_blocks`,
the one body formula (the constant plus the rendered policy blocks) - never a second copy
of it - as the next `chatbot_semantic_parser` version with NO label, the same immutable
versions plus movable labels split as 475 / 490 / 519: promoting is one label move on
the Prompts page and rolling back is the reverse move. The schema half
(`head/parser.PARSE_OUTPUT_JSON_SCHEMA`: the answer modes pick / yes / no) and the user
block's object line are live at once; the shape rules still answer a verdict that
declares nothing.

Idempotent: s4's publish skips when the full rendered template is already published.

`downgrade()` does nothing: the registry is append-only, and an unlabelled version is
inert (s12's own rule). A version the owner has since promoted must never be deleted.

Revision ID: oq_0001_parser_open_question
Revises: sales_0002_team_leader
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "oq_0001_parser_open_question"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None


def _load_s4():
    """S4's module, for its publish entrypoint (the same loader s12 uses: alembic
    revision files are not importable as a package)."""
    spec = importlib.util.spec_from_file_location(
        "_oq_0001_s4", Path(__file__).resolve().parent / "chatbot_rearch_s4.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMMIT_MESSAGE = (
    "Issue #1293: every question the bot asks is one open question object, answered in "
    "open_question_answer (pick / yes / no / fill / all / done / cancel). Unlabelled - "
    "promote from the Prompts page."
)


def upgrade() -> None:
    from sqlalchemy.orm import Session

    from app.models.ai_prompt import AIPromptVersion

    s4 = _load_s4()
    bind = op.get_bind()
    s4.publish_policy_blocks(bind)
    # s4 stamps its own generic message on what it publishes; the Prompts page should say
    # which change this version carries. Only s4's own message is replaced (a version
    # someone published by hand keeps theirs), and never the template.
    session = Session(bind=bind)
    try:
        template, _blocks_hash = s4._body(session)
        row = (
            session.query(AIPromptVersion)
            .filter(
                AIPromptVersion.name == s4.PROMPT_NAME,
                AIPromptVersion.template == template,
            )
            .first()
        )
        if row is not None and (row.commit_message or "").startswith("Turn re-architecture"):
            row.commit_message = COMMIT_MESSAGE
            session.commit()
    finally:
        session.close()


def downgrade() -> None:
    pass
