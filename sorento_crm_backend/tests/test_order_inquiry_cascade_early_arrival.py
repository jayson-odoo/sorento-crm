"""S1/S2 - the auto-link cascade skips a document arriving outside the row's lead-time
window.

`PLAN-oi-cascade-skip-early-arrival.md`, UAC `oi-cascade-skip-early-arrival-acceptance-
criteria.md` AC-EA-1 to AC-EA-12 (AC-EA-13 is the browser one, not this file's).

`blank_session` throughout, not `pg_session`, for the same reason
`test_order_inquiry_links.py` and `test_order_inquiry_dedication.py` give: the cascade this
file exercises is ranked against the WHOLE open purchase-order book, and the shared local
database holds the captain's real one. The `_World` below is the same shape those two
files build (seed your own chain; CI's database is empty), widened with a `lead_time`
helper for `product_suppliers.standard_lead_time_days` and a `delivery_date`/`state` on
`row()`.

Dates fixed for every test (UAC preamble): delivery 2027-01-15. Stated lead 30 days puts
the window edge at 2026-12-16 (on or before is early); the default 90-day lead puts it at
2026-10-17.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.project_so import OrderInquiryLink
from app.services.project_order_inquiry_service import (
    ProjectOrderInquiryService,
    arrives_outside_window,
)

from ._pg_fixture import blank_session

MARKER = "ZZT-OICE"

#: The seed's own delivery date and the two lead-time thresholds derived from it.
DELIVERY = date(2027, 1, 15)
STATED_LEAD = 30
STATED_THRESHOLD = DELIVERY - timedelta(days=STATED_LEAD)  # 2026-12-16
DEFAULT_LEAD = 90
DEFAULT_THRESHOLD = DELIVERY - timedelta(days=DEFAULT_LEAD)  # 2026-10-17


def _uid() -> str:
    return str(uuid.uuid4())


#: The `projects` schema THIS session writes to, bound once by the `world` fixture - see
#: `test_order_inquiry_links.py._projects` for the trap this guards against (a hard-coded
#: `projects.*` inside a `text()` statement resolves by NAME, reaching the real schema).
P = "projects"


def _projects(db) -> str:
    current = db.execute(text("select current_schema()")).scalar()
    return "projects" if current in (None, "public") else f'"{current}_projects"'


class _World:
    """Masters + one PROJECT sales order (the row's own identity), the same shape
    `test_order_inquiry_dedication.py._World` builds, widened for this slice."""

    def __init__(self, db):
        self.db = db
        self.company_id = db.execute(
            text("select id from companies where code = 'SRT'")
        ).scalar()
        self.warehouses: dict[str, str] = {}
        self.svc = ProjectOrderInquiryService(db)
        self._build()

    # -- masters ---------------------------------------------------------------

    def _build(self) -> None:
        db = self.db
        cat, uom = _uid(), _uid()
        db.execute(
            text(
                "INSERT INTO product_categories (id, category_code, category_name) "
                "VALUES (:i, :c, :c)"
            ),
            {"i": cat, "c": f"{MARKER}-CAT"},
        )
        db.execute(
            text("INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:i, :c, :c)"),
            {"i": uom, "c": f"{MARKER}-UOM"},
        )
        self.product = _uid()
        db.execute(
            text(
                "INSERT INTO products (id, company_id, product_code, product_name, "
                "category_id, base_uom_id, list_price) "
                "VALUES (:i, :c, :code, :code, :cat, :uom, 0)"
            ),
            {
                "i": self.product,
                "c": self.company_id,
                "code": f"{MARKER}-7405",
                "cat": cat,
                "uom": uom,
            },
        )
        # BRW is a POOL: `segment` left NULL, which `is_site_pool` reads as a site pool
        # (COALESCE ... <> 'project'). No hyphen in the code, so `group_of_warehouse_code`
        # resolves no ownership group for it either - never a candidate for ladder v4's
        # group-deficit gate, which this file has nothing to say about.
        pool = _uid()
        db.execute(
            text(
                "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
                "is_active) VALUES (:i, :c, 'BRW', 'BRW', true)"
            ),
            {"i": pool, "c": self.company_id},
        )
        self.warehouses["BRW"] = pool
        self.supplier = _uid()
        db.execute(
            text(
                "INSERT INTO suppliers (id, company_id, supplier_code, supplier_name, "
                "is_active) VALUES (:i, :c, :code, :code, true)"
            ),
            {"i": self.supplier, "c": self.company_id, "code": f"{MARKER}-SUP"},
        )
        self.pso, self.inquiry = _uid(), _uid()
        db.execute(
            text(
                "INSERT INTO " + P + ".sales_orders (id, company_id, provisional_ref, "
                "status, created_at, updated_at) "
                "VALUES (:i, :c, :ref, 'published', now(), now())"
            ),
            {"i": self.pso, "c": self.company_id, "ref": f"{MARKER}-PSO"},
        )
        db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiries (id, company_id, inquiry_no, "
                "project_sales_order_id, state, raised_at) "
                "VALUES (:i, :c, :no, :p, 'raised', now())"
            ),
            {
                "i": self.inquiry,
                "c": self.company_id,
                "no": f"OI-{_uid()[:6].upper()}",
                "p": self.pso,
            },
        )
        self.line = _uid()
        db.execute(
            text(
                "INSERT INTO " + P + ".sales_order_lines (id, company_id, "
                "project_sales_order_id, line_no, qty, unit_price, amount, product_id, "
                "created_at) VALUES (:i, :c, :p, 1, 100, 0, 0, :prod, now())"
            ),
            {"i": self.line, "c": self.company_id, "p": self.pso, "prod": self.product},
        )
        db.flush()

    # -- documents -------------------------------------------------------------

    def purchase_order(self, number: str, issue_date: date, lines, *, product=None) -> list[str]:
        """One purchase order and its lines. `lines` is (location, qty, expected, label)."""
        po = _uid()
        self.db.execute(
            text(
                "INSERT INTO purchase_orders (id, company_id, po_number, supplier_id, "
                "status, issue_date) VALUES (:i, :c, :n, :s, 'active', :d)"
            ),
            {
                "i": po,
                "c": self.company_id,
                "n": number,
                "s": self.supplier,
                "d": issue_date,
            },
        )
        ids = []
        for location, qty, expected, label in lines:
            lid = _uid()
            self.db.execute(
                text(
                    "INSERT INTO purchase_order_lines (id, company_id, "
                    "purchase_order_id, product_id, warehouse_id, qty_ordered, "
                    "qty_received, line_status, expected_date, source_ref) "
                    "VALUES (:i, :c, :po, :p, :w, :q, 0, 'open', :e, :r)"
                ),
                {
                    "i": lid,
                    "c": self.company_id,
                    "po": po,
                    "p": product or self.product,
                    "w": self.warehouses[location],
                    "q": qty,
                    "e": expected,
                    "r": label,
                },
            )
            ids.append(lid)
        self.db.flush()
        return ids

    def spo_allocation(
        self, number: str, location: str, qty, *, line_number=1, expected=None, product=None
    ) -> str:
        allocation = _uid()
        self.db.execute(
            text(
                "INSERT INTO spo_allocations (id, company_id, spo_number, "
                "spo_line_number, product_id, warehouse_id, allocated_quantity, "
                "quantity_received, quantity_rejected, receipt_status, line_status, "
                "issue_date, expected_date, synced_to_excel, created_at) "
                "VALUES (:i, :c, :n, :ln, :p, :w, :q, 0, 0, 'pending', 'open', :iss, "
                ":exp, false, now())"
            ),
            {
                "i": allocation,
                "c": self.company_id,
                "n": number,
                "ln": line_number,
                "p": product or self.product,
                "w": self.warehouses[location],
                "q": qty,
                "iss": date(2026, 8, 12),
                "exp": expected,
            },
        )
        self.db.flush()
        return allocation

    def another_product(self, code: str) -> str:
        """A SECOND product on the same masters, for AC-EA-5's independent scenario."""
        cat = self.db.execute(
            text("SELECT id FROM product_categories WHERE category_code = :c"),
            {"c": f"{MARKER}-CAT"},
        ).scalar()
        uom = self.db.execute(
            text("SELECT id FROM units_of_measure WHERE uom_code = :c"),
            {"c": f"{MARKER}-UOM"},
        ).scalar()
        product = _uid()
        self.db.execute(
            text(
                "INSERT INTO products (id, company_id, product_code, product_name, "
                "category_id, base_uom_id, list_price) "
                "VALUES (:i, :c, :code, :code, :cat, :uom, 0)"
            ),
            {"i": product, "c": self.company_id, "code": code, "cat": cat, "uom": uom},
        )
        self.db.flush()
        return product

    def lead_time(self, product_id: str, *, days: int) -> None:
        """The STATED source `ProjectSupplyService.lead_times` (and the pill) read
        (`product_suppliers.standard_lead_time_days`) - no `scm.supplier_performance`
        row, so the MEASURED source never outranks it."""
        supplier = _uid()
        self.db.execute(
            text(
                "INSERT INTO suppliers (id, company_id, supplier_code, supplier_name, "
                "is_active) VALUES (:i, :c, :code, :code, true)"
            ),
            {"i": supplier, "c": self.company_id, "code": f"{MARKER}-LEAD-{_uid()[:8]}"},
        )
        self.db.execute(
            text(
                "INSERT INTO product_suppliers (id, company_id, product_id, supplier_id, "
                "standard_lead_time_days, is_primary_supplier) "
                "VALUES (:i, :c, :p, :s, :d, true)"
            ),
            {"i": _uid(), "c": self.company_id, "p": product_id, "s": supplier, "d": days},
        )
        self.db.flush()

    def row(
        self,
        verb: str,
        qty,
        *,
        location="BRW-IB",
        cited=None,
        so_line=True,
        item_code=None,
        ack_state="acknowledged",
        delivery_date=None,
        state="raised",
    ):
        """One instruction, ACKNOWLEDGED by default (`PLAN-scm-oi-handshake.md`). `state`
        is a parameter so AC-EA-10 can seed a row that already reads `placed` from an
        earlier (pre-feature) cascade pass."""
        rid = _uid()
        line_id = self.line if so_line is True else (None if so_line is False else so_line)
        self.db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiry_rows (id, company_id, "
                "order_inquiry_id, so_line_id, item_code, qty, verb, stock_location, "
                "cited_document, state, ack_state, delivery_date, redirected_to_pool, "
                "created_at) "
                "VALUES (:i, :c, :inq, :l, :code, :q, :v, :loc, :cd, :st, :ack, :dd, "
                "false, now())"
            ),
            {
                "i": rid,
                "c": self.company_id,
                "inq": self.inquiry,
                "l": line_id,
                "code": item_code or f"{MARKER}-7405",
                "q": Decimal(str(qty)),
                "v": verb,
                "loc": location,
                "cd": cited,
                "st": state,
                "ack": ack_state,
                "dd": delivery_date,
            },
        )
        self.db.flush()
        return self.svc._row_or_404(rid)

    # -- G7 evidence (AC-EA-6) --------------------------------------------------

    def set_own_so_number(self, value: str) -> None:
        """The identity `_row_so_number` reads for every row in this world - the
        PROJECT sales order's `autocount_doc_no`."""
        self.db.execute(
            text("UPDATE " + P + ".sales_orders SET autocount_doc_no = :v WHERE id = :i"),
            {"v": value, "i": self.pso},
        )
        self.db.flush()

    def claiming_so(
        self, so_number: str, order_date: date, *, qty=100, qty_delivered=0,
        line_status="open",
    ) -> tuple[str, str]:
        """A CORE sales order + one line, standing in for the SO that claims a document
        line (G7). Returns `(sales_order_id, sales_order_line_id)`."""
        so_id = _uid()
        self.db.execute(
            text(
                "INSERT INTO sales_orders (id, company_id, so_number, order_date, "
                "status, demand_class) VALUES (:i, :c, :n, :d, 'open', 'project')"
            ),
            {"i": so_id, "c": self.company_id, "n": so_number, "d": order_date},
        )
        line_id = _uid()
        self.db.execute(
            text(
                "INSERT INTO sales_order_lines (id, company_id, sales_order_id, "
                "product_id, warehouse_id, qty_ordered, qty_delivered, line_status, "
                "required_date) VALUES (:i, :c, :so, :p, :w, :q, :qd, :ls, :d)"
            ),
            {
                "i": line_id,
                "c": self.company_id,
                "so": so_id,
                "p": self.product,
                "w": self.warehouses["BRW"],
                "q": Decimal(str(qty)),
                "qd": Decimal(str(qty_delivered)),
                "ls": line_status,
                "d": order_date,
            },
        )
        self.db.flush()
        return so_id, line_id

    def claim(
        self, *, so_number: str, po_number: str, so_line_id, po_line_id=None,
        spo_allocation_id=None, item_code=None, source="po_history", resolved=True,
    ) -> str:
        """One `scm.order_link_claim` row - the evidence `_dedication_for_target` reads.
        Unqualified table name: `blank_session` pins `search_path` to the scratch `_scm`
        schema first (see `test_order_inquiry_dedication.py._World.claim` for the trap a
        hard-coded `scm.` prefix would walk into)."""
        claim_id = _uid()
        self.db.execute(
            text(
                "INSERT INTO order_link_claim (id, company_id, so_number, po_number, "
                "item_code, source, so_line_id, po_line_id, spo_allocation_id, "
                "resolved_at) VALUES (:i, :c, :son, :pon, :item, :src, :sol, :pol, "
                ":spo, :resolved_at)"
            ),
            {
                "i": claim_id,
                "c": self.company_id,
                "son": so_number,
                "pon": po_number,
                "item": item_code,
                "src": source,
                "sol": so_line_id,
                "pol": po_line_id,
                "spo": spo_allocation_id,
                "resolved_at": datetime.utcnow() if resolved else None,
            },
        )
        self.db.flush()
        return claim_id


