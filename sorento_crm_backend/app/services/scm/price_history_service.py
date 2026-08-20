"""What we last paid, when, and whether that price is still worth using.

> "the purchase cost that we are going to use now, another decision point: how much i need
>  to buy, should i use the last price, or should i rfq to get new price from supplier ...
>  of course, the system need to suggest to a certain extent, but i am not sure how smart
>  can we suggest whether to use the same price or need new price cause we are blind to
>  market condition"

The buyer drew the boundary and this module stays inside it. **Nothing here knows the
market.** Every output is either a fact from our own purchase ledger or an arithmetic
consequence of one:

- what we last paid this supplier for this item, on which order, on what date
- how old that is today
- how it compares with the purchase before it, when both are in the same currency
- how it compares with the standing cost the plan is costing against

The advice code is a statement about that history and its age. `stale` means "this price
is older than the window", never "prices have gone up". A re-quote is recommended because
we cannot vouch for a six-year-old number, not because we know a better one exists.

## The thresholds are policy configuration (S13e)

`scm.reorder_policy.price_stale_after_days` and `price_movement_threshold_pct` override
the two module constants, which remain only as the defaults for a policy that has not
said. Both are still returned in the payload so the screen states the rule it applied.
The movement threshold also gates the change-supplier suggestion: one figure for "a
price difference worth acting on", not two.
"""
from __future__ import annotations

from datetime import date
from typing import NamedTuple, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

#: A price older than this is not trusted for a new order. Six months.
STALE_AFTER_DAYS = 180

#: Movement between our last two purchases, in percent, that is worth telling the buyer
#: about. Below this the price is holding and re-quoting buys nothing.
MOVEMENT_PCT = 5.0

#: Statuses that are NOT evidence of a purchase. A draft recommendation is this planner's
#: own proposal; feeding it back as "what we paid" would let the system cite itself.
_NOT_A_PURCHASE = ("draft_recommendation", "cancelled", "void")


class Purchase(NamedTuple):
    """One priced line we actually placed."""

    po_number: Optional[str]
    issue_date: Optional[date]
    unit_cost: float
    currency: Optional[str]
    qty: Optional[float]


class PriceAdvice(NamedTuple):
    """The facts, and a code naming which of them dominates.

    `advice` is deliberately a code and not a sentence: the wording belongs to the screen,
    and a backend that ships prose ends up owning the tone of a UI it cannot see.
    """

    #: zero_cost | no_history | other_supplier_price | history_without_price |
    #: unknown_age | stale | moving | recent
    advice: str
    last: Optional[Purchase]
    previous: Optional[Purchase]
    age_days: Optional[int]
    #: Percent change from `previous` to `last`. None unless both exist, share a currency,
    #: and the earlier price is non-zero.
    movement_pct: Optional[float]
    #: True when the last two purchases were billed in different currencies, so the
    #: absence of a movement figure is explained rather than looking like missing data.
    currency_changed: bool
    #: What the plan is costing against (`product_suppliers.unit_cost`).
    standing_cost: Optional[float]
    standing_currency: Optional[str]
    #: Percent the last paid price sits above the standing cost. Same-currency only.
    standing_gap_pct: Optional[float]
    #: Lines we bought from this supplier at 0.00. Set aside rather than treated as the
    #: price (see `_PURCHASES_SQL`), and counted here so the omission is visible instead
    #: of looking like missing history.
    free_of_charge_lines: int = 0
    stale_after_days: int = STALE_AFTER_DAYS
    movement_threshold_pct: float = MOVEMENT_PCT
    #: `other_supplier_price` only - the supplier `last` was actually bought from, which is
    #: NOT the run's chosen supplier for this row. Named so the screen can say "bought from
    #: X, not Y" rather than presenting somebody else's price as if it were a quote from Y.
    other_supplier_code: Optional[str] = None
    other_supplier_name: Optional[str] = None
    #: `history_without_price` only - what the structured PO/SPO extract DOES carry for a
    #: line with no price and no supplier code attached (`purchase_history_reader.py`: it
    #: states the document, the date and the quantity, never a cost). Recoverable facts, so
    #: a product bought 143 times does not read the same as one never bought at all.
    history_last_date: Optional[date] = None
    history_doc_number: Optional[str] = None
    history_po_count: Optional[int] = None
    history_total_qty: Optional[float] = None


