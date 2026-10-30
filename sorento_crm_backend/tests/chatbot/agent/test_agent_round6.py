"""AGENTIC-P1 round 6 (crew re-run, 20/30): red tests.

1 product find by description, 2 figures backed by any result or a column total, 3 the plan tool and
unanswered parts, 4 exact code with variants, 5 the contact's own ids out of the reply.
"""
from __future__ import annotations

import json
import re

import pytest

from app.models.user import SystemSetting
from tests.chatbot.agent.test_agent_round5 import (  # noqa: F401 - fixtures and helpers
    KIND_SLUGS,
    UUID_A,
    UUID_B,
    Rec,
    _dispatch,
    _results,
    held,
    hit,
    resolver,
)
from tests.chatbot.agent.test_agent_round5c import (  # noqa: F401
    CATALOG,
    Mcp,
    Provider,
    asks,
    call,
    db,
    run,
)
from tests.chatbot.agent._seed import seed_agent_contact
from tests.chatbot.agent.test_agent_round5e import (  # noqa: F401
    _brand,
    _codes,
    _find,
    _product,
    world,
)

@pytest.fixture()
def contact(db):
    return seed_agent_contact(
        db, slugs=("inventory.stock.view", "order_management.orders.view", KIND_SLUGS["product"])
    )


STOCK = "crm_inventory_stock_balance_list"
REPORT = "crm_report_ask"
PLAN = "plan"
ANSWER = "answer"
RESOLVE = "crm_resolve"


def answer6(text, *, figures=(), not_found=(), not_checked=(), answered=None, cid="a1"):
    args = {
        "text": text, "figures": [dict(f) for f in figures], "not_found": [dict(n) for n in not_found],
        "not_checked": list(not_checked),
    }
    if answered is not None:
        args["answered"] = list(answered)
    return asks(call(ANSWER, args, cid))


def plan_call(*parts, cid="p1"):
    return call(PLAN, {"parts": list(parts)}, cid)


def _budget(db, **cols):
    row = db.query(SystemSetting).first() or SystemSetting()
    db.add(row)
    for k, v in cols.items():
        setattr(row, k, v)
    db.flush()


def _tool_msgs(messages):
    return [json.loads(m["content"]) for m in messages if m.get("role") == "tool"]


# ------------------------------------------------------------------ 1. product find by description


def test_a_description_match_is_found_by_the_whole_phrase_and_by_one_word(db, world):
    hit_ = _product(db, code="ZZT-WC1", name="Closet one")
    hit_.description = "Kids BABY WC with soft seat"
    _product(db, code="ZZT-TAP", name="Basin tap")
    db.flush()
    assert _codes(_find(db, world, {"query": "baby wc"}, set())) == ["ZZT-WC1"]
    assert _codes(_find(db, world, {"query": "baby"}, set())) == ["ZZT-WC1"]


def test_every_word_must_match_somewhere_and_a_stray_word_pulls_nothing(db, world):
    both = _product(db, code="ZZT-BOTH", name="Closet")
    both.description = "baby wc"
    seat = _product(db, code="ZZT-SEAT", name="baby seat")
    wc_only = _product(db, code="ZZT-WCONLY", name="plain wc")
    db.flush()
    assert _codes(_find(db, world, {"query": "baby wc"}, set())) == ["ZZT-BOTH"]
    assert sorted(_codes(_find(db, world, {"query": "wc"}, set()))) == ["ZZT-BOTH", "ZZT-WCONLY"]
    # the words may sit in different fields of one product
    mixed = _product(db, code="ZZT-MIX", name="baby")
    mixed.description = "wc"  # a different field of the same product
    db.flush()
    assert "ZZT-MIX" in _codes(_find(db, world, {"query": "baby wc"}, set()))
    assert seat and wc_only


def test_exact_code_then_prefix_then_the_rest(db, world):
    _product(db, code="ZZT-BABY-ZZ", name="a baby thing")
    _product(db, code="ZZT-BABY", name="x")
    _product(db, code="ZZT-BABYWC", name="y")
    _product(db, code="AAA-LAST", name="baby")
    out = _find(db, world, {"query": "ZZT-BABY"}, set())
    assert _codes(out)[:2] == ["ZZT-BABY", "ZZT-BABY-ZZ"] or _codes(out)[0] == "ZZT-BABY"
    assert _codes(out)[0] == "ZZT-BABY"
    prefixes = [c for c in _codes(out) if c.startswith("ZZT-BABY")]
    assert _codes(out)[: len(prefixes)] == prefixes
    out = _find(db, world, {"query": "baby"}, set())
    assert _codes(out)[-1] == "AAA-LAST" or "AAA-LAST" in _codes(out)


