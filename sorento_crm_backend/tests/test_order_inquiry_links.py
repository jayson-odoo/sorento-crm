"""Section 3.I - one order inquiry row, many links.

`PLAN-scm-cs-planning-uat.md` section 3.I, `PLAN-scm-purchasing-uat-journey.md` section 4b,
UAC AC-I1 to AC-I10.

`blank_session` throughout, not `pg_session`: the walk this file tests is ranked by the
PURCHASE ORDER BOOK, and the shared local database holds the captain's real 80,000-line
one, so a fixture line for a real product would be judged against thousands of neighbours
and the assertions would move whenever somebody re-uploaded a book. A scratch schema is the
only substrate where "these are the four open lines for this product" is a sentence a test
may say out loud.

The one shape worth knowing before reading: every assertion about ORDER is about a row that
may name a purchase order line and nothing else, and every assertion about ORDER BACK is
about the ONE verb that may also name an `spo_allocations` row (captain, 25 August 2026).
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.services.project_order_inquiry_service import (
    TIER_ELSEWHERE,
    TIER_POOL,
    TIER_SAME_GROUP,
    TIER_SAME_LOCATION,
    TIER_SIBLING,
    ProjectOrderInquiryService,
    link_location_tier,
)

from ._pg_fixture import blank_session

MARKER = "ZZT-LINKS"

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "421_order_inquiry_links.py"
)

#: Relative to today, so an open SPO allocation does not quietly stop being one a few days
#: after this file was written (`spo_supply.open_incoming_clauses` reads the book, not the
#: clock, but the fixture's own dates are read by the walk's ordering).
SOON = date.today() + timedelta(days=30)


def _migration():
    spec = importlib.util.spec_from_file_location("zzt_migration_421", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _uid() -> str:
    return str(uuid.uuid4())


#: The `projects` schema THIS session writes to, bound once by the `world` fixture. A
#: module global rather than a parameter on twenty call sites: `blank_session` caches one
#: scratch schema for the whole run, so there is exactly one answer.
P = "projects"


def _projects(db) -> str:
    """Where `projects.*` lives under THIS session.

    `blank_session` builds `<scratch>_projects` and puts it on the search_path, but a
    hard-coded `projects.order_inquiry_rows` inside a `text()` statement is resolved by
    NAME and reaches the REAL schema - writing live data while the test believes it is
    isolated. The same trap migration 420 and 421 carry `_schema` for.
    """
    current = db.execute(text("select current_schema()")).scalar()
    return "projects" if current in (None, "public") else f'"{current}_projects"'


# --------------------------------------------------------------------------- the world


class _World:
    """Everything one test needs, named the way the fixture sheet names it."""

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
        for code in ("BRW-IB", "DC1-IB", "BRW-BB"):
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

    def row(self, verb: str, qty, *, location="BRW-IB", cited=None, so_line=True):
        rid = _uid()
        self.db.execute(
            text(
                "INSERT INTO " + P + ".order_inquiry_rows (id, company_id, "
                "order_inquiry_id, so_line_id, item_code, qty, verb, stock_location, "
                "cited_document, state, redirected_to_pool, created_at) "
                "VALUES (:i, :c, :inq, :l, :code, :q, :v, :loc, :cd, 'raised', false, "
                "now())"
            ),
            {
                "i": rid,
                "c": self.company_id,
                "inq": self.inquiry,
                "l": self.line if so_line else None,
                "code": f"{MARKER}-7405",
                "q": Decimal(str(qty)),
                "v": verb,
                "loc": location,
                "cd": cited,
            },
        )
        self.db.flush()
        return self.svc._row_or_404(rid)


@pytest.fixture()
def world():
    global P
    with blank_session() as db:
        P = _projects(db)
        built = _World(db)
        with company_scope(db, frozenset({built.company_id})):
            yield built


# ------------------------------------------------------------------- the tier rule (Q5)


def test_link_location_tier_ranks_the_four_tiers_and_the_pool_sub_rank():
    """Q5, ruled 25 August 2026: "same location, same group location, pool, then sibling
    location". The sub-rank exists for the pool tier alone and puts the row's OWN site
    pool ahead of the others - "BRW, then the other pools" - which one integer cannot
    say."""
    pools = {"BRW", "MWH", "DC1", "WH3", "RSW"}

    assert link_location_tier("BRW-IB", "BRW-IB", pools) == (TIER_SAME_LOCATION, 0)
    assert link_location_tier("BRW-IB", "DC1-IB", pools) == (TIER_SAME_GROUP, 0)
    assert link_location_tier("BRW-IB", "MWH-IB", pools) == (TIER_SAME_GROUP, 0)
    assert link_location_tier("BRW-IB", "BRW", pools) == (TIER_POOL, 0)
    assert link_location_tier("BRW-IB", "MWH", pools) == (TIER_POOL, 1)
    assert link_location_tier("BRW-IB", "BRW-BB", pools) == (TIER_SIBLING, 0)
    assert link_location_tier("BRW-IB", "RSW-QQ", pools) == (TIER_ELSEWHERE, 0)


def test_link_location_tier_ranks_nothing_when_either_side_names_no_location():
    """A row that names no location can be ranked by nothing, so every candidate is the
    last tier and the DATES decide - honest, rather than claiming a fit nobody stated."""
    pools = {"BRW"}
    assert link_location_tier(None, "BRW-IB", pools) == (TIER_ELSEWHERE, 0)
    assert link_location_tier("BRW-IB", None, pools) == (TIER_ELSEWHERE, 0)


def test_a_pool_is_decided_by_the_foreign_key_not_by_the_shape_of_the_code():
    """Every pool on the live book happens to be a plain site code with no hyphen, and
    that is a naming convention the data does not enforce. A code nobody points at is a
    sibling location, whatever it looks like."""
    assert link_location_tier("BRW-IB", "BRW", set()) == (TIER_SIBLING, 0)


# -------------------------------------------------- the candidate walk (AC-I2, AC-I10)


def _two_purchase_orders(world) -> dict:
    """The fixture sheet's own shape: an APRIL order whose BRW-IB line is late, and an
    AUGUST order whose BRW-IB line arrives EARLIER. The April one must still win, because
    the cascade orders on the purchase order's own issue date first (Q7)."""
    april = world.purchase_order(
        "202604-S0083",
        date(2026, 4, 28),
        [
            ("BRW-BB", 27, date(2026, 9, 15), "7"),
            ("BRW", 165, date(2026, 5, 10), "5"),
            ("DC1-IB", 40, date(2026, 10, 1), "3"),
            ("BRW-IB", 25, date(2026, 8, 19), "1"),
        ],
    )
    august = world.purchase_order(
        "202608-S0015", date(2026, 8, 7), [("BRW-IB", 500, date(2026, 6, 1), "1")]
    )
    return {"april": april, "august": august}


