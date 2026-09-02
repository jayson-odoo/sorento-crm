"""`crm_supply` joins the order-link claim's source vocabulary (G12, 2 Sep 2026).

Revision ID: 458_claim_crm_supply
Revises: 454_order_inquiry_born_ack
Create Date: 2026-09-02

BATCH CHAIN (S6 merges LAST). The 1 Sep feedback batch numbers its migrations in slice
order, and this pair was renumbered on 2 Sep when S3 and S4 pushed theirs first:

    454 (S1, order-inquiry born ack)
     -> 455 (S4, saved views + perms)
     -> 456 (S3, reorder perf quick wins)
     -> 457 (S5, re-plan)
     -> 458 / 459 (S6, this pair)

    merge order: #471 -> #488 -> #489 -> #491 -> #493 -> #490

`down_revision` here is still `454_order_inquiry_born_ack`, NOT `457_reorder_replan`,
because 457 does not exist on this branch yet and PR #490 has to stay standalone-green.
IMMEDIATELY BEFORE MERGING #490, flip it to `457_reorder_replan` in a one-line commit -
that is the whole handover, and skipping it leaves two Alembic heads on main.

G12 says a PO/SPO line destined for a project bin is auto-taken ONLY by the sales order
that claims it, and the captain's 2 September reading closed the last hole in that: the
cascade may NEVER write the claim it then reads. Attribution comes from the BOOK
(`po_history` / `po_upload`, the `FromSODocList` column), from a PERSON in the Link dialog
(`manual`), or from the SUPPLY WRITER at the moment it creates the line - a purchase order
this codebase raises off the reorder plan is a buy FOR the order-inquiry rows that sized
it, and it says so in the same transaction that opens the line.

That last one needs a source of its own, and it cannot borrow `order_inquiry`. That value
means "a claim written in lockstep with a link the cascade wrote", and two readers turn on
telling the two apart:

  * `project_order_inquiry_service._reserved_for_netting` - an `order_inquiry` claim names
    a quantity already counted by the link beside it, so subtracting it a second time
    double-counts; a `crm_supply` claim can stand alone, before any link exists;
  * the one-shot repair `scripts/repair_project_bin_self_claims.py`, which drops the links
    the withdrawn born-claimed mechanism wrote and must not drop a legitimate write-time
    attribution alongside them.

Constraint only - no data moves. Every existing row is `po_history` or `order_inquiry`
(measured on the prod copy, 2 Sep 2026: 33,231 and 3,220, nothing else), so widening what
is allowed cannot invalidate anything already stored.
"""
from alembic import op

revision = "458_claim_crm_supply"
down_revision = "454_order_inquiry_born_ack"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_scm_order_link_claim_source"
_OLD = "source IN ('po_history', 'order_inquiry', 'so_upload', 'po_upload', 'manual')"
_NEW = (
    "source IN ('po_history', 'order_inquiry', 'so_upload', 'po_upload', 'manual', "
    "'crm_supply')"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "order_link_claim", schema="scm", type_="check")
    op.create_check_constraint(
        _CONSTRAINT, "order_link_claim", _NEW, schema="scm"
    )


def downgrade() -> None:
    # A `crm_supply` row would fail the narrower check, so it is relabelled rather than
    # deleted: the attribution is real evidence and a downgrade that destroys it is worse
    # than one that stores it under the nearest older word.
    op.execute(
        "UPDATE scm.order_link_claim SET source = 'manual' WHERE source = 'crm_supply'"
    )
    op.drop_constraint(_CONSTRAINT, "order_link_claim", schema="scm", type_="check")
    op.create_check_constraint(
        _CONSTRAINT, "order_link_claim", _OLD, schema="scm"
    )
