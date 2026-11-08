"""`crm_contact_grant`: one row of a pasted access table, applied as the user (AGENT-BULK-ACTIONS).

PLAN-agent-bulk-actions-7nov.md. The row names its contact and customers by EXPLICIT keys only: the phone (exact
after `normalise_phone`), customer codes, or exact customer names with one match in the user's companies; nothing
is guessed (owner rule "no auto name-matching"). The access a row grants is the 26 Oct template of the Respond sheet
upload (`contact_access_sheet_service.TEMPLATE`) through the same engine (`contact_setup_engine._plan_contact` /
`_apply_contact`), so the agent and the upload give the same result. The whole template is written whatever the
confirming user could set by hand (DEALER-ACCESS-PORTAL Q2 a), and Business owner is the company's owner tag
(`TEMPLATE["owner_tags"]`), not the owner types written directly. A user holding only `edit_own` reaches only their
own accounts (active customers of their own sales agents). A phone not in the CRM is created as a contact in the
same transaction. `read_before` refuses (4xx) a row that cannot apply; the batch tool shows that message as the
row's skip reason.
"""
from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from typing import Any

from app.services.chatbot.agent import writes
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

GRANT = "crm_contact_grant"
EDIT = writes.CONTACT_EDIT
EVENT = writes.CONTACT_EVENT
LINK_SOURCE = "agent"
NO_OWN_ACCOUNT = "Name one of your accounts for this person (code or name)."
OTHER_ACCOUNT = "This person also has access through another account; ask the office to change their level."
#: Own scope, a contact another account also reaches (UAC A13): the settings someone else chose stay as they are;
#: only the additive facets (link, company, end_user, missing enquiry agents, retail segment) apply.
NON_ADDITIVE = frozenset({
    "chatbot_allowed", "chatbot_stock_allowed", "chatbot_eta_offset_applied", "escalation_allowed",
    "packing_list_allowed", "stock_check_mode", "stock_locations", "brands", "media",
})
COMPANY_WORDS = {"SRT": "Sorento", "MCH": "Mocha"}
#: The template facets the preview names in words, in this order (the role and the links have their own words).
_FACET_WORDS = (
    ("stock_check_mode", "stock check"),
    ("stock_locations", "stock locations"),
    ("brands", "brands"),
    ("market_segments", "retail segment"),
    ("media", "image replies"),
    ("agent_access", "enquiry agents"),
    ("chatbot_allowed", "AI replies on"),
    ("chatbot_stock_allowed", "stock replies"),
    ("chatbot_eta_offset_applied", "ETA offset"),
    ("escalation_allowed", "hand-over off"),
    ("packing_list_allowed", "packing list off"),
)
_FACET_LABELS = {"access_types": "Access types", "companies": "Companies", "customers": "Customer links"}


def _refuse(message: str):
    from app.services.error_handler import AppException

    return AppException(status_code=422, message=message, code="VALIDATION_ERROR")


def _company_words(codes) -> str:
    return ", ".join(COMPANY_WORDS.get(c, c) for c in codes)


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _new_contact(phone: str, name: str) -> SimpleNamespace:
    """A contact not yet in the CRM as the engine reads it: the switches at their column defaults."""
    from app.models.access import RespondContact

    columns = RespondContact.__table__.c
    out = SimpleNamespace(id=None, name=name, phone_number=phone)
    for col in ("chatbot_allowed", "chatbot_stock_allowed", "chatbot_eta_offset_applied", "escalation_allowed",
                "packing_list_allowed"):
        default = columns[col].default
        setattr(out, col, bool(default.arg) if default is not None else False)
    return out


MAX_CHOICES = 10


def _significant_words(text: str) -> list[str]:
    """The words of a business name that can identify it: 3+ characters, company suffix words left out."""
    from app.services.contact_setup_engine import _NAME_SUFFIXES

    return list(dict.fromkeys(
        w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in _NAME_SUFFIXES
    ))


