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
OTHER_COMPANY = "This number already has access in another company."
CUSTOMERS_MAX = 50
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


def _customer_conds(db: Session, user_id: str, mine: bool) -> list | None:
    """The customers the list may show: active, of a granted company, and (`mine`) of my own sales agents. None
    when there are none to show."""
    from app.models.order import Customer
    from app.services.company_scope_resolver import resolve_user_grant_ids

    granted = set(resolve_user_grant_ids(db, user_id))
    if not granted:
        return None
    conds = [Customer.is_active.is_(True), Customer.company_id.in_(granted)]
    if mine:
        agents = writes._own_agent_ids(db, user_id)
        if not agents:
            return None
        conds.append(Customer.sales_agent_id.in_(agents))
    return conds


def customers(
    db: Session, user_id: str, *, query: str | None = None, mine: bool = True, companies: list[str] | None = None,
) -> list[dict]:
    """N3.1: the Customer filter's options, at most 50 `{id, code, name, company}` of the customers the list can show,
    matched on name or code (any case), sorted by name."""
    from app.models.company import Company
    from app.models.order import Customer

    conds = _customer_conds(db, user_id, mine)
    if conds is None:
        return []
    wanted = {str(c).strip().upper() for c in companies or [] if str(c).strip()}
    text = (query or "").strip()
    with company_scope(db, None):
        q = (
            db.query(Customer.id, Customer.customer_code, Customer.customer_name, Company.code)
            .join(Company, Company.id == Customer.company_id)
            .filter(*conds)
        )
        if wanted:
            q = q.filter(Company.code.in_(wanted))
        if text:
            like = f"%{text}%"
            q = q.filter(Customer.customer_name.ilike(like) | Customer.customer_code.ilike(like))
        rows = q.order_by(Customer.customer_name.collate("C"), Customer.customer_code).limit(CUSTOMERS_MAX).all()
    return [{"id": str(r.id), "code": r.customer_code, "name": r.customer_name, "company": r.code} for r in rows]


