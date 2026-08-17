"""Team-membership <-> brand assignment (the second routing axis).

Sibling of ``market_segment_service`` and deliberately the same shape: a membership
carries the brand(s) that member serves, an untagged membership serves every brand,
and ``team-members`` / ``next-assignee`` intersect that with the brand n8n resolved
for the item. Keyed by (team, user) so one person can serve Mocha in the promotion
team and everything in another.

There is no catalog half here - brands are master data (``brands``), owned by
``product_service``. This module only owns the assignment table
(``team_member_brands``).
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.access import TeamMember, team_member_brands
from app.models.base import company_scope
from app.models.product import Brand
from app.services.error_handler import handle_not_found, handle_validation_error
from app.services.user_service import normalise_brand_code

logger = logging.getLogger(__name__)


class TeamMemberBrandService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ read

    def _member(self, team_id: str, user_id: str) -> TeamMember:
        member = (
            self.db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
            .first()
        )
        if member is None:
            raise handle_not_found("TeamMember", f"team_id={team_id}, user_id={user_id}")
        return member

    def _codes_for_member(self, member_id: str) -> list[str]:
        rows = (
            self.db.query(team_member_brands.c.brand_code)
            .filter(team_member_brands.c.team_member_id == str(member_id))
            .all()
        )
        return sorted({normalise_brand_code(r[0]) for r in rows} - {None})

    def get_member_brand_codes_by_team_user(self, team_id: str, user_id: str) -> list[str]:
        return self._codes_for_member(str(self._member(team_id, user_id).id))

    # ----------------------------------------------------------------- write

    def _validate(self, codes) -> list[str]:
        """Normalise, de-duplicate and refuse codes no brand carries.

        Read scope-free: brands are company-scoped, but the ROUTING handle is the
        code, which is unique across the table - a Mocha tag saved by an admin in
        the Sorento company must still validate when the same code exists under
        another one, and the alternative (silently accepting anything) turns a typo
        into a member who quietly serves a brand that will never be asked for.
        """
        wanted = sorted({normalise_brand_code(c) for c in (codes or [])} - {None})
        if not wanted:
            return []
        with company_scope(self.db, None):
            found = {
                normalise_brand_code(r[0])
                for r in self.db.query(Brand.brand_code)
                .filter(Brand.brand_code.in_(wanted))
                .all()
            }
        missing = [c for c in wanted if c not in found]
        if missing:
            raise handle_validation_error(
                f"Unknown brand code(s): {', '.join(missing)}"
            )
        return wanted

    def set_member_brands_by_team_user(
        self, team_id: str, user_id: str, codes
    ) -> list[str]:
        """Replace this membership's brand tags with exactly ``codes`` (empty = serves all)."""
        member = self._member(team_id, user_id)
        wanted = self._validate(codes)
        member_id = str(member.id)
        self.db.execute(
            team_member_brands.delete().where(
                team_member_brands.c.team_member_id == member_id
            )
        )
        for code in wanted:
            self.db.execute(
                team_member_brands.insert().values(
                    team_member_id=member_id, brand_code=code
                )
            )
        self.db.commit()
        return self._codes_for_member(member_id)

    # ------------------------------------------------------------- reporting

    def brand_codes_for_members(self, member_ids) -> dict[str, list[str]]:
        """``{team_member_id: [codes]}`` for a whole roster, in one query.

        Used by the access-agent detail listing, which renders a chip row per member
        and would otherwise issue one query per person.
        """
        ids = [str(m) for m in (member_ids or [])]
        if not ids:
            return {}
        rows = (
            self.db.query(
                team_member_brands.c.team_member_id, team_member_brands.c.brand_code
            )
            .filter(team_member_brands.c.team_member_id.in_(ids))
            .all()
        )
        out: dict[str, set[str]] = {}
        for member_id, code in rows:
            normalised: Optional[str] = normalise_brand_code(code)
            if normalised:
                out.setdefault(str(member_id), set()).add(normalised)
        return {k: sorted(v) for k, v in out.items()}
