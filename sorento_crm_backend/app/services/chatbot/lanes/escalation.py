"""The `out_of_scope` lane: hand the turn to a person (S5, AC-501 to AC-507).

Port of the LIVE `sub-escalation` (`fr2u3e6FKg52cPvK` @ `bac9613b`, 10 nodes) plus the
assignment path inside `sub-human-intervention` (@ `ae310ea1`). The live graph is:

    escalation-input -> escalation-context -> clarify-company-gate (If)
        -> [true]  clarify-company-reply       -> escalation-result {arm: 'clarify'}
        -> [false] Call 'sub-human-intervention' -> escalation-result {arm: 'human-intervention'}

**What is NOT here, and why that is the point.** The EXPORT of this workflow carries a
`fresh-entity-gate` and a `clarify-team-gate` / `clarify-team-reply` pair. Neither is live:
they belong to unpromoted builds (B-HB-1 and B-TEAM-1'). Porting them would have shipped
behaviour production has never run, so:

* **H26 stays open.** The lane never calls the resolver, so escalation routing is
  brand-blind exactly as it is today. `resolve_and_gate` is in the services bundle for the
  day B-HB-1 promotes and is never invoked.
* **H27 stays open.** There is no team clarify. A null team is not reachable through the
  real pipeline anyway - `head/output_exchange.derive_routing`'s nullish chain hard-defaults
  `suggested_team` to `customer_service` long before this lane sees it - so the hazard is
  live in the PARSER, not here, and this lane simply carries whatever arrives.

Both are marked `xfail(strict=True)` in the tester's suite, so the promotion makes itself
noticed rather than needing to be remembered.

**D14 is evaluated FIRST** (H37). Live's own `test-guard` If sits ahead of the first
send and everything after it, so a dry run reaches no seam at all: no assignee is picked,
no SLA row is created, no cursor moves. `run()` reproduces that ordering literally rather
than guarding each seam, because "guarded afterwards" is what H37 records going wrong.

**D9: the CRM never sends.** Every effect leaves as an `action` for the caller to execute,
in the order the live graph performs them.

**This lane never writes chat history.** `sub-add-comment-respond` does two things when it
runs - the respond.io comment AND a CRM chat-history POST - and it keeps doing both when the
caller executes the `add_comment` action. Writing the comment here as well would double it:
one row from this lane and one from the sub. There is no import of the chat-history service
anywhere in this module, and `test_s5_no_chat_history_write.py` asserts the row count.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.services.chatbot import jsc
from app.services.chatbot.contracts import PREVIEW

logger = logging.getLogger(__name__)

# `escalation-context`'s own STOPGAP mirror of the parser fork's map. The real source is
# the CRM `companies.code` column threaded through the resolver; kept byte-identical here
# and in `head/output_exchange.CO_ALIASES` until that lands.
CO_ALIASES: dict[str, list[str]] = {
    "sorento": ["sorento", "srt"],
    "mocha": ["mocha", "mch"],
    "cabana": ["cabana", "cbn"],
}

# `sorento-sub-respond-sendmsg-respond-routed-to-pic2`'s `message`, verbatim. Sent BEFORE
# the assignment work, which is why the customer hears something even when the round robin
# is slow.
OUT_OF_SCOPE_REPLY = (
    "Your request is out of the scope of my ability and require human assistance. "
    "We are directing your enquiry to the correct person. Please wait for a moment."
)

# `sorento-sub-respond-sendmsg-respond-routed-to-pic`'s `message`, with `{{ ...team }}`
# prettified the way `tail/outcome.pretty_team` prettifies every other team in customer
# copy (the raw slug `customer_service` was reaching WhatsApp).
ROUTED_TO_PIC_REPLY = (
    "This inquiry has been routed to the respective person-in-charge (PIC) from {team} "
    "team. We will get back to you soon. Thanks for your patience."
)

# `Call 'sub-add-comment-respond'`'s `comment`, and the timezone its DateTime conversion
# uses. Asia/Kuala_Lumpur is +08:00 with no DST, so a fixed offset is the whole rule.
MALAYSIA = timezone(timedelta(hours=8))
RESPOND_INBOX_URL = "https://app.respond.io/space/{space_id}/inbox/{contact_id}#{message_id}"

# `get-round-robin-assignee`'s body has these two frozen, as literals in the JSON.
NEXT_ASSIGNEE_POLICY_CODE = "NORMAL"
NEXT_ASSIGNEE_TIER = 1


# --------------------------------------------------------------------------- #
# The services seam
# --------------------------------------------------------------------------- #


class ResolveAndGateFn(Protocol):
    def __call__(self, ctx: Any, item: Any) -> Any: ...


class NextAssigneeFn(Protocol):
    def __call__(self, body: dict[str, Any]) -> dict[str, Any]: ...


class SlaCreateFn(Protocol):
    def __call__(self, body: dict[str, Any]) -> dict[str, Any]: ...


class TeamMembersFn(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...


class StaffLookupFn(Protocol):
    """`(first_name) -> [{team_code, team_name, user_id, user_name, respond_user_id}]`."""

    def __call__(self, name: str) -> list[dict[str, Any]]: ...


# --------------------------------------------------------------------------- #
# escalation-input.js
# --------------------------------------------------------------------------- #


def escalation_input(trigger: Any) -> dict[str, Any]:
    """The sub's item carrier: `trigger.item`, whole.

    It exists so the escalation lane's items keep `route-turn`'s `{...access, branch_kind}`
    keys, which `escalation-context` and `clarify-company-reply` both spread over. The
    throw is the node's own and is reproduced: a trigger with no `item` object is a caller
    contract break, not something to paper over with `{}`.
    """
    item = jsc.get(trigger, "item")
    if not isinstance(item, dict):
        raise ValueError(
            "sub-escalation: the trigger carried no `item` object - the contract is "
            "{ ctx, item, is_test }"
        )
    return item


# --------------------------------------------------------------------------- #
# escalation-context.js (live: five outcomes, no `gate`)
# --------------------------------------------------------------------------- #


def _prev_variables(ctx: Any) -> dict[str, Any]:
    """`ctx.session.session_vars.variables`, with the node's own two fallbacks.

    The JS tries `session.session_vars.variables`, then `session.variables`, then `{}` -
    three shapes because the session block has had three over its life. Reproduced whole.
    """
    try:
        session = jsc.get(jsc.get(ctx, "session"), "session_vars")
        variables = jsc.get(session, "variables")
        if jsc.truthy(variables):
            return variables
        direct = jsc.get(jsc.get(ctx, "session"), "variables")
        return direct if jsc.truthy(direct) else {}
    except Exception:  # noqa: BLE001 - the JS's own try/catch, same fallback
        return {}


def _company_keys(company: Any) -> set[str]:
    """Every string a `company_pick` may legitimately match this row by."""
    name = jsc.get(company, "company_name")
    name_key = jsc.js_string(name).lower().strip() if jsc.truthy(name) else ""
    keys: set[str] = set()
    if name_key:
        keys.add(name_key)
    company_id = jsc.get(company, "company_id")
    if jsc.truthy(company_id):
        keys.add(jsc.js_string(company_id).lower())
    for code in (jsc.get(company, "company_code"), jsc.get(company, "code")):
        if isinstance(code, str) and code.strip():
            keys.add(code.lower().strip())
    for alias in CO_ALIASES.get(name_key, []):
        keys.add(alias)
    return keys


def escalation_context(item: dict[str, Any], *, ctx: dict[str, Any]) -> dict[str, Any]:
    """The brand / company axes this escalation routes on. Pure.

    A five-rung ladder, in the live body's order:

    1. `picked_member` - the customer picked a row out of the frozen `last_result_set`, so
       both axes are that row's own, verbatim;
    2. `company_pick` - the parser resolved a company name against the OFFERED pool. It
       sits ABOVE the multi-company arm so a resolvable reply routes instead of re-asking;
    3. `sameTeam` - the roster the offer was fetched with, which splits three ways:
       `prior_state` (one company), `prior_state_no_company` (one row, no id) and
       `multi_company_unpicked` (more than one, nobody picked - the clarify arm);
    4. `stated_brand` - a brand the customer named when no roster was involved at all;
    5. `none`.

    Both axes are always what the `get-cs-members` call USED, never re-derived from this
    turn's `query_brands`: re-deriving would narrow the assignee pool to one the customer
    was never shown.
    """
    output = jsc.get(jsc.get(ctx, "parse"), "output") or {}
    prev = _prev_variables(ctx)

    team = jsc.get(jsc.get(output, "routing"), "suggested_team") or None
    prev_routing = jsc.get(prev, "routing")
    same_team = bool(
        jsc.truthy(prev_routing)
        and jsc.truthy(team)
        and jsc.get(prev_routing, "suggested_team") == team
    )
    picked = jsc.get(jsc.get(output, "escalation"), "preferred_assignee_id") or None
    row = None
    if picked:
        last_set = jsc.array(jsc.get(prev, "last_result_set"))
        row = jsc.find(last_set, lambda r: jsc.truthy(r) and jsc.get(r, "uuid") == picked)

    query_brands = jsc.get(output, "query_brands")
    stated_brand = (
        jsc.js_string(query_brands[0]).lower()
        if jsc.is_array(query_brands) and len(query_brands) == 1
        else None
    )

    raw_pick = jsc.get(jsc.get(output, "escalation"), "company_pick")
    company_pick = jsc.js_string(raw_pick).lower().strip() if jsc.truthy(raw_pick) else None

    pick_row = None
    if company_pick:
        # (A) the pool is the companies actually OFFERED: the roster plan when non-empty,
        # else `routing_companies`. Never the union, so a pick can never land on a company
        # whose roster the customer was not shown.
        plan = jsc.array(jsc.get(prev, "routing_roster_plan"))
        source = plan if len(plan) else jsc.array(jsc.get(prev, "routing_companies"))
        pool = [
            c
            for c in source
            if jsc.truthy(c) and (jsc.truthy(jsc.get(c, "company_name")) or jsc.truthy(jsc.get(c, "company_id")))
        ]
        hits = [c for c in pool if company_pick in _company_keys(c)]
        # Deduplicated by identity before the count: two rows for one company are one hit.
        unique = list(
            {
                jsc.js_string(jsc.get(c, "company_id") or jsc.get(c, "company_name")).lower(): c
                for c in hits
            }.values()
        )
        pick_row = unique[0] if len(unique) == 1 else None

    brand_code: Any = None
    company_id: Any = None
    company_name: Any = None
    source_name = "none"

    if row is not None:
        company_id = jsc.get(row, "company_id") or None
        company_name = jsc.get(row, "company_name") or None
        # `'brand_code' in row` is the node's own test: a row that CARRIES the key uses it
        # even when it is null, and only a row without the key falls back to prior state.
        if jsc.has(row, "brand_code"):
            brand_code = jsc.get(row, "brand_code") or None
        else:
            brand_code = (jsc.get(prev, "routing_brand") if same_team else None) or None
        source_name = "picked_member"
    elif pick_row is not None:
        company_id = jsc.get(pick_row, "company_id") or None
        company_name = jsc.get(pick_row, "company_name") or None
        brand_code = jsc.get(pick_row, "brand_code") or None
        source_name = "company_pick"
    elif same_team:
        plan = jsc.array(jsc.get(prev, "routing_roster_plan"))
        if len(plan) == 1:
            company_id = jsc.get(plan[0], "company_id") or None
            company_name = jsc.get(plan[0], "company_name") or None
            brand_code = jsc.get(plan[0], "brand_code") or None
            source_name = "prior_state" if company_id else "prior_state_no_company"
        elif len(plan) > 1:
            source_name = "multi_company_unpicked"
        else:
            companies = jsc.array(jsc.get(prev, "routing_companies"))
            company_id = jsc.get(prev, "routing_company") or None
            match = jsc.find(
                companies, lambda x: jsc.truthy(x) and jsc.get(x, "company_id") == company_id
            )
            company_name = (jsc.get(match, "company_name") or None) if match is not None else None
            if company_id:
                source_name = "prior_state"
            elif len(companies) > 1:
                source_name = "multi_company_unpicked"
            else:
                source_name = "prior_state_no_company"
            # rev-2: NO roster was fetched for this offer, so there is no shown pool for a
            # brand to disagree with - carry the resolved brand rather than dropping it.
            # `next-assignee` narrows to brand-tagged plus untagged members, so this can
            # only refine the pool, and there is no pinned pick on this arm to exclude.
            if source_name != "multi_company_unpicked":
                routing_brand = jsc.get(prev, "routing_brand")
                brand_code = routing_brand if routing_brand is not None else None
    elif stated_brand:
        brand_code = stated_brand
        source_name = "stated_brand"

    return {
        **item,
        "brand_code": brand_code,
        "company_id": company_id,
        "company_name": company_name,
        "routing_source": source_name,
        "team": team,
    }


# --------------------------------------------------------------------------- #
# clarify-company-reply.js (live: one shape, no gate branch)
# --------------------------------------------------------------------------- #


def clarify_company_reply(item: dict[str, Any], *, ctx: dict[str, Any]) -> dict[str, Any]:
    """The ask that goes out when a multi-company offer was not resolved. Pure.

    It COMPOSES only; nothing is sent from here. The copy offers a number, a name, or the
    company, and the companies are bold in both the lead and the parenthetical because the
    parser matches a reply against this same printed pool. Two pool rows sharing one name
    collapse to one printed name, and that single name still resolves (the pool keys are
    per name). With no names at all the ask degrades to number-or-name: never invite a
    reply that cannot resolve.
    """
    prev = _prev_variables(ctx)
    plan = jsc.array(jsc.get(prev, "routing_roster_plan"))
    pools = plan if len(plan) else jsc.array(jsc.get(prev, "routing_companies"))

    names: list[str] = []
    for entry in pools:
        name = jsc.get(entry, "company_name") if jsc.truthy(entry) else None
        if jsc.truthy(name) and name not in names:
            names.append(name)

    bold = [f"*{name}*" for name in names]
    listed = " / ".join(bold)
    if len(bold) > 1:
        joined = f"{', '.join(bold[:-1])} and {bold[-1]}"
    else:
        joined = bold[0] if bold else ""

    if len(names) == 2:
        lead = f"Both {joined} teams are listed"
    elif joined:
        lead = f"{joined} teams are listed"
    else:
        lead = "More than one team is listed"

    clarify_text = (
        f"{lead} - reply a number, a name, or the company ({listed}) and I'll assign automatically."
        if names
        else f"{lead} - reply a number or a name and I'll assign automatically."
    )
    return {**item, "clarify_company": True, "clarify_text": clarify_text}


# --------------------------------------------------------------------------- #
# escalation-result.js
# --------------------------------------------------------------------------- #


def escalation_result(
    *, clarify_team: Any = None, clarify_company: Any = None
) -> dict[str, Any]:
    """The sub's ONE exit. Two mutually exclusive terminals, one output shape.

    `clarify_team` is always `None` on live - there is no `clarify-team-reply` node - and is
    kept in the signature for the day B-TEAM-1' promotes, so the caller does not change
    shape twice.
    """
    if jsc.truthy(clarify_company):
        return {"arm": "clarify", "clarify": clarify_company}
    if jsc.truthy(clarify_team):
        return {"arm": "clarify", "clarify": clarify_team}
    return {"arm": "human-intervention", "clarify": None}


# --------------------------------------------------------------------------- #
# The lane
# --------------------------------------------------------------------------- #


def _pretty_team(team: Any) -> str:
    """Underscores to spaces, for CUSTOMER copy only. The slug is what routing keeps."""
    from app.services.chatbot.tail.outcome import pretty_team

    return pretty_team(team)


def _malaysia(value: Any) -> str:
    """`DateTime.fromISO(v, {zone:'utc'}).setZone('Asia/Kuala_Lumpur')`, formatted.

    Asia/Kuala_Lumpur is +08:00 all year, so the conversion is a fixed offset and needs no
    timezone database. A value that will not parse is printed as-is, which is what Luxon's
    invalid DateTime does rather than throwing the comment away.
    """
    text = jsc.js_string(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(MALAYSIA).strftime("%Y-%m-%d %H:%M:%S")


def _clarify_gate(context_item: dict[str, Any], ctx: dict[str, Any]) -> bool:
    """`clarify-company-gate`: an OPEN member picker whose pool nobody chose from.

    Three conditions, all of them state: the previous turn left a member offer open, it
    carried rows, and `escalation-context` came out of the ladder at
    `multi_company_unpicked`. Assigning here would round-robin a pool the customer was
    never shown a choice from, which is the live bug this arm exists to close.
    """
    prev = _prev_variables(ctx)
    return (
        jsc.get(context_item, "routing_source") == "multi_company_unpicked"
        and jsc.get(prev, "selection_context") == "member_offer"
        and len(jsc.array(jsc.get(prev, "last_result_set"))) > 0
    )


def run(
    ctx: dict[str, Any],
    item: dict[str, Any],
    *,
    services: Any = None,
    dry_run: bool = False,
    session_factory: Any = None,
) -> dict[str, Any]:
    """One escalation turn: `{arm, clarify, actions, pending}`.

    `services` defaults to the production bundle so `engine.py` can call this as the lane
    without knowing what it needs; every test passes its own.

    `session_factory` is the TURN's factory, and it is what the production branch opens its
    own unit of work from (H56): `run_turn` stamps the contact's company scope on every
    session that factory makes, so the lane's session is scoped like every other one the
    turn opens. It is defence in depth rather than a repair - `post_next_assignee` pins its
    own scope (`_scope_request_to_company`) before it reads `Team` / `AgentTeam`, so the
    draw itself was never failing - but the reads BEFORE that pin
    (`_routing_company_for_body`) and the lane's own unit of work did run unscoped, and one
    mechanism for the whole turn beats a per-callee pin. A caller that injects `services`
    never reaches it, which is why it is optional here and required at `production_session`.

    **The dry-run check is the first thing that happens after the arm is chosen**, which is
    live's own `test-guard` ordering and the whole of H37: n8n called `next-assignee` and
    guarded afterwards, so a test turn moved a real round-robin cursor. Here the seams are
    not reached at all.
    """
    context_item = escalation_context(item, ctx=ctx)

    if _clarify_gate(context_item, ctx):
        clarify = clarify_company_reply(context_item, ctx=ctx)
        result = escalation_result(clarify_company=clarify)
        # R3's marker, and it goes on the TURN ROW only - `response.pending` and the
        # trace. It is NOT what the next turn reads: `compile_state` writes
        # `variables.pending` from `pending_marker.derive`, which emits `escalation_offer`
        # or nothing, and `output_exchange` reads only `escalation_offer` off it. What
        # actually carries a company clarify across the turn boundary is the structured
        # pair the tail re-persists - `selection_context` plus `last_result_set` - which
        # `test_s5_escalation_seams.py` pins end to end. The marker is here so the trace
        # says WHY this turn asked instead of assigning.
        return {**result, "actions": [], "pending": {"kind": "company_clarify"}}

    result = escalation_result()
    team = jsc.get(context_item, "team")

    if dry_run:
        # D14 / H37, AC-507. No WRITING seam is reached - nothing is drawn, no cursor
        # advances, no SLA row is written - and the turn still returns every action it WOULD
        # have taken, in order, each flagged `dry_run` and `preview`. The executor renders
        # its expressions against this shape, so a dry run that returned a shorter list
        # would be a different contract from the live one and could not be rendered against.
        #
        # The assignee is PREVIEWED, not left blank: `preview_assignee` reads the same pool
        # and the same cursor as the live draw and advances neither, so the owner sees the
        # name the live turn would have picked. "Would assign to somebody" answered the
        # question nobody was asking.
        #
        # The ROUTING decision is previewed too, and that is not a nicety: the owner finds
        # these defects from the console, and the console runs dry (`is_test`). A dry run
        # that skipped the person / team gate would show the inherited team a live turn
        # would never use, which is the very thing the gate exists to stop being shown.
        # Both reads, no writes.
        #
        # `assign_conversation` is always present here: whether the live run omits it
        # depends on `is_already_assigned`, which only the seam knows, so a preview cannot
        # honestly leave it out.
        preview_sla = {
            "initiated_at": PREVIEW,
            "due_at": PREVIEW,
            "due_at_resolution": PREVIEW,
        }
        routed, preview_assignee = _preview_routing(
            ctx, context_item, team, services, session_factory
        )
        if routed is not None and routed["kind"] == "clarify":
            clarify = {**context_item, "clarify_team": True, "clarify_text": routed["text"]}
            return {
                **escalation_result(clarify_team=clarify),
                "actions": [],
                "pending": {"kind": "team_clarify"},
            }
        if routed is not None and routed["kind"] == "assign":
            team = routed["team"]
        actions = _assignment_actions(
            ctx,
            team,
            assignee=preview_assignee,
            sla=preview_sla,
            include_assign=True,
            dry_run=True,
            preview=True,
        )
        return {**result, "actions": actions, "pending": None}

    if services is not None:
        return _human_intervention(ctx, context_item, team, services, result)

    # No injected seam, so this is production: the session is opened HERE, off the TURN's
    # own factory (so it carries the contact's company scope, H56), and closed on the way
    # out whether the seams answered or raised. See `escalation_services`.
    from app.services.chatbot.lanes import escalation_services

    with escalation_services.production_session(session_factory) as db:
        return _human_intervention(
            ctx, context_item, team, production_services(db), result
        )


def _human_intervention(
    ctx: dict[str, Any],
    context_item: dict[str, Any],
    team: Any,
    services: Any,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Assign the conversation, or ask which team - one place, both seam sources.

    The person / team decision needs a seam, so it happens HERE rather than in `run()`,
    where the production bundle does not exist yet.
    """
    routed = _person_routing(ctx, context_item, team, services)
    if routed is not None and routed["kind"] == "clarify":
        # The tail keys on `clarify_text` (`compile_state`'s clarify arm), the same field
        # `clarify-company-reply` writes; the item carries the context so the trace shows
        # what was asked and why.
        clarify = {**context_item, "clarify_team": True, "clarify_text": routed["text"]}
        return {
            **escalation_result(clarify_team=clarify),
            "actions": [],
            "pending": {"kind": "team_clarify"},
        }
    if routed is not None and routed["kind"] == "assign":
        actions = _assign(
            ctx,
            context_item,
            routed["team"],
            services,
            assignee=routed["assignee"],
        )
        return {**result, "actions": actions, "pending": None}
    actions = _assign(ctx, context_item, team, services)
    return {**result, "actions": actions, "pending": None}


