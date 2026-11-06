"""PR #2220 crew hand-test setup (`scripts/handtest_fp_email_setup.py`): what it builds, that the
AutoCount removal it replays emails nobody, that the board Confirm it leaves for the owner is the
one email, and that `--cleanup` puts every automation and order back.

The real-SO pick (`PICK_SQL`) needs a prod copy, so the test hands `apply` its own pick built on
the `env` fixture's products; everything after the pick is the script's own code. Dispatches are
captured (`_captured_dispatches`), so no automation actually runs. Postgres only.
"""
from __future__ import annotations

import importlib.util
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


def _automations(db) -> dict:
    template = EmailTemplate(
        code=f"zzt-fp-email-{date.today().isoformat()}-{id(db)}",
        name="ZZT", subject="OI", body_html="<p>x</p>",
    )
    db.add(template)
    db.flush()
    rows = {}
    for trigger in script.TRIGGERS:
        row = Automation(
            name=f"ZZT {trigger}", trigger_type=trigger, enabled=False,
            email_template_id=template.id, recipient_config=dict(ORIGINAL_RECIPIENTS),
        )
        db.add(row)
        rows[trigger] = row
    db.commit()
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


def test_apply_switches_on_one_automation_per_trigger_mailing_only_the_test_address(built):
    env, calls, automations, report = built
    for row in automations.values():
        env.db.refresh(row)
        assert row.enabled is True
        assert row.recipient_config["extra_emails"] == [script.HANDTEST_ADDRESS]
        assert row.recipient_config["role_ids"] == []
        assert row.recipient_config["include_actor"] is False


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
    for row in automations.values():
        assert row.enabled is False
        assert row.recipient_config == ORIGINAL_RECIPIENTS
    assert all(script._header(env.db, doc_key) is None for _, _, doc_key in script.ORDERS)
    assert not script._state_file(env.db).exists()
