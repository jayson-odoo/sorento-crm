"""S3 (fulfilment planning) - sales order lines in AutoCount order.

Plan: `documentation/plans/scm/PLAN-so-lines-autocount-order.md` section 3.5.
UAC: `documentation/plans/scm/so-lines-autocount-order-acceptance-criteria.md`.

  AC-S3-1  `FulfilmentBoardService._line_numbers`: an order whose lines all carry
           DISTINCT `line_no` reports those numbers (over the derived rule).
  AC-S3-2  `_line_numbers`: an order with one NULL `line_no` falls back to the derived
           rule for the WHOLE order.
  AC-S3-3  `_line_numbers`: a fully mirrored order still reports the mirror's numbers -
           mirror wins over `line_no`, same as it already wins over the derived rule.
  AC-S3-4  `ProjectSOAdoptionService._mirror`: lines with `line_no` 5, 1, 3 get mirror
           `line_no` 1, 2, 3 in the order 1, 3, 5.
  AC-S3-5  `mirror_missing_lines`: a later core line takes the next number; existing
           mirror lines keep theirs (`line_no` never reorders an ALREADY mirrored line).
  AC-S3-6  the sheet's own reader (`ProjectSupplyService.lines_of`, the same accessor
           `confirm` builds its `by_id` from) lists a freshly adopted order's lines in
           AutoCount order.

AC-S3-2 and AC-S3-5 are NOT expected to be red today - noted per-test below - because
today's code already behaves the way the plan asks there (one NULL already falls back
for the whole order since `line_no` is not consulted at all yet; `mirror_missing_lines`
already only appends). They are included because the captain's test list names them, and
they guard against a coder regression while AC-S3-1/3/4/6 are the real gaps.

Postgres only, `blank_session()` for the adoption tests (mirrors
`tests/test_project_so_adoption.py`'s own substrate) and a bare `pg_session()` for the
pure `_line_numbers` reads, which touch no table this file needs to seed.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.base import company_scope
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.project_so import ProjectSalesOrder
from app.services.project_fulfilment_board_service import FulfilmentBoardService
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from app.services.project_supply_service import ProjectSupplyService

from tests._pg_fixture import blank_session, pg_session
from tests.test_project_so_adoption import (
    D1,
    D2,
    D3,
    _core_line,
    _core_order,
    _mirror_lines,
    _product,
    _sorento,
    _warehouse,
)


def _u() -> str:
    return str(uuid.uuid4())


def _rec(line, order, product):
    """One `_line_numbers` record tuple: `(line, order, product, warehouse, agent)` -
    the last two are unused by `_line_numbers` itself."""
    return (line, order, product, None, None)


class TestLineNumbersPrefersLineNo:
    def test_ac_s3_1_distinct_line_no_wins_over_the_derived_rule(self):
        """Derived (required_date, product code) would order these B-then-A (B is due
        earlier and sorts first on code too); `line_no` says the opposite, and it must
        win once every line on the order carries one."""
        with pg_session() as db:
            svc = FulfilmentBoardService(db)
            order = SalesOrder(id=_u())
            product_a = Product(id=_u(), product_code="ZZZ-A")
            product_b = Product(id=_u(), product_code="AAA-B")
            line_a = SalesOrderLine(id=_u(), required_date=date(2027, 3, 1))
            line_a.line_no = 9
            line_b = SalesOrderLine(id=_u(), required_date=date(2026, 1, 1))
            line_b.line_no = 1
            records = [_rec(line_a, order, product_a), _rec(line_b, order, product_b)]

            numbers = svc._line_numbers(records)

            assert numbers[str(line_a.id)] == 9
            assert numbers[str(line_b.id)] == 1

    def test_ac_s3_2_one_null_line_no_falls_back_for_the_whole_order(self):
        """NOT expected to be red today: `_line_numbers` does not consult `line_no` at
        all yet, so it already falls back to the derived rule unconditionally - this
        guards that a partial `line_no` never gets treated as good enough."""
        with pg_session() as db:
            svc = FulfilmentBoardService(db)
            order = SalesOrder(id=_u())
            product_a = Product(id=_u(), product_code="AAA")
            product_b = Product(id=_u(), product_code="BBB")
            line_a = SalesOrderLine(id=_u(), required_date=date(2026, 1, 1))
            line_a.line_no = 5
            line_b = SalesOrderLine(id=_u(), required_date=date(2026, 2, 1))
            line_b.line_no = None
            records = [_rec(line_a, order, product_a), _rec(line_b, order, product_b)]

            numbers = svc._line_numbers(records)

            # Derived: line_a (earlier date) -> 1, line_b -> 2.
            assert numbers[str(line_a.id)] == 1
            assert numbers[str(line_b.id)] == 2

    def test_ac_s3_3_mirror_numbers_still_win_over_line_no(self):
        """NOT expected to be red today: the mirror-wins branch is unconditional
        already and does not look at `line_no` either way - this guards that adding
        the `line_no` rule does not demote the mirror underneath it."""
        with pg_session() as db:
            svc = FulfilmentBoardService(db)
            order = SalesOrder(id=_u())
            product_a = Product(id=_u(), product_code="AAA")
            product_b = Product(id=_u(), product_code="BBB")
            line_a = SalesOrderLine(id=_u(), required_date=date(2026, 1, 1))
            line_a.line_no = 9
            line_b = SalesOrderLine(id=_u(), required_date=date(2026, 2, 1))
            line_b.line_no = 1
            svc._addressing = {
                str(line_a.id): {"line_no": 1},
                str(line_b.id): {"line_no": 2},
            }
            records = [_rec(line_a, order, product_a), _rec(line_b, order, product_b)]

            numbers = svc._line_numbers(records)

            assert numbers[str(line_a.id)] == 1
            assert numbers[str(line_b.id)] == 2


class TestMirrorOrdersByLineNo:
    def test_ac_s3_4_mirror_orders_by_line_no_not_required_date(self):
        """`required_date` is set to DISAGREE with `line_no` on purpose - D1 is
        earliest but belongs to the HIGHEST `line_no` (5) - so a mirror that still
        sorted by date would produce [line_5, line_3, line_1], not the AutoCount
        order this test pins."""
        with blank_session() as db:
            company_id = _sorento(db)
            with company_scope(db, frozenset({company_id})):
                product = _product(db)
                warehouse = _warehouse(db, company_id)
                core = _core_order(db, company_id)
                line_5 = _core_line(db, core, product, warehouse=warehouse, required_date=D1)
                line_3 = _core_line(db, core, product, warehouse=warehouse, required_date=D2)
                line_1 = _core_line(db, core, product, warehouse=warehouse, required_date=D3)
                line_5.line_no = 5
                line_3.line_no = 3
                line_1.line_no = 1
                db.flush()

                result = ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)
                order = db.query(ProjectSalesOrder).get(result["project_sales_order_id"])
                mirror = _mirror_lines(db, order.id)

                assert [row.line_no for row in mirror] == [1, 2, 3]
                assert [str(row.core_sales_order_line_id) for row in mirror] == [
                    str(line_1.id),
                    str(line_3.id),
                    str(line_5.id),
                ]

    def test_ac_s3_6_the_sheets_own_reader_lists_lines_in_autocount_order(self):
        """The same fixture as AC-S3-4, read through `ProjectSupplyService.lines_of` -
        the accessor `confirm` itself builds `by_id` from - so the sheet a planner
        actually opens names lines in AutoCount's own order, not just the raw table."""
        with blank_session() as db:
            company_id = _sorento(db)
            with company_scope(db, frozenset({company_id})):
                product = _product(db)
                warehouse = _warehouse(db, company_id)
                core = _core_order(db, company_id)
                line_5 = _core_line(db, core, product, warehouse=warehouse, required_date=D1)
                line_3 = _core_line(db, core, product, warehouse=warehouse, required_date=D2)
                line_1 = _core_line(db, core, product, warehouse=warehouse, required_date=D3)
                line_5.line_no = 5
                line_3.line_no = 3
                line_1.line_no = 1
                db.flush()

                result = ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)

                sheet_lines = ProjectSupplyService(db).lines_of(result["project_sales_order_id"])

                assert [str(row.core_sales_order_line_id) for row in sheet_lines] == [
                    str(line_1.id),
                    str(line_3.id),
                    str(line_5.id),
                ]


