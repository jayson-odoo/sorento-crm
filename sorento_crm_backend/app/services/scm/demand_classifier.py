"""The one DB rung `demand_class.classify_document` needs and cannot import at
module scope (see that module's import-cycle warning): the customer's market
segment, read by debtor code.

Moved here verbatim from `outstanding_import_service._segment_of` (D4,
PLAN-autocount-document-ingest-v2.md section 1/2.3) so the upload and the
AutoCount document ingest classify off the SAME segment read rather than two
that could drift. `outstanding_import_service` re-exports this under its old
name (`_segment_of = segment_of`), so its own directly-testing callers are
unaffected.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Customer


def segment_of(
    db: Session, debtor_code: Optional[str], company_id: Optional[str] = None
) -> Optional[str]:
    """This customer's market segment code, or None when there is no customer to read.

    Three answers, and the caller needs all three apart: "no such customer" and
    "customer with no segment" are both None and both nothing to go on, and a
    segment that says retail is an answer.

    `company_id` is optional and, when omitted, this relies ENTIRELY on the
    session's ambient company scope (the upload's own long-standing behaviour -
    `outstanding_import_service`'s callers never pass one). A caller that holds
    an explicit anchor (the AutoCount document ingest) passes it so the filter
    does not depend on ambient state agreeing with it.

    ORDERED, because `LIMIT 1` without one picks whatever the planner returns
    first. The scope should leave at most one row per code (`customer_code` is
    unique per company), and on the day it leaves two - a company-shared row,
    an unscoped principal - the useful answer is the one that STATES a segment
    rather than a coin toss between an answer and a blank. `id` breaks the
    remaining tie so a re-run cannot classify the same document two ways.
    """
    if not debtor_code:
        return None
    query = db.query(func.lower(func.coalesce(Customer.market_segment_code, ""))).filter(
        func.upper(Customer.customer_code) == str(debtor_code).strip().upper()
    )
    if company_id is not None:
        query = query.filter(Customer.company_id == company_id)
    return (
        query.order_by(
            (func.coalesce(func.trim(Customer.market_segment_code), "") == ""),
            Customer.id,
        )
        .limit(1)
        .scalar()
    )