NO_HISTORY = PriceAdvice(
    advice="no_history",
    last=None,
    previous=None,
    age_days=None,
    movement_pct=None,
    currency_changed=False,
    standing_cost=None,
    standing_currency=None,
    standing_gap_pct=None,
)


def _pct_change(new: float, old: float) -> Optional[float]:
    """Percent change, or None where the question has no answer.

    Zero is the case that matters: a change from nothing is not a percentage, and both
    `inf` and a flat 100 would be inventions.
    """
    if old is None or new is None or old == 0:
        return None
    return round((new - old) / abs(old) * 100.0, 2)


def assess_price(
    last: Optional[Purchase],
    previous: Optional[Purchase],
    standing_cost: Optional[float],
    standing_currency: Optional[str],
    *,
    as_of: date,
    stale_after_days: int = STALE_AFTER_DAYS,
    movement_pct: float = MOVEMENT_PCT,
) -> PriceAdvice:
    """Turn a pair of purchases into facts plus the code that dominates them.

    `as_of` is passed in rather than read from the clock so the same history always yields
    the same answer, in tests and in a re-read of a frozen run alike.
    """
    # A plan costing at 0.00 outranks every other price question, including having no
    # history at all: a zero price makes any quantity free, so it passes a budget check
    # unchallenged and ranks with no cash pressure behind it. On the live run 24 buy lines
    # covering 11,675 units are costed at exactly 0.00, every one of them tracing back to a
    # zero-value line in the 2020 order import (see `free_of_charge_lines`). The engine's
    # cascade treats that zero as a price on purpose; this says so out loud on the row
    # instead of letting 11,675 units be funded for nothing.
    zero_cost = standing_cost == 0

    if last is None:
        return NO_HISTORY._replace(
            advice="zero_cost" if zero_cost else "no_history",
            standing_cost=standing_cost,
            standing_currency=standing_currency,
        )

    age_days = (as_of - last.issue_date).days if last.issue_date else None

    currency_changed = bool(
        previous is not None
        and last.currency
        and previous.currency
        and last.currency != previous.currency
    )
    move = (
        None
        if previous is None or currency_changed
        else _pct_change(last.unit_cost, previous.unit_cost)
    )

    standing_gap_pct = (
        _pct_change(last.unit_cost, standing_cost)
        if standing_cost is not None
        # A gap across currencies is an exchange rate wearing a price's clothes.
        and (not standing_currency or not last.currency or standing_currency == last.currency)
        else None
    )

    # Order is the point. A zero cost first, because it makes the buy free; then an
    # undated price, which cannot be vouched for at all; then age, because a six-year-old
    # price needs a quote whether it moved or not; then movement, which only means
    # something on a price recent enough to trust.
    if zero_cost:
        advice = "zero_cost"
    elif age_days is None:
        advice = "unknown_age"
    elif age_days > stale_after_days:
        advice = "stale"
    elif move is not None and abs(move) >= movement_pct:
        advice = "moving"
    else:
        advice = "recent"

    return PriceAdvice(
        advice=advice,
        last=last,
        previous=previous,
        age_days=age_days,
        movement_pct=move,
        currency_changed=currency_changed,
        standing_cost=standing_cost,
        standing_currency=standing_currency,
        standing_gap_pct=standing_gap_pct,
        stale_after_days=stale_after_days,
        movement_threshold_pct=movement_pct,
    )


# Keyed out by supplier CODE, not id. `product_id` is already the data-only key the cover
# pool uses, but a supplier has a human code and the frontend rule is that one never puts a
# UUID on screen it could have shown a code for.
_PAIRS_SQL = """
SELECT DISTINCT r.product_id::text AS product_id, r.supplier_id::text AS supplier_id,
       s.supplier_code
FROM scm.reorder_recommendation r
JOIN suppliers s ON s.id = r.supplier_id
WHERE r.run_id = CAST(:run_id AS uuid)
"""

