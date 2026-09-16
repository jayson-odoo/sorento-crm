"""Order inquiry handover email to purchasing (`PLAN-scm-oi-handover-email.md`, S0-S3).

Contract: `documentation/plans/scm/scm-oi-handover-email-acceptance-criteria.md`, AC-H1 to
AC-H18. TEST-FIRST: written before the recorder/drain/trigger/template exist, so a red
here is a missing attribute (`ProjectOrderInquiryService._record_handover`, the module
constant `_HANDOVER_PENDING_KEY`, the pure function `handover_remark`), a missing trigger
type in the catalog, a missing seed migration, or simply "the automation was never
dispatched" - never an import typo or a fixture bug.

Two harnesses, matching the two things under test:

* the RECORDER/DRAIN/DISPATCH contract (AC-H1 to AC-H10, AC-H15, AC-H17, AC-H18) reuses
  `tests/test_order_inquiry_handshake.py`'s `world` / `api` fixtures wholesale, for the
  same reason `tests/test_order_inquiry_changed_with_links_automation.py` does: one
  seeding chain, the REAL database (`scm.committed_v` and the handshake columns live only
  in the migrated schema), and `AutomationService.dispatch_event` monkeypatched rather
  than exercised for real - the drain's fresh `SessionLocal()` is a genuinely separate
  connection that cannot see this suite's own rolled-back savepoint, so a real dispatch
  attempting to re-read the raised row would find nothing there;
* the TRIGGER CATALOG (AC-H12), RECIPIENT RESOLVER (AC-H11) and SEED MIGRATION + TEMPLATE
  (AC-H13/AC-H14) need no shared seeding chain at all, and use `tests/_pg_fixture.py`'s
  `blank_session()` - a blank scratch schema - instead.

AC-H6 (CHANGE SO NO) is pinned at the `_record_handover` contract boundary rather than
through a real delivery-schedule delta + amendment write, and AC-H15's "outbox row"
language is satisfied via the mocked dispatch call's ordering rather than a literal
`email_outbox` row - both narrowed deliberately; see the module-level note above each test
for why, and the tester's report for the full reasoning.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.base import company_scope
from app.models.project_so import (
    INQUIRY_CANCELLED,
    IV_ALREADY_INBOUND,
    IV_CHANGE_SO,
    IV_ORDER,
    IV_ORDER_BACK,
    IV_PRE_ORDERED,
    IV_RESERVE_AND_ORDER,
    OrderInquiry,
)
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.automation_triggers import build_order_inquiry_link
from app.services.project_order_inquiry_service import ProjectOrderInquiryService
from app.services.project_supply_service import ProjectSupplyService

from ._pg_fixture import blank_session
from .test_order_inquiry_handshake import (
    ACK_URL,
    LINK_NOW,
    LIST,
    NOW,
    WAS,
    _as_purchasing,
    _confirm,
    _core_line,
    _core_so,
    _line_payload,
    _open_po_line,
    _project_line,
    _project_so,
    _raise_one_row,
    _raise_two_rows,
    _uid,
    _warehouse,
    api,
    world,
)

__all__ = ["api", "world"]  # re-exported fixtures; keeps linters from calling them unused

TRIGGER = "order_inquiry_handover"


# --------------------------------------------------------------------------- #
# shared harness (mirrors test_order_inquiry_changed_with_links_automation.py) #
# --------------------------------------------------------------------------- #


def _captured_dispatches(monkeypatch) -> list[dict]:
    """Intercepts `AutomationService.dispatch_event` on the drain's fresh session."""
    calls: list[dict] = []

    def _fake_dispatch(self, trigger_type, *, context, source_kind, source_id):
        calls.append(
            {
                "trigger_type": trigger_type,
                "context": context,
                "source_kind": source_kind,
                "source_id": source_id,
            }
        )
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event",
        _fake_dispatch,
    )
    return calls


def _register(world) -> None:
    """Idempotent (module-global flag), same call site the sibling suite uses -
    `TestClient(app)` without `with` never runs FastAPI's lifespan here."""
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()


def _handover_calls(calls: list[dict]) -> list[dict]:
    return [c for c in calls if c["trigger_type"] == TRIGGER]


