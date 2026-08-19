"""SCM M1 sales-order service — CRUD + create-DO-from-SO.

The SO is the committed-demand record (feeds ``scm.committed_v`` → net position).
``create_do_from_so`` materialises a Delivery Order (``orders`` / ``order_lines``)
from the SO and stamps ``sales_order_lines.qty_delivered`` (soft link, no hard FK)
so committed demand drops for those SKUs. so_number/do_number never leak UUIDs.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.access import MarketSegment
from app.models.inventory import Stock, Warehouse
from app.models.lookup import LookupOption
from app.models.order import Customer, Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Product, UnitOfMeasure
from app.models.scm import OrderLinkClaim
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService
from app.services.scm.demand import is_open_demand
from app.services.scm.demand_class import class_of

# Upper bound on suffix retries when reserving a unique DO number under contention.
_DO_NUMBER_MAX_TRIES = 50


#: Where a sales order came from, as one word a buyer can filter on. `inquiry` is separate
#: from `upload` because an order the Order Inquiry sheet created is one CS has never seen.
#: Filter value -> the `source_system` values it selects. `manual` is everything NOT here,
#: so a source added to `_source_label` and forgotten here would silently fall into Manual -
#: which is the one label that must never be wrong, since it claims a person keyed the order.
_SOURCE_SYSTEMS = {
    "inquiry": ("scm_order_inquiry",),
    "upload": ("scm_upload",),
    "history": ("scm_so_history",),
}


def _source_label(source_system: Optional[str]) -> str:
    if source_system == "scm_order_inquiry":
        return "inquiry"
    if source_system == "scm_upload":
        return "upload"
    # Absorbed sales history gets its own answer rather than "Manual", which would claim
    # somebody keyed a 2020 order by hand. Mirrors the purchase-order side's `import`.
    if source_system == "scm_so_history":
        return "history"
    return "manual"


def _line_sort_key(ln: SalesOrderLine):
    """OPEN lines first, then delivery date ascending (nulls last), then product code.

    Applied here rather than on the FE, so the list and the detail screen - both built from
    `serialize()` - and any other consumer of the payload (n8n via MCP, a future export) see
    the same order without agreeing on it separately. The FE's own column-header sort still
    works on top of this: it is the table's default order, not a lock on the rows.
    """
    return (
        0 if ln.line_status == "open" else 1,
        ln.required_date is None,
        ln.required_date or date.min,
        ln.product.product_code if ln.product else "",
    )


def _order_by(sort_cols: dict, sort: Optional[str], direction: str) -> list:
    """The sort, always made total by `id`.

    11,006 of the orders in this book share ONE `created_at`: they were absorbed in a single
    import. Ordering on that column alone leaves their relative order up to the planner, so
    "the 26th record" is a different row from one query to the next - which is how a detail
    pager steps to a correct neighbour and then reports a position taken from a different
    shuffle of the same rows, and how a row can appear on two pages or neither.

    `id` is arbitrary but it is STABLE, which is the whole requirement.
    """
    col = sort_cols.get(sort or "", SalesOrder.created_at)
    if direction == "asc":
        return [col.asc(), SalesOrder.id.asc()]
    return [col.desc(), SalesOrder.id.desc()]


class SalesOrderService:
    def __init__(self, db: Session):
        self.db = db

    # -- resolvers -----------------------------------------------------------

    def _customer(self, code: str) -> Customer:
        # customer_code is NOT unique in this dataset (multiple legal entities share
        # a debtor code). Prefer a row that carries a market_segment (drives
        # demand_nature), then order by name for determinism.
        cust = (
            self.db.query(Customer)
            .filter(func.lower(func.btrim(Customer.customer_code)) == code.strip().lower())
            .order_by(Customer.market_segment_code.asc().nullslast(), Customer.customer_name)
            .first()
        )
        if not cust:
            raise AppException(404, f"Customer not found: {code}", code="CUSTOMER_NOT_FOUND")
        return cust

    def _product(self, sku: str) -> Product:
        prod = (
            self.db.query(Product)
            .filter(func.lower(Product.product_code) == sku.strip().lower())
            .first()
        )
        if not prod:
            raise AppException(404, f"Product not found: {sku}", code="PRODUCT_NOT_FOUND")
        return prod

    def _order_type_label(self, order_type: Optional[str]) -> str:
        if not order_type:
            return ""
        opt = (
            self.db.query(LookupOption)
            .filter(func.lower(LookupOption.value) == order_type.strip().lower())
            .first()
        )
        if opt:
            return opt.label
        return order_type.replace("_", " ").title()

    def _uom_for(self, product: Product) -> str:
        if product.base_uom_id:
            uom = self.db.query(UnitOfMeasure).get(product.base_uom_id)
            if uom:
                return uom.uom_code
        return ""

    def _market_segment_name(self, customer: Optional[Customer]) -> Optional[str]:
        if not customer or not customer.market_segment_code:
            return None
        # Look up by the business key, not `.get()`: the PK is now the uuid `id`,
        # so `.get(code)` would query id == '<code>' and never match.
        seg = (
            self.db.query(MarketSegment)
            .filter(MarketSegment.code == customer.market_segment_code)
            .first()
        )
        return seg.name if seg else customer.market_segment_code

    # -- serialization -------------------------------------------------------

    def serialize(self, so: SalesOrder) -> dict:
        customer = so.customer
        total_qty = 0.0
        committed = 0.0
        lines = []
        open_lines = 0
        for ln in sorted(so.lines, key=_line_sort_key):
            qo = float(ln.qty_ordered or 0)
            qd = float(ln.qty_delivered or 0)
            outstanding = max(qo - qd, 0.0)
            total_qty += qo
            committed += outstanding
            if ln.line_status == "open" and outstanding > 0:
                open_lines += 1
            lines.append({
                "id": ln.id,
                "sku": ln.product.product_code if ln.product else "",
                "product_name": ln.product.product_name if ln.product else "",
                "qty_ordered": qo,
                "qty_delivered": qd,
                "uom": self._uom_for(ln.product) if ln.product else "",
                # The three the detail page needs and the list does not. Per line, not per
                # header: one order routinely ships from two locations on two dates, and
                # folding either onto the header states something the order never said.
                "warehouse_code": (
                    ln.warehouse.warehouse_code if ln.warehouse is not None else ""
                ),
                "line_status": ln.line_status or "open",
                "required_date": (
                    ln.required_date.isoformat() if ln.required_date else None
                ),
            })
        order_dt = so.order_date or (so.created_at.date() if so.created_at else date.today())
        return {
            "id": so.id,
            "so_number": so.so_number,
            "order_type": so.order_type or "",
            "order_type_label": self._order_type_label(so.order_type),
            "customer_code": customer.customer_code if customer else "",
            "customer_name": customer.customer_name if customer else "",
            "market_segment": self._market_segment_name(customer),
            "priority": so.priority or "normal",
            "status": so.status,
            "order_date": order_dt.isoformat(),
            "requested_delivery_date": (
                so.requested_delivery_date.isoformat() if so.requested_delivery_date else None
            ),
            "total_qty": total_qty,
            "committed_qty": committed,
            # What the order SAYS versus what is still owed. Both, because a "Total qty"
            # reading 0 on a fully delivered order is the label lying - the same rule the
            # purchase-order detail already follows with `open_qty` / `total_qty`.
            "line_count": len(lines),
            "open_line_count": open_lines,
            "lines": lines,
            # Where the order came from. `inquiry` is its own answer because an order Joey's
            # sheet created is one CS has never seen, and a buyer looking at the list is
            # entitled to know which of the two he is reading.
            "source": _source_label(so.source_system),
            # The project the sheet named when no customer of that name existed. Kept so the
            # order is not anonymous just because it could not be linked.
            "internal_note": so.internal_note or None,
            # Every distinct stock location its lines ship from. Plural because one order can
            # land in two, and collapsing that to the first would be a quiet lie.
            "stock_locations": sorted({
                ln.warehouse.warehouse_code
                for ln in so.lines
                if ln.warehouse is not None and ln.warehouse.warehouse_code
            }),
            "created_at": so.created_at.isoformat() if so.created_at else "",
        }

    def with_links(self, rows: list[dict]) -> list[dict]:
        """Attach each order's purchase-order claims, in ONE query for the whole page.

        Per-row would be an N+1 across a 15,000-order list. The claim carries whether it has
        been resolved, which is the difference between "waiting on PO 202605-S0042" and
        "matched to it" - and the waiting ones are the reason this column exists at all.
        """
        numbers = [r["so_number"] for r in rows]
        if not numbers:
            return rows
        claims = (
            self.db.query(OrderLinkClaim)
            .filter(OrderLinkClaim.so_number.in_(numbers))
            .all()
        )
        by_number: dict[str, list[dict]] = {}
        for c in claims:
            by_number.setdefault(str(c.so_number), []).append({
                "po_number": c.po_number,
                "item_code": c.item_code,
                "resolved": c.resolved_at is not None,
            })
        for row in rows:
            linked = sorted(
                by_number.get(row["so_number"], []),
                key=lambda l: (l["po_number"], l["item_code"] or ""),
            )
            row["linked_purchase_orders"] = linked
            row["awaiting_purchase_orders"] = sum(1 for l in linked if not l["resolved"])
        return rows

    def _get_or_404(self, so_id: str) -> SalesOrder:
        so = (
            self.db.query(SalesOrder)
            .options(joinedload(SalesOrder.lines).joinedload(SalesOrderLine.product),
                     joinedload(SalesOrder.customer))
            .filter(SalesOrder.id == so_id)
            .first()
        )
        if not so:
            raise AppException(404, "Sales order not found", code="SO_NOT_FOUND")
        return so

    # -- reads ---------------------------------------------------------------

    def get(self, so_id: str) -> dict:
        return self.serialize(self._get_or_404(so_id))

    def list(self, page: int, limit: int, sort: Optional[str], direction: str,
             query: Optional[str], status: Optional[str], priority: Optional[str],
             source: Optional[str] = None, *,
             date_from: Optional[date] = None, date_to: Optional[date] = None,
             customer_code: Optional[str] = None, outstanding: bool = False) -> dict:
        q = self.db.query(SalesOrder).options(
            joinedload(SalesOrder.lines).joinedload(SalesOrderLine.product),
            joinedload(SalesOrder.lines).joinedload(SalesOrderLine.warehouse),
            joinedload(SalesOrder.customer),
        )
        # "Show me the orders the Order Inquiry sheet created" is a filter on this list, not a
        # second screen: a separate list of the same entity is how two screens start
        # disagreeing about the same order.
        if source:
            if source == "manual":
                # Everything neither feed wrote: keyed in, or from a system we have no name
                # for. NULL has to be spelled out because `NOT IN` never matches it.
                known = [v for vs in _SOURCE_SYSTEMS.values() for v in vs]
                q = q.filter(
                    (SalesOrder.source_system.is_(None))
                    | (~SalesOrder.source_system.in_(known))
                )
            else:
                # An unrecognised value matches NOTHING rather than being ignored. A filter
                # that quietly drops the value it did not understand shows the whole book
                # under a heading claiming it is narrowed - the worst of the three options.
                q = q.filter(SalesOrder.source_system.in_(_SOURCE_SYSTEMS.get(source, ())))
        if status:
            q = q.filter(SalesOrder.status == status)
        if priority:
            q = q.filter(SalesOrder.priority == priority)
        # Inclusive of both ends, because a person asking for "March" means the 1st and the
        # 31st. An undated order is excluded from a range rather than swept into one: absorbed
        # rows can arrive with no date, and putting one in January states a fact we do not have.
        if date_from:
            q = q.filter(SalesOrder.order_date >= date_from)
        if date_to:
            q = q.filter(SalesOrder.order_date <= date_to)
        if customer_code:
            # By CODE, not id. `customer_code` is not unique in this dataset - several legal
            # entities share a debtor code - so a person picking "Acme" from the dropdown
            # means every one of them, and filtering by a single id would show part of their
            # book. Trimmed and case-folded to match `_customer`.
            q = q.filter(
                SalesOrder.customer.has(
                    func.lower(func.btrim(Customer.customer_code))
                    == customer_code.strip().lower()
                )
            )
        if outstanding:
            # The SAME rule the netting reads, so "still owed" cannot mean one thing on this
            # screen and another in the plan. Only when asked for: an unticked box must not
            # narrow anything, or clearing a filter looks like data appearing on its own.
            q = q.filter(
                self.db.query(SalesOrderLine.id)
                .filter(
                    SalesOrderLine.sales_order_id == SalesOrder.id,
                    is_open_demand(),
                )
                .exists()
            )
        if query:
            like = f"%{query}%"
            q = q.filter(
                (SalesOrder.so_number.ilike(like))
                | (SalesOrder.customer.has(Customer.customer_name.ilike(like)))
            )
        sort_cols = {
            "so_number": SalesOrder.so_number,
            "order_date": SalesOrder.order_date,
            "status": SalesOrder.status,
            "priority": SalesOrder.priority,
            "created_at": SalesOrder.created_at,
        }
        q = q.order_by(*_order_by(sort_cols, sort, direction))
        total = q.count()
        rows = q.offset((page - 1) * limit).limit(limit).all()
        return {
            "data": [self.serialize(so) for so in rows],
            "empty": total == 0,
            "pagination": {"total": total, "page": page},
        }

    # -- writes --------------------------------------------------------------

    def create(self, data, user_id: Optional[str]) -> dict:
        customer = self._customer(data.customer_code)
        so_number = NumberingService(self.db).get_next_number("sales_order", commit_rule=False)
        if not so_number:
            raise AppException(500, "Sales-order numbering rule missing", code="NUMBERING_MISSING")
        so = SalesOrder(
            so_number=so_number,
            customer_id=customer.id,
            order_date=date.today(),
            requested_delivery_date=(
                date.fromisoformat(data.requested_delivery_date)
                if data.requested_delivery_date else None
            ),
            order_type=data.order_type,
            priority=data.priority,
            status="open",
            source_system="manual",
        )
        self.db.add(so)
        self.db.flush()
        for ln in data.lines:
            prod = self._product(ln.sku)
            self.db.add(SalesOrderLine(
                sales_order_id=so.id,
                product_id=prod.id,
                qty_ordered=ln.qty_ordered,
                qty_delivered=0,
                priority=data.priority,
                line_status="open",
                source_system="manual",
            ))
        self.db.commit()
        return self.serialize(self._get_or_404(so.id))

    def update(self, so_id: str, data, user_id: Optional[str]) -> dict:
        so = self._get_or_404(so_id)
        if data.customer_code is not None:
            so.customer_id = self._customer(data.customer_code).id
        if data.order_type is not None:
            so.order_type = data.order_type
            # A hand-set type follows the same vocabulary the importer classifies demand
            # with, so a manual edit cannot leave the order's `order_type` and
            # `demand_class` disagreeing. `class_of` returns None when the stated type is
            # blank/unrecognised - "nobody said" - which must NOT overwrite a class the
            # importer already resolved, so demand_class is only touched when it answers.
            demand = class_of(data.order_type)
            if demand:
                so.demand_class = demand
        if data.priority is not None:
            so.priority = data.priority
        if data.requested_delivery_date is not None:
            so.requested_delivery_date = (
                date.fromisoformat(data.requested_delivery_date)
                if data.requested_delivery_date else None
            )
        if data.lines is not None:
            for ln in list(so.lines):
                self.db.delete(ln)
            self.db.flush()
            for ln in data.lines:
                prod = self._product(ln.sku)
                self.db.add(SalesOrderLine(
                    sales_order_id=so.id,
                    product_id=prod.id,
                    qty_ordered=ln.qty_ordered,
                    qty_delivered=0,
                    priority=so.priority,
                    line_status="open",
                    source_system="manual",
                ))
        self.db.commit()
        return self.serialize(self._get_or_404(so_id))

    def delete(self, so_id: str) -> None:
        so = self._get_or_404(so_id)
        self.db.delete(so)
        self.db.commit()

    # -- create DO from SO ---------------------------------------------------

    def _warehouse_for_line(self, line: SalesOrderLine) -> Warehouse:
        if line.warehouse_id:
            wh = self.db.query(Warehouse).get(line.warehouse_id)
            if wh:
                return wh
        # else the warehouse holding the most stock of this product
        row = (
            self.db.query(Stock.warehouse_id)
            .filter(Stock.product_id == line.product_id)
            .order_by(Stock.quantity_on_hand.desc())
            .first()
        )
        if row:
            wh = self.db.query(Warehouse).get(row[0])
            if wh:
                return wh
        wh = self.db.query(Warehouse).order_by(Warehouse.warehouse_code).first()
        if not wh:
            raise AppException(422, "No warehouse available to create delivery order",
                               code="NO_WAREHOUSE")
        return wh

    def _do_number_base(self, so_number: str) -> str:
        return f"DO-{so_number.split('-', 1)[-1]}" if "-" in so_number else f"DO-{so_number}"

    def _insert_do_order(self, so: SalesOrder, user_id: Optional[str]) -> Order:
        """Insert the DO ``orders`` row, retrying on ``order_number`` collision.

        There is no dedicated delivery-order numbering rule — real DOs arrive
        pre-numbered from the source ERP, so the SCM DO number stays *derived*
        from the SO. Two concurrent create-DO calls therefore derive the same
        candidate and race the unique ``orders.order_number`` constraint. Reserve
        the number inside a SAVEPOINT and bump the suffix until the INSERT sticks,
        so the loser retries instead of raising a 500.
        """
        base = self._do_number_base(so.so_number)
        candidate = base
        n = 1
        for _ in range(_DO_NUMBER_MAX_TRIES):
            # Best-effort pre-check keeps the number tidy; the SAVEPOINT below is
            # what actually guards against a concurrent insert.
            if self.db.query(Order.id).filter(Order.order_number == candidate).first():
                n += 1
                candidate = f"{base}-{n}"
                continue
            # Manual SAVEPOINT (not the `with` context-manager form): a failed
            # INSERT only rolls back this savepoint, leaving the outer transaction
            # (and the pending SO-line/status mutations) intact for the retry.
            savepoint = self.db.begin_nested()
            try:
                order = Order(
                    order_number=candidate,
                    order_date=date.today(),
                    customer_id=so.customer_id,
                    order_type=so.order_type,
                    customer_ref=so.so_number,
                    remarks=f"Auto-created from sales order {so.so_number}",
                    created_by=user_id,
                    is_cancelled=False,
                )
                self.db.add(order)
                self.db.flush()
                savepoint.commit()
                return order
            except IntegrityError:
                # A concurrent txn grabbed this number first — try the next suffix.
                savepoint.rollback()
                n += 1
                candidate = f"{base}-{n}"
        raise AppException(500, "Could not allocate a unique delivery-order number",
                           code="DO_NUMBER_EXHAUSTED")

    def create_do_from_so(self, so_id: str, user_id: Optional[str]) -> dict:
        so = self._get_or_404(so_id)
        remaining = [
            ln for ln in so.lines
            if float(ln.qty_ordered or 0) - float(ln.qty_delivered or 0) > 0
        ]
        if not remaining:
            raise AppException(422, "Sales order has nothing left to deliver",
                               code="NOTHING_TO_DELIVER")

        order = self._insert_do_order(so, user_id)
        do_number = order.order_number

        seq = 1
        for ln in remaining:
            wh = self._warehouse_for_line(ln)
            qty = float(ln.qty_ordered or 0) - float(ln.qty_delivered or 0)
            self.db.add(OrderLine(
                order_id=order.id,
                line_sequence=seq,
                product_id=ln.product_id,
                warehouse_id=wh.id,
                quantity=qty,
            ))
            seq += 1
            ln.qty_delivered = ln.qty_ordered  # full delivery (soft link)
            ln.line_status = "fulfilled"

        fully = all(
            float(ln.qty_ordered or 0) - float(ln.qty_delivered or 0) <= 0 for ln in so.lines
        )
        so.status = "fulfilled" if fully else "partially_delivered"
        self.db.commit()
        return {"sales_order": self.serialize(self._get_or_404(so_id)), "do_number": do_number}
