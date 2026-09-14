"""Lane 2 - multi-domain fan-out, WORLD reds (AC-1040 to 1053).

Written BEFORE any lane-2 code exists (Phase 2, test-first), from
`documentation/plans/chatbot/chatbot-focus-multi-domain-acceptance-criteria.md`
lines 209-254 and `PLAN-chatbot-focus-multi-domain.md`'s "Fan-out (lane 2)" section.

**The vehicle, and why it is not the `OwnerWorld` harness.** The `test_focus_worlds.py`
harness (lane 1) STUBS the business lane at the resolve+gate boundary
(`_owner_resolve_gate_bundle`) and feeds `complete_answer` a minimal `not_supported`
fragment, so it renders no real section and makes no real tool call - it grades MEMORY
(`focus`, `open_question`) only. Fan-out is exactly the two things that harness cannot
see: N real reads and N rendered sections. So these worlds drive the WHOLE turn -
`engine.run_turn` against the blank-schema Postgres fixture with only the injectable seams
faked - the same recipe `tests/chatbot/test_foundre_rung_end_to_end.py` uses to prove a
rung reaches the reply. The parser, the resolver and the MCP are faked from fixed values;
the intake flatten, the focus rules, `run_fetch`, `complete_answer`, the compose and the
session write all run for real.

**Every world here is RED by construction.** Lane 1 answers ONE domain per turn:
`domains_from_asks` sets `turn.o["domain_hint"] = named[0]` "until lane 2 fans out over the
list" (`dialogue/focus.py`), and `run_fetch` reads that single `domain_hint`, calls
`select_tool` once and records ONE `tool` trace event. A two-domain ask therefore produces
ONE read, ONE section and no incoming/order/promotion event - so every assertion below that
counts two-or-more reads, or that a second domain's tool ran, fails today for the right
reason: the fan-out loop does not exist. A failure for any OTHER reason (a seeding error, a
turn that never reaches `done`) is a defect in THIS file.

The deduper, the missed-domain team set and the ladder-outside-the-asked-set are pure and
are pinned in `tests/chatbot/test_fanout.py`; the escalate-offer RESOLUTION turns (a "1", a
team label, a bare "yes", a "no") are pinned there too on `open_question._team_pick`. These
worlds pin what only the whole turn can show: the reads, their order, their per-section date
filter, the binding, the denial section, and the offer CONSTRUCTION when a section missed.
AC-1054 is [FE][E2E] agent-browser and is out of scope here - a later browser evidence run
covers it.
"""
from __future__ import annotations

import itertools
import json
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from app.services.chatbot.contracts import DOMAIN_SPEC
from app.services.chatbot.lanes.business.services import (
    AnswerServices,
    FetchServices,
    ResolveGateServices,
)
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import (  # noqa: F401 - re-exported fixtures used by name
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)

_INVENTORY_TOOL = DOMAIN_SPEC["inventory"].tools[0]
_INCOMING_TOOL = DOMAIN_SPEC["incoming"].tools[0]
_ORDER_TOOL = DOMAIN_SPEC["order"].tools[0]
_PROMO_TOOL = DOMAIN_SPEC["promotion"].tools[0]
_PO_TOOL = DOMAIN_SPEC["purchase_order"].tools[0]
_COST_TOOL = DOMAIN_SPEC["purchase_cost"].tools[0]

# One monotonic messageId source across every driven turn in this module (Fix B).
_MSG_SEQ = itertools.count(1)


def _uuid_for(code: str) -> str:
    """A stable pseudo-uuid per code, so `product_ids` on a recorded call is checkable."""
    n = abs(hash(code)) % 10**12
    return f"00000000-0000-0000-0000-{n:012d}"


def _found(code: str, *, label: str = "Product Code") -> dict[str, Any]:
    """A found single-row envelope, the shape `output_structurer` reads as a HIT.

    The hit/miss signal a fan section reads is the SAME as the single-domain lane's:
    `output_structurer(envelope).has_result`, and `_extract_envelope` only treats a payload
    as a rendered result when it carries an `items` LIST (an `answers`-only payload reads as
    a MISS). Row shape mirrors `tests/chatbot/test_s6c_answer_lane.py::_row`.
    """
    return {
        "items": [{"fields": [{"key": "product_code", "label": label, "value": code}]}],
        "has_result": True,
    }


_MISS = {"items": [], "has_result": False}


def _ask(domain: str | None, *codes: str) -> dict[str, Any]:
    return {
        "domain": domain,
        "entities": [
            {"raw": c, "hint": "product", "canonical_code": c, "current_message": True}
            for c in codes
        ],
    }


