"""Structured site address on complaints, plus an extraction model override.

**Why the address stops being one text box.** `site_address` is where a technician is sent.
A single free-text line accepts "kajang" and calls it an address, which is a van dispatched
to a town. Postcode and state are also what every downstream document and any future routing
needs, and neither can be recovered from a sentence somebody typed in a hurry.

The composed one-line `site_address` STAYS and stays authoritative for everything that reads
it today (the Service Job copies it, documents print it). These columns are the parts it was
composed from, so a later screen can edit a postcode without re-parsing prose. Writing both
is deliberate duplication: the alternative is every reader learning to assemble an address,
and the readers include a PDF template.

**`ai_extract_model`.** Extraction currently borrows whatever model the AI assistant is
configured with, which is `gpt-4o-mini` on this tenant. That model transcribed `03/08/2026`
as `03/03/2026` from a photograph of a monitor - it is reading the digits wrong, which no
amount of prompt or post-processing can repair. Receipt OCR and assistant chat are different
jobs with different cost/accuracy trade-offs, so extraction gets its own setting and defaults
to `gpt-4o` when blank, leaving the assistant's choice alone.

Revision ID: 328_structured_site_address
Revises: 327_google_maps_api_key
"""
from alembic import op
import sqlalchemy as sa

revision = "328_structured_site_address"
down_revision = "327_google_maps_api_key"
branch_labels = None
depends_on = None

_COMPLAINT_COLUMNS = (
    ("site_address_line1", sa.Text()),
    ("site_address_line2", sa.Text()),
    ("site_postcode", sa.String(16)),
    ("site_city", sa.String(120)),
    ("site_state", sa.String(120)),
    # Defaulted in application code rather than here: a server default would stamp
    # "Malaysia" onto every legacy row, inventing a fact about addresses nobody entered.
    ("site_country", sa.String(120)),
)


def _has_column(bind, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()
    for name, coltype in _COMPLAINT_COLUMNS:
        if not _has_column(bind, "complaints", name):
            op.add_column("complaints", sa.Column(name, coltype, nullable=True))
    if not _has_column(bind, "system_settings", "ai_extract_model"):
        op.add_column(
            "system_settings", sa.Column("ai_extract_model", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    for name, _coltype in _COMPLAINT_COLUMNS:
        op.drop_column("complaints", name)
    op.drop_column("system_settings", "ai_extract_model")
