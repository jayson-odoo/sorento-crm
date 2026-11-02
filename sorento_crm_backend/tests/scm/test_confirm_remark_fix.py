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
