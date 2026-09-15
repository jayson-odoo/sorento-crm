"""The runtime seams stages C to G are handed: state in, resolver, tool runner, state out.

`turn/` is pure by contract (AC-1520 - no I/O, no text, no lane imports), so everything
that has to touch a database, an MCP tool or the kept `lanes/business` machinery lives
here instead, one function per seam:

* `load_state` / `turn_number` - stage A's read of the three shelves (focus + pending
  from the five session keys, profile from `respond_contacts.chatbot_profile`).
* `resolve_kinds` - the resolver seam reconciliation needs (AC-1527). It returns the
  plain `{raw: {kind: hits}}` dict `turn/reconcile.py` already takes, plus the gate's
  compatible entities for the fetch below.
* `tool_runner` - what `turn/fetch.py::run_fetch` calls once per `FetchSpec`. It is the
  KEPT lane: `lanes/business.run_fetch` picks the tool, calls it and structures the rows,
  and this wraps that output as the `{domain, denied, entities, figures, files, miss}`
  envelope the composer reads.
* `lane_parse_output` - the `ctx.parse.output` the kept lanes read, projected from the v3
  verdict: the same keys they have always read, plus the two the re-architecture renamed
  (`document` / `status` are projected back onto `order_status` for the order tools) and
  the offered team an acceptance inherits from the open question rather than from a
  post-processed routing chain.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.chatbot import jsc
from app.services.chatbot.contracts import DEFAULT_SUGGESTED_AGENT, DEFAULT_SUGGESTED_TEAM
from app.services.chatbot.turn.pending import OFFER_KINDS, Pending, from_wire
from app.services.chatbot.turn.plan import FetchSpec
from app.services.chatbot.turn.state import Focus, Profile, State, focus_from_wire
from app.services.chatbot import session_state

logger = logging.getLogger(__name__)

# The inverse of `conversation_variables_service`'s read-time migration: the order tools
# still take one `order_status` bucket, and `focus.document` + `focus.status` is what the
# turn now carries. Projected at THIS seam only - nothing persists a bucket again.
_DOCUMENT_STATUS_TO_ORDER_STATUS: dict[tuple[str, str], str] = {
    ("", "outstanding"): "outstanding",
    ("DO", "outstanding"): "do_outstanding",
    ("SO", "outstanding"): "so_outstanding",
    ("DO,SO", "outstanding"): "outstanding_both",
}


@dataclass
class TurnContext:
    """The duck-typed bag `run_fetch`, `compose` and `tail.persist` read.

    Deliberately NOT a class any of them imports: each reads the attributes it needs by
    name (`ctx.tool_runner`, `ctx.trace`, `ctx.db`), which is what lets a test hand any
    of them a `SimpleNamespace` instead.
    """

    db: Any = None
    contact_respond_id: str | None = None
    trace: Any = None
    policy: Any = None
    profile: Profile = field(default_factory=Profile)
    tool_runner: Callable[[str, FetchSpec], dict[str, Any]] | None = None
    access_levels: list[str] = field(default_factory=list)
    contains_flyer: bool = False
    ideation: Any = None


# --------------------------------------------------------------------------- #
# Stage A: the three shelves
# --------------------------------------------------------------------------- #


def turn_number(db: Session, contact_respond_id: str) -> int:
    """How many turns this contact has had, this one included (stamps `asked_at_turn`)."""
    try:
        count = db.execute(
            text("SELECT count(*) FROM chatbot.turns WHERE contact_respond_id = :cid"),
            {"cid": contact_respond_id},
        ).scalar()
    except Exception:  # noqa: BLE001 - a turn number nobody could read is 1, not a failure
        return 1
    return int(count or 0) or 1


def contact_phone(db: Session, contact_respond_id: str) -> str | None:
    """The contact's phone number off their own row.

    The webhook envelope carries respond.io's contact record, which normally holds it -
    but the retry and poller ingresses rebuild a leaner contact, and the escalation lane's
    round-robin draw REQUIRES a phone number (`post_next_assignee` 400s without one). The
    CRM already knows it, so the turn fills the gap rather than failing the handover.
    """
    try:
        row = db.execute(
            text("SELECT phone_number FROM respond_contacts WHERE respond_io_id = :cid"),
            {"cid": contact_respond_id},
        ).first()
    except Exception:  # noqa: BLE001 - an unknown contact is an unknown phone, not a failure
        return None
    return row[0] if row is not None else None


def load_profile(db: Session, contact_respond_id: str) -> tuple[Profile, bool]:
    """`respond_contacts.chatbot_profile` + `chatbot_recall_enabled` (AC-1503, AC-1548).

    `grants` stays None - unrestricted. The per-domain reveal gate is the one the
    business lane and `output_structurer` already run off `ctx.access.attributes`
    (contract 59); wiring THIS field to that list would deny every domain that declares
    no `reveal_key` at all, since a domain with no key falls back to its bare name. The
    trigger for wiring it is S5's grant sweep, which gives every domain a key.
    """
    try:
        row = db.execute(
            text(
                "SELECT chatbot_profile, chatbot_recall_enabled FROM respond_contacts "
                "WHERE respond_io_id = :cid"
            ),
            {"cid": contact_respond_id},
        ).first()
    except Exception:  # noqa: BLE001 - a contact with no profile row is a blank profile
        return Profile(), False
    if row is None:
        return Profile(), False
    raw = row[0] if isinstance(row[0], dict) else {}
    ledgers = raw.get("default_ledgers")
    return (
        Profile(
            tier=raw.get("tier"),
            language=raw.get("language"),
            grants=None,
            default_ledgers=list(ledgers) if isinstance(ledgers, list) else None,
        ),
        bool(row[1]),
    )


def load_state(session_block: Any, *, profile: Profile, turn_no: int) -> State:
    """Stage A's `State`: focus and pending off the five session keys, profile beside."""
    five = session_state.five_keys(session_block)
    return State(
        focus=focus_from_wire(five.get("focus")),
        pending=from_wire(five.get("open_question")),
        profile=profile,
        turn_no=turn_no,
    )