def test_candidates_rank_by_location_tier_then_by_the_purchase_orders_own_date(world):
    """AC-I2 and AC-I10. Within a document BRW-IB ranks before DC1-IB, before BRW, before
    BRW-BB; ACROSS documents the April order's BRW-IB line beats the August one's even
    though the August line is promised eleven weeks earlier (Q7: "PO document date first,
    then line expected date"). Location NEVER filters a candidate out - all five lines are
    offered."""
    _two_purchase_orders(world)
    row = world.row("ORDER", 8)

    candidates = world.svc.po_candidates_for_row(row.id)

    assert [(c["po_number"], c["location"], c["tier"]) for c in candidates] == [
        ("202604-S0083", "BRW-IB", TIER_SAME_LOCATION),
        ("202608-S0015", "BRW-IB", TIER_SAME_LOCATION),
        ("202604-S0083", "DC1-IB", TIER_SAME_GROUP),
        ("202604-S0083", "BRW", TIER_POOL),
        ("202604-S0083", "BRW-BB", TIER_SIBLING),
    ]


def test_a_candidate_states_both_dates_and_its_line_label(world):
    """AC-I10: "Candidate list shows both dates". A list that showed one could not be
    checked against the rule that orders on the other."""
    _two_purchase_orders(world)
    row = world.row("ORDER", 8)

    first = world.svc.po_candidates_for_row(row.id)[0]

    assert first["issue_date"] == date(2026, 4, 28)
    assert first["expected_date"] == date(2026, 8, 19)
    assert first["line_label"] == "L1"
    assert first["default_take"] == "8", "the cascade's own preview, by the same walk"


