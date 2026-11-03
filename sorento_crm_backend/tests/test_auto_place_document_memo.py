"""CONFIRM-DIALOG-SPEED: a placement pass reads each product's documents ONCE.

Crew profile of the prod clone (3 Nov 2026, SO373923): `auto_place_for_products` walked 489
open rows over 8 products and every row re-read its product's open purchase-order lines and
SPO allocations (`_candidates_for_row`): ~3,000 statements, 76% of a warm confirm-all dry run.
The pass now holds those two reads per product (`_document_rows_memo`).

Contract: the pass writes EXACTLY the same links and answers the same counts with the memo as
without it (the per-row reads are kept here as the oracle by patching the memo off), on a
seed where rows compete for scarce documents (so order and remaining matter), for a first
pass and a re-deal pass; and the document reads drop to one per product.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import event

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation
from app.models.project_so import (
    OrderInquiryLink,
    OrderInquiryRow,
    OrderInquirySuggestedLink,
)
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_so_supply_confirmation import (  # noqa: F401 - `api` is a fixture
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    _suffix,
    api,
)

ROWS = 9


def _raised_rows(client, world):
    """ROWS orders of the product, each confirmed as a Buy BEFORE any document exists, so
    every ORDER row is raised, awaiting and unlinked when the pass runs."""
    db = world.db
    for n in range(ROWS):
        order = _project_so(db, world.project)
        core_so = _core_so(db, world.company_id)
        core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=str(5 + n))
        line = _project_line(db, order, line_no=10, product=world.product, core_line=core)
        db.commit()
        response = client.post(
            f"{BASE}/sales-orders/{order.id}/confirm",
            json={"lines": [_line_payload(line.id, buy_qty=str(5 + n))]},
        )
        assert response.status_code == 200, response.text
    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.item_code == world.product.product_code)
        .all()
    )
    assert len(rows) == ROWS and all(r.state == "raised" for r in rows), [
        (r.state, r.ack_state) for r in rows
    ]
    return rows


def _documents(world):
    """Scarce supply at the pool bin: two PO lines and two SPO allocations whose total
    covers only part of the rows' need, at different dates, so which row gets what depends
    on the order and on every `remaining` the walk tracks."""
    db = world.db
    today = date.today()
    for qty, days in ((12, 20), (9, 45)):
        po = PurchaseOrder(
            id=str(uuid.uuid4()), company_id=world.company_id,
            po_number=f"ZZT-PO-{_suffix()}", issue_date=today, status="active",
        )
        db.add(po)
        db.flush()
        db.add(PurchaseOrderLine(
            id=str(uuid.uuid4()), company_id=world.company_id, purchase_order_id=po.id,
            product_id=world.product.id, warehouse_id=world.pool_wh.id,
            qty_ordered=Decimal(qty), qty_received=Decimal("0"),
            expected_date=today + timedelta(days=days), line_status="open",
        ))
    for qty, days in ((8, 30), (6, 60)):
        db.add(SPOAllocation(
            id=str(uuid.uuid4()), spo_number=f"ZZT-SPO-{_suffix()}", spo_line_number=1,
            product_id=world.product.id, warehouse_id=world.pool_wh.id,
            allocated_quantity=qty, quantity_received=0, receipt_status="pending",
            line_status="open", expected_date=today + timedelta(days=days),
            company_id=world.company_id,
        ))
    db.commit()


def _links(db, item_code):
    """Every link and every suggested link on the product's rows (an awaiting row's
    placement is a suggestion), keyed by what the row IS (its sales-order line, qty and
    state), not its id: a placement may split a row, and the split's id is new each run."""
    out = []
    for kind, model in (("link", OrderInquiryLink), ("suggested", OrderInquirySuggestedLink)):
        for link, row in (
            db.query(model, OrderInquiryRow)
            .join(OrderInquiryRow, OrderInquiryRow.id == model.row_id)
            .filter(OrderInquiryRow.item_code == item_code)
        ):
            out.append((
                kind, str(row.so_line_id), str(Decimal(row.qty).normalize()), str(row.state),
                str(link.po_line_id or ""), str(link.spo_allocation_id or ""),
                str(Decimal(link.qty).normalize()),
            ))
    return sorted(out)


