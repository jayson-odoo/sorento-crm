"""CONFIRM-REMARK-FIX (follow-up to #2091), `PLAN-confirm-remark-fix-3nov.md`.

F1 (prod bug, SO394876, 3 Nov): the SO Remark typed in the Confirm popup was blank in the
queued purchasing email. A Confirm that answers a planning-change batch tells purchasing
(`planning_change_service._notify_purchasing`), and that notification COMMITTED the request
session mid-write: the root commit drained the handover queue (the email went out) before the
confirm route stamped the planner's SO remark onto it (`stamp_so_remark`). The older SO-remark
tests had no active purchasing user, so the notify step returned early and never committed.
"""
from __future__ import annotations

from tests.scm.test_confirm_preview_delivered_change import _press, _seed
from tests.scm.test_planning_change_apply_notifies_purchasing import (  # noqa: F401
    _notices,
    _seed_user_with_role,
    sent_notices,
)
from tests.test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
)
from tests.test_planning_change_apply_on_board import api, world  # noqa: F401
from tests.test_planning_changes import _line_payload

REMARK = "crew r4 real confirm test"


def _seed_purchasing_user(db):
    """An ACTIVE user on a `purchasing*` role (`_purchasing_user_ids`), the prod shape."""
    import uuid

    return _seed_user_with_role(db, f"purchasing_zzt_{uuid.uuid4().hex[:6]}")


def _press_with_remark(s, *, preview, so_remark=REMARK):
    from tests.scm.test_confirm_preview_delivered_change import _fresh_request

    _fresh_request(s)
    return s.client.post(
        "/api/v1/project-sales/fulfilment-planning/confirm-all",
        json={
            "preview": preview,
            "orders": [
                {
                    "pso_id": str(s.order.id),
                    "lines": [_line_payload(s.l10.id, buy_qty="3")],
                    "batch_id": str(s.batch.id),
                    "so_remark": so_remark,
                }
            ],
        },
    )


def test_f1_the_typed_so_remark_reaches_the_email_when_purchasing_is_notified(
    api, monkeypatch, sent_notices
):
    s = _seed(api, pending=True)
    user = _seed_purchasing_user(s.db)
    s.db.commit()
    _register(s.world)
    calls = _captured_dispatches(monkeypatch)

    real = _press_with_remark(s, preview=False)
    assert real.status_code == 200, real.text
    assert real.json()["results"][0]["ok"], real.text

    handovers = _handover_calls(calls)
    assert handovers, "premise: the real press emails purchasing"
    remarks = [o["remark"] for call in handovers for o in call["context"]["handover"]["orders"]]
    assert remarks == [REMARK], remarks

    # Purchasing is still told the batch was applied (best-effort, after the write lands).
    dedup = f"{s.batch.id}:{s.order.id}:planning_change_applied"
    assert len(_notices(sent_notices, user_id=user.id, dedup_key=dedup)) == 1, sent_notices


# F2: the planner's own line REMARK (`ConfirmLine.remark`, typed in the guide) printed in the
# popup, but a Confirm answering a planning-change batch dropped it on the way through the
# batch row's composition, so the email and its Excel printed the generated words ("DELAY").

OWN = "Planner words"


def _press_line_remark(s, *, preview):
    from tests.scm.test_confirm_preview_delivered_change import _fresh_request

    _fresh_request(s)
    line = _line_payload(s.l10.id, buy_qty="3")
    line["remark"] = OWN
    return s.client.post(
        "/api/v1/project-sales/fulfilment-planning/confirm-all",
        json={
            "preview": preview,
            "orders": [
                {"pso_id": str(s.order.id), "lines": [line], "batch_id": str(s.batch.id)}
            ],
        },
    )


def test_f2_the_planners_line_remark_is_the_email_remark_on_a_planning_change_confirm(
    api, monkeypatch
):
    from tests.scm.test_confirm_preview_delivered_change import _email_remarks, _sent_remarks

    s = _seed(api, pending=True)
    _register(s.world)
    calls = _captured_dispatches(monkeypatch)

    preview = _press_line_remark(s, preview=True)
    assert preview.status_code == 200, preview.text
    popup = _email_remarks(preview.json(), s.l10.id)
    calls.clear()
    real = _press_line_remark(s, preview=False)
    assert real.status_code == 200, real.text
    assert real.json()["results"][0]["ok"], real.text
    sent = _sent_remarks(calls, s.world.product.product_code)

    assert sent == [OWN], sent
    assert popup == sent, (popup, sent)


