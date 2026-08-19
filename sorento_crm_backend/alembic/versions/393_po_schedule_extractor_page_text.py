"""AI prompt registry: publish po_extractor/schedule_extractor's page_text turn.

19 Aug follow-up ("make the PO / delivery-schedule read absolutely the fastest";
"text + image together" agreed). ``document_extraction.extract_document`` now sends
the page's own PDF text layer to the model in the SAME turn as the image
(``{{page_text}}``), and both fallback prompts gained the authority rule for it
(text layer wins on codes/numbers, the image wins on strike-throughs, handwriting
and highlights).

Same situation ``391_schedule_extractor_prompt_notes`` fixed for a different edit:
``get_prompt`` serves the hardcoded fallback ONLY when a key has no
``ai_prompt_versions`` row at all. An install that never customised these two keys
needs nothing here - the new fallback text is already what is served (verified: this
deployment's DB holds no saved version for either key today). An install where
somebody DID save a custom version has frozen the OLD text, and the OLD two-variable
declaration, on ``production``; this migration publishes a new version of each
carrying the ``page_text`` addition so the speed-up actually reaches that install.

Idempotent per key: skipped when there is no version row (nothing to update), and
skipped again once the latest version already declares ``page_text``.

Revision ID: 393_po_schedule_extractor_page_text
Revises: ed706a98ddc6
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.ai_prompt_registry import (
    _po_extractor_fallback,
    _schedule_extractor_fallback,
)

revision = "393_po_schedule_extractor_page_text"
down_revision = "ed706a98ddc6"
branch_labels = None
depends_on = None

_TARGETS = {
    "po_extractor": _po_extractor_fallback,
    "schedule_extractor": _schedule_extractor_fallback,
}
_COMMIT_MESSAGE = (
    "Text + image together: the page's own PDF text layer rides along as "
    "{{page_text}}, authoritative for codes/numbers, with the image staying "
    "authoritative for strike-throughs, handwriting and highlights "
    "(19 Aug follow-up, PLAN-demo-followups-19aug-ladder-v2.md workstream B)."
)


def _publish(session: Session, name: str, fallback) -> None:
    latest = (
        session.query(AIPromptVersion)
        .filter(AIPromptVersion.name == name)
        .order_by(AIPromptVersion.version.desc())
        .first()
    )
    if latest is None:
        # No saved version anywhere: the hardcoded fallback is what is served, and
        # it already carries page_text. Nothing to publish.
        return
    if "page_text" in (latest.variables or []):
        return

    next_version = int(latest.version) + 1
    row = AIPromptVersion(
        name=name,
        version=next_version,
        type="text",
        template=fallback(),
        variables=["page_no", "page_count", "page_text"],
        commit_message=_COMMIT_MESSAGE,
    )
    session.add(row)
    session.flush()

    label = (
        session.query(AIPromptLabel)
        .filter(AIPromptLabel.name == name, AIPromptLabel.label == "production")
        .first()
    )
    if label is None:
        session.add(AIPromptLabel(name=name, label="production", version_id=row.id))
    else:
        label.version_id = row.id


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    for name, fallback in _TARGETS.items():
        _publish(session, name, fallback)
    session.commit()


def downgrade() -> None:
    # Versions are immutable/append-only by design; this migration only appends up
    # to two and repoints their production labels, so there is nothing to remove
    # going back without destroying real prompt-edit history.
    pass
