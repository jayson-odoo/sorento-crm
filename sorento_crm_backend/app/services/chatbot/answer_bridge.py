"""The bridge between the new turn engine and production's own answer half
(PLAN-chatbot-answer-half-reattach.md slice R3; AC-1683, AC-1684, AC-1694, AC-1697,
AC-1698).

One rule: the new engine decides WHICH turn this is; production decides WHAT the reply
says. `question_for` covers the two resolver exits a single-domain business turn can
raise BEFORE a fetch ever runs - `access_ask` (the price-tier picker) and `offer` (the
gate's own ambiguous-customer / ambiguous-product picker) - by calling the KEPT
production composers with the arguments `complete_answer` gave them, unchanged. The
"miss" and "hit" arms are R4 and R5's own territory; `question_for` returns `None`
outside its two arms so the caller falls back to `turn/compose.py` for everything else
(a multi-domain plan, a lane question, a team pick).

**Bridge home, captain ruling 20 Sep 2026**: this module lives OUTSIDE `turn/`, as a
sibling of `turn_runtime.py` (the existing impure adaptor between the pure core and the
kept `lanes/business` + `tail` seams) - `turn/`'s own purity guard
(`test_rearch_s2_apply_is_pure.py`) forbids any file under that package from importing
`chatbot.tail`, and this module imports `tail.outcome` / `tail.reply_ladder` freely, by
design. No file under `turn/` may import this module either
(`test_rearch_r3_answer_bridge.py::TestTurnPackagePurity`).

**Access arm has two triggers, exactly production `complete_answer:1578-1588`**:
`exit_kind == "access_ask"` (the resolver's own exit for a contact with NO access rows
configured at all) OR the fetch fragment's own `_fetch_arm == "tier-ask"` (the real
"entitled, must pick a tier" path - `resolve_gate.run` exits `"continue"` here; the ASK
is decided one step later, inside `lanes.business.run_fetch`'s own tier-ask arm, once
the per-tier promotion probe has run - that is where the has/no-promotion stamps come
from). `tier_source` is `fetch` on the second trigger, `payload` on the first - measured
off `lanes/business/__init__.py::run_fetch`'s own `fetch_result` shape.

**MEASURED TRAP**: `answer.access_level_choice_message`'s own `tier_last_result_set`
rows carry `entity_type: "access_tier"` (`answer.py:324`), which
`turn/apply.py::_set_kind_field` does not recognise - only the literal `"tier"` reaches
`focus.tier` (`_CODE_ONLY_FIELDS`). Every tier option this bridge mints is rewritten to
`entity_type: "tier"` before it goes anywhere near `pending.ask`.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import session_state
from app.services.chatbot.lanes.business import answer as answer_mod
from app.services.chatbot.tail import outcome as outcome_mod
from app.services.chatbot.tail import reply_ladder
from app.services.chatbot.turn import compose as turn_compose
from app.services.chatbot.turn import pending

# AC-1691's umbrella: no roster is ever asked with fewer than two options, in any
# domain and for any entity kind - `narrow.decide`'s own rule for every other roster
# kind, applied here too.
_MIN_ROSTER_OPTIONS = 2


def _compose_text(lane_item: dict[str, Any], *, ctx: Any, canned: Any, **catalog_kwargs: Any) -> str:
    """`tail/outcome.escalate_catalog` + `tail/outcome.build_outcome` +
    `tail/reply_ladder.compose_reply`, the SAME chain `complete_answer` walks for every
    canned/business reply - the plan's own "text = tail/outcome.escalate_catalog +
    tail/reply_ladder.compose_reply" line."""
    catalog = outcome_mod.escalate_catalog(lane_item, ctx, canned, **catalog_kwargs)
    built = outcome_mod.build_outcome([{"json": catalog}], {"escalate-catalog": catalog})
    return reply_ladder.compose_reply(built[0]["json"]["outcome"])["text"]


