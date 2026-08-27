"""The draft packing list draws its number from a rule, so `SHIP-DRAFT-<hex8>` can stop.

A packing list created by converting proforma invoices was reading `SHIP-DRAFT-46949e1c`:
`proforma_invoice_service._draft_shipment_number` asked `NumberingService` for the
`inbound_shipment_draft` series, no rule for that doc_type had ever been seeded, and the
random fallback fired every time. A random hex is not a series - two lists sort in no order,
nobody can quote one over the phone, and the operator cannot tell which of them came first.

The rule is `PL-{YYMM}-{NNN}`, monthly (the captain's Q2, 27 Aug): `PL-2608-001`, then
`PL-2608-002`, and back to `-001` in September. `NumberingService` formats the prefix with
`{yy}` and `{month}`, so the template is `PL-{yy}{month:02d}-` with three digits after it.

Seeded PER COMPANY, the shape migration 327 established when `document_numbering_rules` gained
`company_id` and its unique key became `(company_id, doc_type)`: a running number printed on a
document two companies share is not a series. Idempotent - a company that already has the rule
is skipped, so a re-run never resets a counter that has already issued numbers.

Revision ID: 440_pl_draft_numbering
Revises: 438_merge_price_supplier_sets
Create Date: 2026-08-28
"""
from alembic import op
from sqlalchemy import text


revision = "440_pl_draft_numbering"
down_revision = "438_merge_price_supplier_sets"
branch_labels = None
depends_on = None


DOC_TYPE = "inbound_shipment_draft"
PREFIX_TEMPLATE = "PL-{yy}{month:02d}-"
NUMBER_DIGITS = 3
RESET_POLICY = "monthly"


def seed_inbound_shipment_draft_rule(connection) -> None:
    """The seed itself, callable outside a migration run.

    CI builds its database with `create_all`, which never executes a migration body, so a
    test that needs this rule calls this function rather than assuming the row is there -
    the same shape as migration 336's `seed_container_sizes`.
    """
    connection.execute(
        text(
            """
            insert into document_numbering_rules
                (id, company_id, doc_type, enabled, prefix_template, number_digits,
                 next_value, start_value, reset_policy, created_at, updated_at)
            select gen_random_uuid(), c.id, :doc_type, true, :prefix, :digits, 1, 1, :reset,
                   now(), now()
            from companies c
            where not exists (
                select 1 from document_numbering_rules r
                where r.doc_type = :doc_type and r.company_id = c.id
            )
            """
        ),
        {
            "doc_type": DOC_TYPE,
            "prefix": PREFIX_TEMPLATE,
            "digits": NUMBER_DIGITS,
            "reset": RESET_POLICY,
        },
    )


def upgrade() -> None:
    seed_inbound_shipment_draft_rule(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        text("delete from document_numbering_rules where doc_type = :doc_type"),
        {"doc_type": DOC_TYPE},
    )
