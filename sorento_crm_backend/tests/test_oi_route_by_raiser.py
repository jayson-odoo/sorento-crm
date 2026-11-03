"""OI-ROUTE-BY-RAISER: the order inquiry handover / undo emails routed by who raised the OI.

Plan: `documentation/plans/scm/PLAN-oi-route-by-raiser-3nov.md`; contract:
`oi-route-by-raiser-3nov-acceptance-criteria.md` beside it. Written before the code.

The owner's setup this pins: Eling's project row reads "class is Project AND raised by is
none of [Agnes]", a second row "class is Project AND raised by is any of [Agnes]" goes to
Agnes' own people. Every test runs a REAL `dispatch_event` / resend on a blank scratch schema
(the reserve suite's `api` world), SMTP stubbed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.project_so import INQUIRY_RAISED

from .test_oi_route_by_class import _class_rule
from .test_order_inquiry_reserve import _api, _pso
from .test_order_inquiry_worklist import LIST, _inquiry_for, _row, _uid, _user

HANDOVER = "order_inquiry_handover"
UNDONE = "order_inquiry_undone"
CLASS_KEY = "order_inquiry.salesOrderClass"
RAISER_KEY = "order_inquiry.raisedBy"
PREVIEW = f"{LIST}/handover-resend/preview"
SEND = f"{LIST}/handover-resend/send"
ACTION_PERMISSIONS = ["projects.projects.view", "projects.order_inquiry.action"]


def _rule(raiser_op: str | None = None, raisers=(), cls: str | None = "project") -> dict:
    rules = []
    if cls:
        rules.append({"kind": "condition", "fact": CLASS_KEY, "operator": "eq", "value": cls})
    if raiser_op:
        rules.append(
            {"kind": "condition", "fact": RAISER_KEY, "operator": raiser_op,
             "value": [str(r) for r in raisers]}
        )
    return {"kind": "group", "combinator": "and", "rules": rules}


@pytest.fixture()
def rs(monkeypatch):
    from app.services import notification_email

    monkeypatch.setattr(notification_email, "send_notification_email", lambda *a, **kw: None)
    monkeypatch.setattr(
        notification_email, "send_notification_email_multi", lambda *a, **kw: None
    )
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **kw: None)
    yield from _api(ACTION_PERMISSIONS)


def _template(db):
    """Prints every line's item code, so a test can read which lines an email carried."""
    from app.models.email_template import EmailTemplate

    template = EmailTemplate(
        id=str(uuid.uuid4()),
        code=f"zzt-oiraiser-{uuid.uuid4().hex[:6]}",
        name="ZZT OI raiser",
        subject="OI {{ sales_order_class }}",
        body_html=(
            "<p>{% for line in handover.lines %}[{{ line.item_code }}]{% endfor %}</p>"
        ),
        body_text=None,
        is_active=True,
    )
    db.add(template)
    db.flush()
    return template


def _row_automation(db, template, creator, *, name, recipient, conditions=None,
                    trigger=HANDOVER, enabled=True, created_at=None):
    from app.models.automation import Automation

    row = Automation(
        id=str(uuid.uuid4()),
        name=name,
        enabled=enabled,
        trigger_type=trigger,
        trigger_config={},
        action_type="send_email",
        email_template_id=str(template.id),
        recipient_config={"user_ids": [str(recipient)], "one_email": True,
                          "explicit_to_cc": True},
        conditions_json=conditions,
        group_matches=False,
        schedule_type="manual",
        timezone="Asia/Kuala_Lumpur",
        created_by_user_id=str(creator),
    )
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    db.flush()
    return row


class _Setup:
    """Agnes, Bob and Carol raise project OIs; Eling's row is everyone but Agnes, Agnes'
    row is Agnes only."""

    def __init__(self, world):
        db = world.db
        self.db = db
        self.world = world
        self.agnes = _user(db, "ZZT Agnes")
        self.bob = _user(db, "ZZT Bob")
        self.carol = _user(db, "ZZT Carol")
        self.eling = _user(db, "ZZT Eling")
        self.agnes_team = _user(db, "ZZT Agnes Team")
        template = _template(db)
        now = datetime.utcnow()
        self.eling_row = _row_automation(
            db, template, world.requester, name="eling", recipient=self.eling,
            conditions=_rule("not_in", [self.agnes]), created_at=now - timedelta(days=2),
        )
        self.agnes_row = _row_automation(
            db, template, world.requester, name="agnes", recipient=self.agnes_team,
            conditions=_rule("in", [self.agnes]), created_at=now - timedelta(days=1),
        )
        self.template = template
        db.commit()

    def oi(self, raiser, item: str):
        inquiry = _inquiry_for(self.db, self.world.company_id, _pso(self.db, self.world.company_id))
        inquiry.raised_by = raiser
        row = _row(
            self.db,
            self.world.company_id,
            inquiry,
            state=INQUIRY_RAISED,
            qty="10",
            item_code=item,
            stock_location="BRW-BB",
            delivery_date=date(2026, 11, 20),
        )
        self.db.commit()
        return inquiry, row

    def item(self, row):
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        return ProjectOrderInquiryService(self.db).handover_item(row, kind="raised")


