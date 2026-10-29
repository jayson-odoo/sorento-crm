"""STOCKDEBT-PERF PR3 (AC-SDP-D1, D2): the board's heavy reads return ids as text.

WRITTEN BEFORE THE IMPLEMENTATION EXISTS (Phase 2 is test-first). Plan:
documentation/plans/scm/stockdebt-perf-acceptance-criteria.md, section PR3.

Seed: the remapped-placement chain (a placement on a received SPO, stock, demand) so
`_demand`, `_supply`, `_holds` and goods_chain `_placements` all run on a default-view board.
"""
from __future__ import annotations

import traceback
import uuid
from datetime import timedelta

from sqlalchemy import event

from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import requires_pg
from tests.scm.test_stock_debt_routes import (
    TODAY,
    _client,
    _demand,
    _months_ahead,
    _order_back_link_on_spo,
    _product,
    _project_line_for,
    _spo,
    _stock,
    _u,
    _warehouse,
)

pytestmark = requires_pg

UUID_OID = 2950
SITES = {"_demand", "_supply", "_holds", "_placements"}


def _seed(db):
    marker = f"ZZTID{_u()[:6]}".upper()
    wh = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    q = _product(db, f"{marker}-Q")
    p = _product(db, f"{marker}-P")
    _stock(db, p, wh, 50)
    due = _months_ahead(1)
    _order, core_line = _demand(
        db, q, wh, qty=50, required_date=due, so_number=f"{marker}-SO1"
    )
    project_order, project_line = _project_line_for(db, core_line)
    project_line.product_id = p.id
    db.flush()
    allocation = _spo(
        db, p, wh, qty=50, arrives=TODAY - timedelta(days=20),
        received=50, receipt_status="fully_received",
    )
    _order_back_link_on_spo(db, project_order, project_line, allocation=allocation, qty=50)
    # a second product with open demand and no supply: in debt, so the default view lists it
    short = _product(db, f"{marker}-S")
    _demand(db, short, wh, qty=5, required_date=due, so_number=f"{marker}-SO2")
    db.flush()
    return marker, q, short, due


def _site():
    """The innermost function under app/services on the stack."""
    for frame in reversed(traceback.extract_stack()):
        if "/app/services/" in frame.filename.replace("\\", "/"):
            return frame.name
    return None


def test_heavy_reads_return_no_uuid_typed_column(scm_app):
    """AC-SDP-D1: no statement from `_demand`, `_supply`, `_holds` or `_placements` fetches a
    uuid-typed column (ids are selected as text)."""
    from app.services.scm.stock_debt_service import StockDebtService

    app, db = _client(scm_app)
    marker, _q, _short, _due = _seed(db)
    ran: set = set()
    uuid_sites: dict = {}

    def after(conn, cursor, statement, parameters, context, executemany):
        site = _site()
        if site not in SITES:
            return
        ran.add(site)
        if any(col[1] == UUID_OID for col in (cursor.description or [])):
            uuid_sites[site] = uuid_sites.get(site, 0) + 1

    bind = db.get_bind()
    event.listen(bind, "after_cursor_execute", after)
    try:
        StockDebtService(db).list(query=marker, only_debt=True)
    finally:
        event.remove(bind, "after_cursor_execute", after)

    assert ran == SITES, f"these sites never ran, the test would be vacuous: {SITES - ran}"
    assert not uuid_sites, f"statements returning a uuid column, by site: {uuid_sites}"


def _walk_ids(node, path=""):
    """Yield (path, value) for every `id` / `*_id` key in a nested response."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}"
            if key == "id" or key.endswith("_id"):
                yield here, value
            yield from _walk_ids(value, here)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk_ids(item, f"{path}[{i}]")


def test_ids_on_the_board_and_the_drill_are_canonical_strings(scm_app):
    """AC-SDP-D2: every id is a lowercase hyphenated `str`, or None."""
    from app.services.scm.stock_debt_service import StockDebtService

    app, db = _client(scm_app)
    marker, q, short, due = _seed(db)
    svc = StockDebtService(db)

    board = svc.list(query=marker, only_debt=False)
    cell = svc.cell(str(short.id), month_key(due))
    qcell = svc.cell(str(q.id), month_key(due))

    seen = 0
    for label, body in (("board", board["data"]), ("cell", cell), ("qcell", qcell)):
        for path, value in _walk_ids(body):
            if value is None:
                continue
            seen += 1
            assert isinstance(value, str) and not isinstance(value, uuid.UUID), (label, path, value)
            assert str(uuid.UUID(value)) == value, (label, path, value)
    assert seen >= 4, seen
    rows = {r["product_code"]: r for r in board["data"]}
    assert rows[short.product_code]["product_id"] == str(short.id)
    assert rows[short.product_code]["supplier_id"] is None