@pytest.fixture()
def world():
    global P
    with blank_session() as db:
        P = _projects(db)
        built = _World(db)
        with company_scope(db, frozenset({built.company_id})):
            yield built


# ============================================================ S1 - the predicate (AC-EA-1)


@pytest.mark.parametrize(
    "expected, delivery, lead, want",
    [
        # True exactly on the boundary - a full lead time (or more) early.
        (date(2026, 12, 16), date(2027, 1, 15), 30, True),
        # False one day inside the window.
        (date(2026, 12, 17), date(2027, 1, 15), 30, False),
        # False when the document is promised AFTER delivery altogether.
        (date(2027, 2, 1), date(2027, 1, 15), 30, False),
        # False on either date missing.
        (None, date(2027, 1, 15), 30, False),
        (date(2026, 12, 16), None, 30, False),
        (None, None, 30, False),
    ],
)
def test_ac_ea_1_arrives_outside_window_is_the_lead_time_boundary(expected, delivery, lead, want):
    """AC-EA-1: `arrives_outside_window(expected, delivery, lead)` - True at
    `expected == delivery - lead`, False the day after, False past delivery, False on
    either date missing."""
    assert arrives_outside_window(expected, delivery, lead) is want


# ==================================================== S1 - the shared reader (AC-EA-2)