def list_people(
    db: Session,
    user_id: str,
    *,
    mine: bool = True,
    customer_ids: list[str] | None = None,
    companies: list[str] | None = None,
    access: str | None = None,
    query: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict:
    """S3 / N2: one row per (contact, company) for every contact linked to a customer the list may show there (my own
    accounts with `mine`, every active customer of my granted companies without). Each row lists every active linked
    customer of that company, marked `mine`; only my own accounts carry their link id."""
    from app.models.access import RespondContact, RespondContactCustomer
    from app.models.company import Company
    from app.models.order import Customer
    from app.models.user import User
    from app.services.company_scope_resolver import resolve_user_grant_ids
    from app.services.contact_tag_service import owner_codes_by_contact, owner_tag

    conds = _customer_conds(db, user_id, mine)
    if conds is None:
        return {"rows": [], "total": 0}
    agents = set(writes._own_agent_ids(db, user_id))
    granted = set(resolve_user_grant_ids(db, user_id))
    with company_scope(db, None):
        code_of = {str(cid): code for cid, code in db.query(Company.id, Company.code)}
        name_of = {str(cid): name for cid, name in db.query(Company.id, Company.name)}
        own_contact = str(db.query(User.respond_contact_id).filter(User.id == user_id).scalar() or "")
        keys = {
            (str(contact_id), str(company_id))
            for contact_id, company_id in db.query(RespondContactCustomer.contact_id, Customer.company_id)
            .join(Customer, Customer.id == RespondContactCustomer.customer_id)
            .filter(*conds)
            .distinct()
            if str(contact_id) != own_contact
        }
        contact_ids = sorted({cid for cid, _ in keys})
        links = (
            db.query(
                RespondContactCustomer.id, RespondContactCustomer.contact_id, Customer.id, Customer.customer_code,
                Customer.customer_name, Customer.company_id, Customer.sales_agent_id,
            )
            .join(Customer, Customer.id == RespondContactCustomer.customer_id)
            .filter(
                RespondContactCustomer.contact_id.in_(contact_ids),
                Customer.is_active.is_(True),
                Customer.company_id.in_(granted),
            )
            .all()
        ) if contact_ids else []
    grouped: dict[tuple[str, str], list[dict]] = {}
    has_mine: set[str] = set()
    for link_id, contact_id, customer_id, code, name, company_id, agent_id in links:
        key = (str(contact_id), str(company_id))
        if key not in keys:
            continue
        own = agent_id is not None and str(agent_id) in agents
        account = {"id": str(customer_id), "code": code, "name": name, "mine": own}
        if own:
            account["link_id"] = str(link_id)  # another salesperson's link is never sent (N2.3)
            has_mine.add(str(contact_id))
        grouped.setdefault((str(contact_id), code_of[str(company_id)]), []).append(account)
    if not grouped:
        return {"rows": [], "total": 0}
    with company_scope(db, None):
        contacts = {
            str(r.id): r
            for r in db.query(
                RespondContact.id, RespondContact.name, RespondContact.phone_number, RespondContact.respond_io_id
            ).filter(RespondContact.id.in_(contact_ids))
        }
        tag_for = {code: owner_tag(db, code) for code in set(code_of.values())}
        owner_of = owner_codes_by_contact(db, contact_ids, set(code_of.values()))
    company_name = {code: name_of[cid] for cid, code in code_of.items()}

    wanted_companies = {str(c).strip().upper() for c in companies or [] if str(c).strip()}
    wanted_customers = {str(c) for c in customer_ids or [] if str(c).strip()}
    text = (query or "").strip().lower()
    phone_digits = re.sub(r"\D", "", text) if text and _PHONE_QUERY.fullmatch(text) else ""
    rows: list[dict] = []
    for (contact_id, code), accounts in grouped.items():
        contact = contacts.get(contact_id)
        if contact is None or (wanted_companies and code not in wanted_companies):
            continue
        if wanted_customers and not any(a["id"] in wanted_customers for a in accounts):
            continue
        tag = tag_for.get(code)
        is_owner = code in owner_of.get(contact_id, set())
        level = "owner" if is_owner else "employee"
        if access and access != level:
            continue
        accounts = sorted(accounts, key=lambda a: (not a["mine"], a["code"] or "", a["id"]))
        phone = contact.phone_number or ""
        if text and not (
            text in (contact.name or "").lower()
            or (phone_digits and phone_digits in re.sub(r"\D", "", phone))
            or any(text in (a["code"] or "").lower() or text in (a["name"] or "").lower() for a in accounts)
        ):
            continue
        rows.append({
            "contact_id": contact_id, "name": contact.name or "", "phone": phone, "company": code,
            "company_name": company_name.get(code, code), "accounts": accounts, "access": level,
            "owner_tag": tag.name if is_owner else None, "editable": False, "in_respond": bool(contact.respond_io_id),
        })
    rows.sort(key=lambda r: (r["name"].lower(), r["phone"], r["company"]))
    total = len(rows)
    start = max(int(page) - 1, 0) * int(limit)
    shown = rows[start:start + int(limit)]
    # One of my own accounts linked is exactly `contact_in_scope` for an edit_own holder; ask it only otherwise.
    editable = {
        cid: cid in has_mine or writes.contact_in_scope(db, user_id, cid) for cid in {r["contact_id"] for r in shown}
    }
    for r in shown:
        r["editable"] = editable[r["contact_id"]]
    return {"rows": shown, "total": total}


# ------------------------------------------------------------------ S4 grant


def _picked_by_company(db: Session, user_id: str, codes: list[str], account_ids: list[str]) -> dict[str, list]:
    """N4.1: every picked account is my own of one picked company, and every picked company gets at least one; one
    answer for a foreign and an unknown id (S4)."""
    own: dict[str, tuple[str, object]] = {}
    for code in codes:
        row = _company_row(db, user_id, code)
        for c in _own_customers(db, user_id, {str(row.id)}):
            own[str(c.id)] = (code, c)
    ids = list(dict.fromkeys(str(i) for i in account_ids or []))
    if not ids or any(i not in own for i in ids):
        raise _refuse(PICK_OWN)
    out = {code: [own[i][1] for i in ids if own[i][0] == code] for code in codes}
    if any(not accounts for accounts in out.values()):
        raise _refuse(PICK_OWN)
    return out


def _has_access(db: Session, user_id: str, phone: str, codes: list[str]) -> dict | None:
    """N4.3: the refusal for a phone whose contact already has ANY customer link, else None. Named, with the contact
    to open, only when the contact shows on my list (an active customer of a company I am granted); otherwise no name,
    no id. A staff phone is left to the plan's own text."""
    from app.models.access import RespondContact, RespondContactCustomer
    from app.models.company import Company
    from app.models.order import Customer
    from app.services.company_scope_resolver import resolve_user_grant_ids
    from app.services.contact_access_sheet_service import COMPANY_ORDER

    contact = contact_grant._find_contact(db, phone)
    if contact is None or contact_grant._is_staff(db, phone, str(contact.id)):
        return None
    with company_scope(db, None):
        linked = (
            db.query(Customer.company_id, Customer.is_active)
            .join(RespondContactCustomer, RespondContactCustomer.customer_id == Customer.id)
            .filter(RespondContactCustomer.contact_id == str(contact.id))
            .all()
        )
        name = db.query(RespondContact.name).filter(RespondContact.id == str(contact.id)).scalar() or ""
        code_of = {str(cid): code for cid, code in db.query(Company.id, Company.code)}
    if not linked:
        return None
    granted = set(resolve_user_grant_ids(db, user_id))
    visible = {code_of.get(str(cid)) for cid, active in linked if active and str(cid) in granted}
    visible.discard(None)
    if not visible:
        return {"error": OTHER_COMPANY, "contact": None}
    order = [*codes, *COMPANY_ORDER, *sorted(visible)]
    company = next(c for c in order if c in visible)
    return {
        "error": f"{name} already has access." if name else "This number already has access.",
        "contact": {
            "id": str(contact.id), "name": name, "company": company,
            "editable": writes.contact_in_scope(db, user_id, str(contact.id)),
        },
    }


def _respond_outcome(db: Session, contact_id: str) -> dict:
    """N5.1 / N5.3: the shared Respond.io function, its answer as `{respond, respond_error}`; never raises."""
    from app.services import respond_contact_ensure

    try:
        result = respond_contact_ensure.ensure_in_respond(db, str(contact_id))
    except Exception:  # noqa: BLE001 - the access is saved; the failure is reported, never silent
        db.rollback()
        return {"respond": "failed", "respond_error": "Respond.io gave an unexpected answer."}
    if result["status"] in respond_contact_ensure.OK_STATUSES:
        return {"respond": "ok", "respond_error": None}
    return {"respond": "failed", "respond_error": result.get("error") or "Respond.io gave an unexpected answer."}


def grant(db: Session, user_id: str, companies, account_ids: list[str], people: list[dict]) -> dict:
    """S4 / N4: every person is checked first (a duplicate, a phone that already has access, then the agent's grant
    plan once per picked company); one refusal refuses the form and writes nothing. Otherwise each (person, company)
    is executed with the agent's grant execute, each committing on its own (S9: only a concurrent change between the
    plan and the execute can leave earlier rows written). Then each person is found or created in Respond.io inside
    the request (N5.1); a failure there leaves the access saved and is reported on the row (N5.3)."""
    from app.services.company_scope_resolver import grants_scope
    from app.services.contact_setup_engine import normalise_phone

    raw = [companies] if isinstance(companies, str) else list(companies or [])
    codes = list(dict.fromkeys(str(c).strip().upper() for c in raw if str(c).strip()))
    if not codes:
        raise _refuse("Pick a company.")
    picked = _picked_by_company(db, user_id, codes, account_ids)
    user = _user(db, user_id)
    calls = [
        [
            {
                "phone": p.get("phone"), "name": p.get("name"), "role": p.get("role"),
                "companies": [code], "customer_codes": [a.customer_code for a in picked[code]],
            }
            for code in codes
        ]
        for p in people
    ]
    errors: list[dict] = []
    seen: dict[str, int] = {}
    for index, person_calls in enumerate(calls):
        phone = normalise_phone(person_calls[0]["phone"])
        if phone is not None and phone in seen:
            errors.append({"index": index, "error": f"Same as row {seen[phone] + 1}.", "contact": None})
            continue
        if phone is not None:
            seen[phone] = index
        try:
            with grants_scope(db, user_id):
                held = _has_access(db, user_id, phone, codes) if phone is not None else None
                if held is not None:
                    errors.append({"index": index, **held})
                    continue
                for args in person_calls:
                    contact_grant.plan(db, user, args)
        except AppException as exc:
            errors.append({"index": index, "error": exc.message, "contact": None})
    if errors:
        raise _refuse("Some people cannot be added.", details={"rows": errors})
    out = []
    for index, person_calls in enumerate(calls):
        created = False
        contact_id = None
        for args in person_calls:
            with grants_scope(db, user_id):
                done = contact_grant._execute(db, user, args, queue_respond=False)
            created = created or bool(done["after"]["created"])
            contact_id = str(done["id"])
        out.append({"index": index, "contact_id": contact_id, "created": created})
    for row in out:
        row.update(_respond_outcome(db, row["contact_id"]))
    return {"rows": out}


def respond_retry(db: Session, user_id: str, contact_id: str) -> dict:
    """N5.5: "Try again in Respond.io" for a contact I may change (404 otherwise): the same shared function."""
    _editable(db, user_id, contact_id)
    return _respond_outcome(db, contact_id)


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
    from app.services.contact_tag_service import owner_codes_by_contact

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
        owned = owner_codes_by_contact(db, [str(contact_id)], [code]).get(str(contact_id), set())
    current = "owner" if code in owned else "employee"
    add = [c for c in picked if str(c.id) not in held]
    picked_ids = {str(c.id) for c in picked}
    change: dict = {"contact_id": str(contact_id), "unlink_customer_ids": sorted((held & mine) - picked_ids)}
    # Employee means no dealer prices: the owner types of a legacy contact (types, no tag) go too (owner ruling 9 Nov).
    with company_scope(db, None):
        types = {t.code for t in db.get(RespondContact, str(contact_id)).access_types}
    legacy = role == "employee" and bool(types & writes._owner_types([code]))
    if role != current or legacy:
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