def _v3_business(asks: list[dict[str, Any]], **over: Any) -> dict[str, Any]:
    """A v3 business-query emission over `asks`, with the three v3 signals in their
    not-answered / no-anaphora / no-reset default and every entity flattened onto the top
    level `entities` too (the shape the flatten reads)."""
    entities: list[dict[str, Any]] = []
    for a in asks:
        for e in a.get("entities") or []:
            if e not in entities:
                entities.append(e)
    emission = _parser_output(
        message_type="business_query",
        intent_hint="check_stock",
        domain_hint=(asks[0].get("domain") if asks else None),
        entities=entities,
        asks=asks,
        answers_open_question={
            "resolved": False,
            "picks": [],
            "yes_no": None,
            "free_text": None,
        },
        anaphora=False,
        topic_reset=False,
    )
    emission.update(over)
    return emission


def _resolve_entity_for(matches_by_code: dict[str, list[dict[str, Any]]]) -> Callable:
    """A fake `resolve_entity` that resolves exactly the codes handed to it. One exact
    match per code by default; a code mapped to two matches is AMBIGUOUS (AC-1049)."""

    def _resolve(body: dict[str, Any]) -> dict[str, Any]:
        resolutions = []
        for code, matches in matches_by_code.items():
            resolutions.append({"raw": code, "token": code, "matches": matches})
        return {
            "tokens": list(matches_by_code),
            "resolutions": resolutions,
            "unresolved_tokens": [],
        }

    return _resolve


def _one_match(code: str) -> list[dict[str, Any]]:
    return [
        {
            "uuid": _uuid_for(code),
            "entity_type": "product",
            "canonical_code": code,
            "match_tier": "exact",
        }
    ]


def _two_matches(code: str) -> list[dict[str, Any]]:
    return [
        {
            "uuid": _uuid_for(f"{code}-{suffix}"),
            "entity_type": "product",
            "canonical_code": f"{code}-{suffix}",
            "match_tier": "prefix",
        }
        for suffix in ("A", "B")
    ]


def _configure(session_factory) -> None:
    from app.models.user import SystemSetting

    set_chatbot_switches(session_factory, business_lane=True)
    db = session_factory()
    for row in db.query(SystemSetting).all():
        # `check_promotion` too: a promotion ask routes to that branch_kind, so without it
        # AC-1045's turn 2 ("promo for X") delegates instead of completing in-process.
        row.chatbot_completed_lanes = ["business_query", "check_promotion"]
        row.chatbot_crossdomain_ladder = {
            "inventory": ["incoming", "purchase_order"],
            "incoming": ["inventory", "purchase_order"],
        }
    db.commit()


class _Turn:
    """What one driven turn produced: the engine result, the joined reply text, the
    persisted `tool` trace events (name in order) and every recorded MCP call (name, args).
    """

    def __init__(self, result: Any, said: str, tool_events: list[str], calls: list) -> None:
        self.result = result
        self.said = said
        self.tool_events = tool_events
        self.calls = calls

    def call_args(self, tool: str) -> dict[str, Any] | None:
        for name, args in self.calls:
            if name == tool:
                return args
        return None


