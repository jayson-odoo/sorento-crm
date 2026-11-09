"""SO-LOCATION-GAP one-off repair (owner, 9 Nov 2026 ~22:05, option a):
`scripts/repair_pending_change_location.py` gives a PENDING change row written before the fix
(prod SO429664) the location move a row written now carries: `from.location` = where the line
was last confirmed (else where its live ORDER rows sit), `to.location` = where it is now. Dry run
by default, prints each row it would change; `--apply` writes; a re-run is a no-op. Same rule and
helper as `planning_change_service._build_row`.

Postgres only (`tests/_pg_fixture.py`). The script is loaded from its file, as
`tests/test_repair_oi_legacy_dup_rows.py` loads its sibling.
"""
from __future__ import annotations

import importlib.util
import os

from .test_oi_saved_line_email import _order, _post, emails  # noqa: F401
from .test_planning_change_apply_on_board import _confirm, api, world  # noqa: F401
from .test_planning_changes import _line_payload
from .test_so_line_location_change_email import _move, _rows, _sibling
from .test_so_location_gap import _date_change, _pending, _split


def _script():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "repair_pending_change_location.py",
    )
    spec = importlib.util.spec_from_file_location("_repair_pending_change_location", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _as_written_before_the_fix(world, row):
    """The row the pre-fix code wrote for this sequence: no location on either side."""
    row.from_json = {**(row.from_json or {}), "location": None}
    row.to_json = {**(row.to_json or {}), "location": None}
    world.db.commit()


def _so429664(api):
    """The owner's sequence: Buy confirmed at the old location (ORDER raised there), moved
    by AutoCount with no change row, then a date change whose row has no location."""
    _client, world = api
    order, line_a, line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [
        _line_payload(line_a.id, buy_qty="10"), _line_payload(line_b.id, buy_qty="6"),
    ])
    new_wh = _sibling(world)
    new = new_wh.warehouse_code
    _move(world, line_a, new_wh)
    # Line B moved the same way but has no change of its own: never touched (no backfill).
    _move(world, line_b, new_wh)
    batch = _date_change(world, line_a, new, new)
    (row,) = _pending(world, line_a)
    _as_written_before_the_fix(world, row)
    return order, line_a, line_b, old, new, row, batch


def test_dry_run_prints_the_row_it_would_change_and_writes_nothing(api, capsys):
    _client, world = api
    order, line_a, _line_b, old, new, row, _batch = _so429664(api)

    result = _script().run(world.db, apply=False)
    world.db.commit()

    assert (result["found"], result["repaired"]) == (1, 0), result
    out = capsys.readouterr().out
    assert f"{order.autocount_doc_no} line " in out, out
    assert f"location {old} -> {new}" in out, out
    world.db.expire_all()
    (still,) = _pending(world, line_a)
    assert (still.from_json.get("location"), still.to_json.get("location")) == (None, None)
    assert _split(world, order)[str(line_a.id)] == (None, new)


def test_apply_writes_the_move_the_lightbox_and_review_split_read(api):
    from app.services import planning_change_service

    _client, world = api
    order, line_a, line_b, old, new, _row, _batch = _so429664(api)

    result = _script().run(world.db, apply=True)
    world.db.commit()

    assert (result["found"], result["repaired"]) == (1, 1), result
    world.db.expire_all()
    (row,) = _pending(world, line_a)
    wire = planning_change_service.row_out(world.db, row)
    assert (wire["from"].get("location"), wire["to"].get("location")) == (old, new)
    # Nothing else on the row moves.
    assert wire["from"].get("required_date") != wire["to"].get("required_date")
    assert row.kind == "delayed", row.kind
    split = _split(world, order)
    assert split[str(line_a.id)] == (old, new)
    assert split[str(line_b.id)] == (None, new)
    assert _pending(world, line_b) == []


def test_a_second_run_is_a_no_op(api):
    _client, world = api
    _order_, line_a, _line_b, old, new, _row, _batch = _so429664(api)
    script = _script()
    script.run(world.db, apply=True)
    world.db.commit()
    world.db.expire_all()
    (first,) = _pending(world, line_a)
    written = (dict(first.from_json), dict(first.to_json))

    again = script.run(world.db, apply=True)
    world.db.commit()

    assert (again["found"], again["repaired"]) == (0, 0), again
    world.db.expire_all()
    (row,) = _pending(world, line_a)
    assert (row.from_json, row.to_json) == written
    assert (row.from_json["location"], row.to_json["location"]) == (old, new)


def test_rows_already_applied_are_left_alone(api, emails):
    """Only PENDING rows: a row the board Confirm applied is history, told already."""
    client, world = api
    order, line_a, _line_b, _old, _new, row, batch = _so429664(api)
    response = _confirm(client, order.id, [_line_payload(line_a.id, buy_qty="10")],
                        batch_id=str(batch.id))
    assert response.status_code == 200, response.text
    world.db.commit()
    assert _pending(world, line_a) == [], "premise: the Confirm applied the row"

    result = _script().run(world.db, apply=True)
    world.db.commit()

    assert result["found"] == 0, result
    world.db.expire_all()
    world.db.refresh(row)
    assert (row.from_json.get("location"), row.to_json.get("location")) == (None, None)


def test_a_pending_row_on_a_line_that_did_not_move_is_left_alone(api):
    _client, world = api
    order, line_a, _line_b = _order(api)
    old = world.own_wh.warehouse_code
    _post(api, order, [_line_payload(line_a.id, buy_qty="10")])
    _date_change(world, line_a, old, old)

    result = _script().run(world.db, apply=True)
    world.db.commit()

    assert result["found"] == 0, result
    (row,) = _pending(world, line_a)
    assert (row.from_json.get("location"), row.to_json.get("location")) == (None, None)


def test_a_line_with_no_decision_reads_where_its_order_sits(api):
    """UAC G6 for the repair: no confirmed decision, only the raised ORDER at the old place."""
    from .test_oi_handover_purchasing_focus import _imported_raised_order

    _client, world = api
    order, line = _imported_raised_order(api)
    old = world.own_wh.warehouse_code
    (held,) = _rows(world, line)
    held.stock_location = old
    world.db.commit()
    new_wh = _sibling(world)
    new = new_wh.warehouse_code
    _move(world, line, new_wh)
    _date_change(world, line, new, new)
    (row,) = _pending(world, line)
    _as_written_before_the_fix(world, row)

    result = _script().run(world.db, apply=True)
    world.db.commit()

    assert (result["found"], result["repaired"]) == (1, 1), result
    world.db.expire_all()
    (row,) = _pending(world, line)
    assert (row.from_json.get("location"), row.to_json.get("location")) == (old, new)