def focus_diff(before: Focus, after: Focus) -> dict[str, Any]:
    """What APPLY changed, for the `apply` trace record (AC-1549)."""
    from app.services.chatbot.turn.state import focus_to_wire

    left, right = focus_to_wire(before), focus_to_wire(after)
    return {key: {"before": left[key], "after": right[key]} for key in left if left[key] != right[key]}


# --------------------------------------------------------------------------- #
# Stage B/C: the verdict the kept lanes read
# --------------------------------------------------------------------------- #


def _prior_suggested_team(session_block: Any) -> str | None:
    """The legacy `variables.routing.suggested_team` nest a previous turn wrote.

    `session_block` here is exactly what `engine.py` hands `build_ctx` as `session=`, so
    this reads it the SAME way `escalation._prev_variables(ctx)` reads `ctx.session` -
    `session_vars.variables`, then `session_vars`'s own bare `variables`, then nothing.
    Any shape mismatch (a blank session, a five-key-only contact with no legacy nest at
    all) reads as "nothing carried", never an error.
    """
    try:
        session_vars = session_block.get("session_vars") if isinstance(session_block, dict) else None
        variables = session_vars.get("variables") if isinstance(session_vars, dict) else None
        if not variables:
            # The node's own second fallback: `ctx.session.variables` directly, bypassing
            # `session_vars` - the session block has had three shapes over its life
            # (`escalation._prev_variables`'s own docstring), reproduced whole.
            variables = session_block.get("variables") if isinstance(session_block, dict) else None
        routing = variables.get("routing") if isinstance(variables, dict) else None
        team = routing.get("suggested_team") if isinstance(routing, dict) else None
        team = str(team).strip() if team else ""
        return team or None
    except Exception:  # noqa: BLE001 - a session shape this cannot read carries nothing
        return None