def test_f2_the_planners_line_remark_is_frozen_with_the_batch_confirm(api):
    from app.services.project_supply_service import ProjectSupplyService

    s = _seed(api, pending=True)
    real = _press_line_remark(s, preview=False)
    assert real.status_code == 200, real.text
    s.db.expire_all()
    supply = ProjectSupplyService(s.db)
    frozen = supply.frozen_lines_of(supply.active_decision(str(s.order.id)))
    assert frozen[str(s.l10.id)].get("remark") == OWN, frozen[str(s.l10.id)]


# Speed: the guide's dry run is bounded the way Simulate is (5 s lock timeout), and a dry run
# that hit it answers in words, not a database error.


def test_the_dry_run_sets_a_five_second_lock_timeout(api):
    import sqlalchemy as sa

    s = _seed(api, pending=True)
    seen: list = []

    def _spy(conn, cursor, statement, *_a):
        if "lock_timeout" in statement:
            seen.append(statement)

    engine = s.db.get_bind()
    sa.event.listen(engine, "before_cursor_execute", _spy)
    try:
        preview = _press_with_remark(s, preview=True)
    finally:
        sa.event.remove(engine, "before_cursor_execute", _spy)
    assert preview.status_code == 200, preview.text
    assert seen == ["SET LOCAL lock_timeout = '5s'"], seen


def test_the_real_press_sets_no_lock_timeout(api):
    import sqlalchemy as sa

    s = _seed(api, pending=True)
    seen: list = []

    def _spy(conn, cursor, statement, *_a):
        if "lock_timeout" in statement:
            seen.append(statement)

    engine = s.db.get_bind()
    sa.event.listen(engine, "before_cursor_execute", _spy)
    try:
        real = _press_with_remark(s, preview=False)
    finally:
        sa.event.remove(engine, "before_cursor_execute", _spy)
    assert real.status_code == 200, real.text
    assert seen == [], seen


