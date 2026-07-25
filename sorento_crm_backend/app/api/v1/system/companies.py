"""Companies admin + access management (System Management → Companies).

Multi-company data isolation, PLAN §16. Company CRUD + grant/membership management
are **superadmin-only**; ``my-context`` / ``switch`` are for any authenticated user
(they drive the top-right company switcher).

The ``companies`` / ``user_companies`` / ``respond_contact_companies`` tables are NOT
``CompanyScopedMixin`` (they have no ``company_id`` of their own — they ARE the
partition dimension + its membership tables), so the ``do_orm_execute`` scope filter
never touches them regardless of the request scope.

FE contract: ``sorento_crm_frontend/.../companies/services/companyService.ts``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.access import RespondContact
from app.models.company import Company, RespondContactCompany, UserCompany
from app.models.user import User
from app.schemas.common import MAX_PAGE_LIMIT
from app.services.error_handler import AppException, handle_conflict, handle_not_found
from app.services.user_service import UserPermissionService

router = APIRouter(prefix="/companies")


# --------------------------------------------------------------------------- #
# Auth helpers                                                                  #
# --------------------------------------------------------------------------- #
def _is_superadmin(db: Session, user_id: str) -> bool:
    slugs = UserPermissionService(db).get_user_role_slugs(user_id)
    return bool(slugs & {UserPermissionService.SUPERADMIN_ROLE_SLUG, "admin"})


def _require_superadmin(db: Session, current_user: dict) -> None:
    if not _is_superadmin(db, current_user["id"]):
        raise AppException(
            status_code=403,
            message="Superadmin access is required to manage companies.",
            code="FORBIDDEN",
        )


# --------------------------------------------------------------------------- #
# Serializers                                                                   #
# --------------------------------------------------------------------------- #
def _user_count(db: Session, company_id: str) -> int:
    return (
        db.query(func.count(UserCompany.id))
        .filter(UserCompany.company_id == company_id)
        .scalar()
        or 0
    )


def _contact_count(db: Session, company_id: str) -> int:
    return (
        db.query(func.count(RespondContactCompany.id))
        .filter(RespondContactCompany.company_id == company_id)
        .scalar()
        or 0
    )


def _serialize_company(db: Session, company: Company, *, with_counts: bool = True) -> dict:
    out = {
        "id": str(company.id),
        "name": company.name,
        "code": company.code,
        "is_active": bool(company.is_active),
        "autocount_ref": company.autocount_ref,
        "logo_url": company.logo_url,
        "created_at": company.created_at.isoformat() if company.created_at else None,
    }
    if with_counts:
        out["user_count"] = _user_count(db, str(company.id))
        out["contact_count"] = _contact_count(db, str(company.id))
    return out


def _serialize_company_user(user: User) -> dict:
    return {"id": str(user.id), "name": user.name, "email": user.email}


def _serialize_company_contact(contact: RespondContact) -> dict:
    return {
        "id": str(contact.id),
        "name": contact.name or "",
        "phone": contact.phone_number or "",
    }


def _get_company_or_404(db: Session, company_id: str) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise handle_not_found("Company", company_id)
    return company


# --------------------------------------------------------------------------- #
# Request bodies                                                                #
# --------------------------------------------------------------------------- #
class CompanyForm(BaseModel):
    name: str
    code: str
    is_active: bool = True
    autocount_ref: Optional[str] = None
    logo_url: Optional[str] = None


class SwitchBody(BaseModel):
    company_id: str


class AddUserBody(BaseModel):
    user_id: str


class AddContactBody(BaseModel):
    contact_id: str


# --------------------------------------------------------------------------- #
# Company CRUD                                                                  #
# --------------------------------------------------------------------------- #
@router.get("")
def list_companies(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc"),
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List companies. Superadmin sees all; a regular user sees only granted ones."""
    q = db.query(Company)
    if not _is_superadmin(db, current_user["id"]):
        q = q.join(UserCompany, UserCompany.company_id == Company.id).filter(
            UserCompany.user_id == current_user["id"]
        )
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(or_(Company.name.ilike(like), Company.code.ilike(like)))

    sort_col = {
        "name": Company.name,
        "code": Company.code,
        "created_at": Company.created_at,
        "is_active": Company.is_active,
    }.get((sort or "").strip(), Company.name)
    q = q.order_by(sort_col.desc() if dir == "desc" else sort_col.asc())

    total = q.count()
    rows = q.offset((page - 1) * limit).limit(limit).all()
    data = [_serialize_company(db, c) for c in rows]
    return {"data": data, "empty": len(data) == 0, "pagination": {"total": total, "page": page}}