def _rows(db, item_code):
    return sorted(
        (str(r.so_line_id), str(Decimal(r.qty).normalize()), str(r.state))
        for r in db.query(OrderInquiryRow).filter(OrderInquiryRow.item_code == item_code)
    )


def _run_pass(db, product_id, item_code, *, redeal):
    service = ProjectOrderInquiryService(db)
    answer = service.auto_place_for_products(
        [product_id], actor_user_id=None, trigger="test-memo", include_awaiting=True,
        link_horizon="none",
    )
    if redeal:
        answer = (answer, service.auto_place_for_products(
            [product_id], actor_user_id=None, trigger="test-memo", include_awaiting=True,
            link_horizon="none", redeal_drafts=True,
        ))
    db.flush()
    return answer, (_links(db, item_code), _rows(db, item_code))


def _document_reads(db):
    """Counts the statements that read the product's PO lines or SPO allocations."""
    seen = {"po": 0, "spo": 0}

    def count(_conn, _cursor, statement, _params, _context, _many):
        text = " ".join(statement.lower().split())
        if not text.startswith("select"):
            return
        # Schema-qualified in the scratch schema, so matched by pattern.
        if re.search(r"from \S*purchase_order_lines join \S*purchase_orders on", text):
            seen["po"] += 1
        if re.search(r"from \S*spo_allocations left outer join \S*inbound_shipments on", text):
            seen["spo"] += 1

    return seen, count


def _compare(api, monkeypatch, *, redeal):
    client, world = api
    db = world.db
    rows = _raised_rows(client, world)
    _documents(world)
    item_code = world.product.product_code
    product_id = str(world.product.id)
    assert len(rows) == ROWS
    engine = db.get_bind()

    # Oracle: the memo patched off, every row reads its documents itself (the old code).
    savepoint = db.begin_nested()
    with monkeypatch.context() as old:
        old.setattr(
            ProjectOrderInquiryService, "_document_rows", lambda self, key, read: read()
        )
        old_seen, old_count = _document_reads(db)
        event.listen(engine, "before_cursor_execute", old_count)
        try:
            old_answer, old_links = _run_pass(db, product_id, item_code, redeal=redeal)
        finally:
            event.remove(engine, "before_cursor_execute", old_count)
    savepoint.rollback()
    db.expire_all()

    savepoint = db.begin_nested()
    new_seen, new_count = _document_reads(db)
    event.listen(engine, "before_cursor_execute", new_count)
    try:
        new_answer, new_links = _run_pass(db, product_id, item_code, redeal=redeal)
    finally:
        event.remove(engine, "before_cursor_execute", new_count)
    savepoint.rollback()

    # Not vacuous: the pass placed some rows, and the scarce supply could not cover all.
    links, _rows_after = old_links
    assert links, ("the oracle pass placed nothing", old_answer)
    placed_lines = {link[1] for link in links}
    assert 0 < len(placed_lines) < ROWS, placed_lines
    assert new_links == old_links
    assert new_answer == old_answer
    return old_seen, new_seen


def test_a_pass_writes_the_same_links_with_the_document_memo(api, monkeypatch):
    old_seen, new_seen = _compare(api, monkeypatch, redeal=False)
    # A handful per product instead of one per row walked.
    assert old_seen["po"] >= ROWS, old_seen
    assert new_seen["po"] <= 2 and new_seen["spo"] <= 2, new_seen


def test_a_redeal_pass_writes_the_same_links_with_the_document_memo(api, monkeypatch):
    old_seen, new_seen = _compare(api, monkeypatch, redeal=True)
    # Two passes, each holding its own memo: a handful each, not one per row per pass.
    assert old_seen["po"] >= 2 * ROWS, old_seen
    assert new_seen["po"] <= 4 and new_seen["spo"] <= 4, new_seen


def test_outside_a_pass_the_documents_are_read_fresh(api):
    _client, world = api
    service = ProjectOrderInquiryService(world.db)
    assert service._document_rows_memo is None
    reads = []
    assert service._document_rows(("po", "x", False), lambda: reads.append(1) or [1]) == [1]
    assert service._document_rows(("po", "x", False), lambda: reads.append(1) or [1]) == [1]
    assert len(reads) == 2
