"""Market-segment catalog + assignment service (retail / project CS routing).

Source of truth for:
- the configurable ``market_segments`` catalog (admin add / rename / activate / reorder),
- the contact ↔ segment assignment (``respond_contact_market_segments``),
- the team-membership ↔ segment assignment (``team_member_market_segments``),
- resolving a Respond.io contact to its segment codes and the round-robin ``segment_key``.

Matching rule (applied by team-members / next-assignee): a member serves a contact when the
member has NO segments (serves all) OR the member's segments intersect the contact's segments.
An untagged / unknown contact resolves to an empty set = no filter (matches every member).
``is_active`` governs catalog curation / pickers only; it does NOT retroactively unmatch an
already-assigned code.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.access import (
    MarketSegment,
    RespondContact,
    TeamMember,
    respond_contact_market_segments,
    team_member_market_segments,
)
from app.models.respond_workspace import RespondWorkspace
from app.services.error_handler import (
    handle_conflict,
    handle_not_found,
    handle_validation_error,
)

logger = logging.getLogger(__name__)


def segment_key_for(segments) -> str:
    """Canonical round-robin cursor key for a set of segment codes.

    Sorted, ``|``-joined, lowercased. Empty set -> '' (the legacy / no-segment cursor).
    """
    codes = sorted({str(c).strip().lower() for c in (segments or []) if str(c).strip()})
    return "|".join(codes)


class MarketSegmentService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ resolve

    def resolve_contact_segments(
        self, respond_io_id: str, space_id: Optional[str] = None
    ) -> set[str]:
        """Return the contact's segment codes (empty set on miss / untagged).

        Lenient by design: routing must never break on an unknown contact, so a
        missing contact / workspace mismatch yields ``set()`` (= no filter), never 404.
        """
        rid = (respond_io_id or "").strip()
        if not rid:
            return set()
        q = self.db.query(RespondContact).filter(RespondContact.respond_io_id == rid)
        sid = (space_id or "").strip()
        if sid:
            q = q.join(
                RespondWorkspace, RespondWorkspace.id == RespondContact.workspace_id
            ).filter(RespondWorkspace.space_id == sid)
        contact = q.first()
        if contact is None:
            logger.info(
                "market-segment: no contact for respond_io_id=%r space_id=%r -> unfiltered",
                rid,
                sid or None,
            )
            return set()
        return {str(s.code) for s in contact.market_segments}

    # ------------------------------------------------------------------ catalog

    def list_segments(self, active_only: bool = False) -> list[MarketSegment]:
        q = self.db.query(MarketSegment)
        if active_only:
            q = q.filter(MarketSegment.is_active.is_(True))
        return q.order_by(
            MarketSegment.sort_order.asc().nullslast(), MarketSegment.code.asc()
        ).all()

    def get_segment(self, code: str) -> Optional[MarketSegment]:
        return self.db.query(MarketSegment).filter(MarketSegment.code == code).first()

    def create_segment(
        self,
        code: str,
        name: str,
        *,
        description: Optional[str] = None,
        is_active: bool = True,
        sort_order: Optional[int] = None,
    ) -> MarketSegment:
        code = (code or "").strip().lower()
        name = (name or "").strip()
        if not code or not name:
            raise handle_validation_error("code and name are required.")
        if self.get_segment(code) is not None:
            raise handle_conflict(f"Market segment code={code!r} already exists.")
        seg = MarketSegment(
            code=code,
            name=name,
            description=description,
            is_active=is_active,
            sort_order=sort_order,
        )
        self.db.add(seg)
        self.db.commit()
        self.db.refresh(seg)
        return seg

    def update_segment(
        self,
        code: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_order: Optional[int] = None,
    ) -> MarketSegment:
        seg = self.get_segment(code)
        if seg is None:
            raise handle_not_found("MarketSegment", code)
        if name is not None:
            if not name.strip():
                raise handle_validation_error("name cannot be empty.")
            seg.name = name.strip()
        if description is not None:
            seg.description = description
        if is_active is not None:
            seg.is_active = is_active
        if sort_order is not None:
            seg.sort_order = sort_order
        self.db.commit()
        self.db.refresh(seg)
        return seg

    def segment_in_use(self, code: str) -> bool:
        used_contact = (
            self.db.query(respond_contact_market_segments.c.contact_id)
            .filter(respond_contact_market_segments.c.segment_code == code)
            .first()
        )
        if used_contact is not None:
            return True
        used_member = (
            self.db.query(team_member_market_segments.c.team_member_id)
            .filter(team_member_market_segments.c.segment_code == code)
            .first()
        )
        return used_member is not None

    def delete_segment(self, code: str) -> None:
        seg = self.get_segment(code)
        if seg is None:
            raise handle_not_found("MarketSegment", code)
        if self.segment_in_use(code):
            raise handle_conflict(
                f"Market segment code={code!r} is assigned to one or more contacts or "
                "team members; unassign it before deleting."
            )
        self.db.delete(seg)
        self.db.commit()

    # ------------------------------------------------------------- assignment

    def _load_segments(self, codes) -> list[MarketSegment]:
        wanted = [str(c).strip().lower() for c in (codes or []) if str(c).strip()]
        if not wanted:
            return []
        rows = (
            self.db.query(MarketSegment)
            .filter(MarketSegment.code.in_(wanted))
            .all()
        )
        found = {r.code for r in rows}
        missing = [c for c in wanted if c not in found]
        if missing:
            raise handle_validation_error(
                f"Unknown market segment code(s): {', '.join(sorted(set(missing)))}"
            )
        return rows

    def get_contact_segment_codes(self, contact_id: str) -> list[str]:
        contact = (
            self.db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        )
        if contact is None:
            raise handle_not_found("RespondContact", contact_id)
        return [str(s.code) for s in contact.market_segments]

    def set_contact_segments(self, contact_id: str, codes) -> list[str]:
        contact = (
            self.db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        )
        if contact is None:
            raise handle_not_found("RespondContact", contact_id)
        contact.market_segments = self._load_segments(codes)
        self.db.commit()
        self.db.refresh(contact)
        return [str(s.code) for s in contact.market_segments]

    def _member_by_team_user(self, team_id: str, user_id: str) -> TeamMember:
        member = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
            .first()
        )
        if member is None:
            raise handle_not_found("TeamMember", f"team_id={team_id}, user_id={user_id}")
        return member

    def get_member_segment_codes_by_team_user(self, team_id: str, user_id: str) -> list[str]:
        member = self._member_by_team_user(team_id, user_id)
        return [str(s.code) for s in member.market_segments]

    def set_member_segments_by_team_user(
        self, team_id: str, user_id: str, codes
    ) -> list[str]:
        member = self._member_by_team_user(team_id, user_id)
        member.market_segments = self._load_segments(codes)
        self.db.commit()
        self.db.refresh(member)
        return [str(s.code) for s in member.market_segments]

    def get_member_segment_codes(self, team_member_id: str) -> list[str]:
        member = (
            self.db.query(TeamMember).filter(TeamMember.id == team_member_id).first()
        )
        if member is None:
            raise handle_not_found("TeamMember", team_member_id)
        return [str(s.code) for s in member.market_segments]

    def set_member_segments(self, team_member_id: str, codes) -> list[str]:
        member = (
            self.db.query(TeamMember).filter(TeamMember.id == team_member_id).first()
        )
        if member is None:
            raise handle_not_found("TeamMember", team_member_id)
        member.market_segments = self._load_segments(codes)
        self.db.commit()
        self.db.refresh(member)
        return [str(s.code) for s in member.market_segments]
