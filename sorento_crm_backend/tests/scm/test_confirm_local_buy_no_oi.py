"""Confirm-time local-Buy skip (S3, PLAN-local-supplier-oi-routing.md, UAC AC-2.14 - AC-2.19).

RED for Phase 2: `BoardContribution.buy_origin` / `SupplyLine.buy_origin` do not exist on
the schemas yet, and `ProjectOrderInquiryService.refresh_for_decision` has no skip for a
`buy_lines` entry carrying `"origin": "local"` - today it raises/nets every Buy line the
same way regardless of origin. Every assertion below fails against TODAY's code.

Per the plan's own "testing seams" section: `refresh_for_decision` is exercised with
HAND-BUILT `buy_lines` (an `"origin"` key added straight to the dict, the same key
`project_supply_service.py`'s real confirm path will attach from `buy_origin_by_product`)
rather than through the whole board - so these tests do not need a board fixture at all.
AC-2.14's board/sheet half is the one exception, and it is scoped separately below.

Fixtures reused with the justification that earned them: `tests.scm.
test_project_supply_service_ladder._world` / `_seed_line` build the minimum project-SO +
core-SO + line graph every ladder test in that file already relies on; `tests.
test_project_order_inquiry._confirm`'s shape (decision + buy_lines dict) is copied here,
extended with the new `origin` key, because it is the one writer of a real
`SOSupplyDecision` + `refresh_for_decision` call already proven against this schema.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiryRow,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from tests._pg_fixture import blank_session
from tests.scm.test_project_supply_service_ladder import _seed_line, _world

MARKER = "zzt-local-oi"


def _u() -> str:
    return str(uuid.uuid4())


def _confirm(db, order, *, actor_user_id, origin_by_line: dict, buy_qty=None):
    """`refresh_for_decision`, called with hand-built `buy_lines` carrying the new
    `origin` key - the exact seam the plan names, no board or supply-origin lookup
    needed."""
    service = ProjectOrderInquiryService(db)
    lines = (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == order.id)
        .order_by(ProjectSalesOrderLine.line_no.asc())
        .all()
    )
    revision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .count()
        + 1
    )
    decision = SOSupplyDecision(
        id=_u(), company_id=order.company_id, project_sales_order_id=order.id,
        revision_no=revision,
        state="active" if revision == 1 else "superseded",
        line_snapshots=[{"line_no": line.line_no} for line in lines],
        confirmed_by=actor_user_id, confirmed_at=datetime.utcnow(),
    )
    db.add(decision)
    db.flush()
    buy_lines = [
        {
            "line": line,
            "line_no": line.line_no,
            "item_code": service._product_code(line.product_id),
            "buy_qty": Decimal(str(buy_qty)) if buy_qty is not None else Decimal(str(line.qty)),
            "required_date": line.delivery_date,
            "stock_location": line.stock_location,
            "origin": origin_by_line.get(str(line.id), "overseas"),
        }
        for line in lines
    ]
    return service.refresh_for_decision(order, decision, buy_lines, actor_user_id=actor_user_id)


def _raised_rows(db, so_line_id):
    return (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == so_line_id, OrderInquiryRow.verb == IV_ORDER)
        .all()
    )


# --------------------------------------------------------------------------- #
# AC-2.14: schemas carry buy_origin
# --------------------------------------------------------------------------- #


def test_board_and_supply_carry_buy_origin():
    from app.schemas.project_board import BoardContribution
    from app.schemas.project_supply import SupplyLine

    assert "buy_origin" in BoardContribution.model_fields
    assert "buy_origin" in SupplyLine.model_fields


def test_buy_origin_computed_once_per_board_build(monkeypatch):
    """A counter on `buy_origin_by_product` proves the board calls it ONCE for the whole
    request, not once per contributing line."""
    from app.models.inventory import Stock, Warehouse
    from app.models.order import SalesOrder, SalesOrderLine
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services import project_fulfilment_board_service as board_module

    calls = {"n": 0}
    real = board_module.buy_origin_by_product

    def _counting(db, product_ids):
        calls["n"] += 1
        return real(db, product_ids)

    monkeypatch.setattr(board_module, "buy_origin_by_product", _counting)

    with blank_session() as db:
        cat = ProductCategory(id=_u(), category_code=f"ZZT{_u()[:8]}", category_name="cat")
        uom = UnitOfMeasure(id=_u(), uom_code=f"ZZT{_u()[:6]}", uom_name="unit")
        db.add_all([cat, uom])
        db.flush()
        products = []
        for i in range(2):
            p = Product(
                id=_u(), product_code=f"ZZT-{MARKER}-{i}-{_u()[:6]}", product_name="p",
                category_id=cat.id, base_uom_id=uom.id, list_price=0,
                is_active=True, is_discontinued=False,
            )
            db.add(p)
            products.append(p)
        db.flush()
        warehouse = Warehouse(
            id=_u(), warehouse_code=f"ZZT{_u()[:6]}", warehouse_name="wh",
            is_active=True, fulfilment_planning=True,
        )
        db.add(warehouse)
        db.flush()
        so = SalesOrder(id=_u(), so_number=f"ZZT-{_u()[:8]}", status="open", order_date=date(2026, 1, 1))
        db.add(so)
        db.flush()
        for p in products:
            db.add(Stock(id=_u(), product_id=p.id, warehouse_id=warehouse.id, quantity_on_hand=100))
            db.add(SalesOrderLine(
                id=_u(), sales_order_id=so.id, product_id=p.id, warehouse_id=warehouse.id,
                qty_ordered=Decimal("10"), qty_delivered=Decimal("0"),
                required_date=date(2026, 9, 3), line_status="open",
            ))
        db.flush()

        board_module.FulfilmentBoardService(db).build(
            [so.so_number], granularity="week", as_of=date(2026, 1, 1)
        )

    assert calls["n"] == 1


# --------------------------------------------------------------------------- #
# AC-2.15: a local Buy records the decision, raises NO order_inquiry_rows / order_inquiries
# --------------------------------------------------------------------------- #


def test_local_buy_records_decision_no_oi_row():
    with blank_session() as db:
        company_id, owner, project, product = _world(db)
        from tests.scm.test_project_supply_service_ladder import _group_sites

        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
            required_date=date(2026, 9, 3),
        )

        result = _confirm(db, order, actor_user_id=owner, origin_by_line={str(line.id): "local"})

        assert result["created"] == 0
        assert _raised_rows(db, line.id) == []

        from app.models.project_so import OrderInquiry

        assert (
            db.query(OrderInquiry)
            .filter(OrderInquiry.project_sales_order_id == order.id)
            .count()
            == 0
        )


# --------------------------------------------------------------------------- #
# AC-2.16: a mixed order raises exactly one row, for the overseas line, under one header
# --------------------------------------------------------------------------- #


def test_mixed_order_raises_only_overseas():
    with blank_session() as db:
        company_id, owner, project, product_local = _world(db)
        from tests.test_so_supply_confirmation import _product
        from tests.scm.test_project_supply_service_ladder import _group_sites

        product_overseas = _product(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        order, local_line, _cso1, _cline1 = _seed_line(
            db, company_id, project, product_local, own, qty_ordered="10",
            required_date=date(2026, 9, 3), line_no=10,
        )
        # A second line on the SAME project order, different product.
        from tests.test_so_supply_confirmation import _core_line, _core_so, _project_line

        core_so2 = _core_so(db, company_id)
        core_line2 = _core_line(
            db, core_so2, product_overseas, own, qty_ordered="6", required_date=date(2026, 9, 3),
        )
        overseas_line = _project_line(
            db, order, line_no=20, product=product_overseas, core_line=core_line2,
        )
        db.commit()

        result = _confirm(
            db, order, actor_user_id=owner,
            origin_by_line={str(local_line.id): "local", str(overseas_line.id): "overseas"},
        )

        assert result["created"] == 1
        assert _raised_rows(db, local_line.id) == []
        overseas_rows = _raised_rows(db, overseas_line.id)
        assert len(overseas_rows) == 1
        assert overseas_rows[0].order_inquiry_id == result["inquiry"].id


# --------------------------------------------------------------------------- #
# AC-2.17: a row raised before this lane, on a line now local, is left untouched
# --------------------------------------------------------------------------- #


def test_prior_raised_row_on_now_local_line_untouched():
    with blank_session() as db:
        company_id, owner, project, product = _world(db)
        from tests.scm.test_project_supply_service_ladder import _group_sites

        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
            required_date=date(2026, 9, 3),
        )

        # Revision 1: overseas, raises a row.
        first = _confirm(db, order, actor_user_id=owner, origin_by_line={str(line.id): "overseas"})
        assert first["created"] == 1
        first_row = _raised_rows(db, line.id)[0]
        first_row_id = first_row.id
        first_state = first_row.state
        first_verb = first_row.verb

        # Revision 2: same product, now resolved local. The old row must be untouched:
        # not re-raised (no second row), not cancelled (state/verb unchanged).
        second = _confirm(db, order, actor_user_id=owner, origin_by_line={str(line.id): "local"})

        assert second["created"] == 0
        rows = (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.so_line_id == line.id)
            .all()
        )
        assert [r.id for r in rows] == [first_row_id]
        assert rows[0].state == first_state
        assert rows[0].verb == first_verb


# --------------------------------------------------------------------------- #
# AC-2.18: a carried line (decided earlier, untouched now) whose product is local is
# skipped the same way
# --------------------------------------------------------------------------- #


def test_carried_local_line_skipped():
    with blank_session() as db:
        company_id, owner, project, product_local = _world(db)
        from tests.test_so_supply_confirmation import _product
        from tests.scm.test_project_supply_service_ladder import _group_sites

        product_other = _product(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        order, local_line, _cso1, _cline1 = _seed_line(
            db, company_id, project, product_local, own, qty_ordered="10",
            required_date=date(2026, 9, 3), line_no=10,
        )
        from tests.test_so_supply_confirmation import _core_line, _core_so, _project_line

        core_so2 = _core_so(db, company_id)
        core_line2 = _core_line(
            db, core_so2, product_other, own, qty_ordered="6", required_date=date(2026, 9, 3),
        )
        other_line = _project_line(db, order, line_no=20, product=product_other, core_line=core_line2)
        db.commit()

        # Revision 1: both lines decided, local line raises nothing, other line raises one row.
        first = _confirm(
            db, order, actor_user_id=owner,
            origin_by_line={str(local_line.id): "local", str(other_line.id): "overseas"},
        )
        assert first["created"] == 1

        # Revision 2: only the OTHER line is re-decided; the local line is CARRIED
        # (present in buy_lines, `carried` semantics) and must still raise nothing.
        #
        # `uq_so_supply_decisions_active` allows only ONE active revision per order, and
        # revision 1 (from `_confirm()`) is already it - so this decision follows this
        # file's OWN `_confirm()` convention (`"active" if revision == 1 else
        # "superseded"`) rather than hard-coding "active", the same as
        # `test_project_order_inquiry.py`'s identical helper, whose own tests call it
        # twice on one order (`test_a_later_confirmation_with_buy_raises_the_header_then`)
        # without ever touching revision 1's state.
        service = ProjectOrderInquiryService(db)
        revision = (
            db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == order.id)
            .count()
            + 1
        )
        decision = SOSupplyDecision(
            id=_u(), company_id=order.company_id, project_sales_order_id=order.id,
            revision_no=revision, state="active" if revision == 1 else "superseded",
            line_snapshots=[{"line_no": local_line.line_no}, {"line_no": other_line.line_no}],
            confirmed_by=owner, confirmed_at=datetime.utcnow(),
        )
        db.add(decision)
        db.flush()
        buy_lines = [
            {
                "line": local_line, "line_no": local_line.line_no,
                "item_code": service._product_code(local_line.product_id),
                "buy_qty": Decimal(str(local_line.qty)), "required_date": local_line.delivery_date,
                "stock_location": local_line.stock_location, "origin": "local", "carried": True,
            },
            {
                "line": other_line, "line_no": other_line.line_no,
                "item_code": service._product_code(other_line.product_id),
                "buy_qty": Decimal(str(other_line.qty)), "required_date": other_line.delivery_date,
                "stock_location": other_line.stock_location, "origin": "overseas",
            },
        ]
        second = service.refresh_for_decision(order, decision, buy_lines, actor_user_id=owner)

        assert _raised_rows(db, local_line.id) == []
        # The OTHER line is actively re-decided (not carried), so its revision-1 row is
        # superseded (CANCELLED, never edited in place - the docstring's own rule) and a
        # fresh row raised under revision 2: two PHYSICAL rows, exactly one of them still
        # standing. `_raised_rows` matches on verb alone, so the still-open row is the one
        # this assertion is about.
        still_open = [
            row for row in _raised_rows(db, other_line.id) if row.state != INQUIRY_CANCELLED
        ]
        assert len(still_open) == 1


# --------------------------------------------------------------------------- #
# AC-2.19: SCM demand shows no project demand for a confirmed local Buy
# --------------------------------------------------------------------------- #


def test_scm_demand_sees_no_local_buy():
    from tests._pg_fixture import pg_session

    with pg_session() as db:
        company_id, owner, project, product = _world(db)
        from tests.scm.test_project_supply_service_ladder import _group_sites

        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        order, line, _core_so, core_line = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
            required_date=date(2026, 9, 3),
        )

        result = _confirm(db, order, actor_user_id=owner, origin_by_line={str(line.id): "local"})
        assert result["created"] == 0

        # `project_committed` is the view's own exposed column (498_committed_v_bundled_qty.py);
        # `project_qty` is internal to the view's CTE and not selectable from the outside.
        project_committed = db.execute(
            text(
                "SELECT COALESCE(SUM(project_committed), 0) FROM scm.committed_v "
                "WHERE product_id = :p AND warehouse_id = :w"
            ),
            {"p": str(product.id), "w": str(own.id)},
        ).scalar()
        assert float(project_committed or 0) == 0.0
