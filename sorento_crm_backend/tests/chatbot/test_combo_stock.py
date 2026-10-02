"""COMBO-STOCK RED tests: a stock ask naming a product SET code is answered over the
set's members, never refused as filterless.

Plan: `documentation/plans/chatbot/PLAN-combo-stock-2oct.md`.

Owner, 2 Oct 2026 (dev, business_query v43): "chck stock SRTWC8608-RL" answered
"That would search every stock we have - I need at least one filter ... Give me a
product code" although `SRTWC8608-RL` IS a code - a `product_sets` row naming the
pedestal, the cistern and the seat cover. The chain, measured in this harness:

* `entity_resolver._probe_product_set` places the token as `product_set`, carrying its
  members (uuid + code + quantity) on `display.members`;
* `gate.ALLOWED["inventory"]` does not take `product_set`, so `compatible_entities`
  came out empty;
* the 22 Sep no-subject guard in `turn_runtime.make_tool_runner.runner` then saw an
  inventory fetch with no uuid at all and refused it with the scope-needed sentence.

Membership comes ONLY from `product_set_members` (the explicit link), never from the
code's shape: the members seeded here share no prefix with the set code on purpose.

Harness copied from `test_rearch_r13_stock_no_subject.py` (the REAL resolver / gate /
narrower over seeded Postgres rows, only `FetchServices.mcp_call` doubled).
"""
from __future__ import annotations

import json
from typing import Any

from app.models.product_set import ProductSet, ProductSetMember
from app.services.chatbot.lanes.business import gate as gate_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_engine_company_scope import _seed_product
from tests.chatbot.test_rearch_r5_production_decides import _mcp_double, _seed_contact_and_get
from tests.chatbot.test_rearch_r6_review_round import _run_turn_engine
from tests.chatbot.test_rearch_r12_handpass12 import STOCK_TOOL, _said, _unknown_envelope

NEEDS_SCOPE_OPENING = "That would search every stock we have"


def _seed_set(session_factory, *, members: int = 3) -> tuple[str, list[str], list[str]]:
    """A set whose members' codes share NOTHING with the set code, so a pass can only
    come from the explicit `product_set_members` link, never from a prefix match."""
    tag = unique_code("", alpha=True)[-8:].upper()
    member_codes = [f"ZZM{tag}{i}7-X" for i in range(members)]
    member_ids = [
        _seed_product(session_factory, company_id=DEFAULT_COMPANY_ID, code=code)
        for code in member_codes
    ]
    set_code = f"ZZS{tag}8608-RL"
    db = session_factory()
    try:
        product_set = ProductSet(
            set_code=set_code, name=f"ZZT combo {tag}", company_id=DEFAULT_COMPANY_ID
        )
        db.add(product_set)
        db.flush()
        for position, member_id in enumerate(member_ids):
            db.add(
                ProductSetMember(
                    product_set_id=product_set.id,
                    product_id=member_id,
                    quantity=1,
                    sort_order=position,
                )
            )
        db.commit()
    finally:
        db.close()
    return set_code, member_codes, [str(i) for i in member_ids]


