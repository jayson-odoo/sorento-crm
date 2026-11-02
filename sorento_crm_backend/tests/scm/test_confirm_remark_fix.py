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


def test_f1_one_email_per_press_when_purchasing_is_notified(api, monkeypatch, sent_notices):
    """The mid-write commit also split the press: the lines queued after it went in a second
    email. One press, one email."""
    s = _seed(api, pending=True)
    _seed_purchasing_user(s.db)
    s.db.commit()
    _register(s.world)
    calls = _captured_dispatches(monkeypatch)

    real = _press_with_remark(s, preview=False)
    assert real.status_code == 200, real.text
    assert len(_handover_calls(calls)) == 1, _handover_calls(calls)


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
