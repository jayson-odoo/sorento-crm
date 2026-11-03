"""CONFIRM-DIALOG-SPEED regression: a planning-change DRY RUN keeps its placement pass.

The path crew profiled on SO373923 (pending AutoCount batch): `planning_change_service`
defers the pass and then calls `auto_place_for_confirmed_products` (76% of a warm dry run).
Crew ruling (3 Nov 2026): keep the pass in the dry run, as the press runs it, and make it
cheap instead (`tests/test_auto_place_document_memo.py`), so the dry run stays the press's own
write by construction. An earlier "ORDER 25 vs ORDER 15" measurement here was an artifact of
stale handover items on the test session (the post-commit listeners were not registered; see
PREVIEW-EMAIL-PLANCHANGE #2135, which owns the preview/press parity tests). This module only
pins that the dry run runs the pass and still answers the email's lines; it pins no words.
Its own module because the fixture chain (`api`, `world`, `_form_three`)
is the real-DB one of `tests/test_planning_change_apply_on_board.py`, which clashes by name
with the blank-schema `api` of the ordinary-confirm module.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.procurement import PurchaseOrder, PurchaseOrderLine

from .test_confirm_preview_runs_placement import _PlacementSpy
from .test_planning_change_apply_on_board import (  # noqa: F401 - fixtures
    BASE,
    _confirm,
    _core_line,
    _core_so,
    _form_three,
    _project_line,
    _project_so,
    _line_payload,
    _uid,
    api,
    world,
)

URL = f"{BASE}/fulfilment-planning/confirm-all"


def _open_pool_po_line(world, *, qty):
    """An open purchase order line at the pool bin (a project bin is locked to its project),
    landing inside the other order's lead-time window, so the pass places that row on it."""
    db = world.db
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        issue_date=date(2026, 6, 1), status="active",
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.pool_wh.id,
        qty_ordered=Decimal(str(qty)), qty_received=Decimal("0"),
        expected_date=date(2027, 2, 20), line_status="open",
    ))
    db.commit()


def _another_orders_raised_row(fixture):
    """Another sales order of the same product, confirmed as a Buy BEFORE the pool line
    exists, so its ORDER row is still raised and unlinked: the product-scoped pass walks it
    (on prod it walked 489 such rows for SO373923's 8 products)."""
    client, world = fixture["client"], fixture["world"]
    db = world.db
    core_so = _core_so(db, world.company_id)
    core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="7")
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core)
    db.commit()
    response = _confirm(client, order.id, [_line_payload(line.id, buy_qty="7")])
    assert response.status_code == 200, response.text


def _post(fixture, *, preview):
    order = fixture["order"]
    body = {
        "orders": [
            {
                "pso_id": str(order.id),
                "batch_id": str(fixture["batch"].id),
                "lines": [_line_payload(fixture["lines"][0].id, buy_qty="25")],
            }
        ],
        **({"preview": True} if preview else {}),
    }
    response = fixture["client"].post(URL, json=body)
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is True, result
    return result


def test_a_planning_change_dry_run_runs_the_placement_pass(api, monkeypatch):
    """The pass runs in the dry run, and the dry run still answers the email's own lines."""
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    # As prod does at startup (app/main.py): without it the session keeps the fixture's
    # earlier handover items and they leak into this write's email.
    register_order_inquiry_post_commit_dispatch()
    fixture = _form_three(api)
    world = fixture["world"]
    _another_orders_raised_row(fixture)
    _open_pool_po_line(world, qty=500)
    spy = _PlacementSpy(monkeypatch)

    preview = _post(fixture, preview=True)

    assert spy.calls >= 1 and spy.placed > 0, (spy.calls, spy.placed)
    assert preview["email_lines"], preview
    assert preview["inquiry_rows"], preview
