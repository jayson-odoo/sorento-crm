"""Current-state reads so the ESB can render before/after diffs (AC-AC-19).

The ESB stages changes for human approval and shows what would change. It
therefore needs Sorento's *current* values for a set of source references, in
the same canonical shape it pushes - a diff between two different vocabularies
is not a diff anyone can review.

Batched, because a diff over several hundred records must not become several
hundred round trips.

**A reference we do not hold is reported explicitly**, not omitted. Silence is
ambiguous: the ESB cannot tell "Sorento has no such record" from "the response
was truncated", and those demand opposite actions - create it, versus stop and
investigate.

Read inside ONE company (group A1), the same anchor the ingest writes under. The
reference table is global, so a ref resolves to its row whatever company asked;
a row belonging to another company is reported under ``not_found``, because a
diff rendered against a company's values the caller never named is a diff that
would then be pushed back.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.integration_reference_service import IntegrationReferenceService
# One list of shared tables, owned by the ingest side and read here, so the two
# halves of this surface cannot disagree about which rows carry a company.
from app.services.master_ingest_service import _is_company_scoped

logger = logging.getLogger(__name__)

# Canonical field -> source column, per entity. The inverse of the ingest
# mapping, so what the ESB reads back is shaped like what it sent.
_READ_COLUMNS: dict[str, dict[str, str]] = {
    "product_categories": {
        "code": "category_code",
        "name": "category_name",
        "description": "description",
        "is_active": "is_active",
    },
    "units_of_measure": {
        "code": "uom_code",
        "name": "uom_name",
        "description": "description",
        "is_active": "is_active",
    },
    "warehouses": {
        "code": "warehouse_code",
        "name": "warehouse_name",
        "location": "location",
        "is_active": "is_active",
    },
    "suppliers": {
        "code": "supplier_code",
        "name": "supplier_name",
        "email": "email",
        "phone_number": "phone_number",
        "payment_terms_days": "payment_terms_days",
        "is_active": "is_active",
    },
    "customers": {
        "code": "customer_code",
        "name": "customer_name",
        "email": "email",
        "phone_number": "phone_number",
        "registration_number": "registration_number",
        "tax_id": "tax_id",
        "credit_limit": "credit_limit",
        "payment_terms_days": "payment_terms_days",
        "country": "country",
        "is_active": "is_active",
    },
    # Exactly the four the ingest writes. Reading back an annotation the ESB
    # cannot push would invite it into a diff, and the next approved sync would
    # then write it - which is how a column nobody upstream owns gets overwritten.
    "sales_agents": {
        "code": "sales_agent",
        "description": "description",
        "is_active": "is_active",
        "person_label": "person_label",
    },
    "products": {
        "code": "product_code",
        "name": "product_name",
        "description": "description",
        "list_price": "list_price",
        "cost_price": "cost_price",
        "is_active": "is_active",
    },
}


class MasterReadService:
    def __init__(self, db: Session, *, company_id: str):
        self.db = db
        # Required for the same reason the ingest requires it: the six masters are
        # partitioned per company, so "the current value" is not a question that
        # has one answer without naming one.
        self.company_id = company_id
        self.refs = IntegrationReferenceService(db)

    def current_state(self, entity_type: str, source_refs: list[str]) -> dict[str, Any]:
        columns = _READ_COLUMNS.get(entity_type)
        if columns is None:
            return {"records": [], "not_found": list(source_refs)}

        found: list[dict[str, Any]] = []
        not_found: list[str] = []

        for source_ref in source_refs:
            # resolve() also clears a reference whose target has been deleted,
            # so a stale mapping reports as not-found rather than as a record
            # the ESB would then try to update.
            entity_id = self.refs.resolve(entity_type=entity_type, source_ref=source_ref)
            if entity_id is None:
                not_found.append(source_ref)
                continue

            selected = ", ".join(f"{col} AS {name}" for name, col in columns.items())
            # The company predicate is part of the lookup, not a check after it:
            # another company's row must read exactly like a row that is not
            # there, so the caller acts on one answer rather than two. A shared
            # table's rows carry no company and are readable from either.
            if _is_company_scoped(entity_type):
                where = "id = :id AND company_id = :cid"
            else:
                where = "id = :id AND (company_id IS NULL OR company_id = :cid)"
            row = self.db.execute(
                text(f"SELECT {selected} FROM {entity_type} WHERE {where}"),
                {"id": entity_id, "cid": self.company_id},
            ).mappings().first()
            if row is None:
                not_found.append(source_ref)
                continue

            found.append({"source_ref": source_ref, "entity_id": entity_id, **dict(row)})

        return {
            "records": found,
            # Named explicitly so the caller can act on them rather than
            # inferring absence from a shorter list than it asked for.
            "not_found": not_found,
        }