def test_ac_ea_2_the_worklist_reads_the_shared_predicate(world):
    """AC-EA-2: `order_inquiry_worklist_service` calls the SAME `arrives_outside_window`
    the cascade does - checked by identity, not by re-deriving the rule a second time -
    and a hand-placed early link still reads `reallocate` / `unlink` through it exactly
    as it always did (the existing `test_order_inquiry_worklist.py` S1b suite, unchanged)."""
    from app.services import order_inquiry_worklist_service as worklist_module
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    assert worklist_module.arrives_outside_window is arrives_outside_window

    world.lead_time(world.product, days=STATED_LEAD)
    line = world.purchase_order(
        "ZZT-EA2-PO", date(2026, 8, 1), [("BRW", 20, date(2026, 10, 1), "1")]
    )[0]
    row = world.row("ORDER", 20, location="BRW", delivery_date=DELIVERY)
    world.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line, "qty": Decimal("20")}], actor_user_id=None
    )
    world.db.flush()

    entry = next(
        item
        for item in OrderInquiryWorklistService(world.db).list_rows(limit=100)["data"]
        if item["id"] == row.id
    )
    [link] = entry["links"]
    assert link["suggestion"]["kind"] in ("reallocate", "unlink")


# ======================================================== S2 - the cascade (AC-EA-3..12)