def _drive(
    session_factory,
    monkeypatch,
    stub_parser,
    stub_access,
    *,
    emission: dict[str, Any],
    matches_by_code: dict[str, list[dict[str, Any]]],
    tool_responses: dict[str, dict[str, Any]] | None = None,
    grants: list[str] | None = None,
    arm: dict[str, Any] | None = None,
) -> _Turn:
    from app.models.chatbot_turn import ChatbotTurn
    from app.services.chatbot import engine as engine_mod

    _configure(session_factory)
    if arm is not None:
        # Write the roster (and any focus slots) into the session BEFORE the turn runs -
        # the same deterministic arming `test_focus_worlds.py` uses (`_patch_owner_session`)
        # so the gate does not have to be tripped into producing a picker for a pick turn
        # to be graded. The seeded fixture has already created the contact row.
        _arm_session(session_factory, arm)
    responses = tool_responses or {}
    calls: list[tuple[str, dict[str, Any]]] = []

    def _mcp_call(name: str, args: dict[str, Any]) -> str:
        calls.append((name, dict(args)))
        return json.dumps(responses.get(name, _MISS))

    def _mcp_probe(name: str, args: dict[str, Any]) -> Any:
        calls.append((name, dict(args)))
        return responses.get(name, _MISS)

    bundle = ResolveGateServices(
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
        resolve_entity=_resolve_entity_for(matches_by_code),
        probe=lambda **_: None,
    )
    monkeypatch.setattr(
        engine_mod.business_services, "production_services", lambda db, *, space_id=None: bundle
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "fetch_services",
        lambda db: FetchServices(mcp_call=_mcp_call),
    )
    monkeypatch.setattr(
        engine_mod.business_services,
        "answer_services_for",
        lambda session_factory: AnswerServices(
            mcp_probe=_mcp_probe, family_fetch=lambda query: {"data": []}
        ),
    )

    stub_parser(emission, emits_v3=True)
    stub_access(attributes=list(grants) if grants is not None else None)

    # A UNIQUE messageId per driven turn: `run_turn` is idempotent on (contact, message_id),
    # so a second `_drive` call reusing `_envelope`'s fixed "ZZT-msg-1" would return turn 1's
    # cached result and never run - every two-turn world would grade turn 1 twice.
    envelope = _envelope()
    envelope.message["message"]["messageId"] = f"ZZT-fanout-msg-{next(_MSG_SEQ)}"
    result = engine_mod.run_turn(envelope, session_factory=session_factory)
    row = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.id == result.turn_id)
        .first()
    )
    events = [
        e.get("name")
        for e in (row.trace or [])
        if isinstance(e, dict) and e.get("kind") == "tool"
    ]
    said = "\n".join(
        [((result.reply or {}).get("text") or "")]
        + [a.get("text") or "" for a in (result.actions or []) if isinstance(a, dict)]
    )
    return _Turn(result, said, events, calls)


# --------------------------------------------------------------------------- #
# AC-1040 - one message, a stock section then an incoming section, two reads
# --------------------------------------------------------------------------- #


def test_ac1040_stock_and_eta_is_one_message_with_two_reads_in_order(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1040: "SRTWT2634 stock and eta" -> ONE message: a Stock section then an Incoming
    section, in that order, then one escalate line. TWO tool calls, two `tool` trace events.

    RED: today `run_fetch` reads only `domain_hint` (`inventory`), so there is ONE tool
    event and the incoming tool never runs.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", code), _ask("incoming", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _found(code), _INCOMING_TOOL: _found(code)},
    )
    assert turn.result.status == "done", turn.result.error
    assert turn.tool_events == [_INVENTORY_TOOL, _INCOMING_TOOL], (
        f"one read per asked domain, stock then incoming - got {turn.tool_events!r}"
    )
    assert turn.said.lower().count("escalate") <= 1, (
        "one message carries at most one escalate line, never one per section"
    )


# --------------------------------------------------------------------------- #
# AC-1046 - sections render in the dealer's (asks) order, never canonical
# --------------------------------------------------------------------------- #