def _customers(
    db, args: dict, companies: list[str], company_ids: dict[str, str], own_agents: list[str] | None = None,
) -> tuple[list, list[str], list[dict]]:
    """(customers, problems, choices) for what the row names, read under the user's companies (the caller set that
    scope). A code is exact (case and spaces aside). A name is exact (case and spaces aside) with exactly one match in
    the row's companies; otherwise the active accounts of those companies whose name CONTAINS the written text, or
    failing that (own scope only) carries its first significant word, are offered as a pick (never linked on their
    own, even one). A
    customer of a company the row does not name is refused: an account links only to a contact of its own company
    (sheet rule). `own_agents` (own scope, DEALER-ACCESS-PORTAL A2-A4): only active customers of those sales agents
    exist at all, so another salesperson's account reads exactly like one that does not exist."""
    from sqlalchemy import case, func, literal

    from app.models.company import Company
    from app.models.order import Customer

    code_of = {str(cid): code for cid, code in db.query(Company.id, Company.code)}
    wanted = set(companies)
    mine_ids = set(company_ids.values())
    out: dict[str, Any] = {}
    problems: list[str] = []
    choices: list[dict] = []
    where = "your accounts" if own_agents is not None else "your companies"

    def query(*columns):
        q = db.query(*columns)
        if own_agents is not None:
            q = q.filter(Customer.is_active.is_(True), Customer.sales_agent_id.in_(own_agents))
        return q

    def keep(rows: list, said: str, kind: str) -> bool:
        """True when `rows` linked one account; else records the reason and returns False."""
        if not rows:
            problems.append(f"No customer with the {kind} \"{said}\" in {where}.")
            return False
        mine = [r for r in rows if code_of.get(str(r.company_id)) in wanted]
        if not mine:
            other = _company_words(sorted({code_of.get(str(r.company_id), "another company") for r in rows}))
            problems.append(f"\"{said}\" is a {other} customer, but the row's company is {_company_words(companies)}.")
            return False
        if len(mine) > 1:
            problems.append(f"More than one customer has the {kind} \"{said}\"; give its customer code.")
            return False
        out[str(mine[0].id)] = mine[0]
        return True

    columns = (Customer.id, Customer.customer_code, Customer.customer_name, Customer.company_id)
    for code in dict.fromkeys(_clean(c) for c in args.get("customer_codes") or []):
        if code:
            keep(query(*columns).filter(func.lower(func.trim(Customer.customer_code)) == code.lower()).all(),
                 code, "code")
    norm = func.lower(func.regexp_replace(func.trim(Customer.customer_name), r"\s+", " ", "g"))

    def offer(name: str, found: list) -> None:
        choices.append({
            "written": name, "company": ", ".join(companies),
            "candidates": [{"code": r.customer_code, "name": r.customer_name} for r in found[:MAX_CHOICES]],
            "more": len(found) > MAX_CHOICES,
        })

    for name in dict.fromkeys(_clean(n) for n in args.get("customer_names") or []):
        if not name:
            continue
        exact = [r for r in query(*columns).filter(norm == name.lower()).all() if str(r.company_id) in mine_ids]
        if len(exact) == 1:
            out[str(exact[0].id)] = exact[0]
            continue
        contains = query(*columns).filter(Customer.is_active.is_(True), func.strpos(norm, name.lower()) > 0)
        found = contains.filter(Customer.company_id.in_(mine_ids)).order_by(Customer.customer_code).limit(MAX_CHOICES + 1).all()
        if found:
            offer(name, found)
            continue
        words = _significant_words(name) if own_agents is not None else []
        if words:
            # Own scope only (UAC A4): the account carries the written name's first significant word, most shared
            # words first. Whole-word matches (\m \M); the words are [a-z0-9] only.
            def has(w: str):
                return norm.op("~")(literal(rf"\m{w}\M"))

            shared = sum((case((has(w), 1), else_=0) for w in words), literal(0))
            found = (
                query(*columns).filter(Customer.is_active.is_(True), Customer.company_id.in_(mine_ids), has(words[0]))
                .order_by(shared.desc(), Customer.customer_code).limit(MAX_CHOICES + 1).all()
            )
            if found:
                offer(name, found)
                continue
        elsewhere = contains.with_entities(Customer.company_id).distinct().all()
        if elsewhere:
            other = _company_words(sorted({code_of.get(str(r.company_id), "another company") for r in elsewhere}))
            problems.append(f"\"{name}\" is a {other} customer, but the row's company is {_company_words(companies)}.")
        else:
            problems.append(f"No customer named \"{name}\" in {where}.")
    return list(out.values()), problems, choices


def _fits(choice: dict) -> str:
    n, noun = len(choice["candidates"]), choice.get("noun") or "account"
    count = f"more than 10 {noun}s" if choice.get("more") else f"{n} {noun}{'' if n == 1 else 's'}"
    return f"\"{choice['written']}\" fits {count}"


