"""OI-ONE-DELIVERY-DATE: the legs that must read the SO line date, each seeded with a stored
(told) date that differs from the SO line date so reverting the reader turns the test red
(AC-A3 matrix, A6 undo and confirm preview, A8 link window and demand legs, C1 re-upload)."""
from __future__ import annotations

import uuid
from datetime import date

from app.models.base import company_scope
from app.models.project_so import DECISION_ACTIVE, OrderInquiryRow, SOSupplyDecision

from ._oi_one_date_seed import Chain, digits
from ._pg_fixture import blank_session
from .test_order_inquiry_worklist import _restore, _sorento
from .test_project_order_inquiry_import_migration import D_NOV, D_OCT, sheet, world as import_world

OLD = date(2026, 7, 1)
NEW = date(2027, 1, 7)


def test_a3_matrix_buckets_by_the_so_line_date():
    from ._oi_one_date_seed import worklist_client

    with blank_session() as db:
        company_id = _sorento(db)
        client, originals = worklist_client(db, company_id)
        try:
            with company_scope(db, frozenset({company_id})):
                chain = Chain(db, company_id)
                chain.product.product_code = f"ZZT-LEG-{digits(10)}"
                _c, line = chain.add_line(core_date=NEW, mirror_date=NEW)
                chain.add_row(line, told=OLD)
                db.commit()
                response = client.get(
                    "/api/v1/project-sales/order-inquiries/matrix",
                    params={"axis": "product", "by": "month", "query": chain.product.product_code},
                )
                assert response.status_code == 200, response.text
                periods = {c["period"] for c in response.json()["data"]}
                assert periods == {"2027-01-01"}, periods
        finally:
            _restore(originals)


def test_a6_undo_email_prints_the_so_line_date():
    from app.services.project_supply_undo_service import _undo_email_lines, _table_name

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            _c, line = chain.add_line(core_date=NEW, mirror_date=NEW)
            row = chain.add_row(line, told=OLD)
            db.commit()
            journal = [{"table": _table_name(OrderInquiryRow), "op": "insert", "pk": row.id}]

            lines = _undo_email_lines(db, journal, str(chain.pso.id))

            assert [l["delivery_date"] for l in lines] == ["07/01/2027"]


def test_a6_confirm_preview_rows_print_the_so_line_date():
    from app.services.project_supply_service import ProjectSupplyService

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            _c, line = chain.add_line(core_date=NEW, mirror_date=NEW)
            row = chain.add_row(line, told=OLD)
            db.add(SOSupplyDecision(
                id=str(uuid.uuid4()),
                company_id=company_id, project_sales_order_id=str(chain.pso.id),
                revision_no=1, state=DECISION_ACTIVE, line_snapshots=[],
            ))
            db.flush()

            out = ProjectSupplyService(db)._preview_of(chain.pso, {}, {})

            dates = [r["delivery_date"] for r in out["inquiry_rows"]]
            assert dates == [NEW], dates


def test_a8_link_window_reads_the_so_line_date():
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            _c, line = chain.add_line(core_date=NEW, mirror_date=NEW)
            row = chain.add_row(line, told=OLD)
            db.commit()
            # Arrives 2026-12-20: far too early for the 2027-01-07 line (outside the window)
            # but inside it for the told date 2026-07-01 plus any lead time.
            candidate = {"expected_date": date(2026, 12, 20), "target_id": "t"}

            kept = ProjectOrderInquiryService(db)._within_window(row, [candidate], 14)

            assert kept == [], "early against the SO line date, so it is removed"


def test_a8_demand_leg_horizon_reads_the_so_line_date():
    from app.services.scm.demand import run_scope_oi_rows

    with blank_session() as db:
        company_id = _sorento(db)
        with company_scope(db, frozenset({company_id})):
            chain = Chain(db, company_id)
            _c, line = chain.add_line(core_date=NEW, mirror_date=NEW)
            row = chain.add_row(line, told=OLD)
            db.commit()
            pid = [str(chain.product.id)]

            in_line_month = run_scope_oi_rows(
                db, pid, horizon_start=date(2027, 1, 1), horizon=date(2027, 1, 31)
            )
            in_told_month = run_scope_oi_rows(
                db, pid, horizon_start=date(2026, 7, 1), horizon=date(2026, 7, 31)
            )

            assert [r["row_id"] for r in in_line_month] == [str(row.id)]
            assert in_told_month == []
            assert in_line_month[0]["delivery_date"] == NEW


def test_c1_reupload_of_the_same_sheet_raises_nothing_twice():
    with import_world() as w:
        order = w.order()
        w.line(order, qty_ordered="50", required_date=D_OCT)
        data = sheet([
            (order.so_number, w.product.product_code, 30, D_NOV, w.warehouse.warehouse_code, ""),
        ])
        first = w.apply(data)
        assert first["rows_raised"] == 1, first
        again = w.apply(data)
        assert again["rows_raised"] == 0, again
        row = w.one_row()
        assert (row.delivery_date, row.previous_delivery_date) == (D_OCT, D_NOV)


def test_c1_reupload_with_two_dated_rows_on_one_item_raises_nothing_twice():
    sheet_a, sheet_b = date(2026, 9, 1), date(2026, 9, 15)
    with import_world() as w:
        order = w.order()
        line_a = w.line(order, qty_ordered="50", required_date=D_OCT)
        line_b = w.line(order, qty_ordered="50", required_date=D_NOV)
        data = sheet([
            (order.so_number, w.product.product_code, 50, sheet_b, w.warehouse.warehouse_code, ""),
            (order.so_number, w.product.product_code, 50, sheet_a, w.warehouse.warehouse_code, ""),
        ])
        first = w.apply(data)
        assert first["rows_raised"] == 2, first
        by_line = {str(r.so_line_id): r for r in w.rows()}
        # The earlier sheet date picks the earlier line; each keeps its sheet date as the Was.
        assert by_line[str(w.mirror_of(line_a).id)].previous_delivery_date == sheet_a
        assert by_line[str(w.mirror_of(line_b).id)].previous_delivery_date == sheet_b
        again = w.apply(data)
        assert again["rows_raised"] == 0, again
        assert len(w.rows()) == 2
