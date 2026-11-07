"""OI-DATE-WAS-FIX UAC 4: after `oiod_0002_pending_restore`, CS Confirm of the pending
date move tells purchasing Was (old told date) and Now (new SO line date).

The real path end to end: a line confirmed as Buy on WAS_1, AutoCount moves the SO line date
(a pending `delayed` / `advanced` planning change), then oiod_0001's backfill runs (the 4 Nov
deploy) and moves the told date onto the new line date. With oiod_0002 run before the
Confirm, the handover carries Was WAS_1 / Now the new date and the row is stamped as it would
have been without the backfill.

The control (no oiod_0002) runs in PROD's start order, which `_prod_start_order` below sets up
(release sweep RELEASE-SWEEP-4NOV-PM, #2171): the post-commit dispatch listener is registered
before any fixture writes, as `app/main.py`'s startup registers it before any request. In
that order the Confirm STILL emails Was WAS_1 / Now: the Was comes from the pending planning
change's own old date, not from the row's `previous_delivery_date` (measured: blanking that
column before the Confirm leaves the email unchanged). The control used to assert "nothing
reaches purchasing", which held only when the test's own `_register` was the first
registration in the process: the fixture's earlier handover then stayed undrained on
`Session.info`, the Confirm read the line as already told in this write and said nothing. Any
earlier file that ran the app lifespan (`with TestClient(app)`) flipped it, so it failed by
xdist file placement.

Real database, every write rolled back (`_real_db_session` via the `api` fixture); the two
migrations run as raw SQL inside that same transaction.
"""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.project_so import INQUIRY_CANCELLED
from app.services import planning_change_service
from app.services.scm.outstanding_diff import DATE_MOVED

from ..test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
)
from ..test_planning_change_apply_on_board import (
    NOW,
    WAS_1,
    _build,
    _change,
    _rows_of,
    api,
    world,
)
from .test_oi_date_move_settle import _one_row_fixture

__all__ = ["api", "world"]



@pytest.fixture(autouse=True, scope="module")
def _prod_start_order():
    """Prod's start order: the post-commit dispatch listener exists before any write, as
    `app/main.py`'s startup registers it (idempotent, process-global). A module fixture, set
    up before the function-scoped `world`, rather than an import-time call: collection
    imports this file in EVERY xdist worker, and registering there changed other files'
    runs (tests/scm/test_container_request_product_index.py's plans, measured on #2171)."""
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
LATER = date(2026, 9, 30)  # WAS_1 is 25 Aug: LATER is a DELAY, NOW (19 Aug) an ADVANCE


def _migrate(db, name: str) -> None:
    path = VERSIONS / f"{name}.py"
    assert path.exists(), f"{path.name} does not exist yet"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db.flush()
    with Operations.context(MigrationContext.configure(db.connection())):
        module.upgrade()
    db.expire_all()


def _pending_move_after_backfill(api, monkeypatch, new_date, *, restore: bool):
    fixture = _one_row_fixture(api, qty="10")
    world = fixture["world"]
    core, line, core_so = fixture["core"], fixture["line"], fixture["core_so"]
    _register(world)
    calls = _captured_dispatches(monkeypatch)

    # AutoCount moves the SO line date: a pending planning change, not yet confirmed.
    core.required_date = new_date
    line.delivery_date = new_date
    world.db.commit()
    batch = _build(
        world,
        [
            _change(
                DATE_MOVED, core, so_number=core_so.so_number,
                old_date=WAS_1, new_date=new_date, old_qty="10", new_qty="10",
            )
        ],
        core_so,
        [str(core.id)],
    )
    assert batch is not None

    # The 4 Nov deploy: the backfill moves the told date onto the line date.
    _migrate(world.db, "oiod_0001_backfill")
    row = fixture["row"]
    world.db.refresh(row)
    assert (row.delivery_date, row.previous_delivery_date) == (new_date, WAS_1)

    if restore:
        _migrate(world.db, "oiod_0002_pending_restore")
        world.db.refresh(row)
        assert (row.delivery_date, row.previous_delivery_date) == (WAS_1, None)
    world.db.commit()
    calls.clear()

    # CS Confirm.
    out = planning_change_service.get_batch(world.db, str(batch.id))
    row_out = out["orders"][0]["rows"][0]
    assert row_out["kind"] == ("delayed" if new_date > WAS_1 else "advanced")
    planning_change_service.set_row_decision(world.db, str(batch.id), row_out["id"], "confirm")
    result = planning_change_service.apply(world.db, str(batch.id), world.actor)
    world.db.commit()
    assert result["failed_orders"] == [], result["failed_orders"]
    world.db.expire_all()
    return world, line, calls


def _date_moves(calls):
    out = []
    for call in _handover_calls(calls):
        for entry in call["context"]["handover"]["lines"]:
            was = entry.get("was") or {}
            if was.get("delivery_date"):
                out.append((was["delivery_date"], entry["delivery_date"]))
    return out


def test_control_without_the_restore_confirm_still_tells_was_and_now(api, monkeypatch):
    """Prod start order (see the module docstring): without oiod_0002 the Confirm still
    emails Was WAS_1 / Now the new date, read off the pending planning change, and stamps
    the row the same way the restore does."""
    world, line, calls = _pending_move_after_backfill(api, monkeypatch, LATER, restore=False)
    assert _date_moves(calls) == [(WAS_1.strftime("%d/%m/%Y"), LATER.strftime("%d/%m/%Y"))]
    live = [r for r in _rows_of(world, line) if r.state != INQUIRY_CANCELLED]
    assert [(r.delivery_date, r.previous_delivery_date) for r in live] == [(LATER, WAS_1)]


@pytest.mark.parametrize("new_date", [LATER, NOW], ids=["delay", "advance"])
def test_after_the_restore_confirm_emails_was_and_now(api, monkeypatch, new_date):
    """UAC 4: the handover (email + attachment) carries Was WAS_1, Now the new date, and
    the row is stamped with it."""
    world, line, calls = _pending_move_after_backfill(api, monkeypatch, new_date, restore=True)

    assert _date_moves(calls) == [
        (WAS_1.strftime("%d/%m/%Y"), new_date.strftime("%d/%m/%Y"))
    ]
    live = [r for r in _rows_of(world, line) if r.state != INQUIRY_CANCELLED]
    assert [(r.delivery_date, r.previous_delivery_date) for r in live] == [(new_date, WAS_1)]