class NeedsChoice(AppException):
    """A row whose only problem is that a written name fits several records: the batch tool asks the user to pick.
    `choices` = [{"written", "company", "candidates": [{"code", "name"}], "more"}], plus "noun" ("account" when
    absent) and "kept" (the row's values that resolved exactly, which a re-proposal may keep) for a tag row."""

    def __init__(self, choices: list[dict]):
        noun = (choices[0].get("noun") if choices else None) or "account"
        super().__init__(status_code=409, message=f"Which {noun}? " + "; ".join(_fits(c) for c in choices), code="NEEDS_CHOICE")
        self.choices = choices


def _find_contact(db, phone: str):
    """The one contact holding this phone, stored in either form (+60 1... or 01...); None when there is none.
    Two contacts holding it is refused: the row would not know which to change, and a new one would be a third."""
    from sqlalchemy import func
    from sqlalchemy.orm import load_only

    from app.models.access import RespondContact
    from app.services import contact_access_sheet_service as sheet

    full = phone.lstrip("+")
    digits = func.regexp_replace(RespondContact.phone_number, r"\D", "", "g")
    rows = (
        db.query(RespondContact).options(load_only(*sheet.CONTACT_COLUMNS))
        .filter(digits.in_({full, full[1:]})).order_by(RespondContact.id).limit(2).all()
    )
    if len(rows) > 1:
        raise _refuse("More than one contact has this phone number; fix it on the contacts screen first.")
    return rows[0] if rows else None


def _is_staff(db, phone: str, contact_id: str | None) -> bool:
    """Is this phone staff (UAC A9, A16)? A CRM user's contact number (by digits, with or without the leading 6), or,
    for a contact already in the CRM, a user's or a sales agent's own contact. Never granted dealer access."""
    from sqlalchemy import func

    from app.models.base import company_scope
    from app.models.sales_agent import SalesAgent
    from app.models.user import User

    full = phone.lstrip("+")
    digits = func.regexp_replace(User.contact_number, r"\D", "", "g")
    with company_scope(db, None):
        if db.query(User.id).filter(digits.in_({full, full[1:]})).first() is not None:
            return True
        return contact_id is not None and (
            db.query(User.id).filter(User.respond_contact_id == contact_id).first() is not None
            or db.query(SalesAgent.id).filter(SalesAgent.contact_id == contact_id).first() is not None
        )