def test_ac_ea_3_a_stated_lead_row_refuses_its_only_early_po_line(world):
    """AC-EA-3: delivery 2027-01-15, lead 30, the only open PO line promised 2026-10-01 -
    no link, `placed_rows == 0`, the row stays `raised`."""
    world.lead_time(world.product, days=STATED_LEAD)
    world.purchase_order(
        "ZZT-EA3-PO", date(2026, 8, 1), [("BRW", 20, date(2026, 10, 1), "1")]
    )
    row = world.row("ORDER", 20, location="BRW", delivery_date=DELIVERY)

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row)

    assert result["placed_rows"] == 0
    assert row.state == "raised"
    assert world.svc._links_of(row.id) == []


def test_ac_ea_4_a_stated_lead_row_links_a_po_line_inside_the_window(world):
    """AC-EA-4: same row, the PO line promised 2026-12-20 (inside the window) - linked as
    before, `placed_rows == 1`."""
    world.lead_time(world.product, days=STATED_LEAD)
    line = world.purchase_order(
        "ZZT-EA4-PO", date(2026, 8, 1), [("BRW", 20, date(2026, 12, 20), "1")]
    )[0]
    row = world.row("ORDER", 20, location="BRW", delivery_date=DELIVERY)

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row)

    assert result["placed_rows"] == 1
    assert row.state == "placed"
    [link] = world.svc._links_of(row.id)
    assert link.po_line_id == line


