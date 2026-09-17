"""Hotfix red tests - the undo journal's Core SQL `null` write is a JSON literal, not a
SQL NULL, and Postgres's `jsonb_array_length` blows up on it.

Found 17 Sep on a lane copy, shipped to prod in #985 04:37Z. `app/services/
project_supply_undo_service.py` clears a decision's journal with Core SQL
`table.update().values(undo_journal=None)` at two sites:

* `UndoJournal.attach` (about line 316) - the decision THIS confirm superseded, at every
  confirm that supersedes a journalled revision.
* `undo_last_confirm` (about line 952) - the decision an undo just reinstated, so R3 ("one
  revision back, once") holds.

The column is `Column(JSONB, nullable=True)` (`app/models/project_so.py:1264`).
SQLAlchemy's JSON type default (`none_as_null=False`) serialises a Python `None` VALUE as
the JSON literal `null`, not a SQL NULL - the column itself is never NULL, it holds a JSON
scalar. `_journalled_decision_clause()` (about line 90) guards with
`undo_journal.isnot(None)` (true for a JSON-null row: the column is not SQL NULL) then
`jsonb_array_length(undo_journal) > 0`, and Postgres raises `InvalidParameterValue: cannot
get array length of a scalar` on a JSON `null` - so `board_undo_map`, and therefore the
fulfilment planning board read (`GET /project-sales/fulfilment-planning/board`), 500s for
any order carrying one. Reproduced in raw psql on a prod copy.

RED for the right reason:

* Tests 1 and 2 read the column with raw SQL (`... IS NULL`, `jsonb_typeof(...)`) rather
  than through the ORM - a plain `decision.undo_journal is None` would pass even with the
  bug, because SQLAlchemy's JSON type deserialises the stored JSON `null` back into Python
  `None` on the way out, which is exactly why this bug survived review: nothing but a raw
  SQL read (or Postgres's own `jsonb_array_length`) can tell a JSON `null` apart from a SQL
  NULL. Both fail today with an assertion error (`is_sql_null` reads `False`,
  `jsonb_typeof` reads `'null'`) - not an import error or a fixture bug.
* Test 3 seeds a legacy-style row (`undo_journal = 'null'::jsonb` by raw SQL, standing in
  for a pre-fix row on prod) and calls the real board route; it fails today with a 500 -
  the reproduction itself - and pins a repair-independent contract once the crash is fixed:
  a JSON-null journal must read as not-undoable (`order["undo"] is None`), not merely
  "does not crash".

Postgres only, via the `api` fixture (`tests/_pg_fixture.py::blank_session` underneath) and
`_confirm_linked_world`, both borrowed from
`tests/test_board_undo_last_confirm.py`/`tests/test_so_supply_confirmation.py`. Every test
seeds its own full chain; nothing is borrowed from an existing row.
"""
from __future__ import annotations

from sqlalchemy import text

from app.models.project_so import SOSupplyDecision
from app.services.project_supply_undo_service import undo_last_confirm

from .test_board_undo_last_confirm import _confirm_linked_world
from .test_so_supply_confirmation import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    _stock,
    api,
)

MARKER = "zzt-undo-journal-null"


def _raw_journal_state(db, decision_id):
    """`(is_sql_null, jsonb_typeof)` read with raw SQL - the only way to tell a real SQL
    NULL apart from the JSON literal `null` the buggy Core SQL write leaves behind. A
    correctly-cleared journal reads `(True, None)`; the bug reads `(False, "null")`.
    """
    # Bare table name, never schema-qualified: `blank_session` resolves raw SQL through
    # `search_path` onto the scratch schema, and a real `projects` schema already exists
    # on this migrated database - `projects.so_supply_decisions` would silently read
    # (and find nothing in) THAT one instead of the test's own scratch rows.
    row = db.execute(
        text(
            "SELECT undo_journal IS NULL AS is_sql_null, jsonb_typeof(undo_journal) AS jtype "
            "FROM so_supply_decisions WHERE id = :id"
        ),
        {"id": decision_id},
    ).mappings().one()
    return bool(row["is_sql_null"]), row["jtype"]


def test_supersede_clears_journal_to_sql_null(api):
    """Confirm twice on one order: rev2 supersedes rev1. Rev1's journal must be cleared to
    a real SQL NULL, not the JSON literal `null` (`UndoJournal.attach`, ~line 316)."""
    fixture = _confirm_linked_world(api, second_buy_qty="15")
    db = fixture["db"]
    decision1 = fixture["decision1"]

    is_sql_null, jtype = _raw_journal_state(db, decision1.id)
    assert is_sql_null is True, (
        f"rev1's undo_journal must be SQL NULL after being superseded, not a JSON "
        f"literal (jsonb_typeof={jtype!r})"
    )
    assert jtype is None, f"jsonb_typeof must read NULL, not {jtype!r}"


def test_undo_clears_reinstated_journal_to_sql_null(api):
    """Confirm twice, then undo once: the reinstated rev1 (R3, "one revision back, once")
    must have its own journal cleared to a real SQL NULL, not the JSON literal `null`
    (`undo_last_confirm`, ~line 952)."""
    fixture = _confirm_linked_world(api, second_buy_qty="15")
    db = fixture["db"]
    order = fixture["order"]
    decision1 = fixture["decision1"]

    undo_last_confirm(db, order, actor_user_id=fixture["world"].eling)

    is_sql_null, jtype = _raw_journal_state(db, decision1.id)
    assert is_sql_null is True, (
        f"the reinstated decision's undo_journal must be SQL NULL, not a JSON literal "
        f"(jsonb_typeof={jtype!r})"
    )
    assert jtype is None, f"jsonb_typeof must read NULL, not {jtype!r}"


def test_board_read_survives_a_json_null_journal(api):
    """A legacy row (`undo_journal = 'null'::jsonb`, exactly what the bug writes and what
    a pre-fix prod row already carries) must not crash the fulfilment planning board read
    (`GET .../fulfilment-planning/board`, via `FulfilmentBoardService.build` ->
    `board_undo_map` -> `_journalled_decision_clause`). It must come back 200 and report
    the order as not undoable - the repair-independent guard
    (`jsonb_typeof(undo_journal) = 'array'`) rather than the raw `IS NOT NULL` this bug
    leans on today.
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    confirm = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="20")]},
    )
    assert confirm.status_code == 200, confirm.text

    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    assert decision.undo_journal, "setup: the confirm must journal normally first"

    # Simulate a legacy prod row: the JSON literal `null`, not a SQL NULL - exactly what
    # the buggy Core SQL `.values(undo_journal=None)` writes today.
    db.execute(
        text(
            "UPDATE so_supply_decisions SET undo_journal = 'null'::jsonb WHERE id = :id"
        ),
        {"id": decision.id},
    )
    db.commit()

    response = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core_so.so_number},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    order_standing = next(o for o in body["orders"] if o["so_number"] == core_so.so_number)
    assert order_standing["undo"] is None, (
        "a json-null journal must read as not-undoable, never crash the board"
    )