def _row(**kwargs) -> SimpleNamespace:
    """A stand-in for `OrderInquiryRow`. `handover_remark` is documented (PLAN 3.3) as a
    PURE, table-tested function that reads a handful of attributes off the row - a
    lightweight namespace pins the table without a database."""
    base = dict(
        verb=None,
        qty=None,
        delivery_date=None,
        previous_qty=None,
        previous_delivery_date=None,
        cited_document=None,
        note=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# AC-H12: trigger catalog                                                     #
# --------------------------------------------------------------------------- #


def test_trigger_in_catalog():
    from app.services import automation_triggers

    spec = next(
        (s for s in automation_triggers.list_specs() if s.type == TRIGGER),
        None,
    )
    assert spec is not None, f"{TRIGGER!r} must be registered in the trigger catalog"
    assert spec.config_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


# --------------------------------------------------------------------------- #
# AC-H2/H3/H4/H5: handover_remark, table-tested and pure (PLAN 3.3)            #
# --------------------------------------------------------------------------- #


def test_handover_remark_raised_rows_use_the_verb_label():
    """AC-H2: ORDER / RESERVE & ORDER / PRE-ORDERED / ALREADY INBOUND print their own
    verb label with no `was`; ORDER BACK appends the cited document."""
    from app.services.project_order_inquiry_service import handover_remark

    assert handover_remark("raised", _row(verb=IV_ORDER), None) == "ORDER"
    assert (
        handover_remark("raised", _row(verb=IV_RESERVE_AND_ORDER), None)
        == "RESERVE & ORDER"
    )
    assert (
        handover_remark("raised", _row(verb=IV_PRE_ORDERED), None)
        == "PRE-ORDERED, DO NOT ORDER"
    )
    assert (
        handover_remark("raised", _row(verb=IV_ALREADY_INBOUND), None)
        == "ALREADY INBOUND"
    )

    order_back = handover_remark(
        "raised", _row(verb=IV_ORDER_BACK, cited_document="SPO-2026/08-0061"), None
    )
    assert order_back.startswith("ORDER BACK")
    assert "SPO-2026/08-0061" in order_back


def test_handover_remark_appends_a_cs_note_after_the_verb():
    """AC-H2: "`note` appended after ' - ' when present" (PLAN 3.3)."""
    from app.services.project_order_inquiry_service import handover_remark

    remark = handover_remark(
        "raised", _row(verb=IV_ORDER, note="Confirmed by WhatsApp"), None
    )
    assert remark == "ORDER - Confirmed by WhatsApp"


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (WAS, NOW, "ADVANCE"),  # NOW (19 Aug) is earlier than WAS (25 Aug)
        (NOW, WAS, "DELAY"),
    ],
)
def test_handover_remark_settle_date_advance_or_delay(old, new, expected):
    """AC-H3."""
    from app.services.project_order_inquiry_service import handover_remark

    row = _row(verb=IV_ORDER, qty=Decimal("10"), delivery_date=new)
    remark = handover_remark("settled", row, {"delivery_date": old})
    assert remark == expected


def test_handover_remark_settle_qty_down_cancel_balance_up_order():
    """AC-H4."""
    from app.services.project_order_inquiry_service import handover_remark

    down = handover_remark(
        "settled", _row(verb=IV_ORDER, qty=Decimal("6"), delivery_date=WAS),
        {"qty": Decimal("10")},
    )
    assert down == "CANCEL BALANCE 4 NOS"

    up = handover_remark(
        "settled", _row(verb=IV_ORDER, qty=Decimal("15"), delivery_date=WAS),
        {"qty": Decimal("10")},
    )
    assert up == "ORDER 5"


def test_handover_remark_settle_both_moved_joins_date_then_qty():
    """AC-H4's table row: "settled, both moved: date verb first, then qty phrase,
    joined by ', '" (PLAN 3.3)."""
    from app.services.project_order_inquiry_service import handover_remark

    remark = handover_remark(
        "settled",
        _row(verb=IV_ORDER, qty=Decimal("15"), delivery_date=NOW),
        {"qty": Decimal("10"), "delivery_date": WAS},
    )
    assert remark == "ADVANCE, ORDER 5"


def test_handover_remark_settle_to_zero_is_cancel_balance():
    """AC-H5."""
    from app.services.project_order_inquiry_service import handover_remark

    remark = handover_remark(
        "cancelled", _row(verb=IV_ORDER, qty=Decimal("0")), {"qty": Decimal("10")}
    )
    assert remark == "CANCEL BALANCE 10 NOS"


# --------------------------------------------------------------------------- #
# AC-H1: one dispatch per commit, however many orders it raised                #
# --------------------------------------------------------------------------- #


def test_one_dispatch_per_commit_two_orders(api, monkeypatch):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    db = world.db
    supply = ProjectSupplyService(db)

    core_so_1 = _core_so(db, world.company_id)
    core_line_1 = _core_line(
        db, core_so_1, world.product, world.warehouse, qty_ordered="10", required_date=WAS
    )
    order_1 = _project_so(
        db, world.project, so_id=core_so_1.id, autocount_doc_no=core_so_1.so_number
    )
    line_1 = _project_line(db, order_1, line_no=1, product=world.product, core_line=core_line_1)

    core_so_2 = _core_so(db, world.company_id)
    core_line_2 = _core_line(
        db, core_so_2, world.product, world.warehouse, qty_ordered="8", required_date=WAS
    )
    order_2 = _project_so(
        db, world.project, so_id=core_so_2.id, autocount_doc_no=core_so_2.so_number
    )
    line_2 = _project_line(db, order_2, line_no=1, product=world.product, core_line=core_line_2)
    db.commit()

    supply.confirm(
        order_1,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(line_1.id), buy_qty="10")]),
        actor_user_id=world.cs_user,
    )
    supply.confirm(
        order_2,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(line_2.id), buy_qty="8")]),
        actor_user_id=world.cs_user,
    )
    db.commit()

    matches = _handover_calls(calls)
    assert len(matches) == 1, f"expected exactly one dispatch for the one commit, got {len(matches)}"
    handover = matches[0]["context"]["handover"]
    so_numbers = {o["so_number"] for o in handover["orders"]}
    assert so_numbers == {core_so_1.so_number, core_so_2.so_number}
    assert len(handover["lines"]) == 2


