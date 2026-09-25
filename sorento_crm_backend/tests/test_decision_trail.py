"""The decision trail behind ONE core sales-order line (`PLAN-oi-decision-trail-ui.md`,
round 2, AC-DT-10) - the History icon's own read, mirroring `test_order_inquiry_raise_
event.py` (the matcher this reuses) and `test_board_decision_trail.py` (the confirmed/
saved facts this reads the same way).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models.order import SalesOrderLine as CoreSalesOrderLine
from app.models.project_so import (
    DECISION_ACTIVE,
    DECISION_SUPERSEDED,
    OI_RAISE_RAISED,
    OI_RAISE_RECONFIRMED,
    ProjectSalesOrderLine,
    SOSupplyDecision,
    SOSupplyDecisionDraft,
)

from ._pg_fixture import blank_session
from .test_order_inquiry_raise_event import _raise
from .test_order_inquiry_worklist_raised_by import (
    MARKER,
    READ_ONLY,
    _adopted_order,
    _client,
    _inquiry,
    _product,
    _restore,
    _row,
    _sorento,
    _uid,
    _user,
)

BASE = "/api/v1/project-sales"


def _trail_url(core_line_id: str) -> str:
    return f"{BASE}/sales-order-lines/{core_line_id}/decision-trail"


def _core_line(db, sales_order_id: str, product_id: str, *, qty: str = "10") -> CoreSalesOrderLine:
    row = CoreSalesOrderLine(
        id=_uid(),
        sales_order_id=sales_order_id,
        product_id=product_id,
        qty_ordered=Decimal(qty),
        qty_delivered=Decimal("0"),
        required_date=date(2026, 9, 3),
    )
    db.add(row)
    db.flush()
    return row


def _mirror_line(
    db, company_id: str, project_order, core_line: CoreSalesOrderLine, *, line_no: int = 1
) -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=project_order.id,
        core_sales_order_line_id=core_line.id,
        line_no=line_no,
        product_id=core_line.product_id,
        description=f"{MARKER} decision-trail line",
        qty=core_line.qty_ordered,
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal("0"),
        delivery_date=core_line.required_date,
    )
    db.add(row)
    db.flush()
    return row


def _decision(
    db,
    company_id: str,
    project_order,
    *,
    revision_no: int,
    confirmed_by: str,
    confirmed_at: datetime,
    core_line_id: str,
    project_line_id: str,
    components: list,
    supersedes: SOSupplyDecision | None = None,
) -> SOSupplyDecision:
    if supersedes is not None:
        supersedes.state = DECISION_SUPERSEDED
        supersedes.superseded_at = confirmed_at
        db.flush()
    decision = SOSupplyDecision(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=project_order.id,
        revision_no=revision_no,
        state=DECISION_ACTIVE,
        line_snapshots=[
            {
                "project_line_id": project_line_id,
                "core_line_id": core_line_id,
                "components": components,
            }
        ],
        confirmed_by=confirmed_by,
        confirmed_at=confirmed_at,
    )
    db.add(decision)
    db.flush()
    return decision


def _draft(
    db,
    company_id: str,
    project_order,
    core_line: CoreSalesOrderLine,
    *,
    saved_by: str,
    saved_at: datetime,
    decision: dict,
) -> SOSupplyDecisionDraft:
    row = SOSupplyDecisionDraft(
        id=_uid(),
        company_id=company_id,
        sales_order_id=project_order.so_id,
        core_line_id=core_line.id,
        line_no=1,
        item_code=f"{MARKER}-DRAFT",
        bucket_key="2026-09-03",
        decision=decision,
        saved_by=saved_by,
        saved_at=saved_at,
    )
    db.add(row)
    db.flush()
    return row


def test_confirmed_revisions_a_draft_and_raise_events_all_list_newest_first():
    with blank_session() as db:
        company_id = _sorento(db)
        alice = _user(db, f"{MARKER} Alice", f"alice.{_uid()[:8]}@zzt.test")
        bob = _user(db, f"{MARKER} Bob", f"bob.{_uid()[:8]}@zzt.test")
        carol = _user(db, f"{MARKER} Carol", f"carol.{_uid()[:8]}@zzt.test")
        dara = _user(db, f"{MARKER} Dara", f"dara.{_uid()[:8]}@zzt.test")

        project_order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
        product = _product(db, f"ZZT-{_uid()[:6]}")
        core_line = _core_line(db, project_order.so_id, product.id)
        mirror = _mirror_line(db, company_id, project_order, core_line)

        rev1_at = datetime(2026, 9, 20, 1, 0)
        rev1 = _decision(
            db, company_id, project_order,
            revision_no=1, confirmed_by=alice.id, confirmed_at=rev1_at,
            core_line_id=core_line.id, project_line_id=mirror.id,
            components=[{"kind": "buy", "qty": "5"}],
        )
        rev2_at = datetime(2026, 9, 25, 1, 20, 34)
        _decision(
            db, company_id, project_order,
            revision_no=2, confirmed_by=bob.id, confirmed_at=rev2_at,
            core_line_id=core_line.id, project_line_id=mirror.id,
            components=[{"kind": "reserve", "qty": "8"}, {"kind": "buy", "qty": "2"}],
            supersedes=rev1,
        )

        saved_at = datetime(2026, 9, 25, 3, 0)
        _draft(
            db, company_id, project_order, core_line,
            saved_by=carol.id, saved_at=saved_at,
            decision={"verdict": "amended", "buy_qty": "3"},
        )

        # Row 1: a sheet-migrated row - reads `sheet`, no name or date, even though its
        # inquiry also carries an unrelated `raised` event (B1, round 1: sheet outranks
        # the event).
        header = _inquiry(
            db, company_id, project_order, raised_by=alice.id,
            raised_at=datetime(2026, 9, 1, 0, 0),
        )
        _raise(
            db, company_id, header,
            kind=OI_RAISE_RAISED, raised_by=alice.id,
            raised_at=datetime(2026, 9, 1, 0, 0),
        )
        sheet_row = _row(db, company_id, header, mirror, f"{MARKER}-SHEET")
        sheet_row.note = "Migrated from order inquiry sheet, row 12"
        sheet_row.created_at = datetime(2026, 9, 1, 0, 0)

        # Row 2, on the SAME core line: an ordinary raised row whose reconfirm event
        # lands 1.3s after it (the measured prod gap).
        row2_created_at = datetime(2026, 9, 25, 1, 20, 33, 559000)
        reconfirm_at = row2_created_at + timedelta(seconds=1, microseconds=300000)
        _raise(
            db, company_id, header,
            kind=OI_RAISE_RECONFIRMED, raised_by=dara.id,
            raised_at=reconfirm_at,
        )
        row2 = _row(db, company_id, header, mirror, f"{MARKER}-ROW2")
        row2.created_at = row2_created_at

        # B1 (review round 3): the planning_change branch had no coverage of its own - a
        # note that IS the exact stamp `planning_change_service.py` writes fires its own
        # entry, independent of any raise event; an ordinary raise/reconfirm note that
        # merely STARTS WITH "Was" must not (reviewer S2, round 1 - the same distinction
        # `orderInquiryWorklist.ts`'s `PLANNING_CHANGE_NOTE` draws).
        planning_change_row = _row(db, company_id, header, mirror, f"{MARKER}-PLANCHANGE")
        planning_change_row.note = "Was 2026-09-01"
        planning_change_row.created_at = datetime(2026, 7, 1, 0, 0)

        ordinary_was_row = _row(db, company_id, header, mirror, f"{MARKER}-ORDINARYWAS")
        ordinary_was_row.note = "Was 5 on 2026-09-01"
        ordinary_was_row.created_at = datetime(2026, 6, 1, 0, 0)
        db.commit()

        client, originals = _client(db, alice.id, READ_ONLY)
        try:
            response = client.get(_trail_url(core_line.id))
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        body = response.json()
        entries = body["entries"]
        # response_model keeps all four keys, on the ACTUAL response - a dropped field
        # here is invisible to a service-level assertion.
        for entry in entries:
            assert set(entry.keys()) == {"kind", "actor_name", "at", "detail"}

        by_kind_detail = {(e["kind"], e["detail"]): e for e in entries}

        rev1_entry = next(e for e in entries if e["detail"].startswith("Revision 1"))
        assert rev1_entry["kind"] == "confirmed"
        assert rev1_entry["actor_name"] == alice.name
        assert rev1_entry["at"] is not None
        assert "Buy 5" in rev1_entry["detail"]

        rev2_entry = next(e for e in entries if e["detail"].startswith("Revision 2"))
        assert rev2_entry["kind"] == "confirmed"
        assert rev2_entry["actor_name"] == bob.name
        assert "Reserve 8" in rev2_entry["detail"]
        assert "Buy 2" in rev2_entry["detail"]

        saved_entries = [e for e in entries if e["kind"] == "saved"]
        assert len(saved_entries) == 1
        assert saved_entries[0]["actor_name"] == carol.name
        assert saved_entries[0]["detail"].startswith("Amended")

        # Round 3 (owner ruling 25 Sep 2026): a sheet entry now carries the row's own
        # `created_at` as `at` - the row IS a real fact with a real time, only the
        # uploader is unknown - so it sorts among the other entries instead of always
        # trailing behind the fallback `datetime.min`. `actor_name` still stays `None`:
        # the sheet import records no uploader.
        sheet_entries = [e for e in entries if e["kind"] == "sheet"]
        assert len(sheet_entries) == 1
        assert sheet_entries[0]["actor_name"] is None
        assert datetime.fromisoformat(sheet_entries[0]["at"]) == sheet_row.created_at
        assert header.inquiry_no in sheet_entries[0]["detail"]

        reconfirmed_entries = [e for e in entries if e["kind"] == "reconfirmed"]
        assert len(reconfirmed_entries) == 1
        assert reconfirmed_entries[0]["actor_name"] == dara.name
        assert header.inquiry_no in reconfirmed_entries[0]["detail"]

        # B1: exactly one planning_change entry, off the exact stamp, at the ROW's own
        # created_at (not the header's, not `None`) - and no such entry for the ordinary
        # "Was 5 on 2026-09-01" raise note, which merely starts the same word.
        planning_change_entries = [e for e in entries if e["kind"] == "planning_change"]
        assert len(planning_change_entries) == 1
        assert planning_change_entries[0]["detail"] == "Was 2026-09-01"
        assert planning_change_entries[0]["actor_name"] is None
        assert datetime.fromisoformat(planning_change_entries[0]["at"]) == (
            planning_change_row.created_at
        )
        assert not any(
            e["detail"] == "Was 5 on 2026-09-01" for e in planning_change_entries
        )

        # Newest first: every entry that carries a timestamp is sorted descending by it.
        # The `sheet` entry now carries a real time (round 3) and sorts among the rest,
        # older than rev1's 20 Sep confirm but newer than the 1 Jul planning-change row,
        # which is the oldest fact in this trail and sits last.
        timed = [e["at"] for e in entries if e["at"] is not None]
        assert timed == sorted(timed, reverse=True)
        assert entries[-1]["kind"] == "planning_change"
        assert by_kind_detail  # keeps the helper referenced for readability above


def test_a_core_line_with_nothing_returns_an_empty_list():
    with blank_session() as db:
        company_id = _sorento(db)
        actor = _user(db, f"{MARKER} Nobody", f"nobody.{_uid()[:8]}@zzt.test")
        project_order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
        product = _product(db, f"ZZT-{_uid()[:6]}")
        core_line = _core_line(db, project_order.so_id, product.id)
        db.commit()

        client, originals = _client(db, actor.id, READ_ONLY)
        try:
            response = client.get(_trail_url(core_line.id))
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        assert response.json()["entries"] == []


def test_a_sheet_row_also_surfaces_a_later_reconfirm_event():
    """B3 (review round 3, browser pass on SO390524 / OI-2609-0731): a `sheet` row's own
    origin match never touches `order_inquiry_raises` at all, so the inquiry's own LATER
    reconfirm (the exact fact the dispute needed) never appeared anywhere in the trail.
    An event strictly inside the row's own window must still never be duplicated."""
    with blank_session() as db:
        company_id = _sorento(db)
        nurain = _user(db, f"{MARKER} Nurain", f"nurain.{_uid()[:8]}@zzt.test")
        project_order = _adopted_order(db, company_id, f"ZZTSO{_uid()[:8]}")
        product = _product(db, f"ZZT-{_uid()[:6]}")
        core_line = _core_line(db, project_order.so_id, product.id)
        mirror = _mirror_line(db, company_id, project_order, core_line)

        row_created_at = datetime(2026, 9, 20, 3, 0)
        header = _inquiry(
            db, company_id, project_order, raised_by=None, raised_at=row_created_at
        )
        sheet_row = _row(db, company_id, header, mirror, f"{MARKER}-SHEET-B3")
        sheet_row.note = "Migrated from order inquiry sheet, row 1"
        sheet_row.created_at = row_created_at

        # Strictly inside the row's own 10-minute window - must never appear at all (a
        # `sheet` row's own origin never consumes an event, and this one is too close to
        # count as "later" either).
        _raise(
            db, company_id, header,
            kind=OI_RAISE_RAISED, raised_by=nurain.id,
            raised_at=row_created_at + timedelta(seconds=2),
        )
        # The fact the dispute needed: a reconfirm hours after the sheet migration.
        later_reconfirm_at = row_created_at + timedelta(hours=8)
        _raise(
            db, company_id, header,
            kind=OI_RAISE_RECONFIRMED, raised_by=nurain.id,
            raised_at=later_reconfirm_at,
        )
        db.commit()

        client, originals = _client(db, nurain.id, READ_ONLY)
        try:
            response = client.get(_trail_url(core_line.id))
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        entries = response.json()["entries"]

        sheet_entries = [e for e in entries if e["kind"] == "sheet"]
        assert len(sheet_entries) == 1

        reconfirmed_entries = [e for e in entries if e["kind"] == "reconfirmed"]
        assert len(reconfirmed_entries) == 1
        assert reconfirmed_entries[0]["actor_name"] == nurain.name
        assert datetime.fromisoformat(reconfirmed_entries[0]["at"]) == later_reconfirm_at
        assert header.inquiry_no in reconfirmed_entries[0]["detail"]

        # The inside-window event never surfaces as anything - not an origin (the sheet
        # note outranks it), not a "later" entry (it is inside the window, not past it).
        assert [e for e in entries if e["kind"] == "raised"] == []


