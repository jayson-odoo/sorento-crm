"""`spo_allocations` gains `stated_received` (D28c, spo-xlsx-supersede round 4).

The receipt a DECLARER stated for an AutoCount line, as opposed to the one a GRN
proves. `quantity_received` alone could not tell the two apart, and the group
recompute paid for it twice (reviewer round 3): deleting the only GRN against a
line whose ESB `TransferedQty` was 25 wrote it to 0, and a share redistributed
onto a sibling stayed there after the GRN that produced it was deleted, closed
and invisible to reorder planning.

Nullable with NO server default, deliberately: NULL reads as 0 everywhere it is
read (every row written before this column existed stated nothing), and a raw
INSERT that omits it stays valid on both a migrated schema and a
`Base.metadata.create_all` one.

The backfill sets `stated_received = quantity_received` for `source_system =
'autocount'` rows ONLY. On production those hold ESB-stated values and nothing
else: no picking line has ever pointed at an AutoCount line (they all point at
the xlsx-era rows), so nothing GRN-derived can be captured by this copy. Rows of
any other source keep NULL - an `scm_upload` or CRM-raised row declares nothing
and stays on the per-allocation recompute.

Revision ID: 488_spo_alloc_stated_received
Revises: 487_chatbot_warehouse_cue
"""
import sqlalchemy as sa
from alembic import op

revision = "488_spo_alloc_stated_received"
down_revision = "487_chatbot_warehouse_cue"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE spo_allocations ADD COLUMN IF NOT EXISTS stated_received INTEGER"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE spo_allocations SET stated_received = quantity_received "
            "WHERE source_system = 'autocount' AND stated_received IS NULL"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS stated_received"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