# --------------------------------------------------------------------------- #
# AC-H2 (end-to-end half): raised rows carry no `was`; ORDER BACK cites its    #
# document                                                                     #
# --------------------------------------------------------------------------- #


def test_raised_rows_no_was_and_order_back_carries_cited_document(api, monkeypatch):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    db = world.db

    core_so = _core_so(db, world.company_id)
    plain_core = _core_line(
        db, core_so, world.product, world.warehouse, qty_ordered="10", required_date=WAS
    )
    order_back_core = _core_line(
        db, core_so, world.product, world.warehouse, qty_ordered="6", required_date=WAS
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    plain_line = _project_line(db, order, line_no=1, product=world.product, core_line=plain_core)
    order_back_line = _project_line(
        db, order, line_no=2, product=world.product, core_line=order_back_core
    )
    db.commit()

    payload = [
        _line_payload(plain_line.id, buy_qty="10"),
        {
            **_line_payload(order_back_line.id, buy_qty="6"),
            "order_back": True,
            "cited_document": "SPO-2026/08-0061",
        },
    ]
    response = _confirm(client, order.id, payload)
    assert response.status_code == 200, response.text
    db.commit()

    matches = _handover_calls(calls)
    assert matches, "the raise must dispatch the handover"
    lines = matches[-1]["context"]["handover"]["lines"]
    plain = next(l for l in lines if l["remark"] == "ORDER")
    assert plain["was"] is None
    order_back = next(l for l in lines if l["remark"].startswith("ORDER BACK"))
    assert order_back["was"] is None
    assert "SPO-2026/08-0061" in order_back["remark"]


# --------------------------------------------------------------------------- #
# AC-H3/H4/H5 (end-to-end half): the real settle seam records + dispatches    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("new_date", "expected_remark"),
    [(NOW, "ADVANCE"), (date(2026, 9, 10), "DELAY")],
)
def test_settle_date_earlier_is_advance_later_is_delay(api, monkeypatch, new_date, expected_remark):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    fixture = _raise_one_row(api, qty="10")
    calls.clear()  # only the settle's own dispatch matters here

    from .test_order_inquiry_handshake import _settle

    _settle(world, fixture, qty="10", required_date=new_date)

    matches = _handover_calls(calls)
    assert matches, "a settle that moves the date must dispatch the handover"
    line = matches[-1]["context"]["handover"]["lines"][0]
    assert line["remark"] == expected_remark
    assert line["was"]["delivery_date"] == WAS.strftime("%d/%m/%Y")
    assert line["delivery_date"] == new_date.strftime("%d/%m/%Y")


@pytest.mark.parametrize(
    ("new_qty", "expected_remark"),
    [("6", "CANCEL BALANCE 4 NOS"), ("15", "ORDER 5")],
)
def test_settle_qty_down_cancel_balance_up_order(api, monkeypatch, new_qty, expected_remark):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    fixture = _raise_one_row(api, qty="10")
    calls.clear()

    from .test_order_inquiry_handshake import _settle

    _settle(world, fixture, qty=new_qty, required_date=WAS)

    matches = _handover_calls(calls)
    assert matches, "a qty settle must dispatch the handover"
    line = matches[-1]["context"]["handover"]["lines"][0]
    assert line["remark"] == expected_remark
    assert line["was"]["qty"] == "10"
    assert line["qty"] == new_qty


def test_settle_to_zero_prints_cancel_balance(api, monkeypatch):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    fixture = _raise_one_row(api, qty="10")
    calls.clear()

    from .test_order_inquiry_handshake import _settle

    _settle(world, fixture, qty="0")

    matches = _handover_calls(calls)
    assert matches, "a settle to zero must dispatch the handover"
    line = matches[-1]["context"]["handover"]["lines"][0]
    assert line["qty"] == "0"
    assert line["was"]["qty"] == "10"
    assert line["remark"] == "CANCEL BALANCE 10 NOS"


# --------------------------------------------------------------------------- #
# AC-H6: CHANGE SO NO - pinned at the `_record_handover` contract boundary    #
# --------------------------------------------------------------------------- #


