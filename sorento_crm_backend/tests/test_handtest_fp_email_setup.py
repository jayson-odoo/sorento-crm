"""PR #2220 crew hand-test setup (`scripts/handtest_fp_email_setup.py`): what it builds, that the
AutoCount removal it replays emails nobody, that the board Confirm it leaves for the owner is the
one email, and that `--cleanup` puts every automation and order back.

The real-SO pick (`PICK_SQL`) needs a prod copy, so the test hands `apply` its own pick built on
the `env` fixture's products; everything after the pick is the script's own code. Dispatches are
captured (`_captured_dispatches`), so no automation actually runs. Postgres only.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.models.automation import Automation
from app.models.email_template import EmailTemplate
from app.models.inventory import Warehouse

from .test_ingest_documents import _code_of_ref, env  # noqa: F401 - pytest fixture
from .test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
)

__all__ = ["env"]

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "handtest_fp_email_setup.py"
_spec = importlib.util.spec_from_file_location("handtest_fp_email_setup", _PATH)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

ORIGINAL_RECIPIENTS = {"role_ids": ["zzt-purchasing"], "include_actor": True}


def _user(db, *, active: bool) -> str:
    from app.models.user import User

    user_id = str(uuid.uuid4())
    db.add(User(
        id=user_id, email=f"{user_id}@zzt.test", name="ZZT",
        status="ACTIVE" if active else "INACTIVE",
    ))
    db.flush()
    return user_id


def _class_and_raiser(cls: str, raisers: list) -> dict:
    return {
        "combinator": "and",
        "rules": [
            {"fact": "order_inquiry.salesOrderClass", "operator": "eq", "value": cls},
            {"fact": "order_inquiry.raisedBy", "operator": "in", "value": raisers},
        ],
    }


def _automations(db) -> dict:
    """The copy's shape (sorento_prod_1104, 6 Nov): the Project and Dealer handover rows are
    on and route by class AND raiser; "Order inquiry undone" is off, with no conditions."""
    template = EmailTemplate(
        code=f"zzt-fp-email-{uuid.uuid4().hex[:12]}",
        name="ZZT", subject="OI", body_html="<p>x</p>",
    )
    db.add(template)
    db.flush()
    inactive, active, dealer_only = (
        _user(db, active=False), _user(db, active=True), _user(db, active=True)
    )
    spec = {
        "project": ("order_inquiry_handover", True, _class_and_raiser("project", [inactive, active])),
        "dealer": ("order_inquiry_handover", True, _class_and_raiser("retail", [dealer_only])),
        "undone": ("order_inquiry_undone", False, None),
    }
    rows = {}
    for key, (trigger, enabled, conditions) in spec.items():
        row = Automation(
            name=f"ZZT {key}", trigger_type=trigger, enabled=enabled,
            email_template_id=template.id, recipient_config=dict(ORIGINAL_RECIPIENTS),
            conditions_json=conditions,
        )
        db.add(row)
        rows[key] = row
    db.commit()
    rows["active_raiser"] = active
    return rows


def _pick(env) -> dict:
    warehouse_id = env.refs.resolve(entity_type="warehouses", source_ref=env.warehouse_ref)
    code = env.db.query(Warehouse.warehouse_code).filter(Warehouse.id == str(warehouse_id)).scalar()
    when = date.today() + timedelta(days=30)
    return {
        "company_id": env.company_a,
        "customer_code": None,
        "item_codes": [_code_of_ref(env, env.product_ref), _code_of_ref(env, env.product2_ref)],
        "locations": [code, code],
        "qtys": ["10", "6"],
        "prices": ["12.50", "8.00"],
        "dates": [when, when],
        "uoms": [None, None],
    }


@pytest.fixture()
def built(env, monkeypatch, tmp_path):
    monkeypatch.setattr(script, "STATE_DIR", tmp_path)
    _register(None)
    calls = _captured_dispatches(monkeypatch)
    automations = _automations(env.db)
    report = script.apply(env.db, pick=_pick(env))
    return env, calls, automations, report


def test_the_autocount_removal_emails_nobody_and_waits_on_the_board(built):
    env, calls, automations, report = built
    removal = report["remove"]

    assert removal["pushed_now"] is True
    assert removal["line_status"] == "cancelled"
    assert removal["oi_row_states"] == ["raised"], removal
    assert removal["pending_cancelled_changes"] == 1, removal
    assert removal["new_automation_runs"] == 0 and removal["new_outgoing_mails"] == 0, removal
    assert _handover_calls(calls) == [], [c["trigger_type"] for c in calls]


def test_apply_raises_the_inquiries_as_an_active_user_the_project_row_lets_through(built):
    """Crew on the copy (6 Nov): with no raiser no handover row passed. The raiser is the
    first ACTIVE user the Project row's `raisedBy` "is any of" names (the inactive one is
    skipped), and both hand-test inquiries carry it."""
    from app.models.project_so import OrderInquiry, ProjectSalesOrder

    env, calls, automations, report = built
    assert report["raiser"] == automations["active_raiser"]
    for _, _, doc_key in script.ORDERS:
        header = script._header(env.db, doc_key)
        raised_by = (
            env.db.query(OrderInquiry.raised_by)
            .join(ProjectSalesOrder, ProjectSalesOrder.id == OrderInquiry.project_sales_order_id)
            .filter(ProjectSalesOrder.so_id == str(header.id))
            .scalar()
        )
        assert str(raised_by) == automations["active_raiser"]


def test_apply_switches_on_the_project_and_undone_rows_mailing_only_the_test_address(built):
    env, calls, automations, report = built
    for key in ("project", "undone"):
        row = automations[key]
        env.db.refresh(row)
        assert row.enabled is True, key
        assert row.recipient_config["extra_emails"] == [script.HANDTEST_ADDRESS]
        assert row.recipient_config["role_ids"] == []
        assert row.recipient_config["include_actor"] is False
    dealer = automations["dealer"]
    env.db.refresh(dealer)
    assert dealer.enabled is True and dealer.recipient_config == ORIGINAL_RECIPIENTS


def test_apply_again_changes_nothing(built):
    env, calls, automations, report = built

    again = script.apply(env.db)

    assert again["remove"]["pushed_now"] is False
    assert again["remove"]["oi_row_states"] == ["raised"]
    assert _handover_calls(calls) == []


def test_the_owners_board_confirm_is_the_one_email(built):
    """What the owner's press does on HT-EMAIL-REMOVE: the board Confirm applies the pending
    change (the route marks its transaction), retires the row and emails one CANCEL."""
    from app.models.planning_change import PlanningChangeRow
    from app.services import planning_change_service
    from app.services.project_order_inquiry_service import mark_purchasing_email_trigger

    env, calls, automations, report = built
    header = script._header(env.db, script.ORDERS[0][2])
    core = script._core_line(env.db, str(header.id), script.SEQ_SUBJECT)
    batch_id = (
        env.db.query(PlanningChangeRow.batch_id)
        .filter(PlanningChangeRow.core_line_id == str(core.id))
        .scalar()
    )

    mark_purchasing_email_trigger(env.db)
    planning_change_service.apply(env.db, str(batch_id), None)
    env.db.commit()

    assert script._removal_state(env.db, header)["oi_row_states"] == ["cancelled"]
    matches = _handover_calls(calls)
    assert len(matches) == 1, [c["trigger_type"] for c in calls]
    assert all("CANCEL" in line["remark"] for line in matches[0]["context"]["handover"]["lines"])


def test_cleanup_restores_every_automation_and_removes_both_orders(built):
    env, calls, automations, report = built
    from app.models.project_so import ProjectSalesOrder
    from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
    from app.services.project_order_inquiry_service import mark_purchasing_email_trigger
    from app.services.project_supply_service import ProjectSupplyService

    # The owner's Confirm on HT-EMAIL-UNDO, so cleanup also meets a confirmed order.
    header = script._header(env.db, script.ORDERS[1][2])
    order = env.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == str(header.id)).one()
    from app.models.project_so import ProjectSalesOrderLine

    supply = ProjectSupplyService(env.db)
    line = (
        env.db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == order.id)
        .order_by(ProjectSalesOrderLine.line_no)
        .first()
    )
    mark_purchasing_email_trigger(env.db)
    supply.confirm(
        supply.get_order(str(order.id)),
        ConfirmSupplyBody(lines=[ConfirmLine(
            project_line_id=str(line.id), buy_qty=str(line.qty), buy_reason="ZZT hand test",
        )]),
        actor_user_id=None,
    )
    env.db.commit()
    assert len(_handover_calls(calls)) == 1

    script.cleanup(env.db)

    env.db.expire_all()
    assert [automations[k].enabled for k in ("project", "dealer", "undone")] == [True, True, False]
    for key in ("project", "dealer", "undone"):
        assert automations[key].recipient_config == ORIGINAL_RECIPIENTS, key
    assert all(script._header(env.db, doc_key) is None for _, _, doc_key in script.ORDERS)
    assert not script._state_file(env.db).exists()


def test_a_second_row_that_would_also_fire_is_off_for_the_test_and_restored(
    env, monkeypatch, tmp_path
):
    """Only the hand-test address may be mailed: another enabled row that passes for the
    hand-test orders (it would mail its real recipients) is switched off by `--apply` and
    switched back on by `--cleanup`."""
    monkeypatch.setattr(script, "STATE_DIR", tmp_path)
    _register(None)
    _captured_dispatches(monkeypatch)
    automations = _automations(env.db)
    twin = Automation(
        name="ZZT project twin", trigger_type="order_inquiry_handover", enabled=True,
        email_template_id=automations["project"].email_template_id,
        recipient_config=dict(ORIGINAL_RECIPIENTS),
        conditions_json=_class_and_raiser("project", [automations["active_raiser"]]),
    )
    env.db.add(twin)
    env.db.commit()

    script.apply(env.db, pick=_pick(env))
    env.db.refresh(twin)
    assert twin.enabled is False

    script.cleanup(env.db)
    env.db.expire_all()
    assert twin.enabled is True and twin.recipient_config == ORIGINAL_RECIPIENTS
