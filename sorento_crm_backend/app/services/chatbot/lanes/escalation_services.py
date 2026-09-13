"""The three I/O seams `sub-human-intervention` has, as injectable callables.

n8n makes them two HTTP calls back into this same CRM and one `executeWorkflow`; the port
makes them in-process. They live here rather than inline in `escalation.py` so the lane
stays a pure function over structured state in every test - no database, no network - which
is what lets the 66-fixture replay run as JSON in, JSON out.

| n8n node | this seam | CRM service |
| --- | --- | --- |
| `get-round-robin-assignee` (httpRequest) | `next_assignee` | `POST /api/v1/external/next-assignee`'s own handler |
| (the same node, previewed) | `preview_assignee` | the same handler with `preview: true` |
| `conversation-sla-tracking-create` (httpRequest) | `sla_create` | `ConversationSLATrackingService.create_tracking` |
| `Call 'sub-resolve-and-gate'` | `resolve_and_gate` | the business lane's own resolver |
| (the member roster) | `team_members` | `app.api.v1.external.team_members` |
| (new, 6 Sep 2026) | `staff_lookup` | `users` x `team_members` x `agent_teams`, read here |

Every test in `test_s5_escalation_lane.py` injects its own `services`, which is the point
of the seam; `test_s5_escalation_seams.py` covers THIS module - the wiring that runs once
the owner adds `out_of_scope` to `system_settings.chatbot_completed_lanes` - with the two
CRM services stubbed at their own boundary, because a seam nothing ever executes is where
a typo waits for production.

`team_members` is declared and NOT wired, and it is the only one left that way. The team
ladder this lane runs (`escalation._person_routing`) asks over the CATALOGUE, which is a
constant, never over a fetched roster - so there is nothing for it to read. It raises
rather than half-working, so a future arm that does need a roster fails loudly instead of
silently asking over the wrong list.

`resolve_and_gate` IS wired as of PLAN-chatbot-escalation-routing (H26 closed): the
escalation lane resolves the product THIS turn named so the assignment can name its brand.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EscalationServices:
    """One bundle, six callables. `team_members` is the only one not wired (see above)."""

    resolve_and_gate: Any
    next_assignee: Any
    preview_assignee: Any
    sla_create: Any
    team_members: Any
    staff_lookup: Any


def _next_assignee(db: Any):
    def call(body: dict[str, Any]) -> dict[str, Any]:
        """The `/external/next-assignee` handler, in process.

        It is declared `async def` and its body contains no `await` at all (measured: zero
        in the module), so driving it with `asyncio.run` is a formality that costs one
        event loop and changes nothing about what it does. Calling the handler rather than
        re-implementing round robin is deliberate: the cursor advance, the working-hours
        check and the already-assigned check are the behaviour n8n has been getting, and a
        second implementation of them would drift.
        """
        from app.api.v1.external.next_assignee import post_next_assignee

        return asyncio.run(
            post_next_assignee(body=body, current_user={"id": None, "email": "chatbot"}, db=db)
        )

    return call


def _preview_assignee(db: Any):
    def call(body: dict[str, Any]) -> dict[str, Any]:
        """The SAME handler, asked who it WOULD draw (`preview: true`).

        A dry run has to name the real next assignee, and it shares the round-robin cursor
        with live traffic, so it must not advance it. Going through the handler rather than
        reaching for the service keeps ONE implementation of team resolution, the company
        pin, segments and brands - the same reason `next_assignee` calls it.
        """
        from app.api.v1.external.next_assignee import post_next_assignee

        return asyncio.run(
            post_next_assignee(
                body={**body, "preview": True},
                current_user={"id": None, "email": "chatbot"},
                db=db,
            )
        )

    return call


def _sla_create(db: Any):
    def call(body: dict[str, Any]) -> dict[str, Any]:
        from app.schemas.sla import ConversationSLATrackingCreate
        from app.services.sla_service import ConversationSLATrackingService

        created = ConversationSLATrackingService(db).create_tracking(
            ConversationSLATrackingCreate(**body)
        )
        # The lane reads three fields off this for the comment; hand back a plain dict so
        # the seam's contract is a dict either way, stubbed or real.
        return {
            "id": getattr(created, "id", None),
            "initiated_at": getattr(created, "initiated_at", None),
            "due_at": getattr(created, "due_at", None),
            "due_at_resolution": getattr(created, "due_at_resolution", None),
        }

    return call


def _staff_lookup(db: Any):
    def call(name: str) -> list[dict[str, Any]]:
        """Active staff whose FIRST NAME is `name`, with the team each is on.

        The name comes from the parser's `person_mention` (D11 - the lane never reads the
        customer's words), and the match is deliberately narrow: the first word of the
        user's name, case-insensitively, or the whole name. Anything looser turns "escalate
        to Ali" into a guess, and the lane's answer to more than one hit is to ASK.

        The routing slug is `agent_teams.code` - the code the rest of the escalation path
        speaks - so a team with no agent-team row cannot be routed to and does not appear.
        The session carries the contact's company scope, so a person in another company's
        team is not a candidate.
        """
        from sqlalchemy import func, or_

        from app.models.access import AgentTeam, Team, TeamMember
        from app.models.user import User, UserStatus

        wanted = str(name or "").strip().lower()
        if not wanted:
            return []
        rows = (
            db.query(
                User.id,
                User.name,
                User.respond_user_id,
                Team.id,
                Team.name,
                AgentTeam.code,
            )
            .join(TeamMember, TeamMember.user_id == User.id)
            .join(Team, Team.id == TeamMember.team_id)
            .join(AgentTeam, AgentTeam.team_id == Team.id)
            .filter(
                # `status` is a String on the model and a NATIVE ENUM in production, so it
                # is compared as a literal and never wrapped in `lower()` - the function
                # does not exist for the enum type and the query 500s there while passing
                # every test on the String column.
                User.status == UserStatus.ACTIVE.value,
                User.is_trashed.is_(False),
                User.name.isnot(None),
                or_(
                    func.lower(User.name) == wanted,
                    func.lower(func.split_part(User.name, " ", 1)) == wanted,
                ),
            )
            # Stable, so the clarify list reads the same way twice: team name, then person.
            .order_by(Team.name.asc(), User.name.asc(), AgentTeam.code.asc())
            .all()
        )
        # One hit per PERSON per TEAM. A team commonly carries more than one agent-team
        # code (a tier or a legacy brand-suffixed variant - "customer_service" and
        # "customer_service_c" both point at Customer Service), and returning both would
        # read as two candidates and make the lane ask about an ambiguity that is not one.
        # The shortest code wins, then alphabetical: the base code is the short one, and
        # the tie-break is there so the answer cannot depend on row order.
        best: dict[tuple, dict[str, Any]] = {}
        for user_id, user_name, respond_user_id, team_id, team_name, team_code in rows:
            key = (str(user_id), str(team_id))
            held = best.get(key)
            code = str(team_code)
            if held is not None and (len(held["team_code"]), held["team_code"]) <= (len(code), code):
                continue
            best[key] = {
                "user_id": str(user_id),
                "user_name": user_name,
                "respond_user_id": respond_user_id,
                "team_name": team_name,
                "team_code": code,
            }
        return list(best.values())

    return call


# `lanes/business/miss_suggest._dym_plan`'s own `d1s = d1s[:5]` - the number of TOKEN blocks
# a did-you-mean offer prints. Its per-token cap is `_cap3`, imported where it is used.
MISS_TOKEN_BLOCK_CAP = 5


def _product_tokens(ctx: Any, body: dict[str, Any]) -> list[str]:
    """The tokens THIS MESSAGE's product entities were sent to the resolver as.

    Taken from the REQUEST, not re-derived: `resolve_entity_body` maps `ctx.parse.output.
    entities` positionally onto `tokens` (and onto `allowed_entity_types`), and a product
    token is folded on the way (`mfg6651-gm` is sent as `mfg6651gm`), so zipping the two is
    the only way the filter can be byte-identical to what was asked about.

    Why it has to exist at all: the body sends EVERY entity, the carried ones
    (`current_message: false`) and the category beside the code included. Without the filter
    a carried product or a category spec that resolves exact makes `resolved` non-empty, so
    the turn skips the did-you-mean the typed code needed and routes on a brand belonging to
    something the customer did not name this turn.
    """
    entities = (ctx or {}).get("parse", {}) if isinstance(ctx, dict) else {}
    entities = (entities or {}).get("output", {}) if isinstance(entities, dict) else {}
    rows = (entities or {}).get("entities") if isinstance(entities, dict) else None
    rows = rows if isinstance(rows, list) else []
    tokens = body.get("tokens") or []
    wanted: list[str] = []
    for entity, token in zip(rows, tokens):
        if not isinstance(entity, dict):
            continue
        if str(entity.get("hint") or "").lower() != "product":
            continue
        if entity.get("current_message") is not True:
            continue
        key = str(token or "").strip().lower()
        # Ordered and de-duplicated: the filter only needs membership, but the lane's own
        # `query` is built from this list and should read in the order the customer typed.
        if key and key not in wanted:
            wanted.append(key)
    return wanted


def _product_rows(
    payload: Any, wanted_tokens: list[str] | set[str] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(resolved, did_you_mean)` out of one resolver payload. Pure.

    The resolver answers per TOKEN with `matches` and `alternatives`, each row carrying
    `uuid`, `canonical_code`, `company_id`, `company_name`, `match_tier` and `display`
    (`app/services/entity_resolver.py`'s `as_dict`). The escalation lane wants one fact off
    it - the brand of the product the customer named - so the split is two rules:

    * `resolved` - PRODUCT rows at the `exact` tier. That is the same test the business
      lane's did-you-mean planner uses to decide a token resolved (`miss_suggest._is_exact`),
      so the two lanes cannot disagree about whether a code is known.
    * `did_you_mean` - every other product row, matches and alternatives alike, in the order
      the resolver ranked them (variants first, then by similarity). These are the rows the
      customer is offered when the code they typed does not exist.

    Product rows only, and only for the TOKENS THIS TURN'S PRODUCT ENTITIES WERE SENT AS
    (`wanted_tokens`, from `_product_tokens`). Two filters, two different mistakes they stop:
    an escalation turn commonly names a category beside the code ("BIDET SEAT COVER FOR
    SRTWC60630-SH") and a category has no brand to route by; and the body sends the CARRIED
    entities too, so a carried product that still resolves would answer for a code the
    customer did not type this turn - `resolved` non-empty, no did-you-mean for the code that
    missed, and the wrong brand on the assignment.

    The two degenerate values are different on purpose. `None` means NO FILTER, which is what a
    direct caller with no ctx gets (the cap still applies). An EMPTY LIST means "this turn named
    no product token", so every resolution is filtered out and both sides come back empty -
    which is the honest answer: the lane then carries no brand and arms no ask, exactly as a
    turn that named no product at all does (`escalation._resolve_product` does not even reach
    the seam on that turn, so the empty list is only seen by a caller that asked about nothing).

    De-duplicated by uuid on the resolved side and by code on the offer side, which is what
    the customer can tell apart on screen.

    **The OFFER side carries the business lane's own caps**, because AC-1124 says these are
    "the business lane's did-you-mean rows" and a numbered list nobody can read is not an
    offer. `lanes/business/miss_suggest.dym_rows_per_token` is three candidates per token and
    `_dym_plan`'s `d1s = d1s[:5]` is five token blocks, so the resolver's 15 matches per
    token over several tokens (75 rows on a five-token message) become at most 15 numbered
    lines, in the resolver's own ranking. The per-token cap is IMPORTED rather than
    re-spelled so the number cannot drift from the lane it is copied from; the block cap is a
    constant here beside it, with its source named, because `_dym_plan` holds it as a literal
    inside a 500-line planner this lane does not run.

    The RESOLVED side is not capped: it decides the brand, and "exactly one row" is the
    test the lane makes on it (`escalation._resolve_product`), so dropping a row there would
    change a routing decision rather than shorten a list.
    """
    from app.services.chatbot.lanes.business.miss_suggest import dym_rows_per_token

    resolved: dict[str, dict[str, Any]] = {}
    offers: dict[str, dict[str, Any]] = {}
    blocks: list[list[dict[str, Any]]] = []
    for resolution in (payload or {}).get("resolutions") or []:
        if not isinstance(resolution, dict):
            continue
        if wanted_tokens is not None:
            token = str(resolution.get("token") or "").strip().lower()
            if token not in wanted_tokens:
                continue
        rows = [
            row
            for key in ("matches", "alternatives")
            for row in (resolution.get(key) or [])
            if isinstance(row, dict)
        ]
        block: list[dict[str, Any]] = []
        for row in rows:
            if str(row.get("entity_type") or "").lower() != "product":
                continue
            code = row.get("canonical_code")
            if str(row.get("match_tier") or "").lower() == "exact":
                uuid = str(row.get("uuid") or code or "")
                if uuid and uuid not in resolved:
                    resolved[uuid] = row
            elif code and str(code) not in offers:
                # Recorded in `offers` as it is seen so the de-dupe is across TOKENS, the
                # way `_token_candidates`' uuid-keyed dedupe is, not per block.
                offers[str(code)] = row
                block.append(row)
        if block:
            blocks.append(dym_rows_per_token(block))
    did_you_mean = [row for block in blocks[:MISS_TOKEN_BLOCK_CAP] for row in block]
    return list(resolved.values()), did_you_mean