def test_change_so_row_carries_source_in_was(api, monkeypatch):
    """AC-H6.

    The plan itself flags (section 6, item 1) that WHICH FIELD an `IV_CHANGE_SO` row's
    raise reads for "the source order" is still to be discovered while building - the
    only real producer of this verb (`derive_for_amendment` reading a delivery-schedule
    delta's `CHANGE_REPOINT` rows) reports `field: "area_group"`,
    `from_value: "COMMON AREA"` / `to_value: "PODIUM"` (see
    `tests/test_project_so_delta.py::test_...`), not a second sales order's
    so_number/customer/project - so reproducing that whole delivery-schedule fixture
    chain here would not exercise AC-H6 as WRITTEN, only whatever the coder decides that
    ambiguity resolves to. This test instead pins the CONTRACT one level down: whatever
    the raise seam captures as `was` for a CHANGE SO NO row reaches the dispatched
    context unchanged, keyed by so_number/customer/project, while the row's own line is
    read as usual (the TARGET) at drain time.
    """
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    fixture = _raise_one_row(api, qty="10")
    row = fixture["row"]
    row.verb = IV_CHANGE_SO
    world.db.flush()

    service = ProjectOrderInquiryService(world.db)
    service._record_handover(
        row,
        kind="raised",
        was={
            "so_number": "SO-SOURCE-001",
            "customer": "SOURCE CUSTOMER SDN BHD",
            "project": "Source Project",
        },
        actor_user_id=world.cs_user,
    )
    world.db.commit()

    matches = _handover_calls(calls)
    assert matches
    line = matches[-1]["context"]["handover"]["lines"][-1]
    assert line["was"] == {
        "so_number": "SO-SOURCE-001",
        "customer": "SOURCE CUSTOMER SDN BHD",
        "project": "Source Project",
    }
    assert line["so_number"] == fixture["core_so"].so_number
    assert line["remark"] == "CHANGE SO NO"


# --------------------------------------------------------------------------- #
# AC-H7: subject scope                                                        #
# --------------------------------------------------------------------------- #


def test_subject_scope_single_and_mixed_location(api, monkeypatch):
    """AC-H7.

    `ProjectSupplyService._restamp_stock_location` overwrites `line.stock_location` with
    the CONFIRMED core line's own warehouse code (`fact.own_code`, read off
    `core.warehouse_id` in `_facts_for`) on every confirm - so hand-setting
    `ProjectSalesOrderLine.stock_location` directly never survives (coder finding, 16
    Sep). The location has to be driven the way the system actually derives it: give
    each CORE line its own warehouse and let the confirm's own restamp read it back.
    """
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    db = world.db
    supply = ProjectSupplyService(db)

    # One order, two lines, ONE shared warehouse -> "<location> @ <so>".
    shared_wh = _warehouse(db, f"ZZT-OIHE-{_uid()[:8]}")
    core_so = _core_so(db, world.company_id)
    line_a_core = _core_line(
        db, core_so, world.product, shared_wh, qty_ordered="10", required_date=WAS
    )
    line_b_core = _core_line(
        db, core_so, world.product, shared_wh, qty_ordered="6", required_date=WAS
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line_a = _project_line(db, order, line_no=1, product=world.product, core_line=line_a_core)
    line_b = _project_line(db, order, line_no=2, product=world.product, core_line=line_b_core)
    db.commit()

    response = _confirm(
        client, order.id,
        [_line_payload(line_a.id, buy_qty="10"), _line_payload(line_b.id, buy_qty="6")],
    )
    assert response.status_code == 200, response.text
    db.commit()

    matches = _handover_calls(calls)
    assert matches, "the raise must dispatch the handover"
    assert (
        matches[-1]["context"]["handover"]["subject_scope"]
        == f"{shared_wh.warehouse_code} @ {core_so.so_number}"
    )
    calls.clear()

    # Two DIFFERENT orders, two DIFFERENT warehouses, one commit -> mixed, no location.
    wh_c = _warehouse(db, f"ZZT-OIHE-{_uid()[:8]}")
    wh_d = _warehouse(db, f"ZZT-OIHE-{_uid()[:8]}")
    core_so_2 = _core_so(db, world.company_id)
    line_c_core = _core_line(
        db, core_so_2, world.product, wh_c, qty_ordered="4", required_date=WAS
    )
    order_2 = _project_so(
        db, world.project, so_id=core_so_2.id, autocount_doc_no=core_so_2.so_number
    )
    line_c = _project_line(db, order_2, line_no=1, product=world.product, core_line=line_c_core)

    core_so_3 = _core_so(db, world.company_id)
    line_d_core = _core_line(
        db, core_so_3, world.product, wh_d, qty_ordered="3", required_date=WAS
    )
    order_3 = _project_so(
        db, world.project, so_id=core_so_3.id, autocount_doc_no=core_so_3.so_number
    )
    line_d = _project_line(db, order_3, line_no=1, product=world.product, core_line=line_d_core)
    db.commit()

    supply.confirm(
        order_2,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(line_c.id), buy_qty="4")]),
        actor_user_id=world.cs_user,
    )
    supply.confirm(
        order_3,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(line_d.id), buy_qty="3")]),
        actor_user_id=world.cs_user,
    )
    db.commit()

    mixed = _handover_calls(calls)
    assert mixed, "the mixed-location write must dispatch too"
    assert (
        mixed[-1]["context"]["handover"]["subject_scope"]
        == f"{core_so_2.so_number} , {core_so_3.so_number}"
    )


# --------------------------------------------------------------------------- #
# AC-H19: a retired row (dropped from the buy list, no settle) still prints    #
# as a cancelled line; an unrelated raise in the same commit prints beside it #
# --------------------------------------------------------------------------- #


