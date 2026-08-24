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


def _normalized_conditions(match_conditions: Optional[list]) -> list:
    """Validate + shape an incoming predicate list to [{field, operator, value}].

    Rejects unknown operators and malformed predicates (422). An empty/None list is
    the wildcard []. Field/value are stored as-is (strings); type-appropriate
    operators are enforced in the UI, but the operator vocabulary is enforced here."""
    from app.services.cs_routing_match import VALID_OPERATORS

    if not match_conditions:
        return []
    out: list[dict] = []
    for i, pred in enumerate(match_conditions):
        if not isinstance(pred, dict):
            raise handle_validation_error(f"match_conditions[{i}] must be an object.")
        field = pred.get("field")
        operator = pred.get("operator")
        value = pred.get("value")
        if not field or not isinstance(field, str):
            raise handle_validation_error(f"match_conditions[{i}].field is required.")
        if operator not in VALID_OPERATORS:
            raise handle_validation_error(
                f"match_conditions[{i}].operator must be one of {VALID_OPERATORS}; "
                f"got {operator!r}."
            )
        out.append({"field": field, "operator": operator, "value": value})
    # Store in canonical (sorted) order so the DB unique index
    # md5(match_conditions::text) is deterministic per logical condition-set  - 
    # matching app-side canonical_conditions (predicate order is not semantic; AND).
    out.sort(key=lambda c: (str(c["field"]), str(c["operator"]), str(c["value"])))
    return out


