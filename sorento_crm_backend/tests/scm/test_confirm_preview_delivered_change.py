"""CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): popup = email = Excel for a line delivered in
full that a PENDING AutoCount change names.

Shape of the owner's order: every line delivered in full; AutoCount moves one line's date
28/09 -> 02/11. The purchasing email takes Was -> Now off the change row (28/09 -> 02/11), so
the Review split (the line-split read) must print the same: DELIVERY DATE 28/09, NEW DATE
02/11 and the change word, never a blank NEW DATE.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.scm.outstanding_diff import DATE_MOVED
from tests.scm.test_line_splits_api import _get, _line, _mirror
from tests.test_planning_change_apply_on_board import _build, _change, _confirm, api, world  # noqa: F401
from tests.test_planning_changes import _core_so, _line_payload, _project_so

WAS = date(2026, 9, 28)
NOW = date(2026, 11, 2)


class _S:
    pass


def _seed(api, *, pending: bool):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    # Line 10: 3 ordered on 28/09, confirmed as Buy 3, then delivered in full.
    s.c10, s.l10 = _mirror(db, order, core_so, world.product, world.own_wh,
                           line_no=10, qty=3, when=WAS)
    # Line 20: delivered in full, nothing pending.
    s.c20, s.l20 = _mirror(db, order, core_so, world.product, world.own_wh,
                           line_no=20, qty=5, when=WAS)
    s.c20.qty_delivered = Decimal("5")
    db.commit()
    resp = _confirm(client, order.id, [_line_payload(s.l10.id, buy_qty="3")])
    assert resp.status_code == 200, resp.text
    s.c10.qty_delivered = Decimal("3")
    db.commit()
    if pending:
        # AutoCount moves line 10 to 02/11 (the book re-upload already wrote the new date).
        s.c10.required_date = NOW
        s.l10.delivery_date = NOW
        db.commit()
        s.batch = _build(world, [
            _change(DATE_MOVED, s.c10, so_number=core_so.so_number,
                    old_date=WAS, new_date=NOW, old_qty="3", new_qty="3"),
        ], core_so, [str(s.c10.id)])
        assert s.batch is not None, "premise: the pending change row exists"
    return s


def test_a_delivered_line_named_by_a_pending_date_change_shows_the_email_was_now(api):
    s = _seed(api, pending=True)
    l10 = _line(_get(s), s.l10.id)
    assert l10["pending_change"] is True
    assert l10["base_date"] == "2026-09-28", "DELIVERY DATE is the date before the change"
    assert l10["new_date"] == "2026-11-02", "NEW DATE is the change's Now, as the email prints"
    assert l10["new_qty"] is None, "the qty did not move"
    assert "DELAY" in (l10["remark_generated"] or ""), l10["remark_generated"]


def test_a_delivered_line_with_no_pending_change_still_has_no_new_cells(api):
    s = _seed(api, pending=True)
    l20 = _line(_get(s), s.l20.id)
    assert l20["delivered_in_full"] is True
    assert l20["pending_change"] is False
    assert (l20["new_qty"], l20["new_date"]) == (None, None)


def test_a_delivered_line_named_by_a_pending_change_is_still_listed_read_only(api):
    """No split on a delivered line: the read still marks it delivered in full (the sheet's
    lock), it only stops hiding the change."""
    s = _seed(api, pending=True)
    l10 = _line(_get(s), s.l10.id)
    assert l10["delivered_in_full"] is True
    assert l10["splits"] == []


def test_a_delivered_line_autocount_closed_reads_its_change_word_not_cancel_all(api):
    """Crew browser pass (2 Nov): on the copy every delivered-in-full line's AutoCount line is
    CLOSED (closed by the delivery, not cancelled). Its words are the change's (DELAY), never
    the cancelled-line words CANCEL ALL."""
    s = _seed(api, pending=True)
    s.c10.line_status = "closed"
    s.db.commit()
    l10 = _line(_get(s), s.l10.id)
    assert l10["new_date"] == "2026-11-02"
    assert "CANCEL" not in (l10["remark_generated"] or ""), l10["remark_generated"]
    assert "DELAY" in (l10["remark_generated"] or ""), l10["remark_generated"]


def test_a_delivered_line_s_saved_buy_on_a_plain_confirm_reaches_purchasing(api):
    """Item 4 (crew, 2 Nov): plain Confirm (nothing pending) on a line delivered in full. The
    board plans a line at its ordered qty (`plan_qty_of`, owner ruling 14 Sep: "a delivered
    line ... a Buy raises the order-back inquiry"), so Confirm does NOT skip it: the #1362 skip
    is only for a line whose PLAN qty is 0 (cancelled, returned, qty_required 0). Pins the
    premise the sheet's words rest on: something does go to purchasing."""
    from app.models.project_so import OrderInquiryRow

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    core, line = _mirror(db, order, core_so, world.product, world.own_wh, line_no=30, qty=3, when=WAS)
    core.qty_delivered = Decimal("3")
    db.commit()
    resp = _confirm(client, order.id, [_line_payload(line.id, buy_qty="3")])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("lines_fulfilled_skipped", 0) == 0, body
    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state != "cancelled")
        .all()
    )
    assert sum((Decimal(str(r.qty)) for r in rows), Decimal("0")) == Decimal("3"), [
        (r.verb, r.qty, r.state) for r in rows
    ]


