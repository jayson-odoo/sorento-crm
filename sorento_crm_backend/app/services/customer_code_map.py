"""The customer's own item codes, learned once per customer (AC-E4, PO-UPLOAD-MATCHING AC-A4).

`BUI-HB-SRTWC8613-RL` means `SRTWC8613-RL` for that buyer, whether it was printed on a
delivery schedule or on a purchase order. Both readers resolve through this one module and
both remember a person's pick through it, so a code taught on one document is known on the
next document of either kind. No other module queries ``CustomerItemCodeMap``.
"""
from __future__ import annotations

import unicodedata
from typing import Dict, Optional, Set

from sqlalchemy.orm import Session

from app.models.project_so import CustomerItemCodeMap
from app.models.projects import Project, ProjectParty, ProjectPurchaseOrder

#: ``customer_item_code_map.customer_code`` is String(180).
CODE_MAX_LENGTH = 180


def normalise_code(code: Optional[str]) -> str:
    """The comparison key of a printed code: case-folded, with whitespace, dashes and
    asterisks removed, and NOTHING else removed.

    Owner ruling 13 Nov: case, spaces, dashes and marks do not make a different code, so
    `SORENTO BBTSRTWT9121 -GM **` is `sorento bbtsrtwt9121-gm` (an en dash, a Unicode hyphen
    or a minus sign counts as a dash). Every other character still counts: `2.5MM` is not
    `25MM`, `1/2` is not `12`, `X1(B)` is not `X1B`, and non-ASCII letters stay. Only the
    comparison uses this; the map stores the code as printed.
    """
    return "".join(
        character
        for character in (code or "").casefold()
        if not (
            character.isspace()
            or character in _IGNORED_MARKS
            or unicodedata.category(character) == "Pd"
        )
    )


#: Removed by ``normalise_code`` besides whitespace and dash punctuation (category Pd).
_IGNORED_MARKS = frozenset({"*", "\uff0a", "\u2212"})


class RememberedCodes(dict):
    """``remembered_codes``'s answer: UPPER printed code -> product id, plus the normalised
    index ``lookup`` compares against, built once per load rather than once per line."""

    def __init__(self, pairs=(), index: Optional[Dict[str, Set[str]]] = None) -> None:
        super().__init__(pairs)
        self.index = index


def _index(pairs) -> Dict[str, Set[str]]:
    """normalised code -> every product a code of that key points at. An empty key (a code
    made only of spaces, dashes or asterisks) is never indexed: it compares to nothing."""
    out: Dict[str, Set[str]] = {}
    for code, product_id in pairs:
        key = normalise_code(code)
        if key and product_id:
            out.setdefault(key, set()).add(str(product_id))
    return out


def lookup(remembered: Dict[str, str], code: Optional[str]) -> Optional[str]:
    """The product a remembered code points at, comparing by ``normalise_code``. The one
    lookup both the PO reader and the delivery-schedule matcher use.

    None for an empty key, and None when the codes that compare equal point at DIFFERENT
    products (rows saved before codes were compared this way): a person decides, the map
    does not guess.
    """
    key = normalise_code(code)
    if not key:
        return None
    index = getattr(remembered, "index", None)
    if index is None:
        index = _index(remembered.items())
    products = index.get(key) or set()
    return next(iter(products)) if len(products) == 1 else None


def customer_code_for(stock_code: Optional[str], description: Optional[str]) -> Optional[str]:
    """What a PO line is remembered by: its printed stock code, or, when the line has none,
    its description (cut to the column length). Read and write both use this one rule."""
    code = (stock_code or "").strip() or (description or "").strip()
    return code[:CODE_MAX_LENGTH] or None


def remembered_codes(db: Session, customer_id: Optional[str]) -> Dict[str, str]:
    """Every code this customer taught us, as UPPER printed code -> product id. Compare a
    printed code against it only through ``lookup``, never by key: two printings of one
    code ("X-1", "X 1") are two keys here and one code there."""
    if not customer_id:
        return RememberedCodes()
    rows = (
        db.query(CustomerItemCodeMap)
        .filter(CustomerItemCodeMap.customer_id == customer_id)
        .all()
    )
    pairs = [(row.customer_code or "", row.product_id) for row in rows]
    return RememberedCodes(
        ((code.upper(), product_id) for code, product_id in pairs), index=_index(pairs)
    )


def remember_code(
    db: Session,
    *,
    company_id: Optional[str],
    customer_id: Optional[str],
    customer_code: Optional[str],
    product_id: str,
    actor_user_id: Optional[str],
) -> None:
    """Insert, or overwrite EVERY row whose code is the same by ``normalise_code`` (rows saved
    before codes were compared this way can disagree; the person's pick settles all of
    them). A code that normalises to nothing only ever updates its own exact spelling. A
    blank code or no customer is a no-op: there is nothing to key the memory on."""
    code = (customer_code or "").strip()[:CODE_MAX_LENGTH]
    if not customer_id or not code or not product_id:
        return
    key = normalise_code(code)
    rows = (
        db.query(CustomerItemCodeMap)
        .filter(CustomerItemCodeMap.customer_id == customer_id)
        .all()
    )
    matching = [
        row
        for row in rows
        if (normalise_code(row.customer_code) == key if key else row.customer_code == code)
    ]
    for row in matching:
        row.product_id = product_id
        row.confirmed_by = actor_user_id
    if not matching:
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