_PURCHASES_SQL = """
WITH pairs AS (
    SELECT DISTINCT r.product_id, r.supplier_id
    FROM scm.reorder_recommendation r
    WHERE r.run_id = CAST(:run_id AS uuid) AND r.supplier_id IS NOT NULL
),
purchases AS (
    SELECT pol.product_id, po.supplier_id, po.po_number, po.issue_date,
           pol.unit_cost::numeric        AS unit_cost,
           COALESCE(pol.currency, po.currency) AS currency,
           pol.qty_ordered::numeric      AS qty,
           ROW_NUMBER() OVER (
               PARTITION BY pol.product_id, po.supplier_id
               -- NULLS LAST: an undated line is the weakest evidence of "most recent",
               -- so it only surfaces when nothing dated exists.
               ORDER BY po.issue_date DESC NULLS LAST, pol.created_at DESC
           ) AS rn
    FROM purchase_order_lines pol
    JOIN purchase_orders po ON po.id = pol.purchase_order_id
    JOIN pairs pr ON pr.product_id = pol.product_id AND pr.supplier_id = po.supplier_id
    -- `> 0`, not merely NOT NULL. 637 lines in the live ledger are recorded at 0.00 -
    -- free-of-charge items, samples and blank rows - and 116 pairs would take one as
    -- their newest price. Handing a buyer "our last price was 0.00" invites an order at
    -- zero, and calling the change from 26.15 to 0.00 a 100% price fall is nonsense.
    -- They are counted separately instead of being folded into the price.
    WHERE pol.unit_cost > 0
      AND po.status NOT IN :not_a_purchase
)
SELECT product_id::text, supplier_id::text, po_number, issue_date, unit_cost, currency, qty, rn
FROM purchases
WHERE rn <= 2
"""

# The cost the RUN used, not today's `product_suppliers.unit_cost`. A run is frozen, and
# the gap the buyer is being shown has to be against the number the plan actually costed
# with - re-reading the master would compare the paid price against a figure that was
# never in the plan, and the gap would move whenever somebody edited the supplier record.
_STANDING_SQL = """
SELECT r.product_id::text AS product_id, r.supplier_id::text AS supplier_id,
       MAX(r.unit_cost)::numeric AS unit_cost, MAX(r.currency) AS currency
FROM scm.reorder_recommendation r
WHERE r.run_id = CAST(:run_id AS uuid) AND r.supplier_id IS NOT NULL AND r.unit_cost IS NOT NULL
GROUP BY r.product_id, r.supplier_id
"""

_FREE_LINES_SQL = """
SELECT pol.product_id::text AS product_id, po.supplier_id::text AS supplier_id,
       COUNT(*) AS n
FROM purchase_order_lines pol
JOIN purchase_orders po ON po.id = pol.purchase_order_id
JOIN (
    SELECT DISTINCT r.product_id, r.supplier_id
    FROM scm.reorder_recommendation r
    WHERE r.run_id = CAST(:run_id AS uuid) AND r.supplier_id IS NOT NULL
) pr ON pr.product_id = pol.product_id AND pr.supplier_id = po.supplier_id
WHERE pol.unit_cost = 0 AND po.status NOT IN :not_a_purchase
GROUP BY pol.product_id, po.supplier_id
"""


def _f(v) -> Optional[float]:
    return None if v is None else float(v)