# ------------------------------------------------------------------ 2. figures


def _run_figures(db, contact, text, result, *, figures=(), user_text="how is it?"):
    provider = Provider([asks(call(REPORT, {"query": "x", "basis": "invoiced"}, "c1")), answer6(text, figures=figures)])
    out = run(db, contact, provider, Mcp(result), text=user_text)
    return out, provider


REPORT_ENVELOPE = {
    "result_type": "report_ask",
    "response": "Sales by agent\nFANNY I 51\nWT I 40\nDelivered total 2,822",
    "has_result": True,
    "drill_rows": [{"agent": "FANNY I", "amount": 51}, {"agent": "WT I", "amount": 40}],
}


def test_report_rows_and_the_delivered_total_are_backed_when_not_cited(db, contact):
    text = "FANNY I has 51 and the delivered total is 2,822."
    result, provider = _run_figures(db, contact, text, REPORT_ENVELOPE)
    assert result.reply_text == text
    assert len(provider.seen) == 2


def test_a_figure_cited_to_a_different_call_is_still_backed(db, contact):
    text = "FANNY I has 51."
    result, provider = _run_figures(
        db, contact, text, REPORT_ENVELOPE, figures=[{"value": "51", "call_id": "some-other-call"}]
    )
    assert result.reply_text == text
    assert len(provider.seen) == 2


def test_a_column_total_of_the_returned_rows_is_backed(db, contact):
    rows = {"items": [{"qty": 4}, {"qty": 5}, {"qty": 6}], "has_result": True}
    result, provider = _run_figures(db, contact, "15 units in total.", rows)
    assert result.reply_text == "15 units in total."
    assert len(provider.seen) == 2


def test_a_column_total_over_the_field_rows_of_a_presenter_envelope_is_backed(db, contact):
    env = {
        "items": [
            {"fields": [{"key": "total", "label": "Total", "value": 4}]},
            {"fields": [{"key": "total", "label": "Total", "value": "6"}]},
        ],
        "has_result": True,
    }
    result, _ = _run_figures(db, contact, "10 in total.", env)
    assert result.reply_text == "10 in total."


def test_a_made_up_total_is_still_flagged(db, contact):
    rows = {"items": [{"qty": 4}, {"qty": 5}, {"qty": 6}], "has_result": True}
    provider = Provider(
        [asks(call(STOCK, {"query": "x"}, "c1")), answer6("9,999 units in total."), answer6("9,999 units in total.", cid="a2")]
    )
    result = run(db, contact, provider, Mcp(rows))
    assert "(not verified)" in result.reply_text and "9,999" not in result.reply_text


def test_headings_with_list_numbers_are_not_figures():
    from app.services.chatbot.agent.loop import unsupported_figures

    assert unsupported_figures("1. Stock\n2) Incoming\n10. Done", []) == []
    assert unsupported_figures("1. Stock has 9,999", []) == ["9,999"]


# ------------------------------------------------------------------ 3. plan


def test_the_plan_tool_is_offered_and_answer_has_answered(db, contact):
    provider = Provider([answer6("Hello.")])
    run(db, contact, provider, Mcp({}))
    tools = {t["function"]["name"]: t["function"] for t in provider.seen[0]["tools"]}
    assert PLAN in tools and set(tools[PLAN]["parameters"]["properties"]) == {"parts"}
    assert "answered" in tools[ANSWER]["parameters"]["properties"]


def test_a_part_not_answered_and_not_checked_is_listed(db, contact):
    provider = Provider(
        [
            asks(plan_call("stock of A", "stock of B", "incoming of A")),
            answer6("A and B are fine.", answered=["stock of A", "stock of B"]),
        ]
    )
    result = run(db, contact, provider, Mcp({}))
    assert result.reply_text.startswith("A and B are fine.")
    assert "I did not get to: incoming of A." in result.reply_text


def test_a_part_the_model_put_in_not_checked_is_not_listed_twice(db, contact):
    provider = Provider(
        [
            asks(plan_call("stock of A", "incoming of A")),
            answer6("A is fine.", answered=["stock of A"], not_checked=["incoming of A"]),
        ]
    )
    result = run(db, contact, provider, Mcp({}))
    assert "Not checked: incoming of A." in result.reply_text
    assert "I did not get to" not in result.reply_text


def test_two_open_parts_are_joined_and_all_answered_adds_nothing(db, contact):
    provider = Provider([asks(plan_call("a part", "b part", "c part")), answer6("Only a.", answered=["a part"])])
    result = run(db, contact, provider, Mcp({}))
    assert "I did not get to: b part; c part." in result.reply_text
    provider = Provider([asks(plan_call("a part", "b part")), answer6("Both.", answered=["a part", "b part"])])
    result = run(db, contact, provider, Mcp({}))
    assert result.reply_text == "Both."


