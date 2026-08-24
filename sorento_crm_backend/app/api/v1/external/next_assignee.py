"""External endpoint for n8n: get next assignee by round-robin for (agent_id, team_id)."""
import logging
from typing import Any, NamedTuple, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.models.sla import SLAPolicy, SLAPolicyTier
from app.services.calendar_service import CalendarService
from app.services.company_routing_service import (
    DEFAULT_COMPANY_ID,
    RoutingCompany,
    resolve_routing_company,
)
from app.models.base import set_company_scope
from app.services.sla_service import ConversationSLATrackingService
from app.services.user_service import (
    AccessAgentService,
    normalise_brand_code,
    split_legacy_team_set_code,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_SLA_FIELDS_EMPTY = {
    "policy_id": None,
    "tier_response_hours": None,
    "tier_resolution_hours": None,
}


def _resolve_sla_policy_tier_for_next_assignee(
    db: Session, body: dict, company_id: Optional[str] = None
) -> dict:
    """
    When policy_code and tier are both sent, load SLA policy id and tier hour targets.
    When neither is sent, return nulls for those fields. If only one is sent, 400.

    Filtered by the resolved routing company. ``SLAPolicy`` is deliberately NOT a
    ``CompanyScopedMixin`` (see its docstring), so pinning the request scope does
    nothing for it and isolation has to be spelled out at each read. ``code`` is
    unique per company, not globally - NORMAL and PURCHASING each exist in two
    companies today - so an unfiltered read returned whichever row came back
    first, and with it another company's response/resolution hour targets.
    """
    policy_code = (body.get("policy_code") or body.get("sla_policy_code") or "").strip()
    tier_raw = body.get("tier") if "tier" in body else body.get("tier_level")

    if not policy_code and tier_raw is None:
        return dict(_SLA_FIELDS_EMPTY)
    if not policy_code or tier_raw is None:
        raise HTTPException(
            status_code=400,
            detail="policy_code and tier must both be provided together.",
        )
    try:
        tier_level = int(tier_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="tier must be an integer.")

    policy_q = db.query(SLAPolicy).filter(SLAPolicy.code == policy_code)
    if company_id:
        policy_q = policy_q.filter(SLAPolicy.company_id == str(company_id))
    policy = policy_q.order_by(SLAPolicy.created_at, SLAPolicy.id).first()
    if not policy:
        raise HTTPException(status_code=404, detail=f"No SLA policy found with code={policy_code!r}")

    tier_row = (
        db.query(SLAPolicyTier)
        .filter(
            SLAPolicyTier.policy_id == policy.id,
            SLAPolicyTier.tier_level == tier_level,
        )
        .first()
    )
    if not tier_row:
        raise HTTPException(
            status_code=404,
            detail=f"No tier {tier_level} for SLA policy code={policy_code!r}",
        )

    return {
        "policy_id": policy.id,
        "tier_response_hours": tier_row.response_hours,
        "tier_resolution_hours": tier_row.resolution_hours,
    }


def _format_assignee_response(result: dict) -> dict:
    return {
        "assignee_id": result.get("id"),
        "assignee_email": result.get("email"),
        "assignee_name": result.get("name"),
        "assignee_respond_user_id": result.get("respond_user_id"),
    }


def _tier_level_from_body(body: dict) -> Optional[int]:
    """Parse tier or tier_level from body; None if absent or invalid."""
    tier_raw = body.get("tier") if "tier" in body else body.get("tier_level")
    if tier_raw is None:
        return None
    try:
        return int(tier_raw)
    except (TypeError, ValueError):
        return None


class ResolvedTeam(NamedTuple):
    """What the team resolution decided, in n8n's terms.

    ``brand_code`` is the brand we were ASKED to route (normalised, or None). It does
    NOT pick the team - one team set has one team per tier - it narrows the member
    pool inside that team, so whether it actually matched anybody is only known after
    the round-robin draw and is reported separately.
    """

    team_id: str
    team_set_code: Optional[str]
    brand_code: Optional[str]


def _resolve_round_robin_team_id(
    service: AccessAgentService, agent_id: str, body: dict, *, company_id: str
) -> ResolvedTeam:
    """
    Resolve team_id for round-robin within ONE company and brand. Cursors are per
    (agent_id, team_id); the same team_code on multiple tiers must use tier (or
    tier_level) with team_code so we advance the correct team.

    Brand comes from ``brand_code`` in the body, falling back to the brand encoded in
    a legacy suffixed team-set code. The explicit field wins: it is what an updated
    n8n sends, and the suffix is only there so an un-updated one keeps working. It is
    carried through rather than used here - the team is brand-blind; the brand picks
    the members inside it.
    """
    brand_code = normalise_brand_code(body.get("brand_code"))

    team_id = body.get("team_id")
    if team_id is not None and str(team_id).strip():
        return ResolvedTeam(str(team_id).strip(), None, brand_code)

    team_code = body.get("team_code") or body.get("team")
    code = body.get("code")
    code_eff = (str(team_code).strip() if team_code else "") or (str(code).strip() if code else "")
    if not code_eff:
        raise HTTPException(
            status_code=400,
            detail="team_id, team_code, or code is required.",
        )
    base_code, suffix_brand = split_legacy_team_set_code(code_eff)
    brand_code = brand_code or suffix_brand

    tier_level = _tier_level_from_body(body)
    if tier_level is not None:
        tid = service.get_team_id_by_tier(
            agent_id, tier_level, team_set_code=base_code, company_id=company_id
        )
        if tid:
            return ResolvedTeam(tid, base_code, brand_code)

    ids = service.list_team_ids_for_agent_code(agent_id, base_code, company_id=company_id)
    if len(ids) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"team_code={base_code!r} is linked to multiple teams for this agent (e.g. SLA tiers). "
                "Send tier (or tier_level) together with team_code so the correct round-robin pool is used."
            ),
        )
    if len(ids) == 1:
        return ResolvedTeam(ids[0], base_code, brand_code)

    # Naming the company matters: without it this reads as "the agent is misconfigured"
    # when the real cause is that this company has no team for that code yet (AC-C5).
    raise HTTPException(
        status_code=404,
        detail=(
            f"No team found for agent and team_code={base_code!r} in company "
            f"{company_id!r}. Configure that company's team set before routing to it."
        ),
    )