def plan(db, user: dict, args: dict) -> dict:
    """What the row would change, after every check. Raises the refusal the preview shows otherwise.
    Runs under every company the user is granted (the contact screens do the same)."""
    from app.models.base import get_company_scope
    from app.models.company import Company
    from app.models.media import ContactMediaLimit
    from app.services import contact_access_sheet_service as sheet
    from app.services import contact_setup_engine as engine
    from app.services.contact_access_copy_service import AccessSnapshot, Names, names_for, snapshots
    from app.services.contact_customer_service import list_links
    from app.services.contact_tag_service import owner_tag, tags_by_contact

    uid = str(user["id"])
    # Own scope (edit_own without edit): only the user's own accounts exist for this row (UAC A2-A4, A10).
    own_agents = None if writes._permitted(db, uid, EDIT) else writes._own_agent_ids(db, uid)
    problems: list[str] = []
    phone = engine.normalise_phone(args.get("phone"))
    if phone is None:
        problems.append(f"Phone \"{_clean(args.get('phone'))}\" is not a Malaysian mobile number.")
    name = _clean(args.get("name"))[:255]
    role = args.get("role")
    if role not in ("owner", "employee"):
        # The model reads the access word; a word that is neither role is never forced into one (owner card Q3).
        said = _clean(args.get("access_as_written"))[:60] or "not given"
        problems.append(f"Unknown access: {said}.")
    companies = list(dict.fromkeys(_clean(c).upper() for c in args.get("companies") or []))
    unknown = [c for c in companies if c not in sheet.TEMPLATE["companies"].values()]
    company_ids: dict[str, str] = {}
    customers: list = []
    choices: list[dict] = []
    if unknown or not companies:
        problems.append("Name the company as SRT (Sorento) or MCH (Mocha).")
    else:
        companies = [c for c in sheet.COMPANY_ORDER if c in companies]
        company_ids = {code: str(cid) for cid, code in db.query(Company.id, Company.code).filter(Company.code.in_(companies))}
        scope = get_company_scope(db)
        outside = [c for c in companies if c not in company_ids or (isinstance(scope, frozenset) and company_ids[c] not in scope)]
        if outside:
            problems.append(f"{_company_words(outside)} is not one of your companies.")
        else:
            customers, found, choices = _customers(db, args, companies, company_ids, own_agents)
            problems += found
    if problems:
        problems += [_fits(c) for c in choices]
        raise _refuse("; ".join(p.rstrip(".") for p in problems) + ".")
    if choices:
        raise NeedsChoice(choices)
    if own_agents is not None and not customers:
        raise _refuse(NO_OWN_ACCOUNT)  # UAC A12: no grant without one of the user's own accounts
    # Business owner is the company's owner tag (UAC A6); a missing or switched-off tag refuses the row (A7). Checked
    # once the row is otherwise ready: the row's own problems and its account pick come first.
    tags: list = []
    if role == "owner":
        missing = []
        for code in companies:
            tag = owner_tag(db, code)
            if tag is None:
                missing.append(f"The \"{sheet.TEMPLATE['owner_tags'][code]}\" tag is missing; ask the office")
            else:
                tags.append(tag)
        if missing:
            raise _refuse("; ".join(missing) + ".")
    contact = _find_contact(db, phone)
    if _is_staff(db, phone, str(contact.id) if contact is not None else None):
        raise _refuse("This number belongs to a staff member.")
    # Own scope: links to accounts that are not the user's own, counted, never named (A10, A13, A14, B3).
    others = writes._not_own_links(db, uid, str(contact.id)) if own_agents is not None and contact is not None else set()
    if others and role == "owner":
        raise _refuse(OTHER_ACCOUNT)  # UAC A14: promotion is as restricted as demotion
    # The whole template is written whatever the confirming user could set by hand (UAC A5, owner Q2 a), except on a
    # contact another account reaches too (A13): for anyone acting, so an own-scope console operator acting for a
    # `.edit` user still writes only the additive facets (security review L2).
    operator = str(user.get("operator_user_id") or "")
    shared = bool(others) or (
        contact is not None and bool(operator) and operator != uid and not writes._permitted(db, operator, EDIT)
        and bool(writes._not_own_links(db, operator, str(contact.id)))
    )
    skip = NON_ADDITIVE if shared else frozenset()
    world = sheet._world(db, set(companies))
    if contact is not None:
        cid = str(contact.id)
        snaps = snapshots(db, [contact])
        snap, names = snaps[cid], names_for(db, snaps.values())
        media = db.query(ContactMediaLimit.contact_id, ContactMediaLimit.is_allowed).filter(
            ContactMediaLimit.contact_id == cid, ContactMediaLimit.modality == sheet.TEMPLATE["media_modality"]
        ).first()
        held = sorted(str(link.customer_id) for link in list_links(db, cid))
        subject = contact
    else:
        cid, snap, names, media, held = "", AccessSnapshot(contact_id="", label=phone), Names(), None, []
        subject = _new_contact(phone, name)
    # The template base only; the owner types come from the owner tags added on confirm.
    desired = engine.Desired(phone=phone, name=name, rows=[], companies=set(companies), owner_companies=set())
    changes, todo = engine._plan_contact(db, subject, snap, desired, names, world, sheet.TEMPLATE, media, skip)
    changed = [c for c in changes if c["changed"]]
    add_links = [c for c in customers if str(c.id) not in held]
    held_tags = tags_by_contact(db, [cid]).get(cid, []) if cid else []
    add_tags = [t for t in tags if str(t.id) not in {h["id"] for h in held_tags}]
    if contact is not None and not changed and not add_links and not add_tags:
        raise _refuse("Already has this access; nothing to change.")

    facets = {c["facet"] for c in changed}
    lines = [] if contact is not None else ["create contact"]
    if "access_types" in facets or contact is None or add_tags:
        lines.append(f"{'Business owner' if role == 'owner' else 'Employee'} ({_company_words(companies)})")
    if "companies" in facets:
        added = [code for code, i in company_ids.items() if i in set(todo["companies"])]
        lines.append(f"add company {_company_words(added)}")
    lines += [f"link {c.customer_code} {_clean(c.customer_name)}".strip() for c in add_links]
    if others:
        # Add-only beside it; the other account is never named (UAC A10, owner Q5 a).
        lines.append("also has access through another account")
    extra = [word for facet, word in _FACET_WORDS if facet in facets]
    if extra:
        lines.append("template: " + ", ".join(extra))
    if shared:
        lines.append("kept as they are: AI replies, stock, brands and media (another account also has this person)")
    # `targets`: the customers the row resolved to, so a rename between preview and confirm fails the row. Own scope:
    # another account's link is only counted (B3).
    before = {
        "contact_id": cid, "types": sorted(snap.access_types), "companies": sorted(snap.companies),
        "links": [h for h in held if h not in others], "targets": sorted(str(c.id) for c in customers),
    }
    if own_agents is not None:
        before["other_links"] = len(others)
    return {
        "phone": phone, "name": name or (contact.name if contact is not None else "") or "", "contact": contact,
        "contact_id": cid, "desired": desired, "todo": todo, "changed": changed, "add_links": add_links,
        "lines": lines, "snap": snap, "held": held, "add_tags": add_tags, "held_tags": [h["name"] for h in held_tags],
        "before": before,
    }


