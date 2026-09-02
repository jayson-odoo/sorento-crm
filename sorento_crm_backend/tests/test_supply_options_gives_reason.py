"""C5 (code review round 3 batch 2): the supply sheet's own ladder options never got v8's
`gives_qty` / `reason`, so `SupplyLineCard` (through the shared `BoardLadderOptionsTable`)
rendered a blank Gives column - the board's OWN options (`BoardLadderOption`, R-K) already
carry both, and `_option_row` in `project_fulfilment_board_service.py` already computes
them; `_serialize_line` in `project_supply_service.py` simply never copied the two fields
across when v8 landed.

`response_model=SupplyProposal` silently drops an undeclared field (LESSONS-LEARNT), so this
is asserted on the JSON body, never on the internal dict.

Postgres via `tests/_pg_fixture.py::blank_session`, the fixture chain reused from
`tests/test_so_supply_confirmation.py`, per PRINCIPLES.
"""
from __future__ import annotations

from .test_so_supply_confirmation import BASE, _core_line, _core_so, _project_line, _project_so, _stock, api


def test_the_supply_sheet_s_options_carry_gives_qty_and_reason(api):
    """GET /sales-orders/{pso_id}/supply -> lines[].options[] carries both fields, the same
    shape the board's own `BoardLadderOption` already sends."""
    client, world = api
    db = world.db
    # Enough on the pool that at least one option is a whole cover, and the line is small
    # enough that `pool_share` is the chosen step - the row every case here reads off.
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    order = _project_so(db, world.project, so_id=core_so.id)
    _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    response = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["lines"]) == 1
    options = body["lines"][0]["options"]
    assert len(options) == 5, "the five ladder v8 steps, one entry each (R36, AC-S3-14)"
    for option in options:
        assert "gives_qty" in option, option
        assert "reason" in option, option

    chosen = next(option for option in options if option["chosen"])
    assert chosen["step"] == "pool_share"
    # The chosen step covers the whole 10-unit line: `gives_qty` states it, the same figure
    # the board's own `_option_row` would print for this walk.
    assert chosen["gives_qty"] == "10"