def _tier_options(rows: list[dict[str, Any]], *, asked_at_turn: int | None) -> pending.Pending | None:
    """`tier_last_result_set` rows -> a `tier_pick` `Pending`, or `None` when fewer than
    two tiers are on offer (AC-1691) - the caller then has a text-only `Answer`, settling
    the single tier outright rather than asking about it."""
    fixed_rows = [{**row, "entity_type": "tier"} for row in rows]
    options = [
        option
        for option in (
            session_state._legacy_option(row, "tier_pick", i + 1)
            for i, row in enumerate(fixed_rows)
        )
        if option
    ]
    if len(options) < _MIN_ROSTER_OPTIONS:
        return None
    return pending.ask("tier_pick", options, asked_at_turn=asked_at_turn)


def _access_ask_answer(
    payload: dict[str, Any] | None,
    *,
    fetch: dict[str, Any] | None,
    parser: dict[str, Any] | None,
    ctx: Any,
    canned: Any,
    asked_at_turn: int | None,
) -> turn_compose.Answer:
    tier_source = fetch if isinstance(fetch, dict) and fetch.get("_fetch_arm") == "tier-ask" else payload
    lane_item = {
        **answer_mod.access_level_choice_message(tier_source, parser=parser),
        "branch_kind": "access_choice",
    }
    text = _compose_text(lane_item, ctx=ctx, canned=canned, access_choice=lane_item)
    rows = lane_item.get("tier_last_result_set")
    rows = rows if isinstance(rows, list) else []
    question = _tier_options(rows, asked_at_turn=asked_at_turn)
    return turn_compose.Answer(text=text, question=question)


def _offer_answer(
    payload: dict[str, Any],
    *,
    parser: dict[str, Any] | None,
    ctx: Any,
    canned: Any,
    asked_at_turn: int | None,
) -> turn_compose.Answer:
    lane_item = {**payload, "branch_kind": "not_found"}
    text = _compose_text(lane_item, ctx=ctx, canned=canned, incoming_picker=lane_item)
    entities = [e for e in (payload.get("compatible_entities") or []) if isinstance(e, dict)]
    question = None
    if len(entities) >= _MIN_ROSTER_OPTIONS:
        entity_kind = entities[0].get("entity_type") or "product"
        kind = f"{entity_kind}_pick"
        rows = [
            {
                "idx": i + 1,
                "label": e.get("title") or e.get("code"),
                "uuid": e.get("uuid"),
                "entity_type": e.get("entity_type"),
            }
            for i, e in enumerate(entities)
        ]
        options = [
            option
            for option in (
                session_state._legacy_option(row, kind, i + 1) for i, row in enumerate(rows)
            )
            if option
        ]
        if len(options) >= _MIN_ROSTER_OPTIONS:
            question = pending.ask(kind, options, asked_at_turn=asked_at_turn)
    return turn_compose.Answer(text=text, question=question)


def question_for(
    payload: dict[str, Any] | None,
    *,
    fetch: dict[str, Any] | None = None,
    parser: dict[str, Any] | None,
    ctx: Any,
    canned: Any,
    asked_at_turn: int | None,
) -> turn_compose.Answer | None:
    """The ONE seam (PLAN "Design"): `None` outside its two arms, so the caller falls
    back to `turn/compose.py` for a multi-domain plan, a lane question or a team pick.

    `fetch` is `lanes.business.run_fetch`'s own tier-ask fragment (its `"fetch"` key,
    not the wrapper dict `run_fetch` returns) - see the module docstring for the
    measured shape. `payload` is the resolver's own exit item
    (`ResolveOutcome.payload`).
    """
    if not isinstance(payload, dict):
        return None
    exit_kind = payload.get("_exit_kind")
    fetch_arm = fetch.get("_fetch_arm") if isinstance(fetch, dict) else None
    if exit_kind == "access_ask" or fetch_arm == "tier-ask":
        return _access_ask_answer(
            payload, fetch=fetch, parser=parser, ctx=ctx, canned=canned, asked_at_turn=asked_at_turn
        )
    if exit_kind == "offer":
        return _offer_answer(payload, parser=parser, ctx=ctx, canned=canned, asked_at_turn=asked_at_turn)
    return None
