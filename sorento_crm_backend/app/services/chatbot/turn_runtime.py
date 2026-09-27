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
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.services.chatbot import jsc
from app.services.chatbot.contracts import DEFAULT_SUGGESTED_AGENT, DEFAULT_SUGGESTED_TEAM
from app.services.chatbot.turn.decide import picked_positions
from app.services.chatbot.turn.pending import OFFER_KINDS, Pending, from_wire, tick as tick_pending
from app.services.chatbot.turn.plan import FetchSpec
from app.services.chatbot.turn import policy_rows
from app.services.chatbot.turn.reconcile import hits_for_token
from app.services.chatbot.turn.state import (
    EXTRA_KIND_ALIASES,
    KIND_FIELD_MAP,
    Focus,
    Profile,
    State,
    focus_from_wire,
    token_key,
)
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
    # SRTSC07 (prod transcript, 22 Sep 2026): this turn's own `routing.suggested_agent`,
    # read by `turn/compose.py::compose` so a freshly minted `team_pick` offer can carry
    # the agent half beside the team it already carries - `answer_bridge`'s own mint
    # sites read it straight off `parser["routing"]`, which needs no ctx field of its
    # own, so this is the ONE mint site that had nowhere else to read it from.
    suggested_agent: str | None = None
    # Round 4 (owner-approved, 22 Sep 2026): the SAME reasoning, one axis over - this
    # turn's own resolved brand (`lanes/business/gate.py`'s `routing_brand`), read by
    # `turn/compose.py::compose` so a freshly minted `team_pick`/roster re-arm can
    # stamp `payload["brand_code"]` beside the agent it already stamps.
    routing_brand: str | None = None


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
    "c.chatbot_profile, c.chatbot_recall_enabled, c.chatbot_stock_allowed, "
    "c.notify_salesman, c.packing_list_allowed "
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


def _envelope_text(envelope: Any) -> str | None:
    """The message text a stored envelope carries (the respond.io payload,
    `message.message.message.text`), else an attachment's description."""
    inner = envelope
    for key in ("message", "message", "message"):
        inner = inner.get(key) if isinstance(inner, dict) else None
    if not isinstance(inner, dict):
        return None
    text = inner.get("text")
    if not (isinstance(text, str) and text.strip()):
        attachment = inner.get("attachment")
        text = attachment.get("description") if isinstance(attachment, dict) else None
    return text if isinstance(text, str) and text.strip() else None


def recent_exchanges(
    db: Session,
    *,
    contact_respond_id: str,
    ingress: str | None,
    is_test: bool,
    limit: int = 3,
) -> list[tuple[str, str]]:
    """The last `limit` completed exchanges with this contact, oldest first, as (what
    the contact said, what the bot answered) - the parser's "Recent exchanges" lines
    (PR #1247 round 8: the owner's "is the context too less already?").

    Read from the same rows and under the same three scopes as `previous_reply_text`,
    so the newest pair's answer IS the Previous response. A row with no reply text is
    skipped; a row whose envelope carries no text (a photo or voice note) is "(media)".
    A lookup failure is no exchanges, never a failed turn.
    """
    from app.models.chatbot_turn import ChatbotTurn

    try:
        query = db.query(ChatbotTurn.envelope, ChatbotTurn.response).filter(
            ChatbotTurn.contact_respond_id == str(contact_respond_id),
            ChatbotTurn.status == "done",
            ChatbotTurn.is_test.is_(bool(is_test)),
        )
        if str(ingress or "") == _CONSOLE_INGRESS:
            query = query.filter(ChatbotTurn.ingress == _CONSOLE_INGRESS)
        else:
            query = query.filter(ChatbotTurn.ingress != _CONSOLE_INGRESS)
        rows = query.order_by(ChatbotTurn.created_at.desc()).limit(limit * 2).all()
    except Exception:  # noqa: BLE001 - no history is no lines, never a failure
        logger.warning(
            "chatbot: recent exchanges lookup failed for %s", contact_respond_id, exc_info=True
        )
        return []
    pairs: list[tuple[str, str]] = []
    for envelope, response in rows:
        reply = response.get("reply") if isinstance(response, dict) else None
        answer = reply.get("text") if isinstance(reply, dict) else None
        if not (isinstance(answer, str) and answer.strip()):
            continue
        pairs.append((_envelope_text(envelope) or "(media)", answer))
        if len(pairs) == limit:
            break
    return list(reversed(pairs))


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
            # S2 (PLAN-chatbot-stock-ask-v2-24sep.md, R7): NULL cannot happen either
            # (NOT NULL, default false) - `is True` keeps the fail-closed reading if it
            # somehow did, matching these two columns' default-OFF rule.
            notify_salesman=row[3] is True,
            packing_list_allowed=row[4] is True,
            stock_availability_only=_stock_availability_only(
                db, contact_respond_id, space_id
            ),
        ),
        bool(row[1]),
    )


def _stock_availability_only(db: Session, contact_respond_id: str, space_id: str | None) -> bool:
    """Is this contact's stock visibility policy "Availability only" (hand test F1)?

    The same resolution the stock balance read applies (`stock_visibility.
    resolve_policy`: the contact override, else the merged access types, else the
    default), so the engine and the tool can never disagree about who is a dealer. A
    read that fails is not a dealer: today's behaviour, never a silent refusal."""
    try:
        from app.services.stock_visibility import resolve_policy

        # A savepoint, so a failed read cannot leave the turn's session aborted.
        with db.begin_nested():
            policy = resolve_policy(db, contact_respond_id, space_id)
    except Exception:  # noqa: BLE001 - a policy read is a profile fact, not the turn
        logger.warning("chatbot: stock visibility policy unreadable for %s", contact_respond_id)
        return False
    return policy is not None and policy.mode == "availability"


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
        # Issue #1178: the open idea draft rides in as state, read by `apply()`'s
        # `_continues_open_draft`. Both session shapes, because `five_keys` already
        # folds the n8n-nested `variables.ideation` onto the flat key.
        ideation=five.get("ideation"),
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


#: The two offer kinds whose options can name a COMPANY - the escalate offer this engine
#: mints itself (`answer_bridge`) and the company clarify the escalation lane asks back
#: (`engine._question_offered`). `member_offer`'s options name a PERSON, so it carries no
#: roster of its own and is not listed.
_COMPANY_OFFER_KINDS: frozenset[str] = frozenset({"team_pick", "company_pick"})


def escalation_roster_plan(
    pending: Any, *, accepted_lane: str | None, accepted_rules: Any = None
) -> list[dict[str, Any]] | None:
    """`variables.routing_roster_plan`, for an ACCEPTED company-carrying offer this turn
    is about to hand to escalation (security N-3/S2, hand pass 11 review):
    `escalation_context` (`lanes/escalation.py:236-299`) reads this EXACT legacy field,
    unchanged, for BOTH of its company arms - the `company_pick` pool a named company is
    validated against, and the single-row `same_team` roster a bare "yes" routes by. It
    is the field `compile-current-state` (the kept n8n-mirroring path) writes from
    `cs_roster_plan`'s member-offer roster. This engine mints its OWN offers directly
    (`answer_bridge.apply_silent_company_offer` / `_miss_question`) with no
    `compile-current-state` equivalent, so the company those options carried never
    reached escalation on a bare "yes" - `option_payload` is empty on that arm by design
    (`turn/decide.py::picked_positions`, defect 4: a yes/no offer is answered by the word
    alone, never a position, so `turn/apply.py::_answer_offer`'s `picked` stays `None`).

    Built straight off the pending's OWN options - no new pending kind, no new field, the
    SAME row shape `cs_roster_plan` / `sub_answer.miss_roster_plan` already produce
    (`plan_idx`/`company_id`/`company_name`/`brand_code`), one entry per option that
    carries a company. The **id** is the point (hand pass 11 blocker 1): routing reads
    `company_id` and nothing else, so a row carrying only the NAME routes exactly as if
    no company had been named at all.

    `None` for a plain (no-company) yes/no offer - the zero-stock ladder's own bare "Yes"
    needs no roster at all, `team` alone already reaches `escalation_context` through
    `lane_parse_output`'s existing `accepted_team` chain.

    Gated on the ACCEPT rule, not on the lane alone (security nit, hand pass 11): a FRESH
    handover request is also `lane == "escalation"` (`turn/apply.py::_lane`) while a
    still-live offer sits in state, and that turn accepted nothing - its pool is not a
    roster anybody was just shown.
    """
    rules = accepted_rules if isinstance(accepted_rules, (list, tuple, set, frozenset)) else ()
    if (
        accepted_lane != "escalation"
        or "answer_pending_accept" not in rules
        or pending is None
        or pending.kind not in _COMPANY_OFFER_KINDS
    ):
        return None
    plan: list[dict[str, Any]] = []
    for opt in pending.options:
        # Mapping guard (reviewer N-b): a persisted option that is not a dict must not
        # take the turn down on its way through a roster read.
        payload = opt.get("payload") if isinstance(opt, Mapping) else None
        payload = payload if isinstance(payload, Mapping) else {}
        company = payload.get("company")
        if not company:
            continue
        plan.append(
            {
                "plan_idx": len(plan),
                "company_id": payload.get("company_id") or None,
                "company_name": company,
                "brand_code": payload.get("brand_code") or None,
            }
        )
    return plan or None


def _accepted_pending_field(
    pending: Pending | None, verdict: Mapping[str, Any], field: str
) -> str | None:
    """The AGENT or BRAND the customer just picked THIS turn, off an ACCEPTABLE open
    offer - one reader, parameterized only by which payload key it is reading, shared
    by `_accepted_pending_agent` (called from `with_routing_agent_default`, before
    the access read) and `_accepted_pending_brand` (round 4, called from
    `lane_parse_output`, for `escalation_context`'s new `carried_brand` rung). The
    gate, the accept check and the per-option/top-level fall-through are the SAME
    for both fields - only the key read off each payload differs.

    Reuses `turn.decide.picked_positions` - the SAME reading `apply()` uses to tell
    which option a numbered pick answered - rather than re-parsing
    `reference_positions` a second time here (PLAN "one seam"). A multi-team
    `team_pick` names one specific option's own `payload[field]`; a plain
    acceptance (a bare "yes" over a single-option offer, or a roster's attached
    escalate sentence - nothing picked by number) falls to the pending's own
    top-level `payload[field]`, which is where the mint sites
    (`turn/compose.py::_team_pick_question`, `answer_bridge.py::_miss_question`,
    `engine.py::_question_offered`) store the minting turn's own value.

    SRTSC07 review round 1, SHOULD-1: gated on the SAME condition `turn/apply.py:691`
    uses to decide "this offer is acceptable" - `pending.kind in OFFER_KINDS or
    pending.payload.get("escalate_offered") is True`. Without this gate a roster
    pending with NO escalate offer attached (a plain `product_pick`, still open while
    this turn asks for something else entirely) could still supply a value here,
    while `lane_parse_output`'s own team chain (`pending.kind in OFFER_KINDS` alone,
    no `escalate_offered` arm - a fresh, un-accepted handover carries no `accepted_
    team` either) left the team at `DEFAULT_SUGGESTED_TEAM` - the two halves of the
    pair disagreeing and `/external/next-assignee` 404ing on a pool that does not
    exist (measured: `incoming_stock_enquiries` / `customer_service`).

    SHOULD-3: the per-option read only short-circuits on an option that actually
    NAMES a value for this field, or the explicit hold (`payload.get("hold") is
    True`, the "No it's okay" decline). A MEMBER option (a combined roster+CS
    offer's own member half, `_miss_question`'s `combined_member_rows` arm) carries
    no agent/brand of its own - picking one IS still an escalation acceptance
    (`turn/apply.py:546`) - so it falls through to the pending's own top-level value
    instead of returning `None` outright.

    SRTSC07 review round 2, SHOULD-1 residual: the round 1 gate was "ACCEPTABLE",
    not "ACCEPTED" - an `escalate_offered` roster (not in `OFFER_KINDS`) still open
    while THIS turn asks about something else entirely (no yes, no escalation
    confirmation, no number landing on the roster) supplied its carried value
    unconditionally, while the TEAM half stays at `DEFAULT_SUGGESTED_TEAM` for that
    same roster - `lane_parse_output`'s own chain only reads `pending.team` for an
    `OFFER_KINDS` pending (`turn_runtime.py:647`), never a roster, accepted or not.
    An extra accept check now gates ONLY that arm, using the same signal `decide()`
    itself reads at `turn/decide.py:571-575` (a bare "yes"/escalation-confirmation
    flag, vetoed by a decline or a negation) plus a numbered pick that actually
    lands on one of the roster's own options. A proper `OFFER_KINDS` pending
    (`team_pick`/`company_pick`/`member_offer`) kept round 1's behaviour
    unconditionally at the time - its team was ALSO read unconditionally at that
    same `lane_parse_output` line, so the two halves stayed in step either way.

    Historical note (S10, fix round 6, 23 Sep 2026): `lane_parse_output` no longer
    has an `OFFER_KINDS` pending arm at all - `turn/apply.py::_answer_pending`
    already makes the acceptance judgement this paragraph describes and stamps it
    onto `trace.team`, which reaches `lane_parse_output` as `accepted_team` (the
    chain's own first read). The paragraph above is kept as the design history for
    THIS function's own accept-check, not a claim about `lane_parse_output`'s
    current shape.

    SRTSC07 review round 2 NITs: (A) a numbered pick only counts as landing on the
    roster's OWN escalation offer when the matched option is MEMBER-typed - the
    same reading `turn/apply.py::_picks_a_member_option` uses to decide a roster
    pick is an escalation acceptance rather than a business one. Without it, "2"
    over an ordinary PRODUCT option in a did-you-mean roster that also carries an
    attached escalate sentence carried the roster's agent onto a plain business
    fetch, with the team still defaulted (no assign happens, but the access check
    and any miss-offer minted off that same turn saw the mismatched pair). (B) the
    accept signal is vetoed by the SAME two reads `decide()`'s own qualifier uses
    (`facts["declined"]` off `escalation.escalation_declined`, `facts["negated"]`
    off `is_affirmative is False`) - a verdict can carry BOTH `is_affirmative: true`
    and an explicit decline (the parser is not asked to keep the two mutually
    exclusive), and `decide()` treats the decline as decisive either way.
    """
    if pending is None:
        return None
    payload = pending.payload if isinstance(pending.payload, Mapping) else {}
    acceptable_offer = pending.kind in OFFER_KINDS
    escalate_offered_roster = not acceptable_offer and payload.get("escalate_offered") is True
    if not acceptable_offer and not escalate_offered_roster:
        return None
    try:
        picked = picked_positions(pending, dict(verdict))
    except Exception:  # noqa: BLE001 - a malformed verdict must not break the carry
        picked = None
    picked_position = None
    if picked:
        positions, _via = picked
        if len(positions) == 1:
            picked_position = positions[0]
    if escalate_offered_roster:
        escalation = verdict.get("escalation")
        escalation = escalation if isinstance(escalation, Mapping) else {}
        landed_on_a_member_option = picked_position is not None and any(
            isinstance(opt, Mapping)
            and opt.get("position") == picked_position
            and opt.get("entity_type") == "member"
            for opt in pending.options
        )
        declined = escalation.get("escalation_declined") is True
        negated = verdict.get("is_affirmative") is False
        accepted = (
            verdict.get("is_affirmative") is True
            or escalation.get("is_escalation_confirmation") is True
            or landed_on_a_member_option
        ) and not (declined or negated)
        if not accepted:
            return None
    if picked_position is not None:
        for opt in pending.options:
            if not isinstance(opt, Mapping) or opt.get("position") != picked_position:
                continue
            opt_payload = opt.get("payload")
            opt_payload = opt_payload if isinstance(opt_payload, Mapping) else {}
            value = opt_payload.get(field)
            if value or opt_payload.get("hold") is True:
                return value or None
            # A matched option that names neither a value for this field nor the
            # hold flag (a MEMBER option) falls through to the pending's own
            # top-level value below, rather than returning `None` here.
            break
    value = payload.get(field)
    return value or None