def test_ac_ea_5_default_lead_time_refuses_at_ninety_days_and_links_the_day_after(world):
    """AC-EA-5: no stated and no measured lead time -> default 90. A PO promised
    2026-10-17 (delivery - 90) is refused; one promised 2026-10-18 is linked. Two
    independent products so the two outcomes cannot interfere with each other's walk."""
    refused_product = world.product
    world.purchase_order(
        "ZZT-EA5A-PO", date(2026, 8, 1), [("BRW", 20, DEFAULT_THRESHOLD, "1")]
    )
    row_refused = world.row("ORDER", 20, location="BRW", delivery_date=DELIVERY)

    linked_code = f"{MARKER}-EA5B"
    linked_product = world.another_product(linked_code)
    line_linked = world.purchase_order(
        "ZZT-EA5B-PO", date(2026, 8, 1),
        [("BRW", 20, DEFAULT_THRESHOLD + timedelta(days=1), "1")],
        product=linked_product,
    )[0]
    row_linked = world.row(
        "ORDER", 20, location="BRW", delivery_date=DELIVERY,
        item_code=linked_code, so_line=False,
    )

    result = world.svc.auto_place_for_products(
        [refused_product, linked_product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row_refused)
    world.db.refresh(row_linked)

    assert result["placed_rows"] == 1
    assert row_refused.state == "raised"
    assert world.svc._links_of(row_refused.id) == []
    assert row_linked.state == "placed"
    [link] = world.svc._links_of(row_linked.id)
    assert link.po_line_id == line_linked


def test_ac_ea_6_an_early_line_this_rows_own_so_claims_links_regardless_of_the_window(world):
    """AC-EA-6: an early PO line THIS row's own SO claims (`scm.order_link_claim`) is
    linked regardless of the window."""
    world.lead_time(world.product, days=STATED_LEAD)
    line = world.purchase_order(
        "ZZT-EA6-PO", date(2026, 8, 1), [("BRW", 20, date(2026, 10, 1), "1")]
    )[0]
    world.set_own_so_number("ZZT-EA6-OWN")
    _, own_core_line = world.claiming_so("ZZT-EA6-OWN", date(2026, 7, 1), qty=20)
    world.claim(
        so_number="ZZT-EA6-OWN", po_number="ZZT-EA6-PO", so_line_id=own_core_line,
        po_line_id=line,
    )
    row = world.row("ORDER", 20, location="BRW", delivery_date=DELIVERY)

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row)

    assert result["placed_rows"] == 1
    assert row.state == "placed"
    [link] = world.svc._links_of(row.id)
    assert link.po_line_id == line