def _user_field(user: Any, name: str) -> Any:
    """Read attribute; prefer instance __dict__ so detached / test User instances work."""
    d = getattr(user, "__dict__", None)
    if isinstance(d, dict) and name in d:
        return d.get(name)
    return getattr(user, name, None)


def _user_to_conversation_assignee_payload(user: Any) -> dict:
    return {
        "conversation_assignee_id": _user_field(user, "id"),
        "conversation_assignee_email": _user_field(user, "email"),
        "conversation_assignee_name": _user_field(user, "name"),
        "conversation_assignee_respond_user_id": _user_field(user, "respond_user_id"),
    }


def _conversation_assignee_from_tracking(tracking: Optional[Any], db: Session) -> dict:
    """
    CRM conversation assignee (SLA tracking), distinct from round-robin assignee_* fields.
    When tracking has no assignee, all fields are None.
    """
    empty = {
        "conversation_assignee_id": None,
        "conversation_assignee_email": None,
        "conversation_assignee_name": None,
        "conversation_assignee_respond_user_id": None,
    }
    if tracking is None:
        return empty

    from app.models.user import User

    au = getattr(tracking, "assigned_user", None)
    if au is not None and isinstance(au, User):
        return _user_to_conversation_assignee_payload(au)

    aid = getattr(tracking, "assigned_to_id", None)
    if aid:
        user = db.query(User).filter(User.id == aid).first()
        if user is not None and isinstance(user, User):
            return _user_to_conversation_assignee_payload(user)

    at = getattr(tracking, "assigned_to", None)
    if not isinstance(at, str) or not str(at).strip():
        return empty
    s = str(at).strip()

    user = db.query(User).filter(User.id == s).first()
    if user is not None and isinstance(user, User):
        return _user_to_conversation_assignee_payload(user)
    user = db.query(User).filter(User.respond_user_id == s).first()
    if user is not None and isinstance(user, User):
        return _user_to_conversation_assignee_payload(user)
    user = db.query(User).filter(User.email == s).first()
    if user is not None and isinstance(user, User):
        return _user_to_conversation_assignee_payload(user)

    # Legacy text only: often respond.io user id; may be email or display string
    out = {**empty}
    if "@" in s:
        out["conversation_assignee_email"] = s
    else:
        out["conversation_assignee_respond_user_id"] = s
    return out


def _tracking_is_assigned(tracking: Any) -> bool:
    """True if SLA tracking row has an assignee at CRM (user id and/or legacy respond id string)."""
    if tracking is None:
        return False
    if getattr(tracking, "assigned_to_id", None):
        return True
    at = getattr(tracking, "assigned_to", None)
    if at is None:
        return False
    if isinstance(at, str):
        return bool(at.strip())
    return True


def _routing_company_for_body(db: Session, body: dict, contact_phone: str) -> RoutingCompany:
    """Resolve the routing company, degrading to Sorento on ANY failure (AC-J1).

    ``resolve_routing_company`` already swallows its own errors; this second net is
    here because routing must survive even an import-time / signature-level breakage
    of the resolver. A conversation nobody is assigned is worse than a wrong company.
    """
    try:
        return resolve_routing_company(
            db,
            company_id=body.get("company_id"),
            company_code=body.get("company_code"),
            contact_id=body.get("contact_id") or body.get("respond_io_id"),
            space_id=body.get("space_id"),
            phone=contact_phone,
        )
    except Exception:
        logger.warning("next-assignee: routing company resolution failed", exc_info=True)
        return RoutingCompany(
            company_id=DEFAULT_COMPANY_ID, company_code=None, source="default"
        )


