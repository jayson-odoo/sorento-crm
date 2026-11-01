"""AGENTIC-UNIFY PR 4, slice 1 (red): the labels (AC-8) and the read-only allow-list (AC-7, first half).

`agent_tool_labels()` is reached through the module at call time. The stored `chatbot_router` prompt is the
published text Jev reads; only the list sent in the call changes, never the stored row.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.agent import loop as agent_loop
from app.services.chatbot.agent import tools as agent_tools
from tests._pg_fixture import blank_session
from tests.chatbot.agent._ported_reads_support import (
    AC1_NAMES,
    CAPABILITIES,
    FIND,
    PORTED_NAMES,
    ported_reads,
)

# Fixtures and helpers from the router suites (fixtures must live in this namespace to be found).
from tests.chatbot.agent.test_router import (  # noqa: F401
    _fresh_prompt_cache,
    jev,
    route,
    set_jev_key,
)
from tests.chatbot.agent.test_router_tool_labels import publish_criteria, stored_prompt  # noqa: F401
from tests.chatbot.agent._seed import seed_agent_contact


@pytest.fixture(scope="module")
def db():
    """One blank schema for the module; every test seeds its own uniquely named users."""
    with blank_session() as session:
        yield session


def router_labels() -> list[str]:
    from app.services.chatbot import router

    return router.agent_tool_labels()


def label_of(name: str) -> str:
    label = agent_tools.TOOL_LABELS.get(name)
    assert label and label.strip(), f"{name} has no entry in TOOL_LABELS"
    return label


# ------------------------------------------------------------------ AC-8


@pytest.mark.parametrize("name", AC1_NAMES)
def test_AC8_every_tool_in_the_document_has_a_plain_label(name):
    label = label_of(name)
    assert "crm_" not in label, f"{name} label shows a tool name: {label!r}"


def test_AC8_the_new_labels_are_distinct_from_each_other_and_from_every_other_label():
    ours = {name: label_of(name) for name in AC1_NAMES}
    assert len(set(ours.values())) == len(ours), ours
    others = {label for name, label in agent_tools.TOOL_LABELS.items() if name not in ours}
    clashes = set(ours.values()) & others
    assert not clashes, f"a ported label repeats an existing one: {clashes}"


def test_AC8_agent_tool_labels_holds_the_label_of_every_ported_read():
    labels = router_labels()
    assert sorted(ported_reads()) == sorted(PORTED_NAMES)
    for name in PORTED_NAMES:
        assert label_of(name) in labels, f"{name} is not told to Jev"


def test_AC8_agent_tool_labels_holds_neither_find_nor_capabilities():
    labels = router_labels()
    assert label_of(FIND) not in labels
    assert label_of(CAPABILITIES) not in labels


def test_AC8_the_list_has_no_repeats_and_keeps_the_existing_labels():
    labels = router_labels()
    assert len(labels) == len(set(labels))
    for existing in ("your customer asks", "approve or reject a purchase request", "your ideas"):
        assert existing in labels


def test_AC8_the_labels_reach_jev_and_the_stored_router_prompt_is_not_modified(db, jev):
    contact = seed_agent_contact(db)
    set_jev_key(db)
    publish_criteria(db, {"chat": {"what": "c"}, "agent": {"what": "a"}})
    before = stored_prompt(db)
    route(db, contact["respond_id"])
    db.expire_all()
    sent = jev.calls[0]["criteria"]["agent"]["tools"]
    for name in PORTED_NAMES:
        assert label_of(name) in sent, f"{name} did not reach Jev"
    assert label_of(FIND) not in sent and label_of(CAPABILITIES) not in sent
    assert stored_prompt(db) == before


def test_AC8_a_user_missing_the_slug_gets_the_label_in_the_outside_access_line(db):
    for name in PORTED_NAMES + [FIND]:
        text = agent_loop._system_prompt(db, "ZZT User", tool_names=())
        assert label_of(name) in text.split("Outside this user's or this contact's access:")[-1], name


def test_AC8_a_tool_the_user_holds_is_left_out_of_the_outside_access_line(db):
    held = ("crm_complaints_list", "crm_projects_list")
    text = agent_loop._system_prompt(db, "ZZT User", tool_names=held)
    tail = text.split("Outside this user's or this contact's access:")[-1].split("When asked about these")[0]
    for name in held:
        assert label_of(name) not in tail
    assert label_of("crm_complaint_analytics") in tail


# ------------------------------------------------------------------ AC-7: the read-only allow-list


@pytest.mark.parametrize("name", AC1_NAMES)
def test_AC7_each_read_is_in_the_chatbot_read_only_set(name):
    from app.services.chatbot.lanes.business.fetch import CHATBOT_READ_ONLY_TOOLS, ensure_read_only

    assert name in CHATBOT_READ_ONLY_TOOLS
    ensure_read_only(name)


@pytest.mark.parametrize("name", AC1_NAMES)
def test_AC7_each_read_has_a_brand_scope_decision(name):
    from app.services.chatbot import contracts

    assert name in contracts.BRAND_SCOPE_TREATMENT