def test_retired_row_prints_cancelled_line(api, monkeypatch):
    """AC-H19.

    `_retire_uncovered_rows` retires a row whose LINE was dropped from the buy list
    entirely - CS un-decided it (`ProjectSupplyService.uncover_lines`, the same seam
    `test_order_inquiry_changed_with_links_automation.py`'s
    `test_a_dropped_lines_cascade_linked_row_dispatches_when_retired` drives) - not a
    settle and not a same-line supersede. The retired row must still print as a CANCEL
    BALANCE line: `qty` "0", `was.qty` the old qty, remark "CANCEL BALANCE <old> NOS".

    The PLAN's revised rule (16 Sep, after AC-H19 was added) is that a retire prints
    ALWAYS, with no pairing to whatever else the same commit raises - a cross-reference
    "does this retired row have an exact replacement" would need every raise in the
    commit indexed by line, which the coder found impractical. So the second half here
    is a genuinely UNRELATED line raised in the very same write (not a replacement FOR
    the retired line): both must appear as their own, separate `lines` entries.
    """
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)

    fixture = _raise_two_rows(api, first_qty="10", second_qty="6")
    world.db.commit()
    calls.clear()

    db = world.db
    supply = ProjectSupplyService(db)

    # A second, unrelated order, raised in the SAME write as the retire below.
    core_so_fresh = _core_so(db, world.company_id)
    fresh_core_line = _core_line(
        db, core_so_fresh, world.product, world.warehouse, qty_ordered="4", required_date=WAS
    )
    fresh_order = _project_so(
        db, world.project, so_id=core_so_fresh.id, autocount_doc_no=core_so_fresh.so_number
    )
    fresh_line = _project_line(
        db, fresh_order, line_no=1, product=world.product, core_line=fresh_core_line
    )
    db.flush()

    supply.uncover_lines(
        fixture["order"],
        [str(fixture["first"]["line"].id)],
        actor_user_id=world.cs_user,
        reason="CS took the line back.",
    )
    supply.confirm(
        fresh_order,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(fresh_line.id), buy_qty="4")]),
        actor_user_id=world.cs_user,
    )
    db.commit()

    world.db.refresh(fixture["first"]["row"])
    assert fixture["first"]["row"].state == INQUIRY_CANCELLED, (
        "the retire has to have actually cancelled the row for this test to mean anything"
    )

    matches = _handover_calls(calls)
    assert matches, "the retire must dispatch the handover"
    lines = matches[-1]["context"]["handover"]["lines"]

    cancelled = [l for l in lines if l["remark"] == "CANCEL BALANCE 10 NOS"]
    assert cancelled, f"no cancelled line for the retired row in {lines}"
    assert cancelled[0]["qty"] == "0"
    assert cancelled[0]["was"] == {"qty": "10"}

    fresh = [l for l in lines if l["so_number"] == core_so_fresh.so_number]
    assert fresh, "an unrelated raise in the same commit must print beside the retire, unpaired"
    assert fresh[0]["remark"] == "ORDER"


# --------------------------------------------------------------------------- #
# AC-H20: an unchanged carry is silent; a changed carry prints once as settled #
# --------------------------------------------------------------------------- #


def test_unchanged_carried_row_is_not_printed(api, monkeypatch):
    """AC-H20.

    H19's own captured output shows the gap this pins: the carried line's row goes
    through the SAME cancel-and-re-raise site as any other raise
    (`refresh_for_decision`'s `raised_row = OrderInquiryRow(...)` /
    `self._record_handover(raised_row, kind="raised", ...)`, called UNCONDITIONALLY) -
    so an UNCHANGED carry (line 2, same qty/date it already had, only line 1 was
    uncovered) currently prints as a fresh "ORDER" line with no `was`. Nothing changed
    for purchasing, so it must print NOTHING. A carry the active decision's own frozen
    snapshot genuinely restates at a DIFFERENT qty is the opposite case: it DID change,
    so it must print exactly once, but as a SETTLED line (`was.qty` set), never as a
    second bare ORDER.
    """
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)

    # -- unchanged carry: line 1 dropped, line 2 carried at the SAME qty/date. --
    fixture = _raise_two_rows(api, first_qty="10", second_qty="6")
    world.db.commit()
    calls.clear()

    supply = ProjectSupplyService(world.db)
    supply.uncover_lines(
        fixture["order"],
        [str(fixture["first"]["line"].id)],
        actor_user_id=world.cs_user,
        reason="CS took the line back.",
    )
    world.db.commit()

    matches = _handover_calls(calls)
    assert matches, "the retire must still dispatch the handover"
    lines = matches[-1]["context"]["handover"]["lines"]
    unchanged_carry = [l for l in lines if l["qty"] == "6"]
    assert unchanged_carry == [], (
        f"an unchanged carry must print nothing for purchasing, found {lines}"
    )

    # -- a variant: the carry's qty DID change - the row's live qty has drifted from
    # what the active decision's own frozen snapshot carries forward for it (the same
    # kind of drift an earlier settle-in-place could leave behind). It must print
    # exactly once, as a settled line carrying `was.qty`, never as a second bare ORDER.
    fixture2 = _raise_two_rows(api, first_qty="10", second_qty="6")
    world.db.commit()
    second_row = fixture2["second"]["row"]
    second_row.qty = Decimal("9")
    world.db.flush()
    world.db.commit()
    calls.clear()

    ProjectSupplyService(world.db).uncover_lines(
        fixture2["order"],
        [str(fixture2["first"]["line"].id)],
        actor_user_id=world.cs_user,
        reason="CS took the line back.",
    )
    world.db.commit()

    matches2 = _handover_calls(calls)
    assert matches2, "the retire must dispatch the handover"
    lines2 = matches2[-1]["context"]["handover"]["lines"]
    changed_carry = [l for l in lines2 if l["was"] == {"qty": "9"}]
    assert len(changed_carry) == 1, (
        f"a carry that actually changed qty must print exactly once with was.qty, got {lines2}"
    )
    assert changed_carry[0]["qty"] == "6"