def _scope_request_to_company(db: Session, routing_company: RoutingCompany) -> None:
    """Pin the rest of this request to the COALESCED routing company (AC-F3).

    Deliberately the coalesced company, never the contact's raw company set: an
    untagged contact coalesces to Sorento here, whereas the request-entry scope
    resolver would give it ``frozenset()`` = zero rows and strand the call. That
    difference is the whole reason routing has its own resolver (D6).
    """
    try:
        set_company_scope(db, frozenset({str(routing_company.company_id)}))
    except Exception:
        logger.warning("next-assignee: could not pin request company scope", exc_info=True)


def _enrich_n8n_response(
    base: dict,
    *,
    is_working_hours: bool,
    is_already_assigned: bool,
    conversation_assignee: Optional[dict] = None,
    sla_policy_tier: Optional[dict] = None,
    routing_company: Optional[RoutingCompany] = None,
    resolved_team: Optional["ResolvedTeam"] = None,
    brand_matched: bool = False,
) -> dict:
    status_flags: list[str] = []
    if not is_working_hours:
        status_flags.append("non_working_hours")
    if is_already_assigned:
        status_flags.append("already_assigned")
    if routing_company is not None and routing_company.ambiguous:
        status_flags.append("ambiguous_company")

    if is_working_hours and not is_already_assigned:
        message = "Within working hours; conversation not yet assigned in CRM."
    elif is_working_hours and is_already_assigned:
        message = "Within working hours; conversation already has an assignee in CRM (use comment flow)."
    elif not is_working_hours and not is_already_assigned:
        message = "Outside working hours (Asia/Kuala_Lumpur); queue for later; round-robin assignee included."
    else:
        message = (
            "Outside working hours (Asia/Kuala_Lumpur) and conversation already has an assignee in CRM; "
            "queue and use comment flow as needed."
        )

    out = {**base}
    if sla_policy_tier is not None:
        out.update(sla_policy_tier)
    if routing_company is not None:
        out["company_id"] = routing_company.company_id
        out["company_code"] = routing_company.company_code
        out["company_source"] = routing_company.source
    if resolved_team is not None:
        out["team_set_code"] = resolved_team.team_set_code
        out["brand_code"] = resolved_team.brand_code
        # Per assignee: true only when the member DRAWN carries that brand tag. An
        # untagged serve-all member drawn from the same pool reports false, which is
        # the difference between "the brand specialist has it" and "somebody who
        # serves every brand has it".
        out["brand_matched"] = bool(resolved_team.brand_code) and brand_matched
    out["is_working_hours"] = is_working_hours
    out["is_already_assigned"] = is_already_assigned
    out["status_flags"] = status_flags
    out["message"] = message
    if conversation_assignee is not None:
        out.update(conversation_assignee)
    return out


