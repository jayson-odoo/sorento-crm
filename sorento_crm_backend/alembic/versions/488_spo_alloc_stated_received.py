"""`spo_allocations` gains `stated_received` (D28c) and `retired_at` (D28d),
spo-xlsx-supersede rounds 4 and 5.

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

`retired_at` (D28d) is the OTHER half of the same problem: a line the ESB has
stopped naming - by absence in a re-push of the same DocKey, or because the
document was re-created under a new DocKey - is closed but otherwise
indistinguishable from a live, fully received one, so it rejoined its
`(spo_number, product, location)` group and could both take a share of a
sibling's GRN and be REOPENED when a GRN was deleted (58 open units on a
29-unit order). One nullable timestamp says "the ESB no longer names this
line", and the group recompute skips those rows entirely. NOT backfilled: no
row can be known retired retrospectively, and the two setters stamp it the
next time the document is pushed.

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
            "ALTER TABLE spo_allocations "
            "ADD COLUMN IF NOT EXISTS retired_at TIMESTAMP WITH TIME ZONE"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE spo_allocations SET stated_received = quantity_received "
            "WHERE source_system = 'autocount' AND stated_received IS NULL"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS retired_at"))
    bind.execute(sa.text("ALTER TABLE spo_allocations DROP COLUMN IF EXISTS stated_received"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
