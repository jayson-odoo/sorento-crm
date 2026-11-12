"""AGENTIC-UNIFY PR 4, AC-0: every tool of this PR is offered on a staff-principal (panel) turn only.

Crew ruling on the security review, 2 Nov: on a console or WhatsApp turn the route runs as the shared key, so the
agent's one slug was the only guard and it missed per-route rules. So the twelve reads, `crm_find`,
the two finds and the three writes are, on any other turn (a console operator, a linked user, a contact principal),
all holding the slug:

- not in the turn's tool list;
- refused at call time, with no route or MCP call;
- not sent to Jev as a label;
- not named in the prompt's "Outside this user's or this contact's access" line, so that prompt is what main sends.

On a staff-principal turn the same tools are offered. Real role rows on the blank Postgres schema throughout.
"""
from __future__ import annotations

import dataclasses
import uuid

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.user import User
from app.services.chatbot import router
from app.services.chatbot.agent import loop as agent_loop
from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent import writes
from app.services.chatbot.agent.access import AgentContext, permitted_tools
from app.services.company_scope import register_company_scope_listeners
from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS, staff_reveal_keys
from tests._pg_fixture import blank_session
from tests.chatbot.agent._ported_reads_support import (
    AC1,
    AC1_NAMES,
    LOCAL_PORTED,
    EXTRA_SLUGS,
    PORTED_NAMES,
    Recorder,
    dispatch,
    make_ctx,
    panel_ctx,
    panel_turn,
    tool,
)
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.agent.test_ported_writes import (
    CANCEL, CLOSE, CLOSE_SLUG, ORDERS_VIEW, TICKET, TICKET_SLUG, make_complaint,
)
from tests.chatbot.agent.test_ported_writes import make_order, make_world

FINDS = ["crm_complaints_find", "crm_projects_find"]
WRITE_NAMES = [CLOSE, CANCEL, TICKET]
#: Every tool that did not exist before this PR.
NEW_NAMES = frozenset([*AC1_NAMES, *LOCAL_PORTED, *FINDS, *WRITE_NAMES])
TURNS = ["operator", "linked_user", "contact_principal"]
LABEL_MARK = "Outside this user's or this contact's access:"

EVERY_SLUG = tuple(
    dict.fromkeys(
        [slug for _n, slug, _own in AC1]
        + [own for _n, _s, own in AC1 if own]
        + [s for extra in EXTRA_SLUGS.values() for s in extra]
        + [
            "complaint_management.complaints.view",
            "complaint_management.complaints.view_own",
            "projects.projects.view",
            "projects.projects.view_own",
            CLOSE_SLUG,
            ORDERS_VIEW,
            TICKET_SLUG,
        ]
    )
)


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


@pytest.fixture(scope="module")
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(scope="module")
def world(db):
    """A user who holds every slug of every tool, and an operator who holds them too."""
    user_id = seed_user(db, contact_pk=None, slugs=EVERY_SLUG)
    operator_id = seed_user(db, contact_pk=None, slugs=EVERY_SLUG)
    db.commit()
    return type("W", (), {"user": user_id, "operator": operator_id})


def read_ctx(db, world, kind: str) -> AgentContext:
    keys = staff_reveal_keys(db, world.user)
    base = make_ctx(world.user, grants=keys)
    if kind == "operator":
        return dataclasses.replace(base, operator_user_id=world.operator)
    if kind == "linked_user":
        return base
    return dataclasses.replace(
        base, user_id="", principal="contact", access_codes=frozenset({"dealer"}),
        grants=frozenset(key for key, _label in FIELD_REVEAL_KEYS),
    )


# ------------------------------------------------------------------ the twelve reads


@pytest.mark.parametrize("kind", TURNS)
@pytest.mark.parametrize("name", AC1_NAMES)
def test_AC0_a_read_is_not_offered_and_is_refused_off_the_panel(db, world, kind, name):
    ctx = read_ctx(db, world, kind)
    assert agent_tools.user_may_use(db, ctx, tool(name)) is False
    assert name not in [t.name for t in permitted_tools(db, ctx)]
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == [], "the route was reached on a turn that is not a panel turn"


