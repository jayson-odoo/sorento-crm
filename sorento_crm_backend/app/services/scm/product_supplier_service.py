"""The `product_suppliers` link - sourcing terms owned by a (product, supplier) pair,
not by any one plan run.

S13 (round 2, PLAN-reorder-feedback-9sep.md, captain screenshots 17-20): "MOQ edits land
only as `set_moq_override` on the recommendation (per run)" - a MOQ the buyer types is
thrown away the moment the plan is re-run, because it only ever touched the frozen row.
`remember_moq` is the fix: it upserts the SAME figure onto the link
`reorder_engine.load_supplier_candidates` reads on every future run, so a correction
made once stays corrected.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

#: What a lead time is worth when a link is created here with none on file - the same
#: "nobody knows one" default `reorder_engine.load_supplier_candidates` falls back to for
#: an uncontracted supplier, so a link born from a remembered MOQ costs nothing to plan
#: with next.
DEFAULT_LEAD_TIME_DAYS = 30


def remember_moq(db: Session, product_id: str, supplier_id: str, moq: float) -> None:
    """Upsert `moq` onto the (product, supplier) link, creating it when it does not
    exist yet.

    Raw SQL, matching `product_suppliers`'s existing write pattern elsewhere in this
    module (`_link` in `tests/scm/test_m3_run.py`) - `company_id` is left to its DB
    default rather than stamped by hand, the same way that helper does.
    """
    existing = db.execute(
        text(
            "SELECT id FROM product_suppliers WHERE product_id = :p AND supplier_id = :s"
        ),
        {"p": product_id, "s": supplier_id},
    ).first()
    if existing:
        db.execute(
            text("UPDATE product_suppliers SET moq = :m WHERE id = :id"),
            {"m": moq, "id": existing[0]},
        )
        return
    db.execute(
        text(
            "INSERT INTO product_suppliers "
            "(id, product_id, supplier_id, standard_lead_time_days, moq, "
            " is_primary_supplier, created_at) "
            "VALUES (:id, :p, :s, :lead, :m, false, now())"
        ),
        {
            "id": str(uuid.uuid4()),
            "p": product_id,
            "s": supplier_id,
            "lead": DEFAULT_LEAD_TIME_DAYS,
            "m": moq,
        },
    )


def resolve_supplier_for_moq(
    db: Session, rec_id: str, product_supplier_id: Optional[str],
    last_purchase_supplier_id: Optional[str],
) -> Optional[str]:
    """Which (product, supplier) link a row's remembered MOQ belongs to.

    Precedence (S13 design, plan section 4 "Round 2"): the row's own CHOSEN supplier
    (`scm.plan_row_decision.supplier_id`, the buyer's override) first, else the supplier
    the LAST PURCHASE actually named (S11's own `inputs.last_purchase.supplier_id`), else
    the primary link - the engine's frozen `rec.supplier_id`, passed in as
    ``product_supplier_id``.
    """
    chosen = db.execute(
        text(
            "SELECT supplier_id FROM scm.plan_row_decision "
            "WHERE recommendation_id = :rid AND supplier_id IS NOT NULL"
        ),
        {"rid": rec_id},
    ).scalar()
    if chosen:
        return str(chosen)
    if last_purchase_supplier_id:
        return str(last_purchase_supplier_id)
    if product_supplier_id:
        return str(product_supplier_id)
    return None