class CsRoutingService:
    """Manage salesman → CS PIC pins and resolve the CS candidate pool."""

    def __init__(self, db: Session):
        self.db = db

    # ---- candidate pool ----------------------------------------------------

    def _cs_team_id(self, *, company_id: Optional[str] = None) -> Optional[str]:
        """Resolve the tier-1 team_id of the procurement customer-service team.

        ``company_id`` defaults to Sorento because the CS candidate list is also read
        by the admin pin dropdown, which has no contact in scope. Pin RESOLUTION
        passes the pinned contact's own company (AC-E6).
        """
        from app.services.company_routing_service import DEFAULT_COMPANY_ID
        from app.services.user_service import AccessAgentService

        agent_svc = AccessAgentService(self.db)
        agent_id = agent_svc.get_agent_id_by_code(CS_AGENT_CODE)
        if not agent_id:
            return None
        return agent_svc.get_team_id_by_tier(
            agent_id,
            1,
            team_set_code=CS_TEAM_SET_CODE,
            company_id=str(company_id or DEFAULT_COMPANY_ID),
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

    # ---- routable fields (predicate builder) -------------------------------

    # The form-header table backing each use_case (predicates match header fields).
    _USE_CASE_TABLE = {
        "purchase_request": "purchase_requests",
        "sponsorship_form": "purchase_requests",
        "complaint": "complaints",
        "stock_inquiry": "stock_inquiries",
    }
    # Curated non-lookup header fields offered as routing dimensions per table
    # (label, type). Excludes system/audit/status columns.
    _CURATED_FIELDS: dict[str, list[tuple[str, str, str]]] = {
        "purchase_requests": [
            ("customer_name", "Customer Name", "string"),
            ("project_title", "Project Title", "string"),
            ("total_project_value", "Total Project Value", "numeric"),
        ],
        "complaints": [
            ("customer_name", "Customer Name", "string"),
            ("complaint_type", "Complaint Type", "string"),
        ],
        "stock_inquiries": [
            ("customer_name", "Customer Name", "string"),
        ],
    }

    def routable_fields(self, use_case: str) -> list[dict]:
        """Fields a routing predicate can match, for a use_case's form. Lookup-bound
        columns (with their options, type='lookup') + a curated set of common
        string/numeric header fields."""
        from app.models.lookup import LookupBinding, LookupOption, LookupSet

        table = self._USE_CASE_TABLE.get(use_case)
        if not table:
            return []
        fields: list[dict] = []
        seen: set[str] = set()
        # Lookup-bound columns on the table.
        bindings = (
            self.db.query(LookupBinding)
            .filter(LookupBinding.table_name == table)
            .all()
        )
        for b in bindings:
            s = self.db.query(LookupSet).filter(LookupSet.id == b.set_id).first()
            if not s:
                continue
            opts = (
                self.db.query(LookupOption)
                .filter(LookupOption.set_id == s.id, LookupOption.is_active.is_(True))
                .order_by(LookupOption.sort_order.asc(), LookupOption.label.asc())
                .all()
            )
            fields.append({
                "field": b.column_name,
                "label": b.column_name.replace("_", " ").title(),
                "type": "lookup",
                "options": [{"value": o.value, "label": o.label} for o in opts],
            })
            seen.add(b.column_name)
        # Curated common fields (skip any already surfaced as a lookup).
        for field, label, ftype in self._CURATED_FIELDS.get(table, []):
            if field not in seen:
                fields.append({"field": field, "label": label, "type": ftype})
        return fields

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
        """All active routing rows for a contact (predicates + priority + PIC name),
        ordered by use_case then priority (the admin evaluation order)."""
        self._require_contact(contact_id)
        rows = (
            self.db.query(RespondContactCsRouting)
            .filter(
                RespondContactCsRouting.respond_contact_id == contact_id,
                RespondContactCsRouting.is_active.is_(True),
            )
            .order_by(
                RespondContactCsRouting.use_case.asc(),
                RespondContactCsRouting.priority.asc(),
                RespondContactCsRouting.created_at.asc(),
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
                    "id": r.id,
                    "use_case": r.use_case,
                    "cs_pic_user_id": r.cs_pic_user_id,
                    "cs_pic_name": (u.name or u.email) if u else None,
                    "match_conditions": r.match_conditions or [],
                    "priority": r.priority or 0,
                }
            )
        return out

    def upsert(
        self,
        contact_id: str,
        use_case: str,
        cs_pic_user_id: str,
        *,
        match_conditions: Optional[list] = None,
        priority: int = 0,
        created_by: Optional[str] = None,
    ) -> RespondContactCsRouting:
        """Create or update a routing row for (contact, use_case, condition-set).

        Uniqueness is per distinct condition-set (canonicalized), so a contact may
        have several rows for the same use_case routing different predicate sets to
        different PICs. Validates the use_case and that the CS PIC is a current member
        of the procurement customer-service team (D5). ``match_conditions`` is stored
        canonicalized so logically-equal sets collide on the unique index.
        """
        from app.services.cs_routing_match import canonical_conditions

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
        conds = _normalized_conditions(match_conditions)
        key = canonical_conditions(conds)
        # Find an existing row with the SAME canonical condition-set (not just use_case).
        row = next(
            (
                r
                for r in self.db.query(RespondContactCsRouting).filter(
                    RespondContactCsRouting.respond_contact_id == contact_id,
                    RespondContactCsRouting.use_case == use_case,
                )
                if canonical_conditions(r.match_conditions or []) == key
            ),
            None,
        )
        if row:
            row.cs_pic_user_id = cs_pic_user_id
            row.priority = priority
            row.match_conditions = conds
            row.is_active = True
        else:
            row = RespondContactCsRouting(
                respond_contact_id=contact_id,
                use_case=use_case,
                cs_pic_user_id=cs_pic_user_id,
                match_conditions=conds,
                priority=priority,
                is_active=True,
                created_by=created_by,
            )
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, contact_id: str, use_case: str, row_id: Optional[str] = None) -> None:
        """Clear routing rows. With ``row_id`` deletes one specific row; without it,
        clears every row for (contact, use_case) → reverts to round-robin. Idempotent."""
        self._require_contact(contact_id)
        q = self.db.query(RespondContactCsRouting).filter(
            RespondContactCsRouting.respond_contact_id == contact_id,
            RespondContactCsRouting.use_case == use_case,
        )
        if row_id:
            q = q.filter(RespondContactCsRouting.id == row_id)
        rows = q.all()
        for row in rows:
            self.db.delete(row)
        if rows:
            self.db.commit()
