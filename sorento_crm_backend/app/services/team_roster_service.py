"""The active roster of a routing team, resolved the way next-assignee resolves it.

Extracted from `app/api/v1/external/team_members.py` at S2 so it has TWO callers: the
external endpoint n8n still uses, and the chatbot tail, which builds the numbered CS
escalation offer in process instead of over HTTP (D1: the HTTP hop was transport).

**Why an extraction and not a second implementation.** The endpoint's own docstring says
it: an id offered here must always be accepted by `/external/next-assignee`, which means
the company, the market segments and the brand pool have to be resolved by the SAME code
in both places. Two spellings of that rule is how a roster starts offering staff the
assign endpoint then rejects.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.base import set_company_scope
from app.services.company_routing_service import resolve_routing_company
from app.services.market_segment_service import MarketSegmentService
from app.services.user_service import AccessAgentService


def list_team_roster(
    db: Session,
    *,
    team_code: Optional[str] = None,
    team_id: Optional[str] = None,
    agent_code: Optional[str] = None,
    agent_id: Optional[str] = None,
    tier: Optional[int] = None,
    contact_id: Optional[str] = None,
    space_id: Optional[str] = None,
    contact_phone_number: Optional[str] = None,
    company_code: Optional[str] = None,
    company_id: Optional[str] = None,
    brand_code: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Active members of the resolved team: `[{user_id, name, respond_user_id, email, sort_order}]`.

    Raises `HTTPException` for an unknown agent code or an unresolvable team, which is
    what the endpoint surfaces and what the chatbot's roster fetch degrades on (n8n's
    `onError: continueRegularOutput`, one company's failure never costs the whole offer).

    **`HTTPException` from a SERVICE is parity, not the pattern.** The layering rule
    says a service raises `AppException` and lets the global handler serialise it; this
    raises what the ROUTE raised before the extraction, byte for byte, so the endpoint's
    404 and 400 bodies cannot move under a refactor that was supposed to change nothing.
    Swap both to `AppException` at S8, with those response bodies asserted first.
    """
    # LOCAL on purpose, and the only one: `_resolve_round_robin_team_id` still lives in
    # the next-assignee ROUTER, so importing it at module level would make a service
    # import an api module at import time. Moving it out is the right fix and is a
    # different change from this extraction; until then the cycle is broken here rather
    # than pretended away.
    from app.api.v1.external.next_assignee import _resolve_round_robin_team_id

    service = AccessAgentService(db)

    # Resolve agent_id from agent_code (needed when resolving a team via team_code).
    resolved_agent_id = agent_id
    if agent_code and not resolved_agent_id:
        resolved_agent_id = service.get_agent_id_by_code(agent_code)
        if not resolved_agent_id:
            raise HTTPException(status_code=404, detail=f"No agent found with code={agent_code!r}")

    # team_id given directly -> no agent needed; the team_code path needs agent_id.
    if not (team_id and str(team_id).strip()) and not resolved_agent_id:
        raise HTTPException(
            status_code=400,
            detail="agent_id or agent_code is required to resolve team_code (or pass team_id directly).",
        )

    # Same resolution as next-assignee, so an id returned here is always accepted there
    # (AC-E1). Resolving the company differently in the two would hand a roster from one
    # company and reject those ids from the other.
    routing_company = resolve_routing_company(
        db,
        company_id=company_id,
        company_code=company_code,
        contact_id=contact_id,
        space_id=space_id,
        phone=contact_phone_number,
    )
    set_company_scope(db, frozenset({routing_company.company_id}))

    resolved = _resolve_round_robin_team_id(
        service,
        str(resolved_agent_id).strip() if resolved_agent_id else "",
        {"team_id": team_id, "team_code": team_code, "tier": tier},
        company_id=routing_company.company_id,
    )

    # Market-segment filter. Unknown / untagged contact -> empty set -> no filter.
    contact_segments = MarketSegmentService(db).resolve_contact_segments(
        respond_io_id=contact_id, space_id=space_id, phone=contact_phone_number
    )
    # Brand narrows the roster by the rule next-assignee applies to the round-robin pool:
    # tagged with it, or tagged with nothing. The explicit param wins, falling back to the
    # brand a legacy suffixed team_code encodes - without that fallback an un-updated
    # caller gets the whole team here and the brand pool there, and the id it picks is one
    # next-assignee never had.
    return service.list_active_team_members_detail(
        resolved.team_id,
        contact_segments or None,
        brand_code=brand_code or resolved.brand_code,
    )
