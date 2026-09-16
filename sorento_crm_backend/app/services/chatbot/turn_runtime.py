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

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.services.chatbot import jsc
from app.services.chatbot.contracts import DEFAULT_SUGGESTED_AGENT, DEFAULT_SUGGESTED_TEAM
from app.services.chatbot.turn.pending import OFFER_KINDS, Pending, from_wire, tick as tick_pending
from app.services.chatbot.turn.plan import FetchSpec
from app.services.chatbot.turn.state import KIND_FIELD_MAP, Focus, Profile, State, focus_from_wire
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
    # The field-reveal keys this contact holds (`ctx["access"]["attributes"]`, contract
    # 59). `None` is the empty grant set, as it is everywhere else that reads it. The
    # cross-domain ladder is the reader: a rung the contact was never granted is not
    # probed at all (owner ruling, 8 Sep 2026).
    granted_reveals: list[str] | None = None
    access_levels: list[str] = field(default_factory=list)
    contains_flyer: bool = False
    ideation: Any = None


# --------------------------------------------------------------------------- #
# Stage A: the three shelves
# --------------------------------------------------------------------------- #


def turn_number(db: Session, contact_respond_id: str) -> int:
    """How many turns this contact has had, this one included (stamps `asked_at_turn`).

    Uses the ORM, not raw SQL, for the same reason `previous_reply_text` does: the table
    is `chatbot.turns`, and only ORM constructs go through the test fixture's
    `schema_translate_map`. A literal `chatbot.turns` in a text() query reads the REAL
    schema under pytest - which the blank-schema fixture never writes to - so this
    counted 0 on every turn and every `asked_at_turn` stamp was 1.
    """
    from app.models.chatbot_turn import ChatbotTurn

    try:
        count = (
            db.query(func.count(ChatbotTurn.id))
            .filter(ChatbotTurn.contact_respond_id == str(contact_respond_id))
            .scalar()
        )
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


_PROFILE_COLUMNS = (
    "c.chatbot_profile, c.chatbot_recall_enabled, c.chatbot_stock_allowed "
    "FROM respond_contacts c"
)


def _fail_closed_profile() -> tuple[Profile, bool]:
    """What an AMBIGUOUS contact gets: no stock, no recall.

    The same `respond_io_id` can exist in two workspaces (which is why
    `field_access.resolve_contact_id` takes a `space_id` at all). Picking the first row
    would answer one person's stock question with another person's allowance and could
    recall another person's episodes. Two rows is a resolution failure, and a resolution
    failure denies.
    """
    return Profile(stock_allowed=False), False


def _profile_rows(db: Session, contact_respond_id: str, space_id: str | None) -> list[Any]:
    """This contact's rows under `space_id`, falling back to the NULL-workspace ones.

    Mirrors `field_access.resolve_contact_with_null_workspace_fallback`, which is the
    resolution the rest of the chatbot already runs (`head/access.check_access`, the
    company scope) on top of `mcp_access_service.evaluate_agent`'s workspace join:
    resolve inside the workspace first, and only then consider the measured 16 contacts
    whose `workspace_id` is NULL and which no join can reach. A contact in a DIFFERENT,
    non-default workspace stays unresolved here on purpose, exactly as it does there.
    """
    if not space_id:
        return list(
            db.execute(
                text(f"SELECT {_PROFILE_COLUMNS} WHERE c.respond_io_id = :cid LIMIT 2"),
                {"cid": contact_respond_id},
            ).fetchall()
        )
    scoped = list(
        db.execute(
            text(
                f"SELECT {_PROFILE_COLUMNS} "
                "JOIN respond_workspaces w ON w.id = c.workspace_id "
                "WHERE c.respond_io_id = :cid AND w.space_id = :space LIMIT 2"
            ),
            {"cid": contact_respond_id, "space": str(space_id)},
        ).fetchall()
    )
    if scoped:
        return scoped
    return list(
        db.execute(
            text(
                f"SELECT {_PROFILE_COLUMNS} "
                "WHERE c.respond_io_id = :cid AND c.workspace_id IS NULL LIMIT 2"
            ),
            {"cid": contact_respond_id},
        ).fetchall()
    )


