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
| (B-HB-1, not live) | `resolve_and_gate` | S6a's `business.run_until_exit` |
| (the member roster) | `team_members` | `app.api.v1.external.team_members` |
| (new, 6 Sep 2026) | `staff_lookup` | `users` x `team_members` x `agent_teams`, read here |

Every test in `test_s5_escalation_lane.py` injects its own `services`, which is the point
of the seam; `test_s5_escalation_seams.py` covers THIS module - the wiring that runs once
the owner adds `out_of_scope` to `system_settings.chatbot_completed_lanes` - with the two
CRM services stubbed at their own boundary, because a seam nothing ever executes is where
a typo waits for production.

`team_members` is declared and NOT wired. It is not spare machinery: `test_no_hard_default_
team` (xfail `strict=True`) names it as the roster read the B-TEAM-1' promotion needs, and
the field is what its stub duck-types against. Like `resolve_and_gate` it raises rather
than half-working, so promoting the build without wiring it is a loud failure.
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
    """One bundle, four callables. `resolve_and_gate` is never called on the live graph."""

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
        resolve_and_gate=_not_live("resolve_and_gate"),
        next_assignee=_next_assignee(db),
        preview_assignee=_preview_assignee(db),
        sla_create=_sla_create(db),
        team_members=_not_live("team_members"),
        staff_lookup=_staff_lookup(db),
    )
