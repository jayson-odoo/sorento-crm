"""dealer kit: page.draft_doc - autosave writes a draft, not history (B1)

Captain ruling, 2 Sep 2026 (PLAN-price-tag-feedback-r2 S8): the request
designer's ~1s autosave must NOT create ``page_version`` rows. It used to call
the same ``PUT /design`` the manual Save button calls, so a minute of nudging a
layer wrote sixty immutable versions and the request's own history became
unreadable.

One nullable column, no new table: this mirrors the draft/live split S5 already
gave tag templates, where the DRAFT is a column on the row (``tag_template.doc``)
and only the deliberate act (Publish there, manual Save here) snapshots it into
an immutable version. One draft per page, so it is a column - a second draft per
page would be what turns it into a table, and nothing asks for one.

NULL is exactly "no work in progress", which is what every existing page has, so
there is no backfill: ``GET /design`` falls back to the latest version the same
way it always did.

Guarded like ``453_shared_brand_attach`` / ``454_tag_template_versions``: the
shared local Postgres converges through ``Base.metadata.create_all`` rather than
``alembic upgrade``, so this column is hand-applied there with
``alembic_version`` parked on another revision. The probe below makes a replay a
no-op instead of a duplicate-column error.

MERGE ORDER: chains onto ``455_products_barcode`` (PR #492, unmerged at
authoring time) so this branch adds no second head on ``main``. Merge #492
first.

Revision ID: 456_page_draft_doc
Revises: 455_products_barcode
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "456_page_draft_doc"
down_revision = "455_products_barcode"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = :t"
            ),
            {"s": SCHEMA, "t": table},
        )
    }


def upgrade() -> None:
    if "draft_doc" not in _columns("page"):
        op.add_column(
            "page",
            sa.Column("draft_doc", JSONB(), nullable=True),
            schema=SCHEMA,
        )


def downgrade() -> None:
    if "draft_doc" in _columns("page"):
        op.drop_column("page", "draft_doc", schema=SCHEMA)
