"""AC-CF-1..16 (`PLAN-oi-confirm-per-so.md`,
`oi-confirm-per-so-acceptance-criteria.md`): red tests written BEFORE the coder, against
the contract only - no implementation for this slice exists yet.

S1 of the plan REVERSES G4 (`PLAN-scm-reorder-oi-feedback-1sep.md`): a row raised from
the fulfilment board is born `awaiting` again, not `acknowledged`
(`_handshake_for_raise`, `app/services/project_order_inquiry_service.py`), and
purchasing's own Confirm press is what takes it on - the very thing G4 retired. Most of
the assertions below therefore state the POST-S1 world and fail TODAY for that single
reason: the raise still stamps `ACK_ACKNOWLEDGED`. `tests/test_order_inquiry_handshake.py`
and `tests/test_order_inquiry_handshake_edges.py` pin the PRE-S1 (G4) behaviour this lane
retires and are left untouched here - they are the coder's to update, not the tester's.

Reuses `tests/test_order_inquiry_handshake.py`'s harness wholesale (`world` / `api`
fixtures - one CS user, one purchasing user, one project, one product, one warehouse,
company-scoped and rolled back; `_raise_one_row`, `_as_purchasing`, `_settle`,
`_project_committed`, `_open_po_line`, `_links_of`) rather than rebuilding it: every row
this file touches is seeded fresh, behind that harness's own `zzt-planchg` / `ZZT-`
markers, inside ONE outer transaction rolled back at teardown - nothing here depends on
a row already in the shared local database.

Runs on the REAL database (rolled back), for the same reason the harness does:
`scm.committed_v`, the `ack_state` column and its index all live in the migrated schema,
which a blank scratch schema does not carry.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
)

from ..test_order_inquiry_handshake import (
    ACK_URL,
    LIST,
    WAS,
    _as_purchasing,
    _confirm,
    _core_line,
    _core_so,
    _line_payload,
    _links_of,
    _open_po_line,
    _order_row,
    _project_committed,
    _project_line,
    _project_so,
    _raise_one_row,
    _settle,
    api,
    world,
)

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused


# ---------------------------------------------------------------------------
# seeding helper this file owns: several rows on ONE sales order
# ---------------------------------------------------------------------------


def _raise_n_rows_one_so(api, qtys):
    """N lines of ONE sales order, all confirmed wholly as Buy in a single press - N
    raised inquiry rows sharing one SO number a caller can search by (AC-CF-8b)."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_lines = [
        _core_line(
            db, core_so, world.product, world.warehouse,
            qty_ordered=qty, required_date=WAS,
        )
        for qty in qtys
    ]
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    lines = [
        _project_line(db, order, line_no=i + 1, product=world.product, core_line=core_line)
        for i, core_line in enumerate(core_lines)
    ]
    db.commit()

    response = _confirm(
        client, order.id,
        [_line_payload(line.id, buy_qty=qty) for line, qty in zip(lines, qtys)],
    )
    assert response.status_code == 200, response.text
    db.commit()
    return {
        "order": order,
        "so_number": core_so.so_number,
        "lines": lines,
        "rows": [_order_row(world, line) for line in lines],
    }


# ---------------------------------------------------------------------------
# AC-CF-1 / AC-CF-2 / AC-CF-3: the handshake, reversed
# ---------------------------------------------------------------------------


def test_ac_cf_1_row_born_awaiting_on_raise(api):
    """AC-CF-1. A board confirm raises a row `awaiting`, `acknowledged_by`/`_at` null.

    Today `_handshake_for_raise` returns `(ACK_ACKNOWLEDGED, actor_user_id, now, None)`
    for a fresh row (G4) - red on all three assertions until the raise is flipped to
    born-awaiting (S1)."""
    _client, world = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]

    assert row.ack_state == ACK_AWAITING
    assert row.acknowledged_by is None
    assert row.acknowledged_at is None