def test_an_order_row_is_never_offered_an_spo_allocation(world):
    """Captain, 25 August: "Only for order back, we link to SPO allocations." A normal
    ORDER is a NEW purchase and goes on a purchase order."""
    _two_purchase_orders(world)
    world.spo_allocation("SPO-2026/08-0061", "BRW-IB", 332)
    row = world.row("ORDER", 8)

    assert all(c["kind"] == "po" for c in world.svc.po_candidates_for_row(row.id))


def test_an_order_back_walks_its_cited_document_first_then_spo_then_purchase_orders(world):
    """AC-I2 + part 2 section 4b, against the fixture's SRTWCY7405-PJ row: the document CS
    cited comes before everything, then SPO allocations, then purchase order lines."""
    _two_purchase_orders(world)
    world.spo_allocation("SPO-2026/08-0061", "BRW-IB", 332, line_number=2)
    row = world.row("ORDER_BACK", 10, cited="SPO-2026/08-0061")

    candidates = world.svc.po_candidates_for_row(row.id)

    assert (candidates[0]["kind"], candidates[0]["po_number"]) == (
        "spo",
        "SPO-2026/08-0061",
    )
    assert candidates[0]["cited"] is True
    assert candidates[0]["line_label"] == "L2"
    assert [c["kind"] for c in candidates[1:]] == ["po"] * 5


def test_a_cited_purchase_order_beats_an_uncited_one_of_the_same_tier(world):
    """The citation is the most specific thing anybody knows about the row, so it is the
    OUTERMOST key - ahead of the tier and ahead of both dates."""
    _two_purchase_orders(world)
    row = world.row("ORDER_BACK", 8, cited="202608-S0015")

    candidates = world.svc.po_candidates_for_row(row.id)

    assert candidates[0]["po_number"] == "202608-S0015"
    assert candidates[0]["cited"] is True


# ------------------------------------------------------------- linking (AC-I6, AC-I7)


def test_the_cascade_links_across_two_lines_and_never_splits_the_row(world):
    """AC-I6, the captain on SO414285: "1 line here should correspond to 1 line in sales
    order, so 1 line can be placed by multiple PO and SPO". 8 needed, 5 on the first line
    and 3 on the second - ONE row, two links, and the row keeps its 8."""
    orders = _two_purchase_orders(world)
    first, second = orders["april"][3], orders["august"][0]
    row = world.row("ORDER", 8)

    world.svc.place_on_po_allocations(
        row.id,
        [
            {"po_line_id": first, "qty": Decimal("5")},
            {"po_line_id": second, "qty": Decimal("3")},
        ],
        actor_user_id=None,
    )
    world.db.flush()
    world.db.refresh(row)

    body = world.svc.serialize_rows([row])[0]
    assert body["qty"] == "8"
    assert body["state"] == "placed"
    assert body["linked_qty"] == "8"
    assert [(link["qty"], link["document"]) for link in body["links"]] == [
        ("5", "202604-S0083"),
        ("3", "202608-S0015"),
    ]
    assert (
        world.db.execute(
            text(
                "SELECT count(*) FROM " + P + ".order_inquiry_rows "
                "WHERE order_inquiry_id = :i"
            ),
            {"i": world.inquiry},
        ).scalar()
        == 1
    )


def test_a_part_covered_row_reads_partly_linked_and_keeps_its_quantity(world):
    """AC-I7. 8 needed, 5 linked: the row is PARTLY LINKED at 8, and the dialog opens
    looking for the 3 nobody has covered."""
    orders = _two_purchase_orders(world)
    row = world.row("ORDER", 8)

    world.svc.place_on_po_allocations(
        row.id, [{"po_line_id": orders["april"][3], "qty": Decimal("5")}], actor_user_id=None
    )
    world.db.flush()
    world.db.refresh(row)

    assert row.state == "partly_linked"
    assert row.qty == Decimal("8")
    assert world.svc._unlinked_need(row) == Decimal("3")
    assert row.po_ref == "202604-S0083", "the first link is the derived display"


