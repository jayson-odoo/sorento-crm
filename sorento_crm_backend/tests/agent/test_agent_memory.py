"""AGENTIC-P1 card section 4: one continuous conversation per contact, with compaction.

Postgres via the blank schema. Turns are seeded with explicit `created_at` values because
every row in one test transaction would otherwise share `now()`.

Assumed digest shape (the contract says "name, key arguments, status"): each entry of
`response["tool_digest"]` is `{"name", "args", "status"}`.
"""
from __future__ import annotations

import pytest

from tests._pg_fixture import blank_session, unique_code
from tests.agent._turns import at, seed_turn


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def rid():
    return unique_code("mem")


def _long(n: int = 400) -> str:
    return "w" * n


# ------------------------------------------------------------------ conversations


def test_current_conversation_creates_then_reuses(db, rid):
    from app.models.chatbot_agent import AgentConversation
    from app.services.agent import memory

    first = memory.current_conversation(db, rid)
    again = memory.current_conversation(db, rid)

    assert isinstance(first, AgentConversation)
    assert first.id == again.id
    assert first.contact_respond_id == rid
    assert first.summary is None and first.summary_through is None
    assert db.query(AgentConversation).filter_by(contact_respond_id=rid).count() == 1


def test_new_conversation_becomes_the_current_one_and_nothing_is_deleted(db, rid):
    from app.models.chatbot_agent import AgentConversation
    from app.services.agent import memory

    old = memory.current_conversation(db, rid)
    fresh = memory.new_conversation(db, rid)

    assert fresh.id != old.id
    assert memory.current_conversation(db, rid).id == fresh.id
    assert db.query(AgentConversation).filter_by(contact_respond_id=rid).count() == 2


def test_conversations_are_per_contact(db, rid):
    from app.services.agent import memory

    a = memory.current_conversation(db, rid)
    b = memory.current_conversation(db, unique_code("other"))
    assert a.id != b.id


def test_the_next_turn_after_a_new_conversation_starts_empty(db, rid):
    from app.services.agent import memory

    old = memory.current_conversation(db, rid)
    seed_turn(db, old, minute=1, text="how much stock", reply="42 units")
    assert memory.history_messages(db, old) != []

    fresh = memory.new_conversation(db, rid)

    assert memory.history_messages(db, fresh) == []
    assert memory.conversation_turns(db, fresh) == []
    assert len(memory.conversation_turns(db, old)) == 1  # the old one is intact


# ------------------------------------------------------------------ turns and history


def test_conversation_turns_are_agent_ingress_of_this_conversation_oldest_first(db, rid):
    from app.services.agent import memory

    conv = memory.current_conversation(db, rid)
    t2 = seed_turn(db, conv, minute=2, text="second", reply="r2")
    t1 = seed_turn(db, conv, minute=1, text="first", reply="r1")
    seed_turn(db, conv, minute=3, text="console one", reply="x", ingress="console")
    other = memory.new_conversation(db, unique_code("elsewhere"))
    seed_turn(db, other, minute=4, text="not mine", reply="y")

    assert [t.id for t in memory.conversation_turns(db, conv)] == [t1.id, t2.id]


def test_history_has_user_and_assistant_messages_with_a_tools_digest(db, rid):
    from app.services.agent import memory

    conv = memory.current_conversation(db, rid)
    seed_turn(
        db,
        conv,
        minute=1,
        text="stock of SRTWT7445?",
        reply="There are 12 units.",
        digest=[{"name": "crm_inventory_stock_balance_list", "args": {"query": "SRTWT7445"}, "status": "ok"}],
    )

    msgs = memory.history_messages(db, conv)

    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "stock of SRTWT7445?"
    assert msgs[1]["content"].startswith("There are 12 units.")
    assert "[tools:" in msgs[1]["content"]
    assert "crm_inventory_stock_balance_list" in msgs[1]["content"]
    assert "ok" in msgs[1]["content"].split("[tools:")[1]


