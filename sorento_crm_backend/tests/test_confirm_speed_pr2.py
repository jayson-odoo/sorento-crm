"""CONFIRM-SPEED-PR2 (UAC P1-P4): the same answers, fewer reads.

P1  `_oi_placements` keeps returning exactly the rows the one-join statement returned (the
    oracle below is that statement, copied verbatim).                         GUARD (green now)
P3  `assignments_for` over several products equals one call per product.     GUARD (green now)
P2  A board GET reads the stock-debt assignment at most twice.                 RED now
P4  A placement pass reads a project line's identity once per line and an
    inquiry's SO number once per inquiry, and writes the same links.           RED now

Postgres only, every FK target seeded here (the CI database is empty).
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.models.base import company_scope
from app.models.order import SalesOrderLine
from app.models.procurement import SPOAllocation
from app.models.project_so import (
    INQUIRY_CANCELLED,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    OrderInquirySuggestedLink,
    ProjectSalesOrderLine,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.project_supply_service import ProjectSupplyService

from ._pg_fixture import blank_session
from .test_fulfilment_board import (  # noqa: F401
    TODAY,
    _adopt,
    _confirm,
    _line as _board_line,
    _order as _board_order,
    _product as _board_product,
    _service as _board_service,
    _sorento,
    _stock as _board_stock,
    _user as _board_user,
    _warehouse as _board_warehouse,
)
from .test_so_supply_confirmation import (  # noqa: F401 - `api` is a fixture
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    _second_company,
    _spo,
    _stock,
    _suffix,
    _warehouse,
    api,
)


def _uid() -> str:
    return str(uuid.uuid4())


# =========================================================================== P1 =========


def _oracle_oi_placements(db, refs, product_ids, *, company_id=None):
    """The one-join statement `_oi_placements` ran before PR 2, verbatim
    (`project_supply_service.py` lines 3410-3439 on main at 44775ba104)."""
    query = (
        db.query(
            SalesOrderLine.source_ref,
            SalesOrderLine.product_id,
            SalesOrderLine.company_id,
            SPOAllocation.spo_number,
            OrderInquiryLink.qty,
            SPOAllocation.quantity_received,
        )
        .join(
            ProjectSalesOrderLine,
            ProjectSalesOrderLine.core_sales_order_line_id == SalesOrderLine.id,
        )
        .join(OrderInquiryRow, OrderInquiryRow.so_line_id == ProjectSalesOrderLine.id)
        .join(OrderInquiryLink, OrderInquiryLink.row_id == OrderInquiryRow.id)
        .join(
            SPOAllocation,
            (SPOAllocation.id == OrderInquiryLink.spo_allocation_id)
            & (SPOAllocation.product_id == SalesOrderLine.product_id)
            & (SPOAllocation.company_id == SalesOrderLine.company_id),
        )
        .filter(
            SalesOrderLine.source_ref.in_(list(refs)),
            SalesOrderLine.product_id.in_(list(product_ids)),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
    )
    if company_id is not None:
        query = query.filter(SalesOrderLine.company_id == company_id)
    return query.all()


def _key(rows):
    return sorted(
        (str(r[0]), str(r[1]), str(r[2]), str(r[3]), str(Decimal(r[4]).normalize()),
         str(Decimal(r[5]).normalize()))
        for r in rows
    )


def _place(db, *, company_id, project, product, ref, spo_product=None, spo_company=None,
           state="raised", qty="4", received=3, spo_number=None):
    """core SalesOrderLine(source_ref) <- project line <- inquiry row <- link -> SPO row."""
    own_wh = _warehouse(db, f"ZZT-OWN-{_suffix()}", segment="project")
    core_so = _core_so(db, company_id)
    core = _core_line(db, core_so, product, own_wh, qty_ordered="10")
    core.source_ref = ref
    pso = _project_so(db, project)
    pline = _project_line(db, pso, line_no=10, product=product, core_line=core)
    inquiry = OrderInquiry(
        id=_uid(), company_id=company_id, project_sales_order_id=pso.id,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_uid(), company_id=company_id, order_inquiry_id=inquiry.id, so_line_id=pline.id,
        item_code=product.product_code, qty=Decimal(qty), verb="ORDER", state=state,
    )
    db.add(row)
    db.flush()
    spo = SPOAllocation(
        id=_uid(), company_id=spo_company or company_id,
        spo_number=spo_number or f"ZZT-SPO-{_suffix()}", spo_line_number=1,
        warehouse_id=own_wh.id, product_id=(spo_product or product).id,
        allocated_quantity=10, quantity_received=received,
    )
    db.add(spo)
    db.flush()
    db.add(OrderInquiryLink(
        id=_uid(), company_id=company_id, row_id=row.id, spo_allocation_id=spo.id,
        qty=Decimal(qty),
    ))
    db.flush()
    return spo


def test_oi_placements_returns_the_same_rows_as_the_one_join_statement(api):
    """P1 guard: positives place, every negative places nothing, for no company, the right
    company and another company."""
    _client, world = api
    db = world.db
    c1 = world.company_id
    c2 = _second_company(db)
    p = _product(db)
    other_product = _product(db)
    ref = f"ZZT-REF-{_suffix()}"

    hit_a = _place(db, company_id=c1, project=world.project, product=p, ref=ref,
                   qty="4", received=3, spo_number="ZZT-SPO-HIT-A")
    hit_b = _place(db, company_id=c1, project=world.project, product=p, ref=ref,
                   qty="2", received=9, spo_number="ZZT-SPO-HIT-B")
    # Negatives: each would place if it were not for its one flaw.
    _place(db, company_id=c1, project=world.project, product=p, ref=ref,
           state=INQUIRY_CANCELLED, spo_number="ZZT-SPO-NEG-CANCELLED")
    _place(db, company_id=c1, project=world.project, product=p, ref=ref,
           spo_product=other_product, spo_number="ZZT-SPO-NEG-PRODUCT")
    _place(db, company_id=c1, project=world.project, product=p, ref=ref,
           spo_company=c2, spo_number="ZZT-SPO-NEG-COMPANY")
    _place(db, company_id=c1, project=world.project, product=p, ref=f"{ref}-NOT-ASKED",
           spo_number="ZZT-SPO-NEG-REF")
    _place(db, company_id=c1, project=world.project, product=other_product, ref=ref,
           spo_number="ZZT-SPO-NEG-NOT-ASKED-PRODUCT")
    db.flush()

    service = ProjectSupplyService(db)
    expected = _key([
        (ref, p.id, c1, "ZZT-SPO-HIT-A", "4", 3),
        (ref, p.id, c1, "ZZT-SPO-HIT-B", "2", 9),
    ])
    # Under the fixture's own scope {c1} the scope filter on spo_allocations drops the c2 SPO
    # row by itself; UNSCOPED, only the statement's own company pairing excludes it, so the
    # review-round check (delete the pairing and this goes red) runs there.
    for scope in (frozenset({c1}), None):
        with company_scope(db, scope):
            for company in (None, c1, c2):
                old = _key(_oracle_oi_placements(db, [ref], [p.id], company_id=company))
                new = _key(service._oi_placements([ref], [p.id], company_id=company))
                assert new == old, (scope, company, new, old)
                assert old == (expected if company in (None, c1) else []), (scope, company, old)
                assert all("NEG-COMPANY" not in row[3] for row in new), (scope, company, new)
    assert hit_a is not None and hit_b is not None


# =========================================================================== P3 =========


def _planning_warehouses_like_the_board(supply):
    warehouses = dict(supply._planning_warehouses())
    warehouses.update(supply._site_pool_warehouses())
    return warehouses


def _faithful(assignment):
    """Every line's key, result and quantities, and every event: what `assign()` answered."""
    def plain(value):
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        if isinstance(value, dict):
            return {str(k): plain(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        if hasattr(value, "__dict__") and not isinstance(value, (str, int, float, Decimal, date)):
            return {k: plain(v) for k, v in sorted(vars(value).items())}
        return repr(value)

    return plain(assignment)


def test_assignments_for_several_products_equals_one_call_per_product():
    """P3 guard: no product's answer depends on which products were asked beside it."""
    from app.services.scm.stock_debt_service import StockDebtService

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            own = _board_warehouse(db, f"ZZTO{_uid()[:6]}"[:20])
            pool = _board_warehouse(db, f"ZZTP{_uid()[:6]}"[:20])
            own.pool_warehouse_id = pool.id
            db.flush()
            products = [_board_product(db, f"ZZT-{_uid()[:6]}") for _ in range(2)]
            for n, product in enumerate(products):
                _board_stock(db, product, own, on_hand=3 + n)
                _board_stock(db, product, pool, on_hand=7 + n)
                for k in range(2):
                    order = _board_order(db, so_number=f"ZZT-SO-{_uid()[:8]}",
                                         order_date=date(2026, 1, 1 + k))
                    _board_line(db, order, product, qty=str(6 + n + k),
                                required_date=date(2026, 9, 3 + k), warehouse=own)
                core_so = _core_so(db, company_id)
                _spo(db, company_id, _as_so_product(product), own, qty=5 + n,
                     arrival_date=date(2026, 9, 10), spo_number=f"ZZT-SPO-{_uid()[:8]}")
            db.flush()

            def read(ids):
                supply = ProjectSupplyService(db)
                reader = StockDebtService(db)
                reader.supply = supply
                return reader.assignments_for(
                    list(ids), _planning_warehouses_like_the_board(supply), as_of=TODAY
                )

            ids = [str(p.id) for p in products]
            together = read(ids)
            assert set(together) == set(ids)
            for pid in ids:
                alone = read([pid])[pid]
                assert _faithful(together[pid]) == _faithful(alone), pid
            # Not vacuous: the walk found demand for both products.
            assert all(_faithful(together[pid]) for pid in ids)


def _as_so_product(product):
    """`_spo` only reads `.id`; the board's Product row serves."""
    return product


# =========================================================================== P2 =========


def _covered_order(db, actor, so_number, qty="43"):
    """One order whose only line is decided as a whole-line borrow from a donor: COVERED, of a
    product no undecided order owes (so the board's main walk does not read it)."""
    product = _board_product(db, f"ZZT-{_uid()[:6]}")
    own = _board_warehouse(db, f"ZZTO{_uid()[:6]}"[:20])
    donor = _board_warehouse(db, f"ZZTD{_uid()[:6]}"[:20])
    _board_stock(db, product, own, on_hand=20)
    _board_stock(db, product, donor, on_hand=int(qty))
    order = _board_order(db, so_number=so_number, order_date=date(2026, 1, 1))
    line = _board_line(db, order, product, qty=qty, required_date=date(2026, 9, 4), warehouse=own)
    pso_id = _adopt(db, str(order.id))
    mirror = (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id,
                ProjectSalesOrderLine.core_sales_order_line_id == line.id)
        .first()
    )
    _confirm(db, pso_id, actor, [{
        "project_line_id": str(mirror.id), "timely_spo_qty": "0", "reserve": [],
        "borrow": [{"source": "other_location", "warehouse_id": str(donor.id), "qty": qty,
                    "reason": "The other site can wait a week."}],
        "buy_qty": "0",
        "amend_reason": "Borrowed rather than bought, agreed with the other site.",
    }])
    return order


def test_a_board_build_reads_the_stock_debt_assignment_at_most_twice_P2_RED():
    """RED on main: the main walk, one single-product read per new product a covered row's
    donor lookup asks, and one per covered order (`_suggest_live_for_covered`)."""
    from app.services.scm.stock_debt_service import StockDebtService

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            actor = _board_user(db, "zzt-board planner")
            covered = [
                _covered_order(db, actor, "ZZT-SO-COV-A"),
                _covered_order(db, actor, "ZZT-SO-COV-B"),
            ]
            undecided_product = _board_product(db, f"ZZT-{_uid()[:6]}")
            own = _board_warehouse(db, f"ZZTO{_uid()[:6]}"[:20])
            _board_stock(db, undecided_product, own, on_hand=30)
            undecided = _board_order(db, so_number="ZZT-SO-UNDECIDED",
                                     order_date=date(2026, 1, 2))
            _board_line(db, undecided, undecided_product, qty="10",
                        required_date=date(2026, 9, 5), warehouse=own)
            db.flush()

            calls = []
            original = StockDebtService.assignments_for

            def counting(self, product_ids, *args, **kwargs):
                calls.append(sorted(str(p) for p in product_ids))
                return original(self, product_ids, *args, **kwargs)

            StockDebtService.assignments_for = counting
            try:
                board = _board_service(db).build(
                    ["ZZT-SO-COV-A", "ZZT-SO-COV-B", "ZZT-SO-UNDECIDED"],
                    granularity="week", as_of=TODAY,
                )
            finally:
                StockDebtService.assignments_for = original

            # Sanity: every order is on the board, covered ones as covered.
            by_so = {
                c["so_number"]: c
                for cell in board["cells"] for c in cell["contributions"]
            }
            assert set(by_so) == {"ZZT-SO-COV-A", "ZZT-SO-COV-B", "ZZT-SO-UNDECIDED"}
            assert by_so["ZZT-SO-COV-A"]["covered"] and by_so["ZZT-SO-COV-B"]["covered"]
            assert not by_so["ZZT-SO-UNDECIDED"]["covered"]
            assert len(covered) == 2
            assert len(calls) <= 2, f"{len(calls)} assignment reads: {calls}"


# =========================================================================== P4 =========


def _count_statements(db, patterns):
    seen = {name: 0 for name in patterns}

    def count(_conn, _cursor, statement, _params, _context, _many):
        text = " ".join(statement.lower().split())
        if not text.startswith("select"):
            return
        for name, pattern in patterns.items():
            if re.search(pattern, text):
                seen[name] += 1

    return seen, count


ROWS_PER_LINE = 2


def test_a_placement_pass_reads_line_identity_once_per_line_and_inquiry_once_P4_RED(api):
    """RED on main: `_resolve_product_id` reads each row's project line twice and
    `claim_identity` once more, and each row re-reads its inquiry."""
    client, world = api
    db = world.db
    product = world.product
    today = date.today()
    lines = []
    for n in range(3):
        order = _project_so(db, world.project)
        core_so = _core_so(db, world.company_id)
        core = _core_line(db, core_so, product, world.own_wh, qty_ordered="20")
        lines.append((order, _project_line(db, order, line_no=10, product=product, core_line=core)))
    inquiries = []
    for order, pline in lines:
        inquiry = OrderInquiry(id=_uid(), company_id=world.company_id,
                               project_sales_order_id=order.id)
        db.add(inquiry)
        db.flush()
        inquiries.append(inquiry)
        for k in range(ROWS_PER_LINE):
            db.add(OrderInquiryRow(
                id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
                so_line_id=pline.id, item_code=product.product_code, qty=Decimal("3"),
                verb="ORDER", state="raised", ack_state="awaiting",
                delivery_date=today + timedelta(days=30 + k),
            ))
    for qty, days in ((5, 20), (4, 40)):
        db.add(SPOAllocation(
            id=_uid(), spo_number=f"ZZT-SPO-{_suffix()}", spo_line_number=1,
            product_id=product.id, warehouse_id=world.pool_wh.id,
            allocated_quantity=qty, quantity_received=0, receipt_status="pending",
            line_status="open", expected_date=today + timedelta(days=days),
            company_id=world.company_id,
        ))
    db.commit()
    rows = db.query(OrderInquiryRow).filter(
        OrderInquiryRow.item_code == product.product_code).count()
    assert rows == 3 * ROWS_PER_LINE

    def pass_():
        service = ProjectOrderInquiryService(db)
        service.auto_place_for_products(
            [str(product.id)], actor_user_id=None, trigger="test-pr2",
            include_awaiting=True, link_horizon="none",
        )
        db.flush()

    def links():
        out = []
        for model in (OrderInquiryLink, OrderInquirySuggestedLink):
            for link, row in (
                db.query(model, OrderInquiryRow)
                .join(OrderInquiryRow, OrderInquiryRow.id == model.row_id)
                .filter(OrderInquiryRow.item_code == product.product_code)
            ):
                out.append((str(row.so_line_id), str(Decimal(row.qty).normalize()),
                            str(link.spo_allocation_id or ""), str(Decimal(link.qty).normalize())))
        return sorted(out)

    patterns = {
        "line_by_id": r"from \S*sales_order_lines where \S*sales_order_lines\.id = ",
        "inquiry_by_id": r"from \S*order_inquiries where \S*order_inquiries\.id = ",
    }
    seen, count = _count_statements(db, patterns)
    engine = db.get_bind()
    savepoint = db.begin_nested()
    event.listen(engine, "before_cursor_execute", count)
    try:
        pass_()
    finally:
        event.remove(engine, "before_cursor_execute", count)
    placed = links()
    savepoint.rollback()
    db.expire_all()

    # Not vacuous: the pass placed something.
    assert placed, "the pass placed nothing"
    # The exact placement the per-row reads produced (measured on main): the 9 units of
    # scarce supply dealt across three rows as 2+1, 3 and 3. The memo must not move it.
    assert sorted(p[3] for p in placed) == ["1", "2", "3", "3"], placed
    # The identity reads: once per project line (+2 slack), once per inquiry (+1 slack).
    assert seen["line_by_id"] <= len(lines) + 2, seen
    assert seen["inquiry_by_id"] <= len(inquiries) + 1, seen


def test_each_claim_a_pass_writes_carries_its_own_orders_so_number_P4_CLAIMS(api):
    """Review round: a so_number memo keyed wrongly (every row given the first inquiry's
    number) must fail. One pass writes claims for rows of three inquiries on three
    different sales orders; each claim's so_number is its own order's."""
    from app.models.scm import OrderLinkClaim

    client, world = api
    db = world.db
    product = world.product
    today = date.today()
    orders = []
    for n in range(3):
        order = _project_so(db, world.project)
        order.autocount_doc_no = f"ZZT-AC-{_suffix()}"
        core_so = _core_so(db, world.company_id)
        core = _core_line(db, core_so, product, world.own_wh, qty_ordered="5")
        pline = _project_line(db, order, line_no=10, product=product, core_line=core)
        inquiry = OrderInquiry(id=_uid(), company_id=world.company_id,
                               project_sales_order_id=order.id)
        db.add(inquiry)
        db.flush()
        for k in range(2):
            db.add(OrderInquiryRow(
                id=_uid(), company_id=world.company_id, order_inquiry_id=inquiry.id,
                so_line_id=pline.id, item_code=product.product_code, qty=Decimal("2"),
                verb="ORDER", state="raised", ack_state="acknowledged",
                delivery_date=today + timedelta(days=30 + k),
            ))
        orders.append(order)
    for qty, days in ((12, 20),):
        db.add(SPOAllocation(
            id=_uid(), spo_number=f"ZZT-SPO-{_suffix()}", spo_line_number=1,
            product_id=product.id, warehouse_id=world.pool_wh.id,
            allocated_quantity=qty, quantity_received=0, receipt_status="pending",
            line_status="open", expected_date=today + timedelta(days=days),
            company_id=world.company_id,
        ))
    db.commit()
    # A pass's own real links come only from the PO book step (needs ingested book rows), so
    # the claim writer is driven the way a pass drives it: `_write_link` on rows of several
    # inquiries while the pass's identity memo is live (`auto_place_for_products` sets it).
    service = ProjectOrderInquiryService(db)
    service._line_identity_memo = {}
    try:
        rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.item_code == product.product_code)
            .order_by(OrderInquiryRow.created_at, OrderInquiryRow.id)
            .all()
        )
        assert len({r.order_inquiry_id for r in rows}) == 3
        for row in rows:
            candidates = service._candidates_for_row(row)
            assert candidates, "the seeded SPO row is not a candidate"
            service._write_link(row, candidates[0], Decimal("2"), actor_user_id=None,
                                auto_trigger="test-pr2-claims")
    finally:
        service._line_identity_memo = None
    db.flush()
    expected = {order.autocount_doc_no for order in orders}
    claims = (
        db.query(OrderLinkClaim)
        .filter(OrderLinkClaim.item_code == product.product_code)
        .all()
    )
    assert {c.so_number for c in claims} == expected, (
        sorted(c.so_number for c in claims), sorted(expected))
    # Each claim sits on its own order's core line, not the first inquiry's.
    by_line = {}
    for claim in claims:
        by_line.setdefault(str(claim.so_line_id), set()).add(claim.so_number)
    assert all(len(numbers) == 1 for numbers in by_line.values()), by_line
