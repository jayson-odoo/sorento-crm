"""Lane 2 - multi-domain fan-out, UNIT reds (AC-1040, 1047, 1051, 1053).

Written BEFORE any lane-2 code exists (Phase 2, test-first), from
`documentation/plans/chatbot/chatbot-focus-multi-domain-acceptance-criteria.md`
lines 209-254 and `PLAN-chatbot-focus-multi-domain.md`'s "Fan-out (lane 2)" section.

Every test here is expected to fail TODAY, and the docstring of each says why and with
which reason. The companion file `test_fanout_worlds.py` grades the same slice end to end
through `engine.run_turn` with a fake MCP; this file is the pure/near-pure half the plan's
own testing seams asked for ("`dialogue/*`: pure functions, pytest per rule").

Two red shapes live here:

* EXISTING seam, wrong answer today. `run_fetch` runs ONE domain per turn (it reads
  `parse_output.domain_hint`, which `domains_from_asks` sets to `named[0]` "until lane 2
  fans out over the list"), so a two-domain ask makes exactly ONE `tool` trace event. The
  no-cap and two-tool tests assert 2 or 4, which is red by construction. Likewise
  `open_question._team_pick` resolves a bare "yes" on a TWO-team offer as an escalation
  today; AC-1051 says it must re-ask - red on the existing handler.

* NEW pure surface, not written yet. The general deduper, the missed-domain team set and
  the ladder-outside-the-asked-set are described in the plan as pure helpers. This file
  imports them from a module `app.services.chatbot.lanes.business.fanout` that does not
  exist yet, so those tests fail with `ImportError` / `AttributeError` naming the missing
  symbol - the correct red reason.

  **The `fanout` module name and the three function signatures below are the TESTER's
  choice** where the plan under-specifies them (same precedent as
  `tests/chatbot/test_s6b_fetch_lane.py`'s own contract docstring): the plan names the
  behaviour (`printed: set[(entity id, domain)]`, `{DOMAIN_SPEC[d].escalation_team for d
  in MISSED} - {None}` deduped in section order, "the ladder climbs only to rungs OUTSIDE
  the asked set") but not the callables. The coder may adopt these or rename them and say
  so; a rename is not a drift.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.chatbot.contracts import DOMAIN_SPEC
from app.services.chatbot.dialogue import open_question as oq
from app.services.chatbot.lanes import business
from app.services.chatbot.lanes.business.services import FetchServices
from app.services.chatbot.trace import TurnTrace
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures used by name
    seeded,
    stub_access,
    stub_parser,
)
from tests.chatbot.test_fanout_worlds import (  # noqa: F401 - engine harness reused
    _INCOMING_TOOL as _WORLD_INCOMING_TOOL,
    _INVENTORY_TOOL as _WORLD_INVENTORY_TOOL,
    _PO_TOOL as _WORLD_PO_TOOL,
    _ask,
    _drive,
    _MISS,
    _found,
    _one_match,
    _v3_business,
)

# The two tools the stock/incoming pair answers from, off `DOMAIN_SPEC` (D9). Named here
# so a test asserts the ORDER of the tool events by the tool the domain owns, never by a
# literal repeated in five places.
_INVENTORY_TOOL = DOMAIN_SPEC["inventory"].tools[0]  # crm_inventory_stock_balance_list
_INCOMING_TOOL = DOMAIN_SPEC["incoming"].tools[0]  # crm_incoming_stock_list
_ORDER_TOOL = DOMAIN_SPEC["order"].tools[0]  # crm_order_management_orders_list
_PROMO_TOOL = DOMAIN_SPEC["promotion"].tools[0]  # crm_marketing_promotions_list

_UUID = "11111111-1111-1111-1111-111111111111"


def _found_envelope(code: str) -> str:
    """A found single-row envelope, the shape `parse_mcp_content` reads (AC-604 fixtures).

    `has_result: true` so the section is a HIT, not a miss - the fan-out tests here are
    about how many reads run and in what order, not about the miss ladder.
    """
    return json.dumps(
        {
            "answers": [
                {"fields": [{"key": "product_code", "label": "Product Code", "value": code}]}
            ],
            "has_result": True,
        }
    )


def _run_fetch_over_domains(
    domains: list[str],
    *,
    code: str = "SRTWC8517",
    date: str | None = None,
    granted: list[str] | None = None,
) -> tuple[TurnTrace, list[tuple[str, dict[str, Any]]]]:
    """Drive `run_fetch` once for a turn that ASKED `domains` (in order) about `code`.

    The payload carries every read a fan-out loop could plausibly consult, so the test is
    robust to whether the coder loops `focus.domains`, `parse.output.asks` or both: the
    `asks` list, the derived `domain_hint = domains[0]` (what the single-domain engine
    reads today), and the `_focus.domains.value` list lane 1 already persists. One product
    entity, already resolved in `gate.compatible_entities`, so the tool is actually called.
    """
    trace = TurnTrace()
    trace.start()
    calls: list[tuple[str, dict[str, Any]]] = []

    def _rec(name: str, args: dict[str, Any]) -> str:
        calls.append((name, dict(args)))
        return _found_envelope(code)

    entity = {"uuid": _UUID, "entity_type": "product", "code": code}
    asks = [
        {"domain": d, "entities": [{"raw": code, "hint": "product", "canonical_code": code}]}
        for d in domains
    ]
    output: dict[str, Any] = {"domain_hint": domains[0], "asks": asks}
    if date is not None:
        output["date_filter_start"] = date
        output["date_filter_end"] = date
        output["date_mode"] = "delivery"
    payload = {
        "_exit_kind": "continue",
        "gate": {"compatible_entities": [entity]},
        "ctx": {
            "parse": {"output": output, "_focus": {"domains": {"value": list(domains)}}},
            "access": {"attributes": list(granted or [])},
            "contact": {"id": "ZZT-fanout-contact"},
        },
    }
    business.run_fetch(
        payload, services=FetchServices(mcp_call=_rec), dry_run=False, trace=trace
    )
    return trace, calls


def _tool_names(trace: TurnTrace) -> list[str]:
    return [e.get("name") for e in trace.entries("tool")]


# --------------------------------------------------------------------------- #
# AC-1040 (execution half) + AC-1053 - no cap on the number of reads
# --------------------------------------------------------------------------- #


class TestOneReadPerAskedDomain:
    def test_stock_and_eta_makes_two_reads_in_ask_order(self) -> None:
        """AC-1040: "SRTWT2634 stock and eta" is TWO reads - one stock, one incoming - and
        two `tool` trace events, in the order the message asked (stock then incoming).

        RED today: `run_fetch` reads `domain_hint` (= `inventory`, the first ask) and calls
        exactly one tool, so `trace.entries("tool")` has length 1 and the incoming tool is
        never called. The fan-out loop over `focus.domains` is what this asserts and it does
        not exist yet.
        """
        trace, calls = _run_fetch_over_domains(["inventory", "incoming"])
        assert _tool_names(trace) == [_INVENTORY_TOOL, _INCOMING_TOOL], (
            f"one tool event per asked domain, in ask order - got {_tool_names(trace)!r}"
        )
        assert [name for name, _ in calls] == [_INVENTORY_TOOL, _INCOMING_TOOL]

    def test_a_four_domain_ask_makes_four_reads(self) -> None:
        """AC-1053: no cap. A four-domain ask makes four tool calls and four trace events.

        RED today: one event, for `inventory` only.
        """
        trace, calls = _run_fetch_over_domains(
            ["inventory", "incoming", "order", "promotion"]
        )
        assert _tool_names(trace) == [
            _INVENTORY_TOOL,
            _INCOMING_TOOL,
            _ORDER_TOOL,
            _PROMO_TOOL,
        ], f"four reads, one per domain, no cap - got {_tool_names(trace)!r}"
        assert len(calls) == 4


# --------------------------------------------------------------------------- #
# AC-1052 - the date window reaches only the domains whose tool takes one
# --------------------------------------------------------------------------- #


class TestDateWindowPerSection:
    def test_the_date_filters_the_order_read_and_not_the_stock_read(self) -> None:
        """AC-1052: "stock and DO last month" filters the order section and leaves stock
        unfiltered. `crm_order_management_orders_list` takes `actual_delivery_date_*`;
        `crm_inventory_stock_balance_list` is not in `fetch.DATE_PARAMS`, so its call must
        carry no date key.

        RED today: only the stock tool runs (order is never called), so there is no order
        read to carry the date at all - the assertion that the order call exists and is
        dated fails.
        """
        _, calls = _run_fetch_over_domains(["inventory", "order"], date="2026-08-01")
        by_tool = {name: args for name, args in calls}
        assert _ORDER_TOOL in by_tool, (
            "the order domain was asked and must be read - the fan-out did not run it"
        )
        assert by_tool[_ORDER_TOOL].get("actual_delivery_date_from") == "2026-08-01", (
            "the order read takes the date window"
        )
        stock_args = by_tool.get(_INVENTORY_TOOL, {})
        assert not any(
            k in stock_args for k in ("eta_from", "eta_to", "actual_delivery_date_from")
        ), f"the stock read must stay unfiltered - got {stock_args!r}"


# --------------------------------------------------------------------------- #
# AC-1051 - the escalate offer: the team_pick handler (D5, owner ruling)
# --------------------------------------------------------------------------- #


def _two_team_offer() -> list[dict[str, Any]]:
    """A `team_pick`'s options when TWO sections missed: Warehouse then Purchasing, numbered
    from 1 in section order (the deduped `escalation_team` of `inventory` then `incoming`).
    """
    return [
        {"idx": 1, "team": "warehouse", "label": "Warehouse"},
        {"idx": 2, "team": "purchasing", "label": "Purchasing"},
    ]


class TestTeamPickResolution:
    def test_one_picks_the_first_team(self) -> None:
        """AC-1051: on a two-team offer, "1" picks the first team (Warehouse). This half is
        already right on `_team_pick` today; it is asserted alongside the reask so the
        contract reads as one rule.
        """
        outcome = oq.resolve(
            "team_pick",
            {"picks": [1], "yes_no": None},
            _two_team_offer(),
            payload={"expects": "pick"},
        )
        assert outcome.resolved is True
        assert outcome.routing == {"suggested_team": "warehouse"}

    def test_a_team_label_picks_by_equality(self) -> None:
        """AC-1051: a team LABEL ("purchasing") picks that team by equality, not the first.

        The normalised answer carries the pick as the option index the label resolved to;
        "purchasing" is option 2, so `picks: [2]` must route to purchasing.
        """
        outcome = oq.resolve(
            "team_pick",
            {"picks": [2], "yes_no": None},
            _two_team_offer(),
            payload={"expects": "pick"},
        )
        assert outcome.resolved is True
        assert outcome.routing == {"suggested_team": "purchasing"}

    def test_a_bare_yes_on_a_two_team_offer_re_asks_rather_than_escalating(self) -> None:
        """AC-1051: "a bare 'yes' re-asks with the same buttons (handler outcome `reask`)".

        RED today: `_team_pick` sees `one_team is None` (two options) and falls through to
        the unconditional `if answer.get("yes_no") == "yes"` arm, which returns
        `resolved=True, escalate=True` and routes to `payload.get("team")`. That silently
        escalates to a team the customer never chose. The two-team offer must instead come
        back UNRESOLVED with a `reask` marker so the lane re-asks the same numbered buttons.
        """
        outcome = oq.resolve(
            "team_pick",
            {"picks": [], "yes_no": "yes"},
            _two_team_offer(),
            payload={"expects": "pick"},
        )
        assert outcome.resolved is not True, (
            "a bare yes on a 2+ team offer must NOT resolve - the customer named no team"
        )
        assert getattr(outcome, "escalate", None) is not True, (
            "a bare yes on a 2+ team offer must not escalate to a guessed team"
        )
        assert "reask" in (outcome.outcome or "").lower(), (
            f"the two-team yes re-asks the same buttons - got {outcome.outcome!r}"
        )

    def test_no_declines_the_two_team_offer(self) -> None:
        """AC-1051: "no" renders the declined copy. Asserted so the decline path is pinned
        beside the reask (this half is already right on `_team_pick`).
        """
        outcome = oq.resolve(
            "team_pick",
            {"picks": [], "yes_no": "no"},
            _two_team_offer(),
            payload={"expects": "pick"},
        )
        assert outcome.resolved is True
        assert getattr(outcome, "declined", None) is True


# --------------------------------------------------------------------------- #
# AC-1051 - the team SET over the MISSED domains (new pure helper)
# --------------------------------------------------------------------------- #


class TestEscalationTeamSet:
    """`{DOMAIN_SPEC[d].escalation_team for d in MISSED} - {None}`, deduped, in section
    order (plan, "Fan-out (lane 2)"). Imported from the not-yet-written `fanout` module -
    RED with `ImportError`/`AttributeError` today. The name is the tester's choice.
    """

    def test_two_missed_domains_yield_their_two_teams_in_order(self) -> None:
        from app.services.chatbot.lanes.business import fanout

        assert fanout.escalation_teams(["inventory", "incoming"]) == [
            "warehouse",
            "purchasing",
        ]

    def test_only_the_missed_domain_contributes_a_team(self) -> None:
        """AC-1051: "no stock but incoming found offers Warehouse only" - only `inventory`
        missed, so only its team appears.
        """
        from app.services.chatbot.lanes.business import fanout

        assert fanout.escalation_teams(["inventory"]) == ["warehouse"]

    def test_teams_are_deduped_and_none_is_dropped(self) -> None:
        """`purchase_order` and `incoming` both route to `purchasing`; the set collapses to
        one. A domain whose `escalation_team` is `None` contributes nothing.
        """
        from app.services.chatbot.lanes.business import fanout

        assert fanout.escalation_teams(["incoming", "purchase_order"]) == ["purchasing"]
        assert fanout.escalation_teams(["portal_link"]) == []


# --------------------------------------------------------------------------- #
# AC-1047 - the general deduper, keyed (entity id, domain) (new pure helper)
# --------------------------------------------------------------------------- #


class TestTheGeneralDeduper:
    """One deduper `printed: set[(entity id, domain)]`, shared by every section and every
    ladder rung (D12). Imported from `fanout` - RED (`ImportError`) today. Names are the
    tester's choice; the behaviour is the plan's.
    """

    def test_a_pair_prints_once_then_is_skipped(self) -> None:
        from app.services.chatbot.lanes.business import fanout

        printed = fanout.Consumed()
        assert printed.seen("SRTWT2634", "inventory") is False
        printed.add("SRTWT2634", "inventory")
        assert printed.seen("SRTWT2634", "inventory") is True

    def test_the_key_is_the_pair_not_the_entity_alone(self) -> None:
        """The SAME entity under a DIFFERENT domain is a different fact and prints (a stock
        line and an incoming line for one product are both wanted).
        """
        from app.services.chatbot.lanes.business import fanout

        printed = fanout.Consumed()
        printed.add("SRTWT2634", "inventory")
        assert printed.seen("SRTWT2634", "incoming") is False

    def test_a_rung_and_a_section_share_the_one_set(self) -> None:
        """A fact a SECTION printed for (X, purchase_order) is skipped by a later LADDER
        rung for the same pair - the whole point of one shared set rather than two.
        """
        from app.services.chatbot.lanes.business import fanout

        printed = fanout.Consumed()
        printed.add("SRTWT2634", "purchase_order")  # a section printed it
        assert printed.seen("SRTWT2634", "purchase_order") is True  # the rung skips it


# --------------------------------------------------------------------------- #
# AC-1047 - the closing ladder climbs only to rungs OUTSIDE the asked set
# --------------------------------------------------------------------------- #


class TestLadderOutsideTheAskedSet:
    """After the sections, the ladder climbs only to rungs OUTSIDE the asked set, once
    (plan). Imported from `fanout` - RED (`ImportError`) today. Name is the tester's choice.
    """

    def test_a_stock_and_eta_ask_climbs_only_to_purchase_order(self) -> None:
        """Both `inventory` and `incoming` were asked, so neither is a NEW rung; the only
        rung left in the shipped ladder is `purchase_order`.
        """
        from app.services.chatbot.lanes.business import fanout

        ladder = {
            "inventory": ["incoming", "purchase_order"],
            "incoming": ["inventory", "purchase_order"],
        }
        assert fanout.ladder_rungs_outside(["inventory", "incoming"], ladder) == [
            "purchase_order"
        ]

    def test_a_rung_already_in_the_asked_set_is_not_reclimbed(self) -> None:
        """Asking `inventory`, `incoming` AND `purchase_order` leaves the ladder with no new
        rung at all - nothing outside the asked set.
        """
        from app.services.chatbot.lanes.business import fanout

        ladder = {
            "inventory": ["incoming", "purchase_order"],
            "incoming": ["inventory", "purchase_order"],
        }
        assert (
            fanout.ladder_rungs_outside(
                ["inventory", "incoming", "purchase_order"], ladder
            )
            == []
        )


# --------------------------------------------------------------------------- #
# AC-1051 (finding 7) - the two-team offer's quick replies must reach the SEND
# action, the channel the customer actually receives, not only the armed
# open_question.options.
# --------------------------------------------------------------------------- #


def test_two_team_offer_quick_replies_reach_the_send_action(
    session_factory, seeded, stub_parser, stub_access, system_settings_row, monkeypatch
) -> None:
    """A 2+ team escalate offer (both `inventory` and `incoming` missed -> Warehouse and
    Purchasing) must put its numbered quick replies on the `send_message` action, not only
    on the armed `open_question.options`.

    RED: `_render_fan_sections` patches `quick_replies` onto a COPY of `completed.reply`
    AFTER `complete_turn` has already composed the `send_message` action (with
    `compose_send_action=True`), so the action the customer's channel receives carries
    `quick_replies = None` - the buttons never reach WhatsApp.
    """
    code = "SRTWT2634"
    turn = _drive(
        session_factory,
        monkeypatch,
        stub_parser,
        stub_access,
        emission=_v3_business([_ask("inventory", code), _ask("incoming", code)]),
        matches_by_code={code: _one_match(code)},
        tool_responses={
            _WORLD_INVENTORY_TOOL: _MISS,
            _WORLD_INCOMING_TOOL: _MISS,
            _WORLD_PO_TOOL: _MISS,
        },
        grants=["purchase_orders.placed"],
    )
    assert turn.result.status == "done", turn.result.error
    send = next(
        (
            a
            for a in (turn.result.actions or [])
            if isinstance(a, dict) and a.get("kind") == "send_message"
        ),
        None,
    )
    assert send is not None, "the fan turn must emit a send_message action"
    qr = send.get("quick_replies")
    qr_text = qr if isinstance(qr, str) else ",".join(qr or [])
    assert "Warehouse" in qr_text and "Purchasing" in qr_text, (
        "the numbered team quick replies must ride the send_message action the customer "
        f"actually receives, not only the armed open_question: {send!r}"
    )