def test_auto_link_finishes_a_partly_linked_row_and_a_second_pass_links_nothing(world):
    """The cascade's idempotence, which the three automatic triggers all rely on - and
    the widening the links table brought: a PARTLY LINKED row is in scope, because it is
    exactly the row a fresh purchase order should finish."""
    orders = _two_purchase_orders(world)
    row = world.row("ORDER", 8)
    world.svc.place_on_po_allocations(
        row.id, [{"po_line_id": orders["april"][3], "qty": Decimal("5")}], actor_user_id=None
    )
    world.db.flush()

    first = world.svc.auto_place_for_products(None, actor_user_id=None, trigger="zzt")
    world.db.flush()
    world.db.refresh(row)
    assert first["placed_rows"] == 1
    assert row.state == "placed"

    second = world.svc.auto_place_for_products(None, actor_user_id=None, trigger="zzt")
    assert second["placed_rows"] == 0


def test_an_order_row_naming_an_spo_allocation_is_refused_in_the_buyers_own_words(world):
    """Part 2 section 4b, held at the write and not only at the read: the candidate list
    never offers one, and a caller that names one anyway is told why."""
    _two_purchase_orders(world)
    allocation = world.spo_allocation("SPO-2026/08-0061", "BRW-IB", 332)
    row = world.row("ORDER", 8)

    from app.services.error_handler import AppException

    with pytest.raises(AppException) as caught:
        world.svc.place_on_po_allocations(
            row.id,
            [{"spo_allocation_id": allocation, "qty": Decimal("8")}],
            actor_user_id=None,
        )

    assert "order_inquiry_spo_not_order_back" in str(caught.value)


def test_an_order_back_may_link_to_an_spo_allocation(world):
    """The other half of the same rule: the one verb that may."""
    allocation = world.spo_allocation("SPO-2026/08-0061", "BRW-IB", 332)
    row = world.row("ORDER_BACK", 10, cited="SPO-2026/08-0061")

    world.svc.place_on_po_allocations(
        row.id,
        [{"spo_allocation_id": allocation, "qty": Decimal("10")}],
        actor_user_id=None,
    )
    world.db.flush()
    world.db.refresh(row)

    body = world.svc.serialize_rows([row])[0]
    assert row.state == "placed"
    assert body["links"][0]["kind"] == "spo"
    assert body["links"][0]["document"] == "SPO-2026/08-0061"


def test_an_order_back_whose_only_cover_is_an_spo_still_offers_a_link(world):
    """The flag the row action reads. With no purchase order in the world at all, an
    ORDER BACK row still has somewhere to go, and a flag that counted purchase orders
    alone hid the Link button on the one row the feature was built for."""
    world.spo_allocation("SPO-2026/08-0061", "BRW-IB", 332)
    back = world.row("ORDER_BACK", 10)
    plain = world.row("ORDER", 10)

    candidates = world.svc.link_candidate_products([world.product])

    assert candidates["po"] == set()
    assert candidates["spo"] == {world.product}
    assert (
        world.svc.has_link_candidate(back.verb, world.product, candidates) is True
    )
    assert (
        world.svc.has_link_candidate(plain.verb, world.product, candidates) is False
    )


def test_unlinking_one_link_leaves_the_others_and_the_row_partly_linked(world):
    """A row sitting on two documents can give ONE back. Before the child table, Unplace
    was the only move and it took the whole placement with it."""
    orders = _two_purchase_orders(world)
    row = world.row("ORDER", 8)
    world.svc.place_on_po_allocations(
        row.id,
        [
            {"po_line_id": orders["april"][3], "qty": Decimal("5")},
            {"po_line_id": orders["august"][0], "qty": Decimal("3")},
        ],
        actor_user_id=None,
    )
    world.db.flush()

    links = world.svc._links_of(row.id)
    world.svc.unplace(row.id, actor_user_id=None, link_id=links[1].id)
    world.db.refresh(row)

    assert row.state == "partly_linked"
    assert [link.qty for link in world.svc._links_of(row.id)] == [Decimal("5.0000")]

    world.svc.unplace(row.id, actor_user_id=None)
    world.db.refresh(row)
    assert row.state == "raised"
    assert world.svc._links_of(row.id) == []
    assert row.po_ref is None and row.po_line_id is None