def _parser_team(ctx: dict[str, Any], team: Any) -> Any:
    """The team the PARSER itself resolved, not the one the turn inherited.

    `ctx.parse.output.routing` is post-processed, and `output_exchange` carries the previous
    turn's routing into it - so by the time this lane sees it, a turn the parser routed
    nowhere looks routed. `_parser_raw` is the pre-derivation snapshot the same block keeps
    (`output_exchange` sets it, `engine` puts it on `ctx.parse`), and it is what says whether
    THIS message named a team. Falls back to the derived value when there is no snapshot, so
    an injected ctx behaves as it reads.
    """
    raw = jsc.get(jsc.get(ctx, "parse"), "_parser_raw")
    if not isinstance(raw, dict):
        return team
    return jsc.get(jsc.get(raw, "routing"), "suggested_team")


def _pick_staff(hits: list, team: Any) -> Any:
    """The ONE staff member this ask names, or `None` when the roster cannot say.

    One hit is the answer. Several hits for the SAME person are several team memberships,
    not several people (5 of 22 staff on this install are on more than one team), so the
    team the parser already resolved breaks that tie - and only that tie. Two DIFFERENT
    people sharing a name is a real ambiguity and the lane asks, whatever team came in:
    picking by the parser's team there would answer a question about WHO with a fact about
    WHERE.
    """
    if len(hits) == 1:
        return hits[0]
    people = {jsc.js_string(jsc.get(h, "user_id")) for h in hits}
    if len(people) != 1:
        return None
    wanted = jsc.nullish_str(team).strip().lower()
    if not wanted:
        return None
    matched = [h for h in hits if jsc.nullish_str(jsc.get(h, "team_code")).strip().lower() == wanted]
    return matched[0] if len(matched) == 1 else None