# --------------------------------------------------------------------------- #
# AC-H8: purchasing's own actions never dispatch                              #
# --------------------------------------------------------------------------- #


def test_purchasing_actions_do_not_dispatch(api, monkeypatch):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)

    # acknowledge
    ack_fixture = _raise_one_row(api, qty="10")
    world.db.commit()
    calls.clear()
    with _as_purchasing(world) as buyer:
        resp = buyer.post(ACK_URL, json={"row_ids": [str(ack_fixture["row"].id)]})
        assert resp.status_code == 200, resp.text
    world.db.commit()
    assert _handover_calls(calls) == [], "acknowledge must not dispatch the handover"

    # reject
    reject_fixture = _raise_one_row(api, qty="10")
    world.db.commit()
    calls.clear()
    with _as_purchasing(world) as buyer:
        resp = buyer.post(
            f"{LIST}/{reject_fixture['row'].id}/reject", json={"reason": "No stock"}
        )
        assert resp.status_code == 200, resp.text
    world.db.commit()
    assert _handover_calls(calls) == [], "reject must not dispatch the handover"

    # link now (drives auto_place_for_products / place_on_po underneath)
    _open_po_line(world, qty=50)
    link_fixture = _raise_one_row(api, qty="10")
    world.db.commit()
    calls.clear()
    with _as_purchasing(world) as buyer:
        resp = buyer.post(LINK_NOW, json={"product_ids": [str(world.product.id)]})
        assert resp.status_code == 200, resp.text
    world.db.commit()
    assert _handover_calls(calls) == [], "link now / place on PO must not dispatch the handover"

    # unplace
    calls.clear()
    ProjectOrderInquiryService(world.db).unplace(
        str(link_fixture["row"].id), actor_user_id=world.buyer
    )
    world.db.commit()
    assert _handover_calls(calls) == [], "unplace must not dispatch the handover"


# --------------------------------------------------------------------------- #
# AC-H9: the sheet importer never dispatches                                  #
# --------------------------------------------------------------------------- #


def test_importer_apply_does_not_dispatch(monkeypatch):
    from .test_project_order_inquiry_import_migration import D_OCT, World, sheet

    _register(None)
    calls = _captured_dispatches(monkeypatch)

    with blank_session() as db:
        company_id = db.execute(
            sa.text("select id from companies where code = 'SRT'")
        ).scalar()
        with company_scope(db, frozenset({company_id})):
            w = World(db, company_id)
            order = w.order()
            w.line(order, qty_ordered="50")
            data = sheet(
                [
                    (
                        order.so_number,
                        w.product.product_code,
                        30,
                        D_OCT,
                        w.warehouse.warehouse_code,
                        "",
                    ),
                ]
            )
            result = w.apply(data)
            assert result["rows_raised"] == 1, result
            db.commit()

    assert _handover_calls(calls) == [], "the sheet importer must never dispatch the handover"


# --------------------------------------------------------------------------- #
# AC-H10: a rollback discards the queued entry                                #
# --------------------------------------------------------------------------- #


def test_rollback_discards_pending(api, monkeypatch):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    fixture = _raise_one_row(api, qty="10")
    calls.clear()

    service = ProjectOrderInquiryService(world.db)
    savepoint = world.db.begin_nested()
    service._record_handover(
        fixture["row"], kind="settled", was={"qty": Decimal("10")}, actor_user_id=world.cs_user
    )
    savepoint.rollback()

    world.db.commit()  # an unrelated commit: nothing rolled back above may still fire

    assert _handover_calls(calls) == [], "a rolled-back record must never be dispatched"


# --------------------------------------------------------------------------- #
# AC-H15: post-commit, on a fresh session, and never raises                   #
# --------------------------------------------------------------------------- #


def test_dispatch_runs_after_commit_not_before(api, monkeypatch):
    """AC-H15, first half.

    The literal "an EmailOutbox row exists after the commit; none before" cannot be
    tested honestly on this harness: the drain's fresh `SessionLocal()` is a genuinely
    separate connection (same reasoning
    `test_order_inquiry_changed_with_links_automation.py` gives for always mocking
    `dispatch_event`), so it can never see the still-uncommitted (savepoint-only) order
    this fixture just raised - letting the real dispatch run would silently produce an
    empty/broken context rather than a genuine email-outbox row. This asserts the
    equivalent, real contract instead: nothing is dispatched while the write is still
    open, and the commit fires it exactly once.
    """
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    db = world.db

    core_so = _core_so(db, world.company_id)
    core_line = _core_line(
        db, core_so, world.product, world.warehouse, qty_ordered="10", required_date=WAS
    )
    order = _project_so(
        db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number
    )
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    ProjectSupplyService(db).confirm(
        order,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(line.id), buy_qty="10")]),
        actor_user_id=world.cs_user,
    )
    assert _handover_calls(calls) == [], "nothing may dispatch before the write commits"

    db.commit()
    assert len(_handover_calls(calls)) == 1, "the commit must fire the dispatch exactly once"


