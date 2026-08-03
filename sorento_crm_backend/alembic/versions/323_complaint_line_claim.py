"""S3 - what the consumer claimed, kept beside what the system resolved.

A complaint line has carried only `product_code` (NOT NULL, free text) since long before
this module. That was enough when CS typed the code themselves off a document they were
reading. It is not enough for a consumer typing "the tap in my kitchen" into a phone.

Four columns, and the split between them is the point:

  `claimed_text`       what was actually said, verbatim and permanent.
  `product_id`         the exact variant, resolved. NULLABLE, and usually null.
  `kind_id`            the Kind, resolved. Nullable.
  `fault_description`  what is wrong with THIS product.

`product_code` stays NOT NULL and keeps doing its old job, so every existing reader,
export and DataGrid column is untouched.

**Why `product_id` is nullable and stays that way.** `SRTWC8152` matches three real
variants in `products` and resolves to none of them (AC-C17). ADR-0010 makes cover
decidable from the Kind alone precisely so this line is still assessable. A NOT NULL
`product_id` would make the ordinary consumer line unwritable, which is AC-C14's failure
in a different costume: the consumer with the broken toilet is not the person to punish
for an ambiguous base code.

**Why `fault_description` is per line rather than per complaint.** `complaints` already has
`defect_description`, and it describes the complaint. A consumer lodging two products in one
visit has two faults, and folding them into one paragraph loses which is which - the
technician then arrives knowing a toilet and a tap are both broken but not how.

`kind_id` mirrors `consumer_purchase_lines.kind_id` exactly: ON DELETE SET NULL, so purging
the warranty module leaves the complaint standing (AC-L2) rather than being refused by a
constraint no ON DELETE action could satisfy.

Revision ID: 323_complaint_line_claim
Revises: 322_consent_notices
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "323_complaint_line_claim"
down_revision = "322_consent_notices"
branch_labels = None
depends_on = None

TABLE = "complaint_product_lines"


def _columns(bind) -> set:
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
            ),
            {"t": TABLE},
        )
    }


def upgrade() -> None:
    bind = op.get_bind()
    held = _columns(bind)

    # Idempotent per column. Shared dev databases across worktrees routinely hold a
    # partial version of this ALTER already: `consumer_purchase_line_id` and
    # `defect_type_id` landed with S1/S2 and are expected to be present.
    if "claimed_text" not in held:
        op.add_column(TABLE, sa.Column("claimed_text", sa.Text(), nullable=True))
    if "fault_description" not in held:
        op.add_column(TABLE, sa.Column("fault_description", sa.Text(), nullable=True))

    if "product_id" not in held:
        op.add_column(
            TABLE, sa.Column("product_id", postgresql.UUID(as_uuid=False), nullable=True)
        )
        op.create_foreign_key(
            "fk_complaint_product_lines_product",
            TABLE,
            "products",
            ["product_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{TABLE}_product_id", TABLE, ["product_id"])

    if "kind_id" not in held:
        op.add_column(
            TABLE, sa.Column("kind_id", postgresql.UUID(as_uuid=False), nullable=True)
        )
        # Only when warranty is actually installed. The FK is the live link; the
        # module owning the target may legitimately be absent (AC-L2).
        exists = bind.execute(
            sa.text("SELECT to_regclass('public.warranty_product_kinds')")
        ).scalar()
        if exists:
            op.create_foreign_key(
                "fk_complaint_product_lines_kind",
                TABLE,
                "warranty_product_kinds",
                ["kind_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(f"ix_{TABLE}_kind_id", TABLE, ["kind_id"])


def downgrade() -> None:
    bind = op.get_bind()
    held = _columns(bind)
    for name in ("kind_id", "product_id", "fault_description", "claimed_text"):
        if name in held:
            op.drop_column(TABLE, name)