@pytest.mark.parametrize("name", AC1_NAMES)
def test_AC0_the_same_read_is_offered_and_called_on_a_staff_principal_turn(db, world, name):
    ctx = panel_ctx(db, world.user)
    rec = Recorder()
    with panel_turn(world.user):
        assert agent_tools.user_may_use(db, ctx, tool(name)) is True
        assert name in [t.name for t in permitted_tools(db, ctx)]
        out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "ok", (out.status, out.message)
    assert [c[0] for c in rec.calls] == [name]


@pytest.mark.parametrize("name", PORTED_NAMES)
def test_AC0_an_operator_on_the_console_is_refused_even_when_the_linked_user_and_operator_hold_the_slug(
    db, world, name
):
    ctx = read_ctx(db, world, "operator")
    rec = Recorder()
    out = dispatch(db, ctx, name, rec=rec)
    assert out.status == "denied" and rec.calls == [], (out.status, out.message)


# ------------------------------------------------------------------ the two finds


@pytest.mark.parametrize("kind", TURNS)
@pytest.mark.parametrize("name", FINDS)
def test_AC0_a_find_is_not_offered_and_does_not_run_off_the_panel(db, world, monkeypatch, kind, name):
    ctx = read_ctx(db, world, kind)
    assert name in writes.USER_READS, f"{name} is not in writes.USER_READS"
    ran: list = []
    spy = dataclasses.replace(writes.USER_READS[name], run=lambda d, c, a: ran.append(a) or pytest.fail("ran"))
    monkeypatch.setitem(writes.USER_READS, name, spy)
    assert name not in [r.name for r in writes.permitted_user_reads(db, ctx)]
    out = writes.run_user_read(db, ctx, name, {"query": "ZZT-X-1"}, set())
    assert out.status == "denied", (out.status, out.message)
    assert ran == [], "the find ran on a turn that is not a panel turn"


@pytest.mark.parametrize("name", FINDS)
def test_AC0_a_find_is_offered_on_a_staff_principal_turn(db, world, name):
    ctx = make_ctx(world.user)
    with panel_turn(world.user):
        assert name in [r.name for r in writes.permitted_user_reads(db, ctx)]


# ------------------------------------------------------------------ the three writes


def write_args(db, name):
    if name == CLOSE:
        row = make_complaint(db)
        return {"complaint_id": row.id}, {row.id.lower()}
    if name == CANCEL:
        return {"order_number": make_order(db).order_number}, set()
    return {"title": f"ZZT ticket {uuid.uuid4().hex[:8]}"}, set()


@pytest.mark.parametrize("kind", TURNS)
@pytest.mark.parametrize("name", WRITE_NAMES)
def test_AC0_a_write_is_not_offered_and_is_refused_at_proposal_off_the_panel(db, kind, name):
    w = make_world(db, CLOSE_SLUG, ORDERS_VIEW, TICKET_SLUG)
    operator = seed_user(db, contact_pk=None, slugs=(CLOSE_SLUG, ORDERS_VIEW, TICKET_SLUG))
    from tests.chatbot.agent.test_ported_writes import console_ctx

    ctx = console_ctx(db, w)
    if kind == "operator":
        ctx = dataclasses.replace(ctx, operator_user_id=operator)
    elif kind == "contact_principal":
        ctx = dataclasses.replace(ctx, user_id="", principal="contact", access_codes=frozenset({"dealer"}))
    args, seen = write_args(db, name)
    assert name in writes.WRITES, f"{name} is not in writes.WRITES"
    assert name not in [d.name for d in writes.permitted_writes(db, ctx)]
    res, step = writes.propose_step(db, ctx, name, args, seen_ids=seen)
    assert step is None and res.status == "denied", (res.status, res.message)


@pytest.mark.parametrize("name", WRITE_NAMES)
def test_AC0_a_write_is_offered_and_proposed_on_a_staff_principal_turn(db, name):
    from tests.chatbot.agent.test_ported_writes import ctx_of, panel

    w = make_world(db, CLOSE_SLUG, ORDERS_VIEW, TICKET_SLUG)
    args, seen = write_args(db, name)
    with panel(db, w):
        ctx = ctx_of(db, w)
        assert name in [d.name for d in writes.permitted_writes(db, ctx)]
        res, step = writes.propose_step(db, ctx, name, args, seen_ids=seen)
    assert res.status == "proposed" and step is not None, (res.status, res.message)


