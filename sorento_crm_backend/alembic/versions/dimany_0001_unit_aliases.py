"""DIMENSION-ANY: `unit_aliases` on the spec registry.

The other units a customer writes a key's quantity in, as data on the key (crew audit of PR #1949,
owner rule 28 Oct 2026: no word lists in code). Every millimetre key gets centimetres, metres and
inches; the candidate block offers "15cm" as "size 150 mm" off them and the parser decides what was
meant ("5 in stock" included). A row someone already gave aliases is left alone. Additive and
idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through `create_all`, can take it.

Revision ID: dimany_0001_unit_aliases
Revises: resub_0001_resubmitted_status
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "dimany_0001_unit_aliases"
down_revision = "resub_0001_resubmitted_status"
branch_labels = None
depends_on = None

# No bare "in": "any 5 in stock" is a stock ask, and offering it as 127 mm leads the Spec block with a size
# (reviewer round 5). "inch" / "inches" carry the unit.
MM_ALIASES = '{"cm": 10, "m": 1000, "inch": 25.4, "inches": 25.4}'


def upgrade() -> None:
    op.execute(
        "ALTER TABLE product_spec_registry "
        "ADD COLUMN IF NOT EXISTS unit_aliases jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        f"UPDATE product_spec_registry SET unit_aliases = '{MM_ALIASES}'::jsonb "
        "WHERE unit = 'mm' AND unit_aliases = '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE product_spec_registry DROP COLUMN IF EXISTS unit_aliases")