def _accepted_pending_agent(pending: Pending | None, verdict: Mapping[str, Any]) -> str | None:
    """The agent half - see `_accepted_pending_field`'s own docstring for the shared
    gate/accept-check/fall-through this and `_accepted_pending_brand` both share."""
    return _accepted_pending_field(pending, verdict, "agent")


def _accepted_pending_brand(pending: Pending | None, verdict: Mapping[str, Any]) -> str | None:
    """The brand half (round 4, owner-approved, 22 Sep 2026 - "a MOCHA product's
    escalation goes to Lucas, a SORENTO product's to Jereen"). Read by
    `lane_parse_output`, not `with_routing_agent_default`: the brand has no access
    check to sit ahead of (unlike the agent), and it is written onto
    `out["escalation"]["carried_brand"]` for `escalation_context`'s own new rung to
    read back, the same "one flag on ctx.parse.output" idiom `preferred_assignee_id`
    / `company_pick` already use. See `_accepted_pending_field`'s own docstring for
    the shared gate/accept-check/fall-through."""
    return _accepted_pending_field(pending, verdict, "brand_code")


def with_routing_agent_default(
    verdict: dict[str, Any],
    *,
    pending: Pending | None = None,
) -> dict[str, Any]:
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

    SRTSC07 (prod transcript, 22 Sep 2026): the agent half used to stop here, at the
    hard default, while the team half two lines below (`lane_parse_output`) carried
    an accepted offer's team forward. `pending` is the SAME extra input that chain
    already reads, added here as a keyword so every existing one-arg caller keeps
    working unchanged. Precedence, in order: a NAMED agent (this turn's own, from the
    parser - never overridden); the accepted option's agent off `pending`
    (`_accepted_pending_agent`, the customer picked it THIS turn); the hard default,
    last.

    SRTSC07 review round 1, SHOULD-4: a `session=` keyword and its own
    `_prior_suggested_agent` fallback (`variables.routing.suggested_agent`, one turn
    back) used to sit between the two - removed. No writer in this codebase ever
    produces that nest for the agent half: `turn/tail.py`'s own five session keys hold
    no `variables.routing` at all, and `overwrite_for_contact` replaces the whole
    block rather than merging into a legacy nest. `_prior_suggested_team` keeps its
    own copy of that read because a REAL writer exists for the team half (measured:
    reviewer round 1 found none for the agent half) - the two chains are allowed to
    differ in length for that reason.
    """
    out = dict(verdict)
    routing = dict(out.get("routing") or {})
    if not routing.get("suggested_agent"):
        routing["suggested_agent"] = _accepted_pending_agent(pending, out) or DEFAULT_SUGGESTED_AGENT
    out["routing"] = routing
    _report_status_means_order_domain(out)
    return out


def _report_status_means_order_domain(out: dict[str, Any]) -> None:
    """A REPORT status word always routes to the `order` domain. Mutates `out`.

    Main's finding 3(b) (owner live testing, 19 Sep 2026,
    PLAN-chatbot-sales-report.md), re-homed: it lived in the retired
    `head/output_exchange._post_process`, and this is the seam that now normalises a
    fresh verdict before anything reads it. The measured emission for "Srt5674 August
    total sale quantity" parsed the report status and still named `master_products`,
    and BOTH report overrides in `lanes/business/__init__.py::run_fetch` gate on
    `domain == "order"` - so the turn fell through to the product-master listing. The
    same hole swallows an outstanding ask whose domain came back `inventory`.

    Reads ONLY the parser's own structured fields, never the message text, and only
    the status axis - `OUTSTANDING_ORDER_STATUS` is the set `resolve_gate.py`'s own R20
    rule already shares between the outstanding buckets and `sales_report`, so this
    extends one existing normalisation rather than adding a second.
    """
    from app.services.chatbot.lanes.business import _LOW_STOCK_INTENT
    from app.services.chatbot.lanes.business.resolve_gate import OUTSTANDING_ORDER_STATUS

    if jsc.js_string(out.get("intent_hint") or "").strip() == _LOW_STOCK_INTENT:
        # The ONE intent with a tool override of its own, and `run_fetch` already ranks
        # it ahead of both report overrides (`intent_hint == _LOW_STOCK_INTENT` is its
        # first branch). "reorder report" / "what is below level" records
        # `order_status: "outstanding"` off its own words with `domain_hint:
        # "inventory"`, and flipping the domain here sent three recorded low-stock
        # turns to the order lane (`test_turn_replay.py`'s `handbuilt-lsr-001`,
        # `-lsr-002`, `handbuilt-rp-003`: `pending options ['stock'] -> ['orders']`).
        # Same precedence, stated at both seams.
        return
    status = jsc.js_string(out.get("status") or "").strip()
    if status not in OUTSTANDING_ORDER_STATUS:
        status = jsc.js_string(out.get("order_status") or "").strip()
    if status not in OUTSTANDING_ORDER_STATUS:
        return
    prior = out.get("domain_hint")
    if prior == "order":
        return
    # A message that names SEVERAL domains ("stock and outstanding for 7445") states its
    # own list and this rule is not about it: `asks` is what the plan fans out on, and
    # rewriting the single hint under it would drop the other ask.
    if out.get("asks"):
        return
    out["domain_hint"] = "order"
    out["domain_corrected"] = f"{prior}->order (order_status {status})"


def lane_parse_output(
    verdict: dict[str, Any],
    *,
    focus: Focus | None = None,
    pending: Pending | None = None,
    domain: str | None = None,
    accepted_team: str | None = None,
    accepted_assignee: str | None = None,
    accepted_company: str | None = None,
    declined_offer_copy: bool = False,
    prior_session: Any = None,
    policy: Any = None,
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
      `ctx.parse.output`, not to the lane that reads it). Chain, in order (owner ruling
      23 Sep 2026, R9, satisfied here by `accepted_team` alone - see the S10 note
      below): the team an ACCEPTED offer just named (`apply`'s `trace.team`, the
      option the customer picked off the roster - it outranks the rest because they
      picked it THIS turn, and a multi-team offer's own `pending.team` stays null
      until they do); a NAMED team (this turn's own, read straight off the verdict);
      THIS TURN's own domain (`policy.domain(domain_hint).escalation_team_code`,
      R6/R7 - a parser emission naming no team gets the domain's real escalation
      team, a deterministic fact about the question just asked, read before a stale
      carry from a PREVIOUS turn, AC-EQ-16/17/20); a PREVIOUS turn's own carried
      routing (`_prior_suggested_team`, test_pass4_item5's B3 - "the carried team
      when a previous turn had one, else the table's default" - still applies when
      THIS turn names no resolvable domain at all, AC-EQ-19); the hard default
      (`DEFAULT_SUGGESTED_TEAM`), last of all, for a domain `policy` cannot resolve
      (no `policy` in scope, or a domain with no escalation row) and no prior carry
      either. The parser's own answer stays untouched on `_parser_raw`, which is
      what `escalation._parser_team` reads to tell "this turn named a team" from
      "this turn accepted one".

      **S10 (fix round 6, "simplest thing that works"): there is no separate OPEN-
      OFFER arm here any more.** R9 (23 Sep 2026) ruled that an open offer's team
      wins only on an actual acceptance - but `turn/apply.py`'s own `_answer_pending`
      (:285, :675) ALREADY computes exactly that judgement and stamps it onto
      `trace.team` the moment `decide()` calls a turn an acceptance
      (`answer_pending_accept`), and `engine.py` already hands `trace.team` in here
      as `accepted_team` (the very first read above). A `pending.team` arm gated by
      its own copy of the same accept signal (`_pending_offer_answered`, added in
      fix round 5, deleted here) was judging the SAME fact TWICE - reviewer kill
      test, fix round 6: deleting both the arm and the helper left the full suite
      green except two unit tests (AC-EQ-21/22) that called this function directly
      with `pending=` but no `accepted_team=`, a shape `engine.run_turn` never
      actually produces (a real acceptance always sets `accepted_team`). Those two
      tests are re-pointed to pass `accepted_team`, the production shape, instead.
      AC-EQ-18 (a fresh, unaccepted question over an open offer) is byte-identical
      to AC-EQ-20 once the arm is gone - folded into it, not duplicated.
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
    # PLAN-chatbot-sales-report.md S4 wiring point 2: the sales report's channel, off the
    # FOCUS when this message named none of its own. The turn that answers a customer
    # picker ("1") or a detail offer ("1") types no channel word, and a re-run that
    # dropped it would count every channel under a header still saying "Dealer". One
    # carry, one seam - the same place the document/status projection is made - rather
    # than a second session key the two could disagree about.
    if not out.get("sales_channel") and focus is not None and focus.sales_channel:
        out["sales_channel"] = focus.sales_channel

    routing = dict(out.get("routing") or {})
    if accepted_team:
        # R9 is satisfied here: `accepted_team` IS the open offer's team whenever
        # THIS turn genuinely accepted one - `turn/apply.py::_answer_pending` only
        # stamps `trace.team` (what `engine.py` passes in as `accepted_team`) on the
        # `answer_pending_accept` rule, the acceptance judgement itself. A turn that
        # did not accept anything passes `accepted_team=None` and falls straight
        # through to the domain fill below - see S10 in this function's own
        # docstring for the fix round 6 history (a redundant second arm, judging the
        # SAME fact off `pending` directly, used to sit here and was deleted).
        routing["suggested_team"] = accepted_team
    if not routing.get("suggested_team"):
        # Owner ruling 23 Sep 2026, R7 (AC-EQ-16/17/19), supersedes R6's own
        # ordering (22 Sep 2026). Chain, in order: an ACCEPTED offer's team (above);
        # THIS TURN's domain (`policy.domain(domain_hint).escalation_team_code`,
        # `turn/policy_rows.py`) - a deterministic fact about the QUESTION the
        # parser was just asked, read before the prior-turn carry because a turn
        # that named a real domain is a fresher fact than whatever team a stale
        # session happened to be carrying (AC-EQ-16/17: an incoming ask carrying
        # "purchasing" forward must not paint the NEXT turn's plain stock question
        # "purchasing" too - AC-EQ-20 is the same shape for an unanswered open
        # offer, which reaches this same fallback since it named no `accepted_team`
        # either); a PREVIOUS turn's own carried routing (`_prior_suggested_team`,
        # test_pass4_item5's B3) - still applies when THIS turn names no resolvable
        # domain at all (AC-EQ-19, `policy.domain(None)` is `None`); the hard
        # default (`DEFAULT_SUGGESTED_TEAM`), last of all.
        domain_row = policy.domain(out.get("domain_hint")) if policy else None
        domain_team = domain_row.escalation_team_code if domain_row else None
        routing["suggested_team"] = (
            domain_team or _prior_suggested_team(prior_session) or DEFAULT_SUGGESTED_TEAM
        )
    # `suggested_agent`'s default is applied once, upstream, by `with_routing_agent_default`
    # (finding 2b) - the access read and the lanes see the same value.
    out["routing"] = routing
    # AC-1700: a POSITION over an accepted `member_offer` names that SPECIFIC member
    # (`apply`'s `trace.assignee`) - `lanes/escalation.py::escalation_context` reads
    # this exact key (`output.escalation.preferred_assignee_id`), the retired
    # `head/output_exchange`'s own field, now written by the seam that replaced it.
    # `None` (a bare "yes") leaves whatever the verdict already carried untouched.
    if accepted_assignee:
        out["escalation"] = {**(out.get("escalation") or {}), "preferred_assignee_id": accepted_assignee}
    # The company half of the same idiom (hand pass 11, blocker 2): a POSITION over the
    # company clarify names a COMPANY the customer just picked, and `escalation_context`
    # resolves a named company through ONE key - `output.escalation.company_pick`, which
    # it then validates against the offered pool (`escalation.py:232-255`). Writing the
    # picked option's name here means the position and the typed word reach routing
    # through the SAME seam instead of two, and the validation still runs on both. The
    # verdict's own `company_pick` (the customer typed the name) outranks it: this only
    # fills what the message itself did not say.
    if accepted_company and not (out.get("escalation") or {}).get("company_pick"):
        out["escalation"] = {**(out.get("escalation") or {}), "company_pick": accepted_company}
    # Round 4 (owner-approved, 22 Sep 2026): the brand half of the SAME acceptance
    # carry the agent uses - `_accepted_pending_brand` shares `_accepted_pending_
    # field`'s gate/accept-check with `_accepted_pending_agent`, so an unaccepted
    # turn carries no brand either. `escalation_context`'s own new `carried_brand`
    # rung reads this key back (`lanes/escalation.py`), after its picked-member/
    # company-pick/same-team arms - a SPECIFIC row's own brand there must still
    # outrank a generic carry, which is why this writes a NEW key rather than
    # touching `company_pick`/`preferred_assignee_id` at all.
    carried_brand = _accepted_pending_brand(pending, verdict)
    if carried_brand:
        out["escalation"] = {**(out.get("escalation") or {}), "carried_brand": carried_brand}
    # AC-1703's tail, captain's ruling 20 Sep 2026: a decline over a NON-escalation
    # offer (a did-you-mean roster's own attached escalate sentence, a detail offer)
    # finishes on the SAME `escalation_declined` branch kind as an actual escalation
    # decline - `apply`'s `trace.lane == "offer_declined"` is the only place that
    # knows which of the two this turn was, so it is carried here rather than a
    # second branch kind, the same "one flag on ctx.parse.output" idiom
    # `preferred_assignee_id` just above uses. `escalate_catalog` reads it back to
    # choose R22(a)'s own registry copy over the generic "Escalation declined." line.
    if declined_offer_copy:
        out["chatbot_declined_offer_copy"] = True
    return out


# --------------------------------------------------------------------------- #
# Stage E: resolve, then the tool
# --------------------------------------------------------------------------- #


# `_token_key`: the key the resolver's OWN answer is filed under, for a join against
# it. Separators are REMOVED, not just lower-cased: `resolve_gate.resolve_entity_body`
# sends a product entity through `_PRODUCT_FOLD` (`[-\s]+`) before the resolver ever
# sees it, so a token the customer typed as `SRTWT165-FT` comes back in
# `unresolved_tokens` as `SRTWT165FT`. Keying one side with the hyphen and the other
# without silently failed the join for EVERY hyphenated code - measured on turn
# bb921451 (hand pass 7, B1): `unresolved_tokens: ["SRTWT165FT"]` against an entity
# whose `raw` is `SRTWT165-FT` gave `unplaced == {}`, so the "I could not find X"
# sentence and the unfiltered-catalogue guard (`_without_guesses`) were both dead for
# exactly the codes that need them most. Sorento product codes are hyphenated far more
# often than not.
#
# Hand pass 12 Phase 3 finding F8: this used to be its own copy of `turn.state.
# token_key`'s exact body (`turn/reconcile.py::_key` carried a second one) - moved
# there, beside `fold_token` itself (the ONE copy `turn.narrow._token_of`, R1, also
# uses), and re-imported here under its own established name so every other module's
# docstring reference to `turn_runtime._token_key` still resolves.
_token_key = token_key


def _entity_token_key(entity: dict[str, Any]) -> str:
    """`_token_key` of whichever of the three names a row spells its code under - the key
    to join a plan/compatible row against `unplaced_tokens`."""
    return _token_key(_code_of(entity))


def _entity_token_key(entity: dict[str, Any]) -> str:
    """`_token_key` of whichever of the three names a row spells its code under - the key
    to join a plan/compatible row against `unplaced_tokens`."""
    return _token_key(_code_of(entity))


def _entity_is_unplaced(entity: dict[str, Any], unplaced: dict[str, str]) -> bool:
    """Does this entity carry NOTHING real - no uuid of its own, and its own token key
    is one the resolver could not place THIS turn?

    Hand pass 12 Phase 3 finding F10 (AC-1704 regression): a roster PICK already gives
    its built entity a real `uuid` (`turn/apply.py::_answer_pending`) straight from the
    option the customer chose - by TYPING BACK the roster's own offered code, exactly
    like a position pick. The resolver is independently asked about the SAME raw text
    this message typed (`with_carried_entities` hands over the message's own entities
    untouched, never the focus carry, whenever the message names any at all) and can
    report that exact text as unplaced - the two facts are not in conflict, a pick
    settled it and a fresh, parallel resolve of the same text found nothing new. The
    two `would_be_unfiltered`/`_answered_unfiltered` guards below used to read ONLY the
    token-key membership, so an entity that already carried a real uuid was still
    counted as "nothing placed" the moment its own text also failed the resolver,
    which silently dropped the second tool call a continued roster pick needs.
    """
    return not entity.get("uuid") and _entity_token_key(entity) in unplaced


def unplaced_tokens(entities: list[Any], resolved: Any) -> dict[str, str]:
    """The tokens THIS message named that the resolver could not place, lower-cased.

    `unresolved_tokens` is the resolver's own verdict and the only honest one: a token it
    lists there has no match, whatever it may also have returned under that token's name.
    Measured on turn 7cf56afe ("stock wc287 wc2867 7445"): `wc2867` is in
    `unresolved_tokens` and the same resolution carries ten `spec_search` rows matched on
    the CLASS word it read out of the whole message ("Sorento water closet."), none of
    which is the thing the customer typed.
    """
    named: dict[str, str] = {}
    for entity in jsc.array(entities):
        raw = jsc.nullish_str(jsc.get(entity, "raw")).strip()
        key = _token_key(raw)
        if key and key not in named:
            named[key] = raw
    missed = {_token_key(x) for x in jsc.array(jsc.get(resolved, "unresolved_tokens"))}
    # Keyed on the folded token, valued with the word the CUSTOMER typed, so the answer
    # can quote it back rather than a normalised copy of it.
    return {key: raw for key, raw in named.items() if key in missed}


def companies_by_uuid(resolved: Any) -> dict[str, dict[str, Any]]:
    """R-g (owner hand pass 7, 19 Sep 2026): the resolver's own COMPANY per match, keyed
    by uuid - `{"company_id", "company_name"}`, both stamped by the same pass
    (`entity_resolver._attach_company_info`, which writes the id and the name together).

    Read straight off the RAW resolver payload (never off `gate.py`'s own
    `compatible_entities`/`by_uuid`, which `tests/chatbot/test_replay.py`'s frozen corpus
    compares byte-for-byte; an extra key there broke 100+ recorded fixtures that carry a
    `company_name` on a match with nothing to do with this feature). Flattened the same
    three ways `gate.py::run_gate` flattens its own `flat` list (resolutions, intersection,
    by_entity_type), so a match this module never reads through `compatible_entities`
    still contributes its company - `candidates_by_kind` below only reads the entry for a
    uuid that IS in `compatible`.

    The ID is what ROUTES (`lanes/escalation.py::_next_assignee_body` posts `company_id`
    and nothing else; `external/next_assignee.py` falls back to the CONTACT's company
    when it is absent), so a reader that carries only the name carries nothing routable -
    the hand pass 11 blocker this pair exists to close.
    """
    out: dict[str, dict[str, Any]] = {}

    def _consume(matches: Any) -> None:
        for m in jsc.array(matches):
            uuid = jsc.nullish_str(jsc.get(m, "uuid")).strip()
            company = jsc.get(m, "company_name")
            if uuid and isinstance(company, str) and company.strip():
                out.setdefault(
                    uuid,
                    {
                        "company_id": jsc.nullish_str(jsc.get(m, "company_id")).strip() or None,
                        "company_name": company.strip(),
                    },
                )

    from app.services.chatbot.lanes.business.gate import _flatten_by_entity_type

    for resolution in jsc.array(jsc.get(resolved, "resolutions")):
        _consume(jsc.get(resolution, "matches"))
    _consume(jsc.get(resolved, "intersection"))
    _consume(_flatten_by_entity_type(jsc.get(resolved, "by_entity_type")))
    return out


def company_names_by_uuid(resolved: Any) -> dict[str, str]:
    """`companies_by_uuid`, names only - the shape `candidates_by_kind` has always read.

    Public (reviewer N-a, hand pass 11): `answer_bridge` imported the private name across
    module boundaries, which is a fact about this seam's audience, not about its privacy.
    """
    return {uuid: row["company_name"] for uuid, row in companies_by_uuid(resolved).items()}


def _without_guesses(
    compatible: list[dict[str, Any]], resolved: Any, unplaced: dict[str, str]
) -> list[dict[str, Any]]:
    """`compatible` minus the rows that ONLY a guess matched.

    ONLY when the resolver said it could not place a token this message named. That
    verdict is the whole trigger: "stock for srttwc286" put `srttwc286` in
    `unresolved_tokens` and then returned a SECOND resolution under the token `stock for
    srttwc286` - the whole message, which the resolve route adds as a phrase of its own -
    carrying 200 products at `match_tier: spec_search`, `similarity: 0.0`, and the
    inventory fetch ran for every one of them (turn 11476016).

    A phrase-shaped token is NOT a guess by itself: in AND mode the resolver reports the
    intersection under exactly that shape, and those rows are the named token's real
    answer ("Incoming and stock for 7445" -> the four SRTWT7445 variants,
    `unresolved_tokens` empty). So the phrase test only applies once a named token has
    already been reported unplaced.

    A row a REAL token also matched stays, because then it is that token's answer and the
    guess merely agreed.

    A COUNTED DESCRIBED SET is not a guess either (hand pass 12 R8, owner ruling, turn
    7c39e638 "close couple wc available stock in p trap"): when the resolver's own answer
    carries a `predicate` with a positive `qualifying_total`, the phrase-shaped resolution
    IS that set - `references._emit_spec_matches` emits exactly the qualifying candidates
    `resolve_product_set` counted, over membership the described words actually bound, not
    a similarity reach at a token nothing placed. Turn 11476016's own defect (the
    `similarity: 0.0` catalogue sweep this function exists for) carries no predicate at
    all: `resolve_gate.resolve_entity_body` withholds `require` for a turn that names a
    typed CODE and no class word, so the guard below still fires there unchanged.
    """
    if not unplaced:
        return compatible
    described = jsc.get(resolved, "predicate")
    qualifying = jsc.get(described, "qualifying_total") if isinstance(described, dict) else None
    set_answered = isinstance(qualifying, int) and not isinstance(qualifying, bool) and qualifying > 0
    asked = {_token_key(t) for t in jsc.array(jsc.get(resolved, "tokens"))} - {""}
    placed: set[str] = set()
    guessed: set[str] = set()
    for resolution in jsc.array(jsc.get(resolved, "resolutions")):
        token = _token_key(jsc.get(resolution, "token"))
        # `asked` is only evidence when the answer carries it: a stub or an older
        # recording that lists no `tokens` at all must not turn every resolution it
        # DOES carry into a guess.
        phrase = bool(asked) and token not in asked and not set_answered
        bucket = guessed if (token in unplaced or phrase) else placed
        for match in jsc.array(jsc.get(resolution, "matches")):
            uuid = jsc.nullish_str(jsc.get(match, "uuid")).strip()
            if uuid:
                bucket.add(uuid)
    drop = guessed - placed
    if not drop:
        return compatible
    return [e for e in compatible if jsc.nullish_str(e.get("uuid")).strip() not in drop]


@dataclass(frozen=True)
class ResolveOutcome:
    """The resolver seam's own answer for this turn (AC-1681, PLAN-chatbot-answer-half-
    reattach.md slice R2).

    The first seven fields are `resolve_kinds`'s own long-standing 7-tuple, unchanged in
    shape, order and meaning (see that function's own docstring for what each one is).
    `payload` is new: the raw dict `resolve_gate.run` returned for this turn (`resolved`,
    `gate`, `aggregate`, `tier_gate`, `_exit_kind`), carried through so a later slice can
    read the resolver's REAL gate, its tier-gate outcome and its exit kind without a
    second resolver call. `None` on `resolve_kinds`'s two existing early returns (no
    entities named; the resolver raised) - there is no resolver answer to carry then.
    """

    resolved_kinds: dict[str, dict[str, int]]
    compatible_entities: list[dict[str, Any]]
    predicate: dict[str, Any] | None
    resolved_candidates: dict[str, list[dict[str, Any]]]
    unplaced_tokens: dict[str, str]
    spec_tier: bool
    payload: dict[str, Any] | None


def resolve_kinds(
    db: Session,
    *,
    ctx: dict[str, Any],
    branch_kind: str,
    space_id: str | None,
    dry_run: bool,
    stamp_incoming: bool = False,
    stamp_customer: bool = False,
    stamp_promotion: bool = False,
    stamp_purchase_order: bool = False,
    roster_caps: Mapping[str, int] | None = None,
) -> ResolveOutcome:
    """Ask the resolver what each named token actually IS (AC-1527).

    Returns a `ResolveOutcome` whose first six fields are
    `(resolved_kinds, compatible_entities, predicate, resolved_candidates,
    unplaced_tokens, spec_tier)`, where `unplaced_tokens` is
    `{folded token: the word the customer typed}` for every token this message named
    that the resolver could not place, and `spec_tier` is `spec_tier_matched(resolved)` -
    which tier of the ONE product ladder answered, and therefore whether this turn
    renders as a counted set or as a list.

    A seventh field, `unplaced_alternatives`, is gone with its producer (reviewer S3,
    review round): its only consumer, `make_tool_runner`'s `alts_by_token`, went with
    `_alternatives_ask` when production's own did-you-mean took that job back, and the
    resolver's `resolutions[*].alternatives` is still read where it belongs - by
    `miss_suggest.build_suggest_offer`'s own D1 arm.

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
    `stamp_promotion` and `stamp_purchase_order` are the same seam for those two domains'
    product rosters (owner hand pass 3, rows 1 and 7): has promo / no promo, has PO / no
    PO, measured by the domain's own per-product read.

    `branch_kind` decides which `entry` this call makes into `resolve_gate.run`
    (`lanes.business.ENTRY_BY_BRANCH_KIND`, R2) - a real, computed branch_kind, not a
    literal, so a promotion ask reaches the tier-gate arm ("access_check") instead of
    the generic "resolve" every branch used to share.

    `roster_caps` (PLAN-chatbot-answer-half-reattach.md "Roster cap") is
    `{entity kind: chatbot_entity_kinds.roster_cap}`. The engine passes its own read
    of the already-loaded `Policy` object (no second query); a caller with no policy
    of its own leaves it `None` and this function reads `chatbot_entity_kinds`
    directly - either way it is forwarded to `resolve_gate.run` -> `gate.run_gate`,
    the one place a roster is actually cut.
    """
    from app.services.chatbot.lanes.business import ENTRY_BY_BRANCH_KIND
    from app.services.chatbot.lanes.business import pickers
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business import services as business_services

    entry = ENTRY_BY_BRANCH_KIND.get(branch_kind, "resolve")
    entities = (jsc.get(jsc.get(ctx, "parse"), "output") or {}).get("entities") or []
    # Security B1/S1 (review round, 20 Sep 2026): the `access_check` entry is about the
    # CONTACT, not about anything the message named - `resolve_gate.run` reads the
    # entitlement and runs the tier gate BEFORE resolve-entity is even called, and main's
    # own `run_until_exit` enters there for every `check_promotion` turn whether or not a
    # product was named. Skipping the resolver for an entity-less turn was a rearch-only
    # shortcut, and it cost the two turns that need the entitlement most: a bare "promo"
    # (no product) fell through to `narrow.py`'s entitlement-BLIND tier menu, and the turn
    # that ANSWERS a tier pick (a bare "1", no entity of its own) reached `_tier_gate`
    # with no entitlement to recompose against at all.
    if not entities and entry != "access_check":
        return ResolveOutcome({}, [], None, {}, {}, False, None)
    if roster_caps is None:
        from app.models.chatbot_policy import ChatbotEntityKind

        try:
            roster_caps = {
                row.kind: row.roster_cap for row in db.query(ChatbotEntityKind).all()
            }
        except Exception:  # noqa: BLE001 - a caller handing over a test double with no
            # real session (every `resolve_kinds` test that stubs `resolve_gate.run`
            # entirely) has no opinion on roster caps either; `gate.run_gate`'s own
            # `legacy_default` then stands, exactly as it does for any other caller
            # that never adopted this column.
            roster_caps = None
    services = business_services.production_services(db)
    try:
        payload = resolve_gate.run(
            ctx,
            entry,
            {"branch_kind": branch_kind},
            services=services,
            space_id=space_id,
            probe_default_start=resolve_gate.default_probe_start(),
            dry_run=dry_run,
            roster_caps=roster_caps,
        )
    except Exception:  # noqa: BLE001 - see the docstring: nothing to reconcile, not a failure
        logger.warning("chatbot: the resolver did not answer", exc_info=True)
        return ResolveOutcome({}, [], None, {}, {}, False, None)

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
    unplaced = unplaced_tokens(entities, resolved)
    compatible = _without_guesses(compatible, resolved, unplaced)
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
        #
        # F2 (R2): the gate's OWN `customer_probe_entities` (built at `gate.py:975-979`)
        # carries the product alongside the customers when the picker arm actually ran
        # and substituted a customer-only `compatible_entities` (`gate.py:864-866`,
        # `1053-1061`) - probing `compatible` there measures every DO for the customer,
        # not just this product's, and can stamp "no DO" on a customer who has DOs, just
        # none for the product actually asked. Falls back to `compatible` when the gate
        # never built one (this turn's own picker arm did not run).
        probe_entities = [
            e for e in jsc.array(gate.get("customer_probe_entities")) if isinstance(e, dict)
        ] or compatible
        probe = resolve_gate.probe_customer(
            services,
            ctx=ctx,
            entities=probe_entities,
            aggregate=payload.get("aggregate"),
            default_start=resolve_gate.default_probe_start(),
            space_id=space_id,
        )
        customer_bases = pickers.customer_bases_with_do(probe)

    product_stamp: tuple[set[str], str, str] | None = None
    wants_product_stamp = (stamp_promotion or stamp_purchase_order) and any(
        jsc.nullish_str(e.get("entity_type")).strip().lower() == "product" for e in compatible
    )
    if wants_product_stamp and not isinstance(stamps_from.get("incoming_by_code"), dict):
        # Rows 1 and 7: the promotion and purchase-order rosters carry the same has/no
        # stamp the incoming roster does, from the same seam. The incoming stamp wins when
        # both are on the table: it is the domain the gate itself measured, and one line
        # cannot say two things. `promotion` first for the same reason the plan lists it
        # first - a turn is asked for one of these domains, not both.
        probe_fn = (
            resolve_gate.probe_promotion if stamp_promotion else resolve_gate.probe_purchase_order
        )
        codes = pickers.product_codes_in(
            probe_fn(
                services,
                ctx=ctx,
                entities=compatible,
                aggregate=payload.get("aggregate"),
                space_id=space_id,
            )
        )
        if codes is not None:
            product_stamp = (
                (codes, "has promo", "no promo")
                if stamp_promotion
                else (codes, "has PO", "no PO")
            )

    return ResolveOutcome(
        by_token,
        compatible,
        predicate,
        candidates_by_kind(
            stamps_from, compatible, customer_bases, product_stamp, company_names_by_uuid(resolved)
        ),
        unplaced,
        spec_tier_matched(resolved),
        payload,
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
    product_stamp: tuple[set[str], str, str] | None = None,
    company_names_by_uuid: dict[str, str] | None = None,
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
        # R-g (owner hand pass 7, 19 Sep 2026): the same additive carry as `name`
        # above, off the RAW resolver's own `company_name` (`company_names_by_uuid`,
        # read off `resolved` rather than off `gate.py`'s own `compatible_entities` -
        # see that function's own docstring for why) - `turn/narrow.py::_options` reads
        # it so a code that is a SEPARATE record in two companies stays two options,
        # never merged into one because they share a label.
        company_name = (company_names_by_uuid or {}).get(row.get("uuid") or "")
        if isinstance(company_name, str) and company_name.strip():
            built["company_name"] = company_name.strip()
        if code in stamps:
            built["stamp"] = "has incoming" if stamps[code] else "no incoming"
        elif kind == "product" and product_stamp is not None:
            # Rows 1 and 7: the same line a product carries under incoming, for the
            # promotion and purchase-order rosters - `(codes measured, has, no)`, so the
            # two domains that needed it do not each grow a branch of their own.
            codes_with, has_label, no_label = product_stamp
            built["stamp"] = has_label if _norm_code(code) in codes_with else no_label
        elif kind == "customer" and customer_bases_with_do is not None:
            # Item 2: a customer line says what a product line says - whether the thing
            # it names has anything to show. `None` is "not measured" (the probe failed,
            # or its page saturated) and reads as no stamp at all, never as "no DO".
            base = pickers_module().customer_base(built.get("name") or code)
            built["stamp"] = "has DO" if base in customer_bases_with_do else "no DO"
        grouped.setdefault(kind, []).append(built)
    return grouped


def _norm_code(value: Any) -> str:
    """`pickers._norm`'s own rule, for the one comparison this module makes itself."""
    return jsc.nullish_str(value).strip().lower()


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


