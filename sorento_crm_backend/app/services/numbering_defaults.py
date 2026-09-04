"""The numbering rules a document type cannot be issued without, in one definition.

`document_numbering_rules` holds ROWS, not schema, so nothing in the ORM produces one: a
rule arrives either from a migration seed or from Setup. That makes a seed a per-database
fact, and a per-database fact goes stale the moment a company is created after the migration
ran - migration 440 seeded the `inbound_shipment_draft` series for the companies that existed
at that instant, and the first convert in a company created afterwards was refused with
`numbering_rule_missing` (a 500 on a screen where nothing was wrong).

So the definition lives here, and the callers share it - one pair of functions per series
(`seed_inbound_shipment_draft_rule` for the packing-list draft, `seed_crm_spo_rule` for the
CRM SPO), each with the same three callers:

  * a migration (`seed_inbound_shipment_draft_rule(op.get_bind())` in 440,
    `seed_crm_spo_rule(op.get_bind())` in 470) for every company that already exists,
  * `scripts/bootstrap_env` and the test `after_create` hook, for a database built without
    running migration bodies,
  * the numbering service's own caller (`proforma_invoice_service._draft_shipment_number`,
    `spo_conversion_service._spo_number`), which calls it for the writing company the first
    time that company needs a number.

The insert is idempotent and never resets a counter that has already issued numbers: a
company that holds the rule is skipped, and `on conflict do nothing` covers the race of two
converts arriving together in a company that holds none.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text


#: `NumberingService` doc_type for a draft packing list's own series.
INBOUND_SHIPMENT_DRAFT_DOC_TYPE = "inbound_shipment_draft"
#: `PL-{YYMM}-{NNN}`, monthly (the captain's Q2, 27 Aug): `PL-2608-001`, then `PL-2608-002`,
#: and back to `-001` in September. `NumberingService` formats `{yy}` and `{month}`.
INBOUND_SHIPMENT_DRAFT_PREFIX_TEMPLATE = "PL-{yy}{month:02d}-"
INBOUND_SHIPMENT_DRAFT_NUMBER_DIGITS = 3
INBOUND_SHIPMENT_DRAFT_RESET_POLICY = "monthly"

#: `NumberingService` doc_type for a CRM SPO's own series (`spo_conversion_service`) - kept
#: distinct from every AutoCount pattern and from the CRM's own canonical PO series so an
#: AutoCount import can never collide with a number this module minted.
CRM_SPO_DOC_TYPE = "purchase_order_crm_spo"
#: `S-SPO-{year}/{month:02d}-{NNNN}`, monthly (captain, 4 Sep): `S-SPO-2026/09-0001`, then
#: `S-SPO-2026/09-0002`, back to `-0001` in October.
CRM_SPO_PREFIX_TEMPLATE = "S-SPO-{year}/{month:02d}-"
CRM_SPO_NUMBER_DIGITS = 4
CRM_SPO_RESET_POLICY = "monthly"


_INSERT = text(
    """
    insert into document_numbering_rules
        (id, company_id, doc_type, enabled, prefix_template, number_digits,
         next_value, start_value, reset_policy, created_at, updated_at)
    select gen_random_uuid(), c.id, :doc_type, true, :prefix, :digits, 1, 1, :reset,
           now(), now()
    from companies c
    where (:company_id is null or c.id::text = :company_id)
      and not exists (
        select 1 from document_numbering_rules r
        where r.doc_type = :doc_type and r.company_id = c.id
    )
    on conflict do nothing
    """
)


def seed_inbound_shipment_draft_rule(
    connection, *, company_id: Optional[str] = None
) -> None:
    """Give the packing-list series to `company_id`, or to every company when it is None.

    `connection` is anything with `.execute(clause, params)`: an Alembic bind, an engine
    connection, or the caller's `Session` (the row then lands in the caller's transaction,
    which is what makes the on-the-spot creation atomic with the document it numbers).

    Seeded PER COMPANY, the shape migration 327 established when `document_numbering_rules`
    gained `company_id` and its unique key became `(company_id, doc_type)`: a running number
    printed on a document two companies share is not a series.
    """
    connection.execute(
        _INSERT,
        {
            "doc_type": INBOUND_SHIPMENT_DRAFT_DOC_TYPE,
            "prefix": INBOUND_SHIPMENT_DRAFT_PREFIX_TEMPLATE,
            "digits": INBOUND_SHIPMENT_DRAFT_NUMBER_DIGITS,
            "reset": INBOUND_SHIPMENT_DRAFT_RESET_POLICY,
            "company_id": str(company_id) if company_id else None,
        },
    )


def seed_crm_spo_rule(connection, *, company_id: Optional[str] = None) -> None:
    """Give the CRM SPO series to `company_id`, or to every company when it is None.

    Same shape and same reasoning as `seed_inbound_shipment_draft_rule` above (327's per-company
    key, idempotent, `connection` is anything with `.execute`) - `spo_conversion_service._spo_number`
    fell back to `CRM-SPO-<hex8>` because no `purchase_order_crm_spo` rule had ever been seeded,
    the same absence 440 fixed for the packing-list draft series.
    """
    connection.execute(
        _INSERT,
        {
            "doc_type": CRM_SPO_DOC_TYPE,
            "prefix": CRM_SPO_PREFIX_TEMPLATE,
            "digits": CRM_SPO_NUMBER_DIGITS,
            "reset": CRM_SPO_RESET_POLICY,
            "company_id": str(company_id) if company_id else None,
        },
    )
