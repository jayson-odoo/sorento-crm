"""AGENTIC-IDEATE R1: routing reads the agent's tool labels (UAC AC-R1-1 to AC-R1-9).

Red tests, written before `router.agent_tool_labels` exists. The Jev call is always the
monkeypatched `jev_client.classify` fixture from test_router.py; no test touches the network.
Postgres only, through the blank schema; every test seeds its own contact chain.
`agent_tool_labels` is reached through the module at call time, never imported by name, so a
missing function fails only the tests that need it.
"""
from __future__ import annotations

import json

import pytest

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
from app.services.chatbot.agent import tools as agent_tools
from app.services.chatbot.agent import writes
from tests._pg_fixture import unique_code
from tests.chatbot.agent._seed import seed_agent_contact, seed_contact, seed_user

# Fixtures and helpers from the router suite (fixtures must live in this namespace to be found).
from tests.chatbot.agent.test_router import (  # noqa: F401
    INSTRUCTIONS,
    JEV_MODEL,
    OPEN_QUESTION_VARS,
    _fresh_prompt_cache,
    arm,
    db,
    jev,
    jev_answer,
    publish_router_prompt,
    route,
    seed_agent_turn,
    seed_proposal,
    set_jev_key,
    set_settings,
)

EXPECTED_LABELS = [
    "change a customer ask",
    "create an opportunity",
    "change an opportunity",
    "change a dealer contact",
    "approve or reject a purchase request",
    "take back a purchase request action",
    "submit a new idea or feature request",
    "change one of your ideas",
    "your customer asks",
    "recent changes",
    "your sales opportunities",
    "opportunity stages",
    "finding dealer contacts",
    "purchase requests and sponsorship forms",
    "your ideas",
]


def router_labels():
    from app.services.chatbot import router

    return router.agent_tool_labels()


def publish_criteria(db, criteria):
    publish_router_prompt(db, content={"instructions": INSTRUCTIONS, "criteria": criteria})


def stored_prompt(db):
    """The prompt rows as the database holds them now."""
    versions = sorted(
        (v.name, v.version, v.template) for v in db.query(AIPromptVersion).filter_by(name="chatbot_router")
    )
    labels = sorted(
        (l.name, l.label, str(l.version_id), l.provider, l.model)
        for l in db.query(AIPromptLabel).filter_by(name="chatbot_router")
    )
    return versions, labels


def new_write(name):
    return writes.WriteDef(
        name=name,
        user_permission="",
        schema={"type": "function", "function": {"name": name, "parameters": {"type": "object"}}},
        read_before=lambda db, user, args: {},
        summary=lambda args, before: "stub",
        execute=lambda db, user, args: {"id": "x", "after": {}},
        record_key="",
    )


def new_read(name):
    return writes.UserRead(
        name=name,
        user_permission="",
        schema={"type": "function", "function": {"name": name, "parameters": {"type": "object"}}},
        run=lambda db, ctx, args: None,
    )


# ------------------------------------------------------------------ AC-R1-1


def test_AC_R1_1_agent_criteria_gain_tools_and_nothing_else_changes(db, jev):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    criteria = {
        "chat": {"what": "single lookups", "examples": ["stock of X"]},
        "agent": {"what": "several reads combined", "also": "why and analysis"},
    }
    publish_criteria(db, criteria)
    route(db, contact["respond_id"])
    call = jev.calls[0]
    sent = call["criteria"]
    assert sent["agent"]["what"] == criteria["agent"]["what"]
    assert sent["agent"]["also"] == criteria["agent"]["also"]
    assert sent["agent"]["tools"] == router_labels()
    assert set(sent["agent"]) == {"what", "also", "tools"}
    assert sent["chat"] == criteria["chat"]
    assert set(sent) == {"chat", "agent"}
    assert call["instructions"] == INSTRUCTIONS
    assert call["model"] == JEV_MODEL


# ------------------------------------------------------------------ AC-R1-2


def test_AC_R1_2_stored_prompt_is_untouched_and_list_does_not_grow(db, jev):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
    before = stored_prompt(db)
    route(db, contact["respond_id"])
    route(db, contact["respond_id"])
    db.expire_all()
    assert stored_prompt(db) == before
    first, second = (c["criteria"]["agent"]["tools"] for c in jev.calls)
    assert first == second == router_labels()
    assert len(second) == len(set(second))


# ------------------------------------------------------------------ AC-R1-3


def test_AC_R1_3_new_write_tool_routes_without_a_prompt_edit(db, jev, monkeypatch):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
    before = stored_prompt(db)
    name = "crm_zzt_new_write"
    monkeypatch.setitem(writes.WRITES, name, new_write(name))
    monkeypatch.setitem(agent_tools.TOOL_LABELS, name, "zzt brand new write")
    route(db, contact["respond_id"])
    assert "zzt brand new write" in jev.calls[0]["criteria"]["agent"]["tools"]
    db.expire_all()
    assert stored_prompt(db) == before


def test_AC_R1_3_new_user_read_routes_without_a_prompt_edit(db, jev, monkeypatch):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
    before = stored_prompt(db)
    name = "crm_zzt_new_read"
    monkeypatch.setitem(writes.USER_READS, name, new_read(name))
    monkeypatch.setitem(agent_tools.TOOL_LABELS, name, "zzt brand new read")
    route(db, contact["respond_id"])
    assert "zzt brand new read" in jev.calls[0]["criteria"]["agent"]["tools"]
    db.expire_all()
    assert stored_prompt(db) == before


