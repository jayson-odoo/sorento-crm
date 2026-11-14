"""The customer's own item codes, learned once per customer (AC-E4, PO-UPLOAD-MATCHING AC-A4).

`BUI-HB-SRTWC8613-RL` means `SRTWC8613-RL` for that buyer, whether it was printed on a
delivery schedule or on a purchase order. Both readers resolve through this one module and
both remember a person's pick through it, so a code taught on one document is known on the
next document of either kind. No other module queries ``CustomerItemCodeMap``.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.project_so import CustomerItemCodeMap
from app.models.projects import Project, ProjectParty, ProjectPurchaseOrder

#: ``customer_item_code_map.customer_code`` is String(180).
CODE_MAX_LENGTH = 180


def normalise_code(code: Optional[str]) -> str:
    """The comparison key of a printed code: letters and digits only, upper case.

    Owner ruling 13 Nov: case, spaces, dashes and marks do not make a different code, so
    `SORENTO BBTSRTWT9121 -GM **` is `sorento bbtsrtwt9121-gm`. Different letters or digits
    still differ (`CB310-CR-L` is not `CB310-CR`). Only the comparison uses this; the map
    stores the code as printed.
    """
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def lookup(remembered: Dict[str, str], code: Optional[str]) -> Optional[str]:
    """The product a remembered code points at, comparing by ``normalise_code``. The one
    lookup both the PO reader and the delivery-schedule matcher use."""
    key = normalise_code(code)
    if not key:
        return None
    for remembered_code, product_id in remembered.items():
        if normalise_code(remembered_code) == key:
            return product_id
    return None


def customer_code_for(stock_code: Optional[str], description: Optional[str]) -> Optional[str]:
    """What a PO line is remembered by: its printed stock code, or, when the line has none,
    its description (cut to the column length). Read and write both use this one rule."""
    code = (stock_code or "").strip() or (description or "").strip()
    return code[:CODE_MAX_LENGTH] or None


def remembered_codes(db: Session, customer_id: Optional[str]) -> Dict[str, str]:
    """Every code this customer taught us: UPPER customer code -> product id."""
    if not customer_id:
        return {}
    rows = (
        db.query(CustomerItemCodeMap)
        .filter(CustomerItemCodeMap.customer_id == customer_id)
        .all()
    )
    return {(row.customer_code or "").upper(): row.product_id for row in rows}


def remember_code(
    db: Session,
    *,
    company_id: Optional[str],
    customer_id: Optional[str],
    customer_code: Optional[str],
    product_id: str,
    actor_user_id: Optional[str],
) -> None:
    """Insert, or overwrite the one row whose code is the same by ``normalise_code``. A blank
    code or no customer is a no-op: there is nothing to key the memory on."""
    code = (customer_code or "").strip()[:CODE_MAX_LENGTH]
    if not customer_id or not code or not product_id:
        return
    key = normalise_code(code)
    existing = next(
        (
            row
            for row in db.query(CustomerItemCodeMap)
            .filter(CustomerItemCodeMap.customer_id == customer_id)
            .all()
            if normalise_code(row.customer_code) == key
        ),
        None,
    )
    if existing is not None:
        existing.product_id = product_id
        existing.confirmed_by = actor_user_id
        db.flush()
        return
    db.add(
        CustomerItemCodeMap(
            company_id=company_id,
            customer_id=customer_id,
            customer_code=code,
            product_id=product_id,
            confirmed_by=actor_user_id,
        )
    )
    db.flush()


def lead_customer_id(db: Session, project_id: Optional[str]) -> Optional[str]:
    """The project's lead buyer, when the project came from a lead that names one."""
    project = db.get(Project, project_id) if project_id else None
    if project is None or not project.lead_id:
        return None
    from app.models.projects import ProjectLead

    lead = db.get(ProjectLead, project.lead_id)
    return lead.customer_id if lead is not None and lead.customer_id else None


def customer_id_for_po(db: Session, po: Optional[ProjectPurchaseOrder]) -> Optional[str]:
    """The debtor a PO's item codes belong to.

    The PO's issuer first, through the party-to-customer bridge, then the lead's buyer.
    A document may be issued by somebody else entirely (AC-E6), but the item codes are
    the BUYER's, so the map is keyed on them.
    """
    if po is None:
        return None
    if po.issuing_party_id:
        party = db.get(ProjectParty, po.issuing_party_id)
        if party is not None and party.customer_id:
            return party.customer_id
    return lead_customer_id(db, po.project_id)
