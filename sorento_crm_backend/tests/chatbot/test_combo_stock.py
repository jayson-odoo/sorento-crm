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


def _seed_set(
    session_factory, *, members: int = 3, quantities: tuple[float, ...] = ()
) -> tuple[str, list[str], list[str]]:
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
                    quantity=quantities[position] if position < len(quantities) else 1,
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


def _run_set_ask(
    session_factory,
    monkeypatch,
    *,
    msg_id: str,
    quantities: tuple[float, ...] = (),
    envelope=None,
):
    """`envelope(member_codes) -> dict` is what the stock tool answers; default is a
    plain compact page with Total 5 for every member."""
    _seed_contact_and_get(session_factory)
    set_code, member_codes, member_ids = _seed_set(session_factory, quantities=quantities)
    build = envelope or _stock_envelope

    def _call(name: str, args: dict[str, Any]) -> str:
        if name == STOCK_TOOL:
            return json.dumps(build(member_codes))
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


# --------------------------------------------------------------------------- #
# Slice 2: the full-access set header (owner Q1, Q2, Q4, 2 Oct 2026).
# --------------------------------------------------------------------------- #


def _compact(rows: dict[str, tuple[int, dict[str, int]]], *, missing: tuple[str, ...] = ()):
    """`stock_compact` (`sorento_crm_mcp.presenters._stock_compact`): one item per
    product, Product Code, Total, then one plain field per location code."""

    def build(codes: list[str]) -> dict[str, Any]:
        items = []
        for index, code in enumerate(codes):
            if code in missing or str(index) in missing:
                continue
            total, locations = rows[str(index)]
            fields: list[dict[str, Any]] = [
                {"key": "product_code", "label": "Product Code", "value": code},
                {"label": "Total", "value": total},
            ]
            fields += [{"label": loc, "value": qty} for loc, qty in locations.items()]
            items.append({"title": code, "fields": fields, "flags": {}})
        return {
            "intro": "Stock summary for the requested products.",
            "items": items,
            "has_result": True,
            "attachments": [],
            "result_type": "stock_compact",
            "action_links": [],
        }

    return build


def _detailed(rows: dict[str, dict[str, int]]):
    """`stock` (`presenters._stock`): one item per (product, location) row."""

    def build(codes: list[str]) -> dict[str, Any]:
        items = []
        for index, code in enumerate(codes):
            for loc, qty in rows[str(index)].items():
                items.append(
                    {
                        "title": code,
                        "fields": [
                            {"key": "product_code", "label": "Product Code", "value": code},
                            {"key": "warehouse", "label": "Warehouse", "value": f"WH {loc}"},
                            {"key": "system_location", "label": "System Location", "value": loc},
                            {"key": "quantity_on_hand", "label": "Quantity On Hand", "value": qty},
                        ],
                        "flags": {"discontinued": False},
                    }
                )
        return {
            "intro": "Stock details found for the requested products.",
            "items": items,
            "has_result": True,
            "attachments": [],
            "result_type": "stock",
            "action_links": [],
        }

    return build


def _availability(codes: list[str]) -> dict[str, Any]:
    """`stock_availability` (`presenters._stock_availability`): the dealer's lines, no
    numbers of ours at all."""
    return {
        "intro": "",
        "items": [
            {
                "title": f"{code} x 2: yes, we have stock. Please refer to your salesman.",
                "fields": [],
                "flags": {"needs_quantity": False, "branch": "in_stock"},
            }
            for code in codes
        ],
        "has_result": True,
        "attachments": [],
        "result_type": "stock_availability",
        "action_links": [],
    }


# Members 0, 1, 2; member 2 is taken TWICE per set.
#   total:  0 -> 10, 1 -> 7, 2 -> 20//2 = 10          => 7 complete sets, limited by member 1
#   BRW:    0 -> 6,  1 -> 7, 2 -> 10//2 = 5           => 5
#   KL:     0 -> 4,  1 -> 0, 2 -> 10//2 = 5           => 0
COMPACT_ROWS = {
    "0": (10, {"BRW": 6, "KL": 4}),
    "1": (7, {"BRW": 7, "KL": 0}),
    "2": (20, {"BRW": 10, "KL": 10}),
}
DETAILED_ROWS = {
    "0": {"BRW": 6, "KL": 4},
    "1": {"BRW": 7},
    "2": {"BRW": 10, "KL": 10},
}