def test_ac1046_eta_and_stock_reads_incoming_first(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1046: "eta and stock for X" reads incoming BEFORE inventory - the order follows
    `asks`, never a canonical domain order.

    RED: today only the first ask's domain (`incoming`) reads; asserting inventory also
    reads, second, fails.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("incoming", code), _ask("inventory", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _found(code), _INCOMING_TOOL: _found(code)},
    )
    assert turn.result.status == "done", turn.result.error
    assert turn.tool_events == [_INCOMING_TOOL, _INVENTORY_TOOL], (
        f"the reads follow the ask order, incoming first - got {turn.tool_events!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1042 - each section lists both products
# --------------------------------------------------------------------------- #


def test_ac1042_stock_and_eta_for_a_and_b_lists_both_in_each_section(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1042: "stock and eta for A and B" reads each domain over BOTH products.

    RED: today one read (inventory) over both, and no incoming read at all.
    """
    a, b = "SRTWT2634", "CWCX7605"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", a, b), _ask("incoming", a, b)]),
        matches_by_code={a: _one_match(a), b: _one_match(b)},
        tool_responses={_INVENTORY_TOOL: _found(a), _INCOMING_TOOL: _found(a)},
    )
    assert turn.result.status == "done", turn.result.error
    assert turn.tool_events == [_INVENTORY_TOOL, _INCOMING_TOOL]
    stock_ids = set((turn.call_args(_INVENTORY_TOOL) or {}).get("product_ids") or [])
    incoming_ids = set((turn.call_args(_INCOMING_TOOL) or {}).get("product_ids") or [])
    assert {_uuid_for(a), _uuid_for(b)} <= stock_ids, "the stock read covers both products"
    assert {_uuid_for(a), _uuid_for(b)} <= incoming_ids, (
        "the incoming read covers both products"
    )


# --------------------------------------------------------------------------- #
# AC-1041 - the one-turn binding, then a bare code next turn runs both
# --------------------------------------------------------------------------- #


def test_ac1041_stock_for_a_and_eta_for_b_binds_each_then_bare_c_runs_both(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1041: "stock for A and eta for B" reads stock over A ONLY and incoming over B
    ONLY (the one-turn binding). Turn 2's bare "C" runs C through BOTH domains.

    RED: today only the stock read runs, over A, and turn 2 runs one domain (or none).
    """
    a, b, c = "SRTWT2634", "CWCX7605", "SRTKS6091"
    turn1 = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", a), _ask("incoming", b)]),
        matches_by_code={a: _one_match(a), b: _one_match(b)},
        tool_responses={_INVENTORY_TOOL: _found(a), _INCOMING_TOOL: _found(b)},
    )
    assert turn1.result.status == "done", turn1.result.error
    assert turn1.tool_events == [_INVENTORY_TOOL, _INCOMING_TOOL]
    assert (turn1.call_args(_INVENTORY_TOOL) or {}).get("product_ids") == [_uuid_for(a)], (
        "the stock read is bound to A alone this turn"
    )
    assert (turn1.call_args(_INCOMING_TOOL) or {}).get("product_ids") == [_uuid_for(b)], (
        "the incoming read is bound to B alone this turn"
    )

    turn2 = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask(None, c)], intent_hint=None, domain_hint=None),
        matches_by_code={c: _one_match(c)},
        tool_responses={_INVENTORY_TOOL: _found(c), _INCOMING_TOOL: _found(c)},
    )
    assert turn2.result.status == "done", turn2.result.error
    assert set(turn2.tool_events) == {_INVENTORY_TOOL, _INCOMING_TOOL}, (
        f"a bare code runs every alive domain - got {turn2.tool_events!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1043 - a bare code reruns every alive domain for the new code
# --------------------------------------------------------------------------- #


def test_ac1043_bare_code_after_a_fanout_reruns_every_alive_domain(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1043: after a fan-out answer, a bare code reruns every alive domain for the new
    code.

    RED: today the second turn runs at most one domain.
    """
    a, c = "SRTWT2634", "SRTKS6091"
    _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", a), _ask("incoming", a)]),
        matches_by_code={a: _one_match(a)},
        tool_responses={_INVENTORY_TOOL: _found(a), _INCOMING_TOOL: _found(a)},
    )
    turn2 = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask(None, c)], intent_hint=None, domain_hint=None),
        matches_by_code={c: _one_match(c)},
        tool_responses={_INVENTORY_TOOL: _found(c), _INCOMING_TOOL: _found(c)},
    )
    assert turn2.result.status == "done", turn2.result.error
    assert set(turn2.tool_events) == {_INVENTORY_TOOL, _INCOMING_TOOL}
    assert _uuid_for(c) in ((turn2.call_args(_INVENTORY_TOOL) or {}).get("product_ids") or [])
    assert _uuid_for(c) in ((turn2.call_args(_INCOMING_TOOL) or {}).get("product_ids") or [])


# --------------------------------------------------------------------------- #
# AC-1044 - "PO?" after a fan-out narrows to one domain, keeps the product
# --------------------------------------------------------------------------- #


def test_ac1044_po_after_a_fanout_is_one_section_and_keeps_the_product(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1044: after a fan-out answer, "PO?" sets `focus.domains = [purchase_order]`, keeps
    the product and renders ONE section.

    RED: the first turn fans out (two reads) - which does not happen today - so the world
    fails at turn 1 already; turn 2 then pins the narrow-to-one-domain half.
    """
    code = "SRTWT2634"
    turn1 = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", code), _ask("incoming", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _found(code), _INCOMING_TOOL: _found(code)},
        grants=["purchase_orders.placed"],
    )
    assert turn1.tool_events == [_INVENTORY_TOOL, _INCOMING_TOOL], (
        f"turn 1 must fan out over both asked domains - got {turn1.tool_events!r}"
    )
    turn2 = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business(
            [_ask("purchase_order")], intent_hint="check_po", domain_hint="purchase_order"
        ),
        matches_by_code={code: _one_match(code)},
        tool_responses={_PO_TOOL: _found(code)},
        grants=["purchase_orders.placed"],
    )
    assert turn2.result.status == "done", turn2.result.error
    assert turn2.tool_events == [_PO_TOOL], (
        f"'PO?' narrows to the one PO read, product kept - got {turn2.tool_events!r}"
    )
    focus = _focus(session_factory)
    assert (focus.get("domains") or {}).get("value") == ["purchase_order"]
    assert _focus_product_codes(focus) == [code], "the product carries into the PO ask"


