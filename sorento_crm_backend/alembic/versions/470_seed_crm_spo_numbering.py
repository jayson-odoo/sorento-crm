"""The CRM SPO draws its number from a rule, so `CRM-SPO-<hex8>` can stop.

A CRM SPO created by the packing-list planner was reading `CRM-SPO-7bcb4582`:
`spo_conversion_service._spo_number` asked `NumberingService` for the
`purchase_order_crm_spo` series, no rule for that doc_type had ever been seeded, and the
random fallback fired every time. A random hex is not a series - two SPOs sort in no order,
nobody can quote one over the phone, and the operator cannot tell which of them came first.

The rule is `S-SPO-{year}/{month:02d}-{NNNN}`, monthly (captain, 4 Sep): `S-SPO-2026/09-0001`,
then `S-SPO-2026/09-0002`, and back to `-0001` in October.

Seeded PER COMPANY, the same shape migration 327 established when `document_numbering_rules`
gained `company_id` and its unique key became `(company_id, doc_type)`: a running number
printed on a document two companies share is not a series. Idempotent - a company that already
has the rule is skipped, so a re-run never resets a counter that has already issued numbers.

A company created AFTER this migration ran gets no row from it, which would refuse that
company's first Create SPO the same way 440 had to fix for the packing-list draft series. The
seed therefore lives in `app.services.numbering_defaults` and is shared with the service,
which calls it for the writing company when the series is missing; this migration is one of
its callers.

Revision ID: 470_seed_crm_spo_numbering
Revises: 469_shipment_spo_link_not_unique
Create Date: 2026-09-04
"""
from alembic import op
from sqlalchemy import text

from app.services.numbering_defaults import (
    CRM_SPO_DOC_TYPE,
    CRM_SPO_NUMBER_DIGITS,
    CRM_SPO_PREFIX_TEMPLATE,
    CRM_SPO_RESET_POLICY,
    seed_crm_spo_rule,
)


revision = "470_seed_crm_spo_numbering"
down_revision = "469_shipment_spo_link_not_unique"
branch_labels = None
depends_on = None


#: Re-exported so a caller that loads this file by path (`scripts/bootstrap_env`, the
#: numbering tests) keeps reading the rule's shape off the migration that introduced it.
DOC_TYPE = CRM_SPO_DOC_TYPE
PREFIX_TEMPLATE = CRM_SPO_PREFIX_TEMPLATE
NUMBER_DIGITS = CRM_SPO_NUMBER_DIGITS
RESET_POLICY = CRM_SPO_RESET_POLICY

__all__ = [
    "DOC_TYPE",
    "PREFIX_TEMPLATE",
    "NUMBER_DIGITS",
    "RESET_POLICY",
    "seed_crm_spo_rule",
]


def upgrade() -> None:
    seed_crm_spo_rule(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        text("delete from document_numbering_rules where doc_type = :doc_type"),
        {"doc_type": DOC_TYPE},
    )