def test_a_later_plan_replaces_the_earlier_one(db, contact):
    provider = Provider(
        [
            asks(plan_call("old one", "old two", cid="p1")),
            asks(plan_call("new one", cid="p2")),
            answer6("Done.", answered=["new one"]),
        ]
    )
    result = run(db, contact, provider, Mcp({}))
    assert result.reply_text == "Done."


def test_the_plan_call_is_not_a_chip_or_a_digest_entry(db, contact):
    provider = Provider([asks(plan_call("one", "two")), answer6("Done.", answered=["one", "two"])])
    result = run(db, contact, provider, Mcp({}))
    assert [c["name"] for c in result.tool_calls] == []
    reply = _tool_msgs(provider.seen[1]["messages"])[0]
    assert reply["status"] == "ok"


def test_a_bad_plan_is_invalid(db, contact):
    provider = Provider([asks(call(PLAN, {"parts": "not a list"}, "p1")), answer6("Done.")])
    run(db, contact, provider, Mcp({}))
    # the reply to the plan call is the second message list's only tool message
    assert _tool_msgs(provider.seen[1]["messages"])[0]["status"] == "invalid"


def test_on_a_limit_every_open_part_is_listed_even_with_a_not_checked_list(db, contact):
    _budget(db, chatbot_agent_max_rounds=1)
    provider = Provider(
        [
            asks(plan_call("part a", "part b", "part c"), call(STOCK, {"query": "x"}, "c1")),
            answer6("Part a done.", answered=["part a"], not_checked=["part b"]),
        ]
    )
    result = run(db, contact, provider, Mcp({"items": [{"qty": 1}], "has_result": True}))
    assert result.limit_hit == "rounds"
    assert "I did not get to: part b; part c." in result.reply_text


def test_without_a_plan_the_limit_sentence_stays(db, contact):
    _budget(db, chatbot_agent_max_rounds=1)
    provider = Provider([asks(call(STOCK, {"query": "x"}, "c1")), answer6("Partial.")])
    result = run(db, contact, provider, Mcp({"items": [{"qty": 1}], "has_result": True}))
    assert "I stopped at the rounds limit before finishing, so I did not check:" in result.reply_text
    assert "I did not get to" not in result.reply_text


# ------------------------------------------------------------------ 4. exact code with variants


def test_an_exact_code_is_found_and_the_variants_are_listed(held, resolver):
    held.add(KIND_SLUGS["product"])
    resolver.table = {
        "SRTWT7445": [hit("product", "SRTWT7445-LV", UUID_B), hit("product", "SRTWT7445", UUID_A)],
        "srtwc201": [hit("product", "SRTWC201", UUID_A), hit("product", "SRTWC201-X", UUID_B)],
    }
    out = _dispatch(RESOLVE, {"terms": ["SRTWT7445", "srtwc201"], "kinds": ["product"]}, Rec())
    rows = _results(out)
    one = rows["SRTWT7445"]
    assert one["status"] == "found"
    assert [m["id"] for m in one["matches"]] == [UUID_A]
    assert [v["code"] for v in one["variants"]] == ["SRTWT7445-LV"]
    two = rows["srtwc201"]
    assert two["status"] == "found" and two["matches"][0]["code"] == "SRTWC201"
    assert [v["code"] for v in two["variants"]] == ["SRTWC201-X"]


def test_without_an_exact_code_it_stays_ambiguous(held, resolver):
    held.add(KIND_SLUGS["product"])
    resolver.table = {"SRTWT7445": [hit("product", "SRTWT7445-A", UUID_A), hit("product", "SRTWT7445-B", UUID_B)]}
    row = _results(_dispatch(RESOLVE, {"terms": ["SRTWT7445"], "kinds": ["product"]}, Rec()))["SRTWT7445"]
    assert row["status"] == "ambiguous" and "variants" not in row


def test_variant_ids_are_known_ids_for_later_calls(db, contact, resolver):
    resolver.table = {"SRTWT7445": [hit("product", "SRTWT7445", UUID_A), hit("product", "SRTWT7445-LV", UUID_B)]}
    mcp = Mcp({"items": [{"qty": 1}], "has_result": True})
    provider = Provider(
        [
            asks(call(RESOLVE, {"terms": ["SRTWT7445"]}, "r1")),
            asks(call(STOCK, {"query": "x", "warehouse_ids": [UUID_B]}, "c2")),
            answer6("Done."),
        ]
    )
    run(db, contact, provider, mcp)
    assert [c[0] for c in mcp.calls] == [STOCK]