# ------------------------------------------------------------------ the label sent to Jev


def label_of(name: str) -> str:
    label = agent_tools.TOOL_LABELS.get(name)
    assert label, f"{name} has no label"
    return label


#: The labels Jev is told of: the reads of `PORTED_READS`, the finds and the writes (not `crm_find`).
JEV_NAMES = [*PORTED_NAMES, *FINDS, *WRITE_NAMES]


def test_AC0_off_the_panel_no_label_of_this_pr_is_sent_to_jev(db, world):
    user = db.get(User, world.user)
    labels = router.agent_tool_labels(db, user)
    present = [name for name in JEV_NAMES if label_of(name) in labels]
    assert present == [], f"labels sent on a turn that is not a panel turn: {present}"


def test_AC0_off_the_panel_the_label_list_is_what_main_sends(db, world):
    """Every label that is left is the label of a tool that existed before this PR."""
    user = db.get(User, world.user)
    labels = router.agent_tool_labels(db, user)
    old = {label_of(n) for n in [*writes.WRITES, *writes.USER_READS] if n not in NEW_NAMES and n in agent_tools.TOOL_LABELS}
    assert set(labels) <= old, sorted(set(labels) - old)


def test_AC0_on_a_staff_principal_turn_the_labels_of_the_tools_it_holds_are_sent(db, world):
    user = db.get(User, world.user)
    with panel_turn(world.user):
        labels = router.agent_tool_labels(db, user)
    missing = [name for name in JEV_NAMES if label_of(name) not in labels]
    assert missing == [], f"labels missing on a panel turn: {missing}"


# ------------------------------------------------------------------ the "Outside this user's access" line


def left_out_line(text: str) -> str:
    assert LABEL_MARK in text, "the prompt has no outside-access line"
    return text.split(LABEL_MARK, 1)[1].split(". When asked about these", 1)[0].strip()


def main_left_out(names_held=()) -> str:
    """The line main builds: the labels of the tools that existed before this PR and are not held."""
    held = set(names_held)
    names = [*agent_tools.REGISTRY, *writes.USER_READS, *writes.WRITES]
    labels = [agent_tools.TOOL_LABELS[n] for n in names if n not in NEW_NAMES and n not in held and n in agent_tools.TOOL_LABELS]
    return "; ".join(dict.fromkeys(labels))


def test_AC0_off_the_panel_the_prompt_names_none_of_the_new_tools_and_equals_main(db):
    text = agent_loop._system_prompt(db, "ZZT User", tool_names=())
    assert left_out_line(text) == main_left_out()
    for name in NEW_NAMES:
        assert label_of(name) not in left_out_line(text), f"{name} is named in the outside-access line off the panel"


def test_AC0_off_the_panel_a_held_old_tool_is_still_dropped_from_the_line(db):
    held = ("crm_inventory_stock_balance_list", "crm_customer_asks_list")
    text = agent_loop._system_prompt(db, "ZZT User", tool_names=held)
    assert left_out_line(text) == main_left_out(held)


def test_AC0_off_the_panel_a_contact_prompt_is_unchanged(db):
    text = agent_loop._system_prompt(db, "ZZT User", tool_names=(), principal="contact")
    assert LABEL_MARK not in text


def test_AC0_on_the_panel_a_tool_the_user_lacks_is_named_in_the_line(db):
    with panel_turn(str(uuid.uuid4())):
        text = agent_loop._system_prompt(db, "ZZT User", tool_names=())
    tail = left_out_line(text)
    for name in NEW_NAMES:
        assert label_of(name) in tail, f"{name} is not named in the outside-access line on a panel turn"


def test_AC0_on_the_panel_a_tool_the_user_holds_is_left_out_of_the_line(db):
    held = ("crm_complaints_list", "crm_projects_find", CLOSE)
    with panel_turn(str(uuid.uuid4())):
        text = agent_loop._system_prompt(db, "ZZT User", tool_names=held)
    tail = left_out_line(text)
    for name in held:
        assert label_of(name) not in tail
    assert label_of("crm_complaint_analytics") in tail
