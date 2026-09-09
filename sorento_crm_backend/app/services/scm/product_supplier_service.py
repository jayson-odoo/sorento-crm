"""The `product_suppliers` link - sourcing terms owned by a (product, supplier) pair,
not by any one plan run.

S13 (round 2, PLAN-reorder-feedback-9sep.md, captain screenshots 17-20): "MOQ edits land
only as `set_moq_override` on the recommendation (per run)" - a MOQ the buyer types is
thrown away the moment the plan is re-run. `remember_moq`/`clear_moq` are the fix: they
upsert (or blank) the SAME figure onto the link `reorder_engine.load_supplier_candidates`
reads on every future run, so a correction made once stays corrected.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

#: What a lead time is worth when a link is created here with none on file - the same
#: "nobody knows one" default `reorder_engine.load_supplier_candidates` falls back to for
#: an uncontracted supplier, so a link born from a remembered MOQ costs nothing to plan
#: with next.
DEFAULT_LEAD_TIME_DAYS = 30


def _product_company_id(db: Session, product_id: str) -> Optional[str]:
    """The product's own `company_id` - the one authoritative source for a NEW link's
    stamp (review fix round 2, 9 Sep): `product_suppliers.company_id` carries a DB
    DEFAULT (the legacy single-tenant company), and relying on it silently mis-stamps a
    link created for any other company. Read off the product, never assumed."""
    return db.execute(
        text("SELECT company_id FROM products WHERE id = :p"), {"p": product_id}
    ).scalar()


def remember_moq(
    db: Session,
    product_id: str,
    supplier_id: str,
    moq: float,
    *,
    co: str = "",
    co_params: Optional[dict[str, Any]] = None,
) -> None:
    """Upsert `moq` onto the (product, supplier) link, creating it when it does not
    exist yet.

    `product_suppliers.moq` is an INTEGER column, so a fractional buyer input (never
    offered by the FE input today, but not refused either) is rounded before it lands
    here rather than failing the write or silently truncating toward zero.

    `co`/`co_params` are `company_sql_predicate`'s own output, threaded in from
    `set_moq_override` (review fix round 2, 9 Sep) rather than re-derived, so the read
    this call does shares the SAME company scope the caller already resolved for the
    recommendation it is acting on.
    """
    co_params = co_params or {}
    moq_int = int(round(moq))
    existing = db.execute(
        text(
            "SELECT id FROM product_suppliers "
            f"WHERE product_id = :p AND supplier_id = :s AND {co or 'true'}"
        ),
        {"p": product_id, "s": supplier_id, **co_params},
    ).first()
    if existing:
        db.execute(
            text("UPDATE product_suppliers SET moq = :m WHERE id = :id"),
            {"m": moq_int, "id": existing[0]},
        )
        return
    # A raw INSERT never reaches a company_id by accident - read off the product row
    # explicitly and stamped by hand, never left to the column's DB default.
    company_id = _product_company_id(db, product_id)
    db.execute(
        text(
            "INSERT INTO product_suppliers "
            "(id, product_id, supplier_id, standard_lead_time_days, moq, "
            " is_primary_supplier, company_id, created_at) "
            "VALUES (:id, :p, :s, :lead, :m, false, :co_id, now())"
        ),
        {
            "id": str(uuid.uuid4()),
            "p": product_id,
            "s": supplier_id,
            "lead": DEFAULT_LEAD_TIME_DAYS,
            "m": moq_int,
            "co_id": company_id,
        },
    )


def clear_moq(
    db: Session,
    product_id: str,
    supplier_id: str,
    *,
    co: str = "",
    co_params: Optional[dict[str, Any]] = None,
) -> None:
    """NULL an EXISTING link's `moq` - never creates one (finding 8, review fix round 2).

    A cleared MOQ input is a retraction of a number the buyer once remembered, not a
    statement that this (product, supplier) pair needs a link at all - a no-op UPDATE
    against a pair with no link leaves nothing behind, which is the whole point.
    """
    co_params = co_params or {}
    db.execute(
        text(
            "UPDATE product_suppliers SET moq = NULL "
            f"WHERE product_id = :p AND supplier_id = :s AND {co or 'true'}"
        ),
        {"p": product_id, "s": supplier_id, **co_params},
    )


def resolve_supplier_for_moq(db: Session, rec_ids: list[str]) -> Optional[str]:
    """Which (product, supplier) link a rec's remembered MoQ belongs to, resolved across
    every rec id named - a bare list of one for the single-row `PUT
    /recommendations/{id}/moq` route, a product's whole set of member recs for a
    product-grain row's fan-out (AC-S13.1, review fix round 2: resolved ONCE per
    product, never per member, so two locations of the same product bought from two
    different suppliers do not overwrite each other's link on every save).

    Precedence (S13 design, plan section 4 "Round 2"): the buyer's own CHOSEN supplier on
    ANY of the named rows (`scm.plan_row_decision.supplier_id`) first, else the MOST
    RECENT last-purchase supplier across them (`inputs.last_purchase`, by purchase date),
    else the first member's frozen primary link (`rec.supplier_id`).
    """
    ids = [str(r) for r in rec_ids if r]
    if not ids:
        return None

    chosen = db.execute(
        text(
            "SELECT supplier_id FROM scm.plan_row_decision "
            "WHERE recommendation_id = ANY(CAST(:rids AS uuid[])) AND supplier_id IS NOT NULL "
            "ORDER BY decided_at DESC LIMIT 1"
        ),
        {"rids": ids},
    ).scalar()
    if chosen:
        return str(chosen)

    rows = db.execute(
        text(
            "SELECT supplier_id, inputs FROM scm.reorder_recommendation "
            "WHERE id = ANY(CAST(:rids AS uuid[]))"
        ),
        {"rids": ids},
    ).mappings().all()

    best_supplier: Optional[str] = None
    best_at: Optional[str] = None
    primary_fallback: Optional[str] = None
    for r in rows:
        if primary_fallback is None and r["supplier_id"]:
            primary_fallback = str(r["supplier_id"])
        lp = (r["inputs"] or {}).get("last_purchase") or {}
        sid = lp.get("supplier_id")
        at = lp.get("at")
        if sid and (best_at is None or (at or "") > (best_at or "")):
            best_supplier = str(sid)
            best_at = at
    return best_supplier or primary_fallback
