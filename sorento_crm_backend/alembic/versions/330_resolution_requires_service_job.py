"""A resolution can say that somebody has to go to the site.

**Why the flag lives on the resolution and not in code.** Some resolutions mean a visit
(replace on site, repair on site) and most do not (advice given, goods swapped at the
dealer). Today Agnes has to know which is which and press "Raise service job" herself, so
the visit depends on her remembering a table nobody wrote down. Sorento adds resolutions;
a hardcoded list is a code change per addition, which is a change nobody makes in time.

**Defaulting every existing row to false is deliberate.** Not one of them was chosen under
this rule. Defaulting true would mean the next edit of any historical complaint silently
raises a service job for a case that was closed months ago - a van dispatched by a
migration.

Revision ID: 330_resolution_requires_service_job
Revises: 328_structured_site_address
"""
from alembic import op
import sqlalchemy as sa

revision = "330_resolution_requires_service_job"
down_revision = "328_structured_site_address"
branch_labels = None
depends_on = None


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
    if not _has_column(bind, "complaint_resolutions", "requires_service_job"):
        op.add_column(
            "complaint_resolutions",
            sa.Column(
                "requires_service_job",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    op.drop_column("complaint_resolutions", "requires_service_job")