class TestMirrorMissingLinesNeverRenumbers:
    def test_ac_s3_5_a_later_core_line_takes_the_next_number_keeping_earlier_ones(self):
        """NOT expected to be red today: `mirror_missing_lines` already only appends
        (`_next_line_no`) and never renumbers an existing mirror line, so this already
        holds before `line_no` exists at all. Kept as a named regression guard - the
        captain's test list asks for it, and a coder tempted to "fix" ordering by
        renumbering on every call would break exactly this."""
        with blank_session() as db:
            company_id = _sorento(db)
            with company_scope(db, frozenset({company_id})):
                product = _product(db)
                warehouse = _warehouse(db, company_id)
                core = _core_order(db, company_id)
                first = _core_line(db, core, product, warehouse=warehouse, required_date=D2)
                first.line_no = 5
                db.flush()

                service = ProjectSOAdoptionService(db)
                result = service.adopt(core.id, actor_user_id=None)
                order = db.query(ProjectSalesOrder).get(result["project_sales_order_id"])
                assert [row.line_no for row in _mirror_lines(db, order.id)] == [1]

                # A later upload adds a line whose OWN AutoCount number (1) is EARLIER
                # than the line already mirrored (5) - it must still take the next
                # mirror number (2), never displace line 1.
                later = _core_line(db, core, product, warehouse=warehouse, required_date=D1)
                later.line_no = 1
                db.flush()
                service.mirror_missing_lines(order)
                db.flush()

                mirror = _mirror_lines(db, order.id)
                assert [row.line_no for row in mirror] == [1, 2]
                assert [str(row.core_sales_order_line_id) for row in mirror] == [
                    str(first.id),
                    str(later.id),
                ]