@router.post("", status_code=201)
def create_company(
    body: CompanyForm,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    code = (body.code or "").strip()
    name = (body.name or "").strip()
    if not code or not name:
        raise AppException(status_code=400, message="Name and code are required.", code="VALIDATION_ERROR")
    if db.query(Company).filter(func.lower(Company.code) == code.lower()).first():
        raise handle_conflict(f"A company with code '{code}' already exists.")
    company = Company(
        name=name,
        code=code,
        is_active=body.is_active,
        autocount_ref=(body.autocount_ref or None),
        logo_url=(body.logo_url or None),
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return _serialize_company(db, company)


@router.get("/my-context")
def my_context(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current user's switchable companies + active/last-active — consumed by the
    NextAuth ``jwt`` callback (later slice) and the company switcher."""
    user_id = current_user["id"]
    is_super = _is_superadmin(db, user_id)
    if is_super:
        companies = db.query(Company).order_by(Company.name.asc()).all()
    else:
        companies = (
            db.query(Company)
            .join(UserCompany, UserCompany.company_id == Company.id)
            .filter(UserCompany.user_id == user_id)
            .order_by(Company.name.asc())
            .all()
        )
    grant_ids = {str(c.id) for c in companies}
    user = db.query(User).filter(User.id == user_id).first()
    last_active = str(user.last_active_company_id) if user and user.last_active_company_id else None

    active: Optional[str] = None
    if last_active and last_active in grant_ids:
        active = last_active
    elif len(grant_ids) == 1:
        active = next(iter(grant_ids))
    elif grant_ids:
        # Fail-closed fallback: never surface a non-granted (stale) last_active as
        # active. Deterministically pick the lowest granted id instead.
        active = sorted(grant_ids)[0]
    # else: no grants -> active stays None.

    return {
        "companies": [_serialize_company(db, c, with_counts=False) for c in companies],
        "active_company_id": active,
        "last_active_company_id": last_active,
    }


@router.post("/switch")
def switch_company(
    body: SwitchBody,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist the user's active company. Validates the grant (superadmin: any).
    Token re-mint is the FE's job (NextAuth ``session.update()``)."""
    user_id = current_user["id"]
    target = (body.company_id or "").strip()
    company = _get_company_or_404(db, target)

    if not _is_superadmin(db, user_id):
        granted = (
            db.query(UserCompany)
            .filter(UserCompany.user_id == user_id, UserCompany.company_id == target)
            .first()
        )
        if granted is None:
            raise AppException(
                status_code=403,
                message="You do not have access to this company.",
                code="FORBIDDEN",
            )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise handle_not_found("User", user_id)
    user.last_active_company_id = target
    db.commit()
    return {"active_company_id": target, "company": _serialize_company(db, company, with_counts=False)}


@router.get("/select")
def companies_select(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lightweight ``[{id,name,code}]`` of active companies for pickers.

    Superadmin-only, matching the rest of the company grant/management routes.
    Declared before ``/{company_id}`` so it isn't captured as an id.
    """
    _require_superadmin(db, current_user)
    rows = (
        db.query(Company)
        .filter(Company.is_active.is_(True))
        .order_by(Company.name.asc())
        .all()
    )
    return [{"id": str(c.id), "name": c.name, "code": c.code} for c in rows]


@router.get("/{company_id}")
def get_company(
    company_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = _get_company_or_404(db, company_id)
    if not _is_superadmin(db, current_user["id"]):
        granted = (
            db.query(UserCompany)
            .filter(UserCompany.user_id == current_user["id"], UserCompany.company_id == company_id)
            .first()
        )
        if granted is None:
            raise handle_not_found("Company", company_id)
    return _serialize_company(db, company)


@router.put("/{company_id}")
def update_company(
    company_id: str,
    body: CompanyForm,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    company = _get_company_or_404(db, company_id)
    code = (body.code or "").strip()
    name = (body.name or "").strip()
    if not code or not name:
        raise AppException(status_code=400, message="Name and code are required.", code="VALIDATION_ERROR")
    clash = (
        db.query(Company)
        .filter(func.lower(Company.code) == code.lower(), Company.id != company_id)
        .first()
    )
    if clash:
        raise handle_conflict(f"A company with code '{code}' already exists.")
    company.name = name
    company.code = code
    company.is_active = body.is_active
    company.autocount_ref = body.autocount_ref or None
    company.logo_url = body.logo_url or None
    db.commit()
    db.refresh(company)
    return _serialize_company(db, company)


@router.delete("/{company_id}", status_code=204)
def delete_company(
    company_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    company = _get_company_or_404(db, company_id)
    db.delete(company)  # hard delete; grants/memberships cascade (ON DELETE CASCADE)
    db.commit()
    return None


# --------------------------------------------------------------------------- #
# User grants (user_companies)                                                  #
# --------------------------------------------------------------------------- #
def _company_users(db: Session, company_id: str) -> list[dict]:
    users = (
        db.query(User)
        .join(UserCompany, UserCompany.user_id == User.id)
        .filter(UserCompany.company_id == company_id, User.is_trashed.is_(False))
        .order_by(User.name.asc().nullslast(), User.email.asc())
        .all()
    )
    return [_serialize_company_user(u) for u in users]


@router.get("/{company_id}/users")
def list_company_users(
    company_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    _get_company_or_404(db, company_id)
    return _company_users(db, company_id)


@router.post("/{company_id}/users")
def add_company_user(
    company_id: str,
    body: AddUserBody,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    _get_company_or_404(db, company_id)
    user = db.query(User).filter(User.id == body.user_id, User.is_trashed.is_(False)).first()
    if user is None:
        raise handle_not_found("User", body.user_id)
    existing = (
        db.query(UserCompany)
        .filter(UserCompany.company_id == company_id, UserCompany.user_id == body.user_id)
        .first()
    )
    if existing is None:
        db.add(UserCompany(company_id=company_id, user_id=body.user_id))
        db.commit()
    return _company_users(db, company_id)


@router.delete("/{company_id}/users/{user_id}")
def remove_company_user(
    company_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    _get_company_or_404(db, company_id)
    db.query(UserCompany).filter(
        UserCompany.company_id == company_id, UserCompany.user_id == user_id
    ).delete()

    # If the revoked grant was the user's active/last-active company, it must not
    # linger as a resolvable scope. Repoint to a remaining grant (deterministic
    # lowest id) or null it so the resolver fails closed rather than scoping the
    # user to a company they no longer have access to.
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None and str(user.last_active_company_id or "") == str(company_id):
        remaining = {
            str(r[0])
            for r in db.query(UserCompany.company_id)
            .filter(UserCompany.user_id == user_id)
            .all()
        }
        user.last_active_company_id = sorted(remaining)[0] if remaining else None

    db.commit()
    return _company_users(db, company_id)


# --------------------------------------------------------------------------- #
# Contact memberships (respond_contact_companies)                               #
# --------------------------------------------------------------------------- #
def _company_contacts(db: Session, company_id: str) -> list[dict]:
    contacts = (
        db.query(RespondContact)
        .join(
            RespondContactCompany,
            RespondContactCompany.respond_contact_id == RespondContact.id,
        )
        .filter(RespondContactCompany.company_id == company_id)
        .order_by(RespondContact.name.asc().nullslast(), RespondContact.phone_number.asc())
        .all()
    )
    return [_serialize_company_contact(c) for c in contacts]


@router.get("/{company_id}/contacts")
def list_company_contacts(
    company_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    _get_company_or_404(db, company_id)
    return _company_contacts(db, company_id)


@router.get("/{company_id}/contacts/available")
def list_available_contacts(
    company_id: str,
    query: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Contacts NOT yet tagged to this company (for the add-contact picker)."""
    _require_superadmin(db, current_user)
    _get_company_or_404(db, company_id)
    tagged = db.query(RespondContactCompany.respond_contact_id).filter(
        RespondContactCompany.company_id == company_id
    )
    q = db.query(RespondContact).filter(RespondContact.id.notin_(tagged))
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(
            or_(RespondContact.name.ilike(like), RespondContact.phone_number.ilike(like))
        )
    rows = q.order_by(RespondContact.name.asc().nullslast(), RespondContact.phone_number.asc()).limit(50).all()
    return [_serialize_company_contact(c) for c in rows]


@router.post("/{company_id}/contacts")
def add_company_contact(
    company_id: str,
    body: AddContactBody,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    _get_company_or_404(db, company_id)
    contact = db.query(RespondContact).filter(RespondContact.id == body.contact_id).first()
    if contact is None:
        raise handle_not_found("RespondContact", body.contact_id)
    existing = (
        db.query(RespondContactCompany)
        .filter(
            RespondContactCompany.company_id == company_id,
            RespondContactCompany.respond_contact_id == body.contact_id,
        )
        .first()
    )
    if existing is None:
        db.add(
            RespondContactCompany(company_id=company_id, respond_contact_id=body.contact_id)
        )
        db.commit()
    return _company_contacts(db, company_id)


@router.delete("/{company_id}/contacts/{contact_id}")
def remove_company_contact(
    company_id: str,
    contact_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_superadmin(db, current_user)
    _get_company_or_404(db, company_id)
    db.query(RespondContactCompany).filter(
        RespondContactCompany.company_id == company_id,
        RespondContactCompany.respond_contact_id == contact_id,
    ).delete()
    db.commit()
    return _company_contacts(db, company_id)
