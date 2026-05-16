"""Contact access type catalog service.

Source of truth for the configurable per-tenant access-type catalog
(``contact_access_types``) and the many-to-many assignment between
respond contacts and access types (``respond_contact_access_types``).

Promotion / attachment visibility is evaluated by overlapping a contact's
assigned access codes against a resource's ``access_levels`` JSONB array.
"""
from __future__ import annotations

import logging
import re
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


_ACCESS_LABEL_NONALNUM = re.compile(r"[^a-z0-9 ]")
_ACCESS_LABEL_SEPS = re.compile(r"[\s\-_/]+")


def _normalize_access_label(value: str) -> str:
    """Lower, swap separators to space, strip punctuation, collapse, trim."""
    if not value:
        return ""
    s = _ACCESS_LABEL_SEPS.sub(" ", value.strip().casefold())
    s = _ACCESS_LABEL_NONALNUM.sub("", s)
    return " ".join(s.split())


def _clean_keywords(value) -> list[str]:
    """Coerce admin-supplied keyword payload to a clean str list (dedup, strip, drop empties)."""
    if not value:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in value:
        s = str(v or "").strip()
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _tokenize_access_label(value: str) -> set[str]:
    """Token set with naive plural strip (drop trailing 's' for tokens >3 chars not ending 'ss')."""
    tokens: set[str] = set()
    for tok in _normalize_access_label(value).split():
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        if tok:
            tokens.add(tok)
    return tokens


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
        """Return list of {code, name, description, sort_order, keywords} for active types (API options)."""
        rows = (
            self.db.query(
                ContactAccessType.code,
                ContactAccessType.name,
                ContactAccessType.description,
                ContactAccessType.sort_order,
                ContactAccessType.keywords,
            )
            .filter(ContactAccessType.is_active.is_(True))
            .order_by(ContactAccessType.sort_order.asc().nullslast(), ContactAccessType.code.asc())
            .all()
        )
        return [
            {
                "code": r[0],
                "name": r[1] or r[0],
                "description": r[2],
                "sort_order": r[3],
                "keywords": r[4] if isinstance(r[4], list) else [],
            }
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
            keywords=_clean_keywords(data.get("keywords")),
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
        if "keywords" in data:
            row.keywords = _clean_keywords(data["keywords"])
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
        """TCK-2026-000105 resolution (supersedes TCK-2026-000016 two-call).

        Accepts each input as a fuzzy variant of a contact's CURRENTLY-ACTIVE
        access level (name or code) and normalizes to the canonical code for
        the JSONB overlap filter. Resolution tiers (operate only on the
        contact's active set, never the global catalog):

        1. Exact normalized match against name or code (spaces / underscores
           interchangeable, case-insensitive, punctuation stripped, simple
           plural drop — "Sorento Dealer", "sorento_dealer", "sorento dealers"
           all match the same code).
        2. Concatenated-no-space form ("enduser" ≡ "end user").
        3. Token-subset: input tokens are a non-empty subset of one code's
           name/code tokens. "dealer" matches "Sorento Dealer" if it is the
           ONLY dealer-bearing active code; if multiple ("Sorento Dealer" +
           "Mocha Dealer"), raise 403 listing the candidates so the caller
           disambiguates.

        Edge cases:
        - access_levels empty AND contact has exactly ONE currently-active
          code → auto-default to that code.
        - access_levels empty AND contact has >1 (or zero) active → raise 422
          with the `allowed` name list.
        - any value that matches nothing → raise 403 with refreshed `allowed`.
        """
        from fastapi import HTTPException, status

        allowed = self.resolve_active_access_levels_for_contact(respond_io_id, space_id)
        active_codes = self.resolve_contact_access_codes(respond_io_id, space_id)
        catalog = (
            self.db.query(
                ContactAccessType.code,
                ContactAccessType.name,
                ContactAccessType.keywords,
            )
            .filter(
                ContactAccessType.is_active.is_(True),
                ContactAccessType.code.in_(active_codes),
            )
            .all()
            if active_codes else []
        )

        # Per-code alias index built from name + code + admin-curated keywords.
        # Each alias maps to a LIST of candidate codes so a synonym shared by
        # multiple active rows ("customer" registered on two codes) surfaces as
        # ambiguous instead of silently resolving to whichever was inserted first.
        exact_to_codes: dict[str, list[str]] = {}
        concat_to_codes: dict[str, list[str]] = {}
        code_tokens: dict[str, set[str]] = {}

        def _add_alias(table: dict[str, list[str]], key: str, code_val: str) -> None:
            if not key:
                return
            bucket = table.setdefault(key, [])
            if code_val not in bucket:
                bucket.append(code_val)

        for row in catalog:
            code_val = row[0]
            name_val = row[1]
            keywords = row[2] if len(row) > 2 else None
            labels = [name_val, code_val]
            if isinstance(keywords, list):
                labels.extend(str(k) for k in keywords if k)
            for label in labels:
                norm = _normalize_access_label(label or "")
                _add_alias(exact_to_codes, norm, code_val)
                _add_alias(concat_to_codes, norm.replace(" ", ""), code_val)
                for tok in _tokenize_access_label(label or ""):
                    code_tokens.setdefault(code_val, set()).add(tok)

        normalized: list[str] = []
        invalid: list[str] = []
        ambiguous: list[tuple[str, list[str]]] = []
        for v in access_levels or []:
            raw = (v or "").strip()
            if not raw:
                continue
            n = _normalize_access_label(raw)
            candidates = exact_to_codes.get(n) or concat_to_codes.get(n.replace(" ", "")) or []
            resolved: Optional[str] = None
            if len(candidates) == 1:
                resolved = candidates[0]
            elif len(candidates) > 1:
                ambiguous.append((raw, list(candidates)))
                continue
            else:
                input_tokens = _tokenize_access_label(raw)
                if input_tokens:
                    # Tier A: input tokens ⊆ code tokens — caller used a fragment.
                    # Tier B: code tokens ⊆ input tokens — caller added noise words.
                    matches = [
                        code for code, toks in code_tokens.items()
                        if (
                            input_tokens.issubset(toks)
                            or (toks and toks.issubset(input_tokens))
                        )
                    ]
                    if len(matches) == 1:
                        resolved = matches[0]
                    elif len(matches) > 1:
                        ambiguous.append((raw, matches))
                        continue
            if resolved is None:
                invalid.append(raw)
                continue
            if resolved not in normalized:
                normalized.append(resolved)

        if ambiguous:
            candidates_by_input = {
                raw: [
                    (row[1] or row[0])
                    for row in catalog
                    if row[0] in match_codes
                ]
                for raw, match_codes in ambiguous
            }
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ACCESS_LEVELS_AMBIGUOUS",
                    "message": (
                        f"access_levels ambiguous for this contact: {list(candidates_by_input)}. "
                        "Pick a specific name from the `candidates` mapping."
                    ),
                    "candidates": candidates_by_input,
                    "allowed": allowed,
                },
            )

        if not normalized and not invalid:
            if len(allowed) == 1:
                only_name = allowed[0]["name"]
                bucket = exact_to_codes.get(_normalize_access_label(only_name)) or []
                if len(bucket) == 1:
                    return [bucket[0]]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "ACCESS_LEVELS_REQUIRED",
                    "message": "access_levels is required for contact-scoped requests.",
                    "allowed": allowed,
                },
            )

        if invalid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "ACCESS_LEVELS_NOT_PERMITTED",
                    "message": (
                        f"access_levels not permitted for this contact: {invalid}. "
                        "Pick a name from the `allowed` list (refreshed live)."
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
        """Return [{name, keywords}] for the contact's CURRENTLY-ACTIVE access codes.

        Filtered against the active catalog so deactivated rows never surface.
        ``keywords`` exposes the admin-curated lookup synonyms so MCP agents can
        match user phrasing without an extra catalog round-trip; pass any keyword
        (or the name) back as `access_levels` and
        `enforce_access_levels_for_contact` translates it to the canonical code
        for the JSONB overlap filter.
        """
        codes = self.resolve_contact_access_codes(respond_io_id, space_id)
        if not codes:
            return []
        rows = (
            self.db.query(
                ContactAccessType.code,
                ContactAccessType.name,
                ContactAccessType.keywords,
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
                "name": r[1] or r[0],
                "keywords": r[2] if isinstance(r[2], list) else [],
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