def lane_parse_output(
    verdict: dict[str, Any],
    *,
    focus: Focus | None = None,
    pending: Pending | None = None,
    domain: str | None = None,
    prior_session: Any = None,
) -> dict[str, Any]:
    """`ctx.parse.output` for the kept lanes, projected from the v3 verdict.

    The verdict travels VERBATIM but for four projections, each of which exists because
    a kept reader asks its question in the pre-rearch vocabulary:

    * `order_status` - the order tools' one bucket, from `document` + `status` (D6);
    * `domain_hint` - pinned to the domain being fetched, so a two-domain fan-out picks
      the right tool per leg instead of the first domain's tool twice (contract 122);
    * `routing.suggested_team` / `routing.suggested_agent` - the retired
      `output_exchange` chain never emitted a null routing pair (`DEFAULT_SUGGESTED_TEAM`
      / `DEFAULT_SUGGESTED_AGENT`, `contracts.py`), which is what let the escalation
      lane's round-robin draw assume both were always populated (`_next_assignee_body`
      400s on neither). Reproduced here, ONE LAYER UP from that lane - `escalation.py`
      itself keeps NO guard of its own (H27, deliberately: `test_s5_escalation_lane.py`'s
      `test_no_team_clarify_on_live_team_flows_through_unguarded` and
      `test_two_staff_with_the_same_name_in_different_teams_clarifies_instead_of_guessing`
      both call `escalation.run()` directly with a hand-built ctx and pin a null/inherited
      team flowing through UNGUARDED - the default belongs to the layer that builds
      `ctx.parse.output`, not to the lane that reads it). Chain, in order: a NAMED team
      (this turn's own); an OFFER's carried team (`pending.team`, contract 108, an
      acceptance names no team of its own); a PREVIOUS turn's own carried routing
      (`_prior_suggested_team`, test_pass4_item5's B3 - "the carried team when a previous
      turn had one, else the table's default", never the default unconditionally); the
      hard default, last. The parser's own answer stays untouched on `_parser_raw`, which
      is what `escalation._parser_team` reads to tell "this turn named a team" from "this
      turn accepted one".
    """
    out = dict(verdict)
    if domain:
        out["domain_hint"] = domain

    document = list(out.get("document") or [])
    if focus is not None and not document:
        document = list(focus.document)
    status = out.get("status") or (focus.status if focus is not None else None)
    if status:
        key = (",".join(sorted(document)), status)
        out["order_status"] = _DOCUMENT_STATUS_TO_ORDER_STATUS.get(key, status)
    else:
        out.setdefault("order_status", None)

    routing = dict(out.get("routing") or {})
    if not routing.get("suggested_team") and pending is not None and pending.kind in OFFER_KINDS:
        routing["suggested_team"] = pending.team
    if not routing.get("suggested_team"):
        routing["suggested_team"] = _prior_suggested_team(prior_session) or DEFAULT_SUGGESTED_TEAM
    if not routing.get("suggested_agent"):
        routing["suggested_agent"] = DEFAULT_SUGGESTED_AGENT
    out["routing"] = routing
    return out


# --------------------------------------------------------------------------- #
# Stage E: resolve, then the tool
# --------------------------------------------------------------------------- #


def resolve_kinds(
    db: Session, *, ctx: dict[str, Any], branch_kind: str, space_id: str | None, dry_run: bool
) -> tuple[
    dict[str, dict[str, int]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, list[dict[str, Any]]],
]:
    """Ask the resolver what each named token actually IS (AC-1527).

    Returns `({raw: {kind: hits}}, compatible_entities, predicate, candidates_by_kind)`.
    The resolver and its gate are
    the KEPT ones (`lanes/business/resolve_gate.py`); what is dropped is its picker half,
    which `turn/narrow.py` now decides from the policy instead.

    A resolver that cannot answer is not a failed turn: reconciliation simply has nothing
    to say, and the entities the parser named stand as they are.
    """
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business import services as business_services

    entities = (jsc.get(jsc.get(ctx, "parse"), "output") or {}).get("entities") or []
    if not entities:
        return {}, [], None, {}
    try:
        payload = resolve_gate.run(
            ctx,
            "resolve",
            {"branch_kind": branch_kind},
            services=business_services.production_services(db),
            space_id=space_id,
            probe_default_start=resolve_gate.default_probe_start(),
            dry_run=dry_run,
        )
    except Exception:  # noqa: BLE001 - see the docstring: nothing to reconcile, not a failure
        logger.warning("chatbot: the resolver did not answer", exc_info=True)
        return {}, [], None, {}

    resolved = payload.get("resolved")
    by_token: dict[str, dict[str, int]] = {}
    for resolution in jsc.array(jsc.get(resolved, "resolutions")):
        token = jsc.nullish_str(jsc.get(resolution, "token")).strip()
        if not token:
            continue
        hits = by_token.setdefault(token, {})
        for match in jsc.array(jsc.get(resolution, "matches")):
            kind = jsc.nullish_str(jsc.get(match, "entity_type")).strip().lower()
            if kind:
                hits[kind] = hits.get(kind, 0) + 1

    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
    compatible = [e for e in jsc.array(gate.get("compatible_entities")) if isinstance(e, dict)]
    # The attribute-first `predicate` block (AC-1534): the resolver counted the set the
    # question described, and the count is what the answer's own header says. It rides
    # the gate to the tool trigger, where `fetch.output_structurer` prepends it.
    predicate = gate.get("predicate") if isinstance(gate.get("predicate"), dict) else None
    # The has/no stamps are the PICKER's, and the picker writes them onto its own
    # annotated item (the `offer` exit), not onto the gate it was handed. Fall back to
    # the gate so a turn that never reached the picker still groups its candidates.
    annotated = payload.get("annotate_incoming")
    stamps_from = annotated if isinstance(annotated, dict) else gate
    return by_token, compatible, predicate, candidates_by_kind(stamps_from, compatible)