def test_a_link_never_claims_quantity_another_row_already_holds(world):
    """`remaining` nets every OTHER link on the same line, which is what stops two rows
    being pointed at the same purchase-order quantity."""
    orders = _two_purchase_orders(world)
    line = orders["april"][3]  # BRW-IB, 25 ordered
    first = world.row("ORDER", 20)
    world.svc.place_on_po_allocations(
        first.id, [{"po_line_id": line, "qty": Decimal("20")}], actor_user_id=None
    )
    world.db.flush()

    second = world.row("ORDER", 20)
    candidate = next(
        c
        for c in world.svc.po_candidates_for_row(second.id)
        if c["po_line_id"] == line
    )

    assert candidate["remaining"] == "5"
    assert candidate["already_tagged"] == "20"


# ------------------------------------------------------------ the worklist and SO detail


def test_the_linked_filter_answers_po_spo_and_none(world):
    """AC-I5. WHERE a row is linked is a different question from what STATE it is in: a
    buyer asking "what have I still not put on anything" wants `none`."""
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    orders = _two_purchase_orders(world)
    allocation = world.spo_allocation("SPO-2026/08-0061", "BRW-IB", 332)

    on_po = world.row("ORDER", 8)
    world.svc.place_on_po_allocations(
        on_po.id, [{"po_line_id": orders["april"][3], "qty": Decimal("8")}], actor_user_id=None
    )
    on_spo = world.row("ORDER_BACK", 10)
    world.svc.place_on_po_allocations(
        on_spo.id, [{"spo_allocation_id": allocation, "qty": Decimal("10")}], actor_user_id=None
    )
    unlinked = world.row("ORDER", 4)
    world.db.flush()

    worklist = OrderInquiryWorklistService(world.db)

    def ids(**filters):
        return {
            entry["id"] for entry in worklist.list_rows(limit=100, **filters)["data"]
        }

    assert on_po.id in ids(linked="po") and on_spo.id not in ids(linked="po")
    assert on_spo.id in ids(linked="spo") and on_po.id not in ids(linked="spo")
    assert unlinked.id in ids(linked="none")
    assert {on_po.id, on_spo.id} & ids(linked="none") == set()


def test_the_worklist_row_carries_its_links_and_the_flow_reads_them(world):
    """"Taken from PO" and "Remaining" come off the LINKS now: the pair used to be "sum
    the placed siblings" against "sum the raised siblings", which was only true because
    the cascade had split the line into two rows."""
    from app.services.order_inquiry_worklist_service import OrderInquiryWorklistService

    orders = _two_purchase_orders(world)
    row = world.row("ORDER", 19)
    world.svc.place_on_po_allocations(
        row.id, [{"po_line_id": orders["april"][3], "qty": Decimal("5")}], actor_user_id=None
    )
    world.db.flush()

    entry = next(
        item
        for item in OrderInquiryWorklistService(world.db).list_rows(limit=100)["data"]
        if item["id"] == row.id
    )

    assert entry["linked_qty"] == "5"
    assert entry["taken_from_po"] == "5"
    assert entry["remaining_open"] == "14"
    assert [link["document"] for link in entry["links"]] == ["202604-S0083"]


def test_the_sales_order_detail_states_where_each_lines_buy_sits(world):
    """AC-I9, on the wire. `None` when no inquiry row covers the line at all, `[]` when
    one does and holds no link: "nobody was told" and "told, nothing linked" are different
    answers and the column prints each in its own words."""
    from app.models.order import SalesOrder
    from app.services.scm.sales_order_service import SalesOrderService

    orders = _two_purchase_orders(world)
    core_so, core_line = _uid(), _uid()
    world.db.execute(
        text(
            "INSERT INTO customers (id, company_id, customer_code, customer_name, "
            "is_active) VALUES (:i, :c, :code, :code, true)"
        ),
        {"i": (customer := _uid()), "c": world.company_id, "code": f"{MARKER}-CUST"},
    )
    world.db.execute(
        text(
            "INSERT INTO sales_orders (id, company_id, so_number, customer_id, status, "
            "demand_class, order_date) "
            "VALUES (:i, :c, :n, :cu, 'open', 'project', :d)"
        ),
        {
            "i": core_so,
            "c": world.company_id,
            "n": f"{MARKER}-SO",
            "cu": customer,
            "d": date(2026, 8, 1),
        },
    )
    world.db.execute(
        text(
            "INSERT INTO sales_order_lines (id, company_id, sales_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_required, qty_delivered, line_status, "
            "purchasing_status, required_date) "
            "VALUES (:i, :c, :so, :p, :w, 8, 8, 0, 'open', 'pending', :d)"
        ),
        {
            "i": core_line,
            "c": world.company_id,
            "so": core_so,
            "p": world.product,
            "w": world.warehouses["BRW-IB"],
            "d": date(2026, 9, 1),
        },
    )
    world.db.execute(
        text(
            "UPDATE " + P + ".sales_order_lines SET core_sales_order_line_id = :core "
            "WHERE id = :i"
        ),
        {"core": core_line, "i": world.line},
    )
    row = world.row("ORDER", 8)
    world.svc.place_on_po_allocations(
        row.id, [{"po_line_id": orders["april"][3], "qty": Decimal("5")}], actor_user_id=None
    )
    world.db.flush()

    order = world.db.query(SalesOrder).filter(SalesOrder.id == core_so).first()
    body = SalesOrderService(world.db).serialize(order, line_planning=True)

    linked = body["lines"][0]["linked_to"]
    assert linked == [
        {
            "kind": "po",
            "document": "202604-S0083",
            "line_label": "L1",
            "qty": "5",
            "location": "BRW-IB",
            "expected_date": "2026-08-19",
        }
    ]