def _runs_by_automation(db, trigger=HANDOVER) -> dict[str, list[str]]:
    """automation id -> the body of every email it sent."""
    from app.models.automation import AutomationRun
    from app.models.notification import Notification

    db.expire_all()
    out: dict[str, list[str]] = {}
    for note in (
        db.query(Notification)
        .filter(Notification.type == "automation_email",
                Notification.data["trigger_type"].astext == trigger)
        .all()
    ):
        run = db.get(AutomationRun, note.source_entity_id)
        if run is None:
            continue
        out.setdefault(str(run.automation_id), []).append(
            (note.data or {}).get("body_html") or ""
        )
    return out


# --------------------------------------------------------------------------- #
# R1: the raiser fact                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("trigger", [HANDOVER, UNDONE])
def test_both_triggers_expose_the_raiser_fact(trigger):
    from app.rule_engine.registry import fact_map
    from app.rule_engine.schemas import validate_tree
    from app.services import automation_triggers

    sources = automation_triggers.fact_sources_for(trigger)
    fact = fact_map(sources)[RAISER_KEY]
    assert fact.label == "Raised by"
    assert fact.type == "enum"
    assert validate_tree(_rule("not_in", ["u1"]), sources) == []
    assert validate_tree(_rule("in", ["u1"]), sources) == []


def test_raiser_options_are_people_by_name(rs):
    from app.rule_engine.registry import fact_map
    from app.services import automation_triggers

    _client, world = rs
    agnes = _user(world.db, "ZZT Agnes Options")
    fact = fact_map(automation_triggers.fact_sources_for(HANDOVER))[RAISER_KEY]
    options = fact.options(world.db, None)
    assert {"value": agnes, "label": "ZZT Agnes Options"} in options


def test_raiser_fact_reads_the_context():
    from app.rule_engine.evaluator import evaluate
    from app.rule_engine.registry import resolve_facts
    from app.services.automation_triggers import context_fact_sources

    tree = _rule("not_in", ["agnes"])
    for raiser, expected in (("agnes", False), ("bob", True), (None, True)):
        ctx = {"sales_order_class": "project", "raised_by": raiser}
        facts = resolve_facts(None, context_fact_sources(HANDOVER, ctx))
        assert bool(evaluate(tree, facts)) is expected, raiser


# --------------------------------------------------------------------------- #
# R2-R4: one email per matching row set                                       #
# --------------------------------------------------------------------------- #


def test_handover_item_carries_the_oi_raiser(rs):
    _client, world = rs
    setup = _Setup(world)
    _inquiry, row = setup.oi(setup.agnes, "ZZT-RAISER-ITEM")
    assert setup.item(row)["raised_by"] == setup.agnes


def test_route_groups_split_by_matching_rows(rs):
    from app.services.project_order_inquiry_service import handover_route_groups

    _client, world = rs
    setup = _Setup(world)
    _a, agnes_row = setup.oi(setup.agnes, "ZZT-AGNES-1")
    _b, bob_row = setup.oi(setup.bob, "ZZT-BOB-1")
    _c, carol_row = setup.oi(setup.carol, "ZZT-CAROL-1")
    items = [setup.item(r) for r in (bob_row, agnes_row, carol_row)]

    groups = handover_route_groups(world.db, items)

    codes = sorted(sorted(i["item_code"] for i in g) for g in groups)
    assert codes == [["ZZT-AGNES-1"], ["ZZT-BOB-1", "ZZT-CAROL-1"]]


def test_route_groups_fill_a_missing_raiser_from_the_oi(rs):
    from app.services.project_order_inquiry_service import handover_route_groups

    _client, world = rs
    setup = _Setup(world)
    _a, agnes_row = setup.oi(setup.agnes, "ZZT-AGNES-FILL")
    item = setup.item(agnes_row)
    item.pop("raised_by", None)
    (group,) = handover_route_groups(world.db, [item])
    assert group[0]["raised_by"] == setup.agnes


