"""AGENT-COMMISSION-WA: the last two places #2242 read the user's message text (crew code check on 86e1d873, owner
rule 4 Oct + 28 Oct: understanding is semantic only, never a keyword, regex or substring over the message).

- `strip_self_agent` decided "the user means themselves" from a my / me / mine / saya regex and a substring of the
  message. Now the model says it: `crm_query` `about_self` (true when the user asks about their own figures, in any
  language, or names themselves). Code only compares the call's agent with the asker's stored name.
- `_user_named` decided "the user named this" from a substring of the message. It is gone: a named call is the
  user's (the model passes `agent` as the user said it, and the asker's own name is stripped before the call runs).
"""
from __future__ import annotations

import inspect

import pytest

from tests.chatbot.agent.test_ai_tools_wave2 import grant, refused, run, targets  # noqa: F401  (fixtures)
from tests.test_sales_targets_s1 import api, world  # noqa: F401  (fixtures)

ENTITY = "agent_target_summary"


def test_S1_neither_function_reads_the_message():
    from app.services.chatbot.agent import query_tools

    assert "user_text" not in inspect.signature(query_tools.strip_self_agent).parameters
    assert not hasattr(query_tools, "_user_named")


@pytest.mark.parametrize("value", ["Jayson", "teh jayson", "Jayson Teh", "JAYSON", "Teh"])
def test_S2_the_askers_own_name_is_dropped_unless_the_model_says_the_question_is_about_them(value):
    from app.services.chatbot.agent.query_tools import strip_self_agent

    kept, note = strip_self_agent({"entity": ENTITY, "agent": value, "period": "2026"}, "Jayson Teh")
    assert "agent" not in kept and kept["period"] == "2026" and note
    mine, note = strip_self_agent({"entity": ENTITY, "agent": value, "about_self": True}, "Jayson Teh")
    assert mine["agent"] == value and note is None


def test_S3_a_name_filter_is_dropped_the_same_way_and_someone_else_is_never_dropped():
    from app.services.chatbot.agent.query_tools import strip_self_agent

    filt = {"entity": ENTITY, "filters": [{"field": "owner", "op": "eq", "value": "jayson teh"},
                                          {"field": "owner_kind", "op": "eq", "value": "dealer"}]}
    kept, note = strip_self_agent(filt, "Jayson Teh")
    assert kept["filters"] == [{"field": "owner_kind", "op": "eq", "value": "dealer"}] and note
    for other in ("Agent B", "Jayson Lim"):
        kept, note = strip_self_agent({"entity": ENTITY, "agent": other}, "Jayson Teh")
        assert kept["agent"] == other and note is None


def test_S4_about_self_is_a_query_argument_any_entity_accepts_and_a_boolean(targets):
    db, _c, _t = targets
    assert "rows" in run(db, {"entity": ENTITY, "agent": "Agent A", "about_self": True, "period": "2026-10"})
    assert "rows" in run(db, {"entity": "target_list", "about_self": False, "period": "2026-10"})
    assert "about_self" in refused(db, {"entity": ENTITY, "about_self": "yes"}).message


def test_S5_the_tool_says_when_to_set_it():
    from app.services.chatbot.agent.query_tools import QUERY_SCHEMA

    prop = QUERY_SCHEMA["function"]["parameters"]["properties"]["about_self"]
    assert prop["type"] == "boolean"
    said = prop["description"].lower()
    assert "own" in said and "any language" in said and "names themselves" in said


@pytest.mark.parametrize("said", ["payout to fullshun", "", "zzz", "komisen untuk fullshun"])
def test_S6_a_named_empty_call_hides_an_unasked_table_whatever_the_wording(said):
    """#2242 D2, now decided from the calls alone: the same calls give the same reply for any message."""
    from app.services.chatbot.agent.query_tools import shape_reply

    ledger = {
        "q1": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY, "agent": "fullshun"},
               "data": {"entity": ENTITY, "rows": [], "total": 0}, "display": None},
        "q2": {"name": "crm_query", "status": "ok", "args": {"entity": ENTITY},
               "data": {"entity": ENTITY, "shown_to_user": True, "total": 40}, "display": "WHOLE TABLE"},
    }
    text = shape_reply("No commission payout for fullshun this year.", ledger, user_text=said)
    assert "WHOLE TABLE" not in text and text.startswith("No commission payout for fullshun")


def test_S7_the_askers_own_name_stripped_before_the_call_never_hides_the_next_table():
    """#2242 K1 as the loop records it: the asker's name is stripped before dispatch, so the empty call names nobody
    and the per-dealer table of the second call shows."""
    from app.services.chatbot.agent.query_tools import shape_reply, strip_self_agent

    first, _note = strip_self_agent({"entity": ENTITY, "agent": "Jayson"}, "Jayson Teh")
    ledger = {
        "q1": {"name": "crm_query", "status": "ok", "args": first,
               "data": {"entity": ENTITY, "rows": [], "total": 0}, "display": None},
        "q2": {"name": "crm_query", "status": "ok",
               "args": {"entity": ENTITY, "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]},
               "data": {"entity": ENTITY, "shown_to_user": True, "total": 88}, "display": "DEALER TABLE"},
    }
    for said in ("commission payout per dealer this year", "komisen setiap dealer", ""):
        text = shape_reply("Total dealer payout this year is RM 478,755.53.", ledger, user_text=said)
        assert "DEALER TABLE" in text and text.startswith("Total dealer payout")