# --------------------------------------------------------- migration 421's data half


def _placed_row(world, qty, *, po_line=None, document=None, created="now()"):
    rid = _uid()
    world.db.execute(
        text(
            "INSERT INTO " + P + ".order_inquiry_rows (id, company_id, order_inquiry_id, "
            "so_line_id, item_code, qty, verb, po_ref, po_line_id, state, "
            "redirected_to_pool, created_at) "
            f"VALUES (:i, :c, :inq, :l, :code, :q, 'ORDER', :ref, :pl, 'placed', false, "
            f"{created})"
        ),
        {
            "i": rid,
            "c": world.company_id,
            "inq": world.inquiry,
            "l": world.line,
            "code": f"{MARKER}-7405",
            "q": Decimal(str(qty)),
            "ref": document,
            "pl": po_line,
        },
    )
    world.db.flush()
    return rid


def test_migration_421_writes_one_link_per_placed_row_and_clears_the_scalar(world):
    """AC-I8, first step. The row's own quantity IS the fragment's allocation, which is
    what a split row was."""
    migration = _migration()
    line = world.purchase_order(
        "202607-S0105", date(2026, 7, 29), [("BRW-BB", 20, date(2026, 8, 3), "3")]
    )[0]
    _placed_row(world, 5, po_line=line, document="202607-S0105")

    written = migration.links_from_placed_rows(world.db.connection())

    assert written == 1
    assert world.db.execute(
        text(
            "SELECT qty, document FROM " + P + ".order_inquiry_links "
            "WHERE po_line_id = :l"
        ),
        {"l": line},
    ).fetchall() == [(Decimal("5.0000"), "202607-S0105")]
    assert (
        world.db.execute(
            text(
                "SELECT count(*) FROM " + P + ".order_inquiry_rows "
                "WHERE order_inquiry_id = :i AND po_line_id IS NOT NULL"
            ),
            {"i": world.inquiry},
        ).scalar()
        == 0
    ), "the scalar stops being written the moment the links carry it"


def test_migration_421_merges_a_split_pair_into_one_row_with_two_links(world):
    """AC-I8, the shape the captain saw on SO414285: M310-CR-PJ's 8 is two rows, 5 + 3 on
    two lines of 202607-S0105, and it must come back as ONE instruction."""
    migration = _migration()
    lines = world.purchase_order(
        "202607-S0105",
        date(2026, 7, 29),
        [("BRW-BB", 20, date(2026, 8, 3), "3"), ("BRW-BB", 20, date(2026, 8, 3), "7")],
    )
    _placed_row(
        world, 5, po_line=lines[0], document="202607-S0105",
        created="now() - interval '2 hours'",
    )
    _placed_row(
        world, 3, po_line=lines[1], document="202607-S0105",
        created="now() - interval '1 hour'",
    )
    bind = world.db.connection()
    migration.links_from_placed_rows(bind)

    merged = migration.merge_split_rows(bind)
    migration.refresh_link_states(bind)

    assert merged == {"merged_groups": 1, "rows_removed": 1}
    rows = world.db.execute(
        text(
            "SELECT qty, state, po_ref FROM " + P + ".order_inquiry_rows "
            "WHERE order_inquiry_id = :i"
        ),
        {"i": world.inquiry},
    ).fetchall()
    assert rows == [(Decimal("8.0000"), "placed", "202607-S0105")]
    assert (
        world.db.execute(
            text("SELECT count(*) FROM " + P + ".order_inquiry_links")
        ).scalar()
        == 2
    )