# Ported from PR #1118 (feat/chatbot-dealer-stock-verdict, not merged, owner ruling
# 24 Sep 2026) for chatbot-stock-ask-v2 S3.
def _int(value: Any) -> int | None:
    """A quantity as an int, or None for anything that is not one.

    SEC-N4 (#1118 security review, round 1): a digit STRING counts, because a value
    read back off a session row written by an older build (or by hand) is whatever
    JSON carried - and `requested_quantities` is validated at the route, where one
    bad value is a 400 that kills the whole fetch rather than one product. `bool` is
    not a number here: `True` is 1 in Python and a quantity of one is not what a
    boolean meant.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _spec_quantities(
    out: dict[str, Any], spec: FetchSpec, entities: list[dict[str, Any]]
) -> dict[str, Any]:
    """`{product uuid: quantity}` for this fetch, as the lane's own key (D13, D20,
    ported from PR #1118, not merged).

    Two sources, one shape, and this is the one seam where both halves exist. The
    OPEN TASK's own slots win where a task drove the fetch (`turn/task.py::
    StockQtyTask.to_fetch` stamps them on the spec) - they carry quantities this
    message never repeated, which is the whole point of the task. Otherwise it is
    the quantities THIS message stated per entity, joined by CODE to the uuid the
    resolver placed: the first turn of a stock ask has no task yet, because nothing
    has told the engine a quantity is required until the reply says so (D25).
    """
    carried = spec.filters.get("requested_quantities")
    if isinstance(carried, dict) and carried:
        # SEC-N4: coerced here too, not only in `StockQtyTask.to_fetch` - this is the
        # LAST seam before the value becomes a query param, and a caller that built
        # the spec by hand must not be able to 400 the whole fetch with one bad slot.
        coerced = {
            str(key): _int(value)
            for key, value in carried.items()
            if _int(value) is not None
        }
        return {**out, "requested_quantities": coerced} if coerced else out
    by_code: dict[str, int] = {}
    for e in jsc.array(out.get("entities")):
        if not isinstance(e, dict):
            continue
        quantity = _int(e.get("quantity"))
        if quantity is None:
            continue
        for name in ("canonical_code", "raw"):
            code = e.get(name)
            if isinstance(code, str) and code.strip():
                by_code[code.strip().casefold()] = quantity
    if not by_code:
        # D13 lives in ONE place (review round 9, finding 5): `turn/apply.py::
        # _normalise_demand_qty` writes a single named code's top-level `demand_qty`
        # onto the entity itself, before the task step, the narrowing or this seam
        # read anything - so by the time a fetch is built the quantity is always per
        # entity, whichever field the parser happened to fill.
        return out
    quantities: dict[str, int] = {}
    for e in entities:
        uuid = e.get("uuid") if isinstance(e, dict) else None
        if not isinstance(uuid, str) or not uuid:
            continue
        for name in ("code", "canonical_code", "raw"):
            code = e.get(name)
            if not isinstance(code, str) or not code.strip():
                continue
            quantity = by_code.get(code.strip().casefold())
            if quantity is not None:
                quantities[uuid] = quantity
                break
    return {**out, "requested_quantities": quantities} if quantities else out


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

    # EVERY carried product, not the first: "all" over a ten-variant roster settles ten
    # codes onto the focus, and carrying one of them re-ran the report for that one under
    # a header naming it (turn 0a6f0379 then f8ed3b97, 16 Sep 2026).
    #
    # AC-1692's own rule, one layer up: this function's own docstring says the focus
    # rides in "already resolved" - `canonical_code` (D10's own settle,
    # `_settle_question_subject`, or the resolver's own match) is that evidence,
    # `raw` alone is not. The customer loop below never falls back to a raw guess at
    # all; this one used to, and a refinement's own unresolvable product word
    # ("cheaper") rode out as `outstanding_carried_product_code` - the same
    # never-resolved-code-echoed-back bug `_spec_row` fixes at the fetch seam,
    # caught here first since this is where it enters `parse_output`.
    carried_codes: list[str] = []
    for entity in focus.products:
        if not isinstance(entity, dict):
            continue
        code = entity.get("canonical_code") or entity.get("code")
        if code and str(code) not in carried_codes:
            carried_codes.append(str(code))
    if carried_codes:
        out["outstanding_carried_product_code"] = carried_codes[0]
        if len(carried_codes) > 1:
            out["outstanding_carried_product_codes"] = carried_codes
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


