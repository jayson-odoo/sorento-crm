"""Contact access type catalog and Respond mapping: configurable access levels for promotions/attachments."""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.access import ContactAccessType, RespondAccessTypeMapping
from app.services.error_handler import handle_validation_error, handle_conflict

logger = logging.getLogger(__name__)

# Default codes to use when no catalog exists yet (e.g. before migration)
_FALLBACK_DEFAULT_CODES = ["dealer", "end_user"]


class ContactAccessTypeService:
    """CRUD and lookup for contact_access_types and respond_access_type_mappings."""

    def __init__(self, db: Session):
        self.db = db

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
        """
        Validate that every non-empty code is in the active catalog. Returns normalized list (stripped, deduplicated).
        Raises if any code is invalid.
        """
        if not access_levels:
            raise handle_validation_error(f"{field_name} must contain at least one access type.")
        allowed = set(self.list_active_codes())
        normalized = []
        seen = set()
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

    def resolve_respond_value_to_code(self, respond_value: Optional[str]) -> Optional[str]:
        """
        Resolve Respond raw value (e.g. from custom field) to a contact_access_types.code.
        Tries mapping first, then direct catalog code match. Returns None if not found.
        """
        if not respond_value or not str(respond_value).strip():
            return None
        raw = str(respond_value).strip()
        # Direct mapping
        mapping = (
            self.db.query(RespondAccessTypeMapping.access_type_code)
            .filter(
                RespondAccessTypeMapping.source_key == raw,
                RespondAccessTypeMapping.is_active.is_(True),
            )
            .first()
        )
        if mapping:
            return str(mapping[0])
        # Direct catalog code match (case-sensitive for code)
        exists = (
            self.db.query(ContactAccessType.code)
            .filter(ContactAccessType.code == raw, ContactAccessType.is_active.is_(True))
            .first()
        )
        return str(exists[0]) if exists else None

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
        """Delete a contact access type. Fails if in use (e.g. contacts or mappings)."""
        row = self.get_type_by_code(code)
        if not row:
            raise handle_validation_error(f"Contact access type '{code}' not found.")
        self.db.delete(row)
        self.db.commit()

    def list_mappings(self) -> List[RespondAccessTypeMapping]:
        """Return all respond access type mappings for admin UI."""
        return (
            self.db.query(RespondAccessTypeMapping)
            .order_by(RespondAccessTypeMapping.source_key.asc())
            .all()
        )

    def get_mapping_by_id(self, mapping_id: str) -> Optional[RespondAccessTypeMapping]:
        """Get a single mapping by id."""
        return self.db.query(RespondAccessTypeMapping).filter(RespondAccessTypeMapping.id == mapping_id).first()

    def create_mapping(self, data: dict) -> RespondAccessTypeMapping:
        """Create a new respond access type mapping. Raises if source_key already exists."""
        existing = (
            self.db.query(RespondAccessTypeMapping)
            .filter(RespondAccessTypeMapping.source_key == data["source_key"])
            .first()
        )
        if existing:
            raise handle_conflict(f"Mapping for source key '{data['source_key']}' already exists.")
        access_type = self.get_type_by_code(data["access_type_code"])
        if not access_type:
            raise handle_validation_error(f"Contact access type '{data['access_type_code']}' not found.")
        row = RespondAccessTypeMapping(
            source_key=data["source_key"],
            access_type_code=data["access_type_code"],
            is_active=data.get("is_active", True),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_mapping(self, mapping_id: str, data: dict) -> RespondAccessTypeMapping:
        """Update a respond access type mapping."""
        row = self.get_mapping_by_id(mapping_id)
        if not row:
            raise handle_validation_error(f"Mapping '{mapping_id}' not found.")
        if "source_key" in data:
            other = (
                self.db.query(RespondAccessTypeMapping)
                .filter(RespondAccessTypeMapping.source_key == data["source_key"], RespondAccessTypeMapping.id != mapping_id)
                .first()
            )
            if other:
                raise handle_conflict(f"Another mapping already exists for source key '{data['source_key']}'.")
            row.source_key = data["source_key"]
        if "access_type_code" in data:
            access_type = self.get_type_by_code(data["access_type_code"])
            if not access_type:
                raise handle_validation_error(f"Contact access type '{data['access_type_code']}' not found.")
            row.access_type_code = data["access_type_code"]
        if "is_active" in data:
            row.is_active = data["is_active"]
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_mapping(self, mapping_id: str) -> None:
        """Delete a respond access type mapping."""
        row = self.get_mapping_by_id(mapping_id)
        if not row:
            raise handle_validation_error(f"Mapping '{mapping_id}' not found.")
        self.db.delete(row)
        self.db.commit()
