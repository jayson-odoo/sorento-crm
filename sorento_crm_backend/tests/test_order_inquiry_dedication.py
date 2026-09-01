"""S6 - dedication-aware OI takes (claims), G7 + G12.

`PLAN-scm-reorder-oi-feedback-1sep.md` S6, `scm-reorder-oi-feedback-1sep-acceptance-
criteria.md` AC-6.1 through AC-6.10 (AC-6.11 is `tests/scm/test_project_bin_lock.py`,
AC-6.12 is `tests/scm/test_reorder_engine_project_bin_netting.py`, AC-6.5 is
`sorento_crm_frontend/.../LinkDocumentDialog.test.tsx`).

`blank_session` throughout, not `pg_session`, for the same reason
`test_order_inquiry_links.py` gives: the walk under test is ranked against the WHOLE
purchase-order book, and the shared local database holds the captain's real 80,000-line
one. A fixture line for a real product would be judged against thousands of neighbours a
claim was never written for, and the assertions would move whenever somebody re-uploaded
the book.

The world this file adds on top of `test_order_inquiry_links.py`'s own `_World` shape:
a "claiming SO" is a CORE `sales_orders` row (`world.claiming_so`), because that is what
`scm.order_link_claim.so_line_id` resolves against - never the PROJECT sales order the OI
row itself belongs to. A claim is written directly (`world.claim`), standing in for
whatever wrote it in production (`order_link_service.claim_placed_on_po` on a manual link,
or the resolver once both sides exist).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.services.project_order_inquiry_service import (
    TIER_SIBLING,
    ProjectOrderInquiryService,
)
from app.services.scm import order_link_service

from ._pg_fixture import blank_session

MARKER = "ZZT-DEDIC"

#: Relative to today, so an open SPO allocation does not quietly stop being one a few days
#: after this file was written.
SOON = date.today() + timedelta(days=30)


def _uid() -> str:
    return str(uuid.uuid4())


#: The `projects` schema THIS session writes to, bound once by the `world` fixture.
P = "projects"


def _projects(db) -> str:
    """Where `projects.*` lives under THIS session (see `test_order_inquiry_links.py`'s
    own copy of this function for the trap it guards against)."""
    current = db.execute(text("select current_schema()")).scalar()
    return "projects" if current in (None, "public") else f'"{current}_projects"'


class _World:
    """Everything one test needs: masters, one PROJECT sales order (the OI row's own
    identity), and the helpers G7/G12 tests build claims and project-bin warehouses
    from."""

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
        # BRW is a POOL because other locations point at it, which is the only authority
        # the tier rule reads - never the shape of the code.
        pool = _uid()
        db.execute(
            text(
                "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
                "is_active) VALUES (:i, :c, 'BRW', 'BRW', true)"
            ),
            {"i": pool, "c": self.company_id},
        )
        self.warehouses["BRW"] = pool
        for code in ("BRW-IB", "BRW-BB"):
            wid = _uid()
            db.execute(
                text(
                    "INSERT INTO warehouses (id, company_id, warehouse_code, "
                    "warehouse_name, is_active, pool_warehouse_id) "
                    "VALUES (:i, :c, :code, :code, true, :p)"
                ),
                {"i": wid, "c": self.company_id, "code": code, "p": pool},
            )
            self.warehouses[code] = wid
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

    def purchase_order(self, number: str, issue_date: date, lines) -> list[str]:
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
                    "p": self.product,
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
        self, number: str, location: str, qty, *, line_number=1, expected=None
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
                "p": self.product,
                "w": self.warehouses[location],
                "q": qty,
                "iss": date(2026, 8, 12),
                "exp": expected or SOON,
            },
        )
        self.db.flush()
        return allocation

    def project_bin_warehouse(self, code: str) -> None:
        """A `segment = 'project'` warehouse (G12) - a bin nobody may auto-take unless
        the row's own SO claims it."""
        wid = _uid()
        self.db.execute(
            text(
                "INSERT INTO warehouses (id, company_id, warehouse_code, warehouse_name, "
                "is_active, segment) VALUES (:i, :c, :code, :code, true, 'project')"
            ),
            {"i": wid, "c": self.company_id, "code": code},
        )
        self.warehouses[code] = wid
        self.db.flush()

    def row(self, verb, qty, *, location="BRW-IB", cited=None, so_line=True,
            item_code=None, ack_state="acknowledged"):
        """One instruction, ACKNOWLEDGED by default. `so_line` is `True` for the
        fixture's own `self.line`, `False` for none, or a project sales-order LINE id -
        `world.own_so_line(core_line_id)`'s return - to give a row an identity reconciled
        to a specific CORE line (what a manual link's claim-write needs, AC-6.9)."""
        rid = _uid()
        line_id = self.line if so_line is True else (None if so_line is False else so_line)
        self.db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiry_rows (id, company_id, "
                "order_inquiry_id, so_line_id, item_code, qty, verb, stock_location, "
                "cited_document, state, ack_state, redirected_to_pool, created_at) "
                "VALUES (:i, :c, :inq, :l, :code, :q, :v, :loc, :cd, 'raised', "
                ":ack, false, now())"
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
                "ack": ack_state,
            },
        )
        self.db.flush()
        return self.svc._row_or_404(rid)

    # -- G7 / G12 evidence -------------------------------------------------------

    def set_own_so_number(self, value: str) -> None:
        """The identity `_claim_identity` reads for every row in this world - the
        PROJECT sales order's `autocount_doc_no`, which is what a real reconciled order
        carries once the AutoCount book names it."""
        self.db.execute(
            text("UPDATE " + P + ".sales_orders SET autocount_doc_no = :v WHERE id = :i"),
            {"v": value, "i": self.pso},
        )
        self.db.flush()

    def claiming_so(
        self, so_number: str, order_date: date, *, qty=100, qty_delivered=0,
        line_status="open", location=None,
    ) -> tuple[str, str]:
        """A CORE sales order + one line, standing in for the SO that CLAIMS a document
        line (G7). Returns `(sales_order_id, sales_order_line_id)` - the second is what
        `world.claim`'s `so_line_id` and `_dedication_for_target`'s reservation read."""
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
                "w": self.warehouses[location] if location else None,
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
        `resolved=True` (default) stamps `resolved_at`, exactly as a claim both of whose
        sides are already known would be; `resolved=False` leaves it NULL, so
        `order_link_service.resolve()` has something to do (AC-6.6) - its own query only
        examines rows where `resolved_at IS NULL`.

        Unqualified table name: `blank_session` pins `search_path` to the scratch `_scm`
        schema, so a hard-coded `scm.` prefix here would silently write the REAL schema
        instead (the trap `test_order_inquiry_links.py._projects` documents for the
        `projects` schema)."""
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

    def own_so_line(self, core_line_id) -> str:
        """A SECOND project sales-order line under the same PSO, reconciled to a CORE
        line - what `_claim_identity` resolves a row's own claim-write through
        (AC-6.9)."""
        lid = _uid()
        self.db.execute(
            text(
                "INSERT INTO " + P + ".sales_order_lines (id, company_id, "
                "project_sales_order_id, line_no, qty, unit_price, amount, product_id, "
                "core_sales_order_line_id, created_at) "
                "VALUES (:i, :c, :p, 2, 100, 0, 0, :prod, :core, now())"
            ),
            {
                "i": lid,
                "c": self.company_id,
                "p": self.pso,
                "prod": self.product,
                "core": core_line_id,
            },
        )
        self.db.flush()
        return lid


@pytest.fixture()
def world():
    global P
    with blank_session() as db:
        P = _projects(db)
        built = _World(db)
        with company_scope(db, frozenset({built.company_id})):
            yield built


# --------------------------------------------------------------------- AC-6.1


def test_ac_6_1_a_claim_reserves_its_full_qty_leaving_the_rest_free(world):
    """AC-6.1: PO 100, SO A 30 claimed -> 30 reserved / 70 free; +SO B 50 -> 80
    reserved / 20 free. A third, EARLIER-dated claim added last still decides
    `dedicated_to` - SO-date order, not write order."""
    lines = world.purchase_order("ZZT-PO-6-1", date(2026, 8, 1), [("BRW-IB", 100, SOON, "1")])
    line_id = lines[0]
    world.set_own_so_number("ZZT-SO-OWN")
    row = world.row("ORDER", 5)

    _, so_a_line = world.claiming_so("ZZT-SO-A", date(2026, 7, 1), qty=30)
    world.claim(
        so_number="ZZT-SO-A", po_number="ZZT-PO-6-1", so_line_id=so_a_line,
        po_line_id=line_id,
    )
    candidates = world.svc.po_candidates_for_row(row.id)
    assert candidates[0]["remaining"] == "70"
    assert candidates[0]["dedicated_to"] == "ZZT-SO-A"

    _, so_b_line = world.claiming_so("ZZT-SO-B", date(2026, 7, 5), qty=50)
    world.claim(
        so_number="ZZT-SO-B", po_number="ZZT-PO-6-1", so_line_id=so_b_line,
        po_line_id=line_id,
    )
    svc2 = ProjectOrderInquiryService(world.db)
    candidates = svc2.po_candidates_for_row(row.id)
    assert candidates[0]["remaining"] == "20"
    assert candidates[0]["dedicated_to"] == "ZZT-SO-A", "still the earlier of the two"

    # A THIRD claim, dated earlier than both but written last, must still decide
    # `dedicated_to` by its DATE - never by write order.
    _, so_c_line = world.claiming_so("ZZT-SO-C", date(2026, 6, 1), qty=5)
    world.claim(
        so_number="ZZT-SO-C", po_number="ZZT-PO-6-1", so_line_id=so_c_line,
        po_line_id=line_id,
    )
    svc3 = ProjectOrderInquiryService(world.db)
    candidates = svc3.po_candidates_for_row(row.id)
    assert candidates[0]["remaining"] == "15"
    assert candidates[0]["dedicated_to"] == "ZZT-SO-C"


# --------------------------------------------------------------------- AC-6.2


def test_ac_6_2_a_fully_claimed_line_is_never_auto_taken_by_a_different_so(world):
    """A line another SO has claimed in full shows `remaining == 0` and a
    `default_take` of `0` - the cascade's own preview - to a row it is not claimed by,
    however much that row needs."""
    lines = world.purchase_order("ZZT-PO-6-2", date(2026, 8, 1), [("BRW-IB", 40, SOON, "1")])
    line_id = lines[0]
    world.set_own_so_number("ZZT-SO-OWN")
    _, claim_line = world.claiming_so("ZZT-SO-X", date(2026, 7, 1), qty=40)
    world.claim(
        so_number="ZZT-SO-X", po_number="ZZT-PO-6-2", so_line_id=claim_line,
        po_line_id=line_id,
    )
    row = world.row("ORDER", 15)

    candidates = world.svc.po_candidates_for_row(row.id)
    assert candidates[0]["remaining"] == "0"
    assert candidates[0]["default_take"] == "0"
    assert candidates[0]["dedicated_to"] == "ZZT-SO-X"
    # Still LISTED, never dropped - a buyer may still name it by hand (AC-6.5).
    assert len(candidates) == 1


# --------------------------------------------------------------------- AC-6.3


def test_ac_6_3_a_settled_claiming_so_line_reserves_nothing_but_the_claim_stays(world):
    """A claiming SO line that has since been FULFILLED or CANCELLED reserves nothing -
    the reservation reads the SO line's LIVE outstanding, not what the claim's own
    quantity was when it was made - and the claim row itself is never deleted."""
    lines = world.purchase_order(
        "ZZT-PO-6-3", date(2026, 8, 1),
        [("BRW-IB", 40, SOON, "1"), ("BRW-IB", 25, SOON, "2")],
    )
    fulfilled_line, cancelled_line = lines
    world.set_own_so_number("ZZT-SO-OWN")

    _, fulfilled_so_line = world.claiming_so(
        "ZZT-SO-Y", date(2026, 7, 1), qty=40, line_status="fulfilled",
    )
    claim_id = world.claim(
        so_number="ZZT-SO-Y", po_number="ZZT-PO-6-3", so_line_id=fulfilled_so_line,
        po_line_id=fulfilled_line,
    )
    _, cancelled_so_line = world.claiming_so(
        "ZZT-SO-Z", date(2026, 7, 2), qty=25, line_status="cancelled",
    )
    world.claim(
        so_number="ZZT-SO-Z", po_number="ZZT-PO-6-3", so_line_id=cancelled_so_line,
        po_line_id=cancelled_line,
    )
    row = world.row("ORDER", 10)

    candidates = {c["po_line_id"]: c for c in world.svc.po_candidates_for_row(row.id)}
    assert candidates[fulfilled_line]["remaining"] == "40"
    assert candidates[fulfilled_line]["dedicated_to"] is None
    assert candidates[cancelled_line]["remaining"] == "25"
    assert candidates[cancelled_line]["dedicated_to"] is None

    still = world.db.execute(
        text("SELECT id FROM order_link_claim WHERE id = :i"), {"i": claim_id}
    ).scalar()
    assert str(still) == claim_id, "the claim row is never deleted, whatever it reserves"


# --------------------------------------------------------------------- AC-6.4


def test_ac_6_4_a_line_claimed_by_the_rows_own_so_ranks_first(world):
    """A line THIS row's own SO claims outranks even a same-location candidate: the
    BRW-IB line would ordinarily rank first by location tier alone, but the row's own
    claim on the sibling-location BRW-BB line ranks it first instead."""
    lines = world.purchase_order(
        "ZZT-PO-6-4", date(2026, 8, 1),
        [("BRW-IB", 50, SOON, "1"), ("BRW-BB", 50, SOON, "2")],
    )
    same_location_line, sibling_line = lines
    world.set_own_so_number("ZZT-SO-OWN")
    _, own_line = world.claiming_so("ZZT-SO-OWN", date(2026, 7, 1), qty=50)
    world.claim(
        so_number="ZZT-SO-OWN", po_number="ZZT-PO-6-4", so_line_id=own_line,
        po_line_id=sibling_line,
    )
    row = world.row("ORDER", 10, location="BRW-IB")

    candidates = world.svc.po_candidates_for_row(row.id)
    assert candidates[0]["po_line_id"] == sibling_line
    assert candidates[0]["tier"] == TIER_SIBLING
    assert candidates[0]["dedicated_to"] is None, "this row's OWN claim, not another SO's"
    assert candidates[1]["po_line_id"] == same_location_line


# --------------------------------------------------------------------- AC-6.6


def test_ac_6_6_an_unresolved_claim_dedicates_once_matched_by_po_number_and_item(world):
    """An unresolved claim - the purchase side not yet named, exactly what a claim
    written before the PO import looks like - dedicates nothing until
    `order_link_service.resolve()` matches it by (po_number, item_code), the same
    identity a real claim is written and matched under."""
    lines = world.purchase_order("ZZT-PO-6-6", date(2026, 8, 1), [("BRW-IB", 30, SOON, "1")])
    line_id = lines[0]
    world.set_own_so_number("ZZT-SO-OWN")
    _, so_line_id = world.claiming_so("ZZT-SO-CLAIM", date(2026, 7, 1), qty=30)
    world.claim(
        so_number="ZZT-SO-CLAIM", po_number="ZZT-PO-6-6", so_line_id=so_line_id,
        po_line_id=None, item_code=f"{MARKER}-7405", resolved=False,
    )
    row = world.row("ORDER", 10)

    before = world.svc.po_candidates_for_row(row.id)
    assert before[0]["remaining"] == "30", "unresolved on the purchase side: no reservation"

    result = order_link_service.resolve(world.db, so_numbers={"ZZT-SO-CLAIM"})
    assert result["resolved"] == 1

    svc2 = ProjectOrderInquiryService(world.db)
    after = svc2.po_candidates_for_row(row.id)
    assert after[0]["remaining"] == "0"
    assert after[0]["dedicated_to"] == "ZZT-SO-CLAIM"
    assert after[0]["po_line_id"] == line_id


def test_ac_6_6_an_spo_allocation_dedicates_via_spo_allocation_id_once_resolved(world):
    """The SPO side of the same rule: a claim naming an `SPO-` number resolves onto
    `spo_allocations.id`, not `purchase_order_lines.id`, and dedicates through that
    column."""
    world.spo_allocation("SPO-ZZT-6-6", "BRW", 20)
    world.set_own_so_number("ZZT-SO-OWN")
    _, so_line_id = world.claiming_so("ZZT-SO-SPO", date(2026, 7, 1), qty=20)
    world.claim(
        so_number="ZZT-SO-SPO", po_number="SPO-ZZT-6-6", so_line_id=so_line_id,
        spo_allocation_id=None, item_code=f"{MARKER}-7405", resolved=False,
    )
    row = world.row("ORDER_BACK", 10)

    order_link_service.resolve(world.db, so_numbers={"ZZT-SO-SPO"})

    svc2 = ProjectOrderInquiryService(world.db)
    candidates = svc2.po_candidates_for_row(row.id)
    spo_candidate = next(c for c in candidates if c["kind"] == "spo")
    assert spo_candidate["remaining"] == "0"
    assert spo_candidate["dedicated_to"] == "ZZT-SO-SPO"


# --------------------------------------------------------------------- AC-6.7


def test_ac_6_7_an_existing_link_keeps_netting_untouched_by_a_later_claim(world):
    """A link some earlier flow already wrote against a line keeps reducing
    `remaining` exactly as it always did; a G7 claim from ANOTHER SO written
    afterwards subtracts on top of it, and the earlier link's own row is never
    touched."""
    lines = world.purchase_order("ZZT-PO-6-7", date(2026, 8, 1), [("BRW-IB", 50, SOON, "1")])
    line_id = lines[0]
    world.set_own_so_number("ZZT-SO-OWN")

    existing_row = world.row("ORDER", 15)
    world.svc.place_on_po_allocations(
        existing_row.id, [{"po_line_id": line_id, "qty": Decimal("15")}],
        actor_user_id=None,
    )

    row = world.row("ORDER", 10)
    before = world.svc.po_candidates_for_row(row.id)[0]
    assert before["remaining"] == "35"

    _, claim_line = world.claiming_so("ZZT-SO-OTHER", date(2026, 7, 1), qty=10)
    world.claim(
        so_number="ZZT-SO-OTHER", po_number="ZZT-PO-6-7", so_line_id=claim_line,
        po_line_id=line_id,
    )

    svc2 = ProjectOrderInquiryService(world.db)
    after = svc2.po_candidates_for_row(row.id)[0]
    assert after["remaining"] == "25"

    still = world.db.execute(
        text("SELECT qty FROM " + P + ".order_inquiry_links WHERE po_line_id = :i"),
        {"i": line_id},
    ).scalar()
    assert Decimal(str(still)) == Decimal("15"), "the earlier link's own row is untouched"


# --------------------------------------------------------------------- AC-6.8


def test_ac_6_8_an_unclaimed_project_bin_line_is_never_auto_taken(world):
    """A line at a `segment = 'project'` warehouse nobody has claimed is refused to the
    automatic pass ("unattributed"), whatever its location tier would otherwise say -
    and its FULL quantity is still on offer for a manual link (`remaining` uncut)."""
    world.project_bin_warehouse("PRJ-BIN")
    lines = world.purchase_order("ZZT-PO-6-8", date(2026, 8, 1), [("PRJ-BIN", 40, SOON, "1")])
    line_id = lines[0]
    world.set_own_so_number("ZZT-SO-OWN")
    row = world.row("ORDER", 10, location="PRJ-BIN")

    candidates = world.svc._candidates_for_row(row)
    assert candidates[0]["target_id"] == line_id
    assert candidates[0]["cascadable"] is False
    assert candidates[0]["unattributed"] is True
    assert candidates[0]["dedicated_to"] is None
    assert candidates[0]["remaining"] == Decimal("40")

    dialog = world.svc.po_candidates_for_row(row.id)
    assert dialog[0]["unattributed"] is True
    assert dialog[0]["default_take"] == "0", "the cascade never touches it"


# --------------------------------------------------------------------- AC-6.9


def test_ac_6_9_a_manual_link_on_an_unclaimed_project_bin_line_writes_a_claim(world):
    """Joey links an unclaimed project-bin line by hand: `place_on_po_allocations`
    still allows it (override + audit, unaffected by G12's automatic-pass refusal),
    writes an `order_link_claim` naming this row's own SO, and the line thereafter
    reads dedicated to that SO for every OTHER viewer."""
    world.project_bin_warehouse("PRJ-BIN")
    lines = world.purchase_order("ZZT-PO-6-9", date(2026, 8, 1), [("PRJ-BIN", 40, SOON, "1")])
    line_id = lines[0]

    world.set_own_so_number("ZZT-SO-6-9")
    _, core_line_id = world.claiming_so("ZZT-SO-6-9", date(2026, 7, 1), qty=15)
    own_line = world.own_so_line(core_line_id)
    row = world.row("ORDER", 15, location="PRJ-BIN", so_line=own_line)

    before = world.svc._candidates_for_row(row)
    assert before[0]["unattributed"] is True
    assert before[0]["cascadable"] is False

    world.svc.place_on_po_allocations(
        row.id, [{"po_line_id": line_id, "qty": Decimal("15")}], actor_user_id=None,
    )

    written = world.db.execute(
        text("SELECT so_number FROM order_link_claim WHERE po_line_id = :i"), {"i": line_id}
    ).scalar()
    assert written == "ZZT-SO-6-9"

    svc2 = ProjectOrderInquiryService(world.db)
    reserved, dedicated_to, own_claim = svc2._dedication_for_target(
        line_id, own_so_number="ZZT-SO-SOMEBODY-ELSE",
    )
    assert dedicated_to == "ZZT-SO-6-9"
    assert own_claim is False
    assert reserved == Decimal("15")

    # And read back against ITS OWN identity, the line is its own claim, not a
    # dedication to somebody else - the same distinction AC-6.4 ranks on.
    reserved_own, dedicated_own, own_claim_own = svc2._dedication_for_target(
        line_id, own_so_number="ZZT-SO-6-9",
    )
    assert own_claim_own is True
    assert dedicated_own is None
    assert reserved_own == Decimal("0")


# --------------------------------------------------------------------- AC-6.10


def test_ac_6_10_a_pool_destination_lines_candidacy_is_unchanged_by_g12(world):
    """A line at an ordinary POOL warehouse (no `segment = 'project'`) is cascadable
    exactly as it always was - G12 narrows nothing here."""
    lines = world.purchase_order("ZZT-PO-6-10", date(2026, 8, 1), [("BRW", 40, SOON, "1")])
    line_id = lines[0]
    world.set_own_so_number("ZZT-SO-OWN")
    row = world.row("ORDER", 10, location="BRW-IB")

    candidates = world.svc._candidates_for_row(row)
    assert candidates[0]["target_id"] == line_id
    assert candidates[0]["cascadable"] is True
    assert candidates[0]["unattributed"] is False
    assert candidates[0]["dedicated_to"] is None
    assert candidates[0]["remaining"] == Decimal("40")