def _record_key_rerun_split(
    domain: str,
    verdict: dict[str, Any],
    entities: list[dict[str, Any]],
    resolved: dict[str, dict[str, int]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]] | None:
    """Hand pass 12 round 2, Group C (owner ruling): the rerun's own entities (this
    domain's own RECORD KEY alone, `policy_rows.RECORD_KEY_KIND`), the ones it drops,
    and the WORDS the customer actually typed for the record key (read off `verdict.
    entities` directly, never off the resolved row's own `canonical_code` - a
    shipment resolves to the resolver's own canonical identity, `entity_resolver.py::
    _probe_inbound_shipment`'s `shipment_number`, which is NOT the container number a
    customer typed and the match came in on; measured directly, C1's own turn) - or
    `None` when this fetch is not a record-key-rerun candidate at all.

    `decide.py:427-478`'s own REFINE table is untouched - a combined call still
    carries every carried filter on its FIRST try, exactly as it does today. This is
    the ANSWERING side only, and it reads THIS message's own typed entities (`verdict.
    entities`, `current_message: True`) rather than re-deriving the decision: a typed
    FILTER (customer, product, date, brand - anything whose hint the domain does not
    name as ITS OWN record) never matches `RECORD_KEY_KIND` and so never reruns (C3,
    C4, C6's own green guards). A record key typed ALONE (nothing to drop) or a domain
    with no record key at all both read `None` too - there is nothing to rerun for.

    Hand pass 12 round 4, R4 (owner ruling 5): whether this message's own entity IS the
    domain's record key is decided by what the RESOLVER placed its token as, never by
    what the parser hinted. `resolved` is the resolver's own by-token map
    (`resolve_kinds`'s `by_token`), joined through the ONE fold-aware copy of that join,
    `reconcile.hits_for_token`. Turn 50082c60: a container number on an incoming focus
    was hinted `product` by the parser, the resolver placed it as an `inbound_shipment`
    and reconciliation rewrote the kind, but this gate still read the hint - so the
    combined call's miss stood with no rerun at all, while the correctly-hinted sibling
    turn reran on the shipment alone and answered. The hint is the FALLBACK only, for a
    token the resolver said nothing about, which leaves a resolver-less caller reading
    exactly as it did before. The MIRROR mishint (hinted `inbound_shipment`, resolved
    `product`) still never reruns: a resolved `product` is not this domain's record key,
    so this gate refuses it on the same fact the `keep`/`drop` split below already
    refuses it on.
    """
    record_kind = policy_rows.RECORD_KEY_KIND.get(domain)
    if not record_kind:
        return None

    def _fold(kind: Any) -> Any:
        return EXTRA_KIND_ALIASES.get(kind, kind) if isinstance(kind, str) else kind

    def _typed_the_record_key(entity: dict[str, Any]) -> bool:
        hits = hits_for_token(resolved, entity.get("raw"))
        if hits:
            return any(_fold(kind) == record_kind for kind, count in hits.items() if count)
        return _fold(entity.get("hint")) == record_kind

    current_kind_entities = [
        e
        for e in (verdict.get("entities") or [])
        if isinstance(e, dict) and e.get("current_message") is True and _typed_the_record_key(e)
    ]
    if not current_kind_entities:
        return None

    keep = [e for e in entities if _fold(e.get("entity_type")) == record_kind]
    drop = [e for e in entities if _fold(e.get("entity_type")) != record_kind]
    if not keep or not drop:
        return None
    typed_words = [
        w
        for w in (
            jsc.js_string(e.get("canonical_code") or e.get("raw")).strip()
            for e in current_kind_entities
        )
        if w
    ]
    return keep, drop, typed_words


