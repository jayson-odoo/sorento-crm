"""The `product_suppliers` link - sourcing terms owned by a (product, supplier) pair,
not by any one plan run.

S13 (round 2, PLAN-reorder-feedback-9sep.md, captain screenshots 17-20): "MOQ edits land
only as `set_moq_override` on the recommendation (per run)" - a MOQ the buyer types is
thrown away the moment the plan is re-run. `remember_moq` is the fix: it upserts the
figure onto the link `reorder_engine.load_supplier_candidates` reads on every future run,
so a correction made once stays corrected.

Review fix round 3, 9 Sep, ruling: a CLEARED MOQ (0/blank) touches only the row's own
per-run override, never the remembered link - a buyer who types a fresh number back in
must not find the link already knows a different one. There is deliberately no
`clear_moq` here any more; see `reorder_run_service.set_moq_override`.
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


def remember_moq(db: Session, product_id: str, supplier_id: str, moq: float) -> None:
    """Upsert `moq` onto the (product, supplier) link, keyed globally on the PAIR -
    an existing link wins regardless of which company it is stamped to (finding 2,
    review fix round 3), and the write touches ONLY `moq`, leaving that row's
    `company_id` exactly as it was. A genuinely new row is stamped with the PRODUCT's
    own `company_id`, read off `products` rather than left to the column's DB default
    (review fix round 2).

    NOT a single `INSERT ... ON CONFLICT (product_id, supplier_id) DO UPDATE`, despite
    that being the obvious shape: measured directly (`\\d product_suppliers`), the
    live/shared database's actual unique constraint is `uq_product_supplier_eff` on
    `(product_id, supplier_id, effective_from)` - a column this feature has never read
    or set (a bootstrap-built database instead carries the MODEL's own declared 2-column
    `uq_product_suppliers_product_id_supplier_id`, which no migration has ever created on
    the shared database, so the two disagree). `ON CONFLICT (product_id, supplier_id)`
    raises `InvalidColumnReference` against the real constraint; targeting the 3-column
    one instead would silently open a SECOND row every time `effective_from`'s
    CURRENT_DATE default ticks over a day boundary, which is the exact "moq drifts
    across links" bug this whole feature exists to close. The select-then-branch below
    works correctly against BOTH shapes and is the honest fix until a migration
    reconciles the schemas - a bigger, riskier change (existing (product, supplier)
    duplicates across `effective_from` would have to be consolidated first) than this
    review round covers.

    `product_suppliers.moq` is an INTEGER column, so a fractional buyer input (never
    offered by the FE input today, but not refused either) is rounded before it lands
    here rather than failing the write or silently truncating toward zero.
    """
    moq_int = int(round(moq))
    existing = db.execute(
        text("SELECT id FROM product_suppliers WHERE product_id = :p AND supplier_id = :s"),
        {"p": product_id, "s": supplier_id},
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


def resolve_supplier_for_moq(
    db: Session, rec_ids: list[str],
    *, co: str = "", co_params: Optional[dict[str, Any]] = None,
) -> Optional[str]:
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

    `co`/`co_params` (`company_sql_predicate`'s own output, review fix round 3, finding 8)
    are defense in depth on both reads - `rec_ids` themselves are already scoped by every
    caller before they reach here, so this narrows a resolution that could otherwise never
    actually cross a company boundary, rather than closing a real gap.
    """
    ids = [str(r) for r in rec_ids if r]
    if not ids:
        return None
    co_params = co_params or {}

    chosen = db.execute(
        text(
            "SELECT supplier_id FROM scm.plan_row_decision "
            "WHERE recommendation_id = ANY(CAST(:rids AS uuid[])) AND supplier_id IS NOT NULL "
            f"AND {co or 'true'} "
            "ORDER BY decided_at DESC LIMIT 1"
        ),
        {"rids": ids, **co_params},
    ).scalar()
    if chosen:
        return str(chosen)

    rows = db.execute(
        text(
            "SELECT supplier_id, inputs FROM scm.reorder_recommendation "
            f"WHERE id = ANY(CAST(:rids AS uuid[])) AND {co or 'true'}"
        ),
        {"rids": ids, **co_params},
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
