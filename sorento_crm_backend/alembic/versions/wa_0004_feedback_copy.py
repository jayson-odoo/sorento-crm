"""Publish the "feedback" reply copy (WA-COMPLAINT-INTAKE round 15,
documentation/plans/chatbot/COPY-wa-feedback-rename.md "How it ships").

The seed runs first so every key exists; `ideation_copy_rename.publish` then adds each new text as the next
version and moves that key's `production` label only where production still equals the stock text it replaces
(strip-normalised). An owner-edited text is left alone with a warning; a re-run is a no-op.

Revision ID: wa_0004_feedback_copy
Revises: wa_0003_issue_give_up_copy
Create Date: 2026-11-14
"""
from alembic import op
from sqlalchemy.orm import Session

from app.services.ai_prompt_seed import seed_prompt_registry
from app.services.ideation_copy_rename import publish

revision = "wa_0004_feedback_copy"
down_revision = "wa_0003_issue_give_up_copy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    seed_prompt_registry(op.get_bind())
    session = Session(bind=op.get_bind())
    try:
        publish(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    # Nothing moves back: the old versions stay in the history and the owner can move the label on the Prompts page.
    pass
