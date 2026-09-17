"""S3 (#980) - the "Order inquiry undone" email.

RED for Phase 2 of `documentation/plans/scm/PLAN-board-undo-last-confirm.md`, "The email".
Nothing in this file has an implementation yet:

* `order_inquiry_undone` is not in the trigger catalog - `automation_triggers.list_specs()`
  has no entry for it, and `automation_triggers.fire(db, "order_inquiry_undone", ...)` raises
  `ValueError: Unknown trigger type`.
* `undo_last_confirm` does not record anything for the drain to fire - the "one dispatch"
  tests capture zero calls where they expect exactly one, which is this file's other "right
  reason" until the recorder and the third post-commit triple exist.
* No alembic migration under `alembic/versions/` seeds `email_templates.code =
  'order_inquiry_undone_default'` / `automations.trigger_type = 'order_inquiry_undone'` yet -
  `_load_undo_seed_migration()` asserts a discovery failure by name.

Two harnesses, matching `tests/test_order_inquiry_handover_automation.py`'s own split:

* the RECORDER/DRAIN/DISPATCH contract (AC-UC-32/AC-UC-33) reuses the S2 seed helpers from
  `tests/test_board_undo_last_confirm.py` (imported, not duplicated) - the `api` fixture off
  `tests/test_so_supply_confirmation.py`'s blank scratch schema, and
  `AutomationService.dispatch_event` monkeypatched exactly the way the handover suite's own
  `_captured_dispatches` does, for the same reason: the drain's fresh `SessionLocal()` is a
  genuinely separate connection that cannot see this suite's own rolled-back savepoint;
* the TRIGGER CATALOG (AC-UC-35) and SEED MIGRATION + TEMPLATE (AC-UC-34) need no confirm
  chain at all, and use `tests/_pg_fixture.py`'s `blank_session()` directly - the same split,
  and largely the same code, `test_order_inquiry_handover_automation.py` uses for
  `test_trigger_in_catalog` / `test_seed_migration_idempotent` /
  `test_seed_migration_downgrade_removes_both`.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.project_so import (
    INQUIRY_PLACED,
    IV_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
    SOSupplyDecision,
)
from app.services.error_handler import AppException

from ._pg_fixture import blank_session
from .test_board_undo_last_confirm import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _link_with_claim,
    _po_line,
    _project_line,
    _project_so,
    _stock,
    _uid,
    api,
)

MARKER = "zzt-undo-email"
TRIGGER = "order_inquiry_undone"


# --------------------------------------------------------------------------- #
# shared harness (mirrors test_order_inquiry_handover_automation.py)          #
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


def _register() -> None:
    """Idempotent (module-global flag), same call site the handover suite uses -
    `TestClient(app)` without `with` never runs FastAPI's lifespan here."""
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()


def _undo_calls(calls: list[dict]) -> list[dict]:
    return [c for c in calls if c["trigger_type"] == TRIGGER]