def _stock_ask(code: str) -> dict[str, Any]:
    return _parser_output(
        message_type="business_query",
        intent_hint="check_stock",
        domain_hint="inventory",
        domain_in_message=True,
        continuation=False,
        entities=[
            {
                "raw": code,
                "hint": "product",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
        entity_op="new",
        document=[],
        status=None,
        order_status=None,
        routing={
            "suggested_team": "warehouse",
            "suggested_agent": "general_enquiries",
            "team_source": None,
        },
    )


def _stock_envelope(codes: list[str]) -> dict[str, Any]:
    return {
        "intro": "Stock details found for the requested products.",
        "items": [
            {
                "flags": {},
                "title": code,
                "fields": [
                    {"key": "product_code", "label": "Product Code", "value": code},
                    {"key": "total_on_hand", "label": "Total", "value": 5},
                ],
            }
            for code in codes
        ],
        "has_result": True,
        "attachments": [],
        "result_type": "stock_compact",
        "action_links": [],
    }


def _run_set_ask(session_factory, monkeypatch, *, msg_id: str):
    _seed_contact_and_get(session_factory)
    set_code, member_codes, member_ids = _seed_set(session_factory)

    def _call(name: str, args: dict[str, Any]) -> str:
        if name == STOCK_TOOL:
            return json.dumps(_stock_envelope(member_codes))
        return _unknown_envelope()

    mcp_call, calls = _mcp_double(other=_call)
    result = _run_turn_engine(
        session_factory,
        monkeypatch,
        qf=_stock_ask(set_code),
        text_body=f"chck stock {set_code}",
        msg_id=msg_id,
        mcp_call=mcp_call,
    )
    assert result.status == "done", result.error
    return result, calls, set_code, member_codes, member_ids


def _product_ids(args: dict[str, Any]) -> set[str]:
    raw = args.get("product_ids") or []
    if isinstance(raw, str):
        raw = [p for p in raw.split(",") if p]
    return {str(p) for p in raw}


class TestSetCodeStockAskEngine:
    def test_the_stock_tool_is_called_with_exactly_the_set_members(
        self, session_factory, monkeypatch
    ) -> None:
        _result, calls, set_code, _codes, member_ids = _run_set_ask(
            session_factory, monkeypatch, msg_id="zzt-combo-members"
        )
        stock_calls = [args for name, args in calls if name == STOCK_TOOL]
        assert stock_calls, (
            f"a set code ({set_code}) names its members explicitly - the stock tool "
            f"must be called over them, not refused: {calls!r}"
        )
        assert _product_ids(stock_calls[0]) == set(member_ids), (
            f"the stock call must carry exactly the set's members (product_set_members), "
            f"no more, no fewer: {stock_calls[0]!r} vs {member_ids!r}"
        )

    def test_the_reply_is_not_the_scope_needed_sentence(
        self, session_factory, monkeypatch
    ) -> None:
        result, _calls, set_code, member_codes, _ids = _run_set_ask(
            session_factory, monkeypatch, msg_id="zzt-combo-reply"
        )
        said = _said(result)
        assert not said.startswith(NEEDS_SCOPE_OPENING), (
            f"'chck stock {set_code}' named a code; it must never be refused as "
            f"filterless: {said!r}"
        )
        for code in member_codes:
            assert code in said, f"every member's stock line must reach the reply: {said!r}"


# --------------------------------------------------------------------------- #
# Gate unit: the expansion is the gate's, scoped to inventory.
# --------------------------------------------------------------------------- #


def _set_match(set_code: str, members: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "entity_type": "product_set",
        "canonical_code": set_code,
        "uuid": "11111111-1111-1111-1111-111111111111",
        "match_field": "set_code",
        "match_tier": "exact",
        "display": {
            "name": "set",
            "member_count": len(members),
            "complete_sets": 0,
            "limiting_member": members[0][1] if members else None,
            "members": [
                {"product_code": code, "uuid": uid, "quantity": 1.0, "available": 0}
                for uid, code in members
            ],
        },
    }


def _gate(domain: str, match: dict[str, Any]) -> dict[str, Any]:
    resolver = {
        "resolutions": [
            {"token": match["canonical_code"], "resolved": True, "matches": [match]}
        ],
        "unresolved_tokens": [],
    }
    parser = {
        "domain_hint": domain,
        "intent_hint": "check_stock",
        "entities": [{"raw": match["canonical_code"], "hint": "product"}],
    }
    return gate_mod.run_gate(dict(resolver), parser=parser, resolver=resolver)


MEMBERS = [
    ("22222222-2222-2222-2222-222222222222", "ZZPED-RL"),
    ("33333333-3333-3333-3333-333333333333", "ZZCIS"),
]


class TestGateExpandsASetForInventory:
    def test_inventory_gate_passes_with_the_members_as_products(self) -> None:
        out = _gate("inventory", _set_match("ZZSET-RL", MEMBERS))
        assert out["gate_passed"] is True, out["gate_reason"]
        got = [(e["uuid"], e["entity_type"], e["code"]) for e in out["compatible_entities"]]
        assert got == [(uid, "product", code) for uid, code in MEMBERS]

    def test_the_set_token_is_not_reported_as_incompatible_only(self) -> None:
        """`miss_suggest` forces a did-you-mean on a token whose only matches are an
        incompatible kind. An expanded set is not a miss."""
        out = _gate("inventory", _set_match("ZZSET-RL", MEMBERS))
        incompatible_only = (out.get("gate_debug") or {}).get("incompatible_only") or {}
        assert "ZZSET-RL" not in incompatible_only, incompatible_only

    def test_a_set_with_no_members_still_does_not_pass(self) -> None:
        out = _gate("inventory", _set_match("ZZEMPTY-RL", []))
        assert out["gate_passed"] is False

    def test_other_domains_do_not_expand(self) -> None:
        """Owner ruling Q5 (crew, 2 Oct 2026): inventory stock asks only this lane."""
        out = _gate("promotion", _set_match("ZZSET-RL", MEMBERS))
        assert out["compatible_entities"] == []
