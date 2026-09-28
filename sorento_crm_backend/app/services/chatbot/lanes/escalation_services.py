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
| (new, 27 Sep 2026, #865) | `product_brand` | `products` x `brands` x `companies`, read here (`focus_product_origin`) |
| (new, 28 Sep 2026, #865 round 5) | `product_suggestions` | the resolver's trigram did-you-mean (`entity_resolver._trgm_lookup`), in the contact's scope |

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
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

logger = logging.getLogger(__name__)


def _iso(value: Any) -> Any:
    """`escalation.py::_comment_text` reads `_sla_create`'s three timestamp fields
    through `_malaysia`, which calls `jsc.js_string` on whatever it is handed - a
    `datetime` is not one of `js_string`'s known types, so it rendered JS's own
    `[object Object]` in the SLA comment (owner ruling 22 Sep 2026). ISO-8601 strings
    round-trip through `_malaysia`'s own `datetime.fromisoformat` exactly like the
    stubbed test doubles always have."""
    return value.isoformat() if isinstance(value, datetime) else value


@dataclass(frozen=True)
class EscalationServices:
    """One bundle, four callables. `resolve_and_gate` is never called on the live graph."""

    resolve_and_gate: Any
    next_assignee: Any
    preview_assignee: Any
    sla_create: Any
    team_members: Any
    staff_lookup: Any
    # #865 (owner ruling 27 Sep 2026, fix option 1): the brand of the product the
    # escalation is about, read off the product row. Defaulted so an older injected
    # bundle keeps working and simply resolves no brand, exactly as before.
    product_brand: Any = None
    # #865 round 5: the did-you-mean for a product code no company holds, so a typo is
    # settled inside the escalation. Defaulted for the same reason as `product_brand`.
    product_suggestions: Any = None


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
            "initiated_at": _iso(getattr(created, "initiated_at", None)),
            "due_at": _iso(getattr(created, "due_at", None)),
            "due_at_resolution": _iso(getattr(created, "due_at_resolution", None)),
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


def _product_refs(products: Any) -> tuple[set[str], set[str]]:
    """`(uuids, upper-cased codes)` off focus product entries. A settled entry names its
    row by `uuid`; an unsettled one only by its code (`canonical_code`, else `raw`)."""
    uuids: set[str] = set()
    codes: set[str] = set()
    for entry in products or []:
        if not isinstance(entry, dict):
            continue
        hint = entry.get("hint")
        if hint not in (None, "product"):
            continue
        uid = entry.get("uuid")
        if isinstance(uid, str) and uid.strip():
            try:
                uuids.add(str(uuid.UUID(uid.strip())))
                continue
            except ValueError:
                pass  # not a row id; fall through to the code, as an unsettled entry
        code = entry.get("canonical_code") or entry.get("raw")
        if isinstance(code, str) and code.strip():
            codes.add(code.strip().upper())
    return uuids, codes


def _company_brand(name: Any, code: Any) -> str | None:
    """The brand a company's name stands for, or None (fix round 4).

    The Mocha company sells only the MOCHA brand, and its rows carry no brand row, so
    the company is the brand. The incumbent Sorento company is not: it carries several
    brands (SORENTO, MOCHA), so a Sorento row without a brand row names none, as before.
    Keyed off `escalation.CO_ALIASES`, the lane's own company vocabulary.
    """
    from app.services.chatbot.lanes.escalation import CO_ALIASES

    keys = {str(v).strip().lower() for v in (name, code) if v}
    for brand, aliases in CO_ALIASES.items():
        if brand != "sorento" and keys & {brand, *aliases}:
            return brand
    return None


def focus_product_origin(db: Any, products: Any) -> dict[str, Any]:
    """`{brand, company, not_found}` for the product(s) the conversation is about (#865).

    The brand is a fact the product row owns, so it is read here at the point of use rather
    than persisted beside the product in the session (contract 129 keeps the five-key wire
    shape byte-compatible). One brand is the answer; products that disagree name none,
    because a guess there picks a person for the wrong brand. Lower-cased, the spelling
    `next-assignee` narrows by.

    Fix round 4 (the owner's rule, 27 Sep: every Mocha company item and every Mocha-brand
    product in Sorento goes to the Mocha brand member, whichever company the customer is
    talking to): a code is looked for in the contact's own company first, and only a code
    found nowhere there is looked for across every company. A row's brand is its brand
    row, else the brand its company stands for (`_company_brand`). This read is for
    routing only; stock, prices and orders keep the turn's company scope, and so does this
    session once the read is done. `company` names where the rows were found and
    `not_found` lists the codes no company holds.
    """
    empty: dict[str, Any] = {"brand": None, "company": None, "not_found": []}
    uuids, codes = _product_refs(products)
    if not uuids and not codes:
        return empty
    from sqlalchemy import func

    from app.models.base import company_scope
    from app.models.company import Company
    from app.models.product import Brand, Product
    from app.services.entity_resolver import _prefix_probe_product, _probe_product

    def find(code: str) -> set[str]:
        hits = _probe_product(db, [code]).get(code) or _prefix_probe_product(db, code)
        return {str(hit.uuid) for hit in hits if hit.uuid}

    not_found: list[str] = []
    # A savepoint, so a read that fails aborts only itself and never the caller's unit of
    # work (the turn's, or the lane's own before it draws an assignee).
    with db.begin_nested():
        # An unsettled entry holds the token the customer typed ("srtwc286"), not the
        # row's code (SRTWC286-SH): a domain that does not narrow on product never
        # settles it (fix round 3, the owner's 27 Sep console retest). Its rows are the
        # ones the resolver matched for the answer, so they are found by the resolver's
        # own code tiers: exact, else prefix, else substring.
        for code in sorted(codes):
            found = find(code)
            if not found:
                with company_scope(db, None):
                    found = find(code)
            if not found:
                not_found.append(code)
            uuids.update(found)
        if not uuids:
            return {**empty, "not_found": not_found}
        with company_scope(db, None):
            rows = (
                db.query(func.lower(Brand.brand_code), Company.name, Company.code)
                .select_from(Product)
                .outerjoin(Brand, Brand.id == Product.brand_id)
                .join(Company, Company.id == Product.company_id)
                .filter(Product.id.in_(sorted(uuids)))
                .distinct()
                .all()
            )
    brands = sorted(
        {
            str(brand).strip() if brand and str(brand).strip() else _company_brand(name, company_code)
            for brand, name, company_code in rows
        }
        - {None}
    )
    companies = sorted({str(name) for _brand, name, _code in rows if name})
    return {
        "brand": brands[0] if len(brands) == 1 else None,
        "company": " and ".join(companies) or None,
        "not_found": not_found,
    }


def focus_product_brand(db: Any, products: Any) -> str | None:
    """The brand alone of `focus_product_origin`, for the offer mint sites (#865)."""
    return focus_product_origin(db, products)["brand"]


def _product_brand(db: Any):
    def call(products: Any) -> dict[str, Any]:
        return focus_product_origin(db, products)

    return call


#: How many codes the escalation's did-you-mean offers: the product lane's own "did you
#: mean A, B, or C" length.
SUGGESTIONS_CAP = 3


def product_suggestions(db: Any, code: str) -> list[str]:
    """The product codes the resolver offers for a code it cannot place (#865 round 5).

    The same did-you-mean the product lane shows: `entity_resolver._trgm_lookup`, the
    trigram neighbours `resolve()` turns into a token's alternatives, floored at
    `ENTITY_MISS_SUGGEST_FLOOR`. It runs on the lane's session, so it is scoped to the
    contact's companies exactly as the product lane's is: a customer is never shown a
    code their companies do not hold. Best effort inside a savepoint; a failed probe
    offers nothing and the escalation goes out as before.
    """
    from app.services.entity_resolver import ENTITY_MISS_SUGGEST_FLOOR, _trgm_lookup

    with db.begin_nested():
        hits = _trgm_lookup(db, code, frozenset({"product"}))
    codes: list[str] = []
    for hit in hits:
        if hit.entity_type != "product" or (hit.similarity or 0.0) < ENTITY_MISS_SUGGEST_FLOOR:
            continue
        found = str(hit.canonical_code or "").strip()
        if found and found not in codes:
            codes.append(found)
    return codes[:SUGGESTIONS_CAP]


def _product_suggestions(db: Any):
    def call(code: str) -> list[str]:
        return product_suggestions(db, code)

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
        product_brand=_product_brand(db),
        product_suggestions=_product_suggestions(db),
    )