def test_route_groups_keep_the_class_split(rs):
    """DEALER-OI-ROUTE unchanged: retail and project lines never share an email, even when
    they match the same (unconditioned) row."""
    from app.services.project_order_inquiry_service import handover_route_groups

    _client, world = rs
    setup = _Setup(world)
    _row_automation(world.db, setup.template, world.requester, name="legacy",
                    recipient=setup.eling)
    world.db.commit()
    _a, bob_row = setup.oi(setup.bob, "ZZT-BOB-P")
    _c, carol_row = setup.oi(setup.carol, "ZZT-CAROL-R")
    bob, carol = setup.item(bob_row), setup.item(carol_row)
    carol["sales_order_class"] = "retail"
    groups = handover_route_groups(world.db, [bob, carol])
    assert len(groups) == 2


def test_one_commit_sends_each_line_once_through_its_own_row(rs):
    """R3/R4: Agnes' lines only through her row, Bob's and Carol's together through Eling's,
    and no row fires twice."""
    from app.services.project_order_inquiry_service import send_handover_groups

    _client, world = rs
    setup = _Setup(world)
    _a, agnes_row = setup.oi(setup.agnes, "ZZT-AGNES-2")
    _b, bob_row = setup.oi(setup.bob, "ZZT-BOB-2")
    _c, carol_row = setup.oi(setup.carol, "ZZT-CAROL-2")
    items = [setup.item(r) for r in (agnes_row, bob_row, carol_row)]

    send_handover_groups(world.db, items, store_excel=False)

    runs = _runs_by_automation(world.db)
    assert set(runs) == {str(setup.eling_row.id), str(setup.agnes_row.id)}
    (eling_body,) = runs[str(setup.eling_row.id)]
    (agnes_body,) = runs[str(setup.agnes_row.id)]
    assert "ZZT-AGNES-2" in agnes_body
    assert "ZZT-BOB-2" not in agnes_body and "ZZT-CAROL-2" not in agnes_body
    assert "ZZT-BOB-2" in eling_body and "ZZT-CAROL-2" in eling_body
    assert "ZZT-AGNES-2" not in eling_body


def test_a_row_with_no_raiser_condition_still_gets_every_line(rs):
    """R7: an unconditioned row matches every raiser; Agnes' line goes to it and to her
    row in ONE email each, never twice to the same row."""
    from app.services.project_order_inquiry_service import send_handover_groups

    _client, world = rs
    setup = _Setup(world)
    legacy = _row_automation(world.db, setup.template, world.requester, name="legacy",
                             recipient=setup.eling, conditions=_class_rule("project"))
    world.db.commit()
    _a, agnes_row = setup.oi(setup.agnes, "ZZT-AGNES-3")
    _b, bob_row = setup.oi(setup.bob, "ZZT-BOB-3")

    send_handover_groups(world.db, [setup.item(agnes_row), setup.item(bob_row)],
                         store_excel=False)

    runs = _runs_by_automation(world.db)
    legacy_bodies = runs[str(legacy.id)]
    # Agnes' group {agnes, legacy} and Bob's group {eling, legacy}: legacy gets each line
    # exactly once.
    assert sum(b.count("ZZT-AGNES-3") > 0 for b in legacy_bodies) == 1
    assert sum(b.count("ZZT-BOB-3") > 0 for b in legacy_bodies) == 1
    assert len(runs[str(setup.agnes_row.id)]) == 1
    assert len(runs[str(setup.eling_row.id)]) == 1


# --------------------------------------------------------------------------- #
# R5: undo                                                                    #
# --------------------------------------------------------------------------- #


def test_undo_context_carries_the_raiser():
    from app.services.project_order_inquiry_service import _build_undo_context

    context, _source = _build_undo_context(
        [{"decision_id": "d", "so_number": "SO1", "sales_order_class": "project",
          "raised_by": "agnes", "lines": []}]
    )
    assert context["raised_by"] == "agnes"


def test_undo_of_agnes_order_goes_through_her_row_only(rs):
    from app.services.automation_service import AutomationService

    _client, world = rs
    db = world.db
    agnes, bob = _user(db, "ZZT Agnes U"), _user(db, "ZZT Bob U")
    eling, team = _user(db, "ZZT Eling U"), _user(db, "ZZT Team U")
    template = _template(db)
    eling_row = _row_automation(db, template, world.requester, name="eling-undo",
                                trigger=UNDONE, recipient=eling,
                                conditions=_rule("not_in", [agnes]))
    agnes_row = _row_automation(db, template, world.requester, name="agnes-undo",
                                trigger=UNDONE, recipient=team,
                                conditions=_rule("in", [agnes]))
    db.commit()
    for raiser in (agnes, bob):
        AutomationService(db).dispatch_event(
            UNDONE,
            context={"sales_order_class": "project", "raised_by": raiser, "undo": {}},
            source_kind=UNDONE,
            source_id=str(uuid.uuid4()),
        )
    runs = _runs_by_automation(db, UNDONE)
    assert len(runs[str(agnes_row.id)]) == 1
    assert len(runs[str(eling_row.id)]) == 1