def _entity_display(entity: dict[str, Any]) -> str | None:
    """The word a rerun's own dropped-filter sentence names a DROPPED row by - its
    code where it has one (a product, an order number carried on the focus with raw
    == code), else the raw a customer typed with no code to resolve to (a customer
    name seeded with no separate code, R12 round 2's own C5 fixture)."""
    value = entity.get("code") or entity.get("canonical_code") or entity.get("raw")
    return jsc.js_string(value).strip() or None if value else None


def _drop_focus_entities(focus: Focus, dropped: list[dict[str, Any]]) -> None:
    """Hand pass 12 round 2, Group C: the carried entity a record-key rerun just
    proved wrong (the combined call missed; the rerun on the record key alone did
    not) must not still ride the focus into the NEXT turn - `focus.after` drops it,
    the same "what the ANSWER was about" rule `turn/apply.py::_narrow_and_plan`
    already applies for a freshly-settled kind (S6d's own comment there), applied
    here for a kind a rerun just SETTLED THE OPPOSITE WAY about.
    """
    codes_by_kind: dict[str, set[str]] = {}
    for entity in dropped:
        kind = entity.get("entity_type")
        code = entity.get("code") or entity.get("canonical_code") or entity.get("raw")
        if isinstance(kind, str) and kind and code:
            codes_by_kind.setdefault(kind, set()).add(str(code))
    for kind, codes in codes_by_kind.items():
        attr = KIND_FIELD_MAP.get(kind)
        # P6 (hand pass 12 Phase 3): `KIND_FIELD_MAP` only names the four plural
        # fields - an "order"/"inbound_shipment"/etc kind lives in `focus.extra`
        # instead (through the SAME `EXTRA_KIND_ALIASES` fold `apply._set_kind_field`
        # writes it through), and used to be silently skipped here, so a dropped
        # extra-bucket entity rode straight into the next turn.
        if not attr:
            extra_key = EXTRA_KIND_ALIASES.get(kind, kind)
            current = focus.extra.get(extra_key)
            if not isinstance(current, list):
                continue
            focus.extra[extra_key] = [
                row
                for row in current
                if not (
                    isinstance(row, dict)
                    and str(row.get("canonical_code") or row.get("code") or row.get("raw")) in codes
                )
            ]
            continue
        current = getattr(focus, attr, None)
        if not isinstance(current, list):
            continue
        kept = [
            row
            for row in current
            if not (
                isinstance(row, dict)
                and str(row.get("canonical_code") or row.get("code") or row.get("raw")) in codes
            )
        ]
        setattr(focus, attr, kept)


def make_tool_runner(
    db: Session,
    *,
    ctx: dict[str, Any],
    verdict: dict[str, Any],
    focus: Focus,
    compatible_entities: list[dict[str, Any]],
    predicate: dict[str, Any] | None,
    unplaced: dict[str, str],
    space_id: str | None,
    dry_run: bool,
    turn_trace: Any,
    counted_set: bool = False,
    resolver_gate: dict[str, Any] | None = None,
    resolver_tier_gate: dict[str, Any] | None = None,
    resolved_kinds: dict[str, dict[str, int]] | None = None,
    policy: Any = None,
) -> Callable[[str, FetchSpec], dict[str, Any]]:
    """The ONE seam that reaches a tool: `run_fetch` calls it once per `FetchSpec`.

    The tool pick, the argument build, the MCP call and the row structuring are all the
    kept lane's (`lanes/business.run_fetch` -> `lanes/business/fetch.output_structurer`),
    so a domain answers with exactly the rows it answers with today; what is new is that
    the lane is asked once PER DOMAIN, from a plan, instead of once per turn.

    `resolver_gate` is the resolver's OWN gate for this turn (R2, `ResolveOutcome.
    payload["gate"]`) - `gate_reason`, `require_specific`, `customer_probe_entities`,
    `company_team`, `gate_debug`, whatever it carries. The gate handed to
    `lanes.business.run_fetch` starts from it, unchanged, so those fields reach the
    lane for the first time; `compatible_entities` and `predicate` are still set
    exactly as today (the per-domain narrowed spec entities, the counted-set block),
    overriding whatever `resolver_gate` itself carried under those two keys.
    `resolver_gate=None` (no resolver ran) reproduces today's synthetic gate exactly -
    a bare `compatible_entities` key and nothing else.

    `resolver_tier_gate` (PLAN-chatbot-answer-half-reattach.md slice R3, captain ruling
    20 Sep 2026) is the resolver's OWN `tier_gate` output (`ResolveOutcome.
    payload["tier_gate"]`) - the entitled-tiers-and-availability read from the real
    `access_check` entry, the source of the has/no-promotion stamps. It reaches
    `lanes.business.run_fetch` only when NO tier has been settled yet
    (`spec.filters.get("tier")` falsy - no pick has happened): once a tier IS settled,
    today's synthetic `_tier_gate(spec, verdict, focus)` recompose stands, unchanged -
    that is the KEPT lane's own tier x brand entitlement recomposition, not something
    the resolver's raw read replaces.

    `resolved_kinds` is the resolver's OWN by-token map (`ResolveOutcome.resolved_kinds`,
    the same one reconciliation rewrites a mishinted kind from). One reader: the
    record-key rerun gate below, which asks what the resolver PLACED this message's
    token as rather than what the parser hinted (R4, owner ruling 5). `None` (no
    resolver ran) falls back to the hint, exactly as this read behaved before.
    """
    from app.services.chatbot.lanes import business
    from app.services.chatbot.lanes.business import fetch as business_fetch
    from app.services.chatbot.lanes.business import gate as gate_mod
    from app.services.chatbot.lanes.business import services as business_services

    def runner(domain: str, spec: FetchSpec) -> dict[str, Any]:
        page_predicate: dict[str, Any] | None = None
        page_ids: list[str] = []
        carry = spec.filters.get("set_page")
        if isinstance(carry, dict):
            # Security B2: the entitlement comes off the CARRY (what page 1 answered
            # under), never off this turn's verdict - a bare "more" states no tier, and
            # an empty list is read downstream as "no tier filter at all".
            page_predicate, page_ids = page_the_set(db, carry)
        # R6 (fix round 2), corrected in fix round 4: `policy` is threaded through
        # so a null `routing.suggested_team` gets a domain-aware fill here too,
        # rather than the flat `DEFAULT_SUGGESTED_TEAM` literal - but this is the
        # DOMAIN RUNG ONLY. Unlike `engine.py`'s own `lane_parse_output` call, this
        # one passes no `pending`/`prior_session`, so the fetch context's own
        # `routing.suggested_team` can never come from an open offer or a carried
        # prior-turn team the way the turn's real `ctx.parse.output` can (measured,
        # fix round 4: case-025 turn 1's fetch context reads "purchasing" off the
        # domain rung while its parse output reads "warehouse" off the open offer -
        # the two genuinely disagree). Not a bug worth chasing today: nothing reads
        # this fetch context's own `routing.suggested_team` - `lane_out` feeds tool
        # ARGS (access levels, date filters, entities), never an escalate sentence
        # or a pending write, both of which read the turn's real `ctx.parse.output`
        # instead. Flagged here so the next reader does not assume parity.
        lane_out = lane_parse_output(verdict, focus=focus, domain=domain, policy=policy)
        lane_out = _spec_window(lane_out, spec)
        answered = spec.filters.get("outstanding")
        if isinstance(answered, dict):
            lane_out = outstanding_carry(lane_out, focus, answered)
        lane_ctx = {
            **ctx,
            "parse": {**(ctx.get("parse") or {}), "output": lane_out},
        }
        if page_predicate is not None:
            entities = [
                {"uuid": pid, "entity_type": "product", "canonical_code": None}
                for pid in page_ids
            ]
        elif spec.filters.get("task"):
            # Ported from PR #1118 (not merged): an OPEN TASK's own fetch is about the
            # TASK's subjects, all of them (`turn/task.py::StockQtyTask.to_fetch`): a
            # turn answering two of four products resolves only those two, and
            # `_entities_for` below would keep exactly the resolver's two - so the
            # answer would silently drop the two the dealer had already given a
            # quantity for. The task is the only honest record of what the question is
            # about.
            entities = [_spec_row(e) for e in spec.entities]
        else:
            entities = _entities_for(spec, compatible_entities)
        # Hand pass 12, Group F: a multi-ledger customer pick's own entities carry no
        # `display_name` at all (`turn/apply.py::_answer_pending` leaves it off on
        # purpose for an option covering several uuids) - filled in here, the same
        # DB-backed read `resolve_kinds` already does for a freshly-resolved customer
        # (line ~906 above), so the miss header can name each ledger rather than
        # falling back to the option's own rollup code.
        fill_customer_names(db, entities)
        # Ported from PR #1118 (not merged), D13/D20: the dealer's own quantity per
        # product, resolved to uuids here - `lanes/business/fetch.py` reads it
        # straight off the lane input.
        lane_out = _spec_quantities(lane_out, spec, entities)
        lane_ctx = {**lane_ctx, "parse": {**(lane_ctx.get("parse") or {}), "output": lane_out}}
        # R2: start from the resolver's own gate (gate_reason, require_specific,
        # customer_probe_entities, company_team, gate_debug, ...) - `compatible_entities`
        # and `predicate` are still set exactly as today, below, overriding whatever
        # `resolver_gate` itself carried under those two keys.
        gate: dict[str, Any] = dict(resolver_gate) if isinstance(resolver_gate, dict) else {}
        gate["compatible_entities"] = entities
        block = page_predicate if page_predicate is not None else predicate
        if block is not None:
            gate["predicate"] = block
        # R3: a tier already settled by a pick keeps today's synthetic recompose; an
        # UNSETTLED tier hands the resolver's own real tier_gate through instead, so the
        # per-tier promotion probe (`lanes.business.run_fetch`'s own tier_ask arm) sees
        # what the contact actually holds rather than nothing at all.
        tier_gate_value = (
            _tier_gate(spec, verdict, focus, resolver_tier_gate)
            if spec.filters.get("tier")
            else resolver_tier_gate
        )
        payload = {"gate": gate, "tier_gate": tier_gate_value, "ctx": lane_ctx}
        # Security B1, FAIL CLOSED: a tier-filtered fetch whose recomposed access
        # levels came out EMPTY must never reach the tool. Downstream an empty list
        # is not "nothing matches", it is "no tier filter":
        # `lanes/business/fetch.py` copies it into the tool args,
        # `api/v1/marketing/promotions.py` hands it to
        # `contact_access_type_service.translate_names_to_codes`, which returns None
        # for an empty name list, and the service reads None as "no access-level
        # filter" - so the contact reads promotions of every tier. It is empty only
        # when the contact holds no entitlement the recompose could keep, which is a
        # genuine absence: answered with the SAME `not_found` fragment the
        # unfiltered-answer guard below hands to production's own miss composer, so
        # the words are production's and no tool call goes out.
        #
        # Security B2, the same rule one seam over: a carried set whose page 1
        # entitlement was never recorded cannot be re-counted honestly, and a page with
        # no ids leaves the fetch with NO entities at all - the most unfiltered read
        # there is. `page_the_set` refuses it; this is where that refusal becomes the
        # same production miss.
        # Hand pass 12 round 3, R6 (owner ruling): a stock/inventory tool must never
        # be called with zero filters when the message named an entity and NONE of
        # them placed - a genuinely unresolved product code (turn 328e8b00,
        # "Srtks8060-BL stock") reached the tool with `entities_in: 1,
        # total_uuids_passed: 0` and answered about the whole catalogue. The SAME
        # facts `_answered_unfiltered` already reads to REWRITE the reply after the
        # tool ran (`unplaced`/`entities`) are read HERE, before it runs, so the call
        # never goes out at all - scoped to inventory/incoming only (never `order`,
        # whose outstanding-report ask filters by CODE, not id, and is narrowed by
        # exactly an unplaced token, `_answered_unfiltered`'s own carve-out).
        #
        # Hand pass 12 round 4, R8 (owner ruling, turn 7c39e638 "close couple wc
        # available stock in p trap"): NO entity at all is the same unfiltered read
        # when the message NAMED tokens and the resolver placed none of them - the
        # two `category`-hinted phrases resolved to nothing placeable, the narrower
        # had no candidate to hand the fetch, and `crm_inventory_stock_balance_list`
        # ran with zero filters over 97 products ("+96 more"). `unplaced` IS the
        # "this message named something the resolver could not place" verdict, so a
        # genuinely entity-less ask ("what's on promotion") names no token, leaves
        # `unplaced` empty and still calls its tool - which is the distinction the
        # old `and bool(entities)` was standing in for, and got wrong for the case
        # where nothing survived to be counted at all.
        would_be_unfiltered = (
            domain in ("inventory", "incoming")
            and bool(unplaced)
            and all(_entity_is_unplaced(e, unplaced) for e in entities)
        )
        # Hotfix 22 Sep 2026 (PLAN-chatbot-stock-no-subject-hotfix-22sep.md, live
        # contact 423729104 turns 59-60): the guard above needs `bool(unplaced)`, and
        # the whole-book read that got through carried NOTHING unplaced. Turn 59's
        # "Srtwc8608-p-rl" resolved only as a `product_set` - a kind
        # `ALLOWED["inventory"]` does not take - so the carry was parked on
        # `focus.extra["product_set"]`, handed back to the resolver on turn 60
        # ("Stock"), left `unplaced` empty either way, and `compatible_entities` came
        # out empty: `crm_inventory_stock_balance_list` ran with zero filters and
        # answered with 50 rows of the catalogue. A bare "stock?" on turn 1 is the
        # same hole from the other side - no entities at all, so the resolver never
        # even runs and `unplaced` is empty for that reason instead.
        #
        # `run_gate` is ASKED the question rather than given a second copy of its
        # tables: an entity-less ask in this domain is exactly what `ALLOWS_EMPTY` /
        # `INTENTS_ALLOWING_EMPTY` already rule on (`inventory` is False on purpose -
        # "a bare 'stock?' must ask which product" - and `low_stock_report` is the one
        # intent exempted from it, PLAN-low-stock-report S6), and its verdict carries
        # both the reason string and the `allowed_lookup` production's own miss
        # composer reads to build the scope-needed sentence. Scoped to `inventory`:
        # the trigger to widen is a SECOND domain measured dumping unfiltered, not the
        # fact that other `ALLOWS_EMPTY` rows are False too.
        #
        # A predicate block IS a filter (the described-set ask, "which taps have
        # stock"), so a turn carrying one is never refused here.
        #
        # Reviewer S1: `would_be_unfiltered` is EXCLUDED, not merely redundant with
        # this. Every entity it refuses is unplaced and therefore uuid-less, so
        # without the exclusion this condition also fires on the R6/R8 refusals and
        # stamps `scope_gate` on them - which re-points their miss text at a gate
        # whose `compatible_entities` is empty and loses the breakdown bullets
        # (`answer.py`'s own per-entity lines), for a turn that is not a scope gap at
        # all: the customer DID name a subject, it just did not resolve.
        # `not_found_error_message` says the same thing in its own `needs_scope`
        # condition (`and not has_unresolved`). Those two refusals keep the
        # resolver's gate and their existing "could not find X" wording untouched;
        # `scope_gate` rides ONLY the hole this hotfix opened the guard for.
        no_subject_gate: dict[str, Any] | None = None
        if (
            domain == "inventory"
            and block is None
            and not would_be_unfiltered
            and not any(isinstance(e, dict) and e.get("uuid") for e in entities)
        ):
            probe_gate = gate_mod.run_gate(
                {},
                parser={**lane_out, "domain_hint": domain, "entities": []},
                resolver={"resolutions": []},
            )
            if probe_gate.get("gate_passed") is False:
                no_subject_gate = probe_gate
        if (
            (
                spec.filters.get("tier")
                and isinstance(tier_gate_value, dict)
                and not tier_gate_value.get("access_levels_recomposed")
            )
            or (page_predicate is not None and page_predicate.get("entitlement_missing"))
            or would_be_unfiltered
            or no_subject_gate is not None
        ):
            fragment: dict[str, Any] = {
                "fetch": {"has_result": False, "response": business_fetch.NO_RESULT_INTRO},
                "outcome": "not_found",
            }
            if no_subject_gate is not None:
                # The refusal's OWN reason, for `answer_bridge.answer_for`'s miss
                # composer - which otherwise reads the RESOLVER's gate, and the
                # resolver here either never ran (nothing to resolve) or placed the
                # carry perfectly well and has no opinion about scope at all. The
                # words stay `answer.not_found_error_message`'s own `needs_scope`
                # branch; this carries only the gate verdict that branch keys on.
                fragment["scope_gate"] = no_subject_gate
        else:
            fragment = business.run_fetch(
                payload,
                services=business_services.fetch_services(db),
                dry_run=dry_run,
                space_id=space_id,
                trace=turn_trace,
                db=db,
            )
        # Hand pass 12 round 2, Group C (owner ruling): a combined call (a REFINE
        # turn's own carried filter PLUS this message's own record key,
        # `decide.py:427-478`'s table, unchanged) that MISSED reruns exactly ONCE,
        # on the record key alone - through the SAME `business.run_fetch` call the
        # first try used, never a second path around the access/narrowing/scope
        # gate. `page_predicate is None` keeps a `set_page` continuation (its own,
        # unrelated, id-only entities) out of this.
        if page_predicate is None and not (fragment.get("fetch") or {}).get("has_result"):
            rerun_split = _record_key_rerun_split(domain, verdict, entities, resolved_kinds)
            # P3 (hand pass 12 Phase 3, reviewer S1): the `would_be_unfiltered` guard
            # above is computed once, before the FIRST `run_fetch`, and this rerun
            # never re-consults it - `_record_key_rerun_split`'s own `keep` can carry
            # a record-key entity that never resolved to a uuid at all (a bogus token
            # naming NOTHING real), and the rerun used to fire anyway, a second
            # tool call with zero uuids on it. Nothing to rerun on when no KEPT row
            # carries one.
            if rerun_split is not None and any(
                isinstance(e, dict) and e.get("uuid") for e in rerun_split[0]
            ):
                keep_entities, dropped_entities, record_words = rerun_split
                rerun_gate = dict(gate)
                rerun_gate["compatible_entities"] = keep_entities
                rerun_fragment = business.run_fetch(
                    {"gate": rerun_gate, "tier_gate": tier_gate_value, "ctx": lane_ctx},
                    services=business_services.fetch_services(db),
                    dry_run=dry_run,
                    space_id=space_id,
                    trace=turn_trace,
                    db=db,
                )
                if (rerun_fragment.get("fetch") or {}).get("has_result"):
                    dropped_words = [w for w in (_entity_display(e) for e in dropped_entities) if w]
                    if dropped_words and record_words:
                        note = (
                            f"{', '.join(dropped_words)} does not match "
                            f"{', '.join(record_words)} - dropped, showing "
                            f"{', '.join(record_words)} on its own:"
                        )
                        rerun_fetch = dict(rerun_fragment.get("fetch") or {})
                        original_text = jsc.js_string(rerun_fetch.get("response") or "").strip()
                        rerun_fetch["response"] = (
                            f"{note}\n\n{original_text}" if original_text else note
                        )
                        rerun_fragment = {**rerun_fragment, "fetch": rerun_fetch}
                    _drop_focus_entities(focus, dropped_entities)
                    fragment = rerun_fragment
                    entities = keep_entities
        if _answered_unfiltered(fragment, entities, unplaced):
            # Every subject this fetch had is a token the resolver could not place, so
            # there was nothing to filter by - and a tool called with no filter answers
            # about everything. "stock for srttwc286" reached
            # `crm_inventory_stock_balance_list` with every entity skipped
            # `for_bad_uuid` and replied "5,783 products have stock. Showing 5." (turns
            # 11476016 / 5cf452cd / 9de8ac20, 16 Sep 2026). A miss is the honest answer:
            # the composer names the token and offers the escalation exactly as it does
            # for a code that exists and has nothing to show.
            #
            # Read off the fragment rather than short-circuited before the lane, because
            # the lane answers in more ways than by calling a tool - the gate's own
            # customer and incoming pickers come back from here with no tool at all, and
            # refusing to call it would have swallowed the picker too.
            #
            # PLAN-chatbot-answer-half-reattach.md R4 (Deleted table): this used to try a
            # rearch-only trigram roster of its own (`_alternatives_ask`,
            # `_resolve_dominant_neighbours`) before falling back to a flat miss. That
            # machinery is retired - `outcome: "not_found"` is all this fragment states,
            # so a single-domain business turn's `answer_bridge.answer_for` (via its own
            # `raw_fragment` trigger) can answer it with PRODUCTION's own did-you-mean
            # roster (`miss_suggest.dym_transform` / `dym_annotate`, off the resolver's
            # OWN trigram alternatives on `resolved`), never a second, parallel one.
            fragment = {
                "fetch": {"has_result": False, "response": business_fetch.NO_RESULT_INTRO},
                "outcome": "not_found",
            }
        return envelope_of(
            fragment,
            spec,
            entities,
            # The render follows the TIER that matched (AC-1534): a SPEC-tier answer is
            # the counted set, a code-tier answer is the list, and a carried page is a
            # set by construction.
            counted_set=page_predicate is not None or counted_set,
            denial_text=(
                domain_denial_text(db, domain)
                if fragment.get("outcome") == "access_denied"
                else None
            ),
            ran_with=lane_out,
            unplaced=unplaced,
            raw_fragment=fragment,
        )

    return runner


