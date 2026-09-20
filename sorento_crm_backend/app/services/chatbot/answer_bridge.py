"""The bridge between the new turn engine and production's own answer half
(PLAN-chatbot-answer-half-reattach.md slices R3 and R4; AC-1683, AC-1684, AC-1694,
AC-1697, AC-1698, AC-1699 to AC-1705).

One rule: the new engine decides WHICH turn this is; production decides WHAT the reply
says. `question_for` covers the two resolver exits a single-domain business turn can
raise BEFORE a fetch ever runs - `access_ask` (the price-tier picker) and `offer` (the
gate's own ambiguous-customer / ambiguous-product picker). `answer_for` (R4) covers the
MISS half - a genuine absence, either at the resolver's own exit or discovered once a
fetch has actually run - by calling production's own miss chain
(`not_found_error_message` -> `miss_suggest.run_miss_lane`) and the SAME text ladder
`question_for` uses (`tail.reply.compose_from_fragments`, R4's own extraction of
`engine.run_tail`'s body, so both walk one function, never two). Both functions return
`None` outside their own territory, so the caller falls back to `turn/compose.py` for
everything else (a multi-domain plan, a lane question, a team pick, R5's own hit arm).

**Bridge home, captain ruling 20 Sep 2026**: this module lives OUTSIDE `turn/`, as a
sibling of `turn_runtime.py` (the existing impure adaptor between the pure core and the
kept `lanes/business` + `tail` seams) - `turn/`'s own purity guard
(`test_rearch_s2_apply_is_pure.py`) forbids any file under that package from importing
`chatbot.tail`, and this module imports `tail.outcome` / `tail.reply` / `tail.compose`
freely, by design. No file under `turn/` may import this module either
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

**The miss arm's two triggers (R4), exactly `lanes/business/__init__.py::
complete_answer:1650`**:

  (a) `payload["_exit_kind"] == "not_found"` - the resolver's own exit, nothing resolved
      at all (H11's zero-tool case). No fetch has run; `envelope` is `None`.
  (b) `envelope["raw_fragment"]` is the error arm `business._error_fragment(...,
      outcome="not_found")` mints - a genuine absence discovered once a fetch actually
      ran (`turn_runtime.make_tool_runner.runner`'s own "answered unfiltered" fallback,
      or a document tool refused for want of a filter). `payload` handed to the miss
      chain folds the fetch item in exactly as `complete_answer`'s own `delegate_payload`
      does: `{**payload, "fetch": fetch_item}`.

`answer_for` returns `None` for a hit-shaped envelope (R5's own arm), an `access_denied`
error arm (that refusal path is unchanged) and an infrastructure error arm (`outcome`
neither `not_found` nor `access_denied` - `complete_answer` RAISES on this arm today; a
caller reaching it here must not quietly render it as a miss). A multi-domain plan is a
CALLER-side decision (the engine never calls the bridge for one) and keeps `turn/
compose.py`'s own copy (owner ruling, Hazards section).

**Every question the miss arm raises is a `Pending` minted by `turn.pending.ask`
(AC-1684)**, in precedence order (mirrors `engine.run_tail`'s own `_question_offered`,
the same precedence `tail.reply_ladder.compose_reply`'s `result_set` reads):

  1. The CS member offer (`producers["build-cs-member-offer"]`), when it built one -
     `member_offer`, options from `cs_last_result_set`, `respond_user_id` on the
     payload so an answering turn can assign by it.
  2. A did-you-mean / require-specific roster (`offer["suggest_last_result_set"]`) -
     `{entity_kind}_pick` (contract 36 roster), options in printed order, each carrying
     the SAME has/no stamp the text prints (derived from the composed text itself - none
     of `run_miss_lane`'s own roster rows carry a `stamp` field, only the rendered line
     does), `payload["domain"]` / `payload["escalate_offered"]` so a pick continues the
     ORIGINAL ask (AC-1704).
  3. A plain escalate offer with no roster at all (`producers["escalate-catalog"].
     is_escalate_offer`) - `team_pick`, the same one-option "Yes" shape `engine.run_tail`'s
     own `_question_offered` mints for a canned lane's escalate catalog.

**AC-1705's cross-domain stock ladder** rides on every miss attempt (item 2's `_fold_
crossdomain_ladder`): `answer.crossdomain_zeroset` / `run_crossdomain` already gate
themselves to `domain_hint in ("incoming", "inventory")` and a genuinely resolved,
probeable product, so calling them unconditionally is a no-op (no MCP call at all) for
every other domain's miss. `tail.compose.crossdomain_compose` folds the rendered block
above the escalate marker, exactly as it would for the (dead, pre-rearch) `complete_turn`
path - this is genuinely NEW wiring for the single-domain miss, not a reattachment of
something the new engine already ran (measured: neither function has a live caller on
this branch before R4).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping

from app.services.chatbot.lanes.business import answer as answer_mod
from app.services.chatbot.lanes.business import miss_suggest as miss_mod
from app.services.chatbot.lanes.business import services as business_services
from app.services.chatbot.lanes.business.services import AnswerServices
from app.services.chatbot.tail import compose as tail_compose
from app.services.chatbot.tail import reply as reply_mod
from app.services.chatbot.tail import scope_block
from app.services.chatbot.turn import compose as turn_compose
from app.services.chatbot.turn import pending

# AC-1691's umbrella: no roster is ever asked with fewer than two options, in any
# domain and for any entity kind - `narrow.decide`'s own rule for every other roster
# kind, applied here too.
_MIN_ROSTER_OPTIONS = 2

_ORDER_DATE_LINE_RE = re.compile(r"^Order date: .*$")

logger = logging.getLogger(__name__)


def apply_scope_block(
    answer: turn_compose.Answer,
    *,
    domain: str | None,
    qf: Mapping[str, Any] | None,
    gate_json: Mapping[str, Any] | None,
    resolver_json: Mapping[str, Any] | None,
    focus_customers: Any = None,
    focus_products: Any = None,
) -> turn_compose.Answer:
    """R5's HIT arm (AC-1694 to AC-1696): a single-domain ORDER fetch that genuinely
    found rows opens with the Customer/Product/Dates scope block ahead of
    production's own intro. The caller's own `Answer` (from `turn/compose.py`,
    unchanged - this never touches `sections`/`question`/`offer`/`files`/`actions`)
    is returned AS-IS for every other domain (`tail.scope_block.search_scope_header`
    returns `None`).

    `turn/compose.py`'s own per-section `date_line` decoration
    (`"Order date: ..."`, one line under the header) restates the SAME window the
    scope block's own `Dates:` line already states, once this arm applies - stripped
    here rather than suppressed at its own seam, which would need to know in advance
    whether this bridge was about to run.

    BEST EFFORT, main's own wrapper verbatim in intent ("a disclosure bug must never
    block the answer", `origin/main:tail/compile_state.py::_search_scope_header`): the
    port had no wrapper of its own, so a raise anywhere in here was caught by
    `engine.py`'s fetch/compose handler instead and turned a turn that had genuinely
    found rows into `status="failed"` with "Could not look an answer up." The rows go
    out without the header rather than not at all.
    """
    try:
        scope = scope_block.search_scope_header(
            domain=domain,
            qf=qf,
            gate_json=gate_json,
            resolver_json=resolver_json,
            focus_customers=focus_customers,
            focus_products=focus_products,
        )
        if scope is None or not answer.text:
            return answer
        from dataclasses import replace

        lines = [line for line in answer.text.split("\n") if not _ORDER_DATE_LINE_RE.match(line)]
        return replace(answer, text=f"{scope}\n\n" + "\n".join(lines))
    except Exception:  # noqa: BLE001 - a disclosure bug must never block the answer
        logger.warning("chatbot: the search-scope header did not render", exc_info=True)
        return answer


def _compose_text(lane_item: dict[str, Any], *, ctx: Any, canned: Any, db: Any, **values: Any) -> str:
    """`tail.reply.compose_from_fragments`, the SAME chain `complete_answer` walks for
    every canned/business reply - the plan's own "text = tail/outcome.escalate_catalog +
    tail/reply_ladder.compose_reply" line, extracted once (R4) so no arm in this module
    keeps a second copy of the ladder."""
    result = reply_mod.compose_from_fragments(lane_item, ctx, canned, values, db=db)
    return result.get("text") or ""


def _roster_option(row: dict[str, Any], *, kind: str, position: int) -> dict[str, Any] | None:
    """One roster row -> a `Pending` option, in the SAME shape `turn/narrow.py::_options`
    produces (contract 103) - EVERY arm this module mints a roster from shares this one
    builder (coordinator add-on, 20 Sep 2026: `session_state._legacy_option`'s own
    `uuids` only fills through a customer-only `families` lookup this module never
    supplies, so a lone product roster carried no `uuids` at all).

    `uuids` is always populated: a resolver/candidate row's own family (`row["uuids"]`)
    when it has one, else the single `uuid` standing for itself - never empty when a
    `uuid` exists, matching `narrow._options`'s own rule that a lone candidate is still
    a family of one.
    """
    if not isinstance(row, dict):
        return None
    uuid_val = row.get("uuid")
    code = row.get("code") or row.get("canonical_code") or row.get("product") or row.get("value")
    label = row.get("title") or row.get("name") or row.get("label") or code
    family = row.get("uuids")
    uuids = list(family) if isinstance(family, list) and family else ([uuid_val] if uuid_val else [])
    option: dict[str, Any] = {
        "position": int(row.get("idx") or position),
        "label": label,
        "entity_type": row.get("entity_type") or kind,
        "uuid": uuid_val,
        "uuids": uuids,
        "payload": {},
    }
    if code is not None:
        option["code"] = code
    # AC-1695: the SAME field `turn/narrow.py::_options` carries beside `label` - a
    # customer's own human name, separate from its code, so `turn/apply.py::
    # _answer_pending`'s own pick-to-entity conversion (which reads `option.get(
    # "name")` specifically, not "label") can put the NAME on the focus entity a
    # pick just settled, not the account code nobody typed. Missing here left a
    # picked customer's own scope-block line reading its code back at the
    # customer who just read the name on the roster. `title` first: the gate's own
    # ambiguous-customer picker rows (`resolve_gate.if_customer_picker`) carry the
    # printed name under `title`, never `name` (measured live writing this fix).
    name = row.get("title") or row.get("name")
    if name:
        option["name"] = name
    stamp = row.get("stamp")
    if stamp:
        option["stamp"] = stamp
    for key in ("value", "team"):
        if row.get(key) is not None:
            option["payload"][key] = row[key]
    return option


def _tier_options(rows: list[dict[str, Any]], *, asked_at_turn: int | None) -> pending.Pending | None:
    """`tier_last_result_set` rows -> a `tier_pick` `Pending`, or `None` when fewer than
    two tiers are on offer (AC-1691) - the caller then has a text-only `Answer`, settling
    the single tier outright rather than asking about it."""
    fixed_rows = [{**row, "entity_type": "tier"} for row in rows]
    options = [
        option
        for option in (
            _roster_option(row, kind="tier_pick", position=i + 1)
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
    db: Any,
    asked_at_turn: int | None,
) -> turn_compose.Answer:
    if isinstance(fetch, dict) and fetch.get("_fetch_arm") == "tier-ask":
        tier_source = fetch
    elif isinstance(payload, dict) and payload.get("_exit_kind") == "access_ask":
        # `resolve_gate.run`'s own `exit_item` spreads `tier_gate_out` FIRST for this
        # exit (`resolve_gate.py`'s own access_ask arm), so `payload` itself already
        # carries `name`/`entitled_tiers` at the top level.
        tier_source = payload
    else:
        # R5 (AC-1697's own tier axis, the "product_attachment roster copy" class of
        # gap on the ACCESS side): a resolver `not_found` exit for a promotion ask
        # still carries the SAME tier-gate read (`resolve_gate.run`'s `entry ==
        # "access_check"` runs before the product is even looked up), just nested
        # under `payload["tier_gate"]` rather than flattened - the product genuinely
        # not resolving is not a verdict on which access levels this contact holds.
        # Measured live: `TestRegressionGuardsMustStayGreen::
        # test_promotion_ask_for_a_not_found_product_still_shows_the_three_tier_picker`,
        # a contact entitled to 3 tiers whose typed product never resolves at all
        # (`_exit_kind == "not_found"`, `tier_gate.tier_ask is True`) used to fall
        # through to `turn/narrow.py`'s generic, entitlement-blind tier ask instead of
        # this composer.
        tier_source = payload.get("tier_gate") if isinstance(payload, dict) else None
    lane_item = {
        **answer_mod.access_level_choice_message(tier_source, parser=parser),
        "branch_kind": "access_choice",
    }
    text = _compose_text(lane_item, ctx=ctx, canned=canned, db=db, access_choice=lane_item)
    rows = lane_item.get("tier_last_result_set")
    rows = rows if isinstance(rows, list) else []
    question = _tier_options(rows, asked_at_turn=asked_at_turn)
    return turn_compose.Answer(text=text, question=question)


def _picker_family_uuids(payload: Mapping[str, Any], uuid_val: Any) -> list[str] | None:
    """AC-1694/contract 103: a customer roster option's `uuids` must be its WHOLE
    family (every company's account for that trading name), not just the
    representative row `gate.py`'s own `compatible_entities` carries.

    `gate.py`'s `compatible_entities` shape is pinned byte-for-byte by
    `test_replay.py`'s recorded n8n capture, so the family cannot be added there -
    but `payload["picker_families"]` (`{base name: [every uuid in that family]}`) is
    gate.py's own GENUINE, pre-existing field for exactly this (already consumed by
    `session_state.py`'s legacy carry). Invert it once per turn and look the
    representative's own uuid up in it - a representative is always a member of its
    own family."""
    families = payload.get("picker_families")
    if not isinstance(families, dict) or uuid_val is None:
        return None
    key = str(uuid_val)
    for family in families.values():
        if isinstance(family, list) and key in {str(u) for u in family}:
            return [str(u) for u in family]
    return None


def _offer_answer(
    payload: dict[str, Any],
    *,
    parser: dict[str, Any] | None,
    ctx: Any,
    canned: Any,
    db: Any,
    asked_at_turn: int | None,
) -> turn_compose.Answer:
    lane_item = {**payload, "branch_kind": "not_found"}
    # The resolver's OWN gate (`require_specific` is True for both the customer and the
    # incoming/product picker exits, per `resolve_gate.if_incoming_picker` /
    # `if_customer_picker`) - passed through so `compose_from_fragments`'s own
    # `cs_offer_gate` correctly blocks the CS-member-offer merge (its g4 condition) the
    # same way it does for every other require-specific picker, rather than reading
    # `gate=None` as "no opinion, merge is allowed".
    text = _compose_text(
        lane_item, ctx=ctx, canned=canned, db=db, incoming_picker=lane_item, gate=payload.get("gate")
    )
    entities = [e for e in (payload.get("compatible_entities") or []) if isinstance(e, dict)]
    question = None
    if len(entities) >= _MIN_ROSTER_OPTIONS:
        entity_kind = entities[0].get("entity_type") or "product"
        kind = f"{entity_kind}_pick"
        rows = entities
        if entity_kind == "customer":
            rows = [
                {**e, "uuids": family} if family else e
                for e, family in (
                    (e, _picker_family_uuids(payload, e.get("uuid"))) for e in entities
                )
            ]
        options = [
            option
            for option in (
                _roster_option(row, kind=kind, position=i + 1) for i, row in enumerate(rows)
            )
            if option
        ]
        if len(options) >= _MIN_ROSTER_OPTIONS:
            # AC-1704/contract 121: the domain a pick continues answering FOR - missing
            # here (`pending.ask` with no `payload=` at all) left `payload.domain` unset
            # and a bare number's answer unable to say which ask it settled. `status`
            # is the SAME carry `_answer_outstanding` already does for
            # `outstanding_detail`/`sales_report_detail` (`focus.status`, projected
            # onto `order_status` by `turn_runtime.lane_parse_output`) - a sales
            # report's own ambiguous-customer pick otherwise answers "1" with the
            # generic order tool, never `crm_sales_report`, since the ASKING turn's
            # `order_status` reached the verdict directly (no `document`/`status`
            # pair for `_focus_rules` to carry it on `focus.status` itself) and the
            # answering turn's own verdict never repeats it.
            ask_payload: dict[str, Any] = {"domain": (parser or {}).get("domain_hint")}
            # AC-1708: and EVERY domain the message named, when it named more than one.
            # `domain` alone settled the focus to a single one (`turn/apply.py`'s
            # contract-121 carry), so answering a two-domain ask's customer picker
            # fetched the first section and silently dropped the second. Read off the
            # verdict's own `asks` (contract 122), the same way `turn/apply.py` reads
            # it, and answered by the same reader, which already takes `domains` first.
            ask_domains = [
                row.get("domain")
                for row in ((parser or {}).get("asks") or [])
                if isinstance(row, dict) and row.get("domain")
            ]
            if len(ask_domains) > 1:
                ask_payload["domains"] = ask_domains
            order_status = (parser or {}).get("order_status")
            if order_status:
                ask_payload["status"] = order_status
            question = pending.ask(
                kind,
                options,
                asked_at_turn=asked_at_turn,
                payload=ask_payload,
            )
    return turn_compose.Answer(text=text, question=question)


def question_for(
    payload: dict[str, Any] | None,
    *,
    fetch: dict[str, Any] | None = None,
    parser: dict[str, Any] | None,
    ctx: Any,
    canned: Any,
    db: Any = None,
    asked_at_turn: int | None,
) -> turn_compose.Answer | None:
    """The ASK seam (PLAN "Design"): `None` outside its two arms, so the caller falls
    back to `turn/compose.py` for a multi-domain plan, a lane question or a team pick.

    `fetch` is `lanes.business.run_fetch`'s own tier-ask fragment (its `"fetch"` key,
    not the wrapper dict `run_fetch` returns) - see the module docstring for the
    measured shape. `payload` is the resolver's own exit item
    (`ResolveOutcome.payload`). `db` is optional (R3's two arms never need a live CS
    roster read; `_offer_answer` hands the real gate through so `cs_offer_gate` blocks
    it on its own require_specific condition regardless).
    """
    if not isinstance(payload, dict):
        return None
    exit_kind = payload.get("_exit_kind")
    fetch_arm = fetch.get("_fetch_arm") if isinstance(fetch, dict) else None
    tier_gate = payload.get("tier_gate")
    # R5: a `not_found` exit still needing a tier pick (the product never resolved,
    # but `entry == "access_check"` already ran the tier gate before it tried) - the
    # "continue" exit's own tier-ask (`fetch_arm == "tier-ask"`, run AFTER the real
    # per-tier promotion probe) is untouched; this is the OTHER exit that same gate
    # can leave the resolver on, never overlapping with it (`_access_ask_answer`'s own
    # `tier_source` docstring names the shape difference).
    needs_tier_ask = (
        exit_kind == "not_found"
        and isinstance(tier_gate, dict)
        and tier_gate.get("tier_ask") is True
    )
    if exit_kind == "access_ask" or fetch_arm == "tier-ask" or needs_tier_ask:
        return _access_ask_answer(
            payload, fetch=fetch, parser=parser, ctx=ctx, canned=canned, db=db, asked_at_turn=asked_at_turn
        )
    if exit_kind == "offer":
        return _offer_answer(
            payload, parser=parser, ctx=ctx, canned=canned, db=db, asked_at_turn=asked_at_turn
        )
    return None


# --------------------------------------------------------------------------- #
# R4 - the miss arm
# --------------------------------------------------------------------------- #

_NUMBERED_LINE_RE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*$")


def _stamps_by_position(text: str) -> dict[int, str]:
    """Position -> the has/no suffix that line prints, whatever follows the LAST
    " - " on a numbered line. None of `run_miss_lane`'s own roster rows
    (`suggest_last_result_set`) carry a `stamp` field - every arm (the sibling picker,
    the D1 did-you-mean, the require-specific picker) bakes the suffix into the
    rendered TEXT only - so the option's own stamp is read back off the SAME text the
    customer sees, never re-derived from a probe a second time."""
    stamps: dict[int, str] = {}
    for line in (text or "").split("\n"):
        match = _NUMBERED_LINE_RE.match(line)
        if not match:
            continue
        content = match.group(2)
        if " - " in content:
            stamps[int(match.group(1))] = content.rsplit(" - ", 1)[1].strip()
    return stamps


def _member_option(row: dict[str, Any], position: int) -> dict[str, Any] | None:
    """A `cs_last_result_set` row as a `member_offer` option - `respond_user_id` rides
    on the payload (not `session_state._legacy_option`'s own value/team pair) because an
    answering turn assigns the escalation BY that id, never by the roster's `uuid`
    (a `users.id`, never sent to respond.io)."""
    if not isinstance(row, dict):
        return None
    return {
        "position": int(row.get("idx") or position),
        "label": row.get("label"),
        "entity_type": "member",
        "uuid": row.get("uuid"),
        "payload": {"respond_user_id": row.get("respond_user_id")},
    }


def _stamped_roster_options(rows: list[Any], *, kind: str, text: str) -> list[dict[str, Any]]:
    """`rows` (a `suggest_last_result_set` or a require-specific picker's own
    `compatible_entities`) -> options in `_roster_option`'s shape, each carrying the
    SAME has/no stamp the composed TEXT prints - neither roster row shape carries a
    `stamp` field of its own, only the rendered line does."""
    stamps = _stamps_by_position(text)
    options: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        option = _roster_option(row, kind=kind, position=i + 1)
        if option is None:
            continue
        if not option.get("stamp"):
            stamp = stamps.get(option.get("position"))
            if stamp:
                option["stamp"] = stamp
        options.append(option)
    return options


def _miss_question(
    offer: Mapping[str, Any],
    producers: Mapping[str, Any],
    *,
    gate: Any,
    parser: Mapping[str, Any] | None,
    asked_at_turn: int | None,
    text: str,
) -> pending.Pending | None:
    """AC-1684: every question the miss arm raises, in the SAME precedence
    `tail.reply_ladder.compose_reply`'s own `result_set` already reads (member offer
    first, then the roster a producer built, then a bare escalate offer)."""
    routing = (parser or {}).get("routing") or {}
    team = routing.get("suggested_team")

    member = producers.get("build-cs-member-offer")
    if isinstance(member, Mapping) and member.get("member_offer") is True:
        rows = member.get("cs_last_result_set") or []
        options = [
            option
            for option in (_member_option(row, i + 1) for i, row in enumerate(rows))
            if option
        ]
        if options:
            return pending.ask("member_offer", options, asked_at_turn=asked_at_turn)

    # The did-you-mean roster (`build_suggest_offer`'s D1/D2/D3 arms all populate
    # `suggest_last_result_set`). The require-specific PICKER (F6/AC-1701) is a FOURTH
    # surface `build_suggest_offer` never gives its own `suggest_last_result_set` at
    # all - it only rewrites `escalate_message` in place (answer.py's own "4th surface"
    # comment) - so that roster's rows are `gate.compatible_entities` instead, the SAME
    # rows `gate.py`'s own numbered picker text was built from (FIX A).
    rows = offer.get("suggest_last_result_set") or None
    if not rows and isinstance(gate, Mapping) and gate.get("require_specific") is True:
        rows = [e for e in (gate.get("compatible_entities") or []) if isinstance(e, dict)]
    if rows:
        entity_kind = next(
            (row.get("entity_type") for row in rows if isinstance(row, dict) and row.get("entity_type")),
            None,
        ) or "product"
        kind = f"{entity_kind}_pick"
        options = _stamped_roster_options(rows, kind=kind, text=text)
        # AC-1691's umbrella, "in any domain and for any entity kind" - the SAME guard
        # `_tier_options` and `_offer_answer` already carry, and the one arm of this
        # module that was missing it (reviewer S5). A one-row `suggest_last_result_set`
        # is not a choice; the escalate offer below is the honest question for it.
        if len(options) >= _MIN_ROSTER_OPTIONS:
            return pending.ask(
                kind,
                options,
                team=team,
                asked_at_turn=asked_at_turn,
                payload={"domain": (parser or {}).get("domain_hint"), "escalate_offered": True},
            )

    catalog = producers.get("escalate-catalog")
    if isinstance(catalog, Mapping) and catalog.get("is_escalate_offer") is True:
        return pending.ask(
            "team_pick",
            [{"position": 1, "label": "Yes", "entity_type": "team", "payload": {}}],
            team=team,
            asked_at_turn=asked_at_turn,
            expects="yes_no",
        )
    return None


def _fold_crossdomain_ladder(
    text: str,
    *,
    parser: Mapping[str, Any] | None,
    resolved: Any,
    entities_names: Any,
    crossdomain_ladder: Mapping[str, Any] | None,
    ctx: Any,
    services: AnswerServices,
    contact_id: Any,
    space_id: str | None,
    trace: Any = None,
    dry_run: bool = True,
) -> str:
    """AC-1705: the cross-domain stock ladder, folded above the escalate marker.

    `answer.run_crossdomain` gates itself to `domain_hint in ("incoming", "inventory")`
    and at least one probeable (uuid-carrying) product (`crossdomain_zeroset`'s own
    domain/probeable checks) - calling it unconditionally on every miss is therefore a
    genuine no-op (no MCP call, `render=None`) for every other domain, never a second
    ladder policy of this module's own.

    Every argument is the one `complete_answer` hands its own `run_crossdomain`
    (`lanes/business/__init__.py:1685-1710`), reviewer B3/S2:

    * `entities_names` is the resolver aggregate's own `name` (the contact's entitled
      level names). `None` skips `crossdomain_probe_args`'s intersection entirely and
      sends the PARSER's claimed `access_levels` verbatim, so a level the customer's
      words named but the contact does not hold reached the probe.
    * `crossdomain_ladder` is `system_settings.chatbot_crossdomain_ladder`
      (`engine._crossdomain_ladder`). `answer._next_crossdomain_rung` returns `None`
      for a non-dict ladder, so without it the SECOND rung - the PO rung, migration
      `491_chatbot_ladder_incoming_po`, owner ruling 8 Sep 2026 - never ran at all.
    * `trace` is the turn's own `TurnTrace`, so the rung probes appear on the trace
      screen under this turn rather than nowhere.
    """
    session_block = ctx.get("session") if isinstance(ctx, Mapping) else None
    access = ctx.get("access") if isinstance(ctx, Mapping) else None
    granted = access.get("attributes") if isinstance(access, Mapping) else None
    result = answer_mod.run_crossdomain(
        {},
        parser=parser,
        resolved=resolved,
        session_block=session_block,
        entities_names=entities_names,
        services=services,
        contact_id=contact_id,
        space_id=space_id,
        dry_run=dry_run,
        crossdomain_ladder=(
            dict(crossdomain_ladder) if isinstance(crossdomain_ladder, Mapping) else None
        ),
        trace=trace,
        granted=granted,
    )
    render = result.get("render")
    if not isinstance(render, Mapping):
        return text
    block = render.get("_xdBlock")
    if not isinstance(block, Mapping) or block.get("any") is not True or not block.get("block"):
        return text
    sealed = {"reply": {"text": text, "session_patch": {"user_response": text, "variables": {}}}}
    merged = tail_compose.crossdomain_compose(
        sealed, result={"result": {"xd": {"block": dict(block)}}}, answered=False
    )
    merged_text = (merged.get("reply") or {}).get("session_patch", {}).get("user_response")
    return merged_text if isinstance(merged_text, str) and merged_text else text


def answer_for(
    payload: dict[str, Any] | None,
    *,
    envelope: dict[str, Any] | None,
    parser: dict[str, Any] | None,
    ctx: Any,
    canned: Any,
    services: AnswerServices,
    db: Any,
    asked_at_turn: int | None,
    roster_caps: Mapping[str, int] | None = None,
    crossdomain_ladder: Mapping[str, Any] | None = None,
    turn_id: str | None = None,
    trace: Any = None,
    dry_run: bool = True,
) -> turn_compose.Answer | None:
    """The MISS seam (R4): `None` outside its own two triggers (see module docstring),
    so a hit, an `access_denied` refusal, an infrastructure error and a multi-domain plan
    all fall through to the caller's own fallback (`turn/compose.py`, or R5's own hit
    arm)."""
    if not isinstance(payload, dict):
        return None
    raw_fragment = envelope.get("raw_fragment") if isinstance(envelope, dict) else None
    fragment_outcome = raw_fragment.get("outcome") if isinstance(raw_fragment, dict) else None
    fetch_item = None
    if isinstance(raw_fragment, dict):
        maybe_fetch = raw_fragment.get("fetch")
        fetch_item = maybe_fetch if isinstance(maybe_fetch, dict) else None

    via_resolver_exit = payload.get("_exit_kind") == "not_found"
    via_error_fragment = fragment_outcome == "not_found"
    # R5 (AC-1699, AC-1702): a THIRD trigger - the resolver settled a real subject,
    # the fetch genuinely ran for it, and the tool came back with zero rows. This
    # fragment carries NO top-level `outcome` at all (`kind: "result"`, the ordinary
    # hit shape `lanes.business.fetch.output_structurer` returns via `fetch_result`) -
    # `fetch_item.get("has_result")` is what actually says whether it found anything,
    # the same field `envelope_of`'s own `has_result` computation reads. Checked on
    # `raw_fragment`/`fetch_item` directly, never the OUTER `envelope`'s own
    # `turn/fetch.py::envelope_missed` rule - that rule reads several fields
    # (`figures`, `denied`, `tool_has_result`, `entities`, `miss`) a hand-built test
    # envelope carrying only `raw_fragment` never populates, and every existing
    # `TestMissArmReturnsNoneOutsideItsOwnTerritory` case is exactly such a fixture.
    # `raw_fragment.get("kind") == "error"` (an access_denied refusal or an
    # infrastructure failure, both from `business._error_fragment`) is excluded the
    # same way `via_error_fragment` already excludes an infra failure (neither
    # `not_found` nor `access_denied` outcome) - only the ordinary "result" kind ever
    # reaches this trigger.
    via_fetched_empty = (
        not via_error_fragment
        and isinstance(raw_fragment, Mapping)
        and raw_fragment.get("kind") == "result"
        and isinstance(fetch_item, Mapping)
        and not fetch_item.get("has_result")
    )
    if not (via_resolver_exit or via_error_fragment or via_fetched_empty):
        return None

    # The SAME three reads `complete_answer` opens with
    # (`lanes/business/__init__.py:1553-1560`), coercions included: a non-dict
    # `resolved`/`gate` is `{}` there, never `None`, and `entities_names` is the
    # resolver aggregate's own entitled level names, `None` only when the aggregate
    # genuinely did not run (which both readers handle).
    resolved = payload.get("resolved") if isinstance(payload.get("resolved"), dict) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
    aggregate = payload.get("aggregate") if isinstance(payload.get("aggregate"), dict) else None
    # Security S2. Main's own expression is `aggregate.get("name") if aggregate is not
    # None else None`, and `None` tells `answer.crossdomain_probe_args` to skip its
    # intersection and send the PARSER's claimed `access_levels` verbatim - a level the
    # customer's WORDS named, which nothing has checked against the contact's entitlement.
    # The aggregate only runs on the `access_check` entry (the promotion lane), so every
    # incoming/inventory miss - the only origins the cross-domain ladder has - took that
    # `None` branch. `[]` instead of `None` is the one deliberate divergence: an
    # unverified claim is dropped rather than forwarded. It is byte-identical to main
    # whenever the parser claimed nothing, which is 249 of 249 real captures
    # (`documentation/plans/chatbot/parser-prompt-inventory.md:106`), so the only turn
    # that can observe the difference is the one making an unverified claim.
    entities_names = aggregate.get("name") if aggregate is not None else []
    full_payload = (
        {**payload, "fetch": fetch_item} if (via_error_fragment or via_fetched_empty) else payload
    )

    not_found = answer_mod.not_found_error_message(
        full_payload, parser=parser, resolved=resolved, gate=gate
    )
    contact_id = (ctx.get("contact") or {}).get("id") if isinstance(ctx, Mapping) else None
    space_id = business_services.fetch_space_id(db) if db is not None else None
    offer = miss_mod.run_miss_lane(
        not_found,
        parser=parser,
        resolved=resolved,
        gate=gate,
        services=services,
        # Reviewer B2. `miss_suggest._sibling_gate`'s FOURTH condition is
        # `if build_result is None: return False`, so omitting this closed the sibling
        # gate unconditionally and a partially-typed variant code never got its
        # sibling-family offer - the has-incoming / no-incoming picker - even though
        # every other condition held. Main's own `complete_answer` passes this exact
        # literal on its combined not-found/error arm
        # (`lanes/business/__init__.py:1660-1665`) with a comment saying why, and the
        # literal is TRUE for all three of this function's triggers: `answer_for` is
        # the MISS seam and returns `None` for a hit, and `via_fetched_empty`'s own
        # trigger condition IS `not fetch_item.get("has_result")`.
        build_result={"has_result": False},
        contact_id=contact_id,
        space_id=space_id,
        # Main passes the turn id (`complete_answer`'s own `execution_id=turn_id`), so
        # the miss probes correlate with the turn on the trace screen; a synthetic
        # "bridge-turn-N" correlates with nothing (reviewer N4).
        execution_id=turn_id if turn_id else f"bridge-turn-{asked_at_turn}",
        # Main passes the lane's own flag rather than a hardcoded literal (N3). Inert
        # today - `run_miss_lane`'s own docstring says D14 suppresses WRITES and this
        # lane has none - but it is a real flag the engine holds.
        dry_run=dry_run,
        roster_caps=roster_caps,
    )
    lane_item = {**offer, "branch_kind": "not_found"}
    values = {
        "not_found": not_found,
        "incoming_picker": None,
        "access_choice": None,
        "suggest_offer": offer,
        "gate": gate,
        "offer_hold": None,
    }
    composed = reply_mod.compose_from_fragments(lane_item, ctx, canned, values, db=db)
    text = composed.get("text") or ""
    producers = composed.get("producers") or {}

    question = _miss_question(
        offer, producers, gate=gate, parser=parser, asked_at_turn=asked_at_turn, text=text
    )
    text = _fold_crossdomain_ladder(
        text,
        parser=parser,
        resolved=resolved,
        entities_names=entities_names,
        crossdomain_ladder=crossdomain_ladder,
        ctx=ctx,
        services=services,
        contact_id=contact_id,
        space_id=space_id,
        trace=trace,
        dry_run=dry_run,
    )
    return turn_compose.Answer(text=text, question=question)