def test_migration_421_is_idempotent(world):
    """The shared dev database converges through `create_all` rather than `upgrade`, so
    every step has to be a no-op the second time it is asked."""
    migration = _migration()
    line = world.purchase_order(
        "202607-S0105", date(2026, 7, 29), [("BRW-BB", 20, date(2026, 8, 3), "3")]
    )[0]
    _placed_row(world, 5, po_line=line, document="202607-S0105")
    bind = world.db.connection()
    migration.links_from_placed_rows(bind)
    migration.merge_split_rows(bind)
    migration.refresh_link_states(bind)

    assert migration.links_from_placed_rows(bind) == 0
    assert migration.merge_split_rows(bind) == {"merged_groups": 0, "rows_removed": 0}
    assert (
        world.db.execute(
            text("SELECT count(*) FROM " + P + ".order_inquiry_links")
        ).scalar()
        == 1
    )


def test_migration_421_restates_a_part_covered_row_as_partly_linked(world):
    """The state is DERIVED from the links, never carried over: a row whose links cover
    part of it is the middle the table made expressible."""
    migration = _migration()
    line = world.purchase_order(
        "202607-S0105", date(2026, 7, 29), [("BRW-BB", 20, date(2026, 8, 3), "3")]
    )[0]
    row_id = _placed_row(world, 8, po_line=line, document="202607-S0105")
    bind = world.db.connection()
    migration.links_from_placed_rows(bind)
    world.db.execute(
        text("UPDATE " + P + ".order_inquiry_links SET qty = 5 WHERE row_id = :r"),
        {"r": row_id},
    )

    migration.refresh_link_states(bind)

    assert world.db.execute(
        text("SELECT state FROM " + P + ".order_inquiry_rows WHERE id = :i"),
        {"i": row_id},
    ).scalar() == "partly_linked"


def test_migration_421_downgrade_splits_the_row_back_one_row_per_link(world):
    """A merge cannot be undone row for row, but the SHAPE the pre-421 code reads can be
    rebuilt exactly: one placed row per link, at that link's quantity and line."""
    migration = _migration()
    lines = world.purchase_order(
        "202607-S0105",
        date(2026, 7, 29),
        [("BRW-BB", 20, date(2026, 8, 3), "3"), ("BRW-BB", 20, date(2026, 8, 3), "7")],
    )
    _placed_row(
        world, 5, po_line=lines[0], document="202607-S0105",
        created="now() - interval '2 hours'",
    )
    _placed_row(
        world, 3, po_line=lines[1], document="202607-S0105",
        created="now() - interval '1 hour'",
    )
    bind = world.db.connection()
    migration.links_from_placed_rows(bind)
    migration.merge_split_rows(bind)
    migration.refresh_link_states(bind)

    migration.split_rows_from_links(bind)

    assert sorted(
        world.db.execute(
            text(
                "SELECT qty, state, po_ref FROM " + P + ".order_inquiry_rows "
                "WHERE order_inquiry_id = :i ORDER BY qty"
            ),
            {"i": world.inquiry},
        ).fetchall()
    ) == [
        (Decimal("3.0000"), "placed", "202607-S0105"),
        (Decimal("5.0000"), "placed", "202607-S0105"),
    ]


