"""RED tests for cost lists (#1288, Lane A, AC-CL-01 to AC-CL-08).

TEST-FIRST: `app/models/cost_price.py`, `app/services/procurement/supplier_cost_service.py`
and the cost-list routes do not exist yet. Every import of a not-yet-existing name sits
INSIDE the test body that needs it, so a missing model/module fails only that test, not
the whole file at collection - a route that is not yet mounted 404s the same way.

`price_in_force`/`cost_status` are pure functions over duck-typed rows (`unit_cost`,
`currency`, `start_date`, `end_date`, `created_at`) - no database needed for AC-CL-01.
Everything else goes through `tests.support.cost_price_env.CostPriceEnv`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.support.cost_price_env import (
    PS_EDIT_PERM,
    PS_VIEW_PERM,
    cost_price_env,
)

TODAY = date(2026, 9, 27)


def _row(unit_cost, *, currency="CNY", start=None, end=None, created_at=None):
    return SimpleNamespace(
        unit_cost=Decimal(str(unit_cost)), currency=currency, start_date=start, end_date=end,
        created_at=created_at or datetime(2026, 1, 1),
    )


# --------------------------------------------------------------------------------- AC-CL-01


def test_price_in_force_always_row_alone_wins():
    from app.services.procurement.supplier_cost_service import price_in_force

    always = _row(100, created_at=datetime(2026, 1, 1))
    assert price_in_force([always], TODAY) is always


def test_price_in_force_dated_row_inside_range_beats_always():
    from app.services.procurement.supplier_cost_service import price_in_force

    always = _row(100, created_at=datetime(2026, 1, 1))
    dated = _row(150, start=date(2026, 9, 1), end=date(2026, 9, 30), created_at=datetime(2026, 1, 2))
    assert price_in_force([always, dated], TODAY) is dated


def test_price_in_force_always_wins_again_after_dated_end():
    from app.services.procurement.supplier_cost_service import price_in_force

    always = _row(100, created_at=datetime(2026, 1, 1))
    ended = _row(150, start=date(2026, 8, 1), end=date(2026, 8, 31), created_at=datetime(2026, 1, 2))
    assert price_in_force([always, ended], TODAY) is always


def test_price_in_force_two_covering_rows_the_later_start_wins():
    from app.services.procurement.supplier_cost_service import price_in_force

    earlier = _row(150, start=date(2026, 8, 1), created_at=datetime(2026, 1, 1))
    later = _row(200, start=date(2026, 9, 1), created_at=datetime(2026, 1, 2))
    assert price_in_force([earlier, later], TODAY) is later
    assert price_in_force([later, earlier], TODAY) is later  # order independent


def test_price_in_force_equal_starts_the_newest_created_at_wins():
    from app.services.procurement.supplier_cost_service import price_in_force

    older = _row(150, start=date(2026, 9, 1), created_at=datetime(2026, 1, 1))
    newer = _row(200, start=date(2026, 9, 1), created_at=datetime(2026, 6, 1))
    assert price_in_force([older, newer], TODAY) is newer


def test_price_in_force_none_when_every_row_ended_or_not_started():
    from app.services.procurement.supplier_cost_service import price_in_force

    ended = _row(150, start=date(2026, 1, 1), end=date(2026, 2, 1), created_at=datetime(2026, 1, 1))
    future = _row(200, start=date(2026, 12, 1), created_at=datetime(2026, 1, 1))
    assert price_in_force([ended, future], TODAY) is None


def test_price_in_force_boundaries_are_inclusive():
    from app.services.procurement.supplier_cost_service import price_in_force

    starts_today = _row(150, start=TODAY, created_at=datetime(2026, 1, 1))
    assert price_in_force([starts_today], TODAY) is starts_today

    ends_today = _row(150, start=date(2026, 1, 1), end=TODAY, created_at=datetime(2026, 1, 1))
    assert price_in_force([ends_today], TODAY) is ends_today


# --------------------------------------------------------------------------------- AC-CL-02


def test_cost_row_has_only_price_currency_and_dates():
    from app.models.cost_price import ProductSupplierCost

    cols = {c.name for c in ProductSupplierCost.__table__.columns}
    forbidden = {"basis", "shipping", "tax", "terms", "incoterm", "freight", "cost_basis"}
    assert not (cols & forbidden), cols & forbidden
    assert {"unit_cost", "currency", "start_date", "end_date"} <= cols


# --------------------------------------------------------------------------------- AC-CL-03


def test_end_before_start_is_422(cost_price_env):
    e = cost_price_env
    user = e.user(PS_EDIT_PERM)
    e.as_user(user)
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier)

    r = e.post_cost(link.id, {
        "unit_cost": 100.0, "currency": "CNY",
        "start_date": "2026-10-01", "end_date": "2026-09-01",
    })

    assert r.status_code == 422, r.text


def test_negative_price_is_422(cost_price_env):
    e = cost_price_env
    user = e.user(PS_EDIT_PERM)
    e.as_user(user)
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier)

    r = e.post_cost(link.id, {"unit_cost": -5.0, "currency": "CNY", "start_date": None, "end_date": None})

    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------------- AC-CL-04


def test_hand_edit_keeps_unit_cost_equal_price_in_force(cost_price_env):
    e = cost_price_env
    user = e.user(PS_EDIT_PERM)
    e.as_user(user)
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier, unit_cost=None, currency=None)

    r = e.post_cost(link.id, {"unit_cost": 468.0, "currency": "CNY", "start_date": None, "end_date": None})
    assert r.status_code == 201, r.text

    e.db.expire_all()
    from app.models.procurement import ProductSupplier

    refreshed = e.db.query(ProductSupplier).filter_by(id=link.id).one()
    assert refreshed.unit_cost == Decimal("468.00")
    assert refreshed.currency == "CNY"


def test_hand_edit_sets_unit_cost_null_when_nothing_in_force(cost_price_env):
    e = cost_price_env
    user = e.user(PS_EDIT_PERM)
    e.as_user(user)
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier, unit_cost=None, currency=None)

    create = e.post_cost(link.id, {
        "unit_cost": 468.0, "currency": "CNY",
        "start_date": "2026-01-01", "end_date": "2026-01-31",
    })
    assert create.status_code == 201, create.text
    cost_id = create.json()["id"]

    e.db.expire_all()
    from app.models.procurement import ProductSupplier

    refreshed = e.db.query(ProductSupplier).filter_by(id=link.id).one()
    # The row's own range has already lapsed (relative to `today`), so nothing is in
    # force: unit_cost must be null, never the ended row's stale price.
    assert refreshed.unit_cost is None


def test_link_without_cost_rows_is_never_written(cost_price_env):
    e = cost_price_env
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier, unit_cost=Decimal("10.00"), currency="MYR")
    e.db.commit()

    from app.services.procurement.supplier_cost_service import refresh_prices_in_force

    refresh_prices_in_force(e.db, TODAY)

    e.db.expire_all()
    from app.models.procurement import ProductSupplier

    refreshed = e.db.query(ProductSupplier).filter_by(id=link.id).one()
    assert refreshed.unit_cost == Decimal("10.00")
    assert refreshed.currency == "MYR"


# --------------------------------------------------------------------------------- AC-CL-05


def test_daily_tick_updates_links_and_writes_one_audit_row(cost_price_env):
    from app.models.cost_price import ProductSupplierCost
    from app.models.procurement import ProductSupplier

    e = cost_price_env
    supplier = e.supplier()
    scheduled_product = e.product(description="scheduled")
    ended_product = e.product(description="ended")
    scheduled_link = e.link(scheduled_product, supplier, unit_cost=Decimal("50.00"), currency="CNY")
    ended_link = e.link(ended_product, supplier, unit_cost=Decimal("80.00"), currency="CNY")

    e.db.add(ProductSupplierCost(
        product_supplier_id=scheduled_link.id, unit_cost=Decimal("60.00"), currency="CNY",
        start_date=TODAY, end_date=None,
    ))
    e.db.add(ProductSupplierCost(
        product_supplier_id=ended_link.id, unit_cost=Decimal("80.00"), currency="CNY",
        start_date=date(2026, 1, 1), end_date=date(2026, 8, 31),
    ))
    e.db.commit()

    from app.services.procurement.supplier_cost_service import refresh_prices_in_force

    changed = refresh_prices_in_force(e.db, TODAY)
    assert changed == 2

    e.db.expire_all()
    assert e.db.query(ProductSupplier).filter_by(id=scheduled_link.id).one().unit_cost == Decimal("60.00")
    assert e.db.query(ProductSupplier).filter_by(id=ended_link.id).one().unit_cost is None

    from app.models.audit import AuditLog

    tick_rows = e.db.query(AuditLog).filter(AuditLog.action == "SUPPLIER_COST_TICK").all()
    assert len(tick_rows) == 1, tick_rows

    again = refresh_prices_in_force(e.db, TODAY)
    assert again == 0
    assert e.db.query(AuditLog).filter(AuditLog.action == "SUPPLIER_COST_TICK").count() == 1


def test_daily_tick_is_scheduled():
    """A scheduler job is registered for the tick.

    Gap resolved (the captain's seam list names `refresh_prices_in_force` but not a
    scheduled-task `key`): `cost_price_daily_tick`, matching the snake_case, noun-first
    convention of the existing keys (`respond_contacts_sync`). Flag to the captain if the
    coder registers it under a different key - the assertion is on the shape
    (`TASK_HANDLERS` carries an entry), the exact string is the part open to negotiation.
    """
    from app.services.scheduled_task_service import TASK_HANDLERS

    assert "cost_price_daily_tick" in TASK_HANDLERS


# --------------------------------------------------------------------------------- AC-CL-06


def test_hand_edit_add_change_delete_audited_and_gated(cost_price_env):
    from app.models.audit import AuditLog

    e = cost_price_env
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier)

    no_perm_user = e.user()
    e.as_user(no_perm_user)
    assert e.post_cost(link.id, {"unit_cost": 100.0, "currency": "CNY"}).status_code == 403

    editor = e.user(PS_EDIT_PERM)
    e.as_user(editor)

    created = e.post_cost(link.id, {"unit_cost": 100.0, "currency": "CNY", "start_date": None, "end_date": None})
    assert created.status_code == 201, created.text
    cost_id = created.json()["id"]

    e.as_user(no_perm_user)
    assert e.put_cost(link.id, cost_id, {"unit_cost": 110.0, "currency": "CNY"}).status_code == 403
    assert e.delete_cost(link.id, cost_id).status_code == 403

    e.as_user(editor)
    updated = e.put_cost(link.id, cost_id, {
        "unit_cost": 110.0, "currency": "CNY", "start_date": None, "end_date": None,
    })
    assert updated.status_code == 200, updated.text

    deleted = e.delete_cost(link.id, cost_id)
    assert deleted.status_code == 200, deleted.text

    edit_rows = e.db.query(AuditLog).filter(AuditLog.action == "SUPPLIER_COST_LIST_EDIT").count()
    assert edit_rows == 3, edit_rows  # add, change, delete


def test_cost_delete_form_action_is_registered():
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE
    from app.services.form_action_registry import get_action

    action = get_action("product_supplier_cost.delete")
    assert action is not None
    assert action.entity_types == ("product_supplier_cost",)
    assert action.window == WINDOW_DESTRUCTIVE
    assert action.permission == PS_EDIT_PERM


# --------------------------------------------------------------------------------- contract
# (2.1 / 2.2 shapes, AC-CL-07 / AC-CL-08's data source)


def test_supplier_cost_lists_route_shape_and_statuses(cost_price_env):
    from app.models.cost_price import ProductSupplierCost

    e = cost_price_env
    viewer = e.user(PS_VIEW_PERM)
    e.as_user(viewer)
    supplier = e.supplier()
    always_product = e.product(description="always")
    scheduled_product = e.product(description="scheduled")
    always_link = e.link(always_product, supplier, unit_cost=Decimal("50.00"), currency="CNY")
    scheduled_link = e.link(scheduled_product, supplier, unit_cost=None, currency=None)

    e.db.add(ProductSupplierCost(
        product_supplier_id=always_link.id, unit_cost=Decimal("50.00"), currency="CNY",
        start_date=None, end_date=None,
    ))
    e.db.add(ProductSupplierCost(
        product_supplier_id=scheduled_link.id, unit_cost=Decimal("70.00"), currency="CNY",
        start_date=date(2099, 1, 1), end_date=None,
    ))
    e.db.commit()

    r = e.cost_lists(supplier.id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "today" in body
    by_link = {row["product_supplier_id"]: row for row in body["data"]}

    always_row = by_link[str(always_link.id)]
    assert always_row["costs"][0]["status"] == "always"

    scheduled_row = by_link[str(scheduled_link.id)]
    assert scheduled_row["costs"][0]["status"] == "scheduled"

    # status filter narrows the list
    filtered = e.cost_lists(supplier.id, status="scheduled")
    assert filtered.status_code == 200
    filtered_ids = {row["product_supplier_id"] for row in filtered.json()["data"]}
    assert filtered_ids == {str(scheduled_link.id)}


def test_product_suppliers_by_product_carries_costs(cost_price_env):
    from app.models.cost_price import ProductSupplierCost

    e = cost_price_env
    viewer = e.user(PS_VIEW_PERM)
    e.as_user(viewer)
    supplier = e.supplier()
    product = e.product()
    link = e.link(product, supplier, unit_cost=Decimal("50.00"), currency="CNY")
    e.db.add(ProductSupplierCost(
        product_supplier_id=link.id, unit_cost=Decimal("50.00"), currency="CNY",
        start_date=None, end_date=None,
    ))
    e.db.commit()

    r = e.product_suppliers_by_product(product.id)
    assert r.status_code == 200, r.text
    body = r.json()
    entries = body["data"] if isinstance(body, dict) and "data" in body else body
    entry = next(row for row in entries if row.get("id") == str(link.id) or row.get("product_supplier_id") == str(link.id))
    assert "costs" in entry
    assert entry["costs"][0]["unit_cost"] == 50.0