def test_ac_cf_2_carry_keeps_a_confirmed_rows_ack_fields(api):
    """AC-CF-2. The row is forced to `awaiting` first (the S1 precondition the raise
    will create natively) and genuinely taken on via `acknowledge_rows`; CS then
    re-confirms naming a DIFFERENT line of the same order, so the taken-on row is
    CARRIED, not restated. `_handshake_for_raise`'s `carried` branch copies the prior
    row's stamps verbatim and does not read whether the prior state was born-
    acknowledged or genuinely acknowledged - that branch is untouched by S1, so this
    already passes: a regression pin for the half of the handshake this lane leaves
    alone, not a red test."""
    _client, world = api
    fixture = _raise_n_rows_one_so(api, ["4", "6"])
    kept_row, _other_row = fixture["rows"]
    kept_row.ack_state = ACK_AWAITING
    kept_row.acknowledged_by = None
    kept_row.acknowledged_at = None
    world.db.commit()

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(ACK_URL, json={"row_ids": [str(kept_row.id)]}).status_code == 200
        )
    world.db.commit()
    world.db.refresh(kept_row)
    stamped_by, stamped_at = kept_row.acknowledged_by, kept_row.acknowledged_at
    assert stamped_by and stamped_at

    other_line = fixture["lines"][1]
    response = _confirm(
        _client, fixture["order"].id, [_line_payload(other_line.id, buy_qty="6")]
    )
    assert response.status_code == 200, response.text
    world.db.commit()

    # The carry cancels-and-re-raises under the new revision (13.4) - a FRESH row id,
    # not the same one - so what this proves is the stamp travelling, not the id.
    carried = _order_row(world, fixture["lines"][0])
    assert carried.ack_state == ACK_ACKNOWLEDGED
    assert carried.acknowledged_by == stamped_by
    assert carried.acknowledged_at == stamped_at
    assert carried.changed_at is None


def test_ac_cf_3_change_on_an_acknowledged_row_marks_changed_not_reacknowledged(api):
    """AC-CF-3. Forced to `awaiting` first, then genuinely acknowledged by purchasing,
    then CS changes the quantity: `_settle_row_in_place`
    (`project_order_inquiry_service.py`, the `if row.ack_state in (ACK_ACKNOWLEDGED,
    ACK_CHANGED):` block) today re-stamps `ack_state=ACK_ACKNOWLEDGED`,
    `acknowledged_by=<the CS actor>`, `acknowledged_at=<now>` on every change - the
    opposite of AC-CF-3, which wants `changed` and purchasing's PRIOR stamp kept
    untouched. Red on `ack_state`, `acknowledged_by` and `acknowledged_at`."""
    _client, world = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    row.ack_state = ACK_AWAITING
    row.acknowledged_by = None
    row.acknowledged_at = None
    world.db.commit()

    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    world.db.commit()
    world.db.refresh(row)
    stamped_by, stamped_at = row.acknowledged_by, row.acknowledged_at
    assert stamped_by and stamped_at

    _settle(world, fixture, qty="25")

    world.db.refresh(row)
    assert row.ack_state == ACK_CHANGED
    assert row.changed_at is not None
    assert row.acknowledged_by == stamped_by
    assert row.acknowledged_at == stamped_at
    assert Decimal(str(row.qty)) == Decimal("25")
    assert Decimal(str(row.previous_qty)) == Decimal("10")


# ---------------------------------------------------------------------------
# AC-CF-4: the cascade never waited for confirm
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason=(
        "AC-CF-4 already holds today: `ProjectSupplyService._draft_links_for_decision` "
        "always calls `auto_place_for_products(..., include_awaiting=True)` at raise "
        "time, so an open PO line links to a fresh row whatever its ack_state. Cannot "
        "force the row to genuinely BE awaiting before that raise-time cascade runs "
        "(that is exactly what S1 changes), so this only proves the weaker, "
        "currently-true half - it passes by coincidence pre-S1 and for real once the "
        "raise is born awaiting. xfail(strict=False) so an XPASS is not a failure "
        "either side of that change."
    ),
)
def test_ac_cf_4_cascade_still_auto_links_an_awaiting_row_on_raise(api):
    _client, world = api
    po, _line = _open_po_line(world, qty=50)

    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]

    assert [link.document for link in _links_of(world, row)] == [po.po_number]


# ---------------------------------------------------------------------------
# AC-CF-8: row_ids OR filter, never both, never neither
# ---------------------------------------------------------------------------


def test_ac_cf_8a_acknowledge_by_row_ids_still_works(api):
    """AC-CF-8a. `POST /order-inquiries/acknowledge` with `row_ids` exists today and
    must keep working once `filter` lands beside it - the regression pin. Forced to
    `awaiting` first so the press is a genuine transition, not the born-ack no-op."""
    _client, world = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    row.ack_state = ACK_AWAITING
    row.acknowledged_by = None
    row.acknowledged_at = None
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(ACK_URL, json={"row_ids": [str(row.id)]})
    assert response.status_code == 200, response.text
    assert response.json()["acknowledged"] == 1
    world.db.commit()
    world.db.refresh(row)
    assert row.ack_state == ACK_ACKNOWLEDGED