# `console` is its own world: a console turn replays against the operator's own thread
# and must never read the customer's live reply as its "previous response" (nor the other
# way round). Every other ingress - webhook, poller, retry - is the same live stream.
_CONSOLE_INGRESS = "console"


def previous_reply_text(
    db: Session, *, contact_respond_id: str, ingress: str | None, is_test: bool
) -> str | None:
    """The text this contact was last answered with, for the parser's `Previous response:`.

    Read from the newest COMPLETED `chatbot.turns` row rather than from the session,
    because AC-1504 fixes `session_vars` at exactly five keys and a previous reply is not
    one of them. The turn table already holds every answer the bot has given (D15 needs it
    to replay a duplicate delivery), so this is a read of something already written, not a
    new thing to store.

    Scoped three ways, each because crossing it would answer from the wrong conversation:
    the same contact; the same WORLD (`is_test`, so a test turn never reads a live reply);
    and the same side of the console boundary (a console turn replays against the
    operator's own thread). A dry run reads it too - it has to, or the console's second
    turn parses as though the first never happened.

    `status == "done"` is what "completed" means here, and it also excludes the row for
    the turn currently running, which is still `processing` when this is called.
    """
    from app.models.chatbot_turn import ChatbotTurn

    try:
        query = db.query(ChatbotTurn.response).filter(
            ChatbotTurn.contact_respond_id == str(contact_respond_id),
            ChatbotTurn.status == "done",
            ChatbotTurn.is_test.is_(bool(is_test)),
        )
        if str(ingress or "") == _CONSOLE_INGRESS:
            query = query.filter(ChatbotTurn.ingress == _CONSOLE_INGRESS)
        else:
            query = query.filter(ChatbotTurn.ingress != _CONSOLE_INGRESS)
        row = query.order_by(ChatbotTurn.created_at.desc()).first()
    except Exception:  # noqa: BLE001 - no previous reply is a blank line, never a failure
        logger.warning(
            "chatbot: previous reply lookup failed for %s", contact_respond_id, exc_info=True
        )
        return None
    if row is None:
        return None
    reply = (row[0] or {}).get("reply") if isinstance(row[0], dict) else None
    text_value = reply.get("text") if isinstance(reply, dict) else None
    return str(text_value) if text_value else None


def load_profile(
    db: Session, contact_respond_id: str, *, space_id: str | None = None
) -> tuple[Profile, bool]:
    """`respond_contacts.chatbot_profile` + `chatbot_recall_enabled` (AC-1503, AC-1548),
    and `chatbot_stock_allowed` onto `Profile.stock_allowed` (S6) - the contact facts the
    engine reads before it routes.

    Resolved inside the workspace, not by `respond_io_id` alone: a respond.io id is only
    unique WITHIN a workspace, so the old single-row SELECT could have handed one
    contact's stock allowance and recall toggle to a namesake in another workspace,
    whichever Postgres returned first. `space_id` defaults to the default workspace's,
    the same value `check_access` and the company scope resolve for the turn. Two
    matching rows deny (see `_fail_closed_profile`); no matching row is a blank profile,
    which leaves stock allowed - "everyone is allowed unless an operator switches the
    contact off" is the S6 ruling, and an unknown contact has nobody to have switched it.

    `grants` stays None - unrestricted. The per-domain reveal gate is the one the
    business lane and `output_structurer` already run off `ctx.access.attributes`
    (contract 59); wiring THIS field to that list would deny every domain that declares
    no `reveal_key` at all, since a domain with no key falls back to its bare name. The
    trigger for wiring it is S5's grant sweep, which gives every domain a key.
    """
    try:
        if space_id is None:
            from app.services.chatbot.head.access import default_space_id

            space_id = default_space_id(db)
        rows = _profile_rows(db, contact_respond_id, space_id)
    except Exception:  # noqa: BLE001 - a contact with no profile row is a blank profile
        return Profile(), False
    if not rows:
        return Profile(), False
    if len(rows) > 1:
        logger.warning(
            "chatbot: respond_io_id %s matches %s contacts in this workspace; "
            "denying stock and recall rather than picking one",
            contact_respond_id,
            len(rows),
        )
        return _fail_closed_profile()
    row = rows[0]
    raw = row[0] if isinstance(row[0], dict) else {}
    ledgers = raw.get("default_ledgers")
    return (
        Profile(
            tier=raw.get("tier"),
            language=raw.get("language"),
            grants=None,
            default_ledgers=list(ledgers) if isinstance(ledgers, list) else None,
            # NULL cannot happen (NOT NULL, default true); `is not False` keeps the
            # fail-open reading if it ever did.
            stock_allowed=row[2] is not False,
        ),
        bool(row[1]),
    )