def test_a_delivered_line_s_saved_borrow_on_a_plain_confirm_raises_its_order_back(api):
    """Item 4, the Borrow half (review): a delivered line that borrowed 3 from its own bin
    tells purchasing its order back on a plain Confirm ("Borrow from another order" OFF, the
    default: `_location_order_backs` owes a borrow back on the borrowing line, own location
    included)."""
    from app.models.project_so import OrderInquiryRow
    from tests.test_so_supply_confirmation import _stock

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    core, line = _mirror(db, order, core_so, world.product, world.own_wh, line_no=40, qty=3, when=WAS)
    core.qty_delivered = Decimal("3")
    _stock(db, world.product, world.own_wh, on_hand=10)
    db.commit()
    resp = _confirm(client, order.id, [_line_payload(line.id, borrow=[{
        "source": "other_location",
        "warehouse_id": str(world.own_wh.id),
        "qty": "3",
        "reason": "Borrowed from its own bin.",
    }])])
    assert resp.status_code == 200, resp.text
    assert resp.json().get("lines_fulfilled_skipped", 0) == 0, resp.json()
    backs = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.verb == "ORDER_BACK",
            OrderInquiryRow.state != "cancelled",
        )
        .all()
    )
    assert [Decimal(str(r.qty)) for r in backs] == [Decimal("3")], [
        (r.verb, r.qty, r.state, r.note) for r in backs
    ]

# --------------------------------------------------------------------------------------------
# Round 3 (crew final pass, 2 Nov): popup REMARK = email REMARK, one source. The guided
# Confirm's dry run (`confirm-all` with `preview: true`) answers, per order, the purchasing
# email's own lines (`email_lines`), built by the same queue and context builder the real press
# sends; the popup prints those words.

CONFIRM_ALL = "/api/v1/project-sales/fulfilment-planning/confirm-all"


def _fresh_request(s):
    """Each request gets its own session in production; the test client shares the world's,
    so what the seeding queued for its own (already committed) writes is cleared first."""
    from app.services import project_order_inquiry_service as oi

    for key in (oi._HANDOVER_PENDING_KEY, oi._SAVED_TOLD_KEY):
        s.db.info.pop(key, None)


def _press(s, line_payload, *, preview):
    _fresh_request(s)
    return s.client.post(
        CONFIRM_ALL,
        json={
            "preview": preview,
            "orders": [
                {"pso_id": str(s.order.id), "lines": [line_payload], "batch_id": str(s.batch.id)}
            ],
        },
    )


def _email_remarks(answer, line_id):
    order = answer["results"][0]
    assert order["ok"], order
    return [entry["remark"] for entry in order.get("email_lines") or [] if entry["so_line_id"] == str(line_id)]


def _sent_remarks(calls, item_code):
    from tests.test_order_inquiry_handover_automation import _handover_calls

    return [
        line["remark"]
        for call in _handover_calls(calls)
        for line in call["context"]["handover"]["lines"]
        if line["item_code"] == item_code
    ]