#: The entity hints that name a CLASS of product rather than one of them. They are what
#: the resolve body forwards as `scope_terms` (`resolve_gate.resolve_entity_body`), which
#: is what a described set is scoped BY (AC-1534).
CLASS_HINTS = ("product_type", "category")

#: The resolver's own name for its last tier: the SPEC/class search it falls back to when
#: the code tiers matched nothing (`api/v1/system/references._emit_spec_matches`). Every
#: other tier - exact, prefix, substring, and, scope - matched a CODE.
SPEC_TIER = "spec_search"


def class_scope_terms(verdict: dict[str, Any]) -> list[str]:
    """The class words the PARSER named this turn, in order, deduped.

    What the described set is scoped BY, read off the verdict's entity hints and never
    off the message words (D1/AC-1520).
    """
    terms: list[str] = []
    for entity in verdict.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if jsc.nullish_str(entity.get("hint")).strip().lower() not in CLASS_HINTS:
            continue
        raw = jsc.nullish_str(entity.get("raw")).strip()
        if raw and raw not in terms:
            terms.append(raw)
    return terms


def spec_tier_matched(resolved: Any) -> bool:
    """Did this turn's products come from the SPEC tier rather than from a code?

    ONE product lane, one ladder: the resolver tries the code tiers and falls back to the
    spec/class search only when they matched nothing, so "SRTWC286 got stock" and "which
    water closet got stock" walk the same path and only the second reaches the fallback.
    The counted-set answer ("N water closets have stock. Showing 5." plus the page
    cursor) is simply how a SPEC-tier match RENDERS; a code-tier match renders as the
    list. The render had been following the `require` predicate instead, which
    `predicate.derive_require` builds from the INTENT alone (`check_stock` ->
    `{"stock": true}`) - so it rides every stock, incoming and promotion turn there is,
    and "7445" (matched by code, five real variants) was answered "5 taps have stock."
    with a page describing every product that has stock (turns 92d565a5 / b383d402 /
    2e7ca929, 17 Sep 2026).

    "All of them, and at least one" is the same reading the GATE already earned for the
    same tier (`gate.run_gate`'s C4 branch, AC-1326) and `_strip_word_token_product_
    matches` (AC-1327): a group whose product matches are not ALL `spec_search` is an
    ordinary code answer. Non-product matches are not part of the question.
    """
    products: list[Any] = []
    rows = jsc.get(resolved, "intersection")
    if isinstance(rows, list):
        products = [m for m in rows if isinstance(m, dict) and m.get("entity_type") == "product"]
    else:
        for resolution in jsc.array(jsc.get(resolved, "resolutions")):
            for match in jsc.array(jsc.get(resolution, "matches")):
                if isinstance(match, dict) and match.get("entity_type") == "product":
                    products.append(match)
    return bool(products) and all(m.get("match_tier") == SPEC_TIER for m in products)


SET_PAGE_SIZE = 5


def _entitled_names(values: Any) -> list[str]:
    """The access-level NAMES in `values`, trimmed, non-empty, in order."""
    return [v for v in jsc.array(values) if isinstance(v, str) and v.strip()]


def set_page_carry(
    predicate: dict[str, Any] | None,
    spec: FetchSpec,
    scope_terms: list[str],
    *,
    access_levels: Any = None,
) -> dict[str, Any] | None:
    """Where a counted-set answer got to, for `focus.set_page` (AC-1317).

    `{set_key, offset}` and nothing more: the set is RE-DESCRIBED next turn from
    `set_key` rather than carried as a list of ids, so a session never holds two hundred
    uuids and a "more" three turns later still answers over live data.

    Called only for a SPEC-tier answer (`spec_tier_matched`), and never without a scope
    term: `set_key` describes the population by its `require` leg and its class words, so
    an empty `scope_terms` describes "every product that has stock" and the next "more"
    pages the whole catalogue. A spec tier reached with nothing to scope by is a miss, not
    a set.

    **Security B2 (re-check round, 20 Sep 2026): `access_levels` is part of the
    description, not beside it.** The same `require` leg and the same class words read
    under two entitlements are two different populations, so the levels page 1 actually
    answered under (`lanes/business._fetch_semantic_input`'s own, off
    `tier_gate.access_levels_recomposed`, carried out as the envelope's
    `access_levels_used`) belong INSIDE `set_key` - main records the same fact as
    `access_levels` on its own flat carry (`lanes/business/resolve_gate._set_page_reply`
    reads it back as the next page's `tier_gate`). Without it the "more" turn had nothing
    to recount by and fell to the PARSER's `access_levels`, which is empty in 249 of 249
    real captures: `product_predicate_service._access_level_codes` reads an empty name
    list as "no tier filter", so page 2 of a promotion set counted and named products
    whose only promotion is restricted to a tier the contact does not hold. The key is
    ALWAYS written, empty list included - a carry with no levels recorded is refused by
    `page_the_set` rather than read as "no restriction".
    """
    if not predicate or not scope_terms:
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
            "access_levels": _entitled_names(access_levels),
        },
        "offset": min(SET_PAGE_SIZE, total),
    }