def _read_before(db, user: dict, args: dict) -> dict:
    from app.services.company_scope_resolver import grants_scope

    with grants_scope(db, str(user["id"])):
        p = plan(db, user, args)
    return {
        **p["before"],
        "_show": {
            "phone": p["phone"], "name": p["name"], "contact": "existing" if p["contact_id"] else "new",
            "changes": p["lines"],
        },
    }


def _summary(args: dict, before: dict) -> str:
    who = f"{writes._line(before['phone'])} {writes._line(before['name'])}".strip()
    return f"{who} ({before['contact']}): " + "; ".join(writes._line(c) for c in before["changes"])


def _preview(args: dict, shown: dict | None) -> dict:
    """The row's cells in the preview table; `shown` is None for a row that was skipped."""
    if shown is None:
        return {"Phone": _clean(args.get("phone")), "Name": _clean(args.get("name"))}
    return {
        "Phone": shown.get("phone") or "", "Name": shown.get("name") or "", "Contact": shown.get("contact") or "",
        "Will change": "; ".join(shown.get("changes") or []),
    }


def _batch_key(args: dict) -> str | None:
    from app.services.contact_setup_engine import normalise_phone

    return normalise_phone(args.get("phone")) if isinstance(args, dict) else None


def _words(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v) for v in value) or "none"
    return "none" if value in (None, "") else str(value)


