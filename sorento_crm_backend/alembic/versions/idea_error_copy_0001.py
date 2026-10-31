"""Publish the no-sorry failed-save line to the live prompt registry (31 Oct).

The `ideation_capture_error` reply (en, ms, zh) no longer opens with an apology and now says
what to do. `get_prompt` serves a fallback only when the `production` label has no row, and
`seed_prompt_registry` never changes a live row's text, so a seeded install keeps the old texts. This
migration publishes each new text as the next immutable version and moves the label, but ONLY
where production still equals the old stock text of that key (compared strip-normalised). A
template the owner edited is left alone with a warning, and a re-run is a no-op because
production then equals the fallback. Each key is judged on its own. The seed is not called: it can re-pin
an unrelated prompt (`agent_system`), and a key with no `production` label is skipped here
because the runtime then serves the new fallback.

Revision ID: idea_error_copy_0001
Revises: akn_0001_knowledge
"""
import logging

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import PROMPT_KEYS
from app.services.ai_prompt_seed import (
    _ensure_version,
    _max_version,
    _set_label,
)

revision = "idea_error_copy_0001"
down_revision = "akn_0001_knowledge"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

# The old stock copy, frozen here: a never-edited install holds exactly this text on its
# `production` label.
STOCK_TEXTS = {
    "chatbot_reply_ideation_capture_error": (
        "Sorry, I couldn't save that idea just now. Please try again in a moment.",
    ),
    "chatbot_reply_ideation_capture_error.ms": (
        "Maaf, saya tidak dapat menyimpan idea itu sekarang. Sila cuba lagi sebentar nanti.",
    ),
    "chatbot_reply_ideation_capture_error.zh": ("抱歉，我暂时无法保存这个创意，请稍后再试。",),
}


def _publish_key(session: Session, name: str) -> None:
    spec = PROMPT_KEYS[name]
    fallback_text = spec.fallback()
    label = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == name, AIPromptLabel.label == "production")
        .first()
    )
    if label is None:
        return
    current = (
        session.query(AIPromptVersion).filter(AIPromptVersion.id == label.version_id).first()
    )
    if current is None:
        return
    text = (current.template or "").strip()
    if text == fallback_text.strip():
        return  # already published
    if text not in {t.strip() for t in STOCK_TEXTS[name]}:
        logger.warning(
            "prompt %s version %s is customised; leaving it, the failed-save line is not published",
            name,
            current.version,
        )
        return
    new_row = _ensure_version(
        session, name, _max_version(session, name) + 1, fallback_text, list(spec.variables)
    )
    _set_label(session, name, "production", new_row.id)


def publish(bind) -> None:
    session = Session(bind=bind)
    try:
        for name in STOCK_TEXTS:
            _publish_key(session, name)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upgrade() -> None:
    publish(op.get_bind())


def downgrade() -> None:
    # The published versions stay: dropping them would strip any edit the owner published on
    # top of them, and an unused version costs nothing.
    pass
