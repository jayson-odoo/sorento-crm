"""publish the ideate_extractor and ideate_reply prompts for PR #1279 round 2

Owner console test of 26 Sep 2026 14:09Z (#1277, PR #1279): the Problem line showed the
raw first message for three turns, the Department kept the owner's typo and typed
question mark ("the manufactuirng?"), and the idea was created with no confirmation
question.

* ``ideate_extractor``: problem is always emitted from the first message (the intake
  otherwise seeds it from the raw text), a raw captured value is re-emitted cleaned,
  typed punctuation never enters a value, department in Title Case with the spelling
  corrected, and ``review_action`` is ``submit`` only for a plain yes.
* ``ideate_reply``: a review reply ends with "Submit this idea? Reply yes to submit, or
  tell me what to change." (``compose_ideate_reply`` enforces it either way).

Same mechanism as ``ideation_reply_fmt_prompts``: each key's current fallback is
published as the next immutable version and ``production`` moves to it; a no-op when
production already carries that text.

See ``documentation/plans/ideation/PLAN-ideation-chat-reply-format.md``.

Revision ID: ideation_confirm_prompts
Revises: ideation_reply_fmt_prompts
Create Date: 2026-09-26
"""
from alembic import op

from app.services.ai_prompt_seed import bump_prompt_to_fallback, seed_prompt_registry


revision = "ideation_confirm_prompts"
down_revision = "ideation_reply_fmt_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_prompt_registry(op.get_bind())
    bump_prompt_to_fallback(op.get_bind(), "ideate_extractor")
    bump_prompt_to_fallback(op.get_bind(), "ideate_reply")


def downgrade() -> None:
    # Data-only publish. Rolling back is a label move in the prompt admin screen.
    pass