def _execute(db, user: dict, args: dict) -> dict:
    from app.models.access import RespondContact
    from app.services import audit_service, contact_customer_service
    from app.services import contact_access_sheet_service as sheet
    from app.services import contact_setup_engine as engine
    from app.services.company_scope_resolver import grants_scope

    uid = str(user["id"])
    with grants_scope(db, uid):
        p = plan(db, user, args)
        created = False
        if p["contact"] is None:
            from app.services.respond_workspace_service import RespondWorkspaceService

            workspace = RespondWorkspaceService(db).get_default()
            row = RespondContact(
                phone_number=p["phone"], name=p["name"] or None,
                workspace_id=str(workspace.id) if workspace is not None else None,
            )
            db.add(row)
            db.flush()
            created = True
            p = plan(db, user, args)  # the same plan, now against the real (empty) contact
        cid = p["contact_id"]
        plain = SimpleNamespace(id=cid, name=p["name"], phone_number=p["phone"])
        if p["changed"]:
            engine._apply_contact(db, plain, p["desired"], p["todo"], sheet.TEMPLATE, uid)
        for customer in p["add_links"]:
            contact_customer_service.link_customer(db, cid, str(customer.id), source=LINK_SOURCE, linked_by=uid)
        db.flush()
        if p["add_tags"]:
            from app.services.contact_tag_service import change_tags

            change_tags(db, p["contact"], add=p["add_tags"], actor_id=uid)
        shown = [
            {"field": _FACET_LABELS.get(c["facet"], c["facet"].replace("_", " ").capitalize()),
             "before": _words(c["before"]), "after": _words(c["after"])}
            for c in p["changed"]
        ]
        if p["add_tags"]:
            shown.append({
                "field": "Tags", "before": _words(p["held_tags"]),
                "after": _words([*p["held_tags"], *(t.name for t in p["add_tags"])]),
            })
        if p["add_links"]:
            shown.append({
                "field": "Customer links", "before": _words([]) if not p["held"] else f"{len(p['held'])} linked",
                "after": _words([f"{c.customer_code}" for c in p["add_links"]]),
            })
        audit_service.record(
            db,
            event=EVENT,
            entity_type="respond_contacts",
            entity_id=cid,
            old_values={s["field"]: s["before"] for s in shown},
            new_values={**{s["field"]: s["after"] for s in shown}, **({"Contact": "created"} if created else {})},
            description=f"Agent access grant for {p['phone']} from a pasted table",
        )
    db.commit()
    if created:
        # The screen's create also gives the agents flagged for new contacts (`ContactService.create_contact`).
        try:
            from app.services.contact_service import ContactService

            ContactService(db).assign_default_agents_to_contact(db.get(RespondContact, cid))
            db.commit()
        except Exception:  # noqa: BLE001 - the grant is committed; the defaults are best effort, as on the screen
            logger.warning("agent: default agents for a new contact failed", exc_info=True)
            db.rollback()
    if not db.query(RespondContact.respond_io_id).filter(RespondContact.id == cid).scalar():
        # Instant (UAC B1, V8): the worker finds or creates the person in Respond.io, so the bot answers their
        # first message instead of waiting for the 15 minute sync. The grant is committed either way.
        try:
            from app.services import queue_service
            from app.tasks.respond_io_tasks import ensure_respond_contact

            queue_service.enqueue_job(ensure_respond_contact, cid, queue_name="respond_io", job_timeout=120)
        except Exception:  # noqa: BLE001 - the sync picks the contact up later
            logger.warning("agent: enqueueing ensure_respond_contact failed", exc_info=True)
    return {"id": cid, "after": {"created": created, "changes": shown}}


def _changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    record = f"{shown.get('phone') or ''} {shown.get('name') or ''}".strip()
    out = [{"record": record, "field": "Contact", "before": "none", "after": "created"}] if after.get("created") else []
    return out + [{"record": record, **c} for c in after.get("changes") or []]


MAX_CUSTOMERS = 10
_TEXT_LIST = {"type": "array", "items": {"type": "string"}, "maxItems": MAX_CUSTOMERS}

writes.WRITES[GRANT] = writes.WriteDef(
    name=GRANT,
    # edit_own: the user's own accounts only (DEALER-ACCESS-PORTAL A1).
    user_permission=writes.CONTACT_SLUGS,
    schema={
        "type": "function",
        "function": {
            "name": GRANT,
            "description": (
                "Grant one dealer contact access from a row of a pasted table: the Respond sheet template for the "
                "role and companies, plus links to the named customers. A phone not in the CRM is created as a "
                "contact. For a table, use crm_batch_propose with this write and one row per person. A message "
                "that names people, their phones, Owner or Employee and the dealer is such a table too: one row "
                "per person, and the dealer's name goes in customer_names unless customer codes are given. Use the "
                "table's values as written: never invent a phone, code or name. Nothing changes until the user "
                "confirms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "The phone number exactly as in the table."},
                    "name": {"type": "string", "description": "The person's name from the table."},
                    "role": {
                        "type": "string", "enum": ["owner", "employee", "unknown"],
                        "description": (
                            "owner = the row says the person owns the business (Business owner, Owner, Pemilik, "
                            "Tauke); employee = the row says they are an employee (Employee, Staff, Pekerja). Any "
                            "other access word, or none: unknown (the row is then skipped, never guessed)."
                        ),
                    },
                    "access_as_written": {
                        "type": "string", "description": "The row's access cell exactly as written in the table.",
                    },
                    "companies": {
                        "type": "array", "items": {"type": "string"}, "maxItems": 2,
                        "description": "SRT for Sorento, MCH for Mocha (one or both).",
                    },
                    "customer_codes": {**_TEXT_LIST, "description": "Customer codes as written in the table."},
                    "customer_names": {
                        **_TEXT_LIST,
                        "description": "Customer names as written, when the table gives no code.",
                    },
                },
                "required": ["phone", "role", "companies"],
            },
        },
    },
    read_before=_read_before,
    summary=_summary,
    execute=_execute,
    record_key="",
    changes=_changes,
    batchable=True,
    preview=_preview,
    batch_key=_batch_key,
)