class TestFullAccessSetHeader:
    def test_compact_reply_opens_with_complete_sets_and_the_limiting_member(
        self, session_factory, monkeypatch
    ) -> None:
        result, _calls, set_code, codes, _ids = _run_set_ask(
            session_factory,
            monkeypatch,
            msg_id="zzt-combo-header-compact",
            quantities=(1, 1, 2),
            envelope=_compact(COMPACT_ROWS),
        )
        said = _said(result)
        assert said.startswith(f"*{set_code}* is a set of {codes[0]} x1, {codes[1]} x1, {codes[2]} x2."), said
        assert f"Complete sets: 7 (limited by {codes[1]})" in said, said
        assert "By location: BRW 5, KL 0" in said, said
        # Q1: the header sits ABOVE today's member lines, which stay.
        for code in codes:
            assert said.index(code) < len(said)
        assert said.index("Complete sets") < said.index("Total"), said

    def test_detailed_reply_counts_from_the_per_location_rows(
        self, session_factory, monkeypatch
    ) -> None:
        result, _calls, set_code, codes, _ids = _run_set_ask(
            session_factory,
            monkeypatch,
            msg_id="zzt-combo-header-detailed",
            quantities=(1, 1, 2),
            envelope=_detailed(DETAILED_ROWS),
        )
        said = _said(result)
        assert f"Complete sets: 7 (limited by {codes[1]})" in said, said
        # Member 1 has no KL row at all: it counts 0 there (Q4).
        assert "By location: BRW 5, KL 0" in said, said

    def test_a_member_missing_from_the_reply_counts_zero_and_is_named(
        self, session_factory, monkeypatch
    ) -> None:
        result, _calls, _set_code, codes, _ids = _run_set_ask(
            session_factory,
            monkeypatch,
            msg_id="zzt-combo-header-missing",
            envelope=_compact(COMPACT_ROWS, missing=("2",)),
        )
        said = _said(result)
        assert f"Complete sets: 0 (limited by {codes[2]})" in said, said

    def test_a_dealer_availability_reply_gets_no_header_and_no_number(
        self, session_factory, monkeypatch
    ) -> None:
        result, _calls, set_code, codes, _ids = _run_set_ask(
            session_factory,
            monkeypatch,
            msg_id="zzt-combo-header-dealer",
            envelope=_availability,
        )
        said = _said(result)
        assert "Complete sets" not in said, said
        assert "is a set of" not in said, said
        for code in codes:
            assert f"{code} x 2: yes, we have stock." in said, said


class TestSetHeaderUnit:
    def test_header_is_none_without_a_stock_envelope(self) -> None:
        from app.services.chatbot.lanes.business import set_stock

        product_set = {
            "set_code": "S-RL",
            "members": [{"product_code": "A", "quantity": 1}],
        }
        assert set_stock.set_header(product_set, _availability(["A"])) is None

    def test_part_of_lines_sit_above_the_freshness_footer(self) -> None:
        from app.services.chatbot.lanes.business import set_stock

        out = set_stock.above_footer("Stock summary.\n\n1. A\n\n_Data last updated: 02/10/2026_", "A is part of set(s) S")
        assert out == "Stock summary.\n\n1. A\n\nA is part of set(s) S\n\n_Data last updated: 02/10/2026_", out
        assert set_stock.above_footer("Stock summary.", "X") == "Stock summary.\n\nX"

    def test_fractional_quantity_floors(self) -> None:
        from app.services.chatbot.lanes.business import set_stock

        product_set = {
            "set_code": "S-RL",
            "members": [
                {"product_code": "A", "quantity": 1},
                {"product_code": "B", "quantity": 1.5},
            ],
        }
        envelope = _compact({"0": (9, {"BRW": 9}), "1": (10, {"BRW": 10})})(["A", "B"])
        header = set_stock.set_header(product_set, envelope)
        assert "B x1.5" in header, header
        assert "Complete sets: 6 (limited by B)" in header, header


# --------------------------------------------------------------------------- #
# Slice 3: a BASE code ("SRTWC8608", no set carries it) that prefix-matched member
# products (owner Q3, 2 Oct 2026).
# --------------------------------------------------------------------------- #


