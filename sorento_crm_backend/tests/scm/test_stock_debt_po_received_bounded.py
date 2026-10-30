"""STOCKDEBT-SHM-QUERY: the Stock Debt board's batched PO-received read stays bounded.

PROD 27 Oct 2026: GET /stock-debt died with DiskFull ("could not resize shared memory
segment") in a parallel hash join. `_po_received_by_product` joined purchase_order_lines to
spo_allocations with no product filter on the SPO side, so the hash covered every SPO row
in the company, and it sent every ref (412) in one IN list. The read now filters the SPO
side by product and asks in chunks; its answer is unchanged.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import event, text

from tests.scm.conftest import requires_pg
from tests.scm.test_goods_chain import _World
from tests.scm.test_goods_chain_key_everywhere import _own_arrival_world
from tests.scm.test_stock_debt_routes import _product, _spo, _u

pytestmark = requires_pg

_PADDING = 250  # more refs than one chunk holds


def _core_line_for(db, row):
    from app.models.order import SalesOrderLine
    from app.models.project_so import ProjectSalesOrderLine

    return (
        db.query(SalesOrderLine)
        .join(
            ProjectSalesOrderLine,
            ProjectSalesOrderLine.core_sales_order_line_id == SalesOrderLine.id,
        )
        .filter(ProjectSalesOrderLine.id == row.so_line_id)
        .one()
    )


def _seed(db):
    """Product A: a PO receipt at a ref sorting FIRST and one sorting LAST (so they fall in
    different chunks), an order inquiry SPO placement at a third ref, and 250 padding refs
    with nothing behind them. Product B: an SPO naming A's PO line (wrong product, must not
    count). Returns (refs_by_product, product A id)."""
    w, po, po_line, a, last_ref = _own_arrival_world(db)  # ref "ZZTSO..." sorts after padding

    first = _own_arrival_world(db)
    first_po, first_line, first_ref = first[1], first[2], f"ZZTAA{_u()[:6]}"
    first_line.from_so_line_ref = first_ref
    first_line.product_id = w.product.id
    first[3].product_id = w.product.id
    first[3].quantity_received = 7

    other = _product(db, f"{w.marker}-B")
    stray = _spo(db, other, w.b1, qty=99, arrives=a.expected_date, received=99,
                 receipt_status="fully_received", line_status="closed")
    stray.from_po_number = po.po_number
    stray.from_po_line_ref = po_line.source_ref

    placed = _spo(db, w.product, w.b1, qty=5, arrives=a.expected_date, received=5,
                  receipt_status="fully_received", line_status="closed")
    row, _link = w.place_on_spo(placed, 5, minute=3)
    core = _core_line_for(db, row)
    oi_ref = f"ZZTPL{_u()[:6]}"
    core.source_ref = oi_ref
    db.flush()

    padding = [f"ZZTPAD{i:04d}" for i in range(_PADDING)]
    pid = str(w.product.id)
    return (
        {pid: [first_ref, last_ref, oi_ref, *padding], str(other.id): [last_ref, *padding]},
        pid,
        (first_ref, last_ref, oi_ref),
    )


def test_batched_po_received_matches_the_single_key_read_past_one_chunk(
    scm_app, monkeypatch
):
    from app.services import project_supply_service
    from app.services.project_supply_service import ProjectSupplyService

    # The real chunk is now far larger than the seed; shrink it so the loop still spans
    # several chunks and the chunked answer is proved equal to the single-key read.
    monkeypatch.setattr(project_supply_service, "_REF_CHUNK", 2)
    db = scm_app[1]
    refs_by_product, pid, (first_ref, last_ref, oi_ref) = _seed(db)
    service = ProjectSupplyService(db)

    out = service._po_received_by_product(refs_by_product)

    for product_id, refs in refs_by_product.items():
        expected = service._po_received_by_so_line_ref(
            refs, product_id=product_id, company_id=None
        )
        assert out[product_id] == expected, product_id
    landed = {ref: Decimal(str(v[0])) for ref, v in out[pid].items()}
    assert landed.get(first_ref) == Decimal("7")
    assert landed.get(last_ref) == Decimal("50")
    assert landed.get(oi_ref) == Decimal("5")


def _capture_reads(db, refs_by_product):
    from app.services.project_supply_service import ProjectSupplyService

    seen = []

    def _capture(_conn, _cursor, statement, parameters, _context, _many):
        seen.append((statement, parameters))

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _capture)
    try:
        ProjectSupplyService(db)._po_received_by_product(refs_by_product)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)
    return seen


def test_batched_po_received_filters_the_spo_side_by_product_and_reads_once(scm_app):
    from app.services import project_supply_service

    db = scm_app[1]
    refs_by_product, _pid, _refs = _seed(db)
    all_refs = set().union(*map(set, refs_by_product.values()))
    assert len(all_refs) > 200, "the seed must be past the old chunk of 200"
    seen = _capture_reads(db, refs_by_product)

    def ref_params(parameters):
        values = parameters.values() if isinstance(parameters, dict) else parameters
        return sum(1 for v in values if isinstance(v, str) and v in all_refs)

    po_reads = [(s, p) for s, p in seen if "FROM purchase_order_lines" in s]
    oi_reads = [(s, p) for s, p in seen if "order_inquiry_links ON" in s]
    assert len(po_reads) == 1, f"{len(po_reads)} PO-received reads, want one"
    assert len(oi_reads) == 1, f"{len(oi_reads)} placement reads, want one"
    assert project_supply_service._REF_CHUNK >= 10000
    for statement, parameters in po_reads + oi_reads:
        assert ref_params(parameters) <= project_supply_service._REF_CHUNK, statement
    for statement, _parameters in po_reads:
        assert "spo_allocations.product_id IN" in statement, statement


def test_po_received_reads_run_without_parallel_workers(scm_app):
    """The /dev/shm guard: parallel hash joins use /dev/shm, so the two reads run with
    `max_parallel_workers_per_gather = 0`, and the session's own value is back afterwards."""
    from app.services.project_supply_service import ProjectSupplyService

    db = scm_app[1]
    refs_by_product, _pid, _refs = _seed(db)
    db.execute(text("SET LOCAL max_parallel_workers_per_gather = 2"))
    query = "select current_setting('max_parallel_workers_per_gather')"
    assert db.execute(text(query)).scalar() == "2"
    captured = []
    busy = {"on": False}

    def _probe(_conn, cursor, statement, _parameters, _context, _many):
        if busy["on"] or not (
            "FROM purchase_order_lines" in statement or "order_inquiry_links ON" in statement
        ):
            return
        busy["on"] = True
        try:
            side = cursor.connection.cursor()
            side.execute(query)
            captured.append(side.fetchone()[0])
            side.close()
        finally:
            busy["on"] = False

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _probe)
    try:
        ProjectSupplyService(db)._po_received_by_product(refs_by_product)
    finally:
        event.remove(engine, "before_cursor_execute", _probe)

    assert captured, "neither read ran"
    assert set(captured) == {"0"}, captured
    assert db.execute(text(query)).scalar() == "2", "the previous value was not restored"


def test_a_failed_read_surfaces_its_own_error(scm_app, monkeypatch):
    """A statement that fails inside the no-parallel window must reach the caller as its own
    database error, not as InFailedSqlTransaction from the restore running on the aborted
    transaction."""
    import pytest
    from sqlalchemy.exc import DBAPIError

    from app.services.project_supply_service import ProjectSupplyService

    db = scm_app[1]
    refs_by_product, _pid, _refs = _seed(db)

    def _boom(self, *_a, **_k):
        db.execute(text("select 1/0"))

    monkeypatch.setattr(ProjectSupplyService, "_oi_placements", _boom)
    nested = db.begin_nested()
    try:
        with pytest.raises(DBAPIError) as caught:
            ProjectSupplyService(db)._po_received_by_product(refs_by_product)
        assert type(caught.value.orig).__name__ == "DivisionByZero", repr(caught.value.orig)
    finally:
        if nested.is_active:
            nested.rollback()
        else:
            db.rollback()