def test_record_undo_stamps_the_oi_raiser(rs):
    from app.services.project_order_inquiry_service import (
        _UNDO_PENDING_KEY,
        ProjectOrderInquiryService,
    )

    _client, world = rs
    setup = _Setup(world)
    inquiry, _row_ = setup.oi(setup.agnes, "ZZT-UNDO-STAMP")
    service = ProjectOrderInquiryService(world.db)
    service._record_undo(
        pso_id=str(inquiry.project_sales_order_id),
        decision_id=_uid(),
        revision_no=1,
        lines=[],
        actor_user_id=world.requester,
    )
    item = world.db.info[_UNDO_PENDING_KEY][-1]
    world.db.info.pop(_UNDO_PENDING_KEY, None)
    assert item["raised_by"] == setup.agnes


# --------------------------------------------------------------------------- #
# R6: Send to purchasing uses the same matching                               #
# --------------------------------------------------------------------------- #


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def test_resend_preview_for_agnes_goes_to_her_row_not_the_oldest(rs):
    client, world = rs
    setup = _Setup(world)
    agnes_oi, _r = setup.oi(setup.agnes, "ZZT-RS-AGNES")
    bob_oi, _r2 = setup.oi(setup.bob, "ZZT-RS-BOB")

    agnes = _ok(client.post(PREVIEW, json={"inquiry_ids": [agnes_oi.id]}))
    assert [e["to"]["name"] for e in agnes["emails"]] == ["ZZT Agnes Team"]
    bob = _ok(client.post(PREVIEW, json={"inquiry_ids": [bob_oi.id]}))
    assert [e["to"]["name"] for e in bob["emails"]] == ["ZZT Eling"]


def test_resend_send_goes_through_every_matching_row_once(rs):
    client, world = rs
    setup = _Setup(world)
    legacy = _row_automation(world.db, setup.template, world.requester, name="legacy",
                             recipient=setup.eling, conditions=_class_rule("project"))
    world.db.commit()
    agnes_oi, _r = setup.oi(setup.agnes, "ZZT-RS-AGNES-2")
    bob_oi, _r2 = setup.oi(setup.bob, "ZZT-RS-BOB-2")

    preview = _ok(client.post(PREVIEW, json={"inquiry_ids": [agnes_oi.id, bob_oi.id]}))
    assert preview["inquiry_total"] == 2
    assert len(preview["emails"]) == 4

    result = _ok(client.post(SEND, json={"inquiry_ids": [agnes_oi.id, bob_oi.id]}))
    assert result["skipped"] == []
    assert result["emails_sent"] == 4

    runs = _runs_by_automation(world.db)
    assert [("ZZT-RS-AGNES-2" in b) for b in runs[str(setup.agnes_row.id)]] == [True]
    assert [("ZZT-RS-BOB-2" in b) for b in runs[str(setup.eling_row.id)]] == [True]
    assert sorted(
        "AGNES" if "ZZT-RS-AGNES-2" in b else "BOB" for b in runs[str(legacy.id)]
    ) == ["AGNES", "BOB"]


def test_resend_with_rows_off_falls_back_to_the_oldest_passing_row(rs):
    """Unchanged fallback: nothing enabled, so the oldest switched-off row that passes for
    this OI, and only that one."""
    client, world = rs
    setup = _Setup(world)
    setup.eling_row.enabled = False
    setup.agnes_row.enabled = False
    world.db.commit()
    agnes_oi, _r = setup.oi(setup.agnes, "ZZT-RS-OFF")
    body = _ok(client.post(PREVIEW, json={"inquiry_ids": [agnes_oi.id]}))
    assert [e["to"]["name"] for e in body["emails"]] == ["ZZT Agnes Team"]
    assert body["automation_enabled"] is False


def test_detail_names_the_raiser_not_the_id(rs):
    """No ids in the UI: the automation detail's condition text reads the person's name."""
    from app.rule_engine.prose import tree_text
    from app.rule_engine.registry import fact_map
    from app.services import automation_triggers

    _client, world = rs
    agnes = _user(world.db, "ZZT Agnes Prose")
    facts = fact_map(automation_triggers.fact_sources_for(HANDOVER))
    text = tree_text(_rule("not_in", [agnes]), facts, world.db)
    assert text == "Sales order class is Project AND Raised by is none of ZZT Agnes Prose"