def _person_routing(
    ctx: dict[str, Any], context_item: dict[str, Any], team: Any, services: Any
) -> dict[str, Any] | None:
    """"escalate to Nurain" / "escalate to marketing": route by WHO, or ask which team.

    Owner ruling, 6 Sep 2026, from two console turns that both arrived with
    `routing = {suggested_team: null, suggested_agent: null}` and were assigned to whatever
    team the PREVIOUS turn happened to be routed to - the comment named marketing_product
    for a customer-service person and purchasing for a marketing ask.

    Deterministic throughout, and off structured state only (D11 - the name is the parser's
    own `person_mention`, never a regex over the customer's words):

    * A named person is resolved against the staff roster. One match routes to THEIR team
      with them as the assignee - a person the customer named is a direct pick, not a
      round-robin draw. Two different people sharing the name ASKS.
    * **A miss only asks when the PARSER itself resolved no team.** Review of #700: 70 parse
      outputs in the corpus carry a `person_mention` ALONGSIDE a resolved `suggested_team`
      - a greeting, a signature, a name in passing - and every one of those five names
      returns zero roster hits. Asking there would replace correct routing with a question,
      so a miss falls through to that team.

      The team that decides this is `ctx.parse._parser_raw.routing.suggested_team`, the
      parser's OWN answer, never the derived one - and that distinction is the owner's whole
      case, measured on their turn: "escalate to Nurain" arrived with
      `_parser_raw.routing = {suggested_team: null, suggested_agent: null}` while the
      DERIVED routing had already inherited `purchasing` from the previous turn upstream in
      `output_exchange`. Gating on the derived team would make this gate inert on exactly
      the turn it was written for, which is what the first console run showed. With no
      `_parser_raw` (a mocked parse, an injected ctx) the derived team stands in.
    * No person, no team, and a previous turn that HAD one: ask. That is the inheritance
      the owner rejected, and refusing it here is the whole fix. With no previous routing
      to inherit there is nothing to be wrong about, so the lane carries on exactly as it
      does today (`test_no_team_clarify_on_live_team_flows_through_unguarded`).

    Returns `None` for "nothing to do here", which is every turn that names nobody and
    arrives with a team.
    """
    output = jsc.get(jsc.get(ctx, "parse"), "output") or {}
    person = jsc.nullish_str(jsc.get(output, "person_mention")).strip()

    if person:
        lookup = getattr(services, "staff_lookup", None) if services is not None else None
        if lookup is None:
            return None  # a bundle without the seam behaves exactly as it did before
        try:
            hits = [h for h in jsc.array(lookup(person)) if jsc.truthy(h)]
        except Exception:  # noqa: BLE001 - a failed lookup never guesses
            logger.warning("chatbot: staff lookup did not run", exc_info=True)
            hits = []
        picked = _pick_staff(hits, team)
        if picked is not None:
            return {
                "kind": "assign",
                "team": jsc.get(picked, "team_code"),
                "assignee": {
                    "assignee_id": jsc.get(picked, "user_id"),
                    "assignee_name": jsc.get(picked, "user_name"),
                    "assignee_respond_user_id": jsc.get(picked, "respond_user_id"),
                    "team_set_code": jsc.get(picked, "team_code"),
                    "is_already_assigned": False,
                },
            }
        if jsc.truthy(_parser_team(ctx, team)):
            return None  # the parser itself named a team: the mention was in passing
        return {"kind": "clarify", "text": _team_clarify_text(person, hits)}

    prev_team = jsc.get(jsc.get(_prev_variables(ctx), "routing"), "suggested_team")
    if not jsc.truthy(team) and jsc.truthy(prev_team):
        return {"kind": "clarify", "text": _team_clarify_text(None, [])}
    return None


