"""The salesperson's "Dealer access" screen (DEALER-ACCESS-SCREEN, UAC S2-S7).

Reads: my own accounts and the people who hold access to them. Writes: ONE path, the one the AI agent uses
(DEALER-ACCESS-PORTAL, #2268): `contact_grant.plan` / `contact_grant._execute` to add people and
`writes._contact_plan` / `writes._contact_execute` to change or remove one. Nothing here writes a contact, link, tag
or access type itself, so the checks, texts and audit rows are the agent's. "Own accounts" are the active customers
of the user's own active sales agents (`writes._own_agent_ids`) in the companies the user is granted. Another
salesperson's account is never returned, named or counted beyond the `other_account` boolean.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from app.models.base import company_scope
from app.services.chatbot.agent import contact_grant, writes
from app.services.error_handler import AppException, handle_not_found

PICK_OWN = "Pick one of your accounts."
ALSO = "also has access through another account"
_PHONE_QUERY = re.compile(r"[\d\s+\-()]+")


def _refuse(message: str, **kwargs) -> AppException:
    return AppException(status_code=422, message=message, code="VALIDATION_ERROR", **kwargs)


def _company_row(db: Session, user_id: str, code: str):
    """(id, code, name) of a company the user is granted; 403 `not one of your companies` otherwise."""
    from app.models.company import Company
    from app.services.company_scope_resolver import resolve_user_grant_ids

    code = str(code or "").strip().upper()
    with company_scope(db, None):
        row = db.query(Company.id, Company.code, Company.name).filter(Company.code == code).first()
    if row is None or str(row.id) not in resolve_user_grant_ids(db, user_id):
        words = contact_grant.COMPANY_WORDS.get(code, code or "That company")
        raise AppException(status_code=403, message=f"{words} is not one of your companies.", code="FORBIDDEN")
    return row


def _own_customers(db: Session, user_id: str, company_ids: set[str] | None = None) -> list:
    """The user's own accounts (id, code, name, company_id) in the given companies, or in every granted one."""
    from app.models.order import Customer
    from app.services.company_scope_resolver import resolve_user_grant_ids

    agents = writes._own_agent_ids(db, user_id)
    if not agents:
        return []
    wanted = set(resolve_user_grant_ids(db, user_id))
    if company_ids is not None:
        wanted &= company_ids
    if not wanted:
        return []
    with company_scope(db, None):
        rows = (
            db.query(Customer.id, Customer.customer_code, Customer.customer_name, Customer.company_id)
            .filter(
                Customer.sales_agent_id.in_(agents),
                Customer.is_active.is_(True),
                Customer.company_id.in_(wanted),
            )
            .all()
        )
    return sorted(rows, key=lambda r: (r.customer_code or "", str(r.id)))


def my_accounts(db: Session, user_id: str, company: str) -> list[dict]:
    """S2: my own accounts of one company, by code."""
    row = _company_row(db, user_id, company)
    return [
        {"id": str(c.id), "code": c.customer_code, "name": c.customer_name}
        for c in _own_customers(db, user_id, {str(row.id)})
    ]


def _picked(db: Session, user_id: str, company: str, account_ids: list[str]) -> list:
    """The picked accounts, every one my own of this company; one answer for a foreign and an unknown id (S4)."""
    row = _company_row(db, user_id, company)
    own = {str(c.id): c for c in _own_customers(db, user_id, {str(row.id)})}
    ids = list(dict.fromkeys(str(i) for i in account_ids or []))
    if not ids or any(i not in own for i in ids):
        raise _refuse(PICK_OWN)
    return [own[i] for i in ids]


def _user(db: Session, user_id: str) -> dict:
    from app.dependencies import _load_user_dict_from_db

    user = _load_user_dict_from_db(db, user_id)
    if user is None:
        raise AppException(status_code=403, message="The user is no longer available.", code="USER_GONE")
    return user


# ------------------------------------------------------------------ S3 people