def test_dispatch_failure_is_logged_never_raised(api, monkeypatch):
    """AC-H15, second half: a dispatch that raises must not propagate out of commit()."""
    client, world = api
    _register(world)

    def _boom(self, trigger_type, *, context, source_kind, source_id):
        raise RuntimeError("smtp is down")

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event", _boom
    )

    fixture = _raise_one_row(api, qty="10")  # must not raise despite the dispatch failing
    assert fixture["row"] is not None


# --------------------------------------------------------------------------- #
# AC-H17: context shape and formats                                           #
# --------------------------------------------------------------------------- #


def test_context_shape_and_formats(api, monkeypatch):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    fixture = _raise_one_row(api, qty="10")

    matches = _handover_calls(calls)
    assert matches
    ctx = matches[-1]["context"]
    assert set(ctx.keys()) >= {"handover", "actor", "today"}
    handover = ctx["handover"]
    for key in ("subject_scope", "verbs", "headline", "orders", "lines", "line_count", "link"):
        assert key in handover, key

    assert handover["verbs"] == ["ORDER"]
    assert handover["headline"] == "ORDER"
    assert handover["line_count"] == 1
    line = handover["lines"][0]
    assert line["delivery_date"] == WAS.strftime("%d/%m/%Y")
    assert line["qty"] == "10"
    assert handover["link"] == build_order_inquiry_link(fixture["core_so"].so_number)
    order = handover["orders"][0]
    assert order["so_number"] == fixture["core_so"].so_number


# --------------------------------------------------------------------------- #
# AC-H18: actor resolution and fallback                                       #
# --------------------------------------------------------------------------- #


def test_actor_fallback_to_raised_by(api, monkeypatch):
    client, world = api
    _register(world)
    calls = _captured_dispatches(monkeypatch)
    fixture = _raise_one_row(api, qty="10")

    matches = _handover_calls(calls)
    assert matches
    actor = matches[-1]["context"]["actor"]
    assert actor is not None
    assert actor["email"] == f"{world.cs_user}@zzt.test"
    calls.clear()

    row = fixture["row"]
    inquiry = (
        world.db.query(OrderInquiry).filter(OrderInquiry.id == row.order_inquiry_id).one()
    )
    inquiry.raised_by = world.buyer
    world.db.flush()

    service = ProjectOrderInquiryService(world.db)
    service._record_handover(
        row, kind="settled", was={"qty": Decimal("10")}, actor_user_id=None
    )
    world.db.commit()

    fallback = _handover_calls(calls)
    assert fallback
    actor = fallback[-1]["context"]["actor"]
    assert actor is not None
    assert actor["email"] == f"{world.buyer}@zzt.test"
    calls.clear()

    inquiry.raised_by = None
    world.db.flush()
    service._record_handover(
        row, kind="settled", was={"qty": Decimal("10")}, actor_user_id=None
    )
    world.db.commit()

    neither = _handover_calls(calls)
    assert neither
    assert neither[-1]["context"]["actor"] is None


# --------------------------------------------------------------------------- #
# AC-H11: recipients - include_actor                                          #
# --------------------------------------------------------------------------- #


def test_include_actor_adds_actor_email():
    from app.services import automation_recipients

    with blank_session() as db:
        included = automation_recipients.resolve_recipients(
            db,
            {"user_ids": [], "role_ids": [], "extra_emails": [], "include_actor": True},
            promotion_context={"actor": {"email": "raiser@example.test", "name": "Raiser"}},
        )
        assert [r["email"] for r in included].count("raiser@example.test") == 1

        excluded = automation_recipients.resolve_recipients(
            db,
            {"user_ids": [], "role_ids": [], "extra_emails": [], "include_actor": False},
            promotion_context={"actor": {"email": "raiser@example.test", "name": "Raiser"}},
        )
        assert "raiser@example.test" not in [r["email"] for r in excluded]

        no_actor = automation_recipients.resolve_recipients(
            db,
            {"user_ids": [], "role_ids": [], "extra_emails": [], "include_actor": True},
            promotion_context=None,
        )
        assert no_actor == []

        deduped = automation_recipients.resolve_recipients(
            db,
            {
                "user_ids": [],
                "role_ids": [],
                "extra_emails": ["raiser@example.test"],
                "include_actor": True,
            },
            promotion_context={"actor": {"email": "raiser@example.test", "name": "Raiser"}},
        )
        assert [r["email"] for r in deduped].count("raiser@example.test") == 1