def _team_clarify_text(person: Any, hits: list) -> str:
    """The ask. Names the teams the customer can choose between, and nothing else.

    With hits it is the teams THOSE people are on (that is the whole ambiguity); without,
    it is the routing vocabulary, which is the exact set the router can act on - inventing
    a shorter list would invite a reply nothing could resolve.
    """
    from app.services.chatbot.contracts import SUGGESTED_TEAMS

    names: list[str] = []
    for hit in hits:
        name = jsc.get(hit, "team_name") or _pretty_team(jsc.get(hit, "team_code"))
        if jsc.truthy(name) and name not in names:
            names.append(name)
    if not names:
        names = [_pretty_team(t) for t in SUGGESTED_TEAMS]
    listed = f"{', '.join(names[:-1])} or {names[-1]}" if len(names) > 1 else names[0]
    if person and hits:
        people = {jsc.js_string(jsc.get(h, "user_id")) for h in hits}
        lead = (
            f"{jsc.js_string(person)} is on more than one team"
            if len(people) == 1
            else f"More than one person here goes by {jsc.js_string(person)}"
        )
        return f"{lead}. Which team do you mean - {listed}?"
    if person:
        return (
            f"I could not find anyone called {jsc.js_string(person)}. "
            f"Which team should I pass this to - {listed}?"
        )
    return f"Which team should I pass this to - {listed}?"