def test_ac_cf_8b_acknowledge_by_filter_scopes_to_one_so(api):
    """AC-CF-8 / AC-CF-8b. `AcknowledgeRowsRequest` has no `filter` field today
    (`row_ids: List[str] = Field(..., min_length=1)`) - a body naming only `filter` is
    refused for a MISSING `row_ids`, a 422 for the whole unbuilt feature rather than the
    scoping this test is really about (which SO's rows a filter reaches, and that a
    cancelled or rejected row in the same SO is skipped)."""
    client, world = api
    here = _raise_n_rows_one_so(api, ["4", "6", "3"])
    eligible_row, to_cancel_row, to_reject_row = here["rows"]
    eligible_row.ack_state = ACK_AWAITING
    eligible_row.acknowledged_by = None
    eligible_row.acknowledged_at = None
    to_cancel_row.state = INQUIRY_CANCELLED
    world.db.commit()

    with _as_purchasing(world) as buyer:
        assert (
            buyer.post(
                f"{LIST}/{to_reject_row.id}/reject", json={"reason": "No stock"}
            ).status_code
            == 200
        )
    world.db.commit()

    elsewhere = _raise_one_row(api, qty="9")
    elsewhere["row"].ack_state = ACK_AWAITING
    elsewhere["row"].acknowledged_by = None
    elsewhere["row"].acknowledged_at = None
    world.db.commit()

    with _as_purchasing(world) as buyer:
        response = buyer.post(ACK_URL, json={"filter": {"query": here["so_number"]}})

    assert response.status_code == 200, response.text
    world.db.refresh(eligible_row)
    assert eligible_row.ack_state == ACK_ACKNOWLEDGED
    world.db.refresh(to_cancel_row)
    assert to_cancel_row.ack_state != ACK_ACKNOWLEDGED, "a cancelled row is skipped"
    world.db.refresh(elsewhere["row"])
    assert elsewhere["row"].ack_state == ACK_AWAITING, "a different SO is untouched"


def test_ac_cf_8c_row_ids_and_filter_are_mutually_exclusive(api):
    """AC-CF-8c. Both named at once, or neither, is 422. Today `filter` is an
    undeclared field the schema silently ignores (no `model_config`, pydantic v2
    default `extra="ignore"`), so `both` below actually SUCCEEDS on `row_ids` alone
    (200, not 422) - red for the missing mutual-exclusion guard, not a fixture bug.
    `neither` already 422s today, coincidentally, because `row_ids` alone is a required
    field (`min_length=1`); that half is asserted here too so the future error path (a
    bespoke 'name one' validation) is pinned by the same test once it exists."""
    _client, world = api
    fixture = _raise_one_row(api, qty="4")
    row = fixture["row"]

    with _as_purchasing(world) as buyer:
        both = buyer.post(
            ACK_URL,
            json={"row_ids": [str(row.id)], "filter": {"query": "anything"}},
        )
        neither = buyer.post(ACK_URL, json={})

    assert both.status_code == 422, both.text
    assert neither.status_code == 422, neither.text


# ---------------------------------------------------------------------------
# AC-CF-9: CS is still refused
# ---------------------------------------------------------------------------


def test_ac_cf_9_cs_principal_refused_403_on_acknowledge(api):
    """AC-CF-9. `require_permission(ACKNOWLEDGE)` already gates the route - a
    regression pin, not a red test."""
    cs_client, world = api
    fixture = _raise_one_row(api, qty="5")

    response = cs_client.post(ACK_URL, json={"row_ids": [str(fixture["row"].id)]})

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# AC-CF-11: the default view (FE-side, per the plan's own measured facts)
# ---------------------------------------------------------------------------


def test_ac_cf_11_no_ack_param_lists_everything_to_confirm_narrows(api):
    """AC-CF-11. The backend contract is UNCHANGED by this lane:
    `order_inquiry_worklist_service.py`'s `if ack:` gate means an absent `ack` param has
    always meant no filter, and S3 makes the FE send `ack=to_confirm` when the URL is
    silent, per the plan's own measured facts ("FE: absent `?ack` = no filter"). Pinned
    here as a regression guard on the mechanism S3 depends on, not a red test: `awaiting`
    and `changed` are forced directly since a fresh raise cannot naturally produce
    either pre-S1."""
    client, world = api
    awaiting = _raise_one_row(api, qty="1")
    changed = _raise_one_row(api, qty="1")
    acknowledged = _raise_one_row(api, qty="1")

    awaiting["row"].ack_state = ACK_AWAITING
    awaiting["row"].acknowledged_by = None
    awaiting["row"].acknowledged_at = None
    changed["row"].ack_state = ACK_CHANGED
    changed["row"].changed_at = datetime.utcnow()
    world.db.commit()

    every = client.get(LIST, params={"limit": 200}).json()
    every_ids = {row["id"] for row in every["data"]}
    for fixture in (awaiting, changed, acknowledged):
        assert str(fixture["row"].id) in every_ids, "no ?ack param filters nothing"

    to_confirm = client.get(LIST, params={"ack": "to_confirm", "limit": 200}).json()
    to_confirm_ids = {row["id"] for row in to_confirm["data"]}
    assert str(awaiting["row"].id) in to_confirm_ids
    assert str(changed["row"].id) in to_confirm_ids
    assert str(acknowledged["row"].id) not in to_confirm_ids


