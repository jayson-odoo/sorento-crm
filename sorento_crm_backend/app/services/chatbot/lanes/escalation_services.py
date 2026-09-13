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


def _product_rows(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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

    Product rows only: an escalation turn commonly names a category beside the code ("BIDET
    SEAT COVER FOR SRTWC60630-SH") and a category has no brand to route by. De-duplicated by
    uuid on the resolved side and by code on the offer side, which is what the customer can
    tell apart on screen.

    **The OFFER side carries the business lane's own caps**, because AC-1124 says these are
    "the business lane's did-you-mean rows" and a numbered list nobody can read is not an
    offer. `lanes/business/miss_suggest._cap3` is three candidates per token and
    `_dym_plan`'s `d1s = d1s[:5]` is five token blocks, so the resolver's 15 matches per
    token over several tokens (75 rows on a five-token message) become at most 15 numbered
    lines, in the resolver's own ranking. `_cap3` is imported rather than re-spelled so the
    number cannot drift from the lane it is copied from; the block cap is a constant here
    beside it, with its source named, because `_dym_plan` holds it as a literal inside a
    500-line planner this lane does not run.

    The RESOLVED side is not capped: it decides the brand, and "exactly one row" is the
    test the lane makes on it (`escalation._resolve_product`), so dropping a row there would
    change a routing decision rather than shorten a list.
    """
    from app.services.chatbot.lanes.business.miss_suggest import _cap3

    resolved: dict[str, dict[str, Any]] = {}
    offers: dict[str, dict[str, Any]] = {}
    blocks: list[list[dict[str, Any]]] = []
    for resolution in (payload or {}).get("resolutions") or []:
        if not isinstance(resolution, dict):
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
            blocks.append(_cap3(block))
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
        with db.begin_nested():
            payload = production_services(db).resolve_entity(body)
        resolved, did_you_mean = _product_rows(payload if isinstance(payload, dict) else {})
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