def test_ac_ea_7_an_early_line_the_row_cites_links_regardless_of_the_window(world):
    """AC-EA-7: an early PO line whose document number the row cites is linked
    regardless of the window."""
    world.lead_time(world.product, days=STATED_LEAD)
    line = world.purchase_order(
        "ZZT-EA7-PO", date(2026, 8, 1), [("BRW", 20, date(2026, 10, 1), "1")]
    )[0]
    row = world.row(
        "ORDER", 20, location="BRW", delivery_date=DELIVERY, cited="ZZT-EA7-PO"
    )

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row)

    assert result["placed_rows"] == 1
    assert row.state == "placed"
    [link] = world.svc._links_of(row.id)
    assert link.po_line_id == line


def test_ac_ea_8_only_the_inside_candidate_counts_toward_cover(world):
    """AC-EA-8, first half: an early line and an inside-window line both open - only the
    inside one is taken."""
    world.lead_time(world.product, days=STATED_LEAD)
    lines = world.purchase_order(
        "ZZT-EA8-PO", date(2026, 8, 1),
        [("BRW", 20, date(2026, 10, 1), "1"), ("BRW", 20, date(2026, 12, 20), "2")],
    )
    _early_line, inside_line = lines
    row = world.row("ORDER", 15, location="BRW", delivery_date=DELIVERY)

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row)

    assert result["placed_rows"] == 1
    assert row.state == "placed"
    [link] = world.svc._links_of(row.id)
    assert link.po_line_id == inside_line


def test_ac_ea_8_when_the_inside_candidate_alone_cannot_cover_the_need_nothing_links(world):
    """AC-EA-8, second half: the early line's 100 would have covered the row easily, but
    it does not count toward cover - the inside line's own 4 falls short of the 10
    needed, so nothing links and the row stays raised."""
    world.lead_time(world.product, days=STATED_LEAD)
    world.purchase_order(
        "ZZT-EA8B-PO", date(2026, 8, 1),
        [("BRW", 100, date(2026, 10, 1), "1"), ("BRW", 4, date(2026, 12, 20), "2")],
    )
    row = world.row("ORDER", 10, location="BRW", delivery_date=DELIVERY)

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row)

    assert result["placed_rows"] == 0
    assert row.state == "raised"
    assert world.svc._links_of(row.id) == []