def test_history_includes_the_summary_line_then_only_turns_after_summary_through(db, rid):
    from app.services.agent import memory

    conv = memory.current_conversation(db, rid)
    seed_turn(db, conv, minute=1, text="folded one", reply="folded reply one")
    seed_turn(db, conv, minute=2, text="folded two", reply="folded reply two")
    seed_turn(db, conv, minute=3, text="kept three", reply="kept reply three")
    conv.summary = "User asked about SRTWT7445 stock on 2026-10-01."
    conv.summary_through = at(2)
    db.flush()

    msgs = memory.history_messages(db, conv)

    assert msgs[0] == {
        "role": "user",
        "content": "Summary of the earlier conversation: User asked about SRTWT7445 stock on 2026-10-01.",
    }
    joined = " ".join(m["content"] for m in msgs)
    assert "folded one" not in joined and "folded two" not in joined
    assert "kept three" in joined and "kept reply three" in joined
    assert [m["role"] for m in msgs] == ["user", "user", "assistant"]


# ------------------------------------------------------------------ compaction


def _seed_ten(db, conv, size=400):
    return [
        seed_turn(db, conv, minute=i, text=f"q{i} " + _long(size), reply=f"a{i} " + _long(size))
        for i in range(1, 11)
    ]


def test_below_the_threshold_nothing_changes(db, rid):
    from app.services.agent import memory

    conv = memory.current_conversation(db, rid)
    _seed_ten(db, conv)
    called = []

    def summarize(old, turns):
        called.append((old, turns))
        return "never"

    assert memory.maybe_compact(db, conv, summarize=summarize, threshold_tokens=10_000_000) is False
    assert called == []
    assert conv.summary is None and conv.summary_through is None


def test_above_the_threshold_folds_older_turns_and_keeps_the_last_six(db, rid):
    from app.services.agent import memory

    conv = memory.current_conversation(db, rid)
    turns = _seed_ten(db, conv)
    seen = {}

    def summarize(old, folded):
        seen["old"] = old
        seen["ids"] = [t.id for t in folded]
        return "SUMMARY: user asked q1 to q4."

    assert memory.maybe_compact(db, conv, summarize=summarize, threshold_tokens=500) is True

    assert seen["old"] in (None, "")
    assert seen["ids"] == [t.id for t in turns[:4]]
    assert conv.summary == "SUMMARY: user asked q1 to q4."
    assert conv.summary_through == turns[3].created_at
    assert conv.summary_tokens is not None and conv.summary_tokens > 0

    msgs = memory.history_messages(db, conv)
    assert msgs[0]["content"].startswith("Summary of the earlier conversation: SUMMARY")
    assert len(msgs) == 1 + 6 * 2  # the summary line, then the last six turns verbatim
    assert msgs[1]["content"].startswith("q5 ")


def test_a_second_compaction_folds_on_top_of_the_old_summary(db, rid):
    from app.services.agent import memory

    conv = memory.current_conversation(db, rid)
    turns = _seed_ten(db, conv)
    conv.summary = "OLD SUMMARY"
    conv.summary_through = turns[1].created_at  # turns 1-2 already folded
    db.flush()
    seen = {}

    def summarize(old, folded):
        seen["old"] = old
        seen["ids"] = [t.id for t in folded]
        return "NEW SUMMARY"

    assert memory.maybe_compact(db, conv, summarize=summarize, threshold_tokens=500) is True

    assert seen["old"] == "OLD SUMMARY"
    assert seen["ids"] == [t.id for t in turns[2:4]]  # verbatim part was 3..10; last six stay
    assert conv.summary == "NEW SUMMARY"
    assert conv.summary_through == turns[3].created_at


def test_a_summarizer_that_raises_changes_nothing_and_returns_false(db, rid):
    from app.services.agent import memory

    conv = memory.current_conversation(db, rid)
    _seed_ten(db, conv)

    def summarize(old, folded):
        raise RuntimeError("model down")

    assert memory.maybe_compact(db, conv, summarize=summarize, threshold_tokens=500) is False

    assert conv.summary is None
    assert conv.summary_through is None
    assert len(memory.history_messages(db, conv)) == 20


def test_too_few_turns_to_fold_is_a_no_op(db, rid):
    from app.services.agent import memory

    conv = memory.current_conversation(db, rid)
    for i in range(1, 5):
        seed_turn(db, conv, minute=i, text=_long(4000), reply=_long(4000))
    called = []

    def summarize(old, folded):
        called.append(1)
        return "x"

    assert memory.maybe_compact(db, conv, summarize=summarize, threshold_tokens=100) is False
    assert called == []
    assert conv.summary is None
