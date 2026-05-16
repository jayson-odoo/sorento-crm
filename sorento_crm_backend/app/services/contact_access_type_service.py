"""Contact access type catalog service.

Source of truth for the configurable per-tenant access-type catalog
(``contact_access_types``) and the many-to-many assignment between
respond contacts and access types (``respond_contact_access_types``).

Promotion / attachment visibility is evaluated by overlapping a contact's
assigned access codes against a resource's ``access_levels`` JSONB array.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models.access import (
    ContactAccessType,
    RespondContact,
    respond_contact_access_types,
)
from app.models.respond_workspace import RespondWorkspace
from app.services.error_handler import handle_validation_error, handle_conflict, handle_not_found

logger = logging.getLogger(__name__)

# Default codes to use when no catalog exists yet (e.g. before migration)
_FALLBACK_DEFAULT_CODES = ["dealer", "end_user"]


class ContactAccessTypeService:
    """CRUD on ``contact_access_types`` plus contact↔access-type M2M helpers."""

    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------------- catalog
    def list_active_codes(self) -> list[str]:
        """Return codes of active contact access types, ordered by sort_order then code."""
        rows = (
            self.db.query(ContactAccessType.code)
            .filter(ContactAccessType.is_active.is_(True))
            .order_by(ContactAccessType.sort_order.asc().nullslast(), ContactAccessType.code.asc())
            .all()
        )
        return [r[0] for r in rows] if rows else _FALLBACK_DEFAULT_CODES.copy()

    def get_default_access_levels(self) -> list[str]:
        """Return default access_levels for new promotions/attachments (all active codes, or fallback)."""
        codes = self.list_active_codes()
        return codes if codes else _FALLBACK_DEFAULT_CODES.copy()

    def validate_access_levels(self, access_levels: list[str], field_name: str = "access_levels") -> list[str]:
        """Validate codes against the active catalog. Returns normalized (stripped, deduplicated) list."""
        if not access_levels:
            raise handle_validation_error(f"{field_name} must contain at least one access type.")
        allowed = set(self.list_active_codes())
        normalized: list[str] = []
        seen: set[str] = set()
        for a in access_levels:
            code = (a or "").strip()
            if not code:
                continue
            if code not in allowed:
                raise handle_conflict(
                    f"Invalid access type(s): {[code]}. Allowed (from catalog): {sorted(allowed)}."
                )
            if code not in seen:
                seen.add(code)
                normalized.append(code)
        if not normalized:
            raise handle_validation_error(f"{field_name} must contain at least one access type.")
        return normalized

    def list_types_for_api(self) -> list[dict]:
        """Return list of {code, name, description, sort_order} for active types (API options)."""
        rows = (
            self.db.query(ContactAccessType.code, ContactAccessType.name, ContactAccessType.description, ContactAccessType.sort_order)
            .filter(ContactAccessType.is_active.is_(True))
            .order_by(ContactAccessType.sort_order.asc().nullslast(), ContactAccessType.code.asc())
            .all()
        )
        return [
            {"code": r[0], "name": r[1] or r[0], "description": r[2], "sort_order": r[3]}
            for r in rows
        ]

    def list_all_types(self) -> list[ContactAccessType]:
        """Return all contact access types (including inactive) for admin UI, ordered by sort_order then code."""
        return (
            self.db.query(ContactAccessType)
            .order_by(ContactAccessType.sort_order.asc().nullslast(), ContactAccessType.code.asc())
            .all()
        )

    def get_type_by_code(self, code: str) -> Optional[ContactAccessType]:
        """Get a single contact access type by code."""
        return self.db.query(ContactAccessType).filter(ContactAccessType.code == code).first()

    def create_type(self, data: dict) -> ContactAccessType:
        """Create a new contact access type. Raises if code already exists."""
        existing = self.get_type_by_code(data["code"])
        if existing:
            raise handle_conflict(f"Contact access type with code '{data['code']}' already exists.")
        row = ContactAccessType(
            code=data["code"],
            name=data["name"],
            description=data.get("description"),
            is_active=data.get("is_active", True),
            sort_order=data.get("sort_order"),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_type(self, code: str, data: dict) -> ContactAccessType:
        """Update a contact access type. Code cannot be changed."""
        row = self.get_type_by_code(code)
        if not row:
            raise handle_validation_error(f"Contact access type '{code}' not found.")
        if "name" in data:
            row.name = data["name"]
        if "description" in data:
            row.description = data["description"]
        if "is_active" in data:
            row.is_active = data["is_active"]
        if "sort_order" in data:
            row.sort_order = data["sort_order"]
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_type(self, code: str) -> None:
        """Delete a contact access type. Cascades remove all contact assignments via the pivot."""
        row = self.get_type_by_code(code)
        if not row:
            raise handle_validation_error(f"Contact access type '{code}' not found.")
        self.db.delete(row)
        self.db.commit()

    # ---------------------------------------------------------- contact M2M
    def set_contact_access_codes(self, contact_id: str, codes: List[str]) -> List[str]:
        """Replace the contact's access-type assignment with ``codes``.

        Validates each code against the active catalog, deduplicates, and rewrites
        the pivot in a single transaction. ``codes=[]`` clears all assignments.
        Returns the final list of assigned codes (deterministic by sort_order).
        """
        normalized: list[str] = []
        if codes:
            allowed = set(self.list_active_codes())
            seen: set[str] = set()
            for code in codes:
                c = (code or "").strip()
                if not c or c in seen:
                    continue
                if c not in allowed:
                    raise handle_conflict(
                        f"Invalid access type(s): {[c]}. Allowed (from catalog): {sorted(allowed)}."
                    )
                seen.add(c)
                normalized.append(c)

        self.db.execute(
            respond_contact_access_types.delete().where(
                respond_contact_access_types.c.contact_id == contact_id
            )
        )
        if normalized:
            self.db.execute(
                insert(respond_contact_access_types),
                [{"contact_id": contact_id, "access_type_code": c} for c in normalized],
            )
        return normalized

    def get_contact_access_codes(self, contact_id: str) -> List[str]:
        """Return the contact's assigned access codes ordered by catalog sort_order then code."""
        rows = (
            self.db.query(respond_contact_access_types.c.access_type_code)
            .join(
                ContactAccessType,
                ContactAccessType.code == respond_contact_access_types.c.access_type_code,
            )
            .filter(respond_contact_access_types.c.contact_id == contact_id)
            .order_by(
                ContactAccessType.sort_order.asc().nullslast(),
                ContactAccessType.code.asc(),
            )
            .all()
        )
        return [r[0] for r in rows]

    def enforce_access_levels_for_contact(
        self,
        respond_io_id: str,
        space_id: str,
        access_levels: Optional[list[str]],
    ) -> list[str]:
        """TCK-2026-000016 two-call resolution.

        - access_levels missing/empty → raise AppException(422, allowed=[{code,name,description},...])
        - any code not in the contact's CURRENTLY-ACTIVE set → raise AppException(403, allowed=[...])
        - otherwise return normalized codes (intersection with contact's active set).
        """
        from fastapi import HTTPException, status

        allowed = self.resolve_active_access_levels_for_contact(respond_io_id, space_id)
        allowed_codes = {entry["code"] for entry in allowed}

        normalized: list[str] = []
        for v in access_levels or []:
            code = (v or "").strip()
            if code and code not in normalized:
                normalized.append(code)

        if not normalized:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "ACCESS_LEVELS_REQUIRED",
                    "message": "access_levels is required for contact-scoped requests.",
                    "allowed": allowed,
                },
            )

        invalid = [c for c in normalized if c not in allowed_codes]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ACCESS_LEVELS_NOT_PERMITTED",
                    "message": (
                        f"access_levels not permitted for this contact: {invalid}. "
                        "Pick one of the codes returned in `allowed` (refreshed live)."
                    ),
                    "allowed": allowed,
                    "invalid": invalid,
                },
            )
        return normalized

    def resolve_active_access_levels_for_contact(
        self,
        respond_io_id: str,
        space_id: str,
    ) -> list[dict]:
        """Return [{code, description}] for the contact's CURRENTLY-ACTIVE access codes.

        Filtered against the active catalog so deactivated rows never surface.
        Used by TCK-2026-000016 two-call resolution: when an MCP caller passes
        no `access_levels`, the route responds with this list as the allowed
        set, and the agent re-issues the call with one of the listed codes.
        """
        codes = self.resolve_contact_access_codes(respond_io_id, space_id)
        if not codes:
            return []
        rows = (
            self.db.query(
                ContactAccessType.code,
                ContactAccessType.name,
                ContactAccessType.description,
            )
            .filter(
                ContactAccessType.is_active.is_(True),
                ContactAccessType.code.in_(codes),
            )
            .order_by(
                ContactAccessType.sort_order.asc().nullslast(),
                ContactAccessType.code.asc(),
            )
            .all()
        )
        return [
            {
                "code": r[0],
                "name": r[1] or r[0],
                "description": r[2],
            }
            for r in rows
        ]

    def resolve_contact_access_codes(self, respond_io_id: str, space_id: str) -> List[str]:
        """Resolve a Respond.io (contact_id, space_id) pair to the contact's access codes.

        Raises 404 when no contact matches. The contact must belong to a workspace
        whose ``space_id`` matches the supplied value (exact string match).
        """
        rid = (respond_io_id or "").strip()
        sid = (space_id or "").strip()
        if not rid or not sid:
            raise handle_validation_error("contact_id and space_id are both required.")
        contact = (
            self.db.query(RespondContact)
            .join(RespondWorkspace, RespondWorkspace.id == RespondContact.workspace_id)
            .filter(RespondContact.respond_io_id == rid, RespondWorkspace.space_id == sid)
            .first()
        )
        if contact is None:
            raise handle_not_found("RespondContact", f"respond_io_id={rid}, space_id={sid}")
        return self.get_contact_access_codes(str(contact.id))

    def resolve_optional_contact_access_codes(
        self,
        respond_io_id: Optional[str],
        space_id: Optional[str],
    ) -> Optional[List[str]]:
        """Endpoint-friendly resolver: both absent → None (skip filter), exactly one absent → 400.

        Returns the contact's assigned codes (possibly an empty list if the contact has
        no access types assigned — caller treats that as 'no overlap with anything').
        """
        rid = (respond_io_id or "").strip() if respond_io_id is not None else ""
        sid = (space_id or "").strip() if space_id is not None else ""
        if not rid and not sid:
            return None
        if not rid or not sid:
            raise handle_validation_error(
                "Both contact_id and space_id are required when filtering by contact context."
            )
        return self.resolve_contact_access_codes(rid, sid)
