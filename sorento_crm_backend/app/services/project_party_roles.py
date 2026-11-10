"""PROJECT-PARTY-ROLES: the roles a party plays on a project are the editable lookup set
``project_party_role`` (owner ruling 10 Nov 2026: configurable like the lead source).

One list serves both ends:

* a project links a party in a role through ``projects.party_links`` (developer excepted: it is
  the fixed ``projects.developer_party_id`` column, owner ruling);
* ``parties.party_type`` is a party's usual role, picked from the same list. It never restricts
  which role the party may fill (owner Q4 b, 10 Nov): one firm, one row.

Card: documentation/plans/project-sales/CARD-project-party-roles-10nov.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.error_handler import AppException

SET_KEY = "project_party_role"
SET_NAME = "Project - Party role"
#: The one role that is a column, not a link. It stays in the list as a party type and is locked
#: there (cannot be deactivated or deleted) because the registration lock depends on it.
DEVELOPER = "developer"

#: The seed of the set, as data: (value, label, allows_many). Written once by migration
#: ppr_0001_party_roles and by the test schema seed; the set is the list from then on. Order is the
#: order the registration form shows the roles in.
SEED_ROLES = (
    (DEVELOPER, "Developer", False),
    ("architect", "Architect", False),
    ("main_contractor", "Main contractor", False),
    ("trading_house", "Trading house", True),
    ("subcontractor", "Subcontractor", True),
    ("tender_party", "Tender party", True),
    ("consultant", "Consultant", False),
    ("interior_designer", "Interior designer", False),
)

#: Copies the two legacy single-party columns into ``party_links`` once, idempotently. The role keys
#: here name the COLUMNS being retired, not a role list: after this runs nothing reads them.
BACKFILL_SQL = (
    """
    INSERT INTO projects.party_links (project_id, role, party_id)
    SELECT sp.project_id, 'architect', sp.architect_party_id
      FROM projects.sales_profile sp
     WHERE sp.architect_party_id IS NOT NULL
    ON CONFLICT DO NOTHING
    """,
    """
    INSERT INTO projects.party_links (project_id, role, party_id)
    SELECT sp.project_id, 'main_contractor', sp.main_contractor_party_id
      FROM projects.sales_profile sp
     WHERE sp.main_contractor_party_id IS NOT NULL
    ON CONFLICT DO NOTHING
    """,
)


def _set_id(db: Session) -> Optional[str]:
    from app.models.lookup import LookupSet

    return (
        db.query(LookupSet.id)
        .filter(LookupSet.set_key == SET_KEY, LookupSet.tenant_id.is_(None))
        .scalar()
    )


def roles(db: Session) -> Dict[str, Dict[str, Any]]:
    """``{value: {label, allows_many, is_active, sort_order}}`` for every role, active or not."""
    from app.models.lookup import LookupOption

    set_id = _set_id(db)
    if set_id is None:
        return {}
    return {
        row.value: {
            "label": row.label,
            "allows_many": bool(row.allows_many),
            "is_active": bool(row.is_active),
            "sort_order": row.sort_order,
        }
        for row in db.query(LookupOption)
        .filter(LookupOption.set_id == set_id)
        .order_by(LookupOption.sort_order.asc(), LookupOption.label.asc())
        .all()
    }


def is_role_set(db: Session, set_id: str) -> bool:
    return bool(set_id) and str(set_id) == str(_set_id(db) or "")


def assert_party_type(db: Session, value: Optional[str], *, current: Optional[str] = None) -> None:
    """A party's usual role must be a role of the list; a NEW value must be an active one (a party
    already typed with a since-deactivated role keeps it)."""
    known = roles(db)
    row = known.get(value or "")
    if row is None or (not row["is_active"] and value != current):
        active = [r["label"] for r in known.values() if r["is_active"]]
        raise AppException(
            status_code=422,
            message="Pick the party's role from the list"
            + (": " + ", ".join(active) + "." if active else "."),
            code="project_party_type_invalid",
        )


def check_links(db: Session, wanted: List[tuple], existing: List[tuple]) -> None:
    """``wanted`` / ``existing`` are ``(role, party_id)`` pairs. Refuses an unknown role, the
    developer (a column), a NEW link in an inactive role, and a role allowing one party getting
    more parties than it already had (a role switched to one keeps what it holds, rule 2)."""
    known = roles(db)
    had = set(existing)
    for role, _party_id in wanted:
        if role == DEVELOPER or role not in known:
            raise AppException(
                status_code=422,
                message="That party role is not one a project links.",
                code="project_party_role_invalid",
            )
    for role, party_id in wanted:
        if not known[role]["is_active"] and (role, party_id) not in had:
            raise AppException(
                status_code=422,
                message=f"{known[role]['label']} is no longer a party role.",
                code="project_party_role_inactive",
            )
    for role in {r for r, _p in wanted}:
        if known[role]["allows_many"]:
            continue
        now = sum(1 for r, _p in wanted if r == role)
        before = sum(1 for r, _p in had if r == role)
        if now > 1 and now > before:
            raise AppException(
                status_code=422,
                message=f"A project has one {known[role]['label'].lower()}.",
                code="project_party_role_single",
            )


def assert_option_change(db: Session, option, *, new_value: Optional[str] = None,
                         deactivate: bool = False, delete: bool = False) -> None:
    """The guard on the role list's own options (called by the lookup option service for this
    set only): developer is locked; a key in use can be neither deleted nor rewritten."""
    if not is_role_set(db, option.set_id):
        return
    if option.value == DEVELOPER and (delete or deactivate or (new_value and new_value != DEVELOPER)):
        raise AppException(
            status_code=422,
            message="Developer is always a party role. Rename it if you need to.",
            code="project_party_role_locked",
        )
    rewriting = bool(new_value) and new_value.lower() != (option.value or "").lower()
    if (delete or rewriting) and _in_use(db, option.value):
        raise AppException(
            status_code=409,
            message="This role is in use by parties or projects. Deactivate it instead.",
            code="project_party_role_in_use",
        )


def _in_use(db: Session, value: str) -> bool:
    from sqlalchemy import select, union_all

    from app.models.projects import ProjectParty, ProjectPartyLink

    # Core selects on the Table objects on purpose: the list is tenant-wide, so a role in use by
    # ANY company is in use, and the ORM's company scope only filters mapped entities.
    parties, links = ProjectParty.__table__, ProjectPartyLink.__table__
    stmt = union_all(
        select(parties.c.id).where(parties.c.party_type == value).limit(1),
        select(links.c.party_id).where(links.c.role == value).limit(1),
    )
    return db.execute(stmt).first() is not None
