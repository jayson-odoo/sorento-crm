"""AI prompt registry: publish schedule_extractor's day-first/notes/highlight text.

`get_prompt` (app/services/ai_prompt_registry.py) serves the hardcoded fallback ONLY
when a key has no `ai_prompt_versions` row at all. An install that never customised
`schedule_extractor` needs nothing here - the fallback text (day-first dates, the
`notes` field, the per-cell `highlighted` flag; PLAN-so-book-diff-replanning.md
9.6/9.7a) is already what is served. An install where somebody saved a version has
frozen the OLD text on `production`, and this migration publishes a new version
carrying the update so the fix actually reaches that install.

Idempotent: skipped when there is no version row for the key (nothing to update),
and skipped again once the latest version already carries both markers (a prior
run of this same migration, or a version saved after the source fix landed).

Revision ID: 391_schedule_extractor_prompt_notes
Revises: 390_so_amendment_row_decisions
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import _schedule_extractor_fallback

revision = "391_schedule_extractor_prompt_notes"
down_revision = "390_so_amendment_row_decisions"
branch_labels = None
depends_on = None

_NAME = "schedule_extractor"
_MARKERS = ('"notes"', '"highlighted"')


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    latest = (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == _NAME)
        .order_by(AIPromptVersion.version.desc())
        .first()
    )
    if latest is None:
        # No saved version anywhere: the hardcoded fallback is what is served, and
        # it already carries the fix. Nothing to publish.
        return
    template = latest.template or ""
    if all(marker in template for marker in _MARKERS):
        return

    next_version = int(latest.version) + 1
    row = AIPromptVersion(
        name=_NAME,
        version=next_version,
        type="text",
        template=_schedule_extractor_fallback(),
        variables=["page_no", "page_count"],
        commit_message=(
            "Day-first dates, free-text notes and per-cell highlight flag "
            "(PLAN-so-book-diff-replanning.md 9.6/9.7)."
        ),
    )
    session.add(row)
    session.flush()

    label = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == _NAME, AIPromptLabel.label == "production")
        .first()
    )
    if label is None:
        session.add(AIPromptLabel(name=_NAME, label="production", version_id=row.id))
    else:
        label.version_id = row.id
    session.commit()


def downgrade() -> None:
    # Versions are immutable/append-only by design; this migration only appends
    # one and repoints the production label, so there is nothing to remove going
    # back without destroying a real prompt-edit history.
    pass
