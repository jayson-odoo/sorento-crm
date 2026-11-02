"""Simulate confirm speed (lane SIMULATE-CONFIRM-SPEED).

Plan `documentation/plans/scm/PLAN-simulate-confirm-speed-03nov.md`, UAC
`simulate-confirm-speed-03nov-acceptance-criteria.md` AC-1..AC-6.

Postgres via the fixture chain of `tests/test_fulfilment_simulate_confirm.py`.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

from app.models.project_so import (
    DECISION_ACTIVE,
    DECISION_SUPERSEDED,
    SOSupplyDecision,
)

from .test_confirm_all_preview import (  # noqa: F401 - `api` is a fixture
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    _stock,
    _two_line_order,
    api,
)
from .test_fulfilment_simulate_confirm import (
    URL,
    _as_role,
    _lines_of,
    _post,
    _raise_for_every_payload,
)


def _order_with_lines(world, count):
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=10000)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    lines = []
    for index in range(count):
        core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5")
        lines.append(
            _project_line(
                db, order, line_no=(index + 1) * 10, product=world.product, core_line=core_line
            )
        )
    db.commit()
    return order, lines


# --------------------------------------------------------------------------- AC-1


def test_a_refused_job_is_not_probed_line_by_line(api, monkeypatch):
    from app.services.confirm_simulation import SimulationWouldCommit

    client, world = api
    _as_role(monkeypatch, "admin")
    order, _core, (a, b) = _two_line_order(world)
    seen: list = []
    _raise_for_every_payload(
        monkeypatch, lambda: SimulationWouldCommit("Simulation refused a queued job."), seen
    )

    response = _post(
        client, order, [_line_payload(a.id, buy_qty="50"), _line_payload(b.id, buy_qty="50")]
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is False, result
    assert result["error"].startswith("SimulationWouldCommit: "), result
    assert result["simulated_errors"] is None
    assert len(seen) == 1, "the confirm ran once; no per-line probe for an order-level refusal"
    assert "error_class" not in result and "elapsed_ms" not in result


def test_a_single_line_refused_job_still_names_its_line(api, monkeypatch):
    """The skip only saves probe runs: a one-line order is named without probing, as today."""
    from app.services.confirm_simulation import SimulationWouldCommit

    client, world = api
    _as_role(monkeypatch, "admin")
    order, _core, (a, _b) = _two_line_order(world)
    seen: list = []
    _raise_for_every_payload(
        monkeypatch, lambda: SimulationWouldCommit("Simulation refused a queued job."), seen
    )

    response = _post(client, order, [_line_payload(a.id, buy_qty="50")])

    result = response.json()["results"][0]
    assert len(seen) == 1
    assert [str(e["project_line_id"]) for e in result["simulated_errors"]] == [str(a.id)]


def test_a_409_naming_one_line_is_still_probed_and_named(api, monkeypatch):
    """A 409 is not order-level: "Line X is already cancelled." comes with no failing_lines."""
    from app.services.error_handler import AppException
    from app.services.project_supply_service import ProjectSupplyService

    client, world = api
    _as_role(monkeypatch, "admin")
    order, _core, (a, b) = _two_line_order(world)
    original = ProjectSupplyService.confirm
    message = "Line 20 is already cancelled."

    def wrapper(self, order_, payload, *args, **kwargs):
        if str(b.id) in _lines_of(payload):
            raise AppException(status_code=409, message=message, code="line_cancelled")
        return original(self, order_, payload, *args, **kwargs)

    monkeypatch.setattr(ProjectSupplyService, "confirm", wrapper)

    response = _post(
        client, order, [_line_payload(a.id, buy_qty="50"), _line_payload(b.id, buy_qty="50")]
    )

    result = response.json()["results"][0]
    assert result["ok"] is False and message in result["error"]
    assert [e["line_no"] for e in result["simulated_errors"]] == [20]


# --------------------------------------------------------------------------- AC-2


def test_the_probe_stops_after_five_lines_failing_the_same_way(api, monkeypatch):
    client, world = api
    _as_role(monkeypatch, "admin")
    order, lines = _order_with_lines(world, 8)
    seen: list = []
    _raise_for_every_payload(monkeypatch, lambda: TypeError("same everywhere"), seen)

    response = _post(client, order, [_line_payload(x.id, buy_qty="5") for x in lines])

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is False
    assert result["error"].startswith("TypeError: ")
    assert result["simulated_errors"] is None
    assert len(seen) == 1 + 5, [s[1] for s in seen]
    assert [s[1] for s in seen[1:]] == [[str(x.id)] for x in lines[:5]]


# --------------------------------------------------------------------------- AC-3


def test_lines_failing_each_their_own_way_are_all_probed_and_named(api, monkeypatch):
    from app.services.project_supply_service import ProjectSupplyService

    client, world = api
    _as_role(monkeypatch, "admin")
    order, lines = _order_with_lines(world, 7)
    seen: list = []

    def wrapper(self, order_, payload, *args, **kwargs):
        named = _lines_of(payload)
        seen.append(named)
        raise TypeError("broke on " + ",".join(sorted(named)))

    monkeypatch.setattr(ProjectSupplyService, "confirm", wrapper)

    response = _post(client, order, [_line_payload(x.id, buy_qty="5") for x in lines])

    result = response.json()["results"][0]
    assert len(seen) == 1 + 7
    assert [e["line_no"] for e in result["simulated_errors"]] == [10, 20, 30, 40, 50, 60, 70]


# --------------------------------------------------------------------------- AC-6


def test_simulate_logs_per_order_and_total_time(api, monkeypatch, caplog):
    client, world = api
    _as_role(monkeypatch, "admin")
    order, _core, (a, b) = _two_line_order(world)
    _raise_for_every_payload(monkeypatch, lambda: TypeError("same everywhere"))

    with caplog.at_level(logging.INFO, logger="app.api.v1.projects.fulfilment_planning"):
        _post(client, order, [_line_payload(a.id, buy_qty="50")])

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert f"simulate_confirm order={order.id} ms=" in text, text
    assert "simulate_confirm total orders=1 ms=" in text, text


# --------------------------------------------------------------------------- AC-4, AC-5


def _decision(world, snapshots):
    order = _project_so(world.db, world.project)
    decision = SOSupplyDecision(
        id=str(uuid.uuid4()),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        revision_no=1,
        state=DECISION_ACTIVE,
        line_snapshots=snapshots,
        confirmed_at=datetime.utcnow(),
    )
    world.db.add(decision)
    world.db.flush()
    return decision


def _normal(rows):
    return sorted((str(pso), json.dumps(snaps, sort_keys=True)) for pso, snaps in rows)


def _cold(db):
    return _normal(
        db.query(SOSupplyDecision.project_sales_order_id, SOSupplyDecision.line_snapshots)
        .filter(SOSupplyDecision.state == DECISION_ACTIVE)
        .all()
    )


def _read(db):
    """A fresh service each time: what one order's `_facts_for` does after its reset."""
    from app.services.project_supply_service import ProjectSupplyService

    return _normal(ProjectSupplyService(db)._active_decision_snapshots())