def _preview_routing(
    ctx: dict[str, Any],
    context_item: dict[str, Any],
    team: Any,
    services: Any,
    session_factory: Any,
) -> tuple[dict[str, Any] | None, Any]:
    """`(routing decision, assignee)` for a dry run - both READS, in one unit of work.

    Fails soft throughout, on purpose: a bundle with no preview seam (an older injected
    stub), a lookup that raises, or no session factory at all leave the assignee null,
    which is the placeholder AC-507 shipped with. A dry run must never fail a turn over the
    extra detail it is trying to show.
    """

    def _both(bundle: Any) -> tuple[dict[str, Any] | None, Any]:
        routed = _person_routing(ctx, context_item, team, bundle)
        if routed is not None:
            # A named person IS the assignee, and a clarify assigns nobody. Either way
            # there is no rotation to preview.
            return routed, routed.get("assignee")
        seam = getattr(bundle, "preview_assignee", None)
        if seam is None:
            return None, None
        return None, seam({**_next_assignee_body(ctx, context_item), "preview": True})

    try:
        if services is not None:
            return _both(services)
        if session_factory is None:
            return None, None
        # Production dry run: the same read-only unit of work the live branch uses, so both
        # reads are scoped to the contact's company exactly as the draw would be (H56).
        from app.services.chatbot.lanes import escalation_services

        with escalation_services.production_session(session_factory) as db:
            return _both(escalation_services.build(db))
    except Exception:  # noqa: BLE001 - a preview is never worth failing a test turn for
        logger.warning("chatbot: dry-run routing preview did not run", exc_info=True)
        return None, None