def _session_vars(session_factory) -> dict[str, Any]:
    from sqlalchemy import text

    from tests.chatbot.test_rearch_r12_handpass12 import CONTACT_ID

    db = session_factory()
    try:
        row = db.execute(
            text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
            {"cid": str(CONTACT_ID)},
        ).first()
    finally:
        db.close()
    raw = row.session_vars if row is not None else {}
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _add_set(session_factory, set_code: str, member_ids: list[str]) -> None:
    db = session_factory()
    try:
        product_set = ProductSet(
            set_code=set_code, name=f"ZZT {set_code}", company_id=DEFAULT_COMPANY_ID
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


def _seed_family(session_factory) -> dict[str, Any]:
    """The SRTWC8608 shape, measured on dev 2 Oct: the base code is a prefix of the
    seat cover (in several sets) and of the -UF seat cover; the pedestal and cistern
    are named differently (X / Y) and are reached ONLY through the set links."""
    tag = unique_code("", alpha=True)[-6:].upper()
    base = f"ZZB{tag}8608"
    codes = {
        "sc": f"{base}-SC",
        "sc_uf": f"{base}-SC-UF",
        "ped": f"ZZX{tag}8608-RL",
        "cis": f"ZZY{tag}8608",
        "lonely": f"{base}-ZZ",
    }
    ids = {
        key: str(_seed_product(session_factory, company_id=DEFAULT_COMPANY_ID, code=code))
        for key, code in codes.items()
    }
    sets = {"rl": f"ZZS{tag}8608-RL", "prl": f"ZZS{tag}8608-P-RL", "uf": f"ZZS{tag}8608-S-RL-UF"}
    _add_set(session_factory, sets["rl"], [ids["ped"], ids["cis"], ids["sc"]])
    _add_set(session_factory, sets["prl"], [ids["cis"], ids["sc"]])
    _add_set(session_factory, sets["uf"], [ids["cis"], ids["sc_uf"]])
    return {"base": base, "codes": codes, "ids": ids, "sets": sets}


def _compact_codes(codes: list[str]) -> dict[str, Any]:
    return _compact({str(i): (5, {"BRW": 5}) for i in range(len(codes))})(codes)


def _ask_base(session_factory, monkeypatch, family, *, envelope, msg_id: str):
    def _call(name: str, args: dict[str, Any]) -> str:
        if name == STOCK_TOOL:
            # Whatever products the call named, in a stable order.
            by_id = {v: family["codes"][k] for k, v in family["ids"].items()}
            codes = [by_id[p] for p in sorted(_product_ids(args)) if p in by_id]
            return json.dumps(envelope(codes))
        return _unknown_envelope()

    mcp_call, calls = _mcp_double(other=_call)
    result = _run_turn_engine(
        session_factory,
        monkeypatch,
        qf=_stock_ask(family["base"]),
        text_body=f"chck stock {family['base']}",
        msg_id=msg_id,
        mcp_call=mcp_call,
    )
    assert result.status == "done", result.error
    return result, calls


class TestBaseCodeFullAccess:
    def test_each_member_line_says_which_sets_it_is_part_of(
        self, session_factory, monkeypatch
    ) -> None:
        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)
        result, _calls = _ask_base(
            session_factory, monkeypatch, family, envelope=_compact_codes, msg_id="zzt-combo-base-full"
        )
        said = _said(result)
        sets = family["sets"]
        codes = family["codes"]
        assert (
            f"{codes['sc']} is part of set(s) {sets['prl']}, {sets['rl']} - "
            "ask for the set code to see full-set stock."
        ) in said, said
        assert (
            f"{codes['sc_uf']} is part of set(s) {sets['uf']} - "
            "ask for the set code to see full-set stock."
        ) in said, said
        # A product in no set gets no line; the pedestal was never in the answer.
        assert f"{codes['lonely']} is part of" not in said, said
        assert codes["ped"] not in said, said

    def test_an_exact_code_gets_no_part_of_set_line(
        self, session_factory, monkeypatch
    ) -> None:
        """Q3 is the BASE code. A code typed in full is answered as today."""
        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)

        def _call(name: str, args: dict[str, Any]) -> str:
            if name == STOCK_TOOL:
                return json.dumps(_compact_codes([family["codes"]["sc"]]))
            return _unknown_envelope()

        mcp_call, _calls = _mcp_double(other=_call)
        result = _run_turn_engine(
            session_factory,
            monkeypatch,
            qf=_stock_ask(family["codes"]["sc"]),
            text_body=f"chck stock {family['codes']['sc']}",
            msg_id="zzt-combo-exact",
            mcp_call=mcp_call,
        )
        assert "is part of set(s)" not in _said(result), _said(result)


class TestBaseCodeDealer:
    def test_a_dealer_is_offered_the_sets_as_a_pick(
        self, session_factory, monkeypatch
    ) -> None:
        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)
        result, _calls = _ask_base(
            session_factory, monkeypatch, family, envelope=_availability, msg_id="zzt-combo-base-dealer"
        )
        said = _said(result)
        sets = family["sets"]
        expected = sorted(sets.values())
        for position, code in enumerate(expected, start=1):
            assert f"{position}. {code}" in said, said
        # No member stock line and no number of ours beside the pick.
        assert "yes, we have stock" not in said, said

        question = _session_vars(session_factory).get("open_question") or {}
        assert question.get("kind") == "product_pick", question
        options = question.get("options") or []
        assert [o.get("code") for o in options] == expected, options
        rl = next(o for o in options if o.get("code") == sets["rl"])
        ids = family["ids"]
        assert sorted(rl.get("uuids") or []) == sorted([ids["ped"], ids["cis"], ids["sc"]]), rl

    def test_picking_a_set_answers_over_that_sets_members(
        self, session_factory, monkeypatch
    ) -> None:
        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)
        _ask_base(
            session_factory, monkeypatch, family, envelope=_availability, msg_id="zzt-combo-pick-1"
        )
        expected = sorted(family["sets"].values())
        position = expected.index(family["sets"]["rl"]) + 1

        def _call(name: str, args: dict[str, Any]) -> str:
            if name == STOCK_TOOL:
                return json.dumps(_availability(["X"]))
            return _unknown_envelope()

        mcp_call, calls = _mcp_double(other=_call)
        result = _run_turn_engine(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                reference_positions=[position],
                order_status=None,
            ),
            text_body=str(position),
            msg_id="zzt-combo-pick-2",
            mcp_call=mcp_call,
        )
        assert result.status == "done", result.error
        stock_calls = [args for name, args in calls if name == STOCK_TOOL]
        assert stock_calls, f"the pick must run the stock ask: {calls!r}"
        ids = family["ids"]
        assert _product_ids(stock_calls[-1]) == {ids["ped"], ids["cis"], ids["sc"]}, stock_calls
