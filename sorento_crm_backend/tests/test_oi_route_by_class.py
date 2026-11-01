"""DEALER-OI-ROUTE (DEALER-PLANNING PR 3): order inquiry emails routed by sales order class,
explicit To and Cc.

Plan: `documentation/plans/scm/PLAN-dealer-oi-route-1nov.md`; contract:
`dealer-oi-route-1nov-acceptance-criteria.md` beside it. Written before the code.

Three harnesses:

* pure / catalog checks need no database;
* the handover and undo DISPATCH contract reuses the handshake suite's `api` / `world`
  fixtures and the board-undo suite's seed, with `dispatch_event` captured (the drain's
  fresh session cannot see the test's own savepoint, same reason as the sibling suites);
* the routing itself (conditions, resend pick, To/Cc) runs a REAL `dispatch_event` on a
  blank scratch schema (`blank_session`).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_supply_service import ProjectSupplyService

from ._pg_fixture import blank_session
from .test_order_inquiry_handshake import (  # noqa: F401  (api/world are fixtures)
    WAS,
    _core_line,
    _core_so,
    _project_line,
    _project_so,
    api,
    world,
)

HANDOVER = "order_inquiry_handover"
UNDONE = "order_inquiry_undone"
CLASS_KEY = "order_inquiry.salesOrderClass"


def _class_rule(value: str) -> dict:
    return {
        "kind": "group",
        "combinator": "and",
        "rules": [{"kind": "condition", "fact": CLASS_KEY, "operator": "eq", "value": value}],
    }


# --------------------------------------------------------------------------- #
# AC-R1: the class fact                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("trigger", [HANDOVER, UNDONE])
def test_handover_and_undo_triggers_expose_the_class_fact(trigger):
    from app.rule_engine.registry import fact_map
    from app.services import automation_triggers

    sources = automation_triggers.fact_sources_for(trigger)
    assert sources == ("order_inquiry",)
    fact = fact_map(sources)[CLASS_KEY]
    assert fact.type == "enum"
    assert [o["value"] for o in fact.options] == ["retail", "project"]


@pytest.mark.parametrize(
    "stored, expected",
    [
        ("retail", "retail"),
        ("other", "retail"),
        ("project", "project"),
        (None, "project"),
        ("", "project"),
    ],
)
def test_sales_order_class_mapping(stored, expected):
    from app.services.scm.demand_class import email_class

    assert email_class(stored) == expected


def test_class_condition_validates_for_the_handover_trigger():
    from app.rule_engine.schemas import validate_tree
    from app.services import automation_triggers

    assert validate_tree(_class_rule("retail"), automation_triggers.fact_sources_for(HANDOVER)) == []


# --------------------------------------------------------------------------- #
# AC-R2/AC-R3: one email per class, the class rides the context               #
# --------------------------------------------------------------------------- #


def _captured(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def _fake(self, trigger_type, *, context, source_kind, source_id):
        calls.append({"trigger_type": trigger_type, "context": context})
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event", _fake
    )
    return calls


def _register() -> None:
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()


def _order(db, world, demand_class, qty="10"):
    core_so = _core_so(db, world.company_id)
    core_so.demand_class = demand_class
    core_line = _core_line(
        db, core_so, world.product, world.warehouse, qty_ordered=qty, required_date=WAS
    )
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    return core_so, order, line


@pytest.mark.parametrize(
    "stored, expected",
    [("retail", "retail"), ("other", "retail"), ("project", "project"), (None, "project")],
)
def test_one_order_dispatches_with_its_class(api, monkeypatch, stored, expected):
    client, world = api
    _register()
    calls = _captured(monkeypatch)
    db = world.db
    _core, order, line = _order(db, world, stored)
    db.commit()

    ProjectSupplyService(db).confirm(
        order,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(line.id), buy_qty="10")]),
        actor_user_id=world.cs_user,
    )
    db.commit()

    handover = [c for c in calls if c["trigger_type"] == HANDOVER]
    assert len(handover) == 1
    assert handover[0]["context"]["sales_order_class"] == expected


def test_mixed_class_commit_sends_one_email_per_class(api, monkeypatch):
    client, world = api
    _register()
    calls = _captured(monkeypatch)
    db = world.db
    supply = ProjectSupplyService(db)
    retail_so, retail_order, retail_line = _order(db, world, "retail", qty="10")
    project_so, project_order, project_line = _order(db, world, "project", qty="8")
    db.commit()

    supply.confirm(
        retail_order,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(retail_line.id), buy_qty="10")]),
        actor_user_id=world.cs_user,
    )
    supply.confirm(
        project_order,
        ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(project_line.id), buy_qty="8")]),
        actor_user_id=world.cs_user,
    )
    db.commit()

    handover = [c for c in calls if c["trigger_type"] == HANDOVER]
    by_class = {c["context"]["sales_order_class"]: c["context"]["handover"] for c in handover}
    assert len(handover) == 2, [c["context"]["sales_order_class"] for c in handover]
    assert {o["so_number"] for o in by_class["retail"]["orders"]} == {retail_so.so_number}
    assert {o["so_number"] for o in by_class["project"]["orders"]} == {project_so.so_number}
    assert [ln["so_number"] for ln in by_class["retail"]["lines"]] == [retail_so.so_number]
    assert [ln["so_number"] for ln in by_class["project"]["lines"]] == [project_so.so_number]


def test_two_project_orders_in_one_commit_still_send_one_email(api, monkeypatch):
    client, world = api
    _register()
    calls = _captured(monkeypatch)
    db = world.db
    supply = ProjectSupplyService(db)
    _a, order_a, line_a = _order(db, world, "project")
    _b, order_b, line_b = _order(db, world, None)
    db.commit()
    for order, line in ((order_a, line_a), (order_b, line_b)):
        supply.confirm(
            order,
            ConfirmSupplyBody(lines=[ConfirmLine(project_line_id=str(line.id), buy_qty="10")]),
            actor_user_id=world.cs_user,
        )
    db.commit()

    handover = [c for c in calls if c["trigger_type"] == HANDOVER]
    assert len(handover) == 1
    assert len(handover[0]["context"]["handover"]["lines"]) == 2


def test_undo_context_carries_the_class():
    from app.services.project_order_inquiry_service import _build_undo_context

    for stored, expected in (("retail", "retail"), ("project", "project"), (None, "project")):
        context, _source = _build_undo_context(
            [{"decision_id": "d", "so_number": "SO1", "sales_order_class": expected, "lines": []}]
        )
        assert context["sales_order_class"] == expected
    context, _source = _build_undo_context([{"decision_id": "d", "so_number": "SO1", "lines": []}])
    assert context["sales_order_class"] == "project"


# --------------------------------------------------------------------------- #
# AC-R4/AC-R5: real dispatch, conditions decide which row sends               #
# --------------------------------------------------------------------------- #


def _user(db, stem: str):
    from app.models.user import User

    user = User(
        id=str(uuid.uuid4()),
        email=f"zzt-oiroute-{stem}-{uuid.uuid4().hex[:6]}@test.local",
        name=f"ZZT {stem}",
        status="ACTIVE",
        is_trashed=False,
    )
    db.add(user)
    db.flush()
    return user


def _template(db):
    from app.models.email_template import EmailTemplate

    template = EmailTemplate(
        id=str(uuid.uuid4()),
        code=f"zzt-oiroute-{uuid.uuid4().hex[:6]}",
        name="ZZT OI route",
        subject="OI {{ sales_order_class }}",
        body_html="<p>Hi {{ recipient.name }}</p>",
        body_text=None,
        is_active=True,
    )
    db.add(template)
    db.flush()
    return template


def _automation(db, template, creator, *, name, trigger=HANDOVER, conditions=None,
                recipient_config=None, enabled=True, created_at=None):
    from app.models.automation import Automation

    row = Automation(
        id=str(uuid.uuid4()),
        name=name,
        enabled=enabled,
        trigger_type=trigger,
        trigger_config={},
        action_type="send_email",
        email_template_id=str(template.id),
        recipient_config=recipient_config or {"user_ids": [str(creator.id)], "one_email": True},
        conditions_json=conditions,
        group_matches=False,
        schedule_type="manual",
        timezone="Asia/Kuala_Lumpur",
        created_by_user_id=str(creator.id),
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.flush()
    return row


def _silence_mail(monkeypatch):
    from app.services import notification_email

    monkeypatch.setattr(notification_email, "send_notification_email", lambda *a, **kw: None)
    monkeypatch.setattr(notification_email, "send_notification_email_multi", lambda *a, **kw: None)


@pytest.mark.parametrize("trigger", [HANDOVER, UNDONE])
def test_conditions_pick_the_rows_that_send(monkeypatch, trigger):
    from app.services.automation_service import AutomationService

    _silence_mail(monkeypatch)
    with blank_session() as db:
        creator = _user(db, "creator")
        template = _template(db)
        retail = _automation(db, template, creator, name="retail", trigger=trigger,
                             conditions=_class_rule("retail"))
        project = _automation(db, template, creator, name="project", trigger=trigger,
                              conditions=_class_rule("project"))
        legacy = _automation(db, template, creator, name="legacy", trigger=trigger)
        db.commit()

        def fired(cls: str) -> set:
            result = AutomationService(db).dispatch_event(
                trigger,
                context={"sales_order_class": cls, "handover": {}, "undo": {}},
                source_kind=trigger,
                source_id=str(uuid.uuid4()),
            )
            from app.models.automation import AutomationRun

            run_ids = [r["run_id"] for r in result["results"] if r.get("recipients_attempted", 0) > 0]
            return {
                str(run.automation_id)
                for run in db.query(AutomationRun).filter(AutomationRun.id.in_(run_ids)).all()
            }

        assert fired("retail") == {str(retail.id), str(legacy.id)}
        assert fired("project") == {str(project.id), str(legacy.id)}


def test_resend_picks_the_row_for_the_class(monkeypatch):
    from datetime import datetime, timedelta

    from app.services.oi_handover_resend import handover_automation

    with blank_session() as db:
        creator = _user(db, "creator")
        template = _template(db)
        now = datetime.utcnow()
        project = _automation(db, template, creator, name="project",
                              conditions=_class_rule("project"), created_at=now - timedelta(days=2))
        retail = _automation(db, template, creator, name="retail",
                             conditions=_class_rule("retail"), created_at=now - timedelta(days=1))
        db.commit()

        assert handover_automation(db, "retail").id == retail.id
        assert handover_automation(db, "project").id == project.id

        # A row with no condition answers for every class; the oldest enabled match wins.
        legacy = _automation(db, template, creator, name="legacy",
                             created_at=now - timedelta(days=3))
        db.commit()
        assert handover_automation(db, "retail").id == legacy.id

        # Nothing enabled matches: the oldest row of the trigger, switched off or not.
        for row in (project, retail, legacy):
            row.enabled = False
        db.commit()
        assert handover_automation(db, "retail").id == legacy.id


# --------------------------------------------------------------------------- #
# AC-R6..AC-R9: explicit To and Cc                                            #
# --------------------------------------------------------------------------- #


def test_resolve_marks_cc_entries():
    from app.services.automation_recipients import resolve_recipients

    with blank_session() as db:
        to_user = _user(db, "to")
        cc_user = _user(db, "cc")
        both = _user(db, "both")
        out = resolve_recipients(
            db,
            {
                "user_ids": [str(to_user.id), str(both.id)],
                "cc_user_ids": [str(cc_user.id), str(both.id)],
                "cc_emails": ["cc-external@test.local"],
                "extra_emails": ["to-external@test.local"],
                "include_actor": True,
            },
            promotion_context={"actor": {"name": "Raiser", "email": "raiser@test.local"}},
        )
        by_email = {r["email"].lower(): r["cc"] for r in out}
        assert by_email[to_user.email.lower()] is False
        assert by_email[both.email.lower()] is False, "To wins over Cc"
        assert by_email["to-external@test.local"] is False
        assert by_email[cc_user.email.lower()] is True
        assert by_email["cc-external@test.local"] is True
        assert by_email["raiser@test.local"] is True, "the raiser is always Cc"


def test_cc_role_resolves_to_cc():
    from app.models.user import UserRole, UserRoleAssignment
    from app.services.automation_recipients import resolve_recipients

    with blank_session() as db:
        member = _user(db, "rolemember")
        role = UserRole(id=str(uuid.uuid4()), name=f"ZZT role {uuid.uuid4().hex[:6]}",
                    slug=f"zzt-role-{uuid.uuid4().hex[:6]}")
        db.add(role)
        db.flush()
        db.add(UserRoleAssignment(user_id=str(member.id), role_id=str(role.id)))
        db.flush()
        out = resolve_recipients(db, {"cc_role_ids": [str(role.id)]})
        assert [(r["email"], r["cc"]) for r in out] == [(member.email, True)]


def _one_notification(db, result) -> dict:
    from app.models.notification import Notification

    run_id = result["results"][0]["run_id"]
    notifs = (
        db.query(Notification)
        .filter(
            Notification.source_entity_type == "automation_run",
            Notification.source_entity_id == run_id,
        )
        .all()
    )
    assert len(notifs) == 1
    return dict(notifs[0].data or {})


def test_one_email_puts_every_to_on_to_and_cc_after(monkeypatch):
    from app.services.automation_service import AutomationService

    _silence_mail(monkeypatch)
    with blank_session() as db:
        creator = _user(db, "creator")
        to_a, to_b, cc_c = _user(db, "toa"), _user(db, "tob"), _user(db, "ccc")
        template = _template(db)
        _automation(
            db, template, creator, name="explicit",
            recipient_config={
                "user_ids": [str(to_a.id), str(to_b.id)],
                "cc_user_ids": [str(cc_c.id)],
                "include_actor": True,
                "one_email": True,
            },
        )
        db.commit()
        result = AutomationService(db).dispatch_event(
            HANDOVER,
            context={"sales_order_class": "retail", "handover": {},
                     "actor": {"name": "Raiser", "email": "raiser@test.local"}},
            source_kind=HANDOVER,
            source_id=str(uuid.uuid4()),
        )
        data = _one_notification(db, result)
        emails = [e.lower() for e in data["recipient_emails"]]
        assert emails[:2] == [to_a.email.lower(), to_b.email.lower()]
        assert emails[2:] == [cc_c.email.lower(), "raiser@test.local"]
        assert data["to_count"] == 2


def test_legacy_config_lists_everyone_on_to(monkeypatch):
    """Card Q2 (a): a row saved before Cc existed reads its whole list as To."""
    from app.services.automation_service import AutomationService

    _silence_mail(monkeypatch)
    with blank_session() as db:
        creator = _user(db, "creator")
        a, b = _user(db, "a"), _user(db, "b")
        template = _template(db)
        _automation(
            db, template, creator, name="legacy",
            recipient_config={"user_ids": [str(a.id), str(b.id)], "include_actor": True,
                              "one_email": True},
        )
        db.commit()
        result = AutomationService(db).dispatch_event(
            HANDOVER,
            context={"handover": {}, "actor": {"name": "R", "email": "r@test.local"}},
            source_kind=HANDOVER,
            source_id=str(uuid.uuid4()),
        )
        data = _one_notification(db, result)
        assert data["to_count"] == 2
        assert data["recipient_emails"][-1] == "r@test.local"


def test_only_cc_configured_still_has_a_to(monkeypatch):
    from app.services.automation_service import AutomationService

    _silence_mail(monkeypatch)
    with blank_session() as db:
        creator = _user(db, "creator")
        c = _user(db, "c")
        template = _template(db)
        _automation(db, template, creator, name="cc-only",
                    recipient_config={"cc_user_ids": [str(c.id)], "one_email": True})
        db.commit()
        result = AutomationService(db).dispatch_event(
            HANDOVER, context={"handover": {}}, source_kind=HANDOVER,
            source_id=str(uuid.uuid4()),
        )
        data = _one_notification(db, result)
        assert data["recipient_emails"] == [c.email]
        assert data["to_count"] == 1


def test_outbox_row_carries_every_to(monkeypatch):
    from app.models.email_outbox import EmailOutbox
    from app.services.email_outbox_service import enqueue

    with blank_session() as db:
        outbox_id = enqueue(
            db,
            event_key="notification_delivery",
            to="a@test.local",
            extra_to=["b@test.local"],
            cc=["c@test.local"],
            subject="s",
            body_text="b",
        )
        row = db.get(EmailOutbox, outbox_id)
        assert row.recipient_email == "a@test.local"
        assert row.recipients_json["to"] == ["a@test.local", "b@test.local"]
        assert row.recipients_json["cc"] == ["c@test.local"]


def test_drainer_sends_to_every_to(monkeypatch):
    from types import SimpleNamespace

    from app.tasks import email_outbox_tasks

    sent: dict[str, Any] = {}

    def _fake_send(**kwargs):
        sent.update(kwargs)
        return None

    monkeypatch.setattr(email_outbox_tasks, "send_mime_email", _fake_send)
    monkeypatch.setattr(email_outbox_tasks, "_attachments_for", lambda row: None)
    row = SimpleNamespace(
        recipient_email="a@test.local",
        recipients_json={"to": ["a@test.local", "b@test.local"], "cc": ["c@test.local"], "bcc": []},
        subject="s", body_text="b", body_html=None, from_name=None,
    )
    assert email_outbox_tasks._attempt_send(row, None) is None
    assert sent["to_list"] == ["a@test.local", "b@test.local"]
    assert sent["cc_list"] == ["c@test.local"]

    # An old row with no `to` list still sends to its one recipient.
    sent.clear()
    row.recipients_json = {"cc": ["c@test.local"]}
    email_outbox_tasks._attempt_send(row, None)
    assert sent["to_list"] == ["a@test.local"]


def test_notification_task_splits_on_to_count(monkeypatch):
    from app.tasks import notification_tasks

    captured: dict[str, Any] = {}

    def _fake_enqueue(db, **kwargs):
        captured.update(kwargs)
        return "x"

    monkeypatch.setattr("app.services.email_outbox_service.enqueue", _fake_enqueue)
    split = notification_tasks._split_to_cc(
        {"recipient_emails": ["a@x.test", "b@x.test", "c@x.test"], "to_count": 2}
    )
    assert split == (["a@x.test", "b@x.test"], ["c@x.test"])
    # No to_count (every other sender): first address To, the rest Cc, as before.
    assert notification_tasks._split_to_cc({"recipient_emails": ["a@x.test", "b@x.test"]}) == (
        ["a@x.test"],
        ["b@x.test"],
    )


def test_normalize_keeps_cc_keys():
    from app.services.automation_service import AutomationService

    out = AutomationService._normalize_recipient_config(
        {"cc_user_ids": ["u1"], "cc_role_ids": ["r1"], "cc_emails": [" c@x.test ", ""]}
    )
    assert out["cc_user_ids"] == ["u1"]
    assert out["cc_role_ids"] == ["r1"]
    assert out["cc_emails"] == ["c@x.test"]
    empty = AutomationService._normalize_recipient_config(None)
    assert empty["cc_user_ids"] == [] and empty["cc_role_ids"] == [] and empty["cc_emails"] == []


def test_preview_names_every_to():
    from app.services import park_send

    with blank_session() as db:
        email = park_send.render_preview(
            db,
            HANDOVER,
            {},
            [
                {"email": "a@x.test", "name": "A", "cc": False},
                {"email": "b@x.test", "name": "B", "cc": False},
                {"email": "c@x.test", "name": "C", "cc": True},
            ],
        )
        assert email["to"] == {"name": "A, B"}
        assert email["cc"] == [{"name": "C"}]