def _assign(
    ctx: dict[str, Any],
    context_item: dict[str, Any],
    team: Any,
    services: Any,
    *,
    assignee: Any = None,
) -> list[dict[str, Any]]:
    """Draw an assignee, start the SLA clock, and build the four actions in live's order.

    Both seams run before a single action is built, which is what makes the failure shape
    in `engine.py` true: the lane returns its whole list or raises before returning any of
    it, so "assigned but no SLA row" is not a state a caller can observe.

    `assignee` is passed in ONLY when the customer named the person (the staff-lookup arm):
    a direct pick is not a rotation, so the round robin is not drawn from at all. The SLA
    clock still starts, because the escalation is just as real.
    """
    if assignee is None:
        assignee = services.next_assignee(_next_assignee_body(ctx, context_item))
    sla = services.sla_create(_sla_body(ctx, context_item, assignee))
    return _assignment_actions(
        ctx,
        team,
        assignee=assignee,
        sla=sla,
        # `if-conversation-unassigned`'s true leg. Already assigned in respond.io means
        # someone is on the conversation and re-assigning would take it off them.
        include_assign=jsc.get(assignee, "is_already_assigned") is not True,
        dry_run=False,
        preview=False,
    )


def _assignment_actions(
    ctx: dict[str, Any],
    team: Any,
    *,
    assignee: Any,
    sla: Any,
    include_assign: bool,
    dry_run: bool,
    preview: bool,
) -> list[dict[str, Any]]:
    """The four actions, in the order the live graph performs them.

    ONE builder for the live list and the preview list, so the two can only differ in the
    values a seam would have supplied - never in the shape, the order or the set of keys.
    That is the whole point of AC-507: the executor renders one template against both.

    Neither `send_message` depends on the assignee: the first is a fixed sentence and the
    second interpolates the TEAM, which the ladder resolved before any seam was reached. So
    both carry their real text even in a preview, and only the assignee id, the mention and
    the three timestamps are placeholders.
    """
    respond_user_id = jsc.get(assignee, "assignee_respond_user_id") if assignee is not None else None
    actions: list[dict[str, Any]] = [_send_message(OUT_OF_SCOPE_REPLY, dry_run)]
    if include_assign:
        action: dict[str, Any] = {
            "kind": "assign_conversation",
            "respond_user_id": respond_user_id,
            "dry_run": dry_run,
        }
        if preview:
            action["preview"] = True
        actions.append(action)
    comment: dict[str, Any] = {
        "kind": "add_comment",
        "text": _comment_text(ctx, team, sla),
        # The RESPOND user id, not the CRM one, and exactly one of them: the executor maps
        # this to `sub-add-comment-respond`'s `user_id`, which is what respond.io needs to
        # turn a comment into a mention. `assign_conversation` above carries the same id.
        "mention_user_ids": [respond_user_id] if respond_user_id is not None else [],
        "dry_run": dry_run,
    }
    if preview:
        comment["preview"] = True
    actions.append(comment)
    actions.append(_send_message(ROUTED_TO_PIC_REPLY.format(team=_pretty_team(team)), dry_run))
    return actions


