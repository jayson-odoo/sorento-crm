"""publish the ideate_extractor and ideate_reply prompts for #1277

Owner console test of 26 Sep 2026 (#1277): the Problem line echoed the raw message
(typos, "i have an idea" preamble, later detail glued on with a semicolon), the field
labels were plain, and the title sat unexplained at the top of every recap.

* ``ideate_extractor`` gains the CLEAN VALUES rule: problem / proposed_solution /
  impact are written as clean statements (preamble stripped, spelling corrected,
  extensions merged into one sentence, never a semicolon join). ``raw_transcript``
  still carries the user's own words.
* ``ideate_reply`` asks for WhatsApp-bold labels and no title line in a recap (the
  title stays in the final ``complete`` message). ``compose_ideate_reply`` enforces
  both deterministically either way; the prompt is reworded so it no longer asks for
  the opposite.

Same mechanism as ``272_ideate_intent_parser_prompt``: each key's current fallback is
published as the next immutable version and ``production`` moves to it; a no-op when
production already carries that text. ``render()`` reads the published row, not the
Python constant, so without this the fallback edit would never reach a live turn.

See ``documentation/plans/ideation/PLAN-ideation-chat-reply-format.md``.

Revision ID: ideation_reply_fmt_prompts
Revises: sb3_company_stock_push_at
Create Date: 2026-09-26
"""
from alembic import op

from app.services.ai_prompt_seed import bump_prompt_to_fallback, seed_prompt_registry


revision = "ideation_reply_fmt_prompts"
down_revision = "sb3_company_stock_push_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fresh installs get every key at v1 from its (already amended) fallback.
    seed_prompt_registry(op.get_bind())
    bump_prompt_to_fallback(op.get_bind(), "ideate_extractor")
    bump_prompt_to_fallback(op.get_bind(), "ideate_reply")


def downgrade() -> None:
    # Data-only publish. Rolling back is a label move in the prompt admin screen;
    # leaving the published versions in place is harmless.
    pass
