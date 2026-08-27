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

A company created AFTER this migration ran gets no row from it, which refused that company's
first convert with `numbering_rule_missing`. The seed therefore lives in
`app.services.numbering_defaults` and is shared with the service, which calls it for the
writing company when the series is missing; this migration is one of its callers.

Revision ID: 440_pl_draft_numbering
Revises: 438_merge_price_supplier_sets
Create Date: 2026-08-28
"""
from alembic import op
from sqlalchemy import text

from app.services.numbering_defaults import (
    INBOUND_SHIPMENT_DRAFT_DOC_TYPE,
    INBOUND_SHIPMENT_DRAFT_NUMBER_DIGITS,
    INBOUND_SHIPMENT_DRAFT_PREFIX_TEMPLATE,
    INBOUND_SHIPMENT_DRAFT_RESET_POLICY,
    seed_inbound_shipment_draft_rule,
)


revision = "440_pl_draft_numbering"
down_revision = "438_merge_price_supplier_sets"
branch_labels = None
depends_on = None


#: Re-exported so the callers that load this file by path (`scripts/bootstrap_env`, the
#: numbering tests) keep reading the rule's shape off the migration that introduced it.
DOC_TYPE = INBOUND_SHIPMENT_DRAFT_DOC_TYPE
PREFIX_TEMPLATE = INBOUND_SHIPMENT_DRAFT_PREFIX_TEMPLATE
NUMBER_DIGITS = INBOUND_SHIPMENT_DRAFT_NUMBER_DIGITS
RESET_POLICY = INBOUND_SHIPMENT_DRAFT_RESET_POLICY

__all__ = [
    "DOC_TYPE",
    "PREFIX_TEMPLATE",
    "NUMBER_DIGITS",
    "RESET_POLICY",
    "seed_inbound_shipment_draft_rule",
]


def upgrade() -> None:
    seed_inbound_shipment_draft_rule(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        text("delete from document_numbering_rules where doc_type = :doc_type"),
        {"doc_type": DOC_TYPE},
    )