def list_people(
    db: Session,
    user_id: str,
    *,
    companies: list[str] | None = None,
    access: str | None = None,
    query: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict:
    """S3: one row per (contact, company) for every contact linked to at least one of my own accounts there."""
    from app.models.access import RespondContact, RespondContactCustomer
    from app.models.company import Company
    from app.models.user import User
    from app.services.contact_tag_service import owner_tag, tags_by_contact

    mine = _own_customers(db, user_id)
    if not mine:
        return {"rows": [], "total": 0}
    with company_scope(db, None):
        code_of = {str(cid): code for cid, code in db.query(Company.id, Company.code)}
        name_of = {str(cid): name for cid, name in db.query(Company.id, Company.name)}
        own_contact = str(db.query(User.respond_contact_id).filter(User.id == user_id).scalar() or "")
        by_customer = {str(c.id): c for c in mine}
        links = (
            db.query(RespondContactCustomer.id, RespondContactCustomer.contact_id, RespondContactCustomer.customer_id)
            .filter(RespondContactCustomer.customer_id.in_(list(by_customer)))
            .all()
        )
    grouped: dict[tuple[str, str], list[dict]] = {}
    for link_id, contact_id, customer_id in links:
        if str(contact_id) == own_contact:
            continue
        c = by_customer[str(customer_id)]
        grouped.setdefault((str(contact_id), code_of[str(c.company_id)]), []).append({
            "id": str(c.id), "code": c.customer_code, "name": c.customer_name, "link_id": str(link_id),
        })
    if not grouped:
        return {"rows": [], "total": 0}
    contact_ids = sorted({cid for cid, _ in grouped})
    with company_scope(db, None):
        contacts = {
            str(r.id): r
            for r in db.query(RespondContact.id, RespondContact.name, RespondContact.phone_number)
            .filter(RespondContact.id.in_(contact_ids))
        }
        held = tags_by_contact(db, contact_ids)
        tag_for = {code: owner_tag(db, code) for code in set(code_of.values())}
    company_name = {code: name_of[cid] for cid, code in code_of.items()}

    wanted_companies = {str(c).strip().upper() for c in companies or [] if str(c).strip()}
    text = (query or "").strip().lower()
    phone_digits = re.sub(r"\D", "", text) if text and _PHONE_QUERY.fullmatch(text) else ""
    rows: list[dict] = []
    for (contact_id, code), accounts in grouped.items():
        contact = contacts.get(contact_id)
        if contact is None or (wanted_companies and code not in wanted_companies):
            continue
        tag = tag_for.get(code)
        is_owner = tag is not None and any(t["id"] == str(tag.id) for t in held.get(contact_id, []))
        level = "owner" if is_owner else "employee"
        if access and access != level:
            continue
        accounts = sorted(accounts, key=lambda a: (a["code"] or "", a["id"]))
        phone = contact.phone_number or ""
        if text and not (
            text in (contact.name or "").lower()
            or (phone_digits and phone_digits in re.sub(r"\D", "", phone))
            or any(text in (a["code"] or "").lower() for a in accounts)
        ):
            continue
        rows.append({
            "contact_id": contact_id, "name": contact.name or "", "phone": phone, "company": code,
            "company_name": company_name.get(code, code), "accounts": accounts, "access": level,
            "owner_tag": tag.name if is_owner else None, "other_account": False,
        })
    rows.sort(key=lambda r: (r["name"].lower(), r["phone"], r["company"]))
    total = len(rows)
    start = max(int(page) - 1, 0) * int(limit)
    shown = rows[start:start + int(limit)]
    # A boolean only: another account's link is never named or counted (S3, S8: over all my granted companies).
    for contact_id in {r["contact_id"] for r in shown}:
        other = bool(writes._not_own_links(db, user_id, contact_id))
        for r in shown:
            if r["contact_id"] == contact_id:
                r["other_account"] = other
    return {"rows": shown, "total": total}


# ------------------------------------------------------------------ S4 grant


def grant(db: Session, user_id: str, company: str, account_ids: list[str], people: list[dict]) -> dict:
    """S4: every person is checked with the agent's grant plan first; one refusal refuses the form and writes
    nothing. Otherwise each person is executed with the agent's grant execute, each committing on its own (S9: only a
    concurrent change between the plan and the execute can leave earlier rows written)."""
    from app.services.company_scope_resolver import grants_scope
    from app.services.contact_setup_engine import normalise_phone

    accounts = _picked(db, user_id, company, account_ids)
    code = str(company).strip().upper()
    user = _user(db, user_id)
    calls = [
        {
            "phone": p.get("phone"), "name": p.get("name"), "role": p.get("role"),
            "companies": [code], "customer_codes": [a.customer_code for a in accounts],
        }
        for p in people
    ]
    errors: list[dict] = []
    plans: list[dict | None] = []
    seen: dict[str, int] = {}
    for index, args in enumerate(calls):
        phone = normalise_phone(args["phone"])
        if phone is not None and phone in seen:
            errors.append({"index": index, "error": f"Same as row {seen[phone] + 1}."})
            plans.append(None)
            continue
        if phone is not None:
            seen[phone] = index
        try:
            with grants_scope(db, user_id):
                plans.append(contact_grant.plan(db, user, args))
        except AppException as exc:
            errors.append({"index": index, "error": exc.message})
            plans.append(None)
    if errors:
        raise _refuse("Some people cannot be added.", details={"rows": errors})
    out = []
    for index, args in enumerate(calls):
        with grants_scope(db, user_id):
            done = contact_grant._execute(db, user, args)
        notes = [ALSO] if ALSO in (plans[index] or {}).get("lines", []) else []
        out.append({
            "index": index, "contact_id": str(done["id"]), "created": bool(done["after"]["created"]), "notes": notes,
        })
    return {"rows": out}


# ------------------------------------------------------------------ S5 update


def _editable(db: Session, user_id: str, contact_id: str) -> None:
    """404, the same answer as a contact that does not exist, unless I may change this contact (never my own)."""
    if not writes.contact_in_scope(db, user_id, str(contact_id)):
        raise handle_not_found("Contact", contact_id)


def update(db: Session, user_id: str, contact_id: str, company: str, role: str, account_ids: list[str]) -> dict:
    """S5: set which of my accounts of this company the person holds, and their level there.

    Both steps are planned first (neither plan writes), so a refusal from either writes nothing. Then the new links
    commit through the grant (role `employee`, add-only: the only way an edit_own holder links), and only after that
    the unlinks and a role change commit through the access update (`role_companies` limits the level to this
    company)."""
    from app.models.access import RespondContact, RespondContactCustomer
    from app.services.company_scope_resolver import grants_scope
    from app.services.contact_tag_service import owner_tag, tags_by_contact

    _editable(db, user_id, contact_id)
    row = _company_row(db, user_id, company)
    own = {str(c.id): c for c in _own_customers(db, user_id, {str(row.id)})}
    ids = list(dict.fromkeys(str(i) for i in account_ids or []))
    if not ids or any(i not in own for i in ids):
        raise _refuse(PICK_OWN)
    picked = [own[i] for i in ids]
    code = str(company).strip().upper()
    mine = set(own)
    with company_scope(db, None):
        contact = db.query(RespondContact.id, RespondContact.name, RespondContact.phone_number).filter(
            RespondContact.id == str(contact_id)
        ).one()
        held = {
            str(c) for (c,) in db.query(RespondContactCustomer.customer_id)
            .filter(RespondContactCustomer.contact_id == str(contact_id))
        }
        tag = owner_tag(db, code)
        tags = tags_by_contact(db, [str(contact_id)]).get(str(contact_id), [])
    current = "owner" if tag is not None and any(t["id"] == str(tag.id) for t in tags) else "employee"
    add = [c for c in picked if str(c.id) not in held]
    picked_ids = {str(c.id) for c in picked}
    change: dict = {"contact_id": str(contact_id), "unlink_customer_ids": sorted((held & mine) - picked_ids)}
    if role != current:
        change["role"] = role
        change["role_companies"] = [code]  # the level is per company: only this row's tags and types move
    user = _user(db, user_id)
    # An edit_own holder links only through the grant (A13/A14 and the template apply), role `employee`: add-only.
    grant_args = {
        "phone": contact.phone_number, "name": contact.name or "", "role": "employee", "companies": [code],
        "customer_codes": [c.customer_code for c in add],
    }
    has_change = bool(change["unlink_customer_ids"] or "role" in change)
    # Both steps are planned (neither plan writes) before either is executed: a refusal writes nothing.
    with grants_scope(db, user_id):
        if add:
            contact_grant.plan(db, user, grant_args)
        if has_change:
            writes._contact_plan(db, user, change)
    result: dict = {"id": str(contact_id)}
    with grants_scope(db, user_id):
        if add:
            contact_grant._execute(db, user, grant_args)
        if has_change:
            result = writes._contact_execute(db, user, change)
    return result


# ------------------------------------------------------------------ S6 unlink


def own_link(db: Session, user_id: str, link_id: str):
    """The link row when it is one of MY accounts' links of a contact I may change; 404 otherwise."""
    from app.models.access import RespondContactCustomer

    try:
        uuid.UUID(str(link_id))
    except (TypeError, ValueError):
        raise handle_not_found("Customer link", link_id)
    with company_scope(db, None):
        link = db.query(RespondContactCustomer).filter(RespondContactCustomer.id == str(link_id)).first()
    if link is None or str(link.customer_id) not in {str(c.id) for c in _own_customers(db, user_id)}:
        raise handle_not_found("Customer link", link_id)
    _editable(db, user_id, str(link.contact_id))
    return link


def unlink(db: Session, user_id: str, link_id: str) -> dict:
    """S6: the deferred action's body, run as the requester. Re-checks the link is still mine; C4 (the last link
    turns AI replies off) is the access update's own."""
    from app.services.company_scope_resolver import grants_scope

    link = own_link(db, user_id, link_id)
    # Every granted company, not the request's (or the deferred commit's stored) active one: the link row's company
    # scoped query must see an account of my other company (S8).
    with grants_scope(db, user_id):
        return writes._contact_execute(
            db, _user(db, user_id),
            {"contact_id": str(link.contact_id), "unlink_customer_ids": [str(link.customer_id)]},
        )
