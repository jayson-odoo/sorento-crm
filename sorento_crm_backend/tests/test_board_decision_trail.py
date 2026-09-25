"""Who saved, who confirmed, and how many lines - on the board itself (PLAN-oi-decision-
trail-ui.md, AC-DT-1, AC-DT-2). SO390524 / OI-2609-0731, prod, 25 Sep 2026: the answer
lived only in the database, because the board printed "by <name>" nowhere but inside
`SupplyCompositionSection.tsx`'s own per-composition line.

Three surfaces are pinned here, off the ACTUAL response (never a service helper -
`response_model` drops a field the schema does not declare):

* the board panel's own header block, per order (AC-DT-1);
* the Confirmed chip's tooltip facts, flattened onto the covered line (AC-DT-2, the
  `decided_*` trio);
* the Save-decision facts, flattened the same way (AC-DT-2, the `draft_saved_*` pair).
"""
from __future__ import annotations

from datetime import date

from app.models.base import company_scope
from app.models.project_so import ProjectSalesOrderLine, SOSupplyDecisionDraft

from ._pg_fixture import blank_session
from .test_fulfilment_board import (
    BASE,
    EDIT,
    MARKER,
    TODAY,
    VIEW,
    _adopt,
    _board_world,
    _client,
    _confirm,
    _line,
    _order,
    _pooled_warehouses,
    _product,
    _restore,
    _service,
    _sorento,
    _stock,
    _uid,
    _user,
)


def test_the_board_header_names_the_active_decisions_revision_confirmer_and_line_count():
    with blank_session() as db:
        company_id = _sorento(db)
        confirmer = _user(db, f"{MARKER} Nurain")
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own, pool = _pooled_warehouses(db)
        _stock(db, product, pool, on_hand=200)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=own)
        pso_id = _adopt(db, str(order.id))
        db.commit()

        mirror = (
            db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .first()
        )
        _confirm(
            db,
            pso_id,
            confirmer,
            [
                {
                    "project_line_id": str(mirror.id),
                    "timely_spo_qty": "0",
                    "reserve": [{"warehouse_id": str(pool.id), "qty": "10"}],
                    "buy_qty": "0",
                }
            ],
        )
        db.commit()

        client, originals = _client(db, confirmer, [VIEW, EDIT])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning/board",
                    params={"orders": order.so_number, "granularity": "week"},
                )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        body = response.json()
        standing = body["orders"][0]
        decision = standing["decision"]
        assert decision is not None
        assert decision["revision_no"] == 1
        assert decision["confirmed_by_name"] == f"{MARKER} Nurain"
        assert decision["confirmed_at"] is not None
        assert decision["line_count"] == 1

        contribution = body["cells"][0]["contributions"][0]
        assert contribution["covered"] is True
        # The trail's own flattened trio - the Confirmed chip's tooltip reads these
        # rather than reaching into `decision`, which carries no confirmer at all.
        assert contribution["decided_by_name"] == f"{MARKER} Nurain"
        assert contribution["decided_at"] is not None
        assert contribution["decision_revision"] == 1


def test_an_order_with_no_active_decision_reads_no_decision_yet():
    with blank_session() as db:
        company_id = _sorento(db)
        actor = _user(db, f"{MARKER} Eling")
        order, _product = _board_world(db)
        db.commit()

        client, originals = _client(db, actor, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning/board",
                    params={"orders": order.so_number, "granularity": "week"},
                )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        standing = response.json()["orders"][0]
        assert standing["decision"] is None
        contribution = response.json()["cells"][0]["contributions"][0]
        assert contribution["decided_by_name"] is None
        assert contribution["decided_at"] is None
        assert contribution["decision_revision"] is None
        assert contribution["draft_saved_by_name"] is None
        assert contribution["draft_saved_at"] is None


def test_a_saved_draft_reaches_the_line_as_the_flattened_saver_facts():
    """AC-DT-2, on the ACTUAL response (reviewer S3, round 1): `response_model` drops a
    field the schema does not declare, so a service-dict assertion proves nothing about
    what the chip can read."""
    with blank_session() as db:
        company_id = _sorento(db)
        saver = _user(db, f"{MARKER} Farah")
        product = _product(db, f"ZZT-{_uid()[:6]}")
        own, pool = _pooled_warehouses(db)
        _stock(db, product, pool, on_hand=200)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=date(2026, 9, 3), warehouse=own)
        db.flush()

        # Setup only: the draft row is keyed by the contribution the engine derives, so
        # read it once to know the key, line id and bucket to save under.
        with company_scope(db, frozenset({company_id})):
            board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)
        contribution = board["contributions"][0]
        db.add(
            SOSupplyDecisionDraft(
                id=_uid(),
                sales_order_id=str(order.id),
                core_line_id=contribution["line_id"],
                line_no=contribution["line_no"],
                item_code=contribution["item_code"],
                bucket_key=contribution["key"].split("|")[3],
                decision={"verdict": "approved"},
                line_snapshot={
                    "open_qty": contribution["qty"],
                    "required_date": (
                        contribution["required_date"].isoformat()
                        if contribution["required_date"]
                        else None
                    ),
                },
                saved_by=saver,
            )
        )
        db.commit()

        client, originals = _client(db, saver, [VIEW])
        try:
            with company_scope(db, frozenset({company_id})):
                response = client.get(
                    f"{BASE}/fulfilment-planning/board",
                    params={"orders": order.so_number, "granularity": "week"},
                )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        saved = response.json()["contributions"][0]
        assert saved["draft_saved_by_name"] == f"{MARKER} Farah"
        assert saved["draft_saved_at"] is not None
        # The `draft` object itself travels too - the chip reads both together.
        assert saved["draft"]["saved_by"] == f"{MARKER} Farah"
        # A save is not a confirm: the line stays uncovered.
        assert saved["decided_by_name"] is None
        assert saved["decided_at"] is None
        assert saved["decision_revision"] is None
