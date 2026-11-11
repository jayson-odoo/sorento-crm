"""SAMPLE-REQUEST-V2: a sample request's ship to is a party of the project.

One additive, nullable column on `projects.sample_requests`:

- `ship_to_party_id`: the party the samples go to (owner, 11 Nov: "it is party, not necessarily
  ship to ... I might send the item to trading house or consultant"). `ON DELETE SET NULL`: the
  printed name, address and contact stay in the existing snapshot columns, so a deleted party does
  not empty an old delivery.

No backfill: old rows keep their typed Ship To (card rule 3, example E).

Idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through `create_all`, can
take it in any order.

Revision ID: srv2_0001_ship_to_party
Revises: ptag_0022_request_customers
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "srv2_0001_ship_to_party"
down_revision = "ptag_0022_request_customers"
branch_labels = None
depends_on = None

_T = "projects.sample_requests"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {_T} ADD COLUMN IF NOT EXISTS ship_to_party_id UUID "
        "REFERENCES projects.parties(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sample_requests_ship_to_party "
        f"ON {_T} (ship_to_party_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS projects.ix_sample_requests_ship_to_party")
    op.execute(f"ALTER TABLE {_T} DROP COLUMN IF EXISTS ship_to_party_id")
