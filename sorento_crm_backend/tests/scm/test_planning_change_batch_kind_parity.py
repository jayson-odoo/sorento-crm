"""Slice A, AC-A5b (`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`):
`build_batch` is the single sink for every trigger (SO book upload, AutoCount ingest, manual
edit) - a hand-built `Diff` carrying a CLOSED, an ADDED and a PRODUCT_CHANGED change must map
to the SAME row kinds (`cancelled` / `added` / `product_changed`) the manual-edit tests in
`test_planning_change_diff_parity.py` assert, because they all pass through this one function.

Helpers (`_client`/`api`/`_core_so`/`_core_line`/`_project_so`/`_project_line`/`_product`/
`_line_payload`/`_confirm`) are imported from `tests.test_planning_changes` rather than
copied - `tests/scm/test_planning_change_gate_held_or_inquiry.py` already establishes this
import-not-copy convention for this exact `(client, world)` fixture shape. Postgres only,
every FK seeded here.
"""
from __future__ import annotations

from datetime import date

from app.services import planning_change_service
from app.services.scm.outstanding_diff import ADDED, CLOSED, Change, Diff, Line

from tests.test_planning_changes import (  # noqa: F401  (api is the fixture)
    _confirm,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    api,
)

OLD = date(2026, 8, 20)
NEW = date(2026, 9, 3)


def _build(db, world, core_so, changes):
    return planning_change_service.build_batch(
        db,
        Diff(scope_documents=(core_so.so_number,), changes=[c for c, _ in changes]),
        applied_line_ids={id(c): str(core_line.id) for c, core_line in changes},
        order_ids={core_so.so_number: str(core_so.id)},
        actor=world.actor, import_job_id=None, file_name="book.xlsx",
    )


def test_build_batch_maps_the_three_diff_kinds_the_same_for_every_trigger(api):
    client, world = api
    db = world.db

    old_product = _product(db)
    new_product = _product(db)
    added_product = _product(db)

    core_so = _core_so(db, world.company_id)
    closing_core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40",
                              required_date=OLD)
    swapping_core = _core_line(db, core_so, old_product, world.own_wh, qty_ordered="72",
                               required_date=OLD)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    closing_line = _project_line(db, order, line_no=1, product=world.product,
                                 core_line=closing_core)
    swapping_line = _project_line(db, order, line_no=2, product=old_product,
                                  core_line=swapping_core)
    # A held line on an order confirmed by the SAME held Buy path the manual-edit tests
    # use - both lines are held so the gate (held-or-inquiry) passes for both.
    _confirm(client, order.id, {"lines": [
        _line_payload(closing_line.id, buy_qty="40", buy_reason="ZZT no stock anywhere"),
        _line_payload(swapping_line.id, buy_qty="72", buy_reason="ZZT no stock anywhere"),
    ]})

    # A THIRD core line, never adopted onto any project mirror - only used to carry the
    # ADDED change's `core_line_id` (an `added` change has no "before" mirror line).
    added_core = _core_line(db, core_so, added_product, world.own_wh, qty_ordered="10",
                            required_date=NEW)
    db.commit()

    from app.services.scm.outstanding_diff import PRODUCT_CHANGED

    closed_change = Change(
        CLOSED, core_so.so_number, world.product.product_code, world.own_wh.warehouse_code,
        before=Line(doc_number=core_so.so_number, item_code=world.product.product_code,
                   location=world.own_wh.warehouse_code, qty=40.0, required_date=OLD,
                   row_ref=str(closing_core.id)),
        after=None,
    )
    added_change = Change(
        ADDED, core_so.so_number, added_product.product_code, world.own_wh.warehouse_code,
        before=None,
        after=Line(doc_number=core_so.so_number, item_code=added_product.product_code,
                  location=world.own_wh.warehouse_code, qty=10.0, required_date=NEW,
                  row_ref=str(added_core.id)),
    )
    product_changed = Change(
        PRODUCT_CHANGED, core_so.so_number, new_product.product_code,
        world.own_wh.warehouse_code,
        before=Line(doc_number=core_so.so_number, item_code=old_product.product_code,
                   location=world.own_wh.warehouse_code, qty=72.0, required_date=OLD,
                   row_ref=str(swapping_core.id)),
        after=Line(doc_number=core_so.so_number, item_code=new_product.product_code,
                  location=world.own_wh.warehouse_code, qty=72.0, required_date=OLD,
                  row_ref=str(swapping_core.id)),
    )

    batch = _build(db, world, core_so, [
        (closed_change, closing_core),
        (added_change, added_core),
        (product_changed, swapping_core),
    ])
    db.commit()

    assert batch is not None
    rows = (
        db.query(planning_change_service.PlanningChangeRow)
        .filter_by(batch_id=batch.id)
        .all()
    )
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"cancelled", "added", "product_changed"}, sorted(by_kind)

    cancelled_row = by_kind["cancelled"]
    assert cancelled_row.from_json["qty"] == "40"
    assert cancelled_row.to_json.get("status") == "closed"

    added_row = by_kind["added"]
    assert added_row.to_json["qty"] == "10"
    assert added_row.item_code == added_product.product_code
    assert not (added_row.from_json or {}).get("qty")

    product_changed_row = by_kind["product_changed"]
    assert product_changed_row.from_json["item_code"] == old_product.product_code
    assert product_changed_row.to_json["item_code"] == new_product.product_code
    assert product_changed_row.item_code == new_product.product_code