# The most recent PRICED purchase for a product from ANY supplier - used only as a
# fallback (see `price_history_for_run`) when the run's own chosen supplier has no priced
# purchase of its own. "Never bought this" is a different, more alarming claim than
# "never bought it from THIS supplier, but we have paid someone else for it".
_OTHER_SUPPLIER_PRICE_SQL = """
WITH ranked AS (
    SELECT pol.product_id, po.po_number, po.issue_date,
           pol.unit_cost::numeric AS unit_cost,
           COALESCE(pol.currency, po.currency) AS currency,
           pol.qty_ordered::numeric AS qty,
           s.supplier_code, s.supplier_name,
           ROW_NUMBER() OVER (
               PARTITION BY pol.product_id
               ORDER BY po.issue_date DESC NULLS LAST, pol.created_at DESC
           ) AS rn
    FROM purchase_order_lines pol
    JOIN purchase_orders po ON po.id = pol.purchase_order_id
    LEFT JOIN suppliers s ON s.id = po.supplier_id
    WHERE pol.product_id = ANY(CAST(:pids AS uuid[]))
      AND pol.unit_cost > 0
      AND po.status NOT IN :not_a_purchase
)
SELECT product_id::text AS product_id, po_number, issue_date, unit_cost, currency, qty,
       supplier_code, supplier_name
FROM ranked WHERE rn = 1
"""

# Every line the product's own history carries, priced or not - the totals a buyer can
# still be told even where `_OTHER_SUPPLIER_PRICE_SQL` above found nothing (a purchase
# recorded with no price at all - the structured SPO extract's whole shape).
_PRODUCT_HISTORY_TOTALS_SQL = """
SELECT pol.product_id::text AS product_id,
       COUNT(DISTINCT po.po_number) AS po_count,
       COALESCE(SUM(pol.qty_ordered), 0) AS total_qty
FROM purchase_order_lines pol
JOIN purchase_orders po ON po.id = pol.purchase_order_id
WHERE pol.product_id = ANY(CAST(:pids AS uuid[]))
  AND po.status NOT IN :not_a_purchase
GROUP BY pol.product_id
"""

_PRODUCT_HISTORY_LAST_SQL = """
WITH ranked AS (
    SELECT pol.product_id, po.po_number, po.issue_date,
           ROW_NUMBER() OVER (
               PARTITION BY pol.product_id
               ORDER BY po.issue_date DESC NULLS LAST, pol.created_at DESC
           ) AS rn
    FROM purchase_order_lines pol
    JOIN purchase_orders po ON po.id = pol.purchase_order_id
    WHERE pol.product_id = ANY(CAST(:pids AS uuid[]))
      AND po.status NOT IN :not_a_purchase
)
SELECT product_id::text AS product_id, po_number, issue_date
FROM ranked WHERE rn = 1
"""


def _other_supplier_price(db: Session, product_ids: list[str],
                          not_a_purchase: tuple[str, ...]) -> dict[str, dict]:
    if not product_ids:
        return {}
    rows = db.execute(text(_OTHER_SUPPLIER_PRICE_SQL),
                      {"pids": product_ids, "not_a_purchase": not_a_purchase}).mappings().all()
    return {
        r["product_id"]: {
            "purchase": Purchase(
                po_number=r["po_number"], issue_date=r["issue_date"],
                unit_cost=float(r["unit_cost"]), currency=r["currency"], qty=_f(r["qty"]),
            ),
            "supplier_code": r["supplier_code"],
            "supplier_name": r["supplier_name"],
        }
        for r in rows
    }


def _product_history(db: Session, product_ids: list[str],
                     not_a_purchase: tuple[str, ...]) -> dict[str, dict]:
    if not product_ids:
        return {}
    params = {"pids": product_ids, "not_a_purchase": not_a_purchase}
    totals = {r["product_id"]: r for r in
             db.execute(text(_PRODUCT_HISTORY_TOTALS_SQL), params).mappings().all()}
    last = {r["product_id"]: r for r in
           db.execute(text(_PRODUCT_HISTORY_LAST_SQL), params).mappings().all()}
    out: dict[str, dict] = {}
    for pid, t in totals.items():
        l = last.get(pid)
        out[pid] = {
            "po_count": int(t["po_count"]),
            "total_qty": _f(t["total_qty"]),
            "last_date": l["issue_date"] if l else None,
            "doc_number": l["po_number"] if l else None,
        }
    return out


