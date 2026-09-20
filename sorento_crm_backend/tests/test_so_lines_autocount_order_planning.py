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
           `line_no` 1, 3, 5 - RAW, in the order 1, 3, 5.
  AC-S3-5  `mirror_missing_lines`: a later core line takes ITS OWN raw number (or the
           next free one, with none); an ALREADY mirrored line never gets rewritten.
  AC-S3-6  the sheet's own reader (`ProjectSupplyService.lines_of`, the same accessor
           `confirm` builds its `by_id` from) lists a freshly adopted order's lines in
           AutoCount order.

Reviewer fix round (captain's brief, this file's second pass): the reviewer found
`app/services/project_line_draft_service.py::_resolve_core_line` still numbering by the
OLD derived-only rule while the board already hands out raw `line_no`, and separately
that `_mirror` was RENUMBERING to 1..n instead of keeping AutoCount's own gaps. The
coder is extracting one shared numbering function for the board, the resolver and the
mirror. That fix changes what "correct" means for AC-S3-4 and AC-S3-5 above - both were
written and PASSED against the old (wrong) `_mirror` behaviour, and are UPDATED here
(said so in each test's own docstring) rather than left as false regression guards:

  AC-S1r-1  = the updated AC-S3-4 (raw numbers 1, 3, 5, not renumbered 1, 2, 3).
  AC-S1r-2  adoption of an order with one NULL `line_no` still numbers 1..n by the old
            rule - the SAME guard AC-S3-2 states for the board, now asked of `_mirror`.
  AC-S1r-3  `mirror_missing_lines` on an already raw-numbered mirror (1, 3, 5): a later
            core line with `line_no=7` gets 7; a further later line with NULL `line_no`
            gets `max + 1 = 8`.

AC-S3-2 alone is NOT expected to be red today - today's `_line_numbers` already falls
back to the derived rule for a partial `line_no` since it never trusted anything else.
AC-S3-4 and AC-S3-5 (as updated) ARE expected to be red today, alongside AC-S3-1,
AC-S3-6 and the three new AC-S1r tests: current `_mirror` renumbers 1..n unconditionally
regardless of `line_no`, both on a fresh adopt and on `mirror_missing_lines`'s own call
through it.

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
        order this test pins.

        AC-S1r-1 (reviewer fix round, S1 blocker): UPDATED from this test's original
        expectation (`[1, 2, 3]`) to the RAW AutoCount numbers, gaps allowed - `[1, 3,
        5]`, not renumbered. `FulfilmentBoardService._line_numbers` already hands out
        raw numbers this way (AC-S3-1); the reviewer's blocker was that `_mirror`
        disagreed with it by renumbering 1..n instead of keeping AutoCount's own gaps -
        the one shared numbering function the coder is extracting must agree with
        itself everywhere it is called.
        """
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

                assert [row.line_no for row in mirror] == [1, 3, 5]
                assert [str(row.core_sales_order_line_id) for row in mirror] == [
                    str(line_1.id),
                    str(line_3.id),
                    str(line_5.id),
                ]

    def test_ac_s1r_2_mirror_falls_back_to_the_old_rule_when_one_line_no_is_null(self):
        """AC-S1r-2: the SAME "one NULL drops the whole order back to the derived rule"
        guard `_line_numbers` already applies (AC-S3-2), now asked of `_mirror` too -
        the shared function must answer identically on both call sites. Three lines,
        two carrying a `line_no` that disagrees with date order and one NULL: the
        derived rule (required date, item code, id) decides for ALL three, not just
        the null one, because a PARTIAL `line_no` is not enough to trust.
        """
        with blank_session() as db:
            company_id = _sorento(db)
            with company_scope(db, frozenset({company_id})):
                product = _product(db)
                warehouse = _warehouse(db, company_id)
                core = _core_order(db, company_id)
                line_late = _core_line(db, core, product, warehouse=warehouse, required_date=D3)
                line_late.line_no = 9
                line_mid = _core_line(db, core, product, warehouse=warehouse, required_date=D2)
                line_mid.line_no = None
                line_early = _core_line(db, core, product, warehouse=warehouse, required_date=D1)
                line_early.line_no = 1
                db.flush()

                result = ProjectSOAdoptionService(db).adopt(core.id, actor_user_id=None)
                order = db.query(ProjectSalesOrder).get(result["project_sales_order_id"])
                mirror = _mirror_lines(db, order.id)

                # Derived, by required date ascending: line_early (D1), line_mid (D2),
                # line_late (D3) -> mirror 1, 2, 3 - `line_no` 9/None/1 is ignored entirely.
                assert [row.line_no for row in mirror] == [1, 2, 3]
                assert [str(row.core_sales_order_line_id) for row in mirror] == [
                    str(line_early.id),
                    str(line_mid.id),
                    str(line_late.id),
                ]

    def test_ac_s1r_3_mirror_missing_lines_gives_a_raw_number_or_the_next_free_one(self):
        """AC-S1r-3: on an already RAW-numbered mirror (1, 3, 5 - this test's own setup
        is AC-S3-4's), a later core line carrying its OWN AutoCount number is given
        THAT number verbatim (7, not "the next slot" which would be 4) - the mirror
        keeps agreeing with the board even when a line arrives after adoption. A
        further later line with NO AutoCount number falls back to one past the
        mirror's current highest (8), the same `_next_line_no` rule as before.
        """
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

                service = ProjectSOAdoptionService(db)
                result = service.adopt(core.id, actor_user_id=None)
                order = db.query(ProjectSalesOrder).get(result["project_sales_order_id"])
                assert [row.line_no for row in _mirror_lines(db, order.id)] == [1, 3, 5]

                line_7 = _core_line(db, core, product, warehouse=warehouse, required_date=D2)
                line_7.line_no = 7
                db.flush()
                service.mirror_missing_lines(order)
                db.flush()

                mirror = _mirror_lines(db, order.id)
                assert [row.line_no for row in mirror] == [1, 3, 5, 7]
                assert str(mirror[-1].core_sales_order_line_id) == str(line_7.id)

                line_null = _core_line(db, core, product, warehouse=warehouse, required_date=D3)
                line_null.line_no = None
                db.flush()
                service.mirror_missing_lines(order)
                db.flush()

                mirror = _mirror_lines(db, order.id)
                assert [row.line_no for row in mirror] == [1, 3, 5, 7, 8]
                assert str(mirror[-1].core_sales_order_line_id) == str(line_null.id)

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
    def test_ac_s3_5_mirror_missing_lines_never_renumbers_an_existing_mirror_line(self):
        """UPDATED for the reviewer fix round (AC-S1r-1/3): the ORIGINAL version of this
        test expected a lone `line_no=5` core line to mirror as `1` (pure position) and
        a later `line_no=1` line to append as `2` - both wrong under the corrected rule,
        where a single line's own `line_no` already counts as "every contributing line
        distinct and non-null" and therefore wins RAW (mirror `5`, not `1`). What this
        test still pins, and the only thing AC-S3-5 itself asserts, is narrower:
        `mirror_missing_lines` never REWRITES a line_no a mirror already carries, even
        when a later line's own raw number would sort ahead of it. AC-S1r-3 covers the
        "later line gets its own raw number, or the next free one when it has none"
        half in full; this one is the "existing mirror lines keep theirs" half.
        """
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
                # RAW, not positional: the only line on the order carries `line_no=5`,
                # and one distinct non-null number is still "every line has one".
                assert [row.line_no for row in _mirror_lines(db, order.id)] == [5]

                # A later upload adds a line whose OWN AutoCount number (2) sorts AHEAD
                # of the line already mirrored (5) - it takes ITS OWN number (2), and
                # the existing mirror line keeps 5 rather than being pushed to 6.
                later = _core_line(db, core, product, warehouse=warehouse, required_date=D1)
                later.line_no = 2
                db.flush()
                service.mirror_missing_lines(order)
                db.flush()

                mirror = _mirror_lines(db, order.id)
                assert [row.line_no for row in mirror] == [2, 5]
                assert [str(row.core_sales_order_line_id) for row in mirror] == [
                    str(later.id),
                    str(first.id),
                ]
