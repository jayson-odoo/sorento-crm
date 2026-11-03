"""CONFIRM-DIALOG-SPEED regression: a confirm-all DRY RUN runs the draft-link placement pass.

Crew profile of the prod clone (3 Nov 2026, SO373923): the pass was 76% of a warm dry run.
Skipping it in a dry run was measured and refused (crew ruling, 3 Nov): on the planning-change
path the email's REMARK changes without it
(`tests/test_confirm_preview_runs_placement_planning_change.py`). The pass stays, in the dry
run and the real press alike, and is made cheap instead
(`tests/test_auto_place_document_memo.py`).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.project_so import OrderInquiryLink
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_confirm_all_preview import URL, _two_line_order
from .test_so_supply_confirmation import _line_payload, _suffix, api  # noqa: F401 - fixture


def _open_po_line(world, *, qty):
    """An open purchase order line for the order's product at the pool bin (a project bin
    is locked to its project, so the cascade would not take it): what the placement pass
    draft-links a freshly raised ORDER row to."""
    db = world.db
    po = PurchaseOrder(
        id=str(uuid.uuid4()), company_id=world.company_id, po_number=f"ZZT-PO-{_suffix()}",
        issue_date=date.today(), status="active",
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=str(uuid.uuid4()), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.pool_wh.id,
        qty_ordered=Decimal(str(qty)), qty_received=Decimal("0"),
        expected_date=date.today() + timedelta(days=14), line_status="open",
    )
    db.add(line)
    db.commit()
    return line


class _PlacementSpy:
    """Counts what the placement pass placed, read off its own answer."""

    def __init__(self, monkeypatch):
        self.calls = 0
        self.placed = 0
        self.results = []
        real = ProjectOrderInquiryService.auto_place_for_products
        spy = self

        def wrapped(service, *args, **kwargs):
            result = real(service, *args, **kwargs)
            spy.calls += 1
            spy.results.append(result)
            spy.placed += int((result or {}).get("placed_rows") or 0)
            spy.placed += int((result or {}).get("allocations") or 0)
            return result

        monkeypatch.setattr(ProjectOrderInquiryService, "auto_place_for_products", wrapped)


def _answer(client, order, lines):
    response = client.post(
        URL, json={"orders": [{"pso_id": order.id, "lines": lines}], "preview": True}
    )
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) == 1 and results[0]["ok"] is True, results
    return results[0]


def test_a_dry_run_runs_the_placement_pass_and_writes_no_link(api, monkeypatch):
    client, world = api
    order, _core_so, (line_a, line_b) = _two_line_order(world)
    _open_po_line(world, qty=500)
    lines = [_line_payload(line_a.id, buy_qty="50"), _line_payload(line_b.id, buy_qty="50")]
    before = world.db.query(OrderInquiryLink).count()
    spy = _PlacementSpy(monkeypatch)

    result = _answer(client, order, lines)

    assert spy.calls >= 1 and spy.placed > 0, (spy.calls, spy.placed)
    assert len(result["email_lines"]) == 2, result
    world.db.expire_all()
    assert world.db.query(OrderInquiryLink).count() == before


def test_the_real_press_still_runs_the_placement_pass(api, monkeypatch):
    client, world = api
    order, _core_so, (line_a, line_b) = _two_line_order(world)
    _open_po_line(world, qty=500)
    spy = _PlacementSpy(monkeypatch)
    response = client.post(
        URL,
        json={
            "orders": [
                {
                    "pso_id": order.id,
                    "lines": [
                        _line_payload(line_a.id, buy_qty="50"),
                        _line_payload(line_b.id, buy_qty="50"),
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["ok"] is True
    assert spy.calls >= 1 and spy.placed > 0, (spy.calls, spy.placed)