def test_ac_ea_9_an_early_spo_allocation_is_refused_the_same_way_as_a_po_line(world):
    """AC-EA-9: an SPO allocation candidate promised a full lead time early is refused,
    the same way a PO line is."""
    world.lead_time(world.product, days=STATED_LEAD)
    world.spo_allocation("ZZT-EA9-SPO", "BRW", 20, expected=date(2026, 10, 1))
    row = world.row("ORDER", 20, location="BRW", delivery_date=DELIVERY)

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row)

    assert result["placed_rows"] == 0
    assert row.state == "raised"
    assert world.svc._links_of(row.id) == []


def test_ac_ea_10_a_redeal_keeps_a_draft_on_an_early_line_with_nothing_better(world):
    """AC-EA-10: a row already holding a cascade draft on an early line, walked again
    with `redeal_drafts=True` and no better candidate, keeps that draft - no unlink, no
    note appended."""
    world.lead_time(world.product, days=STATED_LEAD)
    line = world.purchase_order(
        "ZZT-EA10-PO", date(2026, 8, 1), [("BRW", 20, date(2026, 10, 1), "1")]
    )[0]
    row = world.row(
        "ORDER", 20, location="BRW", delivery_date=DELIVERY, state="placed"
    )
    world.db.add(
        OrderInquiryLink(
            id=_uid(), company_id=world.company_id, row_id=row.id, po_line_id=line,
            document="ZZT-EA10-PO", qty=Decimal("20"), auto=True,
        )
    )
    world.db.flush()

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt", redeal_drafts=True
    )
    world.db.refresh(row)

    assert result["placed_rows"] == 0
    assert row.state == "placed"
    assert row.note is None
    [link] = world.svc._links_of(row.id)
    assert link.po_line_id == line


def test_ac_ea_11_a_row_past_the_link_horizon_is_counted_after_horizon_first(world):
    """AC-EA-11: a row due beyond the link horizon is counted `after_horizon` before the
    window is ever consulted - unchanged from the existing horizon behaviour."""
    from app.models.scm import ReorderRun

    world.db.add(
        ReorderRun(
            id=_uid(),
            status="completed",
            plan_horizon_date=date(2026, 12, 1),
            started_at=datetime(2026, 9, 1, 9, 0, 0),
            finished_at=datetime(2026, 9, 1, 9, 0, 0),
        )
    )
    world.db.flush()
    world.lead_time(world.product, days=STATED_LEAD)
    world.purchase_order(
        "ZZT-EA11-PO", date(2026, 8, 1), [("BRW", 20, date(2026, 12, 20), "1")]
    )
    row = world.row("ORDER", 20, location="BRW", delivery_date=DELIVERY)

    result = world.svc.auto_place_for_products(
        [world.product], actor_user_id=None, trigger="zzt"
    )
    world.db.refresh(row)

    assert result["after_horizon"] == 1
    assert result["placed_rows"] == 0
    assert row.state == "raised"


def test_ac_ea_12_the_link_dialog_still_offers_the_early_line_by_hand(world):
    """AC-EA-12: `po_candidates_for_row` still lists the early line, `place_on_po_
    allocations` by hand still links it, and that link then shows the `reallocate` /
    `unlink` suggestion on the worklist - the window narrows the automatic pass only."""
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    world.lead_time(world.product, days=STATED_LEAD)
    line = world.purchase_order(
        "ZZT-EA12-PO", date(2026, 8, 1), [("BRW", 20, date(2026, 10, 1), "1")]
    )[0]
    row = world.row("ORDER", 20, location="BRW", delivery_date=DELIVERY)

    candidates = world.svc.po_candidates_for_row(row.id)
    assert candidates[0]["po_line_id"] == line

    world.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line, "qty": Decimal("20")}], actor_user_id=None
    )
    world.db.flush()

    entry = next(
        item
        for item in OrderInquiryWorklistService(world.db).list_rows(limit=100)["data"]
        if item["id"] == row.id
    )
    [link] = entry["links"]
    assert link["suggestion"]["kind"] in ("reallocate", "unlink")