def _send_message(text: str, dry_run: bool) -> dict[str, Any]:
    """One `send_message` action, in the shape the n8n executor takes.

    `quick_replies` and `result_set` are declared here and left empty ON PURPOSE. They are
    SEALED values that only exist once the tail has composed the reply, and the engine arm
    fills them in from `complete_turn`'s output before the actions leave. Declaring them
    here rather than adding them later keeps every `send_message` the same shape whoever
    built it, so the executor never has to test for a missing key.

    The placeholders match the sealed contract's own empty case (AC-507): `quick_replies`
    null (n8n's `quick_reply` is a comma-joined string or null, never a list) and
    `result_set` `[]` (`compile-current-state`'s own default for `last_result_set`).
    """
    return {
        "kind": "send_message",
        "text": text,
        "quick_replies": None,
        "result_set": [],
        "dry_run": dry_run,
    }


def _next_assignee_body(ctx: dict[str, Any], context_item: dict[str, Any]) -> dict[str, Any]:
    """`get-round-robin-assignee`'s JSON body, key for key.

    `policy_code` and `tier` are literals in the node, not settings - reproduced as
    literals so a change to them is a change to this file and shows up in a diff.
    """
    output = jsc.get(jsc.get(ctx, "parse"), "output") or {}
    return {
        "agent_code": jsc.get(jsc.get(output, "routing"), "suggested_agent"),
        "team_code": jsc.get(context_item, "team"),
        "contact_phone_number": jsc.get(jsc.get(ctx, "contact"), "phone"),
        "policy_code": NEXT_ASSIGNEE_POLICY_CODE,
        "preferred_assignee_id": jsc.get(jsc.get(output, "escalation"), "preferred_assignee_id") or "",
        "tier": NEXT_ASSIGNEE_TIER,
        "brand_code": jsc.get(context_item, "brand_code"),
        "company_id": jsc.get(context_item, "company_id"),
    }


def _sla_body(
    ctx: dict[str, Any], context_item: dict[str, Any], assignee: Any
) -> dict[str, Any]:
    """`conversation-sla-tracking-create`'s JSON body, key for key.

    Three fields prefer the ASSIGNEE's answer over the turn's (`team_set_code`,
    `brand_code`, `company_id`): the round robin may have resolved a narrower pool than the
    turn knew about, and the SLA row has to describe who was actually assigned.
    """
    output = jsc.get(jsc.get(ctx, "parse"), "output") or {}
    message = jsc.get(jsc.get(ctx, "text"), "message")
    message_id = jsc.get(message, "messageId")
    input_message = _input_message(ctx)

    def prefer(key: str, fallback: Any) -> Any:
        value = jsc.get(assignee, key)
        return value if value is not None else fallback

    return {
        "assigned_to_id": jsc.get(assignee, "assignee_id") or "",
        "contact_phone_number": jsc.get(jsc.get(ctx, "contact"), "phone") or "",
        "agent_code": jsc.get(jsc.get(output, "routing"), "suggested_agent") or "",
        "team_set_code": prefer("team_set_code", jsc.get(context_item, "team") or ""),
        "brand_code": prefer("brand_code", jsc.get(context_item, "brand_code") or None),
        "company_id": prefer("company_id", jsc.get(context_item, "company_id") or None),
        "message_id": message_id if message_id is not None else None,
        "source_message_id": None if message_id is None else jsc.js_string(message_id),
        "source_message_text": input_message or "",
    }