def test_migration_421_round_trips_an_spo_link_through_spo_ref(world):
    """An SPO link has no `po_line_id` to restore, so the pre-421 shape for it is the
    row's own `spo_ref` - the only column that ever named a shipping order. The upgrade
    reads it back, so downgrade-then-upgrade is a round trip rather than a loss."""
    migration = _migration()
    allocation = world.spo_allocation("SPO-2026/08-0061", "BRW-IB", 332)
    row = world.row("ORDER_BACK", 10, cited="SPO-2026/08-0061")
    world.svc.place_on_po_allocations(
        row.id,
        [{"spo_allocation_id": allocation, "qty": Decimal("10")}],
        actor_user_id=None,
    )
    world.db.flush()
    bind = world.db.connection()

    migration.split_rows_from_links(bind)
    world.db.execute(text("DELETE FROM " + P + ".order_inquiry_links"))
    assert world.db.execute(
        text("SELECT spo_ref, po_ref FROM " + P + ".order_inquiry_rows WHERE id = :i"),
        {"i": row.id},
    ).fetchone() == ("SPO-2026/08-0061", None)

    assert migration.links_from_placed_rows(bind) == 1
    restored = world.db.execute(
        text(
            "SELECT spo_allocation_id, document FROM " + P + ".order_inquiry_links "
            "WHERE row_id = :r"
        ),
        {"r": row.id},
    ).fetchone()
    assert (str(restored[0]), restored[1]) == (allocation, "SPO-2026/08-0061")


def test_migration_421_never_turns_an_already_inbound_coverage_note_into_a_link(world):
    """`spo_ref` is also the coverage reference the netting engine writes on an ALREADY
    INBOUND row - a note about what already covers the quantity, never a placement.
    Turning one into a link would have retired demand nobody linked."""
    migration = _migration()
    world.spo_allocation("SPO-2026/08-0061", "BRW-IB", 332)
    rid = _uid()
    world.db.execute(
        text(
            "INSERT INTO " + P + ".order_inquiry_rows (id, company_id, order_inquiry_id, "
            "so_line_id, item_code, qty, verb, spo_ref, state, redirected_to_pool, "
            "created_at) VALUES (:i, :c, :inq, :l, :code, 10, 'ALREADY_INBOUND', "
            "'SPO-2026/08-0061', 'raised', false, now())"
        ),
        {
            "i": rid,
            "c": world.company_id,
            "inq": world.inquiry,
            "l": world.line,
            "code": f"{MARKER}-7405",
        },
    )
    world.db.flush()

    assert migration.links_from_placed_rows(world.db.connection()) == 0
    assert world.db.execute(
        text("SELECT spo_ref FROM " + P + ".order_inquiry_rows WHERE id = :i"), {"i": rid}
    ).scalar() == "SPO-2026/08-0061"


# ------------------------------------------------- the order back through a re-confirm


def test_a_partly_linked_order_back_is_netted_half_on_the_next_revision(world):
    """The hole a borrow left is re-judged on every confirmation, and a row that already
    has PART of it on a document must not be asked for that part a second time.

    Before this, the netting recognised `actioned` and `placed` and read a partly linked
    row as untouched: the whole hole was raised again on top of a row already half
    covered, so purchasing was told to buy the covered quantity twice. The row is now
    shrunk to what is linked and only the uncovered remainder is re-raised.
    """
    orders = _two_purchase_orders(world)
    row = world.row("ORDER_BACK", 15, location="BRW-BB")
    world.svc.place_on_po_allocations(
        row.id,
        [{"po_line_id": orders["april"][0], "qty": Decimal("10")}],
        actor_user_id=None,
    )
    world.db.flush()
    world.db.refresh(row)
    assert row.state == "partly_linked"

    class _Decision:
        id = None
        revision_no = 2

    raised = world.svc._raise_borrow_shortfalls(
        type("O", (), {"company_id": world.company_id})(),
        type("I", (), {"id": world.inquiry})(),
        _Decision(),
        [
            {
                "item_code": f"{MARKER}-7405",
                "stock_location": "BRW-BB",
                "qty": Decimal("15"),
                "required_date": None,
                "line": None,
                "note": "hole",
            }
        ],
    )
    world.db.flush()
    world.db.refresh(row)

    assert raised == 1, "only the 5 nobody covered is raised again"
    assert row.state == "placed", "the covered part stands, at the covered quantity"
    assert row.qty == Decimal("10")
    fresh = (
        world.db.execute(
            text(
                "SELECT qty FROM " + P + ".order_inquiry_rows "
                "WHERE order_inquiry_id = :i AND state = 'raised' AND verb = 'ORDER_BACK'"
            ),
            {"i": world.inquiry},
        ).fetchall()
    )
    assert [entry[0] for entry in fresh] == [Decimal("5.0000")]
