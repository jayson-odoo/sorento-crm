"""`crm_contact_grant`: one row of a pasted access table, applied as the user (AGENT-BULK-ACTIONS).

PLAN-agent-bulk-actions-7nov.md. The row names its contact and customers by EXPLICIT keys only: the phone (exact
after `normalise_phone`), customer codes, or exact customer names with one match in the user's companies; nothing
is guessed (owner rule "no auto name-matching"). The access a row grants is the 26 Oct template of the Respond sheet
upload (`contact_access_sheet_service.TEMPLATE`) through the same engine (`contact_setup_engine._plan_contact` /
`_apply_contact`), so the agent and the upload give the same result; facets the user could not set on screen
(`contact_access_copy_service.facets_to_skip`) are planned as "not applied", as the upload does. A phone not in the
CRM is created as a contact in the same transaction. `read_before` refuses (4xx) a row that cannot apply; the batch
tool shows that message as the row's skip reason.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from app.services.chatbot.agent import writes
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

GRANT = "crm_contact_grant"
EDIT = writes.CONTACT_EDIT
EVENT = writes.CONTACT_EVENT
LINK_SOURCE = "agent"
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


def _customers(db, args: dict, companies: list[str], company_ids: dict[str, str]) -> tuple[list, list[str], list[dict]]:
    """(customers, problems, choices) for what the row names, read under the user's companies (the caller set that
    scope). A code is exact (case and spaces aside). A name is exact (case and spaces aside) with exactly one match in
    the row's companies; otherwise the active accounts of those companies whose name CONTAINS the written text are
    offered as a pick (never linked on their own, even one). A customer of a company the row does not name is
    refused: an account links only to a contact of its own company (sheet rule)."""
    from sqlalchemy import func

    from app.models.company import Company
    from app.models.order import Customer

    code_of = {str(cid): code for cid, code in db.query(Company.id, Company.code)}
    wanted = set(companies)
    mine_ids = set(company_ids.values())
    out: dict[str, Any] = {}
    problems: list[str] = []
    choices: list[dict] = []

    def keep(rows: list, said: str, kind: str) -> bool:
        """True when `rows` linked one account; else records the reason and returns False."""
        if not rows:
            problems.append(f"No customer with the {kind} \"{said}\" in your companies.")
            return False
        mine = [r for r in rows if code_of.get(str(r.company_id)) in wanted]
        if not mine:
            where = _company_words(sorted({code_of.get(str(r.company_id), "another company") for r in rows}))
            problems.append(f"\"{said}\" is a {where} customer, but the row's company is {_company_words(companies)}.")
            return False
        if len(mine) > 1:
            problems.append(f"More than one customer has the {kind} \"{said}\"; give its customer code.")
            return False
        out[str(mine[0].id)] = mine[0]
        return True

    columns = (Customer.id, Customer.customer_code, Customer.customer_name, Customer.company_id)
    for code in dict.fromkeys(_clean(c) for c in args.get("customer_codes") or []):
        if code:
            keep(db.query(*columns).filter(func.lower(func.trim(Customer.customer_code)) == code.lower()).all(),
                 code, "code")
    norm = func.lower(func.regexp_replace(func.trim(Customer.customer_name), r"\s+", " ", "g"))
    for name in dict.fromkeys(_clean(n) for n in args.get("customer_names") or []):
        if not name:
            continue
        exact = [r for r in db.query(*columns).filter(norm == name.lower()).all() if str(r.company_id) in mine_ids]
        if len(exact) == 1:
            out[str(exact[0].id)] = exact[0]
            continue
        contains = (
            db.query(*columns).filter(Customer.is_active.is_(True), func.strpos(norm, name.lower()) > 0)
        )
        found = contains.filter(Customer.company_id.in_(mine_ids)).order_by(Customer.customer_code).limit(MAX_CHOICES + 1).all()
        if found:
            choices.append({
                "written": name, "company": ", ".join(companies),
                "candidates": [{"code": r.customer_code, "name": r.customer_name} for r in found[:MAX_CHOICES]],
                "more": len(found) > MAX_CHOICES,
            })
            continue
        elsewhere = contains.all()
        if elsewhere:
            where = _company_words(sorted({code_of.get(str(r.company_id), "another company") for r in elsewhere}))
            problems.append(f"\"{name}\" is a {where} customer, but the row's company is {_company_words(companies)}.")
        else:
            problems.append(f"No customer named \"{name}\" in your companies.")
    return list(out.values()), problems, choices


class NeedsChoice(AppException):
    """A row whose only problem is that a written customer name fits several accounts: the batch tool asks the user
    to pick. `choices` = [{"written", "company", "candidates": [{"code", "name"}], "more"}]."""

    def __init__(self, choices: list[dict]):
        names = ", ".join(f"\"{c['written']}\"" for c in choices)
        super().__init__(status_code=409, message=f"Which account? {names} fits several accounts.", code="NEEDS_CHOICE")
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


def plan(db, user: dict, args: dict) -> dict:
    """What the row would change, after every check. Raises the refusal the preview shows otherwise.
    Runs under every company the user is granted (the contact screens do the same)."""
    from app.models.base import get_company_scope
    from app.models.company import Company
    from app.models.media import ContactMediaLimit
    from app.services import contact_access_sheet_service as sheet
    from app.services import contact_setup_engine as engine
    from app.services.contact_access_copy_service import AccessSnapshot, Names, facets_to_skip, names_for, snapshots
    from app.services.contact_customer_service import list_links

    uid = str(user["id"])
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
            customers, found, choices = _customers(db, args, companies, company_ids)
            problems += found
    if problems:
        problems += [f"\"{c['written']}\" fits {'more than 10' if c['more'] else len(c['candidates'])} accounts" for c in choices]
        raise _refuse("; ".join(p.rstrip(".") for p in problems) + ".")
    if choices:
        raise NeedsChoice(choices)
    contact = _find_contact(db, phone)
    # Only what everyone acting may set on screen: the linked user and the console operator (security review B1).
    acting = dict.fromkeys(i for i in (uid, user.get("operator_user_id")) if i)
    skip = frozenset().union(*(facets_to_skip(db, i) for i in acting))
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
    desired = engine.Desired(
        phone=phone, name=name, rows=[], companies=set(companies),
        owner_companies=set(companies) if role == "owner" else set(),
    )
    changes, todo = engine._plan_contact(db, subject, snap, desired, names, world, sheet.TEMPLATE, media, skip)
    changed = [c for c in changes if c["changed"]]
    add_links = [c for c in customers if str(c.id) not in held]
    not_applied = sorted({c["facet"] for c in changes if c["status"] == "not_applied"})
    if contact is not None and not changed and not add_links:
        raise _refuse("Already has this access; nothing to change.")

    facets = {c["facet"] for c in changed}
    lines = [] if contact is not None else ["create contact"]
    if "access_types" in facets or contact is None:
        lines.append(f"{'Business owner' if role == 'owner' else 'Employee'} ({_company_words(companies)})")
    if "companies" in facets:
        added = [code for code, i in company_ids.items() if i in set(todo["companies"])]
        lines.append(f"add company {_company_words(added)}")
    lines += [f"link {c.customer_code} {_clean(c.customer_name)}".strip() for c in add_links]
    extra = [word for facet, word in _FACET_WORDS if facet in facets]
    if extra:
        lines.append("template: " + ", ".join(extra))
    if not_applied:
        words = dict(_FACET_WORDS) | {"companies": "companies"}
        lines.append("not applied (needs more access): " + ", ".join(dict.fromkeys(words.get(f, f) for f in not_applied)))
    return {
        "phone": phone, "name": name or (contact.name if contact is not None else "") or "", "contact": contact,
        "contact_id": cid, "desired": desired, "todo": todo, "changed": changed, "add_links": add_links,
        "lines": lines, "snap": snap, "held": held,
        # `targets`: the customers the row resolved to, so a rename between preview and confirm fails the row.
        "before": {
            "contact_id": cid, "types": sorted(snap.access_types), "companies": sorted(snap.companies), "links": held,
            "targets": sorted(str(c.id) for c in customers),
        },
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
        shown = [
            {"field": _FACET_LABELS.get(c["facet"], c["facet"].replace("_", " ").capitalize()),
             "before": _words(c["before"]), "after": _words(c["after"])}
            for c in p["changed"]
        ]
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
    return {"id": cid, "after": {"created": created, "changes": shown}}


def _changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    record = f"{shown.get('phone') or ''} {shown.get('name') or ''}".strip()
    out = [{"record": record, "field": "Contact", "before": "none", "after": "created"}] if after.get("created") else []
    return out + [{"record": record, **c} for c in after.get("changes") or []]


MAX_CUSTOMERS = 10
_TEXT_LIST = {"type": "array", "items": {"type": "string"}, "maxItems": MAX_CUSTOMERS}

writes.WRITES[GRANT] = writes.WriteDef(
    name=GRANT,
    user_permission=EDIT,
    schema={
        "type": "function",
        "function": {
            "name": GRANT,
            "description": (
                "Grant one dealer contact access from a row of a pasted table: the Respond sheet template for the "
                "role and companies, plus links to the named customers. A phone not in the CRM is created as a "
                "contact. For a table, use crm_batch_propose with this write and one row per person. Use the "
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
                        "description": "Customer names as written, when the table gives no code (exact names only).",
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
