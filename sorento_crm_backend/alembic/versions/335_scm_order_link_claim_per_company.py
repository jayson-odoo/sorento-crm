"""The order-link claim identity is per COMPANY, not global.

Revision ID: 335_scm_order_link_claim_per_company
Revises: 334_scm_order_link_claim
Create Date: 2026-08-05

`uq_scm_order_link_claim_identity` was `(so_number, po_number, coalesce(item_code, ''))` with
no company. Every read of the table is company-scoped, because `OrderLinkClaim` carries
`CompanyScopedMixin` and the ORM filter applies - so the "does this claim already exist?"
guard in both feeds looks ONLY inside the caller's company, then inserts, and the index
rejects it because ANOTHER company already claimed that pairing.

That is not hypothetical: uploading the same purchase-history book from a second company
died on `(175592, PO-2020/01-0010, )` and the browser showed "Failed to fetch", because a
500 raised this deep skips the CORS middleware and the real error never reaches the screen.

A pairing between company A's sales order and company A's purchase order says nothing about
company B, whose documents are different rows entirely. The guard was right; the constraint
was wrong. Adding `company_id` makes the constraint agree with the read that guards it -
the same family as the nullable-scope uniqueness bug in `project_optional_scope_breaks_uniqueness_lock`,
here in the other direction: a lock too WIDE rather than too narrow.

`company_id` is nullable on the table (legacy rows predate the stamp), so it is coalesced to
the nil UUID for the same reason `item_code` is coalesced to '': Postgres treats NULLs as
distinct, and without it an unstamped claim would insert again on every re-upload.
"""
from alembic import op
import sqlalchemy as sa

revision = "335_scm_order_link_claim_per_company"
down_revision = "334_scm_order_link_claim"
branch_labels = None
depends_on = None

_INDEX = "uq_scm_order_link_claim_identity"
_NIL = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.drop_index(_INDEX, table_name="order_link_claim", schema="scm")
    op.create_index(
        _INDEX,
        "order_link_claim",
        [
            sa.text(f"coalesce(company_id, '{_NIL}'::uuid)"),
            "so_number",
            "po_number",
            sa.text("coalesce(item_code, '')"),
        ],
        unique=True,
        schema="scm",
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="order_link_claim", schema="scm")
    # Recreating the global index can fail where two companies now hold the same pairing,
    # which is exactly the state this migration exists to allow. Deliberately not deleting
    # anybody's claims to force it through: a downgrade that destroys rows is worse than a
    # downgrade that stops and says why.
    op.create_index(
        _INDEX,
        "order_link_claim",
        ["so_number", "po_number", sa.text("coalesce(item_code, '')")],
        unique=True,
        schema="scm",
    )