# --------------------------------------------------------------------------- #
# AC-1045 - "promo for X" after a fan-out replaces both domains and product
# --------------------------------------------------------------------------- #


def test_ac1045_promo_after_a_fanout_replaces_both_domains_and_product(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1045: "promo for CWCX7605" after a fan-out answer replaces both domains and the
    product.

    RED: turn 1 must fan out (two reads); turn 2 then pins the replacement.
    """
    a, b = "SRTWT2634", "CWCX7605"
    turn1 = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", a), _ask("incoming", a)]),
        matches_by_code={a: _one_match(a)},
        tool_responses={_INVENTORY_TOOL: _found(a), _INCOMING_TOOL: _found(a)},
    )
    assert turn1.tool_events == [_INVENTORY_TOOL, _INCOMING_TOOL], (
        f"turn 1 must fan out - got {turn1.tool_events!r}"
    )
    turn2 = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business(
            [_ask("promotion", b)], intent_hint="check_promotion", domain_hint="promotion"
        ),
        matches_by_code={b: _one_match(b)},
        tool_responses={_PROMO_TOOL: _found(b)},
    )
    assert turn2.result.status == "done", turn2.result.error
    assert turn2.tool_events == [_PROMO_TOOL]
    focus = _focus(session_factory)
    assert (focus.get("domains") or {}).get("value") == ["promotion"]
    assert _focus_product_codes(focus) == [b], "the product is replaced by the promo's"


# --------------------------------------------------------------------------- #
# AC-1052 - the date window only reaches domains whose tool takes one
# --------------------------------------------------------------------------- #


def test_ac1052_stock_and_do_last_month_dates_only_the_order_section(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1052: "stock and DO last month" filters the order section and leaves stock
    unfiltered.

    RED: today only the stock read runs (order never runs), so there is no dated order read.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business(
            [_ask("inventory", code), _ask("order", code)],
            date_filter_start="2026-08-01",
            date_filter_end="2026-08-31",
            date_mode="delivery",
        ),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _found(code), _ORDER_TOOL: _found(code)},
    )
    assert turn.result.status == "done", turn.result.error
    assert turn.tool_events == [_INVENTORY_TOOL, _ORDER_TOOL]
    order_args = turn.call_args(_ORDER_TOOL) or {}
    assert order_args.get("actual_delivery_date_from") == "2026-08-01", (
        "the order read is dated"
    )
    stock_args = turn.call_args(_INVENTORY_TOOL) or {}
    assert not any(
        k in stock_args for k in ("eta_from", "eta_to", "actual_delivery_date_from")
    ), f"the stock read stays unfiltered - got {stock_args!r}"


# --------------------------------------------------------------------------- #
# AC-1048 - a domain the contact is not granted renders its denial section
# --------------------------------------------------------------------------- #


def test_ac1048_an_ungranted_domain_renders_denial_and_the_others_still_read(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1048: a domain the contact is not granted renders its section as the existing
    one-line denial copy; the other sections render; no read runs for the denied domain.

    The denied domain here is `purchase_cost` (its grant `purchase_orders.cost` is the one
    `DOMAIN_GRANT_REQUIRED` gate lane 1 already enforces); the UAC's own example is a dealer
    lacking `purchase_orders.placed`, the same rule over `purchase_order`.

    RED: today `domain_hint` is the FIRST ask (`purchase_cost`), so `run_fetch`'s grant gate
    refuses the whole turn and the stock read never runs at all - asserting the stock tool
    IS read fails.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business(
            [_ask("purchase_cost", code), _ask("inventory", code)],
            intent_hint="check_po_cost",
            domain_hint="purchase_cost",
        ),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _found(code), _COST_TOOL: _found(code)},
        grants=[],  # the cost grant is NOT held
    )
    assert turn.result.status == "done", turn.result.error
    assert _INVENTORY_TOOL in turn.tool_events, (
        "the granted stock section must still read despite the denied cost section"
    )
    assert _COST_TOOL not in turn.tool_events, (
        "the denied domain runs no read - it renders the denial line instead"
    )


# --------------------------------------------------------------------------- #
# AC-1053 - no cap: a four-domain ask makes four reads
# --------------------------------------------------------------------------- #


def test_ac1053_a_four_domain_ask_makes_four_reads(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1053: no cap. A four-domain ask makes four tool calls and four trace events.

    RED: today one read.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business(
            [
                _ask("inventory", code),
                _ask("incoming", code),
                _ask("order", code),
                _ask("promotion", code),
            ]
        ),
        matches_by_code={code: _one_match(code)},
        tool_responses={
            _INVENTORY_TOOL: _found(code),
            _INCOMING_TOOL: _found(code),
            _ORDER_TOOL: _found(code),
            _PROMO_TOOL: _found(code),
        },
        grants=["purchase_orders.placed"],
    )
    assert turn.result.status == "done", turn.result.error
    assert turn.tool_events == [
        _INVENTORY_TOOL,
        _INCOMING_TOOL,
        _ORDER_TOOL,
        _PROMO_TOOL,
    ], f"four reads, no cap - got {turn.tool_events!r}"


# --------------------------------------------------------------------------- #
# AC-1047 - the deduper + the closing ladder (review findings 4, 5, 6)
# --------------------------------------------------------------------------- #


def test_ac1047_both_empty_climbs_the_ladder_to_po_once(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1047 (finding 4): "stock and eta for X" with BOTH sections empty must climb the
    ladder PAST the asked set to `purchase_order` (a rung outside `{inventory, incoming}`),
    and the closing escalate line must appear exactly once.

    RED: `fanout.ladder_rungs_outside` is defined but NEVER CALLED - the fan render
    (`_render_fan_sections`) has no closing ladder at all, so the PO tool never fires on a
    both-empty fan turn. Measured: the trace carries `[inventory, incoming]` and no PO
    event.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", code), _ask("incoming", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _MISS, _INCOMING_TOOL: _MISS, _PO_TOOL: _found(code)},
        grants=["purchase_orders.placed"],
    )
    assert turn.result.status == "done", turn.result.error
    assert _PO_TOOL in turn.tool_events, (
        "both asked sections empty must climb the ladder to purchase_order (outside the "
        f"asked set) - the ladder never ran: {turn.tool_events!r}"
    )
    reply = (turn.result.reply or {}).get("text") or ""
    assert reply.lower().count("would you like me to escalate") == 1, (
        f"the closing escalate line prints once, not per section: {reply!r}"
    )


def test_ac1047_stock_miss_with_incoming_folds_into_one_section(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1047 (finding 5): "stock and eta for X", no stock but incoming EXISTS -> ONE Stock
    section reading "No stock for X, but there is incoming: ..." and NO separate Incoming
    section (the shared deduper omits the already-printed `(X, incoming)` key).

    RED: the fan render prints a bare "No stock." miss line AND a separate "*Incoming:*"
    section - the incoming is never folded into the stock miss, so the fold connective the
    single-domain crossdomain path emits ("But there is INCOMING stock ...") is absent.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", code), _ask("incoming", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _MISS, _INCOMING_TOOL: _found(code)},
    )
    assert turn.result.status == "done", turn.result.error
    reply = (turn.result.reply or {}).get("text") or ""
    assert "there is incoming" in reply.lower(), (
        "the stock miss must fold the incoming in ('...but there is incoming: ...'), not "
        f"render a separate Incoming section: {reply!r}"
    )


def test_ac1047_consumed_pairs_are_recorded_on_the_trace(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1047 (finding 6): the turn trace lists the consumed `(entity, domain)` pairs the
    shared deduper printed, so the drawer's Cross-domain panel can show them (AC-1054).

    RED: the fan render uses `fanout.Consumed` but never records the pairs as a `consumed`
    trace event - the persisted trace carries only `focus`/`tool` events. (`consumed` is the
    tester's chosen event kind where the plan under-specifies it; a rename is fine.)
    """
    from app.models.chatbot_turn import ChatbotTurn

    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", code), _ask("incoming", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _found(code), _INCOMING_TOOL: _found(code)},
    )
    assert turn.result.status == "done", turn.result.error
    row = (
        session_factory()
        .query(ChatbotTurn)
        .filter(ChatbotTurn.id == turn.result.turn_id)
        .first()
    )
    trace = [e for e in (row.trace or []) if isinstance(e, dict)]
    consumed = [e for e in trace if e.get("kind") == "consumed"]
    assert consumed, (
        "the fan must record the consumed (entity, domain) pairs on the trace - only "
        f"{sorted({e.get('kind') for e in trace if e.get('kind')})!r} were recorded"
    )
    blob = json.dumps(consumed)
    assert "inventory" in blob and "incoming" in blob, (
        f"the consumed pairs must name their domains: {consumed!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1051 - the escalate offer: construction over the MISSED domains
# --------------------------------------------------------------------------- #


def test_ac1051_one_missed_section_offers_that_one_team_yes_no(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1051 (world 1 of 2, construction): "no stock but incoming found offers Warehouse
    only" - one section missed, so the offer is today's one-team yes/no
    (`inventory`'s team is `warehouse`).

    RED: today only the stock read runs; the incoming read that would make this a
    one-missed-of-two situation never happens, so the offer cannot be the fan-out's
    missed-set offer. Asserting both reads ran fails today.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", code), _ask("incoming", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _MISS, _INCOMING_TOOL: _found(code)},
    )
    assert turn.result.status == "done", turn.result.error
    assert turn.tool_events == [_INVENTORY_TOOL, _INCOMING_TOOL]
    oq = _open_question(session_factory) or {}
    assert oq.get("kind") == "team_pick", "one missed section opens a team_pick offer"
    assert oq.get("expects") == "yes_no", "one team is the yes/no offer (D5)"
    teams = [
        (o.get("team") or o.get("label"))
        for o in (oq.get("options") or [])
    ]
    assert teams == ["warehouse"], f"only the missed section's team is offered - {teams!r}"


def test_ac1051_two_missed_sections_offer_a_numbered_team_pick(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1051 (world 2 of 2, construction): both `inventory` and `incoming` missed, so the
    offer is a numbered `team_pick` over the deduped teams in section order (Warehouse then
    Purchasing), `expects: pick`, plus a "No it's okay" reply.

    RED: today only the stock read runs and the one-team legacy offer is armed with
    `expects: yes_no`; a two-option `pick` offer is never constructed.

    The resolution turns AC-1051 also names ("1" picks first, a team label picks by
    equality, a bare "yes" re-asks, "no" declines) are pinned on `open_question._team_pick`
    in `tests/chatbot/test_fanout.py`.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", code), _ask("incoming", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={_INVENTORY_TOOL: _MISS, _INCOMING_TOOL: _MISS, _PO_TOOL: _MISS},
        grants=["purchase_orders.placed"],
    )
    assert turn.result.status == "done", turn.result.error
    oq = _open_question(session_factory) or {}
    assert oq.get("kind") == "team_pick"
    assert oq.get("expects") == "pick", "two teams is a numbered pick, not a yes/no (D5)"
    teams = [(o.get("team") or o.get("label", "").lower()) for o in (oq.get("options") or [])]
    assert teams == ["warehouse", "purchasing"], (
        f"the deduped missed-domain teams, in section order - got {teams!r}"
    )
    # `quick_replies` is n8n's comma-STRING by contract (AC-507), never a list:
    # `console_service._quick_replies` drops a non-str and the escalation lane joins with
    # ", ". Iterating it would walk characters, so the string is coerced the same way the
    # send-action test (test_fanout.py) reads it.
    qr = (turn.result.reply or {}).get("quick_replies")
    quick = (qr if isinstance(qr, str) else ",".join(qr or [])).lower()
    assert "no it's okay" in quick, (
        f"a 'No it's okay' reply rides the numbered team offer - got {qr!r}"
    )
    assert "warehouse" in quick and "purchasing" in quick, (
        f"the two team labels ride the numbered offer - got {qr!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1049 / AC-1050 - the picker comes before the fan-out
# --------------------------------------------------------------------------- #


def test_ac1049_a_pick_on_a_fanout_ask_reruns_every_alive_domain(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1049: an ambiguous product on a fan-out ask offers ONE `product_pick`; the pick
    then fans out over every alive domain.

    The picker is ARMED deterministically (`test_focus_worlds.py`'s own approach), so the
    graded turn is the PICK: with a `product_pick` open over two rows and both `inventory`
    and `incoming` alive, "1" resolves row 1 and must then read BOTH alive domains. Driving
    the fake resolver to trip the gate's disambiguation is not what this AC is about, so it
    is not what the turn depends on.

    RED: today a pick reruns ONE alive domain (`focus-pick-reruns-the-alive-domain`), so
    only one tool event fires. Fanning the rerun over every alive domain is the lane-2 gap.
    """
    code = "SRTWC286"
    row_a, row_b = _roster_row(1, f"{code}-A"), _roster_row(2, f"{code}-B")
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        arm={
            "focus": {"domains": {"value": ["inventory", "incoming"], "set_at_turn": 1}},
            "open_question": {
                "kind": "product_pick",
                "options": [row_a, row_b],
                "expects": "pick",
                "asked_at_turn": 1,
                "asked_at": None,
                "payload": {},
            },
        },
        emission=_v3_business(
            [],
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            answers_open_question={
                "resolved": True,
                "picks": [1],
                "yes_no": None,
                "free_text": None,
            },
        ),
        matches_by_code={f"{code}-A": _one_match(f"{code}-A")},
        tool_responses={
            _INVENTORY_TOOL: _found(f"{code}-A"),
            _INCOMING_TOOL: _found(f"{code}-A"),
        },
    )
    assert turn.result.status == "done", turn.result.error
    assert set(turn.tool_events) == {_INVENTORY_TOOL, _INCOMING_TOOL}, (
        f"the pick fans out over every alive domain - got {turn.tool_events!r}"
    )


def test_ac1050_product_is_asked_before_tier(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """AC-1050: when a `tier_pick` (promotion) and a `product_pick` would both arise, the
    product is asked FIRST; the tier is asked on the following turn.

    Armed deterministically: a `product_pick` is open on a promotion ask (the product is
    still ambiguous), so a NEUTRAL follow-up that resolves nothing must leave the PRODUCT
    question open and must NOT swap in a `tier_pick` - the product is still what is being
    asked, tier waits its turn.

    This is expected to be a GREEN guard, not a red: while a product is unresolved the tier
    is not asked over it today, and the fan-out does not change that ordering. It is kept as
    a guard so a future change that asked the tier before the product would fail here.
    """
    code = "SRTWC286"
    row_a, row_b = _roster_row(1, f"{code}-A"), _roster_row(2, f"{code}-B")
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        arm={
            "focus": {"domains": {"value": ["promotion"], "set_at_turn": 1}},
            "open_question": {
                "kind": "product_pick",
                "options": [row_a, row_b],
                "expects": "pick",
                "asked_at_turn": 1,
                "asked_at": None,
                "payload": {},
            },
        },
        emission=_v3_business(
            [],
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            entities=[],
            answers_open_question={
                "resolved": False,
                "picks": [],
                "yes_no": None,
                "free_text": None,
            },
        ),
        matches_by_code={code: _two_matches(code)},
        tool_responses={_PROMO_TOOL: _found(code)},
    )
    assert turn.result.status in ("done", "delegated"), turn.result.error
    oq = _open_question(session_factory) or {}
    assert oq.get("kind") == "product_pick", (
        f"the product is still what is asked; tier is not asked over an unresolved product "
        f"- got {oq.get('kind')!r}"
    )


# --------------------------------------------------------------------------- #
# session readers
# --------------------------------------------------------------------------- #


def _session_variables(session_factory) -> dict[str, Any]:
    from sqlalchemy import text

    from tests.chatbot.test_engine import CONTACT_ID

    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": str(CONTACT_ID)},
    ).first()
    raw = row.session_vars if row is not None else {}
    stored = json.loads(raw) if isinstance(raw, str) else (raw or {})
    return stored.get("variables") or {}


def _arm_session(session_factory, patch: dict[str, Any]) -> None:
    from sqlalchemy import text

    from tests.chatbot.test_engine import CONTACT_ID

    db = session_factory()
    row = db.execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": str(CONTACT_ID)},
    ).first()
    raw = row.session_vars if row is not None else {}
    stored = json.loads(raw) if isinstance(raw, str) else (raw or {})
    variables = dict(stored.get("variables") or {})
    variables.update(patch)
    db.execute(
        text(
            "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
            "WHERE respond_io_id = :c"
        ),
        {"c": str(CONTACT_ID), "sv": json.dumps({**stored, "variables": variables})},
    )
    db.commit()


def _roster_row(idx: int, code: str) -> dict[str, Any]:
    return {
        "idx": idx,
        "label": code,
        "code": code,
        "uuid": _uuid_for(code),
        "entity_type": "product",
    }


def _focus(session_factory) -> dict[str, Any]:
    return _session_variables(session_factory).get("focus") or {}


def _open_question(session_factory) -> dict[str, Any] | None:
    return _session_variables(session_factory).get("open_question")


def _focus_product_codes(focus: dict[str, Any]) -> list[str] | None:
    slot = (focus.get("products") or {}).get("value")
    if not isinstance(slot, list):
        return None
    return [e.get("canonical_code") or e.get("raw") for e in slot if isinstance(e, dict)]