def page_the_set(db: Session, carry: dict[str, Any], *, access_levels: Any = None):
    """The next page of a carried set: `(predicate, product_ids)`.

    The set is re-counted from its own description, which is what makes the carry two
    small values instead of a list - and what makes a page honest when the catalogue
    moved between the two turns.

    **Security B2: the entitlement is part of that description.** The recount runs under
    the levels the CARRY recorded (`set_key.access_levels`, written by `set_page_carry`
    from the levels page 1's own fetch used), never under anything this turn's parser
    happened to state - a "more" states nothing, and an empty name list reaches
    `product_predicate_service._access_level_codes` as "no tier filter at all", which is
    how page 2 of a promotion set widened past page 1. A carry that records NO levels is
    refused (`qualifying_total: 0`, no ids, `entitlement_missing`), so the runner answers
    the miss instead of reading the set unfiltered.

    `access_levels` is for a caller that already knows the entitlement and holds a carry
    written before it was recorded: the first page under it STAMPS the carry, so every
    later page of that same carry recounts under the same authority. Production's own
    "more" (`make_tool_runner.runner`) passes nothing at all.
    """
    from app.services.chatbot.lanes.business.answer import SET_PAGE_ID_CAP
    from app.services.product_predicate_service import resolve_product_set

    key = carry.get("set_key") or {}
    offset = int(carry.get("offset") or 0)
    entitled = _entitled_names(key.get("access_levels"))
    if not entitled:
        stamped = _entitled_names(access_levels)
        if stamped:
            key["access_levels"] = list(stamped)
            entitled = stamped
    if not entitled:
        return {
            "require": key.get("require") or {},
            "qualifying_total": 0,
            "truncated": False,
            "unrecognized_terms": [],
            "class_labels": [],
            "entitlement_missing": True,
            "page": {
                "start": offset + 1,
                "end": offset,
                "new_offset": offset,
                "set_noun": key.get("set_noun") or "products",
            },
        }, []
    outcome = resolve_product_set(
        db,
        require=key.get("require") or {},
        specs=[],
        free_terms=None,
        scope_terms=list(key.get("scope_terms") or []),
        limit=SET_PAGE_ID_CAP,
        product_ids=None,
        brand=None,
        access_levels=entitled,
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


def _tier_gate(
    spec: FetchSpec,
    verdict: dict[str, Any],
    focus: Focus,
    resolver_tier_gate: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The tier the narrower already settled, in the shape the kept fetch reads.

    `access_levels_recomposed` is what `lanes/business._fetch_semantic_input` sends to
    the tool as `access_levels`, and that parameter takes access-level NAMES: the route
    (`api/v1/marketing/promotions.py`) translates them through
    `contact_access_types.name` before it overlaps them with the promotion's own JSONB
    of CODES, and an unrecognised name translates to an empty code list, which the
    service reads as "filter by these and there are none" (`marketing_service`'s own
    `q.filter(text("false"))`). Sending the bare tier `"dealer"` therefore answered
    every promotion question with "No matching results found." while 50 dealer
    promotions sat on the clone (browser pass 6, turn 0bd47e62).

    The tier x brand recomposition is the KEPT lane's own rule and it is called, never
    copied (`lanes/business/tier_gate.recompose`): the tier the customer picked plus the
    brands this conversation is about, intersected with the entitlement NAMES the
    envelope carries, is the set of compound levels the CRM understands
    ("dealer" + `["Sorento Dealer", "Mocha Dealer"]` -> both). A tier the contact does
    not hold falls back to their real entitlement, which is the kept lane's own Q23
    reading - answer at what they may see rather than at nothing.

    **Security B1 (review round, 20 Sep 2026): the entitlement comes from the RESOLVER,
    never from the parser's words.** `verdict["access_levels"]` is what the MESSAGE
    stated (`head/parser.py`), and it is empty in 249 of 249 real captures
    (`documentation/plans/chatbot/parser-prompt-inventory.md:106`) - so recomposing
    against it on the turn that ANSWERS a tier pick produced an empty
    `access_levels_recomposed`, which `api/v1/marketing/promotions.py` ->
    `contact_access_type_service.translate_names_to_codes` reads as "no access-level
    filter at all", answering with promotions of every tier. `resolver_tier_gate` is
    `resolve_gate.run`'s own `access_check` output: `name` is the contact's REAL
    entitled compound names and `entitled_tiers` the tiers those map to
    (`lanes/business/tier_gate.py`). A chosen tier outside `entitled_tiers` is dropped
    before the recompose, so a pick off a stale or blind menu cannot widen the read.

    **Security S4 (re-check round, 20 Sep 2026): no resolver tier gate means NO
    entitlement, never the parser's claim.** The verdict used to be the fallback here for
    "a caller with no resolver answer at all", and that left the one exposure B1 was
    about: a message that STATES a tier became the authority whenever
    `resolver_tier_gate` is not a dict, which three production shapes reach - the
    resolver raising (`turn_runtime.py:776-778` logs it and returns `payload=None`), a
    plan naming both `ideate` and `promotion` (the `ideate` entry builds no tier gate,
    `lanes/business/__init__.py:45-49`), and `resolve_gate.run`'s own `set_page` early
    return (`resolve_gate.py:990`, ahead of the `access_check` block). All three now
    recompose to `[]`, and the runner's fail-closed guard above answers the miss.
    """
    tier = spec.filters.get("tier")
    if not tier:
        return None
    from app.services.chatbot.lanes.business.tier_gate import recompose

    resolver_gate = resolver_tier_gate if isinstance(resolver_tier_gate, dict) else None
    entitled = (
        _entitled_names(resolver_gate.get("name")) if resolver_gate is not None else []
    )
    # AC-1698 ("1 and 2", "all"): `narrow_by_tier`'s own settle carries every chosen
    # tier, a list once more than one was picked (a single pick stays the scalar
    # `filter_value` always was) - `recompose` already takes several (`jsc.array`),
    # so every chosen tier reaches ONE fetch's own `access_levels`, never just the last.
    tiers = [t for t in (tier if isinstance(tier, list) else [tier])]
    if resolver_gate is not None:
        held = {
            jsc.js_string(t).strip().lower()
            for t in jsc.array(resolver_gate.get("entitled_tiers"))
        }
        tiers = [t for t in tiers if jsc.js_string(t).strip().lower() in held]
    recomposed = recompose(tiers, list(focus.brands or []), entitled)["access_levels"]
    if not recomposed:
        recomposed = sorted(entitled, key=jsc.js_string)
    return {
        "tier_pick": tier,
        "tier_pick_domain": spec.domain,
        "access_levels_recomposed": recomposed,
    }


def with_carried_entities(
    parse_output: dict[str, Any], focus: Focus, *, unsettled_only: bool = False
) -> dict[str, Any]:
    """What the RESOLVER is asked about on a turn that named nothing (contract 33, 35).

    "incoming", typed after an inventory answer about ten SRTWC286 variants, names no
    product at all - so the resolver was never asked, the narrower had only the carried
    rows to go on, and the fetch reached the tool with a token no `*_ids` param could be
    built from. The conversation's own subject is handed over instead: the same entity
    shape the parser emits, flagged `current_message: false` so every downstream reader
    that distinguishes "typed this turn" from "carried" (the low stock prune, the
    outstanding report's typed-code match) still can.

    A turn that names its own entities is untouched - this is the EMPTY case only.

    `unsettled_only` is the FETCH turn's version of the same question, and the narrower
    reading of it. A carry that already holds a `uuid` is settled: it is in the plan
    already, and re-resolving it is how a stale subject gets back into an answer. A
    carry that holds only a TOKEN is in the plan as a word no `*_ids` param can be built
    from, so the fetch either drops it (promotion, browser pass 6 turn 0bd47e62: "Promo
    for srtwc286" then "1" fetched every dealer promotion, scoped to no product at all)
    or sends the token where a uuid belongs. Those rows, and only those, are handed over
    on a turn that fetches.
    """
    if parse_output.get("entities"):
        return parse_output
    carried: list[dict[str, Any]] = []
    # Every kind the focus holds, `extra` included. `KIND_FIELD_MAP` names four kinds
    # and the rest of them live in the catch-all, so an `attachment_type` carried from
    # "photos for srtwc286" was never handed to the resolver, never became an
    # `attachment_type_ids` argument, and the answer to the product pick that followed
    # listed Certification PDFs under a header that said "photo" (turns d77231ed /
    # 2b9aaa96, 16 Sep 2026).
    by_kind: list[tuple[str, list[Any]]] = [
        (kind, getattr(focus, attr, []) or []) for kind, attr in KIND_FIELD_MAP.items()
    ]
    by_kind += [
        (kind, rows or [])
        for kind, rows in (getattr(focus, "extra", {}) or {}).items()
        if isinstance(rows, list)
    ]
    for kind, rows in by_kind:
        for row in rows:
            if not isinstance(row, dict):
                continue
            if unsettled_only and row.get("uuid"):
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


def _is_certificate_type(db: Session, attachment_type_id: Any) -> bool:
    """`attachment_types.is_certificate` for the RESOLVED row, never the customer's
    own words. `False` for anything unresolved/unreadable - fail closed to the
    default (`marketing_product`) team rather than mis-route on a lookup that could
    not run (a bad uuid, a row deleted since the resolver matched it).

    Run in a SAVEPOINT (`company_scope.stamp_lookup_companies`'s own convention): a
    non-uuid id (a test double's own placeholder, a resolver row this turn's own
    kind is not really a product/attachment_type at all) aborts the STATEMENT on
    Postgres, and a bare try/except around the query alone leaves the WHOLE caller
    transaction poisoned for every later query this same turn makes - measured
    directly writing this function (`test_rearch_r11_catalogue.py`'s own fixture
    uuid is not RFC 4122 shaped) as a cascade of unrelated `InFailedSqlTransaction`
    errors from every db read after this one.
    """
    if not jsc.truthy(attachment_type_id):
        return False
    from app.models.resources import AttachmentType

    try:
        with db.begin_nested():
            row = db.query(AttachmentType).filter(AttachmentType.id == attachment_type_id).first()
    except Exception:  # noqa: BLE001 - a lookup failure is not a reason to mis-route
        logger.warning("chatbot: attachment_type certificate lookup failed", exc_info=True)
        return False
    return bool(row is not None and row.is_certificate)


def answer_parse_output(
    parse_output: dict[str, Any] | None,
    *,
    gate: Any,
    domains: Any = (),
    db: Session | None = None,
) -> dict[str, Any]:
    """What the ANSWER composers read, which is what the RESOLVER read (AC-1701/AC-1702).

    `lanes/business/__init__.py::complete_answer` takes its `parser` off
    `ctx["parse"]["output"]`, and on the pre-rearch head that object had ALREADY been
    post-processed: `head/output_exchange._post_process` restored the open question's
    own domain onto a bare positional pick, and its section (B) ("product_attachment:
    re-attach attachment_type if the current turn lacks one") put the conversation's
    settled document type back on a turn that named none - carrying the RESOLVED type
    name, not the customer's word for it. A recorded turn's own pending payload still
    shows that shape verbatim (`{"raw": "Product Photos", "canonical_code": "Product
    Photos", "uuid": ...}`, `tests/chatbot/replay_turns/console/focus-015-r-c-photo-for-
    srtwc286-product-pick-keeps-the-attachment-type-no-re-ask.json`), and #750's own
    decision 3 is the same rule for the stamp surface: the noun the customer reads is
    the resolved attachment type, never "photo" / "gambar".

    The re-architecture kept the carry on a SEPARATE `resolver_ctx` and handed the
    composers the bare verdict instead, so `answer.not_found_error_message` saw
    `domain_hint = None` and no attachment_type entity at all. Two live misses came out
    of that one gap: "But no null matched these" after a roster pick (turn
    0f732289-fe38-4a3e-bbd5-d472f32fa524, `jsc.js_string(None)`) and "But no photo
    matched these" when the type WAS named this turn (turn
    bf87f9ef-2ebb-49e8-8b29-bc9edd355eb1), both against a breakdown bullet that already
    printed "attachment_type: Product Photos" two lines above.

    Two narrowings, both safety rather than tidiness. The domain is restored only when
    the turn restated none AND the plan names exactly one - a two-domain plan has no
    single answer, and `turn/compose.py` composes those. A type name is taken only when
    the gate settled exactly one `attachment_type` row: several is still a family, the
    same rule `tail/compile_state.reconcile_entities` applies to a multi-match token.
    """
    out = dict(parse_output) if isinstance(parse_output, dict) else {}
    g = gate if isinstance(gate, dict) else {}
    type_rows = [
        row
        for row in jsc.array(g.get("compatible_entities"))
        if isinstance(row, dict)
        and jsc.nullish_str(row.get("entity_type")).strip().lower() == "attachment_type"
        and jsc.truthy(row.get("code"))
    ]
    type_names = [jsc.js_string(row.get("code")).strip() for row in type_rows]
    if len(type_names) == 1:
        entities: list[Any] = []
        for entity in jsc.array(out.get("entities")):
            if (
                isinstance(entity, dict)
                and jsc.nullish_str(entity.get("hint")).strip().lower() == "attachment_type"
            ):
                entities.append({**entity, "raw": type_names[0], "canonical_code": type_names[0]})
            else:
                entities.append(entity)
        out["entities"] = entities
        # Hand pass 11, defect 2 (owner ruling): a RESOLVED attachment_type row
        # (never a regex over the customer's text, D11) whose own
        # `attachment_types.is_certificate` is true routes this turn's escalation to
        # `purchasing_certification` / `general_enquiries`, deterministically and
        # post-LLM - main's deleted `head/output_exchange.py:85-120` made the same
        # domain+is_cert call, and the v39 prompt line names the SAME team the
        # rendered domain block (`chatbot_domains.escalation_team_code`) then
        # contradicts. Applied HERE, the first and only place this function settles
        # which attachment_type the turn is actually about, so the corrected team
        # reaches the miss offer sentence, the pending roster's own `team` stamp
        # (carried across a did-you-mean pick, contract 108), and the escalation
        # lane on "yes" - all three read `out["routing"]`, never a second copy.
        if db is not None and _is_certificate_type(db, type_rows[0].get("uuid")):
            out["routing"] = {
                **(out.get("routing") or {}),
                "suggested_team": "purchasing_certification",
                "suggested_agent": "general_enquiries",
            }
    if not jsc.truthy(out.get("domain_hint")):
        named = [d for d in (domains or []) if d]
        if len(named) == 1:
            out["domain_hint"] = named[0]
    # Hand pass 9, D4: a bare positional pick ("1") parses as `message_type: "casual"` -
    # correctly, that IS what the words are - but this function's own two callers
    # (`answer_bridge.question_for`/`answer_for`) only ever run on a turn ALREADY routed
    # to the business_query/check_promotion branch (`_run_stages`'s own gate on
    # `branch_kind`), so by the time either reads this output the turn IS a business
    # answer, whatever the parser called the customer's one-word reply. Left uncoerced,
    # `answer.crossdomain_zeroset`'s own `message_type != "business_query"` gate read
    # the pick's literal "casual" and switched the whole cross-domain ladder off - an
    # after-a-pick incoming miss never climbed to stock at all (live turn
    # 139f5282-4968-4802-bd11-501de55bca50), where the identical FRESH-ask shape
    # climbs correctly because the customer's own words there really did carry
    # "business_query".
    out["message_type"] = "business_query"
    return out


def _code_of(entity: dict[str, Any]) -> str:
    """The CODE a row carries, whichever of the three names it spells it under.

    `gate.py` renames the resolver's `canonical_code` to `code` when it builds
    `compatible_entities`; the parser, the focus and a picked option all say
    `canonical_code`; a bare parser entity has only its `raw` token. Reading one
    spelling and not the others is what made the match below fall through for EVERY
    spec that named an entity (every compatible row answered `"null"`).
    """
    return jsc.js_string(entity.get("code") or entity.get("canonical_code") or entity.get("raw")).strip().lower()


def _answered_unfiltered(
    fragment: dict[str, Any], entities: list[dict[str, Any]], unplaced: dict[str, str]
) -> bool:
    """Did a TOOL answer this fetch when every subject it had was an unplaced token?

    "Unfiltered" means the tool had nothing to narrow BY. A tool that takes entity ids
    gets none from a token the resolver could not place - every row is skipped
    `missing_or_bad_uuid` - and answers about the whole catalogue. The outstanding report
    is the exception and is named as one: it filters on the product CODE the customer
    typed rather than on an id, states that code in its own scope header, and is
    therefore narrowed by exactly the token in question (`case-071`, `case-058`, whose
    recorded tool args carry `product_code` for a token their own resolver stub reports
    as unresolved).

    An EMPTY entity list is the MOST unfiltered a fetch can be (R1, security review
    N-1): the subject never resolved at all, so there was nothing to narrow BY, whatever
    `unplaced` still names. `entities and not all(...)` is what actually gates the
    non-empty case below - an empty `entities` is falsy and skips that check rather than
    returning False for it, so this one guard clause covers both shapes.
    """
    if not unplaced:
        return False
    if entities and not all(_entity_is_unplaced(e, unplaced) for e in entities):
        return False
    fetched = fragment.get("fetch") if isinstance(fragment.get("fetch"), dict) else {}
    if fetched.get("outstanding_report"):
        return False
    tool = fetched.get("tool") if isinstance(fetched.get("tool"), dict) else {}
    return bool(tool.get("name"))


def _spec_row(entity: dict[str, Any]) -> dict[str, Any]:
    """A plan entity in the shape the gate's own rows use.

    `code` is the name every code reader downstream (`fetch.outstanding_product_codes`,
    the low-stock prune, the report's typed-code match) reads first: a spec entity that
    reaches the tool without it is a product with no code at all.

    AC-1692's own rule, one layer up: `raw` stands in for a missing `code` ONLY when
    something else already confirms this row settled to a real record (a `uuid`) - a
    fully unplaced guess (no `canonical_code`, no `uuid`, `raw` alone) is not a code
    just because nothing else was typed. Measured live: a refinement's own unresolved
    product word ("cheaper") reached this fallback with neither, and every downstream
    code reader then sent it to the tool verbatim as `product_code=cheaper`.
    """
    uuid = entity.get("uuid") or entity.get("canonical_code")
    settled_raw = entity.get("raw") if uuid else None
    return {
        "entity_type": entity.get("hint"),
        "uuid": uuid,
        "code": entity.get("canonical_code") or settled_raw,
        "canonical_code": entity.get("canonical_code") or settled_raw,
        "raw": entity.get("raw"),
        **({"display_name": entity["name"]} if entity.get("name") else {}),
    }


def _entities_for(spec: FetchSpec, compatible: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The resolver's own rows for the kinds it answered for this turn, plus the plan's
    own rows for every kind it did not.

    A kind this spec NARROWED to keeps only what the narrower chose. Every OTHER kind the
    resolver matched passes through untouched: the order domain narrows on customer as
    well as product, and filtering the whole list down to one kind dropped the product and
    the location out of "SRTWT7445 outstanding for Dealer A in IB" - the report then
    printed `Product: all` over a question about one product.

    The second half is the CARRY, and it is what made "i want to see hanlim only customer"
    answer for every product HANLIM ever bought (turn 834ac587, 16 Sep 2026). The
    conversation was about three SRTWC286 variants, the message named a customer, and
    `_focus_rules` kept both halves on the focus exactly as it should - but the resolver
    is only ever asked about the tokens THIS message named, so `compatible` held the six
    HANLIM ledgers and no product at all, and a filter that keeps only resolver rows kept
    only the customer. A kind the resolver did not answer for this turn is a kind whose
    subject was settled on an earlier one, so the plan's own rows are the only evidence
    there is about it, and they are the same rows this function has always fallen back to
    when the resolver answered nothing at all.

    Both halves are KIND-SCOPED to the domain, by the kept lane's own matrix
    (`gate.ALLOWED`, never a second copy). The gate already scopes what it hands back,
    but it scopes by the ONE `domain_hint` the verdict carries, and a bare positional
    ("1") carries none - so on those turns every kind the resolver matched passed through
    to every domain the plan fetched. Measured on the owner's 17 Sep turns: a
    `resource_attachment` ask three minutes earlier left two container-status
    spreadsheets on `focus.extra["attachment"]`, and the "1" that answered a product
    roster fetched incoming AND stock under the header "*incoming stock* for 14.09.2026
    Container Status 2026.xlsx, 11.09.2026 Container Status 2026 MOCHA.xlsx, cb2805q"
    (turns 725e39fd / 543b9a02). The plan knows the domain per fetch, which is what the
    gate could not - so the same matrix is applied here, per spec.
    """
    from app.services.chatbot.lanes.business.gate import ALLOWED

    allowed = ALLOWED.get(spec.domain)
    if allowed is not None:
        compatible = [e for e in compatible if e.get("entity_type") in allowed]
    kinds = {e.get("hint") for e in spec.entities if e.get("hint")}
    codes = {_code_of(e) for e in spec.entities}
    picked = [
        e
        for e in compatible
        if e.get("entity_type") not in kinds
        or not codes
        or _code_of(e) in codes
    ]
    answered = {e.get("entity_type") for e in picked}
    return picked + [e for e in map(_spec_row, spec.entities) if e["entity_type"] not in answered]


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
    ran_with: dict[str, Any] | None = None,
    unplaced: dict[str, str] | None = None,
    counted_set: bool = True,
    raw_fragment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The kept lane's fetch fragment as the composer's envelope (AC-1530, AC-1531).

    `ran_with` is the lane input this fetch actually went out with, read for one fact:
    the date window. Whatever put it there - the verdict's own dates, the focus window
    `_spec_window` defaults in, the outstanding answer's carried filters - the answer
    has to say which dates it searched (browser pass 6 item 4, turn 60927579: "This
    month only" reached the tool as 2026-09-01 to 2026-09-30 and the reply header said
    nothing about it, so a customer reading "No matching results found." could not tell
    an empty month from an empty product).
    """
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
    envelope: dict[str, Any] = {
        "domain": spec.domain,
        "denied": refused,
        "entities": codes,
        "figures": figures,
        "files": [f for f in files if isinstance(f, dict)] if isinstance(files, list) else [],
        "miss": [] if has_result else codes,
        "has_result": has_result,
        # The tokens THIS MESSAGE named that the resolver could not place. The composer
        # says so beside the answer, so a message naming three codes of which one is a
        # typo does not quietly answer for two (hand pass 2 item 6, turn 7cf56afe "stock
        # wc287 wc2867 7445"). Turn-wide rather than per-entity: they are the tokens no
        # fetch could be about, which is why none of them is in `entities`.
        "unresolved": list(unplaced.values()) if unplaced else [],
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
        #
        # ONLY when this turn described a class (`counted_set`). The `require` leg is
        # derived from the INTENT (`predicate.derive_require`: check_stock ->
        # {"stock": true}), so a predicate rides every stock / incoming / promotion
        # turn there is, and its `class_labels` are unioned from whatever the qualifying
        # candidates happen to belong to - not from anything the customer said. "7445"
        # was answered "5 taps have stock." (turn 92d565a5) and a three-domain fan-out
        # over a carried code printed "0 products have incoming stock." over all three
        # sections, stock rows included (turn d5128c67). A code is not a class, so its
        # answer keeps the domain's own header.
        "header_override": fetched.get("set_header") if counted_set else None,
        # Ported from PR #1118 (not merged), D25: what the stock reply said about a
        # quantity being required, per product. The composer never reads it (the
        # sentence is the presenter's); `engine.py` rebuilds the open stock task from
        # it (`turn/task.py::tasks_after_reply`).
        "stock_availability": (
            fetched.get("stock_availability")
            if isinstance(fetched.get("stock_availability"), list)
            else []
        ),
        # Ported from PR #1118 (not merged), D15: the products a "just proceed"
        # dropped, named by the reply so the dealer can see what was not checked.
        # Stamped on the spec by the task, carried here because the composer prints
        # it under the section it belongs to.
        "not_checked": [
            name for name in (spec.filters.get("not_checked") or []) if isinstance(name, str)
        ],
        # The lane's OWN question, when the fetch asked one instead of (or beside)
        # answering: contract 38's "which document?" and contract 39's detail offer both
        # come back as `outstanding_ask` = `{kind, last_result_set, filters}`. The
        # composer turns it into the turn's open question - before this it was dropped
        # here, so the report printed "Reply 1 for the sales order list" and stored the
        # ESCALATE offer instead, and the "1" that came back resolved against the wrong
        # roster.
        #
        # `forms_ask` (item 1, 17 Sep 2026) is the same shape, armed by
        # `output_structurer` off a forms BROWSE with several rows - the two never both
        # carry a value on the same envelope (one tool per spec), so reading either is
        # safe. `alternatives_ask` (R-c, hand pass 6) is the third: the fuzzy roster
        # `make_tool_runner.runner` arms over an entity miss's own trigram neighbours,
        # armed only when the fetch never ran filtered - the same "one tool per spec"
        # rule keeps the three from ever colliding.
        "lane_ask": (
            fetched.get("outstanding_ask")
            or fetched.get("forms_ask")
            or fetched.get("alternatives_ask")
        ),
        # AC-1139: this reply already states the scope it searched, in its own words
        # and its own order (the report's four header lines, and the same four above
        # the scope question). The composer's generic `*orders* for <code>:` line would
        # say it a second time, differently, above the answer.
        "own_header": bool(fetched.get("outstanding_report")),
        "outcome": fragment.get("outcome"),
        "tool": (fetched.get("tool") or {}).get("name") if isinstance(fetched.get("tool"), dict) else None,
        # The window this fetch ran with, already in the words the scope question uses
        # for it (`lanes/business.order_date_text` is the one writer). Absent when the
        # fetch had no window - the header then says nothing rather than "all", which is
        # the report's own line and belongs with the other three.
        "date_line": _date_line(ran_with),
        # R3 (PLAN-chatbot-answer-half-reattach.md): `lanes.business.run_fetch`'s own
        # tier-ask arm - the REAL "entitled, must pick a tier" path, discovered only
        # once the fetch actually ran the per-tier promotion probe. `fragment` (not
        # `fetched`) carries the top-level `_fetch_arm` marker `fetch_result` sets;
        # `fetched` (== `fragment["fetch"]`) is the item `answer_bridge.question_for`'s
        # own `fetch=` kwarg expects. `None` on every other fetch, which is the ONLY
        # value `turn/compose.py` (which never reads this key) will ever see.
        "tier_ask_fetch": fetched if fragment.get("_fetch_arm") == "tier-ask" else None,
        # Security B2 (AC-1333's own rule on main, `lanes/business/__init__.py:1449-
        # 1455`): the RECOMPOSED access levels this fetch actually went out with
        # (`_fetch_semantic_input`'s own, off `tier_gate.access_levels_recomposed` when
        # a tier gate ran). `engine.py` records it on the set-page carry so a later
        # "more" recounts the set under the SAME entitlement rather than under the
        # parser's own, empty, list. `None` on every arm that never called the tool.
        "access_levels_used": fetched.get("access_levels"),
    }
    if raw_fragment is not None:
        # R4 (PLAN-chatbot-answer-half-reattach.md): the UNTOUCHED `business.run_fetch`
        # fragment itself, a general-purpose escape hatch - `answer_bridge.answer_for`
        # reads `raw_fragment.get("outcome")` / `raw_fragment.get("fetch")` off it to
        # discover a genuine absence (`outcome == "not_found"`) after a fetch has
        # actually run, the same way `tier_ask_fetch` above discovers a tier-ask.
        # `turn/compose.py` never reads this key. ABSENT (not merely `None`) unless the
        # caller supplies one - `make_tool_runner.runner` is the one caller that does.
        envelope["raw_fragment"] = raw_fragment
    return envelope


def _date_line(ran_with: dict[str, Any] | None) -> str | None:
    """`Order date: 01/09/2026 to 30/09/2026`, or None when the fetch had no window."""
    if not isinstance(ran_with, dict):
        return None
    start = ran_with.get("date_filter_start")
    end = ran_with.get("date_filter_end")
    if not (start or end):
        return None
    from app.services.chatbot.lanes.business import order_date_text

    return f"Order date: {order_date_text(start, end)}"
