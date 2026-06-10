"""Per-salesman → CS PIC pin-point routing (procurement form-SLA CS stage).

Admin pins a salesman (respond_contact) to a specific customer-service PIC for a
procurement use_case. At CS-stage spawn the form-SLA resolver consults these pins
(see ``form_sla_service._resolve_pinned_assignee``); a valid pin overrides
round-robin. Candidates are the tier-1 members of the ``customer_service`` team
under the ``purchase_request`` access agent.

See docs/plans/PLAN-procurement-cs-handoff-and-pinpoint-routing.md.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact, RespondContactCsRouting, TeamMember
from app.models.user import User
from app.services.error_handler import (
    handle_not_found,
    handle_validation_error,
)

# The access agent + team_set that owns the procurement customer-service team.
CS_AGENT_CODE = "purchase_request"
CS_TEAM_SET_CODE = "customer_service"
PINNABLE_USE_CASES = ("purchase_request", "sponsorship_form")


class CsRoutingService:
    """Manage salesman → CS PIC pins and resolve the CS candidate pool."""

    def __init__(self, db: Session):
        self.db = db

    # ---- candidate pool ----------------------------------------------------

    def _cs_team_id(self) -> Optional[str]:
        """Resolve the tier-1 team_id of the procurement customer-service team."""
        from app.services.user_service import AccessAgentService

        agent_svc = AccessAgentService(self.db)
        agent_id = agent_svc.get_agent_id_by_code(CS_AGENT_CODE)
        if not agent_id:
            return None
        return agent_svc.get_team_id_by_tier(
            agent_id, 1, team_set_code=CS_TEAM_SET_CODE
        )

    def list_candidates(self) -> list[dict]:
        """Tier-1 members of the procurement customer-service team (for the dropdown).

        Returns an empty list (not an error) when the agent/team is not configured
        yet, so the FE renders a "no CS team configured" empty state.
        """
        team_id = self._cs_team_id()
        if not team_id:
            return []
        members = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id)
            .order_by(TeamMember.sort_order.asc().nullslast(), TeamMember.user_id.asc())
            .all()
        )
        user_ids = [m.user_id for m in members]
        if not user_ids:
            return []
        users = {
            u.id: u
            for u in self.db.query(User).filter(User.id.in_(user_ids)).all()
        }
        out: list[dict] = []
        for uid in user_ids:
            u = users.get(uid)
            if not u:
                continue
            out.append(
                {"id": u.id, "name": (u.name or u.email), "email": u.email}
            )
        return out

    def _candidate_ids(self) -> set[str]:
        return {c["id"] for c in self.list_candidates()}

    # ---- pin CRUD ----------------------------------------------------------

    def _require_contact(self, contact_id: str) -> RespondContact:
        contact = (
            self.db.query(RespondContact)
            .filter(RespondContact.id == contact_id)
            .first()
        )
        if not contact:
            raise handle_not_found("Contact", contact_id)
        return contact

    def list_for_contact(self, contact_id: str) -> list[dict]:
        """All active pins for a contact, with the CS PIC's display name."""
        self._require_contact(contact_id)
        rows = (
            self.db.query(RespondContactCsRouting)
            .filter(
                RespondContactCsRouting.respond_contact_id == contact_id,
                RespondContactCsRouting.is_active.is_(True),
            )
            .all()
        )
        if not rows:
            return []
        users = {
            u.id: u
            for u in self.db.query(User)
            .filter(User.id.in_([r.cs_pic_user_id for r in rows]))
            .all()
        }
        out: list[dict] = []
        for r in rows:
            u = users.get(r.cs_pic_user_id)
            out.append(
                {
                    "use_case": r.use_case,
                    "cs_pic_user_id": r.cs_pic_user_id,
                    "cs_pic_name": (u.name or u.email) if u else None,
                }
            )
        return out

    def upsert(
        self,
        contact_id: str,
        use_case: str,
        cs_pic_user_id: str,
        *,
        created_by: Optional[str] = None,
    ) -> RespondContactCsRouting:
        """Pin (or re-pin) a salesman to a CS PIC for one use_case.

        Validates the use_case and that the CS PIC is a current member of the
        procurement customer-service team (D5: pin must be a valid team member).
        """
        self._require_contact(contact_id)
        if use_case not in PINNABLE_USE_CASES:
            raise handle_validation_error(
                f"use_case must be one of {PINNABLE_USE_CASES}; got {use_case!r}."
            )
        if cs_pic_user_id not in self._candidate_ids():
            raise handle_validation_error(
                "Selected user is not a member of the customer-service team "
                "(purchase_request agent, tier 1). Add them to the team first."
            )
        row = (
            self.db.query(RespondContactCsRouting)
            .filter(
                RespondContactCsRouting.respond_contact_id == contact_id,
                RespondContactCsRouting.use_case == use_case,
            )
            .first()
        )
        if row:
            row.cs_pic_user_id = cs_pic_user_id
            row.is_active = True
        else:
            row = RespondContactCsRouting(
                respond_contact_id=contact_id,
                use_case=use_case,
                cs_pic_user_id=cs_pic_user_id,
                is_active=True,
                created_by=created_by,
            )
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, contact_id: str, use_case: str) -> None:
        """Clear a pin → that use_case reverts to round-robin. Idempotent."""
        self._require_contact(contact_id)
        row = (
            self.db.query(RespondContactCsRouting)
            .filter(
                RespondContactCsRouting.respond_contact_id == contact_id,
                RespondContactCsRouting.use_case == use_case,
            )
            .first()
        )
        if row:
            self.db.delete(row)
            self.db.commit()
