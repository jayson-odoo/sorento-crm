"""local-supplier Buy routing behind a system setting (PLAN-local-buy-routing-toggle.md).

RED for Phase 2: `system_settings.local_buy_routing_enabled` does not exist yet (the test
DB, `sorento_lbrt_ci`, is migrated to main's head WITHOUT the new column), so every test
below that touches the column fails with an `AttributeError` / `UndefinedColumn` against
TODAY's code - not a fixture bug. Contract this file drives:

* `SystemSetting.local_buy_routing_enabled`: Boolean, not null, server default false.
* `buy_origin_by_product(db, ids)` reads that setting FIRST. Off (the default): every id
  answers `None` and NO statement touches `product_suppliers` or `purchase_order_lines`.
  On: today's answers, unchanged (`tests/scm/test_supply_origin.py` pins the chain itself).
* The board / confirm callers already do `origin_by_product.get(pid, "overseas")`, and
  `dict.get` returns the stored `None` when the key is present - so a caller needs no
  change at all for the whole rule to disappear when the setting is off.
* Settings API: `local_buy_routing_enabled` in the update schema, the GET dict, POST saves
  it.

Fixtures reused with the justification that earned them elsewhere: `tests.scm.
test_project_supply_service_ladder._world` / `_seed_line` / `_group_sites` build the
minimum project-SO + core-SO + line graph every ladder test relies on; `tests.scm.
test_confirm_local_buy_no_oi._confirm` / `_raised_rows` are the one writer of a real
`SOSupplyDecision` + `refresh_for_decision` call already proven against this schema;
`tests.scm.test_summary_order_service._supplier` / `_link` and `tests.scm.
test_supply_origin._country` / `_add_product` are the supplier/country graph
`buy_origin_by_product` itself is pinned against. Postgres only, `blank_session()` /
`pg_session()`, never sqlite.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text

from app.models.user import SystemSetting

from tests._pg_fixture import blank_session, pg_session
from tests.scm.test_confirm_local_buy_no_oi import _confirm, _raised_rows
from tests.scm.test_project_supply_service_ladder import _group_sites, _seed_line, _world
# `db`/`chain` are the pg_session graph `buy_origin_by_product` is pinned against in
# `tests/scm/test_supply_origin.py` - same fixtures, same justification, reused here.
from tests.scm.test_summary_order_service import _link, _supplier, chain, db  # noqa: F401
from tests.scm.test_supply_origin import _country
from tests.test_so_supply_confirmation import _product

MARKER = "ZZTLBRT"


def _u() -> str:
    return str(uuid.uuid4())


def _set_flag(db, value: bool) -> SystemSetting:
    """Get-or-create the singleton row and flip the flag, per the lane brief.

    Written through `db.query(...).update({SystemSetting.local_buy_routing_enabled:
    ...})` rather than a plain `row.local_buy_routing_enabled = value` attribute set:
    a bare instance-attribute assignment for a column the mapped class does not
    (yet) declare is silently accepted by plain Python and never reaches SQLAlchemy's
    unit of work at all, so it would pass today with the column entirely missing -
    the exact false-green the class-attribute reference here is written to rule out.
    Referencing `SystemSetting.local_buy_routing_enabled` fails loudly (AttributeError)
    the moment the model has no such column, which is the honest red this lane wants.
    Still ORM, not raw SQL, per the lane brief.
    """
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=_u())
        db.add(row)
        db.flush()
    db.query(SystemSetting).filter(SystemSetting.id == row.id).update(
        {SystemSetting.local_buy_routing_enabled: value}
    )
    db.flush()
    db.expire(row)
    return row


def _my_linked_product(db):
    """A fresh product whose PRIMARY `product_suppliers` link is a Malaysian supplier -
    the shape AC-6/AC-8/AC-9/AC-10 all exercise: the resolver must ignore this link
    entirely while the setting is off."""
    product = _product(db)
    my = _country(db, "MY", "Malaysia")
    supplier = _supplier(db, f"zzt-lbrt-my-{_u()[:6]}")
    supplier.country_id = my.id
    db.flush()
    _link(db, product, supplier, primary=True)
    return product


# --------------------------------------------------------------------------------- #
# 1. AC-1: the column itself
# --------------------------------------------------------------------------------- #


def test_setting_column_defaults_false():
    with blank_session() as db:
        row = SystemSetting(id=_u())
        db.add(row)
        db.flush()
        db.refresh(row)

        assert row.local_buy_routing_enabled is False


# --------------------------------------------------------------------------------- #
# 2. AC-5: off answers None for every id, no origin SQL runs at all
# --------------------------------------------------------------------------------- #


def test_resolver_off_returns_none_for_every_id_and_runs_no_origin_sql():
    from app.services.scm.supply_origin import buy_origin_by_product

    with blank_session() as db:
        # No settings row at all: off is the default whether or not the singleton
        # exists yet, per AC-2's "Default false" for both branches.
        product_ids = [_u(), _u(), _u()]
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        connection = db.connection()
        event.listen(connection, "before_cursor_execute", _capture)
        try:
            origins = buy_origin_by_product(db, product_ids)
        finally:
            event.remove(connection, "before_cursor_execute", _capture)

        assert origins == {pid: None for pid in product_ids}
        assert not any(
            "product_suppliers" in s or "purchase_order_lines" in s for s in statements
        ), "off must never touch either origin table"


# --------------------------------------------------------------------------------- #
# 3. AC-12: on, the resolver's answers are untouched (MY primary link local, CN newest
#    PO overseas - the two-product shape the captain's list names)
# --------------------------------------------------------------------------------- #


def test_resolver_on_answers_local_for_my_supplier(db, chain):
    from app.services.scm.supply_origin import buy_origin_by_product
    from tests.scm.test_summary_order_service import _po
    from tests.scm.test_supply_origin import _add_product

    f = chain
    my = _country(db, "MY", "Malaysia")
    cn = _country(db, "CN", "China")
    _set_flag(db, True)

    my_supplier = _supplier(db, f"zzt-lbrt-on-my-{_u()[:6]}")
    my_supplier.country_id = my.id
    db.flush()
    _link(db, f["product"], my_supplier, primary=True)

    cn_supplier = _supplier(db, f"zzt-lbrt-on-cn-{_u()[:6]}")
    cn_supplier.country_id = cn.id
    db.flush()
    cn_product = _add_product(db, f, stem="CNPO")
    _po(db, cn_product, f["bin"], 10, supplier=cn_supplier)

    origins = buy_origin_by_product(db, [f["product"].id, cn_product.id])

    assert origins[str(f["product"].id)] == "local"
    assert origins[str(cn_product.id)] == "overseas"


# --------------------------------------------------------------------------------- #
# 4. AC-6: board contributions carry buy_origin: null for a MY-supplier product, off
# --------------------------------------------------------------------------------- #


def test_board_payload_buy_origin_is_null_when_off():
    from app.models.country import Country
    from app.models.procurement import ProductSupplier, Supplier
    from tests.test_fulfilment_board import TODAY, _line, _order, _product, _service, _stock, _warehouse

    with blank_session() as db:
        # `_product`/`_warehouse`/`_order`/`_line` (`tests/test_fulfilment_board.py`) are
        # the proven board-matching shape - `demand_class`, `segment`, `purchasing_status`
        # all stamped - rather than a hand-rolled insert that quietly never reaches a cell.
        product = _product(db, f"ZZT-{MARKER}-{_u()[:6]}")
        warehouse = _warehouse(db, f"ZZT{_u()[:6]}")
        _stock(db, product, warehouse, on_hand=100)

        my = Country(id=_u(), code="MY", name="Malaysia")
        db.add(my)
        db.flush()
        supplier = Supplier(
            id=_u(), supplier_code=f"ZZT{_u()[:8]}", supplier_name="zzt local sdn bhd",
            country_id=my.id,
        )
        db.add(supplier)
        db.flush()
        db.add(ProductSupplier(
            id=_u(), product_id=product.id, supplier_id=supplier.id,
            standard_lead_time_days=14, is_primary_supplier=True,
        ))
        db.flush()

        order = _order(db, so_number=f"ZZT-{_u()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=warehouse)
        db.commit()

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contributions = [c for cell in board["cells"] for c in cell["contributions"]]
        assert len(contributions) == 1, "the seed must actually reach the board"
        assert contributions[0]["buy_origin"] is None


# --------------------------------------------------------------------------------- #
# 5. AC-8: confirming a Buy on a MY-supplier product, off, raises the OI row
# --------------------------------------------------------------------------------- #


def test_confirm_off_raises_oi_row_for_my_supplier_buy():
    from app.models.project_so import INQUIRY_RAISED, OrderInquiry
    from app.services.scm.supply_origin import buy_origin_by_product

    with blank_session() as db:
        company_id, owner, project, _unused = _world(db)
        product = _my_linked_product(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
            required_date=date(2026, 9, 3),
        )

        origins = buy_origin_by_product(db, [str(product.id)])
        assert origins[str(product.id)] is None, (
            "off must ignore the MY primary link entirely"
        )

        result = _confirm(
            db, order, actor_user_id=owner,
            origin_by_line={str(line.id): origins[str(product.id)]},
        )

        assert result["created"] == 1
        rows = _raised_rows(db, line.id)
        assert len(rows) == 1
        assert rows[0].state == INQUIRY_RAISED
        inquiry = (
            db.query(OrderInquiry)
            .filter(OrderInquiry.project_sales_order_id == order.id)
            .one()
        )
        assert inquiry is not None


# --------------------------------------------------------------------------------- #
# 6. AC-9: a line confirmed local while the setting was on is raised on the next
#    confirm after the setting is off, even carried unchanged
# --------------------------------------------------------------------------------- #


def test_confirm_off_carried_line_previously_skipped_is_raised():
    from app.models.project_so import INQUIRY_RAISED, SOSupplyDecision
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from app.services.scm.supply_origin import buy_origin_by_product

    with blank_session() as db:
        company_id, owner, project, _unused = _world(db)
        product = _my_linked_product(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]

        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
            required_date=date(2026, 9, 3),
        )

        # Revision 1: setting ON, the resolver says local, the line is skipped - no row.
        _set_flag(db, True)
        origins_on = buy_origin_by_product(db, [str(product.id)])
        assert origins_on[str(product.id)] == "local"
        first = _confirm(
            db, order, actor_user_id=owner,
            origin_by_line={str(line.id): origins_on[str(product.id)]},
        )
        assert first["created"] == 0
        assert _raised_rows(db, line.id) == []

        # Flip off. Revision 2 carries the SAME line, untouched, but the resolver now
        # answers None for it - the loop must raise a row it skipped a moment ago.
        _set_flag(db, False)
        origins_off = buy_origin_by_product(db, [str(product.id)])
        assert origins_off[str(product.id)] is None

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
            line_snapshots=[{"line_no": line.line_no}],
            confirmed_by=owner, confirmed_at=datetime.utcnow(),
        )
        db.add(decision)
        db.flush()
        buy_lines = [{
            "line": line, "line_no": line.line_no,
            "item_code": service._product_code(line.product_id),
            "buy_qty": Decimal(str(line.qty)), "required_date": line.delivery_date,
            "stock_location": line.stock_location,
            "origin": origins_off[str(product.id)],
            "carried": True,
        }]
        service.refresh_for_decision(order, decision, buy_lines, actor_user_id=owner)

        rows = _raised_rows(db, line.id)
        assert len(rows) == 1
        assert rows[0].state == INQUIRY_RAISED


# --------------------------------------------------------------------------------- #
# 7. AC-10: SCM reorder demand counts that Buy once the setting is off
# --------------------------------------------------------------------------------- #


def test_scm_demand_sees_buy_when_off():
    from app.services.scm.supply_origin import buy_origin_by_product

    with pg_session() as db:
        company_id, owner, project, _unused = _world(db)
        product = _my_linked_product(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        order, line, _core_so, _core_line = _seed_line(
            db, company_id, project, product, own, qty_ordered="10",
            required_date=date(2026, 9, 3),
        )

        origins = buy_origin_by_product(db, [str(product.id)])
        assert origins[str(product.id)] is None

        result = _confirm(
            db, order, actor_user_id=owner,
            origin_by_line={str(line.id): origins[str(product.id)]},
        )
        assert result["created"] == 1

        project_committed = db.execute(
            text(
                "SELECT COALESCE(SUM(project_committed), 0) FROM scm.committed_v "
                "WHERE product_id = :p AND warehouse_id = :w"
            ),
            {"p": str(product.id), "w": str(own.id)},
        ).scalar()
        assert float(project_committed or 0) == 10.0


# --------------------------------------------------------------------------------- #
# 8. AC-2/AC-3: settings API, both dict-builder branches (row present, row absent)
# --------------------------------------------------------------------------------- #

GENERAL_ENDPOINT = "/api/v1/user-management/settings/general"
SETTINGS_ENDPOINT = "/api/v1/user-management/settings/"
VIEW_PERMISSION = "user_management.settings.view"
EDIT_PERMISSION = "user_management.settings.edit"


@pytest.fixture
def api_db():
    with blank_session() as s:
        yield s


@pytest.fixture
def api(api_db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    allow = {VIEW_PERMISSION, EDIT_PERMISSION}

    def _override_db():
        yield api_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {
        "id": _u(), "email": "zzt-lbrt-settings@zzt.test",
    }
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_settings_api_get_and_post_carry_the_field(api, api_db):
    """AC-2/AC-3, the GET dict builder (`settings.py`'s big `"settings": {...} if
    settings else None` literal): with a row present, the field reads its stored value
    (default False), and a POST to `/general` saves a new value the next GET reads back."""
    row = SystemSetting(id=_u())
    api_db.add(row)
    api_db.commit()

    resp = api.get(SETTINGS_ENDPOINT)
    assert resp.status_code == 200
    assert resp.json()["settings"]["local_buy_routing_enabled"] is False

    resp = api.post(GENERAL_ENDPOINT, json={"local_buy_routing_enabled": True})
    assert resp.status_code == 200

    resp = api.get(SETTINGS_ENDPOINT)
    assert resp.status_code == 200
    assert resp.json()["settings"]["local_buy_routing_enabled"] is True


def test_settings_api_get_returns_null_settings_block_when_no_row_exists(api, api_db):
    """The OTHER branch of the SAME `"settings": {...} if settings else None` ternary
    (measured: the whole block, not just this field, is `None` with no row at all) -
    a regression guard that the new column does not disturb that existing shape."""
    assert api_db.query(SystemSetting).first() is None, "blank schema, nothing seeded"

    resp = api.get(SETTINGS_ENDPOINT)

    assert resp.status_code == 200
    assert resp.json()["settings"] is None


def test_settings_api_post_null_resets_the_field_to_false(api, api_db):
    """AC-3 + the plan's "defaults dict" bullet (measured precedent:
    `chatbot_stock_denial_enabled` is NOT NULL with a default, so an explicit JSON
    `null` in the POST body must reset it to that default rather than attempt to write
    NULL into a NOT NULL column and 500 at commit - `_CHATBOT_COLUMN_DEFAULTS` is the
    second manual dict the lane brief names). `local_buy_routing_enabled` is the same
    shape (Boolean, not null, server default false), so it needs the same entry."""
    row = SystemSetting(id=_u())
    api_db.add(row)
    api_db.commit()

    resp = api.post(GENERAL_ENDPOINT, json={"local_buy_routing_enabled": True})
    assert resp.status_code == 200
    assert api.get(SETTINGS_ENDPOINT).json()["settings"]["local_buy_routing_enabled"] is True

    resp = api.post(GENERAL_ENDPOINT, json={"local_buy_routing_enabled": None})
    assert resp.status_code == 200, "an explicit null must reset, not 500 on a NOT NULL column"

    resp = api.get(SETTINGS_ENDPOINT)
    assert resp.json()["settings"]["local_buy_routing_enabled"] is False