def _seed_undo_world(api):
    """Two lines, twice confirmed: rev1 raises+auto-links line1 (standing in for the
    raise-time cascade, the same trick `test_board_undo_last_confirm.py` uses), rev2 (the
    revision the tests below undo) settles line1 in place (qty 20 -> 15, so the undo's
    context has a "back to 20" line) and freshly Buys line2 (a brand new raised row, so the
    undo's context also has a "removed" line).
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)
    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    core_line_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    order = _project_so(db, world.project, so_id=core_so.id)
    line_1 = _project_line(db, order, line_no=10, product=world.product, core_line=core_line_1)
    line_2 = _project_line(db, order, line_no=20, product=world.product, core_line=core_line_2)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="20")]},
    )
    assert first.status_code == 200, first.text
    decision1 = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    row_1 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_1.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    po, po_line = _po_line(db, world, qty=20)
    _link_with_claim(db, world, row_1, po_line, qty=20, so_number=core_so.so_number)
    row_1.state = INQUIRY_PLACED
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_1.id, buy_qty="15",
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "5"}],
                ),
                _line_payload(line_2.id, buy_qty="10"),
            ]
        },
    )
    assert second.status_code == 200, second.text
    decision2 = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.revision_no == 2,
        )
        .one()
    )
    row_2 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_2.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    return {
        "client": client, "world": world, "db": db, "order": order, "core_so": core_so,
        "decision1": decision1, "decision2": decision2, "row_1": row_1, "row_2": row_2,
    }


# --------------------------------------------------------------------------- AC-UC-32


def test_an_undo_dispatches_one_undone_event_after_commit_with_the_lines(api, monkeypatch):
    _register()
    calls = _captured_dispatches(monkeypatch)
    fixture = _seed_undo_world(api)
    db = fixture["db"]
    order = fixture["order"]
    world = fixture["world"]

    from app.services.project_supply_undo_service import undo_last_confirm

    undo_last_confirm(db, order, actor_user_id=world.eling)
    assert _undo_calls(calls) == [], "nothing may dispatch before the write commits"

    db.commit()

    matches = _undo_calls(calls)
    assert len(matches) == 1, "exactly one dispatch per undo"
    call = matches[0]
    assert call["source_kind"] == TRIGGER
    assert call["source_id"] == str(fixture["decision2"].id)

    ctx = call["context"]
    assert set(ctx.keys()) >= {"undo", "actor", "today"}
    undo_ctx = ctx["undo"]
    for key in ("so_number", "customer", "project", "revision_no", "lines", "link"):
        assert key in undo_ctx, key
    assert undo_ctx["so_number"] == fixture["core_so"].so_number
    assert undo_ctx["revision_no"] == fixture["decision2"].revision_no

    from app.services.automation_triggers import build_order_inquiry_link

    assert undo_ctx["link"] == build_order_inquiry_link(fixture["core_so"].so_number)
    assert ctx["today"] == date.today().strftime("%d/%m/%Y")

    lines = undo_ctx["lines"]
    for line in lines:
        for key in ("item_code", "qty", "delivery_date", "outcome"):
            assert key in line, key

    removed = [entry for entry in lines if entry["outcome"] == "removed"]
    assert len(removed) == 1, "line2's freshly-raised row is gone - outcome 'removed'"
    assert removed[0]["item_code"] == world.product.product_code
    assert removed[0]["qty"] == "10"

    back_to = [entry for entry in lines if entry["outcome"].startswith("back to")]
    assert len(back_to) == 1, "line1's row existed before the undone confirm"
    assert "20" in back_to[0]["outcome"]
    assert back_to[0]["qty"] == "20"


# --------------------------------------------------------------------------- AC-UC-33


@pytest.mark.parametrize("arm", ["refused_manual_link", "rolled_back"])
def test_a_refused_or_rolled_back_undo_dispatches_nothing(api, monkeypatch, arm):
    _register()
    calls = _captured_dispatches(monkeypatch)
    fixture = _seed_undo_world(api)
    db = fixture["db"]
    order = fixture["order"]
    world = fixture["world"]

    from app.services.project_supply_undo_service import undo_last_confirm

    if arm == "refused_manual_link":
        po, po_line = _po_line(db, world, qty=5)
        db.add(
            OrderInquiryLink(
                id=_uid(), company_id=world.company_id, row_id=fixture["row_2"].id,
                po_line_id=po_line.id, document=po.po_number, qty=Decimal("5"),
                linked_by=world.eling, auto=False,
                linked_at=fixture["decision2"].confirmed_at + timedelta(minutes=1),
            )
        )
        db.commit()
        with pytest.raises(AppException):
            undo_last_confirm(db, order, actor_user_id=world.eling)
        db.commit()
    else:
        savepoint = db.begin_nested()
        undo_last_confirm(db, order, actor_user_id=world.eling)
        savepoint.rollback()
        db.commit()  # an unrelated commit: nothing rolled back above may still fire

    assert _undo_calls(calls) == [], f"arm={arm!r} must dispatch nothing"


# --------------------------------------------------------------------------- AC-UC-34


def _find_undo_seed_migration_path() -> Path | None:
    """Locate the coder's seed migration by its data contract - the revision id is not
    fixed at brief time, the same reasoning
    `test_order_inquiry_handover_automation.py::_find_seed_migration_path` states."""
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    for path in versions_dir.glob("*.py"):
        try:
            text = path.read_text()
        except OSError:
            continue
        if "order_inquiry_undone_default" in text and "order_inquiry_undone" in text:
            return path
    return None


def _load_undo_seed_migration():
    path = _find_undo_seed_migration_path()
    assert path is not None, (
        "no alembic migration seeding email_templates.code="
        "'order_inquiry_undone_default' / automations.trigger_type="
        "'order_inquiry_undone' was found under alembic/versions/ - the coder must add it "
        "(PLAN-board-undo-last-confirm.md 'The email', AC-UC-34)."
    )
    spec = importlib.util.spec_from_file_location("zzt_undo_seed_migration", path)
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


def test_the_migration_seeds_an_enabled_automation_and_template_once():
    module = _load_undo_seed_migration()
    with blank_session() as db:
        _run_upgrade(module, db)
        _run_upgrade(module, db)  # idempotent re-run: no duplicates, never an update

        templates = db.execute(
            sa.text(
                "SELECT count(*) FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).scalar()
        assert templates == 1

        rows = db.execute(
            sa.text(
                "SELECT enabled, trigger_type, action_type, recipient_config FROM "
                "automations WHERE trigger_type = 'order_inquiry_undone' "
                "AND name = 'Order inquiry undone'"
            )
        ).fetchall()
        assert len(rows) == 1
        enabled, trigger_type, action_type, recipient_config = rows[0]
        assert enabled is True
        assert trigger_type == "order_inquiry_undone"
        assert action_type == "send_email"
        cfg = (
            recipient_config
            if isinstance(recipient_config, dict)
            else json.loads(recipient_config)
        )
        # No handover automation row exists in this blank schema, so the "copied from the
        # handover row when present" branch falls to its own default - the same shape
        # `oihe_0001_seed_handover_automation.py` seeds when no purchasing role exists.
        assert cfg.get("include_actor") is True
        assert cfg.get("one_email") is True
        assert cfg.get("user_ids") == []
        assert cfg.get("extra_emails") == []
        assert cfg.get("role_ids") == []

        _run_downgrade(module, db)

        templates_after = db.execute(
            sa.text(
                "SELECT count(*) FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).scalar()
        assert templates_after == 0
        automations_after = db.execute(
            sa.text(
                "SELECT count(*) FROM automations WHERE trigger_type = 'order_inquiry_undone'"
            )
        ).scalar()
        assert automations_after == 0


# --------------------------------------------------------------------------- AC-UC-35


def test_the_undone_trigger_is_in_the_catalog():
    from app.services import automation_triggers

    spec = next(
        (s for s in automation_triggers.list_specs() if s.type == TRIGGER),
        None,
    )
    assert spec is not None, f"{TRIGGER!r} must be registered in the trigger catalog"
    assert spec.label == "Order inquiry undone"
    assert spec.config_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    with blank_session() as db:
        matches = automation_triggers.fire(db, TRIGGER, {}, "Asia/Kuala_Lumpur")
    assert matches == [], "pull-mode evaluation yields nothing - this trigger is event-driven"