# ---------------------------------------------------------------------------
# AC-CF-12: the tile's own count
# ---------------------------------------------------------------------------


def test_ac_cf_12_summary_to_confirm_counts_a_freshly_raised_row(api):
    """AC-CF-12. Once S1 ships, a fresh raise is born `awaiting`, so it counts in
    `summary.ack.to_confirm` (`_acks`, `order_inquiry_worklist_service.py`, which
    already sums `awaiting + changed` correctly) the instant CS confirms. Today the
    raise is still born `acknowledged` (G4), so the row is ABSENT from `to_confirm` -
    red for that reason, not a summary-arithmetic bug."""
    client, world = api
    before = client.get(
        f"{LIST}/summary", params={"project_id": str(world.project.id)}
    ).json()["ack"]["to_confirm"]

    _raise_one_row(api, qty="7")

    after = client.get(
        f"{LIST}/summary", params={"project_id": str(world.project.id)}
    ).json()["ack"]["to_confirm"]

    assert after == before + 1


# ---------------------------------------------------------------------------
# AC-CF-14: planning reads confirmed demand only
# ---------------------------------------------------------------------------


def test_ac_cf_14_demand_excludes_awaiting_includes_confirmed_and_changed(api):
    """AC-CF-14. `demand.horizon_committed_select_sql()`'s `PLANNED_ACK_STATES =
    ("acknowledged", "changed")` already excludes anything else - the SQL predicate is
    right today. What is wrong is the BORN state: a fresh raise is `acknowledged`
    already (G4), so it is already inside the plan's demand the instant CS confirms,
    the opposite of what this test pins. Red on the first assertion."""
    _client, world = api
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]

    assert _project_committed(world, planned=True) == Decimal("0"), (
        "a freshly raised row must not be planning demand until purchasing confirms it"
    )

    with _as_purchasing(world) as buyer:
        assert buyer.post(ACK_URL, json={"row_ids": [str(row.id)]}).status_code == 200
    world.db.commit()
    assert _project_committed(world, planned=True) == Decimal("10")

    _settle(world, fixture, qty="15")
    assert _project_committed(world, planned=True) == Decimal("15"), (
        "a changed row stays counted"
    )


# ---------------------------------------------------------------------------
# AC-CF-16: the deploy migration (R1)
# ---------------------------------------------------------------------------

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "oicf_0001_board_rows_to_confirm.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_oicf_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.upgrade()
    return module


def _run_downgrade(db, module) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.downgrade()


def test_ac_cf_16_migration_flips_open_board_rows_only(api):
    """AC-CF-16 (R1). `alembic/versions/oicf_0001_board_rows_to_confirm.py` does not
    exist yet, so `_migration_module()` fails inside `exec_module` (the file cannot be
    opened) - the right red for a slice not yet built. Once it exists: a board row
    (`supply_decision_id` set, `acknowledged`, still open) flips to `awaiting` with its
    ack stamps cleared; a sheet row (`supply_decision_id IS NULL`), a cancelled board
    row and an actioned board row are all left exactly as they are; `downgrade()`
    restores the flipped row (system-attributed, the same convention
    `454_order_inquiry_born_ack.py` uses for its own backfill)."""
    _client, world = api

    board = _raise_one_row(api, qty="4")["row"]
    assert board.supply_decision_id is not None, "raised from the board, so it has one"

    sheet = _raise_one_row(api, qty="6")["row"]
    sheet.supply_decision_id = None  # what the Excel importer's own row looks like

    cancelled = _raise_one_row(api, qty="3")["row"]
    cancelled.state = INQUIRY_CANCELLED

    actioned = _raise_one_row(api, qty="5")["row"]
    actioned.state = INQUIRY_ACTIONED

    world.db.commit()
    stamped_sheet_by = sheet.acknowledged_by
    stamped_sheet_at = sheet.acknowledged_at

    module = _run_upgrade(world.db)

    world.db.expire_all()
    world.db.refresh(board)
    world.db.refresh(sheet)
    world.db.refresh(cancelled)
    world.db.refresh(actioned)

    assert board.ack_state == ACK_AWAITING
    assert board.acknowledged_by is None
    assert board.acknowledged_at is None

    assert sheet.ack_state == ACK_ACKNOWLEDGED
    assert sheet.acknowledged_by == stamped_sheet_by
    assert sheet.acknowledged_at == stamped_sheet_at

    assert cancelled.ack_state == ACK_ACKNOWLEDGED
    assert actioned.ack_state == ACK_ACKNOWLEDGED

    _run_downgrade(world.db, module)

    world.db.expire_all()
    world.db.refresh(board)
    assert board.ack_state == ACK_ACKNOWLEDGED
    assert board.acknowledged_at is not None
