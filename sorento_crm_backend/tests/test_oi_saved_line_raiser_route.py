"""OI-SAVED-LINE-RAISER-HOTFIX (7 Nov 2026): a board Confirm whose purchasing line goes through
`_queue_saved_line` (a qty cut, a date move, a Borrow donor move, a planner's remark) reaches the
raiser-conditioned `order_inquiry_handover` rows (OI-ROUTE-BY-RAISER, #2152).

The bug: `_queue_saved_line`'s queue item carried no `raised_by`, and the header fallback in
`handover_route_groups` ran on `_fire_pending_handover`'s fresh `SessionLocal()`, which in
production carries NO company scope (UNSET, fail-closed: 0 rows). So the raiser read "" and
every raiser-conditioned row matched nothing: no email.

Why the suite missed it: `tests/conftest.py` gives every unscoped session the Sorento company,
and the `emails` fixture fakes `dispatch_event`, so no row's conditions were ever read. Here the
post-commit session is forced back to production's UNSET and the REAL dispatch runs (SMTP
stubbed), against a row conditioned on "raised by is any of [the OI's raiser]".
"""
from __future__ import annotations

import pytest

from .test_oi_route_by_raiser import _rule, _row_automation, _runs_by_automation, _template
from .test_oi_saved_line_email import _borrow_from, _donor, _one_line_order, _post
from .test_planning_change_apply_on_board import api, world  # noqa: F401 - fixtures
from .test_planning_changes import _line_payload
from .test_so_supply_confirmation import _stock

__all__ = ["api", "world"]

HANDOVER = "order_inquiry_handover"


@pytest.fixture()
def production_dispatch(monkeypatch, world):
    """The real post-commit dispatch, its fresh session as production opens it (no company
    scope), SMTP stubbed; yields every item list `send_handover_groups` was handed.

    The fresh session joins the world's connection (`create_savepoint`, as the world's own
    session does) so it sees the seeded, never-really-committed rows."""
    import app.database as database
    from app.models.base import UNSET
    from app.services import notification_email
    from app.services import project_order_inquiry_service as svc

    svc.register_order_inquiry_post_commit_dispatch()
    monkeypatch.setattr(notification_email, "send_notification_email", lambda *a, **kw: None)
    monkeypatch.setattr(
        notification_email, "send_notification_email_multi", lambda *a, **kw: None
    )
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **kw: None)

    from sqlalchemy.orm import Session

    connection = world.db.get_bind()

    def _unscoped_session(*_args, **_kwargs):
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint", autoflush=False
        )
        # Production's default: no resolver ran. The test conftest's after_begin default only
        # fills an ABSENT key, so this wins over it.
        session.info["company_scope"] = UNSET
        return session

    monkeypatch.setattr(database, "SessionLocal", _unscoped_session)

    handed: list = []
    real_send = svc.send_handover_groups

    def _spy(db, items, *, store_excel):
        handed.append([dict(item) for item in items])
        return real_send(db, items, store_excel=store_excel)

    monkeypatch.setattr(svc, "send_handover_groups", _spy)
    return handed


def _raiser_row(world):
    """The owner's shape: a project row conditioned on who raised the OI (the Confirm's actor,
    `OrderInquiry.raised_by` at insert)."""
    db = world.db
    template = _template(db)
    raiser = str(world.actor)
    row = _row_automation(
        db, template, raiser, name="zzt-saved-line-raiser", recipient=raiser,
        conditions=_rule("in", [raiser]),
    )
    db.commit()
    return row


def _saved_line_reconfirm(api, flow):
    """Confirm once, then re-Confirm a change whose purchasing line is a SAVED line
    (`_queue_saved_line`): a Borrow donor move, or Use BRW turned to a Buy."""
    _client, world = api
    _stock(world.db, world.product, world.pool_wh, on_hand=50)
    world.db.commit()
    order, line, _core_line = _one_line_order(world, "10")
    if flow == "borrow_donor_move":
        first_donor, second_donor = _donor(world, "RX"), _donor(world, "RY")
        first = {"borrow": _borrow_from(world, first_donor, "10")}
        second = {"borrow": _borrow_from(world, second_donor, "10")}
    else:
        first = {"reserve": [{"warehouse_id": world.pool_wh.id, "qty": "10"}]}
        second = {"buy_qty": "10"}
    _post(api, order, [_line_payload(line.id, **first)])
    return order, line, second


FLOWS = ["borrow_donor_move", "use_brw_to_buy"]


def _saved_items(handed):
    return [
        item for items in handed for item in items
        if str(item.get("row_id", "")).startswith("saved:")
    ]


@pytest.mark.parametrize("flow", FLOWS)
def test_a_saved_line_change_emails_the_raiser_conditioned_row(api, production_dispatch, flow):
    _client, world = api
    row = _raiser_row(world)
    order, line, second = _saved_line_reconfirm(api, flow)
    before = len(_runs_by_automation(world.db).get(str(row.id), []))
    production_dispatch.clear()

    _post(api, order, [_line_payload(line.id, amend_reason="Changed.", **second)])

    assert _saved_items(production_dispatch), production_dispatch
    after = _runs_by_automation(world.db).get(str(row.id), [])
    assert len(after) == before + 1, (
        "the raiser-conditioned row sent no email for the saved line", after,
    )


@pytest.mark.parametrize("flow", FLOWS)
def test_every_queued_handover_item_carries_its_raiser(api, production_dispatch, flow):
    """The unit guard: no item reaches the post-commit drain without `raised_by`, whichever
    builder queued it (a row line, a saved line), so routing never depends on reading the
    header back on a session with no company scope."""
    _client, world = api
    order, line, second = _saved_line_reconfirm(api, flow)
    _post(api, order, [_line_payload(line.id, amend_reason="Changed.", **second)])

    items = [item for items in production_dispatch for item in items]
    assert _saved_items(production_dispatch), items
    missing = [item.get("row_id") for item in items if not item.get("raised_by")]
    assert missing == [], f"queued without raised_by: {missing}"
    assert {item["raised_by"] for item in items} == {str(world.actor)}


def test_the_header_fallback_reads_the_raiser_on_a_session_with_no_company_scope(api):
    """An item queued without `raised_by` (a stand-in, an older queue) reads it off its OI
    header, also on the post-commit session that carries no company scope."""
    from sqlalchemy.orm import Session

    from app.models.base import UNSET
    from app.models.project_so import OrderInquiry
    from app.services.project_order_inquiry_service import handover_route_groups

    _client, world = api
    order, line, second = _saved_line_reconfirm(api, "use_brw_to_buy")
    _post(api, order, [_line_payload(line.id, amend_reason="Changed.", **second)])
    inquiry_id = (
        world.db.query(OrderInquiry.id)
        .filter(OrderInquiry.project_sales_order_id == order.id)
        .scalar()
    )
    assert inquiry_id is not None
    fresh = Session(
        bind=world.db.get_bind(), join_transaction_mode="create_savepoint", autoflush=False
    )
    fresh.info["company_scope"] = UNSET
    try:
        item = {"order_inquiry_id": str(inquiry_id), "sales_order_class": "project"}
        handover_route_groups(fresh, [item])
    finally:
        fresh.close()
    assert item["raised_by"] == str(world.actor)
