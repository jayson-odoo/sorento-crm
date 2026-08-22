"""The proof behind a hot/cold verdict: one product, both demand classes, every location.

The captain, reading the trail: "don't give me jargon like abc classification, just tell me
hot selling or cold selling, at project or retail, with some button for me to view detail as
a proof". The board and the sheet already say "Dealer hot-selling" / "Cold at retail" in
plain words (`project_fulfilment_board_service._pool_why`); this is the number behind the
word, read on demand rather than carried on every line.

Rank, "of" and cumulative share are computed HERE, live, over the same set of rows the
hot-selling predicate itself reads (`ProjectSupplyService._classification`): a non-null
quantity for the class, at an active, `counts_as_available` warehouse. The letter (A/B/C)
is the one the nightly classification run already wrote to `scm.item_classification` -
never recomputed - so a "hot" verdict here can never disagree with the one the board acted
on; only the rank/share evidence shown beside it is fresh.

Everything below is built from mapped Table columns (`ItemClassification`, `Warehouse`), NOT
raw ``scm.``-qualified `text()` SQL: a hardcoded schema prefix in raw SQL bypasses the ORM's
`schema_translate_map`, which is how the test suite's scratch schema (`tests/_pg_fixture.py
blank_session`) redirects writes and reads away from the real, populated table. Analytics's
own `_abc_class_qty_totals` can get away with that because its tests run against the real
database with a future `as_of`; this function has no time window to hide behind (a letter is
overwritten in place, not dated), so it has to stay ORM-expressible instead.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.product import Product
from app.models.scm import AbcXyzPolicy, ItemClassification
from app.services.error_handler import AppException
from app.services.scm.front_planning_engine import qty_text

#: The trailing window the nightly classification run ranks quantity over
#: (`app.services.scm.analytics_service.ANNUAL_DAYS`) - restated rather than imported so this
#: module never reaches for analytics_service's raw ``scm.``-qualified SQL (see module
#: docstring).
WINDOW_DAYS = 365

_DEFAULT_ABC_A_PCT = 80.0

#: demand_class -> (the quantity column, the letter column) on `scm.item_classification`.
_CLASS_COLUMNS = {
    "retail": (ItemClassification.annual_qty_retail, ItemClassification.abc_class_retail),
    "project": (ItemClassification.annual_qty_project, ItemClassification.abc_class_project),
}
_CLASS_LABELS = {"retail": "Dealer", "project": "Project"}


def _hot_cut_pct(db: Session) -> float:
    """The active `abc_a_pct`, normalised the same way
    `analytics_service._normalize_abc_cuts` reads it (a value <=1 is a fraction, x100)."""
    row = (
        db.query(AbcXyzPolicy)
        .filter(AbcXyzPolicy.is_active.is_(True))
        .order_by(AbcXyzPolicy.updated_at.desc(), AbcXyzPolicy.created_at.asc())
        .first()
    )
    if row is None or row.abc_a_pct is None:
        return _DEFAULT_ABC_A_PCT
    pct = float(row.abc_a_pct)
    return pct * 100.0 if pct <= 1 else pct


def _class_rows(db: Session, product_id: str, demand_class: str) -> List[Any]:
    """Rank every product x location the network holds for one demand class, then return
    only this product's rows - ordered, so `rank` on the row already matches its position.
    """
    qty_col, letter_col = _CLASS_COLUMNS[demand_class]
    scoped = (
        select(
            ItemClassification.product_id.label("product_id"),
            Warehouse.warehouse_code.label("warehouse_code"),
            qty_col.label("qty"),
            letter_col.label("letter"),
            ItemClassification.computed_at.label("computed_at"),
        )
        .join(Warehouse, Warehouse.id == ItemClassification.warehouse_id)
        .where(
            qty_col.isnot(None),
            Warehouse.is_active.is_(True),
            Warehouse.counts_as_available.is_(True),
        )
        .cte("scoped")
    )
    ranked = (
        select(
            scoped.c.product_id,
            scoped.c.warehouse_code,
            scoped.c.qty,
            scoped.c.letter,
            scoped.c.computed_at,
            func.rank().over(order_by=scoped.c.qty.desc()).label("rnk"),
            func.count().over().label("of_count"),
            func.sum(scoped.c.qty)
            .over(order_by=scoped.c.qty.desc(), rows=(None, 0))
            .label("running_qty"),
            func.sum(scoped.c.qty).over().label("total_qty"),
        )
        .select_from(scoped)
        .cte("ranked")
    )
    stmt = select(ranked).where(ranked.c.product_id == product_id).order_by(ranked.c.rnk)
    return db.execute(stmt).fetchall()


def classification_evidence(db: Session, product_id: str) -> Dict[str, Any]:
    """Hot or cold, at retail and at project, with the ranked evidence behind each verdict.

    `verdict` per class: `hot` if any location's letter is A, `cold` if rows exist with a
    letter and none is A, `unclassified` if the class has no row at all (no delivered demand
    of it, ever, at an active location) - the same three-way read
    `project_fulfilment_board_service._pool_why` already speaks in words.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise AppException(
            status_code=404, message="Product not found.", code="product_not_found"
        )

    hot_cut_pct = _hot_cut_pct(db)
    computed_at = None
    classes = []
    for demand_class, label in _CLASS_LABELS.items():
        rows = _class_rows(db, product_id, demand_class)
        locations = []
        any_hot = False
        for row in rows:
            letter = (row.letter or "").upper() or None
            hot = letter == "A"
            any_hot = any_hot or hot
            qty = Decimal(str(row.qty))
            total = Decimal(str(row.total_qty)) if row.total_qty is not None else None
            running = Decimal(str(row.running_qty)) if row.running_qty is not None else None
            cumulative_share = float(running / total * 100) if total else None
            # This row's OWN share of the class's total quantity - "Its share" in the popover.
            # Captain, 19 Aug 2026, reading a cumulative "Share: top 93.6%": "read as good" -
            # a single small row can sit at the top of a thin ranking and look impressive read
            # as a percentage of the WHOLE, so the row now states its own weight plainly and
            # leaves the cumulative figure to "Ranked above it" (FE: cumulative minus this).
            own_share = float(qty / total * 100) if total else None
            locations.append(
                {
                    "warehouse_code": row.warehouse_code,
                    "qty_delivered": qty_text(qty),
                    "rank": int(row.rnk),
                    "of": int(row.of_count),
                    "share_pct": round(own_share, 2) if own_share is not None else None,
                    "cumulative_share_pct": (
                        round(cumulative_share, 1) if cumulative_share is not None else None
                    ),
                    "letter": letter,
                    "hot": hot,
                }
            )
            if row.computed_at is not None and (
                computed_at is None or row.computed_at > computed_at
            ):
                computed_at = row.computed_at
        if not rows:
            verdict = "unclassified"
        elif any_hot:
            verdict = "hot"
        else:
            verdict = "cold"
        classes.append(
            {
                "demand_class": demand_class,
                "label": label,
                "verdict": verdict,
                "locations": locations,
            }
        )

    return {
        "product_id": str(product.id),
        "item_code": product.product_code,
        "computed_at": computed_at,
        "window_days": WINDOW_DAYS,
        "hot_cut_pct": hot_cut_pct,
        "classes": classes,
    }