def _same_as_email(api, monkeypatch, line_payload):
    from tests.test_order_inquiry_handover_automation import _captured_dispatches, _register

    s = _seed(api, pending=True)
    _register(s.world)
    calls = _captured_dispatches(monkeypatch)
    preview = _press(s, line_payload(s), preview=True)
    assert preview.status_code == 200, preview.text
    popup = _email_remarks(preview.json(), s.l10.id)
    calls.clear()
    real = _press(s, line_payload(s), preview=False)
    assert real.status_code == 200, real.text
    item_code = s.world.product.product_code
    return popup, _sent_remarks(calls, item_code)


def test_the_dry_run_answers_the_email_remark_for_a_held_buy_with_a_date_move(api, monkeypatch):
    """Crew case 1: Buy saved again as held, AutoCount moved the date: the email says DELAY,
    and so must the popup (it said ORDER)."""
    popup, sent = _same_as_email(api, monkeypatch, lambda s: _line_payload(s.l10.id, buy_qty="3"))
    assert sent, "premise: the real press tells purchasing about the line"
    assert popup == sent, (popup, sent)
    assert any("DELAY" in remark for remark in popup), popup


def test_the_dry_run_answers_the_email_remark_for_a_changed_decision_with_a_date_move(
    api, monkeypatch
):
    """Crew case 2: Reserve + Buy over a held Buy, with a date move: the email says
    "DELAY, CHANGED: ...", and so must the popup (it dropped "DELAY, ")."""
    from tests.test_so_supply_confirmation import _stock

    seeded = set()

    def payload(s):
        if not seeded:
            _stock(s.db, s.world.product, s.world.own_wh, on_hand=5)
            s.db.commit()
            seeded.add(True)
        return _line_payload(
            s.l10.id,
            reserve=[{"warehouse_id": str(s.world.own_wh.id), "qty": "1"}],
            buy_qty="2",
            amend_reason="Part from the bin.",
        )

    popup, sent = _same_as_email(api, monkeypatch, payload)
    assert sent, "premise: the real press tells purchasing about the line"
    assert popup == sent, (popup, sent)


def test_the_dry_run_names_each_told_line_by_its_own_email_row(api, monkeypatch):
    """Review round 3 (S4): two told lines on one order, one moved later (DELAY), one earlier
    (ADVANCE). Each line's `email_lines` entry carries ITS row of the email, in the email's own
    order, and the whole list equals what the real press sends (the same builder, the zip)."""
    from tests.test_order_inquiry_handover_automation import _captured_dispatches, _register

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    early, late = date(2026, 10, 1), date(2026, 12, 1)
    ca, la = _mirror(db, order, core_so, world.product, world.own_wh, line_no=10, qty=3, when=early)
    cb, lb = _mirror(db, order, core_so, world.product, world.own_wh, line_no=20, qty=4, when=late)
    db.commit()
    resp = _confirm(client, order.id, [
        _line_payload(la.id, buy_qty="3"), _line_payload(lb.id, buy_qty="4"),
    ])
    assert resp.status_code == 200, resp.text
    ca.required_date, la.delivery_date = late, late
    cb.required_date, lb.delivery_date = early, early
    db.commit()
    batch = _build(world, [
        _change(DATE_MOVED, ca, so_number=core_so.so_number,
                old_date=early, new_date=late, old_qty="3", new_qty="3"),
        _change(DATE_MOVED, cb, so_number=core_so.so_number,
                old_date=late, new_date=early, old_qty="4", new_qty="4"),
    ], core_so, [str(ca.id), str(cb.id)])
    assert batch is not None
    s = _S()
    s.client, s.world, s.db, s.order, s.batch = client, world, db, order, batch
    _register(world)
    calls = _captured_dispatches(monkeypatch)

    def press(preview):
        _fresh_request(s)
        return client.post(CONFIRM_ALL, json={"preview": preview, "orders": [{
            "pso_id": str(order.id), "batch_id": str(batch.id),
            "lines": [_line_payload(la.id, buy_qty="3"), _line_payload(lb.id, buy_qty="4")],
        }]})

    preview = press(True)
    assert preview.status_code == 200, preview.text
    lines = preview.json()["results"][0]["email_lines"]
    by_line = {entry["so_line_id"]: entry["remark"] for entry in lines}
    assert "DELAY" in by_line.get(str(la.id), ""), lines
    assert "ADVANCE" in by_line.get(str(lb.id), ""), lines
    calls.clear()
    assert press(False).status_code == 200
    item_code = world.product.product_code
    assert [entry["remark"] for entry in lines] == _sent_remarks(calls, item_code)