def test_active_decision_snapshots_are_reused_and_always_current(api):
    _client, world = api
    db = world.db
    decision = _decision(world, [{"project_line_id": "a", "core_line_id": "c1"}])

    snapshot_reads: list = []

    def count(conn, cursor, statement, *args):
        if "line_snapshots" in statement and "so_supply_decisions" in statement:
            snapshot_reads.append(statement)

    engine = db.get_bind().engine
    event.listen(engine, "before_cursor_execute", count)
    try:
        assert _read(db) == _cold(db)
        snapshot_reads.clear()
        assert _read(db) == _cold(db)
        snapshot_reads.pop()  # the cold read's own
        assert snapshot_reads == [], "an unchanged decision set must not reload line_snapshots"

        # AC-5: an in-place rewrite of the same row.
        decision.line_snapshots = [{"project_line_id": "a", "core_line_id": "c2"}]
        flag_modified(decision, "line_snapshots")
        db.flush()
        assert _read(db) == _cold(db)
        assert any("c2" in snaps for _pso, snaps in _read(db))

        # A new active decision.
        other = _decision(world, [{"project_line_id": "b", "core_line_id": "c3"}])
        assert _read(db) == _cold(db)

        # A retired one.
        other.state = DECISION_SUPERSEDED
        db.flush()
        assert _read(db) == _cold(db)
        assert not any("c3" in snaps for _pso, snaps in _read(db))

        # A rolled-back savepoint that rewrote a row.
        savepoint = db.begin_nested()
        decision.line_snapshots = [{"project_line_id": "a", "core_line_id": "c9"}]
        flag_modified(decision, "line_snapshots")
        db.flush()
        assert any("c9" in snaps for _pso, snaps in _read(db))
        savepoint.rollback()
        assert _read(db) == _cold(db)
        assert not any("c9" in snaps for _pso, snaps in _read(db))
    finally:
        event.remove(engine, "before_cursor_execute", count)
