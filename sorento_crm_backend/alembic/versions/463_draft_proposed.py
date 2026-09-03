"""A saved draft keeps the engine's suggestion at save time (D12, #573).

`PLAN` addendum for D11/D12: the sales order page's Suggested column already reads
`supply_proposed` off the ACTIVE revision's frozen snapshot; a line only SAVED (no
revision confirmed yet) had nothing to read there and showed "-" until Confirm.
`so_supply_decision_drafts.proposed` is the fix - the contribution's own `sources`
(the board's `BoardSource[]` vocabulary) at the moment the draft was written, carried
so this page can read it back the same way the board's own list view already does
("BRW 3 (BRW)"), until Confirm freezes a revision and `decided`/`proposed` on the
snapshot take over.

Nullable and additive only: a draft saved before this ships simply carries `NULL`, which
the reader treats as "nothing recorded", the same as `_decided_lines` already does for a
revision frozen before AC-D1's `proposed_components` existed.

Hand-written and guarded, for the reason 443/450/452/460/461 state: the shared dev
database is a prod copy whose `alembic_version` points at another lane's head, so this is
applied there by hand and re-running it has to be a no-op rather than a failure.

Revision ID: 463_draft_proposed
Revises: 461_so_supply_decision_drafts
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "463_draft_proposed"
down_revision = "461_so_supply_decision_drafts"
branch_labels = None
depends_on = None

TABLE = "so_supply_decision_drafts"
SCHEMA = "projects"
COLUMN = "proposed"


def _columns(schema: str, table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table, schema=schema)}


def upgrade() -> None:
    if COLUMN in _columns(SCHEMA, TABLE):
        return
    op.add_column(
        TABLE,
        sa.Column(COLUMN, postgresql.JSONB(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    if COLUMN not in _columns(SCHEMA, TABLE):
        return
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