def candidates_by_kind(
    gate: dict[str, Any], compatible: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """The resolver's own rows, grouped by entity kind, for the narrower's roster.

    This is what turns "which product do you mean? 1. wc286" into the ten-row roster the
    journey describes: the rows are what the resolver MATCHED, carrying the uuid a pick
    resolves to, and `stamp` is the fact the kept picker probe already measured about
    each one ("has incoming"). Deduped on identity, in the resolver's own order - the
    order the customer will read the numbers in.
    """
    stamps = gate.get("incoming_by_code") if isinstance(gate.get("incoming_by_code"), dict) else {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, set[str]] = {}
    for row in compatible:
        kind = jsc.nullish_str(row.get("entity_type")).strip().lower()
        # `code` is what the RESOLVER calls it; `canonical_code` / `raw` are what the
        # parser and the focus call it. One row shape reaches here from both.
        code = jsc.js_string(row.get("code") or row.get("canonical_code") or row.get("raw"))
        identity = jsc.js_string(row.get("uuid") or code)
        if not kind or not identity:
            continue
        if identity in seen.setdefault(kind, set()):
            continue
        seen[kind].add(identity)
        built: dict[str, Any] = {
            "raw": code or row.get("raw"),
            "canonical_code": code or None,
            "uuid": row.get("uuid") or code,
            "hint": kind,
        }
        family = row.get("uuids")
        if isinstance(family, list) and family:
            built["uuids"] = list(family)
        if code in stamps:
            built["stamp"] = "has incoming" if stamps[code] else "no incoming"
        grouped.setdefault(kind, []).append(built)
    return grouped


def make_tool_runner(
    db: Session,
    *,
    ctx: dict[str, Any],
    verdict: dict[str, Any],
    focus: Focus,
    compatible_entities: list[dict[str, Any]],
    predicate: dict[str, Any] | None,
    space_id: str | None,
    dry_run: bool,
    turn_trace: Any,
) -> Callable[[str, FetchSpec], dict[str, Any]]:
    """The ONE seam that reaches a tool: `run_fetch` calls it once per `FetchSpec`.

    The tool pick, the argument build, the MCP call and the row structuring are all the
    kept lane's (`lanes/business.run_fetch` -> `lanes/business/fetch.output_structurer`),
    so a domain answers with exactly the rows it answers with today; what is new is that
    the lane is asked once PER DOMAIN, from a plan, instead of once per turn.
    """
    from app.services.chatbot.lanes import business
    from app.services.chatbot.lanes.business import services as business_services

    def runner(domain: str, spec: FetchSpec) -> dict[str, Any]:
        page_predicate: dict[str, Any] | None = None
        page_ids: list[str] = []
        carry = spec.filters.get("set_page")
        if isinstance(carry, dict):
            page_predicate, page_ids = page_the_set(
                db, carry, access_levels=list(verdict.get("access_levels") or [])
            )
        lane_ctx = {
            **ctx,
            "parse": {
                **(ctx.get("parse") or {}),
                "output": lane_parse_output(verdict, focus=focus, domain=domain),
            },
        }
        entities = (
            [
                {"uuid": pid, "entity_type": "product", "canonical_code": None}
                for pid in page_ids
            ]
            if page_predicate is not None
            else _entities_for(spec, compatible_entities)
        )
        gate: dict[str, Any] = {"compatible_entities": entities}
        block = page_predicate if page_predicate is not None else predicate
        if block is not None:
            gate["predicate"] = block
        payload = {"gate": gate, "tier_gate": _tier_gate(spec), "ctx": lane_ctx}
        fragment = business.run_fetch(
            payload,
            services=business_services.fetch_services(db),
            dry_run=dry_run,
            space_id=space_id,
            trace=turn_trace,
            db=db,
        )
        return envelope_of(fragment, spec, entities)

    return runner


SET_PAGE_SIZE = 5


def set_page_carry(
    predicate: dict[str, Any] | None, spec: FetchSpec, scope_terms: list[str]
) -> dict[str, Any] | None:
    """Where a counted-set answer got to, for `focus.set_page` (AC-1317).

    `{set_key, offset}` and nothing more: the set is RE-DESCRIBED next turn from
    `set_key` rather than carried as a list of ids, so a session never holds two hundred
    uuids and a "more" three turns later still answers over live data.
    """
    if not predicate:
        return None
    total = int(predicate.get("qualifying_total") or 0)
    if total <= 0:
        return None
    labels = [c for c in (predicate.get("class_labels") or []) if isinstance(c, str)]
    from app.services.chatbot.lanes.business.answer import set_noun_for

    return {
        "set_key": {
            "require": predicate.get("require") or {},
            "scope_terms": list(scope_terms),
            "domain": spec.domain,
            "set_noun": set_noun_for(labels),
        },
        "offset": min(SET_PAGE_SIZE, total),
    }


def page_the_set(db: Session, carry: dict[str, Any], *, access_levels: list[str]):
    """The next page of a carried set: `(predicate, product_ids)`.

    The set is re-counted from its own description, which is what makes the carry two
    small values instead of a list - and what makes a page honest when the catalogue
    moved between the two turns.
    """
    from app.services.chatbot.lanes.business.answer import SET_PAGE_ID_CAP
    from app.services.product_predicate_service import resolve_product_set

    key = carry.get("set_key") or {}
    offset = int(carry.get("offset") or 0)
    outcome = resolve_product_set(
        db,
        require=key.get("require") or {},
        specs=[],
        free_terms=None,
        scope_terms=list(key.get("scope_terms") or []),
        limit=SET_PAGE_ID_CAP,
        product_ids=None,
        brand=None,
        access_levels=access_levels,
    )
    total = int(outcome.get("qualifying_total") or 0)
    ids = [
        c.get("product_id") or c.get("id")
        for c in (outcome.get("candidates") or [])
        if isinstance(c, dict)
    ]
    ids = [i for i in ids if i]
    page_ids = ids[offset : offset + SET_PAGE_SIZE]
    end = offset + len(page_ids)
    predicate = {
        "require": outcome.get("require") or key.get("require") or {},
        "qualifying_total": total,
        "truncated": bool(outcome.get("truncated")),
        "unrecognized_terms": [],
        "class_labels": [],
        "page": {
            "start": offset + 1,
            "end": end,
            "new_offset": end,
            "set_noun": key.get("set_noun") or "products",
        },
    }
    return predicate, page_ids


def _tier_gate(spec: FetchSpec) -> dict[str, Any] | None:
    """The tier the narrower already settled, in the shape the kept fetch reads."""
    tier = spec.filters.get("tier")
    if not tier:
        return None
    return {"tier_pick": tier, "tier_pick_domain": spec.domain, "access_levels_recomposed": [tier]}


def _entities_for(spec: FetchSpec, compatible: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The resolver's own rows for the kinds this spec narrowed to, else the spec's."""
    kinds = {e.get("hint") for e in spec.entities if e.get("hint")}
    codes = {
        jsc.js_string(e.get("canonical_code") or e.get("raw")).strip().lower()
        for e in spec.entities
    }
    picked = [
        e
        for e in compatible
        if (not kinds or e.get("entity_type") in kinds)
        and (
            not codes
            or jsc.js_string(e.get("canonical_code") or e.get("raw")).strip().lower() in codes
        )
    ]
    if picked:
        return picked
    return [
        {
            "entity_type": e.get("hint"),
            "uuid": e.get("uuid") or e.get("canonical_code"),
            "canonical_code": e.get("canonical_code") or e.get("raw"),
            "raw": e.get("raw"),
        }
        for e in spec.entities
    ]


def envelope_of(
    fragment: dict[str, Any], spec: FetchSpec, entities: list[dict[str, Any]]
) -> dict[str, Any]:
    """The kept lane's fetch fragment as the composer's envelope (AC-1530, AC-1531)."""
    fetched = fragment.get("fetch") if isinstance(fragment.get("fetch"), dict) else {}
    codes = [
        jsc.js_string(e.get("canonical_code") or e.get("raw"))
        for e in entities
        if jsc.truthy(e.get("canonical_code") or e.get("raw"))
    ]
    rows = fetched.get("answers")
    figures = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    files = fetched.get("attachments")
    has_result = bool(fetched.get("has_result")) and bool(figures)
    return {
        "denied": False,
        "entities": codes,
        "figures": figures,
        "files": [f for f in files if isinstance(f, dict)] if isinstance(files, list) else [],
        "miss": [] if has_result else codes,
        "has_result": has_result,
        # The lane's OWN rendered sentence. The composer renders the rows itself
        # (#930's grammar, contract 102); this is what a tool with no rows to render -
        # a report, a refusal, a miss suggestion - has to say instead.
        "lane_text": fetched.get("response"),
        # A counted-set answer's own header ("10 taps have certificates. Showing
        # 5.", AC-1316/AC-1317) - unlike `lane_text` this travels ALONGSIDE rows, not
        # instead of them: the composer still renders `figures` through its own
        # per-row grammar, only the domain-generic header line is replaced.
        "header_override": fetched.get("set_header"),
        "outcome": fragment.get("outcome"),
        "tool": (fetched.get("tool") or {}).get("name") if isinstance(fetched.get("tool"), dict) else None,
    }