def price_history_for_run(
    db: Session, run_id: str, *, as_of: Optional[date] = None
) -> dict[str, PriceAdvice]:
    """Price facts for every (product, supplier) pair the run recommends.

    Keyed ``"{product_id}:{supplier_code}"`` because the question the buyer asked is about
    that pair. A cheaper price from a different supplier is a different negotiation and is
    never substituted in: the whole point of the number is that it is what THIS supplier
    charged us.
    """
    as_of = as_of or date.today()

    # The configured thresholds, from the global planning policy (S13e). NULL = default.
    cfg = db.execute(text(
        "SELECT price_stale_after_days, price_movement_threshold_pct "
        "FROM scm.reorder_policy WHERE scope_type = 'global' AND is_active = true "
        "ORDER BY priority DESC NULLS LAST LIMIT 1"
    )).first()
    stale_after = int(cfg[0]) if cfg and cfg[0] else STALE_AFTER_DAYS
    movement = float(cfg[1]) if cfg and cfg[1] else MOVEMENT_PCT

    rows = db.execute(
        text(_PURCHASES_SQL),
        {"run_id": run_id, "not_a_purchase": _NOT_A_PURCHASE},
    ).mappings().all()

    found: dict[str, dict[int, Purchase]] = {}
    for r in rows:
        key = f"{r['product_id']}:{r['supplier_id']}"
        found.setdefault(key, {})[int(r["rn"])] = Purchase(
            po_number=r["po_number"],
            issue_date=r["issue_date"],
            unit_cost=float(r["unit_cost"]),
            currency=r["currency"],
            qty=_f(r["qty"]),
        )

    standing: dict[str, tuple[Optional[float], Optional[str]]] = {}
    for r in db.execute(text(_STANDING_SQL), {"run_id": run_id}).mappings().all():
        standing[f"{r['product_id']}:{r['supplier_id']}"] = (_f(r["unit_cost"]), r["currency"])

    pairs = db.execute(text(_PAIRS_SQL), {"run_id": run_id}).mappings().all()

    free_lines: dict[str, int] = {
        f"{r['product_id']}:{r['supplier_id']}": int(r["n"])
        for r in db.execute(
            text(_FREE_LINES_SQL),
            {"run_id": run_id, "not_a_purchase": _NOT_A_PURCHASE},
        ).mappings().all()
    }

    # Fallback facts for a pair whose OWN chosen supplier has no priced purchase - so
    # "never bought this" (a code the buyer trusts as a green light to go get a fresh
    # quote) is not shown for a product this system genuinely has history for, only
    # under a different supplier or with no price attached at all (the structured SPO
    # extract carries neither a supplier code nor a price - `purchase_history_reader.py`).
    product_ids = sorted({pair["product_id"] for pair in pairs})
    other_supplier = _other_supplier_price(db, product_ids, _NOT_A_PURCHASE)
    history = _product_history(db, product_ids, _NOT_A_PURCHASE)

    out: dict[str, PriceAdvice] = {}
    for pair in pairs:
        inner = f"{pair['product_id']}:{pair['supplier_id']}"
        seen = found.get(inner, {})
        cost, currency = standing.get(inner, (None, None))
        advice = assess_price(
            seen.get(1), seen.get(2), cost, currency, as_of=as_of,
            stale_after_days=stale_after, movement_pct=movement,
        )._replace(free_of_charge_lines=free_lines.get(inner, 0))

        # Only `no_history` is eligible for a fallback - `zero_cost` is a live costing
        # problem that outranks it, and every other code already means a priced purchase
        # under this exact supplier was found.
        if advice.advice == "no_history":
            other = other_supplier.get(pair["product_id"])
            hist = history.get(pair["product_id"])
            if other is not None:
                advice = advice._replace(
                    advice="other_supplier_price",
                    last=other["purchase"],
                    other_supplier_code=other["supplier_code"],
                    other_supplier_name=other["supplier_name"],
                )
            elif hist is not None:
                advice = advice._replace(
                    advice="history_without_price",
                    history_last_date=hist["last_date"],
                    history_doc_number=hist["doc_number"],
                    history_po_count=hist["po_count"],
                    history_total_qty=hist["total_qty"],
                )
        out[f"{pair['product_id']}:{pair['supplier_code']}"] = advice
    return out