@router.post("")
async def post_next_assignee(
    body: dict,
    current_user: dict = Depends(get_external_api_user),
    db=Depends(get_db),
):
    """
    Return the next eligible assignee for the given agent and team (round-robin).
    contact_phone_number is required. Each call advances this team's round-robin cursor only
    (independent of other tiers and of who is on the conversation).

    Response always includes assignee fields plus:
    - is_working_hours: True if now is within configured working calendar in Asia/Kuala_Lumpur
    - is_already_assigned: True if latest SLA tracking for this phone has an assignee in CRM
    - status_flags: e.g. ["non_working_hours"], ["already_assigned"], or both
    - message: human-readable hint for n8n (queue vs assign vs comment)
    - conversation_assignee_*: CRM assignee on the SLA tracking row (when already assigned);
      distinct from assignee_* (round-robin). All null when not assigned.
    - policy_id, tier_response_hours, tier_resolution_hours: set when policy_code and tier are sent;
      otherwise null.

    Body (required): contact_phone_number or contact_phone.
    Body (agent/team): agent_id/agent_code/agent and team_id/team_code/team or code.
    Body (optional): tier (or tier_level) with team_code when the same code is used for more than one
      SLA tier - required in that case so round-robin matches the UI per-tier cursors.
    Body (ignored): current_assignee - backward compatibility only; does not affect rotation.
      Tiers are independent; use conversation_assignee_* in the response for CRM state only.
    Body (optional): policy_code (or sla_policy_code) and tier (or tier_level) together  - 
      response includes policy_id, tier_response_hours, tier_resolution_hours from that SLA tier.
    Body (optional): brand_code - the brand this item belongs to (lower-case
      `brands.brand_code`; blank / absent = unknown). The team is unchanged; the
      round-robin pool inside it narrows to members tagged with that brand plus
      members tagged with none. Nobody tagged for it -> the whole team. The response
      echoes brand_code, brand_matched and team_set_code.
    Body (optional): company_id - a companies.id that overrides the contact-derived
      company (company_source becomes "body"). An unknown id is ignored.
    Body (optional): preferred_assignee_id - when set to a valid member (user_id) of the resolved
      team, that member is returned directly and the round-robin cursor is NOT advanced. Discover
      valid ids via GET /external/team-members. 404 if not a member of the team.

    Example:
      { "contact_phone_number": "+60123456789", "agent_code": "general_enquiries", "team_code": "marketing" }
      Tiered agent:
      { "contact_phone_number": "+60...", "agent_code": "purchasing", "team_code": "project_sales", "tier": 2 }
    """
    contact_phone = (body.get("contact_phone_number") or body.get("contact_phone") or "").strip()
    if not contact_phone:
        raise HTTPException(
            status_code=400,
            detail="contact_phone_number (or contact_phone) is required.",
        )

    # S0: resolved and echoed, but team resolution is deliberately NOT keyed on it yet.
    routing_company = _routing_company_for_body(db, body, contact_phone)
    _scope_request_to_company(db, routing_company)

    sla_policy_tier = _resolve_sla_policy_tier_for_next_assignee(
        db, body, getattr(routing_company, "company_id", None)
    )

    calendar = CalendarService(db)
    is_working_hours = calendar.is_within_working_time()

    sla_service = ConversationSLATrackingService(db)
    tracking: Optional[Any] = sla_service.get_tracking_by_contact_phone(contact_phone)
    is_already_assigned = _tracking_is_assigned(tracking)
    conversation_assignee = (
        _conversation_assignee_from_tracking(tracking, db)
        if is_already_assigned
        else {
            "conversation_assignee_id": None,
            "conversation_assignee_email": None,
            "conversation_assignee_name": None,
            "conversation_assignee_respond_user_id": None,
        }
    )

    # Accept client-friendly names: agent -> agent_code, team -> team_code
    agent_id = body.get("agent_id")
    agent_code = body.get("agent_code") or body.get("agent")

    service = AccessAgentService(db)

    # Resolve agent_id from agent_code if provided
    if agent_code and not agent_id:
        agent_id = service.get_agent_id_by_code(agent_code)
        if not agent_id:
            raise HTTPException(status_code=404, detail=f"No agent found with code={agent_code!r}")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id or agent_code is required")

    resolved_team = _resolve_round_robin_team_id(
        service, str(agent_id).strip(), body, company_id=routing_company.company_id
    )
    team_id = resolved_team.team_id

    # Preferred-assignee override: skip round-robin, go straight to the named member.
    # n8n discovers valid ids via GET /external/team-members. Cursor is NOT advanced.
    preferred_id = body.get("preferred_assignee_id")
    if preferred_id is not None and str(preferred_id).strip():
        preferred_id = str(preferred_id).strip()
        result = service.get_member_assignee(
            team_id, preferred_id, brand_code=resolved_team.brand_code
        )
        if result is None:
            # The team was resolved inside the routing company, so "not a member"
            # also covers "is a member of the OTHER company's team" (AC-D3). Naming
            # the company is what makes that case diagnosable from the n8n log.
            raise HTTPException(
                status_code=404,
                detail=(
                    f"preferred_assignee_id={preferred_id!r} is not a member of the "
                    f"resolved team for company {routing_company.company_id!r}."
                ),
            )
    else:
        # Market-segment scoping. Identity is contact_id when n8n sends one, else the
        # phone it always sends (AC-B1) - keying on contact_id alone left the filter
        # dead on the only path production actually uses. An untagged / unknown
        # contact still resolves to no segments, i.e. the unfiltered '' cursor.
        from app.services.market_segment_service import MarketSegmentService

        contact_ref = body.get("contact_id") or body.get("respond_io_id")
        resolved = MarketSegmentService(db).resolve_contact_segments(
            respond_io_id=str(contact_ref).strip() if contact_ref else None,
            space_id=body.get("space_id"),
            phone=contact_phone,
        )
        contact_segments: Optional[set[str]] = resolved or None
        result = service.get_next_assignee(
            agent_id,
            team_id,
            contact_segments,
            brand_code=resolved_team.brand_code,
        )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No assignee found. Ensure the agent is linked to the team and the team has members.",
        )
    return _enrich_n8n_response(
        _format_assignee_response(result),
        is_working_hours=is_working_hours,
        is_already_assigned=is_already_assigned,
        conversation_assignee=conversation_assignee,
        sla_policy_tier=sla_policy_tier,
        routing_company=routing_company,
        resolved_team=resolved_team,
        brand_matched=bool(result.get("brand_matched")),
    )