def _resolve_and_gate(db: Any):
    def call(ctx: Any, _item: Any = None) -> dict[str, Any]:
        """The turn's product, resolved by the BUSINESS LANE's resolver (H26).

        One round trip, the same body the business lane sends
        (`resolve_gate.resolve_entity_body`), through the same seam
        (`business.services.production_services(db).resolve_entity`) - which is the route
        function behind `POST /api/v1/system/references/resolve`, so the spec-search
        fallback and the brand stamp are the ones every other lane gets rather than a second
        resolver that drifts. The session is the lane's own, and it carries the contact's
        company scope (H56), which is the scope AC-1142 names.

        **The body this lane sends is NOT the business lane's body.** Four keys are
        overridden and one is dropped outright, because this lane reads exactly one field
        off the answer (`display.brand.brand_code`) and pays for everything else:

        * `understand_phrase: False` and `spec_fallback: False` - both put the customer's
          message in front of a model (phrase understanding, then a spec search) to find
          something a CODE would not match. An escalation turn's message is "ESCALATE TO
          MARKETING FOR <code>", so what that would understand is the verb and the team word,
          and any row it invented from them would then choose a brand, and through the brand a
          person. Codes only, and a code that matches nothing becomes the did-you-mean offer.
        * `query` - the product tokens, not the message. Same reason, plus it is the value the
          resolver scores and logs.
        * `match_mode: "or"` (finding 7, owner console re-pass, 13 Sep 2026, prompt v16).
          `resolve_entity_body`'s own default is `parse_output.match_mode or "and"`, so
          every lane call arrived in AND mode with a REAL escalation ctx - and AND mode has
          no exact tier at all: `references.py`'s AND path returns
          `{"intersection": [...], "by_entity_type": {...}}`, every row stamped
          `match_tier="and"` (`_and_probe_product`'s own note, "there is no exact tier on
          that path"), which has no `resolutions` key for `_product_rows` to read at all -
          so `resolved` and `did_you_mean` came back empty for every code, exact match or
          not, and `_carried_brand` / `_resolve_product` both saw `None` regardless of D10.
          Measured on the stack DB, scoped: SRTWB8004 under AND resolved nothing; under OR,
          `resolutions[0].matches` carries the one exact SORENTO row. AND's cross-token
          intersection is for compound phrases ("bidet seat cover for SRTWC60630-SH" as one
          claim); this lane sends ONLY product code tokens and reads ONE fact per token
          (`_product_tokens` already scopes the read that way), which is exactly OR's
          per-token view - so OR is not a workaround, it is the mode this lane's own body
          shape was always asking for.
        * `entity_pins` - DROPPED, not overridden (N4, reviewer review round 10).
          `resolve_entity_body` decides whether to attach pins off the mode IT computed
          (H38, `and` for a real escalation ctx - no pins), before this seam overrides the
          mode to `or` above; a turn whose PARSER already emitted `match_mode: "or"` would
          therefore have kept its pins, sending OR-with-pins on some turns and
          OR-without-pins on others - two shapes for the one body this docstring claims to
          send. A pin mismatch is a 400 `_resolve_product` degrades on, so it was harmless
          today, but harmless is not the same as one shape. This lane never wants pins - it
          asks about ONE code and reads ONE fact per token - so the key is dropped outright.

        `sub-resolve-and-gate`'s gate is deliberately NOT run over the answer. The gate's
        job is to decide which entity types a DOMAIN serves and to build the roster axes for
        an offer; an escalation turn has no domain of its own and is not offering a roster,
        and the one fact this lane needs is on the resolver rows already. Running the gate
        would add a probe (an MCP call) that nothing here reads.

        **The read runs in a SAVEPOINT, and that is what makes AC-1142 true.** This is the
        lane's own unit of work - the same session `next_assignee` draws the round robin on
        and `sla_create` writes the SLA row to. A database error inside the resolver leaves
        the enclosing transaction ABORTED, so catching it upstream
        (`escalation._resolve_product`) was not enough: the next statement on that session
        raises `PendingRollbackError` and the turn closes `failed` with nobody assigned,
        which is the opposite of "degrades to no brand". `begin_nested` rolls back to this
        point and re-raises, so the caller still degrades and the assignment still happens.
        """
        from app.services.chatbot.lanes.business.resolve_gate import resolve_entity_body
        from app.services.chatbot.lanes.business.services import production_services

        body = resolve_entity_body(ctx)
        wanted = _product_tokens(ctx, body)
        body = {
            **body,
            "query": " ".join(wanted),
            "spec_fallback": False,
            "understand_phrase": False,
            "match_mode": "or",
        }
        # N4 (reviewer, review round 10): `entity_pins` is decided by `resolve_entity_body`
        # off the mode IT computed (H38), not the one this seam overrides to above - a turn
        # whose parser already emitted `match_mode: "or"` left pins in the body, so the lane
        # sent OR-with-pins on some turns and OR-without on others, two shapes for the one
        # body this seam claims to send. This lane never wants pins: it asks about ONE code
        # and reads ONE fact per token (`_product_tokens`), never a pin-scoped
        # disambiguation, so the key is dropped outright rather than carried from whichever
        # mode happened to build it.
        body.pop("entity_pins", None)
        with db.begin_nested():
            payload = production_services(db).resolve_entity(body)
        resolved, did_you_mean = _product_rows(
            payload if isinstance(payload, dict) else {}, wanted
        )
        return {"resolved": resolved, "did_you_mean": did_you_mean}

    return call