# ------------------------------------------------------------------ 5. the contact's own ids


def test_the_contacts_own_ids_are_out_of_the_reply(db, contact):
    rid = contact["respond_id"]
    provider = Provider([answer6(f"I checked for contact ID {rid} and contact {contact['pk']}.")])
    result = run(db, contact, provider, Mcp({}))
    assert rid not in result.reply_text and contact["pk"] not in result.reply_text
    assert "(id)" in result.reply_text


def test_the_echo_of_the_injected_guards_is_not_shown_to_the_model(db, contact):
    rid = contact["respond_id"]
    result_body = {
        "items": [{"qty": 3, "contact_id": rid}],
        "contact_id": rid,
        "space_id": "364817",
        "response": f"Stock for contact {rid}",
        "has_result": True,
    }
    provider = Provider([asks(call(STOCK, {"query": "x"}, "c1")), answer6("There are 3 units.")])
    run(db, contact, provider, Mcp(result_body))
    shown = json.dumps(_tool_msgs(provider.seen[1]["messages"])[0])
    assert rid not in shown
    assert '"qty": 3' in shown


# ------------------------------------------------------------------ round 6b


def _reply_after(db, contact, text, result):
    """The reply when the answer (no citations) is checked against one STOCK result, with one repair."""
    provider = Provider(
        [asks(call(STOCK, {"query": "x"}, "c1")), answer6(text), answer6(text, cid="a2")]
    )
    return run(db, contact, provider, Mcp(result), text="how is it?").reply_text


def test_bookkeeping_numbers_back_nothing(db, contact):
    products = {
        "items": [
            {"id": "11111111-2222-4333-8444-555555555555", "code": "ZZT-A", "name": "a", "brand": None, "category": "c"},
            {"id": "11111111-2222-4333-8444-555555555556", "code": "ZZT-B", "name": "b", "brand": None, "category": "c"},
        ],
        "more": 0,
        "has_result": True,
        "page": 1,
        "limit": 50,
        "total_count": 77,
        "score": 0.93,
    }
    reply = _reply_after(db, contact, "2 units in stock, 0 incoming", products)
    assert "0 incoming" not in reply and "(not verified) incoming" in reply
    assert "2 units in stock" in reply  # two product rows
    for key_number in ("50", "77", "0.93"):
        assert "(not verified)" in _reply_after(db, contact, f"There are {key_number} units.", products)


def test_a_name_with_a_number_does_not_back_a_quantity(db, contact):
    result = {"items": [{"name": "Basin 600", "product_name": "Basin 600 white", "label": "Size 600"}], "has_result": True}
    assert "(not verified)" in _reply_after(db, contact, "There are 600 units.", result)


def test_a_real_zero_quantity_still_backs_zero(db, contact):
    reply = _reply_after(db, contact, "There are 0 units.", {"items": [{"qty": 0, "name": "Basin"}], "has_result": True})
    assert reply == "There are 0 units."


def test_a_key_ending_in_id_backs_nothing(db, contact):
    result = {"items": [{"warehouse_id": 4321, "qty": 5}], "has_result": True}
    assert "(not verified)" in _reply_after(db, contact, "There are 4321 units.", result)


def test_a_three_row_column_backs_the_sum_of_all_three_only(db, contact):
    rows = {"items": [{"qty": 5}, {"qty": 7}, {"qty": 9}], "has_result": True}
    assert "(not verified)" in _reply_after(db, contact, "12 units in total.", rows)
    assert _reply_after(db, contact, "21 units in total.", rows) == "21 units in total."


def test_the_row_count_backs_a_figure(db, contact):
    rows = {"items": [{"qty": 4}, {"qty": 6}], "has_result": True}
    text = "10 units across 2 orders."
    assert _reply_after(db, contact, text, rows) == text


# ------------------------------------------------------------------ L6, nits


def test_a_word_only_in_the_remark_does_not_match(db, world):
    p = _product(db, code="ZZT-REM", name="plain")
    p.remark = "secretword"
    p.description = "visible words"
    db.flush()
    assert _find(db, world, {"query": "secretword"}, set()).status == "empty"
    assert _codes(_find(db, world, {"query": "visible"}, set())) == ["ZZT-REM"]


def test_redact_ids_replaces_only_whole_tokens_of_six_or_more_characters():
    from app.services.chatbot.agent.tools import redact_ids

    assert redact_ids("stock 548193 and 5481931120 and 548193112.", ("548193112",)) == (
        "stock 548193 and 5481931120 and (id)."
    )
    assert redact_ids("size 4321 here", ("4321",)) == "size 4321 here"  # too short to be an id token