def _input_message(ctx: dict[str, Any]) -> str:
    """`Call 'sub-human-intervention'`'s `input_message`, expression for expression.

    Live, from the node's `workflowInputs.value.input_message` (two adjacent `{{ }}`
    blocks, concatenated with no separator by the template):

        {{ ctx.text.message.message.text
           || ctx.text.message.message.attachment?.description
           || '[' + (ctx.text.message.message.type || 'unknown') + ' message]' }}
        {{ ctx.text.message.replyTo?.message
           ? ' reply to: ' + ctx.text.message.replyTo.message.text : '' }}

    Reading only `.text` - which is what this file did first - is right for a typed
    message and wrong for every other kind the bot actually receives: an image, a voice
    note or a document arrives with an empty `text`, so the SLA row's
    `source_message_text` came out blank and the person picking the case up saw no trace
    of what the customer sent. Live falls back to the attachment's description and then to
    a `[image message]` style placeholder naming the type, and appends the quoted message
    when the customer replied to one. Reproduced here rather than improved on: the SLA row
    is read beside rows n8n wrote, and two spellings of the same message would be worse
    than the placeholder.

    `replyTo` hangs off the WEBHOOK body (`ctx.text.message`), one level above the message
    body the first chain reads - copying its path from the wrong level is the easy mistake
    here, so both are spelled out above.
    """
    envelope = jsc.get(jsc.get(ctx, "text"), "message")
    body = jsc.get(envelope, "message")

    value = jsc.get(body, "text", jsc.UNDEFINED)
    if not jsc.truthy(value):
        value = jsc.get(jsc.get(body, "attachment"), "description", jsc.UNDEFINED)
    if not jsc.truthy(value):
        kind = jsc.get(body, "type", jsc.UNDEFINED)
        value = "[" + (jsc.js_string(kind) if jsc.truthy(kind) else "unknown") + " message]"

    text = jsc.js_string(value)

    # `replyTo?.message` is the TRUTH TEST, and the text is read off it unguarded - so a
    # quoted message with no text renders JS's own `undefined`, which is what n8n stores
    # today. Faithful, not tidied.
    quoted = jsc.get(jsc.get(envelope, "replyTo"), "message", jsc.UNDEFINED)
    if jsc.truthy(quoted):
        text += " reply to: " + jsc.js_string(jsc.get(quoted, "text", jsc.UNDEFINED))
    return text


def _comment_text(ctx: dict[str, Any], team: Any, sla: Any) -> str:
    """`Call 'sub-add-comment-respond'`'s `comment`, byte for byte.

    Verified against the live node expression by substituting its six `{{ }}` blocks and
    diffing the literal skeleton: equal. The three timestamps are Luxon's
    `fromISO(v, {zone:'utc'}).setZone('Asia/Kuala_Lumpur').toFormat('yyyy-MM-dd HH:mm:ss')`,
    which is `%Y-%m-%d %H:%M:%S` at a fixed +08:00 (Malaysia has no DST), and they come from
    the CRM's OWN in-process SLA create - n8n no longer calls that endpoint or composes this
    text.

    The team is the RAW slug here, not prettified: this is an internal note to the person
    picking the case up, and the slug is what they will search the CRM by.

    **No mention markup.** The text carries no `{{@user.<id>}}`; `sub-add-comment-respond`
    prefixes that itself from the `user_id` it is given, which is why the action carries the
    respond user id in `mention_user_ids` and not a formatted string.
    """
    contact_id = jsc.get(jsc.get(ctx, "contact"), "id")
    message_id = jsc.get(jsc.get(jsc.get(ctx, "text"), "message"), "messageId")
    reference = RESPOND_INBOX_URL.format(
        space_id=_space_id(ctx), contact_id=jsc.js_string(contact_id), message_id=jsc.js_string(message_id)
    )
    return (
        f"Team: {jsc.js_string(team)}\n"
        f"⏰ SLA Alert: This contact is routed to you at {_malaysia(jsc.get(sla, 'initiated_at'))}.\n"
        f"You have until {_malaysia(jsc.get(sla, 'due_at'))} to respond.\n"
        f"You have until {_malaysia(jsc.get(sla, 'due_at_resolution'))} to resolve.\n"
        f"Reference message: {reference}"
    )


def _space_id(ctx: dict[str, Any]) -> str:
    """The respond.io workspace the inbox link points at.

    n8n hard-codes `364817` inside the comment string. D5 moved that to the default respond
    workspace row everywhere else; here the ctx does not carry it, so the literal stays and
    is named rather than hidden. Moving it is S8's job, with the rest of the hard-coded id.
    """
    return "364817"


# --------------------------------------------------------------------------- #
# Production bindings
# --------------------------------------------------------------------------- #


def production_services(db: Any) -> Any:
    """The real four seams over a caller-owned session.

    The session is a REQUIRED argument. This lane's writes (the round-robin cursor and the
    SLA row) are a unit of work of their own and must not ride the turn's routing
    transaction - a turn that fails later must not roll the assignment back out from under
    the person who was just told about it - but "its own session" is not the same as "a
    session nobody closes", which is what the first version left behind. `run()` opens one
    with `escalation_services.production_session(session_factory)` and closes it in the
    same breath.
    """
    from app.services.chatbot.lanes import escalation_services

    return escalation_services.build(db)
