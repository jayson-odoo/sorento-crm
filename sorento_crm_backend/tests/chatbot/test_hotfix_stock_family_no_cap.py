"""Hotfix 28 Sep 2026: a family stock ask lists every matching product, no five-product page.

Production case (owner, 28 Sep 21:4x MYT, "this cap 5 is hurting the production now"): the
dealer wrote "7820 stock"; the catalogue holds seven MKT7820SS products (BL, CR, plain, FGD,
FRG, GM and a duplicate plain row). The reply listed five and silently dropped
MKT7820SS-GM-DIY, because `fetch.entity_ids_transformer` sliced a predicate turn's
`product_ids` to the first five and the engine armed a "more" page for the rest.

Owner's standing rule (26 Sep): the chatbot never pages with "more" or "next"; it states the
full count. The only ceilings left are the tool's own ROW cap (`limit`, untouched) and the
resolver's `PREFIX_LIMIT` of 20.

PR #833 (feat/chatbot-attribute-first-asks) supersedes this with its rewrite; these pins are
the reader-facing result it must keep.
"""
from __future__ import annotations

import uuid

from app.services.chatbot.lanes.business import fetch

# The seven production MKT7820SS rows (the duplicate plain row is a second product with
# the same code family, so it carries its own id and its own code here).
FAMILY_7820 = [
    "MKT7820SS-BL",
    "MKT7820SS-CR",
    "MKT7820SS",
    "MKT7820SS-FGD",
    "MKT7820SS-FRG",
    "MKT7820SS-GM-DIY",
    "MKT7820SS-DUP",
]


def _stock_predicate(total: int) -> dict:
    return {
        "require": {"stock": True},
        "qualifying_total": total,
        "truncated": False,
        "unrecognized_terms": [],
        "class_labels": [],
    }


def test_7820_stock_family_sends_every_product_id_to_the_tool():
    ids = [str(uuid.uuid4()) for _ in FAMILY_7820]
    trigger = {
        "tool": "crm_inventory_stock_balance_list",
        "entities": [
            {"uuid": pid, "entity_type": "product", "canonical_code": code}
            for pid, code in zip(ids, FAMILY_7820)
        ],
        "predicate": _stock_predicate(len(ids)),
        "semantic_input": {"contact_id": "1", "space_id": "s"},
    }

    out = fetch.entity_ids_transformer(trigger)

    assert out["product_ids"] == ids, (
        "a family stock ask must fetch all seven MKT7820SS products, never the first five: "
        f"{out['product_ids']!r}"
    )
    # The tool's own ROW cap is left alone: products are not rows.
    assert "limit" not in out, out


def _stock_row(code: str, warehouse: str) -> dict:
    return {
        "title": code,
        "fields": [
            {"label": "Product Code", "value": code},
            {"label": "Warehouse", "value": warehouse},
        ],
    }


def test_7820_stock_answer_lists_all_seven_and_states_the_count_with_no_showing():
    # Two warehouse rows for two of the products: the header counts PRODUCTS, not rows.
    items = [_stock_row(code, "BRW") for code in FAMILY_7820]
    items += [_stock_row("MKT7820SS-BL", "PJY"), _stock_row("MKT7820SS-GM-DIY", "PJY")]
    envelope = {
        "result_type": "stock_balance",
        "intro": "Stock details found for the requested products.",
        "items": items,
        "has_result": True,
    }

    out = fetch.output_structurer(
        envelope, {"semantic_input": {}, "predicate": _stock_predicate(len(FAMILY_7820))}
    )

    reply = out["response"]
    for code in FAMILY_7820:
        assert code in reply, f"{code} missing from the family stock reply: {reply!r}"
    assert out["set_header"].startswith("7 products have"), out["set_header"]
    assert "Showing" not in reply, reply
    assert "more" not in reply.lower().split("\n")[0], reply


def _state_with_a_page_left_behind():
    """A focus carrying a `set_page` exactly as the pre-hotfix engine wrote it after a
    counted-set answer - what a session saved before this deploy still holds."""
    from app.services.chatbot.turn.state import Focus, Profile, State

    focus = Focus()
    focus.domains = ["inventory"]
    focus.set_page = {
        "set_key": {
            "domain": "inventory",
            "require": {"stock": True},
            "scope_terms": ["7820"],
            "access_levels": [],
        },
        "offset": 5,
    }
    return State(focus=focus, pending=None, profile=Profile(), turn_no=3)


def test_more_after_a_counted_answer_is_not_a_page():
    """With the carry gone a "more" runs the ordinary ladder: the carried domain is
    re-fetched on whatever subject the focus still holds (a plain restatement of the
    same full list), and with no subject at all the inventory no-subject guard
    (`turn_runtime.make_tool_runner`, hotfix 22 Sep) answers the existing "which
    product" miss. It never pages."""
    from app.services.chatbot.turn.apply import apply

    from tests.chatbot._turn_helpers import build_policy, verdict

    v = verdict(message_type="clarification", user_goal="more", continuation=True)
    new_state, plan = apply(_state_with_a_page_left_behind(), v, build_policy())

    assert "set_page_continuation" not in plan.trace.rules_fired, plan.trace.rules_fired
    assert not any(isinstance(s.filters.get("set_page"), dict) for s in plan.fetch), [
        s.filters for s in plan.fetch
    ]
    assert [s.domain for s in plan.fetch] == ["inventory"], plan.fetch
    assert new_state.focus.set_page is None, new_state.focus.set_page
