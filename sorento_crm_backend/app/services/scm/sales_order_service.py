"""SCM M1 sales-order service — CRUD + create-DO-from-SO.

The SO is the committed-demand record (feeds ``scm.committed_v`` → net position).
``create_do_from_so`` materialises a Delivery Order (``orders`` / ``order_lines``)
from the SO and stamps ``sales_order_lines.qty_delivered`` (soft link, no hard FK)
so committed demand drops for those SKUs. so_number/do_number never leak UUIDs.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.access import MarketSegment
from app.models.inventory import Stock, Warehouse
from app.models.lookup import LookupOption
from app.models.order import Customer, Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.planning_change import PLANNING_CHANGE_SOURCE_SO_MANUAL_EDIT
from app.models.product import Product, UnitOfMeasure
from app.models.project_so import ProjectSalesOrder, ProjectSalesOrderLine
from app.models.sales_agent import SalesAgent
from app.models.scm import OrderLinkClaim
from app.services.error_handler import AppException
from app.services.numbering_service import NumberingService
from app.services.scm.demand import is_open_demand
from app.services.scm.demand_class import DEMAND_CLASSES, class_of
from app.services.scm.outstanding_diff import (
    DATE_AND_QTY_CHANGED,
    DATE_MOVED,
    QTY_CHANGED,
    Change,
    Diff,
    Line,
)

logger = logging.getLogger(__name__)

# Upper bound on suffix retries when reserving a unique DO number under contention.
_DO_NUMBER_MAX_TRIES = 50

# A quantity difference below this is noise, not an edit - same threshold and same reason
# `outstanding_diff._QTY_EPSILON` exists: two figures a decimal place apart on export must
# not read as a planner's decision. Duplicated here rather than imported (that name is
# private to that module) - `outstanding_import_service` does the same.
_QTY_EPSILON = 0.0005


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

    def _agent(self, agent_id: str) -> SalesAgent:
        # A malformed id (not a UUID at all) must read as "not found", not as a raw
        # psycopg `invalid input syntax for type uuid` 500 out of the column comparison
        # below - mirrors `supplier_scope.is_uuid`.
        try:
            uuid.UUID(str(agent_id))
        except (ValueError, AttributeError, TypeError):
            raise AppException(404, "Sales agent not found", code="SALES_AGENT_NOT_FOUND")
        agent = self.db.get(SalesAgent, agent_id)
        if not agent:
            raise AppException(404, "Sales agent not found", code="SALES_AGENT_NOT_FOUND")
        return agent

    def list_agents(self, query: Optional[str] = None) -> list[dict]:
        """Every active sales agent, for the Agent filter and the detail page's Agent select.

        `sales_agents` is a shared master (no `CompanyScopedMixin`, see
        `app/models/sales_agent.py`) - unscoped, same as `_agent` above and
        `sales_agent_service.resolve`. `query` is an optional substring match on the code
        or the person label, for the searchable select; omitted, every active row comes
        back (~55 today, comfortably below a page).
        """
        qs = self.db.query(SalesAgent).filter(SalesAgent.is_active.is_(True))
        if query:
            like = f"%{query.strip()}%"
            qs = qs.filter(
                or_(SalesAgent.sales_agent.ilike(like), SalesAgent.person_label.ilike(like))
            )
        rows = qs.order_by(SalesAgent.sales_agent.asc()).all()
        return [
            {
                "id": a.id,
                "sales_agent": a.sales_agent,
                "person_label": a.person_label,
                "location_group": a.location_group,
            }
            for a in rows
        ]

    def list_uom_options(self) -> list[dict]:
        """Every active unit of measure, for the line UoM select on the detail page.

        `UnitOfMeasure` is a `CompanyScopedMixin` table, so a plain query here is already
        scoped to the caller's company by the ORM's own `do_orm_execute` listener
        (`app.services.company_scope.register_company_scope_listeners`) - no manual filter
        needed, unlike the raw-SQL callers elsewhere in SCM. `is_active` IS filtered here,
        unlike the master data `/units-of-measure/select` route, which forgets it - a
        discontinued unit has no business in a fresh edit's dropdown.
        """
        rows = (
            self.db.query(UnitOfMeasure)
            .filter(UnitOfMeasure.is_active.is_(True))
            .order_by(UnitOfMeasure.uom_code.asc())
            .all()
        )
        return [{"id": u.id, "uom_code": u.uom_code, "uom_name": u.uom_name} for u in rows]

    def _product(self, sku: str) -> Product:
        prod = (
            self.db.query(Product)
            .filter(func.lower(Product.product_code) == sku.strip().lower())
            .first()
        )
        if not prod:
            raise AppException(404, f"Product not found: {sku}", code="PRODUCT_NOT_FOUND")
        return prod

    def _warehouse(self, code: str) -> Warehouse:
        wh = (
            self.db.query(Warehouse)
            .filter(func.lower(func.btrim(Warehouse.warehouse_code)) == code.strip().lower())
            .first()
        )
        if not wh:
            raise AppException(404, f"Warehouse not found: {code}", code="WAREHOUSE_NOT_FOUND")
        return wh

    @staticmethod
    def _parse_date(value: str, field_label: str) -> date:
        # A malformed ISO date (bad format, out-of-range day, ...) must read as a 422 the
        # caller can fix, not a raw `ValueError` out of `date.fromisoformat` bubbling up
        # as a 500 - same family as `_agent`'s UUID guard above.
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise AppException(
                422, f"Invalid {field_label}: {value!r} (expected YYYY-MM-DD)",
                code="INVALID_DATE",
            )

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

    def _agent_fields(
        self, agent_id: Optional[str], agent_map: Optional[dict] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """`(code, person_label)` for an agent id, or `(None, None)` when unset.

        `agent_map` is a pre-built `{id: SalesAgent}` dict so a page of orders costs ONE
        query for every distinct agent rather than one per row (see `_agent_map`, used by
        `list`). A single-record read (`get`) has no map to share, so it falls back to one
        direct lookup - still a single query, since it is a single order.
        """
        if not agent_id:
            return None, None
        agent = agent_map.get(agent_id) if agent_map is not None else self.db.get(SalesAgent, agent_id)
        if not agent:
            return None, None
        return agent.sales_agent, agent.person_label

    def _agent_map(self, rows: list[SalesOrder]) -> dict:
        ids = {so.sales_agent_id for so in rows if so.sales_agent_id}
        if not ids:
            return {}
        agents = self.db.query(SalesAgent).filter(SalesAgent.id.in_(ids)).all()
        return {a.id: a for a in agents}

    def serialize(self, so: SalesOrder, agent_map: Optional[dict] = None) -> dict:
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
                # The line's own override when one was set; otherwise the product's base
                # UOM, same as before this column was mapped.
                "uom": ln.uom or (self._uom_for(ln.product) if ln.product else ""),
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
        agent_code, agent_label = self._agent_fields(so.sales_agent_id, agent_map)
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
            # Who sold it. `sales_agent_id` rides along only so the edit screen's select can
            # pre-select the current agent; a person reads the code + label, never the id.
            "sales_agent_id": so.sales_agent_id,
            "sales_agent_code": agent_code,
            "sales_agent_label": agent_label,
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
            # The planning class this order was classified into ('project' / 'retail'), or
            # None when nobody has ever said. `order_type_label` names the ERP document type
            # (often blank, since AutoCount rarely states one); this is the answer people
            # actually asked for on this screen.
            "demand_class": so.demand_class,
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
             customer_code: Optional[str] = None, outstanding: bool = False,
             sales_agent_id: Optional[str] = None,
             demand_class: Optional[str] = None) -> dict:
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
        if sales_agent_id:
            q = q.filter(SalesOrder.sales_agent_id == sales_agent_id)
        # Same "matches nothing" rule as `source`/`status` above - a demand_class the
        # vocabulary does not know is never silently ignored. `unclassified` reads the
        # column as NULL rather than as a third stored value: the whole point of the closed
        # vocabulary (`app.services.scm.demand_class`) is that "nobody said" is not a class.
        if demand_class:
            if demand_class == "unclassified":
                q = q.filter(SalesOrder.demand_class.is_(None))
            elif demand_class in DEMAND_CLASSES:
                q = q.filter(SalesOrder.demand_class == demand_class)
            else:
                q = q.filter(text("false"))
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
        # One query for every distinct agent on the page, not one per row.
        agent_map = self._agent_map(rows)
        return {
            "data": [self.serialize(so, agent_map) for so in rows],
            "empty": total == 0,
            "pagination": {"total": total, "page": page},
        }

    # -- writes --------------------------------------------------------------

    def create(self, data, user_id: Optional[str]) -> dict:
        customer = self._customer(data.customer_code)
        so_number = NumberingService(self.db).get_next_number("sales_order", commit_rule=False)
        if not so_number:
            raise AppException(500, "Sales-order numbering rule missing", code="NUMBERING_MISSING")
        agent_id = self._agent(data.sales_agent_id).id if data.sales_agent_id else None
        so = SalesOrder(
            so_number=so_number,
            customer_id=customer.id,
            sales_agent_id=agent_id,
            order_date=date.today(),
            requested_delivery_date=(
                self._parse_date(data.requested_delivery_date, "requested_delivery_date")
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
        # `model_fields_set`, not `is not None`: an omitted field and an explicit `null`
        # both arrive as `None` on the Pydantic model, and only the latter means "clear the
        # agent" - a plain None-check could never tell "nobody touched this" from "unassign
        # her" apart, and this is the one field on this endpoint that must support clearing.
        if "sales_agent_id" in data.model_fields_set:
            so.sales_agent_id = self._agent(data.sales_agent_id).id if data.sales_agent_id else None
        if data.requested_delivery_date is not None:
            so.requested_delivery_date = (
                self._parse_date(data.requested_delivery_date, "requested_delivery_date")
                if data.requested_delivery_date else None
            )
        line_changes: list[tuple[SalesOrderLine, float, Optional[date]]] = []
        if data.lines is not None:
            line_changes = self._upsert_lines(so, data.lines)
        self.db.commit()
        # PLAN-so-book-diff-replanning.md section 2's own reaction (Order Inquiry
        # suggestions off a changed planned line), triggered by a MANUAL edit rather than
        # a re-uploaded book - see `_propagate_planning_change`. Strictly AFTER the commit
        # above: the edit has already succeeded, and this must never turn that success
        # into a 500 (CLAUDE.md: post-commit side effects are best-effort).
        planning_change_batch = (
            self._propagate_planning_change(so, line_changes, user_id) if line_changes else None
        )
        result = self.serialize(self._get_or_404(so_id))
        result["planning_change_batch"] = planning_change_batch
        return result

    def _propagate_planning_change(
        self,
        so: SalesOrder,
        line_changes: list[tuple[SalesOrderLine, float, Optional[date]]],
        actor: Optional[str],
    ) -> Optional[dict]:
        """A hand-edited qty/date raises the SAME reaction an uploaded book raises.

        `line_changes` is `_upsert_lines`'s own before-state, one `(line, old_qty,
        old_required_date)` per MATCHED existing line (never a newly-added one - there is
        no "before" for a line that did not exist). Classified into the identical
        `outstanding_diff` kinds a re-upload would produce, then handed to
        `planning_change_service.build_batch` exactly the way
        `outstanding_import_service.apply()` does - a planner correcting one line by hand
        on this screen must not get a silently different outcome than the identical
        correction arriving in next week's book.

        Best-effort, mirroring that same call site: this runs after `update()`'s own
        commit, so a defect here must cost the project a batch, never the edit that
        already saved.
        """
        changes: list[Change] = []
        applied_line_ids: dict[int, str] = {}
        for line, old_qty, old_date in line_changes:
            new_qty = float(line.qty_ordered or 0)
            new_date = line.required_date
            qty_changed = abs(new_qty - old_qty) > _QTY_EPSILON
            # A date "change" where either endpoint is `None` is not a schedule move - a
            # line getting its FIRST-EVER date, or one just cleared, is not a delay/advance
            # (mirrors `planning_change_service._is_null_anchored_date_move`). That guard
            # lives downstream in `build_batch` and would drop such a change ENTIRELY,
            # including a real qty change riding on the same line - so it is decided HERE
            # instead, folding a null-anchored date into a plain qty comparison rather than
            # depending on the downstream guard alone to catch it.
            date_changed = (
                old_date is not None and new_date is not None and old_date != new_date
            )
            if date_changed and qty_changed:
                kind = DATE_AND_QTY_CHANGED
            elif date_changed:
                kind = DATE_MOVED
            elif qty_changed:
                kind = QTY_CHANGED
            else:
                continue  # unchanged - not material, never reaches the batch builder
            item_code = line.product.product_code if line.product else ""
            location = line.warehouse.warehouse_code if line.warehouse is not None else ""
            before = Line(
                doc_number=so.so_number, item_code=item_code, location=location,
                qty=old_qty, required_date=old_date, row_ref=str(line.id),
            )
            after = Line(
                doc_number=so.so_number, item_code=item_code, location=location,
                qty=new_qty, required_date=new_date, row_ref=str(line.id),
            )
            change = Change(
                kind=kind, doc_number=so.so_number, item_code=item_code, location=location,
                before=before, after=after,
            )
            changes.append(change)
            applied_line_ids[id(change)] = str(line.id)

        if not changes:
            return None

        diff = Diff(scope_documents=(so.so_number,), changes=changes)
        try:
            from app.services import planning_change_service

            batch = planning_change_service.build_batch(
                self.db,
                diff,
                applied_line_ids=applied_line_ids,
                order_ids={so.so_number: str(so.id)},
                actor=actor,
                import_job_id=None,
                file_name=None,
            )
            if batch is None:
                return None
            # `build_batch` takes no source-kind parameter - its only caller until now was
            # the SO-book upload, which is the column's own `server_default`. Stamp this
            # batch as a manual edit's own reaction after the fact, in its own commit, so a
            # defect in the stamp can never roll back the SO edit `update()` already
            # committed above.
            batch.source_kind = PLANNING_CHANGE_SOURCE_SO_MANUAL_EDIT
            self.db.commit()
            return {
                "id": str(batch.id),
                "order_count": batch.order_count,
                "line_count": batch.line_count,
            }
        except Exception:  # pragma: no cover - defensive, see docstring above
            logger.exception("planning change batch failed for a manual sales-order edit")
            self.db.rollback()
            return None

    def _upsert_lines(
        self, so: SalesOrder, incoming: list
    ) -> list[tuple[SalesOrderLine, float, Optional[date]]]:
        """Reconcile ``so.lines`` against the payload IN PLACE, never delete + recreate.

        A delete-and-reinsert (the previous behaviour) resets `qty_delivered` to 0, forces
        `source_system` back to "manual" on every line, and mints new line ids - which severs
        `ProjectSalesOrderLine.core_sales_order_line_id` and any `OrderLinkClaim` pointing at
        the old id (both `ondelete="SET NULL"`), silently dropping an adopted order's mirror
        link on an ordinary qty edit. Instead: match each payload line to an existing row,
        update only what the payload actually says (qty_ordered / product, plus
        warehouse / required_date / uom when the caller SENT that key - see below), and leave
        `qty_delivered`, `source_system`, `line_status` and the id untouched.

        Matched by `id` when the payload carries one (the FE does not send it today, but a
        future caller - or n8n - might); otherwise by SKU, first-unmatched-row-wins when a
        SKU repeats within the order. A payload line that matches nothing existing is a new
        line. An existing line that nothing in the payload claims is removed - unless it is
        still referenced by a project sales-order line's reconciled core link or an
        SO<->PO `OrderLinkClaim`, in which case the whole update is refused with a 409 rather
        than silently orphaning that link.

        `warehouse_code` / `required_date` / `uom` are applied via `model_fields_set`, not a
        plain `is not None` check: a key the caller never sent must leave the stored value
        alone (this is how a same-order qty-only edit, which does not carry these keys,
        cannot wipe out a location/date/UoM another edit set), while a key sent as an
        explicit `null`/`""` clears it.

        Returns one `(line, old_qty_ordered, old_required_date)` per MATCHED existing line -
        its state as it was before this method touched it - for `_propagate_planning_change`
        to diff against the line's now-written values. Newly-added lines carry no "before"
        and are not returned.
        """
        existing_lines = list(so.lines)
        matched_ids: set[str] = set()
        line_changes: list[tuple[SalesOrderLine, float, Optional[date]]] = []

        for ln in incoming:
            ln_id = getattr(ln, "id", None)
            target = None
            if ln_id and ln_id not in matched_ids:
                target = next((l for l in existing_lines if l.id == ln_id), None)
            if target is None:
                sku_norm = ln.sku.strip().lower()
                target = next(
                    (
                        l for l in existing_lines
                        if l.id not in matched_ids
                        and l.product is not None
                        and l.product.product_code.lower() == sku_norm
                    ),
                    None,
                )
            prod = self._product(ln.sku)
            fields_set = ln.model_fields_set
            warehouse_id = (
                self._warehouse(ln.warehouse_code).id if ln.warehouse_code else None
            ) if "warehouse_code" in fields_set else None
            required_date = (
                self._parse_date(ln.required_date, "required_date") if ln.required_date else None
            ) if "required_date" in fields_set else None
            uom = (ln.uom or None) if "uom" in fields_set else None
            if target is not None:
                matched_ids.add(target.id)
                # Snapshotted BEFORE any of the mutations below - the only place this
                # line's prior qty/date exist once they are overwritten.
                line_changes.append(
                    (target, float(target.qty_ordered or 0), target.required_date)
                )
                target.product_id = prod.id
                target.qty_ordered = ln.qty_ordered
                if "warehouse_code" in fields_set:
                    target.warehouse_id = warehouse_id
                if "required_date" in fields_set:
                    target.required_date = required_date
                if "uom" in fields_set:
                    target.uom = uom
            else:
                self.db.add(SalesOrderLine(
                    sales_order_id=so.id,
                    product_id=prod.id,
                    qty_ordered=ln.qty_ordered,
                    qty_delivered=0,
                    priority=so.priority,
                    line_status="open",
                    source_system="manual",
                    warehouse_id=warehouse_id,
                    required_date=required_date,
                    uom=uom,
                ))

        removed = [l for l in existing_lines if l.id not in matched_ids]
        if removed:
            removed_ids = [l.id for l in removed]
            linked = (
                self.db.query(ProjectSalesOrder.provisional_ref)
                .join(
                    ProjectSalesOrderLine,
                    ProjectSalesOrderLine.project_sales_order_id == ProjectSalesOrder.id,
                )
                .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(removed_ids))
                .first()
            )
            if linked:
                raise AppException(
                    409,
                    f"Cannot remove a line reconciled to project sales order {linked[0]}",
                    code="SO_LINE_LINKED_TO_PROJECT",
                )
            claim = (
                self.db.query(OrderLinkClaim)
                .filter(OrderLinkClaim.so_line_id.in_(removed_ids))
                .first()
            )
            if claim:
                raise AppException(
                    409,
                    f"Cannot remove a line claimed by purchase order {claim.po_number}",
                    code="SO_LINE_LINKED_TO_CLAIM",
                )
            for l in removed:
                self.db.delete(l)

        return line_changes

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