def test_normalize_recipient_config_keeps_include_actor_as_bool():
    from app.services.automation_service import AutomationService

    normalized = AutomationService._normalize_recipient_config({"include_actor": True})
    assert normalized["include_actor"] is True

    normalized_false = AutomationService._normalize_recipient_config({"include_actor": False})
    assert normalized_false["include_actor"] is False


# --------------------------------------------------------------------------- #
# AC-H13/AC-H14: seed migration + template                                    #
# --------------------------------------------------------------------------- #


def _find_seed_migration_path() -> Path | None:
    """Locate the coder's seed migration by its data contract - the revision id is not
    fixed at brief time (PLAN section 3.6). `None` until the migration exists."""
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    for path in versions_dir.glob("*.py"):
        try:
            text = path.read_text()
        except OSError:
            continue
        if "order_inquiry_handover_default" in text and "order_inquiry_handover" in text:
            return path
    return None


def _load_seed_migration():
    path = _find_seed_migration_path()
    assert path is not None, (
        "no alembic migration seeding email_templates.code="
        "'order_inquiry_handover_default' / automations.trigger_type="
        "'order_inquiry_handover' was found under alembic/versions/ - the coder must "
        "add it (PLAN-scm-oi-handover-email.md section 3.6, AC-H13). Fill in this "
        "helper's discovery (or hardcode the revision id) once that file exists if a "
        "faster lookup is wanted."
    )
    spec = importlib.util.spec_from_file_location("zzt_oihe_seed_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(module, db) -> None:
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()


def _run_downgrade(module, db) -> None:
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.downgrade()


def test_seed_migration_idempotent():
    module = _load_seed_migration()
    with blank_session() as db:
        _run_upgrade(module, db)
        _run_upgrade(module, db)  # idempotent re-run: no duplicates

        templates = db.execute(
            sa.text(
                "SELECT count(*) FROM email_templates WHERE code = "
                "'order_inquiry_handover_default'"
            )
        ).scalar()
        assert templates == 1

        rows = db.execute(
            sa.text(
                "SELECT enabled, group_matches, recipient_config FROM automations "
                "WHERE trigger_type = 'order_inquiry_handover' "
                "AND name = 'Order inquiry to purchasing'"
            )
        ).fetchall()
        assert len(rows) == 1
        enabled, group_matches, recipient_config = rows[0]
        assert enabled is True
        assert group_matches is False
        cfg = (
            recipient_config
            if isinstance(recipient_config, dict)
            else json.loads(recipient_config)
        )
        assert cfg.get("include_actor") is True
        assert cfg.get("user_ids") == []
        assert cfg.get("extra_emails") == []
        assert cfg.get("role_ids") == [], (
            "no purchasing role exists in this blank schema, so role_ids must seed empty"
        )


def test_seed_migration_downgrade_removes_both():
    module = _load_seed_migration()
    with blank_session() as db:
        _run_upgrade(module, db)
        _run_downgrade(module, db)

        templates = db.execute(
            sa.text(
                "SELECT count(*) FROM email_templates WHERE code = "
                "'order_inquiry_handover_default'"
            )
        ).scalar()
        assert templates == 0
        automations = db.execute(
            sa.text(
                "SELECT count(*) FROM automations WHERE trigger_type = "
                "'order_inquiry_handover'"
            )
        ).scalar()
        assert automations == 0


def test_template_renders_strike_and_text_was():
    from app.models.email_template import EmailTemplate
    from app.services.email_template_service import EmailTemplateService

    module = _load_seed_migration()
    with blank_session() as db:
        _run_upgrade(module, db)
        template = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.code == "order_inquiry_handover_default")
            .one()
        )

        context = {
            "handover": {
                "subject_scope": "BRW-BB @ SO397450",
                "verbs": ["ADVANCE"],
                "headline": "ADVANCE",
                "orders": [
                    {"so_number": "SO397450", "customer": "BUIMACO", "project": "TUJU RESIDENCE"}
                ],
                "lines": [
                    {
                        "so_date": "02/04/2026",
                        "so_number": "SO397450",
                        "customer": "BUIMACO",
                        "project": "TUJU RESIDENCE",
                        "item_code": "CB6633",
                        "qty": "540",
                        "delivery_date": "21/07/2026",
                        "remark": "ADVANCE",
                        "was": {"delivery_date": "03/08/2026"},
                    }
                ],
                "line_count": 1,
                "link": "https://crm.test/project-sales/order-inquiries?query=SO397450",
            },
            "actor": {"name": "Maryam Ariffin", "email": "project.sadmin03@sorento.com.my"},
            "today": "2026-09-16",
        }

        rendered = EmailTemplateService(db).render(template, context)

        assert rendered["subject"] == "OI: BRW-BB @ SO397450"
        html = rendered["body_html"]
        assert "<s>03/08/2026</s>" in html
        for header in ("S/O NO", "CUSTOMER", "PROJECT"):
            assert header in html
        for header in ("SO DATE", "ITEM CODE", "QTY", "DELIVERY DATE", "REMARK"):
            assert header in html
        assert context["handover"]["link"] in html
        assert "21/07/2026 (was 03/08/2026)" in rendered["body_text"]