def load_state(session_block: Any, *, profile: Profile, turn_no: int) -> State:
    """Stage A's `State`: focus and pending off the five session keys, profile beside.

    The open question is TICKED on the way in (AC-816 rule 1): an escalation offer the
    customer has ignored for three turns is not loaded at all, so nothing downstream can
    accept it and this turn runs as the fresh message it is.
    """
    five = session_state.five_keys(session_block)
    return State(
        focus=focus_from_wire(five.get("focus")),
        pending=tick_pending(from_wire(five.get("open_question"))),
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


def with_routing_agent_default(verdict: dict[str, Any]) -> dict[str, Any]:
    """The verdict with `routing.suggested_agent` filled in ONCE, before access.

    Hand-pass 1 finding 2b (16 Sep 2026): `engine.run_turn` checked access on the
    parser's RAW `routing.suggested_agent`, and the `DEFAULT_SUGGESTED_AGENT` fallback
    only ran later, in `lane_parse_output`, for the lanes - so an unrouted webhook turn
    (the parser named no agent, which is most casual and many business turns) asked the
    access service about agent `None`. The default now lands here, at the one seam every
    turn passes through after the parser (and after the recall re-parse) and before the
    access read; `lane_parse_output` no longer carries its own copy. The team half of the
    routing pair stays in `lane_parse_output`, because its chain reads the pending offer
    and the prior session, which are lane inputs, not a verdict fact.
    """
    out = dict(verdict)
    routing = dict(out.get("routing") or {})
    if not routing.get("suggested_agent"):
        routing["suggested_agent"] = DEFAULT_SUGGESTED_AGENT
    out["routing"] = routing
    return out


def lane_parse_output(
    verdict: dict[str, Any],
    *,
    focus: Focus | None = None,
    pending: Pending | None = None,
    domain: str | None = None,
    accepted_team: str | None = None,
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
      `ctx.parse.output`, not to the lane that reads it). Chain, in order: the team an
      ACCEPTED offer just named (`apply`'s `trace.team`, the option the customer picked
      off the roster - it outranks the rest because they picked it THIS turn, and a
      multi-team offer's own `pending.team` stays null until they do); a NAMED team
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
    # Contract 38: an outstanding ask that named NO document is asked which one before
    # anything is fetched. The lane's gate reads this flag and adds the grant check it
    # is the only place able to make; the flag itself was set by the retired
    # `head/output_exchange._post_process`, and this is the seam that now knows the same
    # fact - it is the one computing the document axis, from the same two fields.
    # Read off the PROJECTED bucket, not off `status` alone: `("", "outstanding")` is
    # the one bucket in the map above that means "outstanding, no document named", and
    # reading it here keeps this true for a caller still speaking the pre-rearch
    # vocabulary (`order_status` straight on the verdict, no `document`/`status` pair).
    out["outstanding_scope_ask_candidate"] = (
        jsc.js_string(out.get("order_status") or "").strip() == "outstanding"
    )

    routing = dict(out.get("routing") or {})
    if accepted_team:
        routing["suggested_team"] = accepted_team
    if not routing.get("suggested_team") and pending is not None and pending.kind in OFFER_KINDS:
        routing["suggested_team"] = pending.team
    if not routing.get("suggested_team"):
        routing["suggested_team"] = _prior_suggested_team(prior_session) or DEFAULT_SUGGESTED_TEAM
    # `suggested_agent`'s default is applied once, upstream, by `with_routing_agent_default`
    # (finding 2b) - the access read and the lanes see the same value.
    out["routing"] = routing
    return out


# --------------------------------------------------------------------------- #
# Stage E: resolve, then the tool
# --------------------------------------------------------------------------- #


def resolve_kinds(
    db: Session,
    *,
    ctx: dict[str, Any],
    branch_kind: str,
    space_id: str | None,
    dry_run: bool,
    stamp_incoming: bool = False,
    stamp_customer: bool = False,
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

    `stamp_incoming` is the caller's own answer to "is this turn about to ask a product
    roster under incoming?" - the engine knows it from the plan, the gate cannot know it
    at all (see `resolve_gate.probe_incoming`), and it is what earns the extra probe.
    `stamp_customer` is its twin for the customer roster's has/no-DO stamps (owner hand
    pass 2, item 2), and the engine withholds it for an OUTSTANDING ask for R20's reason:
    the probe measures DELIVERED orders, which is the opposite population from the
    outstanding report's own DO block, so the stamp would contradict the answer.
    """
    from app.services.chatbot.lanes.business import pickers
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business import services as business_services

    entities = (jsc.get(jsc.get(ctx, "parse"), "output") or {}).get("entities") or []
    if not entities:
        return {}, [], None, {}
    services = business_services.production_services(db)
    try:
        payload = resolve_gate.run(
            ctx,
            "resolve",
            {"branch_kind": branch_kind},
            services=services,
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
    # Every customer option shows the NAME; the code is the fallback, not the default
    # (captain ruling, 16 Sep 2026, browser pass 3 turn 10).
    fill_customer_names(db, compatible)

    annotated = payload.get("annotate_incoming")
    if not isinstance(annotated, dict) and stamp_incoming and compatible:
        # The roster this turn is about to print IS the incoming picker's roster, reached
        # from the other side: the customer switched domain without naming the product
        # again, so nothing was ambiguous and the gate never took its picker arm. Probe
        # the same tool it would have, and annotate a COPY of the gate - `annotate_incoming`
        # writes `escalate_message` onto what it is handed, and the gate the rest of the
        # turn reads must keep saying what the gate said.
        probe = resolve_gate.probe_incoming(
            services,
            ctx=ctx,
            entities=compatible,
            aggregate=payload.get("aggregate"),
            space_id=space_id,
        )
        annotated = pickers.annotate_incoming(copy.deepcopy(gate), probe=probe)
    stamps_from = annotated if isinstance(annotated, dict) else gate

    customer_bases: set[str] | None = None
    if stamp_customer and any(
        jsc.nullish_str(e.get("entity_type")).strip().lower() == "customer" for e in compatible
    ):
        # The roster this turn is about to print IS the customer picker's roster, reached
        # from the other side - nothing was ambiguous to the gate, so it never took its
        # picker arm and the lines went out bare. Same probe, same rule, one annotator
        # (`pickers.customer_bases_with_do`).
        probe = resolve_gate.probe_customer(
            services,
            ctx=ctx,
            entities=compatible,
            aggregate=payload.get("aggregate"),
            default_start=resolve_gate.default_probe_start(),
            space_id=space_id,
        )
        customer_bases = pickers.customer_bases_with_do(probe)

    return (
        by_token,
        compatible,
        predicate,
        candidates_by_kind(stamps_from, compatible, customer_bases),
    )


def fill_customer_names(db: Session, entities: list[dict[str, Any]]) -> None:
    """Give every customer row the CRM's own name for it, where the resolver gave none.

    `gate._display_name` can only carry a name the resolver's match already had
    (`display.customer_name` / `debtor_name`), and several probes match a customer
    without one - so a roster printed "1. 300-C043  2. 300-C124  3. 300-C001  4. CHIN
    CHUN HARDWARE SDN BHD - [A/C I]" and asked the reader to choose between three
    account codes nobody has ever typed and one name (browser pass 3, turn 10). The
    names are in `customers`, keyed by the very uuid the match carries, so they are read
    back here - one indexed query, on a path that has already made an LLM call and a
    resolver run - and the roster, the answer header and the report's own `Customer:`
    echo then all say the same thing.

    Read through the ORM (`_customer_echo` reads the same column the same way), written
    onto the row IN PLACE so the fetch's own entities carry it too. A row whose
    `customer_name` is empty keeps its code: falling back to the code is the honest
    answer when there is no name to print.
    """
    from app.models.order import Customer

    wanted: dict[str, list[dict[str, Any]]] = {}
    for row in entities:
        if jsc.nullish_str(row.get("entity_type")).strip().lower() != "customer":
            continue
        display = row.get("display_name")
        if isinstance(display, str) and display.strip():
            continue
        uuid = row.get("uuid")
        if uuid:
            wanted.setdefault(str(uuid), []).append(row)
    if not wanted:
        return
    try:
        found = (
            db.query(Customer.id, Customer.customer_name)
            .filter(Customer.id.in_(list(wanted)))
            .all()
        )
    except Exception:  # noqa: BLE001 - a name nobody could read is a code, not a failure
        logger.warning("chatbot: the customer names did not come back", exc_info=True)
        return
    for customer_id, name in found:
        if not name or not str(name).strip():
            continue
        for row in wanted.get(str(customer_id), []):
            row["display_name"] = str(name).strip()


def pickers_module():
    """`lanes.business.pickers`, imported lazily - `candidates_by_kind` is called from
    tests with a hand-built gate and must not drag the lane in at module import."""
    from app.services.chatbot.lanes.business import pickers

    return pickers


def candidates_by_kind(
    gate: dict[str, Any],
    compatible: list[dict[str, Any]],
    customer_bases_with_do: set[str] | None = None,
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
        # Finding 3 (owner, hand-pass 1): the gate carries the resolver's own human
        # label as `display_name` - for customers only, by `gate._display_name`'s rule,
        # because a customer's `canonical_code` is an ACCOUNT code the customer never
        # typed while a product code IS its name. Carried onto the candidate as `name`
        # so a roster prints "HANLIM TRADING SDN BHD", not "300-H030".
        display = row.get("display_name")
        if isinstance(display, str) and display.strip():
            built["name"] = display.strip()
        if code in stamps:
            built["stamp"] = "has incoming" if stamps[code] else "no incoming"
        elif kind == "customer" and customer_bases_with_do is not None:
            # Item 2: a customer line says what a product line says - whether the thing
            # it names has anything to show. `None` is "not measured" (the probe failed,
            # or its page saturated) and reads as no stamp at all, never as "no DO".
            base = pickers_module().customer_base(built.get("name") or code)
            built["stamp"] = "has DO" if base in customer_bases_with_do else "no DO"
        grouped.setdefault(kind, []).append(built)
    return grouped


def _spec_window(out: dict[str, Any], spec: FetchSpec) -> dict[str, Any]:
    """The window THIS fetch is for, as the lane's own two keys.

    `FetchSpec.date_window` is the plan's answer to "which dates" - `turn/apply.py` puts
    the focus window on every spec whose domain `takes_date_filter` - and until now it had
    no reader at all: the only projection was `outstanding_carry`'s, which runs on an
    ANSWERING turn alone. So a customer picking "all" off a roster armed inside a question
    the conversation had already dated read `Order date: all`, and the scope question said
    it would search a window nobody had asked for (owner round 8, R21's own chain).

    A DEFAULT, never an override: a window this turn named is already on the verdict and
    stays (N2, the same rule `outstanding_carry` keeps for the answering turn).
    """
    window = spec.date_window if isinstance(spec.date_window, dict) else None
    if not window:
        return out
    if out.get("date_filter_start") or out.get("date_filter_end"):
        return out
    if not (window.get("start") or window.get("end")):
        return out
    out = dict(out)
    out["date_filter_start"] = window.get("start")
    out["date_filter_end"] = window.get("end")
    if not out.get("date_mode"):
        out["date_mode"] = window.get("mode")
    return out


def outstanding_carry(
    out: dict[str, Any], focus: Focus, answered: dict[str, Any]
) -> dict[str, Any]:
    """The ANSWERED outstanding question's own subject, as the lane's carried keys.

    Contract 38 and 39: the turn that answers "1" / "2" / "both" types no product, no
    customer and no location of its own - the subject rode in on the FOCUS, already
    resolved, and it has to ride back out on it or the re-run silently widens to every
    customer and every warehouse under a header that says otherwise. Read off `focus`
    and nothing else: the retired head kept a second copy of this on a session key of
    its own (`outstanding_filters`) and the two could disagree about what the question
    had been about.

    Only on an ANSWERING turn (`FetchSpec.filters["outstanding"]`, stamped by
    `turn/apply.py`): D10 says the carried code WINS over re-resolution, and on an
    ordinary turn that would override the resolver's own exact-code pick with whatever
    token the customer happened to type (AC-1119).
    """
    out = dict(out)
    detail = answered.get("detail")
    if detail in ("so", "do", "both"):
        # AC-1138: the same tool, one argument more - the MCP layer swaps in the
        # numbered list. Not a different question and not a different report.
        out["outstanding_detail_pick"] = detail

    for entity in focus.products:
        if not isinstance(entity, dict):
            continue
        code = entity.get("canonical_code") or entity.get("code") or entity.get("raw")
        if code:
            out["outstanding_carried_product_code"] = str(code)
        break
    ids = [e["uuid"] for e in focus.customers if isinstance(e, dict) and e.get("uuid")]
    if ids:
        out["outstanding_carried_customer_ids"] = ids
    for entity in focus.warehouse:
        if not isinstance(entity, dict):
            continue
        codes = [c for c in (entity.get("warehouse_codes") or []) if c]
        if codes:
            out["outstanding_carried_warehouse_codes"] = codes
        token = entity.get("raw") or entity.get("canonical_code")
        if token:
            out["outstanding_carried_location_token"] = str(token)
        break  # D5/AC-1105: one location per report

    window = focus.date_window or {}
    if not out.get("date_filter_start") and not out.get("date_filter_end"):
        # N2: the carried window is a DEFAULT, not an override - a pick that narrows the
        # window ("2, but only 2026") is answered over ITS dates, not the old ones.
        if window.get("start") or window.get("end"):
            out["date_filter_start"] = window.get("start")
            out["date_filter_end"] = window.get("end")
            if not out.get("date_mode"):
                out["date_mode"] = window.get("mode")
    return out


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
        lane_out = lane_parse_output(verdict, focus=focus, domain=domain)
        lane_out = _spec_window(lane_out, spec)
        answered = spec.filters.get("outstanding")
        if isinstance(answered, dict):
            lane_out = outstanding_carry(lane_out, focus, answered)
        lane_ctx = {
            **ctx,
            "parse": {**(ctx.get("parse") or {}), "output": lane_out},
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
        return envelope_of(
            fragment,
            spec,
            entities,
            denial_text=(
                domain_denial_text(db, domain)
                if fragment.get("outcome") == "access_denied"
                else None
            ),
        )

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


def with_carried_entities(parse_output: dict[str, Any], focus: Focus) -> dict[str, Any]:
    """What the RESOLVER is asked about on a turn that named nothing (contract 33, 35).

    "incoming", typed after an inventory answer about ten SRTWC286 variants, names no
    product at all - so the resolver was never asked, the narrower had only the carried
    rows to go on, and the fetch reached the tool with a token no `*_ids` param could be
    built from. The conversation's own subject is handed over instead: the same entity
    shape the parser emits, flagged `current_message: false` so every downstream reader
    that distinguishes "typed this turn" from "carried" (the low stock prune, the
    outstanding report's typed-code match) still can.

    A turn that names its own entities is untouched - this is the EMPTY case only.
    """
    if parse_output.get("entities"):
        return parse_output
    carried: list[dict[str, Any]] = []
    for kind, attr in KIND_FIELD_MAP.items():
        for row in getattr(focus, attr, []) or []:
            if not isinstance(row, dict):
                continue
            code = row.get("canonical_code") or row.get("raw")
            if not jsc.truthy(code):
                continue
            entity: dict[str, Any] = {
                "raw": row.get("raw") or code,
                "hint": kind,
                "canonical_code": code,
                "current_message": False,
                "confident": True,
            }
            if row.get("uuid"):
                entity["uuid"] = row["uuid"]
            carried.append(entity)
    if not carried:
        return parse_output
    return {**parse_output, "entities": carried}


def _code_of(entity: dict[str, Any]) -> str:
    """The CODE a row carries, whichever of the three names it spells it under.

    `gate.py` renames the resolver's `canonical_code` to `code` when it builds
    `compatible_entities`; the parser, the focus and a picked option all say
    `canonical_code`; a bare parser entity has only its `raw` token. Reading one
    spelling and not the others is what made the match below fall through for EVERY
    spec that named an entity (every compatible row answered `"null"`).
    """
    return jsc.js_string(entity.get("code") or entity.get("canonical_code") or entity.get("raw")).strip().lower()


def _entities_for(spec: FetchSpec, compatible: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The resolver's own rows for the kinds this spec narrowed to, else the spec's."""
    kinds = {e.get("hint") for e in spec.entities if e.get("hint")}
    codes = {_code_of(e) for e in spec.entities}
    picked = [
        e
        for e in compatible
        # A kind this spec NARROWED to keeps only what the narrower chose. Every OTHER
        # kind the resolver matched passes through untouched: the order domain narrows
        # on customer alone, and filtering the whole list down to that kind dropped the
        # product and the location out of "SRTWT7445 outstanding for Dealer A in IB" -
        # the report then printed `Product: all` over a question about one product.
        if e.get("entity_type") not in kinds or not codes or _code_of(e) in codes
    ]
    if picked:
        return picked
    return [
        {
            "entity_type": e.get("hint"),
            "uuid": e.get("uuid") or e.get("canonical_code"),
            # `code` is the name the gate's own rows use, and every code reader
            # downstream (`fetch.outstanding_product_code`, the low-stock prune, the
            # report's typed-code match) reads it first: a spec entity that reaches the
            # tool through this fallback has to answer to the same name, or a picked
            # product is a product with no code at all.
            "code": e.get("canonical_code") or e.get("raw"),
            "canonical_code": e.get("canonical_code") or e.get("raw"),
            "raw": e.get("raw"),
            **({"display_name": e["name"]} if e.get("name") else {}),
        }
        for e in spec.entities
    ]


#: A uuid is an internal identity and never a subject a person reads (the frontend's own
#: "no UUIDs in the UI" rule, here at the seam the answer text is built from): browser
#: pass 2 read `*incoming stock* for 65514803-1609-4fe8-8b60-2e908c8f9bd4:`.
_UUID_TEXT = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.IGNORECASE
)


def _answer_subject(entity: dict[str, Any]) -> str:
    """What the answer's header CALLS this entity - a name, else a code, never a uuid.

    The resolver's own human label wins where it has one (`display_name`, written for
    customers only, `gate._display_name`: an account code is not what the roster printed
    and not what the customer typed). Everything else is its code.
    """
    for key in ("display_name", "name", "code", "canonical_code", "raw"):
        value = entity.get(key)
        if not jsc.truthy(value):
            continue
        label = jsc.js_string(value).strip()
        if label and not _UUID_TEXT.match(label):
            return label
    return ""


def domain_denial_text(db: Session, domain: str) -> str | None:
    """Contract 7's refusal, for a domain the contact is not granted.

    The ONE registered `access_denied` template, rendered through the same
    `canned.field_grant_denied_text` the retired `complete_answer` called - no new
    prose, and no second wording to keep in step. `None` for a domain with no subject
    registered, which leaves the composer's generic denied line as the fallback.
    """
    from app.services.chatbot import copy as copy_mod
    from app.services.chatbot.lanes import canned as canned_lanes
    from app.services.chatbot.lanes.business.answer import DOMAIN_GRANT_SUBJECT

    subject = DOMAIN_GRANT_SUBJECT.get(str(domain or ""))
    if not subject:
        return None
    try:
        return canned_lanes.field_grant_denied_text(copy_mod.resolve(db), subject)
    except Exception:  # noqa: BLE001 - a missing copy row must not fail the turn
        logger.warning("chatbot: the domain refusal copy did not render", exc_info=True)
        return None


def envelope_of(
    fragment: dict[str, Any],
    spec: FetchSpec,
    entities: list[dict[str, Any]],
    *,
    denial_text: str | None = None,
) -> dict[str, Any]:
    """The kept lane's fetch fragment as the composer's envelope (AC-1530, AC-1531)."""
    fetched = fragment.get("fetch") if isinstance(fragment.get("fetch"), dict) else {}
    # The whole-domain grant gate refused before any tool was picked
    # (`lanes/business.run_fetch`'s `outcome="access_denied"`). That is a DENIED
    # envelope, not an empty one: without this the composer rendered a bare
    # `*last purchase cost* for M218:` header and contract 7's refusal sentence was
    # never said - the tool was still never called, so nothing leaked, but the customer
    # was told nothing either.
    refused = fragment.get("outcome") == "access_denied"
    codes = [name for name in (_answer_subject(e) for e in entities) if name]
    rows = fetched.get("answers")
    figures = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    files = fetched.get("attachments")
    has_result = bool(fetched.get("has_result")) and bool(figures)
    return {
        "domain": spec.domain,
        "denied": refused,
        "entities": codes,
        "figures": figures,
        "files": [f for f in files if isinstance(f, dict)] if isinstance(files, list) else [],
        "miss": [] if has_result else codes,
        "has_result": has_result,
        # The TOOL's own verdict, before the rows test above: a report or a refusal
        # renders as `lane_text` with no figures yet DID find something, and the
        # composer's miss rule (an offer to escalate) must not read it as a miss.
        "tool_has_result": bool(fetched.get("has_result")),
        # The lane's own failure, when the fetch did not complete: neither a hit nor a
        # miss, so the composer offers nothing on it (the error text is the answer).
        "error": fragment.get("error") if isinstance(fragment.get("error"), str) else None,
        # The lane's OWN rendered sentence. The composer renders the rows itself
        # (#930's grammar, contract 102); this is what a tool with no rows to render -
        # a report, a refusal, a miss suggestion - has to say instead. A refused domain
        # says contract 7's registered sentence.
        "lane_text": denial_text if refused else fetched.get("response"),
        # A counted-set answer's own header ("10 taps have certificates. Showing
        # 5.", AC-1316/AC-1317) - unlike `lane_text` this travels ALONGSIDE rows, not
        # instead of them: the composer still renders `figures` through its own
        # per-row grammar, only the domain-generic header line is replaced.
        "header_override": fetched.get("set_header"),
        # The lane's OWN question, when the fetch asked one instead of (or beside)
        # answering: contract 38's "which document?" and contract 39's detail offer both
        # come back as `outstanding_ask` = `{kind, last_result_set, filters}`. The
        # composer turns it into the turn's open question - before this it was dropped
        # here, so the report printed "Reply 1 for the sales order list" and stored the
        # ESCALATE offer instead, and the "1" that came back resolved against the wrong
        # roster.
        "lane_ask": fetched.get("outstanding_ask"),
        # AC-1139: this reply already states the scope it searched, in its own words
        # and its own order (the report's four header lines, and the same four above
        # the scope question). The composer's generic `*orders* for <code>:` line would
        # say it a second time, differently, above the answer.
        "own_header": bool(fetched.get("outstanding_report")),
        "outcome": fragment.get("outcome"),
        "tool": (fetched.get("tool") or {}).get("name") if isinstance(fetched.get("tool"), dict) else None,
    }