def test_a_line_in_another_company_404s_for_a_user_scoped_to_this_one():
    """S4 (review round 3): the existence check is a plain `SalesOrderLine` query - it
    has to run through the SAME company-scope filter every other owned read does
    (`app.services.company_scope`'s `do_orm_execute` listener), or a line that is real
    but belongs to a DIFFERENT company would 200 instead of 404 for a user who should
    never learn it exists."""
    from app.models.base import company_scope
    from app.models.company import Company

    with blank_session() as db:
        actor = _user(
            db, f"{MARKER} ScopedToSorento", f"scoped.{_uid()[:8]}@zzt.test"
        )

        other = Company(
            id=str(uuid.uuid4()), name=f"{MARKER} Other Co", code=f"ZL{_uid()[:6]}"
        )
        db.add(other)
        db.flush()
        company_b = str(other.id)

        # Built entirely under company B's own scope, so the core line (which has no
        # explicit `company_id` param of its own - `_core_line` relies on the
        # ambient scope's auto-stamp, same as `_product`) lands there rather than in
        # the test suite's own default Sorento scope.
        with company_scope(db, frozenset({company_b})):
            project_order = _adopted_order(db, company_b, f"ZZTSO{_uid()[:8]}")
            product = _product(db, f"ZZT-{_uid()[:6]}")
            core_line = _core_line(db, project_order.so_id, product.id)
        db.commit()

        client, originals = _client(db, actor.id, READ_ONLY)
        try:
            # No `company_scope` wrapper here - the session falls back to the test
            # suite's own default scope (Sorento, `tests/conftest.py`), exactly as a
            # real request for a Sorento-scoped user would.
            response = client.get(_trail_url(core_line.id))
        finally:
            _restore(originals)

        assert response.status_code == 404, response.text


def test_an_unknown_line_id_404s():
    with blank_session() as db:
        actor = _user(db, f"{MARKER} Ghost", f"ghost.{_uid()[:8]}@zzt.test")
        db.commit()

        client, originals = _client(db, actor.id, READ_ONLY)
        try:
            response = client.get(_trail_url(str(uuid.uuid4())))
        finally:
            _restore(originals)

        assert response.status_code == 404, response.text
