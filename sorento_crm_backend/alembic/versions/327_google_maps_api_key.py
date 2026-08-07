"""Google Maps browser key as an admin-editable integration setting.

The consumer lodge journey asks where the item is installed, and a technician navigates to
the pin rather than to the typed address (AC-M37). That needs a map the consumer can drag,
and a map needs a key.

**A column, not an env var, and deliberately so.** The key belongs to whoever operates the
tenant: it is billed to their Google Cloud project and restricted to their domains. Putting
it in the environment means a redeploy to rotate it and a developer in the loop for something
an admin should own. Every other integration credential on this screen already works this
way.

**The value is NOT a secret, and the code must not pretend otherwise.** A Maps JavaScript key
is delivered to the browser by definition - anyone can read it out of the page. The control
is restriction, not concealment: an HTTP-referrer restriction bound to the deployed hosts,
plus an API restriction to just Maps JavaScript, Places and Geocoding. An unrestricted key is
a billable resource anybody can spend. This column is therefore stored and returned in plain
text like the webhook URLs beside it, and is not masked in the settings response - masking
would imply a protection that does not exist and would stop an admin checking which key is
in force.

Nullable with no default: a tenant that has not configured one gets the typed address fields
and no map, which is the honest degradation (AC-M38 - the pin never blocks).

Revision ID: 327_google_maps_api_key
Revises: 326_seed_service_job_graph
"""
from alembic import op
import sqlalchemy as sa

revision = "327_google_maps_api_key"
down_revision = "326_seed_service_job_graph"
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
    if not _has_column(bind, "system_settings", "google_maps_api_key"):
        op.add_column(
            "system_settings",
            sa.Column("google_maps_api_key", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("system_settings", "google_maps_api_key")