def _not_live(name: str):
    def call(*_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError(
            f"{name} is not on the live escalation graph (bac9613b). It is in the seam for "
            "the B-HB-1 / B-TEAM-1' promotion; wiring it before that promotes would ship "
            "behaviour production has never run."
        )

    return call


@contextmanager
def production_session(session_factory: Any) -> Iterator[Any]:
    """A session owned for exactly one assignment, closed whatever happens.

    The first version called `SessionLocal()` and walked away: nothing closed it, so every
    escalation turn leaked a pooled connection, and a seam that raised left its transaction
    open on the way out - which on Postgres holds the round-robin cursor row's lock until
    the connection is recycled, so the NEXT escalation turn blocks behind a failure nobody
    is watching. Owning it here means the caller cannot forget.

    Rolls back on the way out of an exception: `run()` turns a seam failure into a failed
    turn with NO partial assignment, and a half-written unit of work in the database would
    contradict the trace the operator is reading.

    **The FACTORY is required, and it is the turn's own (H56).** The second version reached
    for `SessionLocal` directly, which is a session with NO company scope on it. The draw
    itself did not fail on that: `post_next_assignee` pins its own scope
    (`_scope_request_to_company`) before every `Team` / `AgentTeam` read. What DID run
    unscoped is the pre-pin half (`_routing_company_for_body`, which resolves which company
    is routing this contact) and this lane's own unit of work. Taking the turn's factory is
    defence in depth and, more usefully, ONE mechanism: the turn scopes every session it
    opens, instead of each callee remembering to pin its own. There is deliberately no
    `SessionLocal` fallback: a caller that forgets gets a loud failure rather than a session
    whose scope depends on which callee happens to pin it.
    """
    if session_factory is None:
        raise ValueError(
            "the escalation lane needs the turn's session factory (it carries the "
            "contact's company scope); pass `session_factory` down from `run_turn`"
        )

    db = session_factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def build(db: Any) -> EscalationServices:
    """The production bundle. `db` is the session the lane's writes run on.

    It is REQUIRED. The old default opened one here and left its lifecycle to nobody; the
    session now belongs to `production_session()`, whose `with` block is the unit of work.
    """
    return EscalationServices(
        resolve_and_gate=_resolve_and_gate(db),
        next_assignee=_next_assignee(db),
        preview_assignee=_preview_assignee(db),
        sla_create=_sla_create(db),
        team_members=_not_live("team_members"),
        staff_lookup=_staff_lookup(db),
    )