def test_a_dry_run_that_waited_out_the_lock_says_so(api, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.services.project_supply_service import (
        PREVIEW_LOCK_BUSY_MESSAGE,
        ProjectSupplyService,
    )

    class _Busy(Exception):
        pgcode = "55P03"

    def _locked(self, *_a, **_k):
        raise OperationalError("SELECT ... FOR UPDATE", {}, _Busy("lock timeout"))

    s = _seed(api, pending=True)
    monkeypatch.setattr(ProjectSupplyService, "get_order", _locked)
    preview = _press_with_remark(s, preview=True)
    assert preview.status_code == 200, preview.text
    result = preview.json()["results"][0]
    assert result["ok"] is False and result["error"] == PREVIEW_LOCK_BUSY_MESSAGE, result


# Review S1: a queued purchasing notice waits for the ROOT commit. `after_commit` also fires on a
# savepoint's own commit (a batch apply gives each order one), and sending then told purchasing
# about a write a later rollback still removed.


def test_a_queued_purchasing_notice_waits_for_the_root_commit(api, sent_notices):
    from app.services.project_order_inquiry_service import queue_purchasing_notification

    _client, world = api
    db = world.db
    item = {
        "user_ids": ["u-1"],
        "title": "Planning change applied - SO1",
        "body": "b",
        "data": {},
        "source_entity_type": "planning_change_batch",
        "source_entity_id": "b-1",
        "dedup_key": "b-1:o-1:planning_change_applied",
    }
    db.connection()  # inside the write's transaction, as an apply always is
    queue_purchasing_notification(db, item)
    db.begin_nested().commit()  # a sibling order's savepoint
    assert sent_notices == [], sent_notices
    db.rollback()
    assert sent_notices == [], sent_notices

    db.connection()
    queue_purchasing_notification(db, item)
    db.begin_nested().commit()
    db.commit()
    assert [n["dedup_key"] for n in sent_notices] == ["b-1:o-1:planning_change_applied"]


def _lock_statements(db, run):
    import sqlalchemy as sa

    seen: list = []

    def _spy(conn, cursor, statement, *_a):
        if "lock_timeout" in statement:
            seen.append(statement)

    engine = db.get_bind()
    sa.event.listen(engine, "before_cursor_execute", _spy)
    try:
        run()
    finally:
        sa.event.remove(engine, "before_cursor_execute", _spy)
    return seen


def _held_back_once(api):
    """A dry run whose write refuses one of two lines once: the hold-back rolls back and
    writes again without it."""
    from app.schemas.project_supply import ConfirmManyOrderBody
    from app.services.project_supply_service import ProjectSupplyService, SupplyLinesRefused

    s = _seed(api, pending=False)
    service = ProjectSupplyService(s.db)
    entry = ConfirmManyOrderBody(
        pso_id=str(s.order.id),
        lines=[_line_payload(s.l10.id, buy_qty="3"), _line_payload(s.l20.id)],
    )
    calls: list = []

    def write(_order, current):
        calls.append(len(current.lines))
        if len(calls) == 1:
            raise SupplyLinesRefused(
                422, "refused", [{"project_line_id": str(s.l20.id), "message": "stale"}]
            )
        return {}

    return s, service, entry, write, calls


def test_a_held_back_dry_run_is_bounded_again_after_its_rollback(api):
    s, service, entry, write, calls = _held_back_once(api)
    s.db.connection()
    seen = _lock_statements(
        s.db,
        lambda: service._write_holding_back(s.order, entry, write, True, preview=True),
    )
    assert calls == [2, 1], calls
    assert seen == ["SET LOCAL lock_timeout = '5s'"], seen


def test_a_held_back_real_write_is_not_bounded(api):
    s, service, entry, write, calls = _held_back_once(api)
    s.db.connection()
    seen = _lock_statements(
        s.db, lambda: service._write_holding_back(s.order, entry, write, True)
    )
    assert calls == [2, 1], calls
    assert seen == [], seen


# F2-dates (crew re-check at 70e528d7, SO418869 CB771): the line's previous revision already froze
# AutoCount's new date while purchasing's row still held the old one, so the change's DELAY row
# carried the Was date and the snapshots did not. With the planner's words the line was rebuilt
# from the snapshots alone: DELIVERY 15/11, NEW DATE blank, while the popup said 01/10 -> 15/11.


def _seed_new_date_frozen_row_old(api):
    from tests.scm.test_confirm_preview_delivered_change import NOW, WAS, _S
    from tests.scm.test_line_splits_api import _mirror
    from tests.test_planning_change_apply_on_board import _build, _change, _confirm
    from tests.test_planning_changes import _core_so, _project_so

    from app.models.project_so import OrderInquiryRow
    from app.services.scm.outstanding_diff import DATE_MOVED

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.order = client, world, db, order
    s.c10, s.l10 = _mirror(db, order, core_so, world.product, world.own_wh,
                           line_no=10, qty=3, when=WAS)
    db.commit()
    assert _confirm(client, order.id, [_line_payload(s.l10.id, buy_qty="3")]).status_code == 200
    # The book moved the line and a later Confirm froze the new date...
    s.c10.required_date = NOW
    s.l10.delivery_date = NOW
    db.commit()
    assert _confirm(client, order.id, [_line_payload(s.l10.id, buy_qty="3")]).status_code == 200
    # ...while purchasing's row still holds the old one (the move is still pending for them).
    for row in db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == s.l10.id):
        row.delivery_date = WAS
    db.commit()
    s.batch = _build(world, [
        _change(DATE_MOVED, s.c10, so_number=core_so.so_number,
                old_date=WAS, new_date=NOW, old_qty="3", new_qty="3"),
    ], core_so, [str(s.c10.id)])
    assert s.batch is not None, "premise: the pending change row exists"
    return s


def _email_rows(calls, item_code):
    return [
        {k: line.get(k) for k in ("qty", "delivery_date", "was", "remark", "location")}
        for call in _handover_calls(calls)
        for line in call["context"]["handover"]["lines"]
        if line["item_code"] == item_code
    ]


def test_f2_the_planners_remark_keeps_the_dates_the_change_told(api, monkeypatch):
    s = _seed_new_date_frozen_row_old(api)
    _register(s.world)
    calls = _captured_dispatches(monkeypatch)

    preview = _press_line_remark(s, preview=True)
    popup = [
        {k: e.get(k) for k in ("qty", "delivery_date", "was", "remark")}
        for e in preview.json()["results"][0].get("email_lines") or []
    ]
    calls.clear()
    real = _press_line_remark(s, preview=False)
    assert real.status_code == 200, real.text
    assert real.json()["results"][0]["ok"], real.text
    sent = _email_rows(calls, s.world.product.product_code)

    assert len(sent) == 1, sent
    assert sent[0]["remark"] == OWN, sent
    assert sent[0]["delivery_date"] == "02/11/2026", sent
    assert (sent[0]["was"] or {}).get("delivery_date") == "28/09/2026", sent
    assert [{k: v for k, v in r.items() if k != "location"} for r in sent] == popup, (sent, popup)
