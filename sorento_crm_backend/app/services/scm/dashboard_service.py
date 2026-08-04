"""SCM M1 dashboard read-model service.

Sources the M0 views (``scm.net_position_v`` / ``scm.consumption_v``) joined to
canonical ``public`` master data, and computes per SKU×warehouse **health status**,
**valuation**, **imbalance**, and the attention ranking that drives the default sort.

Health status (per SKU×warehouse or per aggregated product) precedence:
  1. ``stockout``  — quantity_on_hand == 0 (rendered "Out of stock", M8-B7)
  2. ``dead``      — on_hand > 0 AND last outbound movement older than the resolved
                     ``reorder_policy.dead_stock_days`` (or never moved)
  3. ``low``       — on_hand > 0, not dead, and ``net <= reorder_point`` (the demand-aware
                     engine ROP from the latest completed run); rendered "Low stock" (M8-B7)
  4. ``incoming``  — on_hand > 0, not dead/low, and an open (placed) PO contributes supply
  5. ``healthy``   — otherwise

``stockout_with_committed`` = on_hand == 0 AND committed > 0 (the reorder-signal
attention badge). ``imbalance`` = the same SKU is stocked-out in one warehouse while
holding surplus in another. Valuation = quantity_on_hand × products.cost_price
(null cost → null valuation). Deferred M2/M3 fields are always returned as null.

Filters (shared): warehouses (codes), category_id (product_categories.id),
supplier (supplier_code), health (status chip), q (SKU/name search). The health
filter is applied AFTER status computation (it is a derived attribute).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm.reorder_policy import (
    DEFAULT_DEAD_STOCK_DAYS,
    resolve_global_dead_stock_days,
    resolve_global_overstock_days,
)

# ABC value class rank (A most valuable) — used to pick a product-level class
# across its per-warehouse classification rows.
_ABC_RANK = {"A": 0, "B": 1, "C": 2}

# PO statuses that count as placed supply — mirrors scm.on_order_v (drafts excluded).
PLACED_PO_STATUSES = ("active", "received", "partial", "closed")

_STATUS_RANK = {"stockout": 1, "dead": 2, "low": 3, "incoming": 4, "healthy": 5}


@dataclass
class ScmFilters:
    warehouses: List[str] = field(default_factory=list)
    category_id: Optional[str] = None
    supplier: Optional[str] = None
    health: Optional[str] = None
    q: Optional[str] = None
    # M2 classification filters. Values: A|B|C|unknown / X|Y|Z|unknown. ``unknown``
    # targets rows the analytics job couldn't classify (null class), so they stay
    # reachable rather than silently hidden.
    abc: Optional[str] = None
    xyz: Optional[str] = None
    # Product-lifecycle scope. DEFAULTS are the FOCUSED view — active + ongoing —
    # so inactive/discontinued SKUs never inflate headline counts/valuations unless
    # the user explicitly widens the scope. active_status ∈ {active,inactive,all}
    # → products.is_active; lifecycle ∈ {ongoing,discontinued,all} → is_discontinued.
    active_status: str = "active"
    lifecycle: str = "ongoing"


def _f(value) -> float:
    return float(value) if value is not None else 0.0


def _compute_status(on_hand: float, on_order: float, committed: float,
                    last_movement: Optional[date], dead_days: int, today: date,
                    net: Optional[float] = None,
                    reorder_point: Optional[float] = None) -> str:
    if on_hand <= 0:
        return "stockout"
    if last_movement is None or (today - last_movement).days > dead_days:
        return "dead"
    # M8-B7: a stocked, non-dead SKU sitting at/under its demand-aware reorder point
    # reads as ``low`` (Low stock) rather than healthy/incoming — reorder is the signal
    # that matters. ``net`` already folds in on_order, so an inbound PO that still leaves
    # net at/under ROP is genuinely low. A null reorder_point (no completed run / no rec)
    # skips this branch, so an un-planned SKU never falsely reads as low.
    if reorder_point is not None and net is not None and net <= reorder_point:
        return "low"
    if on_order > 0:
        return "incoming"
    return "healthy"


def _attention_rank(status: str, stockout_with_committed: bool) -> int:
    if stockout_with_committed:
        return 0
    return _STATUS_RANK.get(status, 4)


def _days_of_cover(net_position: float, avg_daily_demand: Optional[float]) -> Optional[float]:
    """Whole days of forward cover = net_position ÷ avg_daily_demand.

    ``None`` when there is no forward cover to quote — either no demand
    (avg_daily_demand 0/None, so cover is effectively infinite; the FE renders ∞
    when there is stock) or a deficit (net_position < 0, nothing to cover with).
    """
    if not avg_daily_demand or avg_daily_demand <= 0:
        return None
    if net_position < 0:
        return None
    return round(net_position / avg_daily_demand)


def _is_overstock(on_hand: float, days_of_cover: Optional[float],
                  avg_daily_demand: Optional[float], ceiling: int) -> bool:
    """Overstock = over-invested inventory. A stocked SKU qualifies TWO ways:

      * finite forward cover above the ceiling (``days_of_cover > ceiling``), OR
      * INFINITE cover with stock — ``on_hand > 0`` but no demand
        (``avg_daily_demand`` 0/None, so days-of-cover is ∞): capital parked on a
        non-mover is over-invested too.

    Zero-stock rows never count (nothing is invested). Keeping the ∞ case here makes
    the grid colour, the rollup count/valuation and the ``health=overstock`` filter all
    agree (S1) — previously the grid painted ∞-cover overstock while the count excluded it.
    """
    if on_hand <= 0:
        return False
    if days_of_cover is not None and days_of_cover > ceiling:
        return True
    return not avg_daily_demand  # 0 or None → infinite cover with stock


def _is_below_rop(on_hand: float, net: float, reorder_point: Optional[float]) -> bool:
    """Low-stock (M8-B): a STOCKED product sitting at or under its demand-aware
    reorder point (engine ROP from the latest completed run, NOT a static min qty).

    ``on_hand > 0`` keeps stockout precedence (M8-B2: an ``on_hand <= 0`` product is
    ``stockout``, never ``low`` — counted in the Stockouts tile only). A null
    ``reorder_point`` (no completed run, or no rec for this product) never counts, so
    an un-planned SKU is simply absent from the low set rather than falsely flagged."""
    if reorder_point is None:
        return False
    if on_hand <= 0:
        return False
    return net <= reorder_point


def _matches_class(value: Optional[str], wanted: Optional[str]) -> bool:
    """ABC/XYZ class-filter predicate. ``unknown`` matches an unclassified (null)
    row; a concrete letter matches exactly; no filter matches everything."""
    if not wanted:
        return True
    if wanted == "unknown":
        return value is None
    return value == wanted


def _class_filter(rows: List[dict], filters: ScmFilters) -> List[dict]:
    """Narrow per SKU×warehouse rows to the requested ABC/XYZ (Value/Demand) class.

    Applied to the warehouse-tile / supplier / roll-up aggregations so their health
    tallies, valuations and counts honour the Value/Demand filter exactly like the
    drill-down popup does (both filter on the per-warehouse ``abc_class``/``xyz_class``).
    A no-op when neither class filter is set."""
    if not filters.abc and not filters.xyz:
        return rows
    return [
        r for r in rows
        if _matches_class(r["abc_class"], filters.abc)
        and _matches_class(r["xyz_class"], filters.xyz)
    ]


def _matches_health(row: dict, health: str) -> bool:
    """Health-filter predicate. ``overstock`` is demand-derived (days-of-cover over
    the ceiling) rather than one of the mutually-exclusive computed statuses, so it
    matches on the row's precomputed ``overstock`` flag; everything else matches the
    computed status letter-for-letter."""
    if health == "overstock":
        return bool(row.get("overstock"))
    if health == "low":
        # Low-stock is demand-derived (net at/under the engine reorder point) and is NOT
        # one of the mutually-exclusive computed statuses, so it matches the row's
        # precomputed ``below_rop`` flag (which already enforces stockout precedence).
        return bool(row.get("below_rop"))
    return row["status"] == health


def _dominant_class(rows: List[dict], class_key: str, weight_key: str) -> Optional[str]:
    """Pick a single product-level ABC/XYZ class across per-warehouse rows.

    Chooses the class of the warehouse row carrying the largest ``weight_key``
    (annual_value for ABC, avg_daily_demand for XYZ) — the dominant value/demand
    location — so a product classed A anywhere it matters surfaces as A. Ties
    break on the value class rank then warehouse_code for determinism.
    """
    best: Optional[dict] = None
    for r in rows:
        if r.get(class_key) is None:
            continue
        if best is None:
            best = r
            continue
        rw = r.get(weight_key) or 0.0
        bw = best.get(weight_key) or 0.0
        if rw > bw or (
            rw == bw
            and _ABC_RANK.get(str(r.get(class_key)), 9)
            < _ABC_RANK.get(str(best.get(class_key)), 9)
        ):
            best = r
    return best.get(class_key) if best else None


class ScmDashboardService:
    def __init__(self, db: Session):
        self.db = db
        self._today = date.today()
        self._policies: Optional[List[dict]] = None
        self._global_dead_days: Optional[int] = None
        self._global_loaded = False
        self._overstock_days: Optional[int] = None
        self._latest_run_id: Optional[str] = None
        self._latest_run_loaded = False

    def _company_clause(self, column: str, prefix: str) -> Tuple[str, dict]:
        """``(clause, params)`` restricting a RAW query to the caller's company.

        Every reader on this service is raw SQL over the `scm.*` views, so the ORM
        isolation filter never sees any of them. Company is a property of the LOCATION,
        so the clause is applied to the joined `warehouses` (or `products` / `suppliers`
        where the row names no location) and everything derived from that row inherits it.
        Always returns a usable boolean, so callers can splice it unconditionally.
        """
        clause, params = company_sql_predicate(self.db, column, param_prefix=prefix)
        return (clause or "true"), params

    # -- latest completed reorder run (reorder-point source) -----------------

    def _latest_completed_run_id(self) -> Optional[str]:
        """Id of the most recent completed reorder run, whose frozen
        ``reorder_recommendation.reorder_point`` values drive the low-stock signal
        (M8-B). The engine is NOT re-run — this is a read of the last snapshot. Ordered
        by finish time (falling back to creation) so the freshest plan wins — the SAME
        ordering key ``reorder_run_service.today_or_latest_run`` uses for its
        latest-completed fallback, so the dashboard ROP source and the reorder page
        reference the same run. ``None`` when no run has ever completed (low-stock then
        reads as zero, never crashing)."""
        if not self._latest_run_loaded:
            # Company-scoped by hand: raw SQL bypasses the ORM isolation filter, and the run
            # this picks is what drives the low-stock signal. Another company's frozen reorder
            # points would produce a warning list about stock this company does not hold.
            co, co_params = company_sql_predicate(
                self.db, "company_id", param_prefix="cdr"
            )
            row = self.db.execute(text(
                "SELECT id FROM scm.reorder_run "
                "WHERE status = 'completed' "
                f"{('AND ' + co + ' ') if co else ''}"
                "ORDER BY COALESCE(finished_at, created_at) DESC, created_at DESC "
                "LIMIT 1"
            ), co_params).fetchone()
            self._latest_run_id = row[0] if row else None
            self._latest_run_loaded = True
        return self._latest_run_id

    # -- overstock ceiling ---------------------------------------------------

    def _overstock_ceiling(self) -> int:
        """Global days-of-cover ceiling above which a SKU reads as overstock."""
        if self._overstock_days is None:
            self._overstock_days = resolve_global_overstock_days(self.db)
        return self._overstock_days

    # -- shared helpers ------------------------------------------------------

    def _dead_days_for(self, product_id: str, category_code: Optional[str]) -> int:
        """Resolve dead_stock_days: sku scope → product_class(category_code) → global."""
        if self._policies is None:
            rows = self.db.execute(text(
                "SELECT scope_type, scope_ref, dead_stock_days FROM scm.reorder_policy "
                "WHERE is_active = true AND dead_stock_days IS NOT NULL"
            )).fetchall()
            self._policies = [
                {"scope_type": r[0], "scope_ref": r[1], "dead_stock_days": int(r[2])}
                for r in rows
            ]
        by_scope: Dict[Tuple[str, Optional[str]], int] = {
            (p["scope_type"], p["scope_ref"]): p["dead_stock_days"] for p in self._policies
        }
        if ("sku", product_id) in by_scope:
            return by_scope[("sku", product_id)]
        if category_code and ("product_class", category_code) in by_scope:
            return by_scope[("product_class", category_code)]
        # Global scope resolves through the SAME canonical row the config endpoint
        # uses (deterministic ORDER BY), so the dead window here and the Settings
        # popover can never disagree when duplicate global rows exist.
        if not self._global_loaded:
            self._global_dead_days = resolve_global_dead_stock_days(self.db)
            self._global_loaded = True
        if self._global_dead_days is not None:
            return self._global_dead_days
        return DEFAULT_DEAD_STOCK_DAYS  # engine default fallback

    @staticmethod
    def _lifecycle_where(filters: ScmFilters, alias: str = "p") -> List[str]:
        """SQL predicates narrowing to the requested product-lifecycle scope.

        Applied on EVERY query that reaches ``products`` so counts, valuations and
        grids all agree. Empty/None scope has already been normalised to the focused
        default (active + ongoing) by the route, so ``all`` here is an explicit widen.
        """
        clauses: List[str] = []
        if filters.active_status == "active":
            clauses.append(f"{alias}.is_active = true")
        elif filters.active_status == "inactive":
            clauses.append(f"{alias}.is_active = false")
        # "all" → no is_active predicate
        if filters.lifecycle == "ongoing":
            clauses.append(f"{alias}.is_discontinued = false")
        elif filters.lifecycle == "discontinued":
            clauses.append(f"{alias}.is_discontinued = true")
        # "all" → no is_discontinued predicate
        return clauses

    def _base_rows(self, filters: ScmFilters) -> List[dict]:
        """Per SKU×warehouse enriched rows respecting all filters EXCEPT health."""
        where = ["1=1"]
        where.extend(self._lifecycle_where(filters))
        params: dict = {}
        for column, prefix in (("w.company_id", "cbw"), ("p.company_id", "cbp")):
            clause, co_params = self._company_clause(column, prefix)
            where.append(clause)
            params.update(co_params)
        if filters.warehouses:
            where.append("w.warehouse_code = ANY(:whs)")
            params["whs"] = filters.warehouses
        if filters.category_id:
            where.append("p.category_id = :cat")
            params["cat"] = filters.category_id
        if filters.q:
            where.append("(p.product_code ILIKE :q OR p.product_name ILIKE :q)")
            params["q"] = f"%{filters.q}%"
        if filters.supplier:
            where.append(
                "EXISTS (SELECT 1 FROM product_suppliers ps JOIN suppliers su ON su.id = ps.supplier_id "
                "WHERE ps.product_id = p.id AND su.supplier_code = :sup)"
            )
            params["sup"] = filters.supplier

        # Reorder-point source (M8-B): the latest completed run's frozen ROP, matched
        # per product (+ warehouse when the rec is per-warehouse; a network/null-warehouse
        # rec falls back for that product). Exact-warehouse recs win over network recs, and
        # only non-null ROPs are considered. Null when no completed run / no rec → the row
        # simply never reads as low. Read-only join, no engine re-run. The SAME chosen rec
        # also yields the ROP inputs (M8-F10): ``safety_stock`` + ``lead_time_days`` ride in
        # the rec's frozen ``inputs`` JSONB, so the reorder-point explain can show the two
        # values that feed it without a second lookup.
        params["latest_run_id"] = self._latest_completed_run_id()
        sql = text(
            f"""
            SELECT p.id AS product_id, p.product_code, p.product_name, p.cost_price,
                   p.variant_of_id, pc.category_code, pc.category_name,
                   w.id AS warehouse_id, w.warehouse_code, w.warehouse_name,
                   np.quantity_on_hand, np.on_order, np.committed, np.net_position,
                   ds.avg_daily_demand, ds.demand_cv,
                   ic.abc_class, ic.xyz_class, ic.annual_value,
                   rop.reorder_point, rop.safety_stock, rop.lead_time_days
            FROM scm.net_position_v np
            JOIN products p ON p.id = np.product_id
            JOIN warehouses w ON w.id = np.warehouse_id
            LEFT JOIN product_categories pc ON pc.id = p.category_id
            LEFT JOIN scm.demand_stat ds
              ON ds.product_id = np.product_id AND ds.warehouse_id = np.warehouse_id
            LEFT JOIN scm.item_classification ic
              ON ic.product_id = np.product_id AND ic.warehouse_id = np.warehouse_id
            LEFT JOIN LATERAL (
                SELECT rr.reorder_point,
                       (rr.inputs->>'safety_stock')::numeric AS safety_stock,
                       (rr.inputs->>'lead_time_days')::numeric AS lead_time_days
                FROM scm.reorder_recommendation rr
                WHERE rr.run_id = :latest_run_id
                  AND rr.product_id = np.product_id
                  AND (rr.warehouse_id = np.warehouse_id OR rr.warehouse_id IS NULL)
                  AND rr.reorder_point IS NOT NULL
                ORDER BY (rr.warehouse_id = np.warehouse_id) DESC NULLS LAST
                LIMIT 1
            ) rop ON true
            WHERE {' AND '.join(where)}
            """
        )
        rows = self.db.execute(sql, params).mappings().all()
        if not rows:
            return []

        product_ids = list({r["product_id"] for r in rows})
        last_move = self._last_movement_map(product_ids, filters.warehouses)
        suppliers = self._supplier_map(product_ids)
        overstock_days = self._overstock_ceiling()

        out: List[dict] = []
        for r in rows:
            pid = r["product_id"]
            wid = r["warehouse_id"]
            on_hand = _f(r["quantity_on_hand"])
            on_order = _f(r["on_order"])
            committed = _f(r["committed"])
            net = _f(r["net_position"])
            lm = last_move.get((pid, wid))
            dead_days = self._dead_days_for(pid, r["category_code"])
            # M8-B low-stock: engine reorder point (latest completed run), frozen; a
            # stocked SKU at/under it reads as ``low`` (after stockout/dead precedence).
            rop_raw = r["reorder_point"]
            reorder_point = float(rop_raw) if rop_raw is not None else None
            # M8-F10: the ROP inputs from the SAME chosen rec (frozen inputs JSONB); null
            # when un-planned or the rec never carried them.
            ss_raw = r["safety_stock"]
            safety_stock = float(ss_raw) if ss_raw is not None else None
            lt_raw = r["lead_time_days"]
            lead_time_days = float(lt_raw) if lt_raw is not None else None
            below_rop = _is_below_rop(on_hand, net, reorder_point)
            status = _compute_status(
                on_hand, on_order, committed, lm, dead_days, self._today,
                net=net, reorder_point=reorder_point,
            )
            sup = suppliers.get(pid)
            cost = r["cost_price"]
            valuation = float(cost) * on_hand if cost is not None else None
            # M2 demand / classification (per SKU×warehouse). avg_daily_demand 0/None
            # → treated as "no demand" (null) so days-of-cover reads as ∞/— on the FE.
            add_raw = r["avg_daily_demand"]
            add = float(add_raw) if add_raw is not None and float(add_raw) > 0 else None
            doc = _days_of_cover(net, add)
            overstock = _is_overstock(on_hand, doc, add, overstock_days)
            av = r["annual_value"]
            out.append({
                "product_id": pid,
                "sku": r["product_code"],
                "product_name": r["product_name"],
                "category_code": r["category_code"],
                "category_name": r["category_name"],
                "variant_of_id": r["variant_of_id"],
                "supplier_name": sup["supplier_name"] if sup else None,
                "cost_price": float(cost) if cost is not None else None,
                "warehouse_id": wid,
                "warehouse_code": r["warehouse_code"],
                "warehouse_name": r["warehouse_name"],
                "on_hand": on_hand,
                "on_order": on_order,
                "committed": committed,
                "net_position": net,
                "last_movement": lm,
                "stock_valuation": valuation,
                "status": status,
                "avg_daily_demand": add,
                "days_of_cover": doc,
                "abc_class": r["abc_class"],
                "xyz_class": r["xyz_class"],
                "annual_value": float(av) if av is not None else None,
                "overstock": overstock,
                "reorder_point": reorder_point,
                "safety_stock": safety_stock,
                "lead_time_days": lead_time_days,
                "below_rop": below_rop,
            })
        return out

    def _last_movement_map(self, product_ids: List[str],
                           warehouses: List[str]) -> Dict[Tuple[str, str], date]:
        if not product_ids:
            return {}
        params: dict = {"pids": product_ids}
        wh_clause = ""
        if warehouses:
            wh_clause = "AND w.warehouse_code = ANY(:whs)"
            params["whs"] = warehouses
        co, co_params = self._company_clause("w.company_id", "clw")
        params.update(co_params)
        rows = self.db.execute(text(
            f"""
            SELECT cv.product_id, cv.warehouse_id, MAX(cv.day) AS last_day
            FROM scm.consumption_v cv
            JOIN warehouses w ON w.id = cv.warehouse_id
            WHERE cv.product_id = ANY(:pids) AND {co} {wh_clause}
            GROUP BY cv.product_id, cv.warehouse_id
            """
        ), params).fetchall()
        return {(r[0], r[1]): r[2] for r in rows}

    def _supplier_map(self, product_ids: List[str]) -> Dict[str, dict]:
        """One representative supplier per product (primary first, else lowest lead time)."""
        if not product_ids:
            return {}
        co, co_params = self._company_clause("su.company_id", "csm")
        rows = self.db.execute(text(
            f"""
            SELECT ps.product_id, su.supplier_code, su.supplier_name,
                   ps.standard_lead_time_days, ps.is_primary_supplier
            FROM product_suppliers ps
            JOIN suppliers su ON su.id = ps.supplier_id
            WHERE ps.product_id = ANY(:pids) AND {co}
            ORDER BY ps.is_primary_supplier DESC NULLS LAST,
                     ps.standard_lead_time_days ASC NULLS LAST
            """
        ), {"pids": product_ids, **co_params}).fetchall()
        out: Dict[str, dict] = {}
        for r in rows:
            if r[0] not in out:  # first per product wins (ordered primary-first)
                out[r[0]] = {
                    "supplier_code": r[1],
                    "supplier_name": r[2],
                    "lead_time": r[3],
                }
        return out

    def _placed_po_rows(self, filters: ScmFilters) -> List[dict]:
        """Open (placed) PO lines with remaining supply, respecting scope filters.

        The predicates mirror ``scm.on_order_v`` exactly, ``pol.line_status`` included: a line
        that left the order book is not incoming, and a dashboard that counted it while the net
        position did not would have the buyer looking at two answers on one screen.
        """
        where = ["po.status = ANY(:statuses)", "pol.line_status = 'open'",
                 "pol.qty_ordered > pol.qty_received"]
        where.extend(self._lifecycle_where(filters))
        params: dict = {"statuses": list(PLACED_PO_STATUSES)}
        if filters.warehouses:
            where.append("w.warehouse_code = ANY(:whs)")
            params["whs"] = filters.warehouses
        if filters.supplier:
            where.append("su.supplier_code = :sup")
            params["sup"] = filters.supplier
        if filters.category_id:
            where.append("p.category_id = :cat")
            params["cat"] = filters.category_id
        if filters.q:
            where.append("(p.product_code ILIKE :q OR p.product_name ILIKE :q)")
            params["q"] = f"%{filters.q}%"
        rows = self.db.execute(text(
            f"""
            SELECT po.id AS po_id, su.supplier_code, su.supplier_name,
                   pol.product_id, pol.warehouse_id, w.warehouse_code,
                   COALESCE(pol.expected_date, po.expected_date) AS eta
            FROM purchase_order_lines pol
            JOIN purchase_orders po ON po.id = pol.purchase_order_id
            LEFT JOIN suppliers su ON su.id = po.supplier_id
            JOIN products p ON p.id = pol.product_id
            LEFT JOIN warehouses w ON w.id = pol.warehouse_id
            WHERE {' AND '.join(where)}
            """
        ), params).mappings().all()
        return [dict(r) for r in rows]

    # -- endpoints -----------------------------------------------------------

    # Scalar columns the aggregated net-position grid may sort by. Anything else
    # (e.g. the list-valued ``warehouses`` breakdown) falls back to the attention
    # default rather than blowing up on an uncomparable key.
    _NET_POSITION_SORTABLE = {
        "sku", "status", "net_position", "on_hand", "on_order", "committed",
        "stock_valuation", "avg_daily_demand", "days_of_cover",
    }

    def net_position(self, filters: ScmFilters, page: int, limit: int,
                     sort: Optional[str], direction: str, query: Optional[str]) -> dict:
        if query and not filters.q:
            filters.q = query
        rows = self._base_rows(filters)

        # aggregate per product across the (scoped) warehouses
        by_product: Dict[str, List[dict]] = {}
        for r in rows:
            by_product.setdefault(r["product_id"], []).append(r)

        overstock_days = self._overstock_ceiling()
        products: List[dict] = []
        for pid, whs in by_product.items():
            first = whs[0]
            on_hand = sum(w["on_hand"] for w in whs)
            on_order = sum(w["on_order"] for w in whs)
            committed = sum(w["committed"] for w in whs)
            net = on_hand + on_order - committed
            cost = first["cost_price"]
            valuation = cost * on_hand if cost is not None else None
            last_moves = [w["last_movement"] for w in whs if w["last_movement"]]
            last_move = max(last_moves) if last_moves else None
            dead_days = self._dead_days_for(pid, first["category_code"])
            # Product-level reorder point = Σ per-warehouse engine ROP (None when no
            # warehouse carries one). ``low`` (below reorder point) reads off the
            # product net vs that aggregate so the net-position row's status chip agrees
            # with its own net + ROP figures (M8-B7).
            rop_parts = [w["reorder_point"] for w in whs if w["reorder_point"] is not None]
            product_rop = sum(rop_parts) if rop_parts else None
            product_below_rop = _is_below_rop(on_hand, net, product_rop)
            status = _compute_status(
                on_hand, on_order, committed, last_move, dead_days, self._today,
                net=net, reorder_point=product_rop,
            )
            stockout_committed = on_hand <= 0 and committed > 0
            # Product-level demand = Σ per-warehouse avg_daily_demand (None when no
            # warehouse has demand). Days-of-cover / overstock read off the product
            # net position; ABC/XYZ collapse to the dominant value/demand location.
            demand_parts = [w["avg_daily_demand"] for w in whs if w["avg_daily_demand"]]
            product_add = sum(demand_parts) if demand_parts else None
            product_doc = _days_of_cover(net, product_add)
            product_overstock = _is_overstock(on_hand, product_doc, product_add, overstock_days)
            abc_class = _dominant_class(whs, "abc_class", "annual_value")
            xyz_class = _dominant_class(whs, "xyz_class", "avg_daily_demand")
            has_zero = any(w["on_hand"] <= 0 for w in whs)
            has_surplus = any(w["on_hand"] > 0 for w in whs)
            imbalance = has_zero and has_surplus
            breakdown = [
                {
                    "warehouse_code": w["warehouse_code"],
                    "warehouse_name": w["warehouse_name"] or w["warehouse_code"],
                    "on_hand": w["on_hand"],
                    "on_order": w["on_order"],
                    "committed": w["committed"],
                    "net_position": w["net_position"],
                    "stock_valuation": w["stock_valuation"],
                    "status": w["status"],
                }
                for w in sorted(whs, key=lambda x: x["warehouse_code"] or "")
            ]
            products.append({
                "sku": first["sku"],
                "product_name": first["product_name"],
                "product_class": first["category_name"],
                "variant": None,
                "supplier_name": first["supplier_name"],
                "on_hand": on_hand,
                "on_order": on_order,
                "committed": committed,
                "net_position": net,
                "stock_valuation": valuation,
                "last_movement_at": last_move.isoformat() if last_move else None,
                "status": status,
                "imbalance": imbalance,
                "stockout_with_committed": stockout_committed,
                "attention_rank": _attention_rank(status, stockout_committed),
                "warehouses": breakdown,
                "avg_daily_demand": product_add,
                "days_of_cover": product_doc,
                "abc_class": abc_class,
                "xyz_class": xyz_class,
                "overstock": product_overstock,
                # Reorder-point column stays deferred on the net-position grid (renders
                # "—"); the aggregate ROP is used only to drive the `low` status +
                # ``below_rop`` health filter at product level (mirrors the per-wh flag).
                "reorder_point": None,
                "below_rop": product_below_rop,
            })

        if filters.health:
            products = [p for p in products if _matches_health(p, filters.health)]
        if filters.abc:
            products = [p for p in products if _matches_class(p["abc_class"], filters.abc)]
        if filters.xyz:
            products = [p for p in products if _matches_class(p["xyz_class"], filters.xyz)]

        # sort: an allow-listed scalar column overrides the attention default;
        # unknown / list-valued keys are ignored (fall back to the default sort).
        if sort in self._NET_POSITION_SORTABLE:
            reverse = direction == "desc"
            if sort == "status":
                products.sort(
                    key=lambda p: (_STATUS_RANK.get(p["status"], 4), p["sku"]),
                    reverse=reverse,
                )
            else:
                # Nulls sort LAST regardless of direction (a null metric — e.g. no
                # demand → no days-of-cover — is "no data", never the top hit).
                present = [p for p in products if p[sort] is not None]
                absent = [p for p in products if p[sort] is None]
                present.sort(key=lambda p: (p[sort], p["sku"]), reverse=reverse)
                products = present + absent
        else:
            products.sort(key=lambda p: (p["attention_rank"], p["net_position"]))

        total = len(products)
        start = (page - 1) * limit
        paged = products[start:start + limit]
        return {
            "data": paged,
            "empty": total == 0,
            "pagination": {"total": total, "page": page},
        }

    def warehouses(self, filters: ScmFilters) -> List[dict]:
        rows = _class_filter(self._base_rows(filters), filters)
        placed = self._placed_po_rows(filters)
        po_by_wh: Dict[str, set] = {}
        for pr in placed:
            po_by_wh.setdefault(pr["warehouse_code"], set()).add(pr["po_id"])

        by_wh: Dict[str, List[dict]] = {}
        for r in rows:
            by_wh.setdefault(r["warehouse_code"], []).append(r)

        out: List[dict] = []
        for code, whs in by_wh.items():
            name = whs[0]["warehouse_name"] or code
            comp = {"stockout": 0, "dead": 0, "low": 0, "healthy": 0, "incoming": 0}
            overstock_ct = 0
            for w in whs:
                comp[w["status"]] = comp.get(w["status"], 0) + 1
                if w["overstock"]:
                    overstock_ct += 1
            costed = [w["stock_valuation"] for w in whs if w["stock_valuation"] is not None]
            valuation = sum(costed) if costed else None
            worst = min(
                (w["status"] for w in whs),
                key=lambda s: _STATUS_RANK.get(s, 4),
                default="healthy",
            )
            out.append({
                "warehouse_code": code,
                "warehouse_name": name,
                "worst_state": worst,
                "stock_valuation": valuation,
                "stockout_count": comp["stockout"],
                "dead_count": comp["dead"],
                "incoming_po_count": len(po_by_wh.get(code, set())),
                "sku_count": len(whs),
                "composition": {
                    "stockout": comp["stockout"],
                    "dead": comp["dead"],
                    "healthy": comp["healthy"],
                    "incoming": comp["incoming"],
                    # M8-B7: stocked SKUs at/under the engine reorder point in this warehouse.
                    "low": comp["low"],
                    "overstock": overstock_ct,
                },
            })
        out.sort(key=lambda w: w["warehouse_code"])
        return out

    def _supplier_performance_map(self, supplier_codes: List[str]) -> Dict[str, dict]:
        """Supplier-level scorecard (``supplier_performance`` where product_id IS NULL)
        keyed by supplier_code. Composite is scaled 0–100 for display; the 0–1 rate
        fields (on_time / reject / fill) stay 0–1 (the FE formats them as %). Suppliers
        with no computed row are simply absent → the caller returns ``performance`` null
        rather than fabricating a score."""
        if not supplier_codes:
            return {}
        co, co_params = self._company_clause("su.company_id", "csp")
        rows = self.db.execute(text(
            f"""
            SELECT su.supplier_code, sp.on_time_rate, sp.avg_lead_time_days,
                   sp.reject_rate, sp.fill_rate, sp.composite_score, sp.sample_size,
                   sp.confidence
            FROM scm.supplier_performance sp
            JOIN suppliers su ON su.id = sp.supplier_id
            WHERE sp.product_id IS NULL AND su.supplier_code = ANY(:codes) AND {co}
            """
        ), {"codes": supplier_codes, **co_params}).fetchall()
        out: Dict[str, dict] = {}
        for r in rows:
            out[r[0]] = {
                "on_time_rate": float(r[1]) if r[1] is not None else None,
                "avg_lead_time_days": float(r[2]) if r[2] is not None else None,
                "reject_rate": float(r[3]) if r[3] is not None else None,
                "fill_rate": float(r[4]) if r[4] is not None else None,
                "composite_score": round(float(r[5]) * 100, 1) if r[5] is not None else None,
                "sample_size": int(r[6]) if r[6] is not None else 0,
                "confidence": r[7] or "low",
            }
        return out

    def suppliers(self, filters: ScmFilters) -> List[dict]:
        rows = _class_filter(self._base_rows(filters), filters)
        placed = self._placed_po_rows(filters)
        overstock_days = self._overstock_ceiling()

        # map product -> ALL of its suppliers (a product can appear under many)
        product_ids = list({r["product_id"] for r in rows})
        sup_links = self.db.execute(text(
            """
            SELECT ps.product_id, su.supplier_code, su.supplier_name, ps.standard_lead_time_days
            FROM product_suppliers ps JOIN suppliers su ON su.id = ps.supplier_id
            WHERE ps.product_id = ANY(:pids)
            """
        ), {"pids": product_ids or [""]}).fetchall() if product_ids else []

        # aggregate product across warehouses
        by_product: Dict[str, dict] = {}
        for r in rows:
            agg = by_product.setdefault(r["product_id"], {
                "sku": r["sku"], "product_name": r["product_name"],
                "on_hand": 0.0, "on_order": 0.0, "committed": 0.0, "net_position": 0.0,
                "category_code": r["category_code"], "whs": [],
            })
            agg["on_hand"] += r["on_hand"]
            agg["on_order"] += r["on_order"]
            agg["committed"] += r["committed"]
            agg["net_position"] += r["net_position"]
            agg["whs"].append(r)

        # placed PO stats per supplier
        po_by_sup: Dict[str, set] = {}
        eta_by_sup: Dict[str, List[date]] = {}
        eta_by_sup_product: Dict[Tuple[str, str], List[date]] = {}
        for pr in placed:
            sc = pr["supplier_code"]
            po_by_sup.setdefault(sc, set()).add(pr["po_id"])
            if pr["eta"]:
                eta_by_sup.setdefault(sc, []).append(pr["eta"])
                eta_by_sup_product.setdefault((sc, pr["product_id"]), []).append(pr["eta"])

        # group products under suppliers
        groups: Dict[str, dict] = {}
        lead_times: Dict[str, List[int]] = {}
        for link in sup_links:
            pid, sup_code, sup_name, lead = link[0], link[1], link[2], link[3]
            if pid not in by_product:
                continue
            g = groups.setdefault(sup_code, {
                "supplier_code": sup_code, "supplier_name": sup_name, "skus": [],
                "_seen": set(),
            })
            if pid in g["_seen"]:
                continue
            g["_seen"].add(pid)
            if lead is not None:
                lead_times.setdefault(sup_code, []).append(int(lead))
            agg = by_product[pid]
            on_hand = agg["on_hand"]
            on_order = agg["on_order"]
            committed = agg["committed"]
            last_moves = [w["last_movement"] for w in agg["whs"] if w["last_movement"]]
            last_move = max(last_moves) if last_moves else None
            dead_days = self._dead_days_for(pid, agg["category_code"])
            # M8-B7: product-level low-stock so the supplier "products supplied" chip
            # agrees with the dashboard (Σ per-warehouse engine ROP; None when none).
            rop_parts = [w["reorder_point"] for w in agg["whs"] if w["reorder_point"] is not None]
            product_rop = sum(rop_parts) if rop_parts else None
            status = _compute_status(
                on_hand, on_order, committed, last_move, dead_days, self._today,
                net=agg["net_position"], reorder_point=product_rop,
            )
            demand_parts = [w["avg_daily_demand"] for w in agg["whs"] if w["avg_daily_demand"]]
            product_add = sum(demand_parts) if demand_parts else None
            product_doc = _days_of_cover(agg["net_position"], product_add)
            etas = eta_by_sup_product.get((sup_code, pid), [])
            g["skus"].append({
                "sku": agg["sku"],
                "product_name": agg["product_name"],
                "on_hand": on_hand,
                "on_order": on_order,
                "net_position": agg["net_position"],
                "status": status,
                "overstock": _is_overstock(on_hand, product_doc, product_add, overstock_days),
                # Mirrors the per-warehouse flag so the `low` health filter resolves here.
                "below_rop": _is_below_rop(on_hand, agg["net_position"], product_rop),
                "incoming_po_eta": min(etas).isoformat() if etas else None,
            })

        perf_map = self._supplier_performance_map(list(groups.keys()))

        out: List[dict] = []
        for sup_code, g in groups.items():
            if filters.supplier and sup_code != filters.supplier:
                continue
            if filters.health:
                g["skus"] = [s for s in g["skus"] if _matches_health(s, filters.health)]
                if not g["skus"]:
                    continue
            leads = lead_times.get(sup_code)
            etas = eta_by_sup.get(sup_code, [])
            out.append({
                "supplier_code": g["supplier_code"],
                "supplier_name": g["supplier_name"],
                "declared_lead_time_days": max(leads) if leads else None,
                "incoming_po_count": len(po_by_sup.get(sup_code, set())),
                "incoming_po_next_eta": min(etas).isoformat() if etas else None,
                "skus": sorted(g["skus"], key=lambda s: s["sku"]),
                # Real supplier-level scorecard, or null when never scored.
                "performance": perf_map.get(sup_code),
            })
        out.sort(key=lambda s: s["supplier_name"] or s["supplier_code"])
        return out

    def rollups(self, filters: ScmFilters) -> dict:
        rows = _class_filter(self._base_rows(filters), filters)
        placed = self._placed_po_rows(filters)

        total_val = 0.0
        dead_val = 0.0
        overstock_val = 0.0
        stockout_count = 0
        overstock_count = 0
        below_rop_count = 0
        missing_cost_products: set = set()
        for r in rows:
            if r["stock_valuation"] is not None:
                total_val += r["stock_valuation"]
                if r["status"] == "dead":
                    dead_val += r["stock_valuation"]
                if r["overstock"]:
                    overstock_val += r["stock_valuation"]
            elif r["on_hand"] > 0:
                missing_cost_products.add(r["product_id"])
            if r["status"] == "stockout":
                stockout_count += 1
            # Overstock is demand-derived (days-of-cover over the ceiling) and
            # counted per SKU×warehouse, independent of the health status.
            if r["overstock"]:
                overstock_count += 1
            # Below-reorder-point (M8-B): stocked SKU at/under the engine ROP. The
            # ``on_hand>0`` guard inside ``below_rop`` means a stockout is never also
            # counted here (M8-B2 precedence) — the two tiles partition the SKUs.
            if r["below_rop"]:
                below_rop_count += 1

        po_ids = {pr["po_id"] for pr in placed}
        etas = [pr["eta"] for pr in placed if pr["eta"]]
        return {
            "total_stock_valuation": round(total_val, 2),
            "dead_stock_valuation": round(dead_val, 2),
            "stockout_count": stockout_count,
            "incoming_po_count": len(po_ids),
            "incoming_po_next_eta": min(etas).isoformat() if etas else None,
            "valuation_missing_cost_count": len(missing_cost_products),
            # Below-reorder-point (M8-B): stocked SKUs at/under the latest completed
            # run's engine reorder point. Zero when no run has completed / no matching recs.
            "below_rop_count": below_rop_count,
            "overstock_valuation": round(overstock_val, 2),
            "overstock_count": overstock_count,
        }

    # Metric columns the drill-down popup can sort by (plus code / status).
    # ``abc_class``/``xyz_class`` (the "Value"/"Demand" headers) sort by class letter
    # A<B<C / X<Y<Z — the raw letter compares in that order — with nulls (unknown)
    # last in either direction via the shared present/absent split below.
    _PRODUCT_SORTABLE = {
        "sku", "status", "net_position", "on_hand", "on_order", "committed",
        "stock_valuation", "avg_daily_demand", "days_of_cover",
        "abc_class", "xyz_class",
    }

    def products(self, filters: ScmFilters, status: Optional[str],
                 warehouse: Optional[str], page: int = 1, limit: int = 50,
                 sort: Optional[str] = None, direction: str = "asc",
                 query: Optional[str] = None) -> dict:
        if query and not filters.q:
            filters.q = query
        if warehouse and warehouse not in filters.warehouses:
            filters.warehouses = [warehouse]
        rows = self._base_rows(filters)
        status = status or filters.health
        out: List[dict] = []
        for r in rows:
            if status and not _matches_health(r, status):
                continue
            if not _matches_class(r["abc_class"], filters.abc):
                continue
            if not _matches_class(r["xyz_class"], filters.xyz):
                continue
            out.append({
                "sku": r["sku"],
                "product_name": r["product_name"],
                # UUIDs carried for the avg-daily-demand explain fetch only (M8-B9) —
                # never displayed; the drill resolves them to DO numbers server-side.
                "product_id": str(r["product_id"]) if r["product_id"] is not None else None,
                "warehouse_id": str(r["warehouse_id"]) if r["warehouse_id"] is not None else None,
                "warehouse_code": r["warehouse_code"],
                "warehouse_name": r["warehouse_name"] or r["warehouse_code"],
                "on_hand": r["on_hand"],
                "on_order": r["on_order"],
                "committed": r["committed"],
                "net_position": r["net_position"],
                "stock_valuation": r["stock_valuation"],
                "status": r["status"],
                "stockout_with_committed": r["on_hand"] <= 0 and r["committed"] > 0,
                # M2 demand / classification (per SKU×warehouse).
                "avg_daily_demand": r["avg_daily_demand"],
                "days_of_cover": r["days_of_cover"],
                "abc_class": r["abc_class"],
                "xyz_class": r["xyz_class"],
                # M8-B — engine reorder point (latest completed run); null when un-planned.
                "reorder_point": r["reorder_point"],
                # M8-F10 — the ROP inputs from the same rec; shown with a plain definition
                # in the Low-stock reorder-point (i). Null when un-planned.
                "safety_stock": r["safety_stock"],
                "lead_time_days": r["lead_time_days"],
            })

        # sort: explicit metric/code/status column overrides the code default.
        if sort in self._PRODUCT_SORTABLE:
            reverse = direction == "desc"
            if sort == "status":
                out.sort(
                    key=lambda x: (_STATUS_RANK.get(x["status"], 4), x["sku"]),
                    reverse=reverse,
                )
            else:
                # Nulls sort LAST regardless of direction.
                present = [x for x in out if x[sort] is not None]
                absent = [x for x in out if x[sort] is None]
                present.sort(key=lambda x: (x[sort], x["warehouse_code"] or ""), reverse=reverse)
                out = present + absent
        else:
            out.sort(key=lambda x: (x["sku"], x["warehouse_code"] or ""))

        total = len(out)
        start = (page - 1) * limit
        paged = out[start:start + limit]
        return {"data": paged, "total": total, "page": page}

    # -- demand trend series (expandable product row viz) ---------------------

    # 12 MONTHLY buckets — the "last 12 months" trend horizon the user asked for,
    # distinct from the 90-day weekly analytics rate window. Reads the same DO
    # consumption source (scm.consumption_v).
    _SERIES_MONTHS = 12

    def demand_series(self, sku: str, warehouse: Optional[str] = None) -> dict:
        """~12 monthly buckets of DO outflow for one SKU (optionally one warehouse).

        Feeds the expandable product row's "Demand — last 12 months" sparkline.
        Returns the oldest→newest monthly buckets (zero-filled) plus the SKU's
        xyz_class + plain-language demand label so the caption can echo it.
        """
        # 11,390 product codes exist in more than one company, so an unscoped lookup by
        # code resolves to whichever copy Postgres returns first - and then every figure
        # below is about another company's stock.
        pco, pco_params = self._company_clause("company_id", "cds")
        prow = self.db.execute(text(
            f"SELECT id, product_code, product_name FROM products "
            f"WHERE product_code = :c AND {pco}"
        ), {"c": sku, **pco_params}).fetchone()
        if not prow:
            raise AppException(status_code=404, message=f"Unknown SKU '{sku}'.")
        pid = prow[0]

        wid = None
        if warehouse:
            wco, wco_params = self._company_clause("company_id", "cdw")
            wrow = self.db.execute(text(
                f"SELECT id FROM warehouses WHERE warehouse_code = :c AND {wco}"
            ), {"c": warehouse, **wco_params}).fetchone()
            if not wrow:
                raise AppException(status_code=404, message=f"Unknown warehouse '{warehouse}'.")
            wid = wrow[0]

        # Build the 12 trailing calendar-month keys, oldest→newest, ending with the
        # current month. ``start`` = first day of the oldest bucket; ``end`` = first
        # day of next month (exclusive upper bound).
        today = self._today
        y, m = today.year, today.month
        months: List[str] = []
        first_start: Optional[date] = None
        for i in range(self._SERIES_MONTHS - 1, -1, -1):
            idx = (y * 12 + (m - 1)) - i
            my, mm = idx // 12, idx % 12 + 1
            months.append(f"{my:04d}-{mm:02d}")
            if first_start is None:
                first_start = date(my, mm, 1)
        end_idx = y * 12 + (m - 1) + 1
        end = date(end_idx // 12, end_idx % 12 + 1, 1)

        where = ["product_id = :pid", "day >= :start", "day < :end"]
        params: dict = {"pid": pid, "start": first_start, "end": end}
        if wid is not None:
            where.append("warehouse_id = :wid")
            params["wid"] = wid
        agg = self.db.execute(text(
            f"""
            SELECT to_char(date_trunc('month', day), 'YYYY-MM') AS ym,
                   COALESCE(SUM(qty_out), 0) AS qty
            FROM scm.consumption_v
            WHERE {' AND '.join(where)}
            GROUP BY 1
            """
        ), params).fetchall()
        by_month = {r[0]: float(r[1]) for r in agg}
        points = [{"month": ym, "qty": by_month.get(ym, 0.0)} for ym in months]

        # xyz_class: the specific warehouse row when scoped, else the dominant
        # (largest-demand) classification across the product's warehouses.
        xyz_rows = self.db.execute(text(
            """
            SELECT ic.xyz_class, ds.avg_daily_demand
            FROM scm.item_classification ic
            LEFT JOIN scm.demand_stat ds
              ON ds.product_id = ic.product_id AND ds.warehouse_id = ic.warehouse_id
            WHERE ic.product_id = :pid
              AND (:wid IS NULL OR ic.warehouse_id = :wid)
            """
        ), {"pid": pid, "wid": wid}).fetchall()
        xyz = _dominant_class(
            [{"xyz_class": r[0], "avg_daily_demand": float(r[1]) if r[1] is not None else None}
             for r in xyz_rows],
            "xyz_class", "avg_daily_demand",
        )

        return {
            "sku": prow[1],
            "product_name": prow[2],
            "warehouse_code": warehouse,
            "xyz_class": xyz,
            "points": points,
            "total_qty": round(sum(p["qty"] for p in points), 2),
            "peak_qty": max((p["qty"] for p in points), default=0.0),
        }
