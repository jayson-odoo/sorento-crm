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


def _stock_ask(code: str, *more: str) -> dict[str, Any]:
    return _parser_output(
        message_type="business_query",
        intent_hint="check_stock",
        domain_hint="inventory",
        domain_in_message=True,
        continuation=False,
        entities=[
            {
                "raw": raw,
                "hint": "product",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
            for raw in (code, *more)
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
        assert said.startswith(f"{set_code}: "), f"a set code is answered at set level: {said!r}"


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


def _availability_asking(codes: list[str]) -> dict[str, Any]:
    """The dealer's FIRST answer when no quantity was given: the presenter asks, and the
    backend's `stock_availability` rows say a quantity is still needed - the rows
    `turn/task.py::after_reply` arms the family pick / quantity ask from."""
    return {
        "intro": "How many units do you need?",
        "items": [
            {"title": code, "fields": [], "flags": {"needs_quantity": True, "branch": None}}
            for code in codes
        ],
        "stock_availability": [
            {"product_code": code, "needs_quantity": True, "requested_qty": None}
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


def _add_set(
    session_factory,
    set_code: str,
    member_ids: list[str],
    *,
    company_id: str = DEFAULT_COMPANY_ID,
    is_active: bool = True,
) -> None:
    db = session_factory()
    try:
        product_set = ProductSet(
            set_code=set_code, name=f"ZZT {set_code}", company_id=company_id, is_active=is_active
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


def _ask_base(
    session_factory,
    monkeypatch,
    family,
    *,
    envelope,
    msg_id: str,
    also: tuple[str, ...] = (),
    others: dict[str, Any] | None = None,
):
    """`others` maps a non-stock tool name to the envelope it answers (the zero-stock
    ladder's incoming / PO probes); anything else answers an unknown envelope."""

    def _call(name: str, args: dict[str, Any]) -> str:
        if name == STOCK_TOOL:
            # Whatever products the call named, in a stable order.
            by_id = {v: family["codes"][k] for k, v in family["ids"].items()}
            codes = [by_id[p] for p in sorted(_product_ids(args)) if p in by_id]
            return json.dumps(envelope(codes))
        if others and name in others:
            return json.dumps(others[name])
        return _unknown_envelope()

    mcp_call, calls = _mcp_double(other=_call)
    result = _run_turn_engine(
        session_factory,
        monkeypatch,
        qf=_stock_ask(family["base"], *also),
        text_body=" ".join(["chck stock", family["base"], *also]),
        msg_id=msg_id,
        mcp_call=mcp_call,
    )
    assert result.status == "done", result.error
    return result, calls



# --------------------------------------------------------------------------- #
# Simplified set answers (owner hand test FAIL + answers, 3 Oct 2026): ONE set-level
# answer, no component rows, no zero rows, no "part of set(s)" lines; a dealer gives
# ONE quantity per set. Staff run in COMPACT mode (owner) and detailed alike.
# --------------------------------------------------------------------------- #


def _dealer_rows(rows: dict[str, tuple[str, str | None]], qty: int | None):
    """A dealer's `availability` envelope with real `stock_availability` rows:
    `{member index: (branch, eta)}`. `qty` None = every member still needs a quantity
    (the presenter's own "How many units ..." case)."""

    tails = {
        "in_stock": "yes, we have stock. Please refer to your salesman.",
        "too_big": "the quantity is more than what I can confirm here. Please refer to your salesman.",
        "no_incoming": "no stock and no incoming at the moment. Please refer to your salesman.",
    }

    def build(
        codes: list[str], ids: dict[str, str] | None = None, asked_by_code: dict[str, int] | None = None
    ) -> dict[str, Any]:
        """`asked_by_code`: the quantities the call itself sent, which the real tool
        echoes per product; they win over `qty` once a quantity was asked at all."""
        entries, items = [], []
        for index, code in enumerate(codes):
            branch, eta = rows.get(str(index), ("in_stock", None))
            asked = qty.get(code) if isinstance(qty, dict) else qty
            if asked is not None and asked_by_code and code in asked_by_code:
                asked = asked_by_code[code]
            needs = asked is None
            entry = {
                "product_id": (ids or {}).get(code, code),
                "product_code": code,
                "needs_quantity": needs,
                "requested_qty": None if needs else asked,
                "branch": None if needs else branch,
                "eta": None if needs else eta,
            }
            tail = f"no stock at the moment, ETA {eta}." if branch == "incoming" else tails[branch]
            if not needs:
                # `sorento_crm_mcp.presenters._stamp_refers`: read off the printed tail.
                entry["refers_to_salesman"] = tail.endswith("Please refer to your salesman.")
            entries.append(entry)
            items.append(
                {
                    "title": code if needs else f"{code} x {entry['requested_qty']}: {tail}",
                    "fields": [],
                    "flags": {"needs_quantity": needs, "branch": entry["branch"]},
                }
            )
        return {
            "intro": "How many units do you need?" if qty is None else "",
            "items": items,
            "stock_availability": entries,
            "has_result": True,
            "attachments": [],
            "result_type": "stock_availability",
            "action_links": [],
        }

    return build


class TestStaffSetCode:
    """Q1 (a): `SET: N sets available (limited by M)` + one line of NON-ZERO locations,
    sorted by sets; nothing else."""

    def _said(self, session_factory, monkeypatch, envelope, msg_id):
        result, _calls, set_code, codes, _ids = _run_set_ask(
            session_factory, monkeypatch, msg_id=msg_id, quantities=(1, 1, 2), envelope=envelope
        )
        return _said(result), set_code, codes

    def test_compact(self, session_factory, monkeypatch) -> None:
        said, set_code, codes = self._said(session_factory, monkeypatch, _compact(COMPACT_ROWS), "zzt-s1-c")
        assert said == (
            f"{set_code}: 7 sets available (limited by {codes[1]})\nBy location: BRW 5"
        ), said

    def test_detailed(self, session_factory, monkeypatch) -> None:
        said, set_code, codes = self._said(session_factory, monkeypatch, _detailed(DETAILED_ROWS), "zzt-s1-d")
        assert said == (
            f"{set_code}: 7 sets available (limited by {codes[1]})\nBy location: BRW 5"
        ), said

    def test_locations_sorted_by_sets_and_zero_left_out(self, session_factory, monkeypatch) -> None:
        rows = {
            "0": (30, {"A1": 3, "B2": 20, "C3": 0, "D4": 7}),
            "1": (30, {"A1": 3, "B2": 20, "C3": 9, "D4": 7}),
            "2": (60, {"A1": 6, "B2": 40, "C3": 0, "D4": 14}),
        }
        said, set_code, _codes = self._said(session_factory, monkeypatch, _compact(rows), "zzt-s1-sort")
        assert said.endswith("By location: B2 20, D4 7, A1 3"), said

    def test_nothing_anywhere_has_no_location_line(self, session_factory, monkeypatch) -> None:
        rows = {"0": (0, {"BRW": 0}), "1": (5, {"BRW": 5}), "2": (6, {"BRW": 6})}
        said, set_code, codes = self._said(session_factory, monkeypatch, _compact(rows), "zzt-s1-zero")
        assert said == f"{set_code}: 0 sets available (limited by {codes[0]})", said


class TestStaffBaseCode:
    """Q2 (a): the list of sets with sets available; a number gives that set's answer."""

    def test_the_list_of_sets_and_nothing_else(self, session_factory, monkeypatch) -> None:
        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)
        result, calls = _ask_base(
            session_factory, monkeypatch, family, envelope=_compact_codes, msg_id="zzt-s2-list"
        )
        sets = family["sets"]
        # Every member has Total 5 / BRW 5 (`_compact_codes`), qty 1 each: 5 sets each.
        assert _said(result) == (
            f"{family['base']} sets:\n"
            f"1. {sets['prl']}: 5 sets\n"
            f"2. {sets['rl']}: 5 sets\n"
            f"3. {sets['uf']}: 5 sets\n"
            "Reply a number for one set's locations."
        ), _said(result)
        # The counts come from the stock tool over EVERY member of those sets.
        ids = family["ids"]
        asked = set().union(*(_product_ids(a) for n, a in calls if n == STOCK_TOOL))
        assert {ids["ped"], ids["cis"], ids["sc"], ids["sc_uf"]} <= asked, asked
        question = _session_vars(session_factory).get("open_question") or {}
        assert [o.get("code") for o in question.get("options") or []] == sorted(sets.values()), question

    def test_a_number_gives_that_sets_answer(self, session_factory, monkeypatch) -> None:
        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)
        _ask_base(session_factory, monkeypatch, family, envelope=_compact_codes, msg_id="zzt-s2-a")
        position = sorted(family["sets"].values()).index(family["sets"]["rl"]) + 1
        by_id = {v: family["codes"][k] for k, v in family["ids"].items()}

        def _call(name: str, args: dict[str, Any]) -> str:
            if name == STOCK_TOOL:
                return json.dumps(_compact_codes([by_id[p] for p in sorted(_product_ids(args)) if p in by_id]))
            return _unknown_envelope()

        mcp_call, calls = _mcp_double(other=_call)
        result = _run_turn_engine(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[position], order_status=None,
            ),
            text_body=str(position),
            msg_id="zzt-s2-b",
            mcp_call=mcp_call,
        )
        ids = family["ids"]
        stock_calls = [a for n, a in calls if n == STOCK_TOOL]
        assert stock_calls and _product_ids(stock_calls[-1]) == {ids["ped"], ids["cis"], ids["sc"]}, (stock_calls, _said(result))
        assert _said(result).startswith(f"{family['sets']['rl']}: 5 sets available"), _said(result)

    def test_a_code_typed_in_full_is_answered_as_before(self, session_factory, monkeypatch) -> None:
        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)

        def _call(name: str, args: dict[str, Any]) -> str:
            if name == STOCK_TOOL:
                return json.dumps(_compact_codes([family["codes"]["sc"]]))
            return _unknown_envelope()

        mcp_call, _calls = _mcp_double(other=_call)
        result = _run_turn_engine(
            session_factory, monkeypatch, qf=_stock_ask(family["codes"]["sc"]),
            text_body=f"chck stock {family['codes']['sc']}", msg_id="zzt-s2-exact", mcp_call=mcp_call,
        )
        said = _said(result)
        assert " sets:" not in said and "sets available" not in said, said

    def test_another_companys_set_and_an_inactive_set_are_never_listed(
        self, session_factory, monkeypatch
    ) -> None:
        from tests.chatbot.test_engine_company_scope import _seed_company

        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)
        other_company = _seed_company(session_factory, name="ZZT combo other")
        foreign = f"ZZF{unique_code('', alpha=True)[-6:].upper()}8608-RL"
        retired = f"ZZR{unique_code('', alpha=True)[-6:].upper()}8608-RL"
        _add_set(session_factory, foreign, [family["ids"]["sc"]], company_id=other_company)
        _add_set(session_factory, retired, [family["ids"]["sc"]], is_active=False)
        result, _calls = _ask_base(
            session_factory, monkeypatch, family, envelope=_compact_codes, msg_id="zzt-s2-scope"
        )
        said = _said(result)
        assert family["sets"]["rl"] in said, said
        assert foreign not in said and retired not in said, said


class TestDealer:
    """Dealer: ONE quantity per set; the weakest part decides, ETA = the latest part's (Q3)."""

    def _dealer(self, monkeypatch) -> None:
        from app.services.chatbot import turn_runtime

        monkeypatch.setattr(turn_runtime, "_stock_availability_only", lambda *a, **k: True)

    def _ask_set(self, session_factory, monkeypatch, envelope, msg_id, *, set_code_qty=None):
        """A set code ask, returning (result, calls, set_code, member codes, member ids)."""
        _seed_contact_and_get(session_factory)
        set_code, codes, ids = _seed_set(session_factory, quantities=(1, 1, 2))
        by_code = dict(zip(codes, ids))
        by_id = dict(zip(ids, codes))

        def _call(name: str, args: dict[str, Any]) -> str:
            if name == STOCK_TOOL:
                asked = args.get("requested_quantities")
                asked = json.loads(asked) if isinstance(asked, str) else (asked or {})
                per_code = {by_id[k]: v for k, v in asked.items() if k in by_id}
                return json.dumps(
                    envelope([by_id[p] for p in sorted(_product_ids(args)) if p in by_id], by_code, per_code)
                )
            return _unknown_envelope()

        mcp_call, calls = _mcp_double(other=_call)
        qf = _stock_ask(set_code)
        if set_code_qty is not None:
            qf["entities"][0]["quantity"] = set_code_qty
        result = _run_turn_engine(
            session_factory, monkeypatch, qf=qf, text_body=f"{set_code} stock", msg_id=msg_id, mcp_call=mcp_call,
        )
        assert result.status == "done", result.error
        return result, calls, set_code, codes, ids

    def test_a_set_code_asks_one_quantity(self, session_factory, monkeypatch) -> None:
        self._dealer(monkeypatch)
        result, _calls, set_code, codes, _ids = self._ask_set(
            session_factory, monkeypatch, _dealer_rows({}, None), "zzt-d1"
        )
        said = _said(result)
        # One question for the whole set, in the open quantity task's own one-slot
        # wording (`turn/task.py::StockQtyTask.question`).
        assert said == f"How many units of {set_code}?", said
        for code in codes:
            assert code not in said, said

    def test_the_quantity_reply_answers_the_set_in_one_line(self, session_factory, monkeypatch) -> None:
        self._dealer(monkeypatch)
        _r, _c, set_code, codes, ids = self._ask_set(
            session_factory, monkeypatch, _dealer_rows({}, None), "zzt-d2-a"
        )
        by_id = dict(zip(ids, codes))
        by_code = dict(zip(codes, ids))

        def _call(name: str, args: dict[str, Any]) -> str:
            if name == STOCK_TOOL:
                # The real tool echoes each part's OWN asked quantity (`requested_quantities`).
                asked = args.get("requested_quantities")
                asked = json.loads(asked) if isinstance(asked, str) else (asked or {})
                per_code = {by_id[k]: v for k, v in asked.items() if k in by_id}
                return json.dumps(
                    _dealer_rows({}, 5)([by_id[p] for p in sorted(_product_ids(args)) if p in by_id], by_code, per_code)
                )
            return _unknown_envelope()

        mcp_call, calls = _mcp_double(other=_call)
        result = _run_turn_engine(
            session_factory, monkeypatch,
            # A bare number, as the parser reads one (`test_dsv_apply_tasks.py`'s own shape).
            qf=_parser_output(
                message_type="business_query", intent_hint=None, domain_hint=None,
                entities=[], demand_qty=5, order_status=None,
            ),
            text_body="5", msg_id="zzt-d2-b", mcp_call=mcp_call,
        )
        assert result.status == "done", result.error
        stock_calls = [a for n, a in calls if n == STOCK_TOOL]
        assert stock_calls, calls
        asked = stock_calls[-1].get("requested_quantities")
        asked = json.loads(asked) if isinstance(asked, str) else asked
        # 5 sets: x1, x1 and x2 per set.
        assert asked == {ids[0]: 5, ids[1]: 5, ids[2]: 10}, stock_calls[-1]
        assert _said(result) == f"{set_code} x 5: yes, we have stock. Please refer to your salesman.", _said(result)

    def test_a_quantity_typed_with_the_set_code_answers_at_once(self, session_factory, monkeypatch) -> None:
        self._dealer(monkeypatch)
        result, calls, set_code, _codes, ids = self._ask_set(
            session_factory, monkeypatch, _dealer_rows({}, 3), "zzt-d3", set_code_qty=3
        )
        asked = [a for n, a in calls if n == STOCK_TOOL][-1].get("requested_quantities")
        asked = json.loads(asked) if isinstance(asked, str) else asked
        assert asked == {ids[0]: 3, ids[1]: 3, ids[2]: 6}, asked
        assert _said(result) == f"{set_code} x 3: yes, we have stock. Please refer to your salesman.", _said(result)

    def test_an_answered_set_is_logged_as_its_parts(self, session_factory, monkeypatch, caplog) -> None:
        """Customer asks (`stock_asks.product_id` -> products) is written from the
        answered rows: a set is not a product, so the answered reply keeps the PARTS'
        own rows, never one row keyed by the set id (FK violation, swallowed)."""
        import logging

        from sqlalchemy import text

        from app.services.chatbot import answer_bridge

        seen: list[dict[str, Any]] = []
        real = answer_bridge._run_crossdomain_ladder

        def _spy(**kwargs):
            seen.append(dict(kwargs.get("item") or {}))
            return real(**kwargs)

        monkeypatch.setattr(answer_bridge, "_run_crossdomain_ladder", _spy)
        self._dealer(monkeypatch)
        caplog.set_level(logging.ERROR, logger="app.services.chatbot.engine")
        _r, _c, _set_code, _codes, ids = self._ask_set(
            session_factory, monkeypatch, _dealer_rows({}, 3), "zzt-d-log", set_code_qty=3
        )
        assert "stock ask follow-up failed" not in caplog.text, caplog.text
        # The ladder still sees a non-empty availability block on the ANSWERED turn.
        assert seen and all(item.get("stock_availability") for item in seen), seen
        db = session_factory()
        try:
            logged = {
                str(r[0])
                for r in db.execute(
                    text("SELECT product_id FROM stock_asks WHERE product_id::text = ANY(:ids)"),
                    {"ids": list(ids)},
                ).fetchall()
            }
        finally:
            db.close()
        assert logged == set(ids), (logged, ids)

    def test_the_weakest_part_decides_and_the_eta_is_the_latest(self, session_factory, monkeypatch) -> None:
        self._dealer(monkeypatch)
        rows = {"0": ("incoming", "05/11/2026"), "1": ("in_stock", None), "2": ("incoming", "20/11/2026")}
        result, _calls, set_code, _codes, _ids = self._ask_set(
            session_factory, monkeypatch, _dealer_rows(rows, 3), "zzt-d4", set_code_qty=3
        )
        assert _said(result) == f"{set_code} x 3: no stock at the moment, ETA 20/11/2026.", _said(result)

    def test_no_incoming_beats_incoming(self, session_factory, monkeypatch) -> None:
        self._dealer(monkeypatch)
        rows = {"0": ("incoming", "05/11/2026"), "1": ("no_incoming", None)}
        result, *_ = self._ask_set(session_factory, monkeypatch, _dealer_rows(rows, 3), "zzt-d5", set_code_qty=3)
        assert _said(result).endswith(": no stock and no incoming at the moment. Please refer to your salesman."), _said(result)

    def test_base_code_pick_then_one_quantity(self, session_factory, monkeypatch) -> None:
        self._dealer(monkeypatch)
        _seed_contact_and_get(session_factory)
        family = _seed_family(session_factory)
        ids = family["ids"]
        by_id = {v: family["codes"][k] for k, v in ids.items()}
        by_code = {family["codes"][k]: v for k, v in ids.items()}

        def asking(codes: list[str]) -> dict[str, Any]:
            return _dealer_rows({}, None)(codes, by_code)

        result, _calls = _ask_base(session_factory, monkeypatch, family, envelope=asking, msg_id="zzt-d6-a")
        said = _said(result)
        assert said.startswith(f"{family['base']} is part of 3 sets. Which one?"), said
        position = sorted(family["sets"].values()).index(family["sets"]["rl"]) + 1

        def _call(name: str, args: dict[str, Any]) -> str:
            if name == STOCK_TOOL:
                return json.dumps(asking([by_id[p] for p in sorted(_product_ids(args)) if p in by_id]))
            return _unknown_envelope()

        mcp_call, calls = _mcp_double(other=_call)
        result = _run_turn_engine(
            session_factory, monkeypatch,
            qf=_parser_output(
                message_type="casual", intent_hint=None, domain_hint=None, entities=[],
                reference_positions=[position], order_status=None,
            ),
            text_body=str(position), msg_id="zzt-d6-b", mcp_call=mcp_call,
        )
        assert _said(result) == f"How many units of {family['sets']['rl']}?", _said(result)
        stock_calls = [a for n, a in calls if n == STOCK_TOOL]
        assert stock_calls and _product_ids(stock_calls[-1]) == {ids["ped"], ids["cis"], ids["sc"]}, stock_calls

    def test_no_number_of_ours_and_no_ladder_block(self, session_factory, monkeypatch) -> None:
        from app.services.chatbot import answer_bridge

        seen: list[dict[str, Any]] = []
        real = answer_bridge._run_crossdomain_ladder

        def _spy(**kwargs):
            seen.append(dict(kwargs.get("item") or {}))
            return real(**kwargs)

        monkeypatch.setattr(answer_bridge, "_run_crossdomain_ladder", _spy)
        self._dealer(monkeypatch)
        result, *_ = self._ask_set(session_factory, monkeypatch, _dealer_rows({}, None), "zzt-d7")
        assert all(item.get("stock_availability") for item in seen), seen
        set_code = _said(result).removeprefix("How many units of ").removesuffix("?")
        assert not any(ch.isdigit() for ch in _said(result).replace(set_code, "")), _said(result)


class TestSetAnswerUnit:
    def test_a_tie_names_the_first_member(self) -> None:
        from app.services.chatbot.lanes.business import set_stock

        envelope = _compact({"0": (9, {"BRW": 9}), "1": (3, {"BRW": 3}), "2": (3, {"BRW": 3})})(["A", "B", "C"])
        text = set_stock.staff_set_answer(
            {"set_code": "S-RL", "members": [{"product_code": c, "quantity": 1} for c in "ABC"]}, envelope
        )
        assert text == "S-RL: 3 sets available (limited by B)\nBy location: BRW 3", text

    def test_a_discontinued_member_supplies_nothing(self) -> None:
        from app.services.chatbot.lanes.business import set_stock

        envelope = _compact({"0": (9, {"BRW": 9}), "1": (8, {"BRW": 8})})(["A", "B"])
        envelope["items"][1]["flags"] = {"discontinued": True}
        text = set_stock.staff_set_answer(
            {"set_code": "S-RL", "members": [{"product_code": c, "quantity": 1} for c in "AB"]}, envelope
        )
        assert text == "S-RL: 0 sets available (limited by B)", text

    def test_fractional_quantity_floors(self) -> None:
        from app.services.chatbot.lanes.business import set_stock

        envelope = _compact({"0": (9, {"BRW": 9}), "1": (10, {"BRW": 10})})(["A", "B"])
        text = set_stock.staff_set_answer(
            {"set_code": "S-RL", "members": [{"product_code": "A", "quantity": 1}, {"product_code": "B", "quantity": 1.5}]},
            envelope,
        )
        assert text.startswith("S-RL: 6 sets available (limited by B)"), text

    def test_no_answer_from_a_dealer_envelope(self) -> None:
        from app.services.chatbot.lanes.business import set_stock

        assert set_stock.staff_set_answer(
            {"set_code": "S", "members": [{"product_code": "A", "quantity": 1}]}, _availability(["A"])
        ) is None