# ------------------------------------------------------------------ AC-R1-4


def test_AC_R1_4_snapshot_of_the_tool_labels():
    assert router_labels() == EXPECTED_LABELS, (
        "a tool was added or renamed, update this list and run the router gate on the PR"
    )


# ------------------------------------------------------------------ AC-R1-5


def test_AC_R1_5_every_agent_tool_has_a_plain_label():
    for name in [*writes.WRITES, *writes.USER_READS]:
        label = agent_tools.TOOL_LABELS.get(name)
        assert label and label.strip(), f"tool {name} has no label in TOOL_LABELS"
        assert "crm_" not in label, f"tool {name} has a label that shows a tool name: {label!r}"


def test_AC_R1_5_a_tool_without_a_label_is_left_out(monkeypatch):
    baseline = router_labels()
    name = "crm_zzt_unlabelled"
    monkeypatch.setitem(writes.WRITES, name, new_write(name))
    monkeypatch.setitem(writes.USER_READS, name + "_read", new_read(name + "_read"))
    assert agent_tools.TOOL_LABELS.get(name) is None
    assert router_labels() == baseline


# ------------------------------------------------------------------ AC-R1-6


def test_AC_R1_6_shared_lookup_labels_are_not_listed():
    labels = router_labels()
    assert "stock on hand" not in labels
    assert "incoming stock" not in labels
    for name in agent_tools.REGISTRY:
        label = agent_tools.TOOL_LABELS.get(name)
        if label:
            assert label not in labels, f"registry tool {name} label {label!r} is listed"


# ------------------------------------------------------------------ AC-R1-7


def test_AC_R1_7_the_list_is_not_filtered_per_user(db, jev):
    narrow = seed_agent_contact(db, slugs=())
    wide = seed_agent_contact(
        db,
        slugs=(
            "sales.customer_asks.view",
            "sales.customer_asks.edit",
            "sales.opportunities.add",
            "sales.opportunities.edit",
            "procurement.purchase_requests.approve",
        ),
    )
    set_jev_key(db)
    publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
    route(db, narrow["respond_id"])
    route(db, wide["respond_id"])
    assert len(jev.calls) == 2
    first, second = (c["criteria"]["agent"]["tools"] for c in jev.calls)
    assert first == second == router_labels()


# ------------------------------------------------------------------ AC-R1-8


def test_AC_R1_8_string_agent_criterion_becomes_an_object(db, jev):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    publish_criteria(db, {"chat": "single lookups", "agent": "several reads combined"})
    route(db, contact["respond_id"])
    sent = jev.calls[0]["criteria"]
    assert sent["agent"] == {"what": "several reads combined", "tools": router_labels()}
    assert sent["chat"] == "single lookups"


def test_AC_R1_8_no_agent_key_is_not_invented(db, jev):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    criteria = {"chat": {"what": "single lookups"}}
    publish_criteria(db, criteria)
    route(db, contact["respond_id"])
    assert jev.calls[0]["criteria"] == criteria


def test_AC_R1_8_published_tools_key_is_replaced(db, jev):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a", "tools": ["stale label"]}})
    route(db, contact["respond_id"])
    sent = jev.calls[0]["criteria"]["agent"]
    assert sent["tools"] == router_labels()
    assert "stale label" not in sent["tools"]
    assert sent["what"] == "a"


# ------------------------------------------------------------------ AC-R1-9


@pytest.mark.parametrize(
    "setup, side, reason",
    [
        ("ineligible", "chat", "not_eligible:switch_off"),
        ("media", "chat", "media"),
        ("pending", "agent", "pending_action"),
        ("open_question", "chat", "open_question"),
        ("daily_cap", "chat", "daily_cap"),
        ("text_length", "chat", "text_length"),
        ("no_key", "chat", "router_failed:no_key"),
        ("no_prompt", "chat", "router_failed:no_prompt"),
    ],
)
def test_AC_R1_9_routes_that_end_before_jev_are_unchanged_and_make_no_call(db, jev, setup, side, reason):
    kwargs = {}
    if setup == "ineligible":
        contact = seed_contact(db, agent_enabled=False)
        seed_user(db, contact_pk=contact["pk"])
        arm(db)
    else:
        contact = seed_agent_contact(db)
        if setup == "no_key":
            publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
        elif setup == "no_prompt":
            set_jev_key(db)
        else:
            set_jev_key(db)
            publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
        if setup == "media":
            kwargs["has_media"] = True
        elif setup == "pending":
            seed_proposal(db, contact)
        elif setup == "open_question":
            kwargs["session_vars"] = OPEN_QUESTION_VARS
        elif setup == "daily_cap":
            from datetime import datetime, timezone

            set_settings(db, chatbot_agent_daily_turns=1)
            seed_agent_turn(db, contact["respond_id"], created_at=datetime.now(timezone.utc))
            db.commit()
        elif setup == "text_length":
            kwargs["text_"] = "x" * 4001
    decision = route(db, contact["respond_id"], **kwargs)
    assert (decision.side, decision.reason) == (side, reason)
    assert jev.calls == []


def test_AC_R1_9_a_jev_failure_still_goes_to_chat(db, jev):
    from app.services.chatbot.jev_client import JevError

    contact = seed_agent_contact(db)
    set_jev_key(db)
    publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
    jev.error = JevError("timeout")
    decision = route(db, contact["respond_id"])
    assert (decision.side, decision.reason) == ("chat", "router_failed:timeout")
    assert len(jev.calls) == 1
