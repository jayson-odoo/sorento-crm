"""Upload the Respond dealer-contact sheet and set each contact's access (BULK-CONTACT-ACCESS).

UAC ``documentation/plans/contacts/bulk-contact-access-26oct-acceptance-criteria.md``; contract
``PLAN-bulk-contact-access-26oct.md``. The planner and writer are the shared engine
(`contact_setup_engine`); this module owns the 26 Oct template, the CSV parse, the dealer
blocks (exact accounts across every company, ranked candidates when there is none) and the one
transaction that applies it all.
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.access import RespondContact, RespondContactCustomer
from app.models.company import Company
from app.models.order import Customer
from app.models.product import Brand
from app.models.sales_agent import SalesAgent
from app.services import audit_service
from app.services import contact_setup_engine as engine
from app.services.contact_access_copy_service import Names, names_for, snapshots
from app.services.contact_customer_service import link_customer
from app.services.error_handler import AppException

EVENT = "contact.access_sheet"
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000
MAX_CANDIDATES = 5
MIN_CANDIDATE_SCORE = 0.6
LINK_SOURCE = "access_sheet"

#: The 26 Oct template (UAC U4-U6). Codes, not data; brands come from `brands.dealer_company_id`.
TEMPLATE: dict[str, Any] = {
    "companies": {"Sorento Sdn Bhd": "SRT", "Mocha Sdn Bhd": "MCH"},
    "owner_types": {"SRT": ["dealer", "cabana_dealer"], "MCH": ["mocha_dealer"]},
    "base_type": "end_user",
    "locations": {"SRT": ["BRW", "MWH"], "MCH": ["HQ", "MOCHA-WH"]},
    "stock_mode": "availability",
    "stock_union": True,
    "stock_mode_facet": "stock_check_mode",  # the copy service's name, so facets_to_skip skips it
    "segment": "retail",
    "media_modality": "image",
    "agents": ["general_enquiries", "order_enquiries", "incoming_stock_enquiries"],
    "agent_valid_from": datetime(2026, 1, 1),
    "agent_valid_to": datetime(2026, 12, 31),
    "switches_on": ["chatbot_stock_allowed", "chatbot_eta_offset_applied", "chatbot_allowed"],
    "switches_off": ["escalation_allowed", "packing_list_allowed"],
}
COMPANY_ORDER = ("SRT", "MCH")
OWNER_WORDS = {"business owner": "owner", "employee": "employee"}
CONTACT_COLUMNS = engine.CONTACT_COLUMNS + (
    RespondContact.brand_ids, RespondContact.chatbot_allowed, RespondContact.regions,
    # read by `snapshots`; left out they would lazy-load once per contact
    RespondContact.chatbot_skip_period_questions, RespondContact.chatbot_files_as_links,
    RespondContact.requires_registered_project,
)
MAX_TAGS_CHARS = 1000
MAX_ALTS = 5
MAX_RANKED_BLOCKS = 300
TAG_MIN_BASES = 8


def _unprocessable(message: str, code: str = "INVALID_SHEET") -> AppException:
    return AppException(status_code=422, message=message, code=code)


# ---------------------------------------------------------------- parse


def _parse_tags(tags: str) -> dict:
    tokens = [t.strip() for t in (tags or "").split(",") if t.strip()]
    companies: dict[str, str] = {}  # company code -> agent text ("" when none named)
    roles: list[str] = []
    alts: list[str] = []
    seen_alts: set[str] = set()
    brand_tags = {k.lower(): v for k, v in TEMPLATE["companies"].items()}
    dealer = tokens[0] if tokens else ""
    rest = tokens[1:]
    i = 0
    while i < len(rest):
        token = rest[i]
        low = token.lower()
        if low in brand_tags:
            code = brand_tags[low]
            companies.setdefault(code, "")
            nxt = rest[i + 1] if i + 1 < len(rest) else None
            if nxt is not None and nxt.lower() not in brand_tags and nxt.lower() not in OWNER_WORDS:
                companies[code] = nxt
                i += 1
        elif low in OWNER_WORDS:
            roles.append(OWNER_WORDS[low])
        elif token not in seen_alts:
            seen_alts.add(token)
            alts.append(token)
        i += 1
    if dealer.lower() in brand_tags or dealer.lower() in OWNER_WORDS:
        dealer = ""
    return {
        "dealer": dealer,
        "companies": companies,
        "role": "owner" if "owner" in roles else ("employee" if roles else None),
        "alts": alts,
    }


def parse_respond_csv(data: bytes) -> list[dict]:
    """One dict per data row: line, name, phone_text, parsed tags, error (or None)."""
    if len(data) > MAX_BYTES:
        raise _unprocessable("That file is too large.", "FILE_TOO_LARGE")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _unprocessable("The file is not UTF-8 text.") from exc
    try:
        return _parse_rows(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise _unprocessable("The file is not a readable CSV.") from exc


def _parse_rows(reader) -> list[dict]:
    try:
        header = next(reader)
    except StopIteration:
        raise _unprocessable("The file is empty.") from None
    index = {h.strip().lower(): n for n, h in enumerate(header)}
    missing = [c for c in ("Phone Number", "Tags") if c.lower() not in index]
    if missing:
        raise _unprocessable(f"Missing column: {', '.join(missing)}.", "MISSING_COLUMN")

    def cell(record: list[str], column: str) -> str:
        n = index.get(column.lower())
        return record[n].strip() if n is not None and n < len(record) else ""

    rows: list[dict] = []
    seen_phones: dict[str, int] = {}
    for record in reader:
        if not any(c.strip() for c in record):
            continue
        if len(rows) >= MAX_ROWS:
            raise _unprocessable(f"More than {MAX_ROWS} rows.", "TOO_MANY_ROWS")
        parsed = _parse_tags(cell(record, "Tags"))
        phone_text = cell(record, "Phone Number")
        phone = engine.normalise_phone(phone_text) or re.sub(r"\D", "", phone_text) or None
        error = None
        if len(cell(record, "Tags")) > MAX_TAGS_CHARS:
            error = f"Tags are longer than {MAX_TAGS_CHARS} characters."
        elif len(parsed["alts"]) > MAX_ALTS:
            error = f"More than {MAX_ALTS} other dealer names."
        elif not phone:
            error = "No phone number."
        elif not _words(parsed["dealer"]):
            error = "No dealer name."
        elif not parsed["companies"]:
            error = "No Sorento or Mocha company tag."
        elif parsed["role"] is None:
            error = "No Business Owner or Employee tag."
        row = {
            "line": reader.line_num, "name": cell(record, "First Name"), "phone_text": phone_text,
            "phone": phone, "tags": parsed, "error": error,
        }
        if error is None:
            if phone in seen_phones:
                row["error"] = f"Same phone as line {seen_phones[phone]}."
            else:
                seen_phones[phone] = row["line"]
        rows.append(row)
    return rows


def parse_confirmed(raw: Optional[str]) -> Optional[dict[str, list[str]]]:
    if raw is None or raw == "":
        return None
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise _unprocessable("Confirmed accounts are not valid JSON.", "INVALID_CONFIRMED") from exc
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, list) and all(isinstance(i, str) for i in v)
        for k, v in value.items()
    ):
        raise _unprocessable("Confirmed accounts must map a dealer key to a list of account ids.", "INVALID_CONFIRMED")
    return value


# ---------------------------------------------------------------- world


def _world(db: Session, used: set) -> dict:
    """The companies, locations, agents and brands of the template, for the companies the sheet
    tags only (a caller granted Sorento alone can still run a Sorento-only sheet)."""
    rules = {
        **TEMPLATE,
        "companies": {k: v for k, v in TEMPLATE["companies"].items() if v in used},
        "locations": {c: w for c, w in TEMPLATE["locations"].items() if c in used},
    }
    try:
        world = engine._resolve_world(db, rules)
    except SystemExit as exc:
        raise _unprocessable(str(exc), "TEMPLATE_WORLD_MISSING") from exc
    by_company: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    code_of = {str(c.id): code for code, c in world["companies"].items()}
    for brand in db.query(Brand.id, Brand.brand_name, Brand.dealer_company_id).filter(
        Brand.is_active.is_(True), Brand.dealer_company_id.in_(list(code_of))
    ):
        by_company.setdefault(code_of[str(brand.dealer_company_id)], []).append(str(brand.id))
        names[str(brand.id)] = brand.brand_name
    world["brands"] = {c: sorted(ids) for c, ids in by_company.items()}
    world["brand_names"] = names
    return world


def _template_sets(world: dict, companies: set, role: str) -> dict:
    types = {TEMPLATE["base_type"]}
    if role == "owner":
        for c in companies:
            types |= set(TEMPLATE["owner_types"][c])
    return {
        "types": types,
        "companies": {str(world["companies"][c].id) for c in companies},
        "locations": {str(world["warehouses"][c][code].id) for c in companies for code in TEMPLATE["locations"][c]},
        "brands": {b for c in companies for b in world["brands"].get(c, ())},
    }


# ---------------------------------------------------------------- blocks and accounts


_SEGMENT_RE = re.compile(r"\[([^\]]*)\]|\(([^)]*)\)")
_DASH_RE = re.compile(r"\s+-(?:\s+|$)")


def _words(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _tag_form(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _split_name(name: str) -> tuple[str, list[str]]:
    """(the name proper, its other segments): bracket texts and the parts after ` - `."""
    raw = name or ""
    brackets = [(m.group(1) if m.group(1) is not None else m.group(2)).strip() for m in _SEGMENT_RE.finditer(raw)]
    rest = _SEGMENT_RE.sub(" ", raw)
    rest = re.sub(r"[\[(][^\])]*$", " ", rest)  # an unclosed bracket
    parts = [p.strip() for p in _DASH_RE.split(rest.strip()) if p.strip()]
    main = parts[0] if parts else ""
    return main, [*parts[1:], *brackets]


def _suffix_only(segment: str) -> bool:
    """A bracket such as `(M)` that holds only legal-suffix words is never part of the name."""
    words = _words(segment).split()
    return bool(words) and all(w in engine._NAME_SUFFIXES for w in words)


def _base_key(main: str) -> str:
    words = _words(main).split()
    if words and words[0] == "the":
        words = words[1:]
    while words and words[-1] in engine._NAME_SUFFIXES:
        words.pop()
    return " ".join(words)


def _account_tags(names: list[str]) -> frozenset:
    """Segment texts found on customers of at least TAG_MIN_BASES different base names (data, not a list)."""
    bases: dict[str, set] = {}
    for name in names:
        main, segments = _split_name(name)
        base = _base_key(main)
        for segment in segments:
            form = _tag_form(segment)
            if form:
                bases.setdefault(form, set()).add(base)
    return frozenset(form for form, found in bases.items() if len(found) >= TAG_MIN_BASES)


def _name_key(name: Optional[str], tags: frozenset) -> str:
    """The key a sheet dealer text and a customer name are matched on (UAC U8)."""
    main, segments = _split_name(name or "")
    keep = [
        _words(sg) for sg in segments
        if _tag_form(sg) not in tags and not _suffix_only(sg)
    ]
    key = " ".join(p for p in (_base_key(main), *keep) if p)
    return key or _words(name or "")


def _customers(db: Session) -> tuple[list[dict], frozenset]:
    agents = {str(a.id): a.sales_agent for a in db.query(SalesAgent.id, SalesAgent.sales_agent)}
    code_of = {str(c.id): c.code for c in db.query(Company.id, Company.code)}
    rows = []
    for c in db.query(
        Customer.id, Customer.customer_code, Customer.customer_name, Customer.company_id,
        Customer.is_active, Customer.sales_agent_id,
    ):
        rows.append({
            "id": str(c.id), "code": c.customer_code or "", "name": c.customer_name or "",
            "company_id": str(c.company_id) if c.company_id else None,
            "company_code": code_of.get(str(c.company_id)),
            "is_active": bool(c.is_active), "agent": agents.get(str(c.sales_agent_id)) if c.sales_agent_id else None,
        })
    tags = _account_tags([r["name"] for r in rows])
    for r in rows:
        r["norm"] = _name_key(r["name"], tags)
    return rows, tags


def _account(c: dict, match: str, score: Optional[float], proposed: bool, sheet_agent: Optional[str]) -> dict:
    return {
        "customer_id": c["id"], "customer_code": c["code"], "customer_name": c["name"],
        "company_code": c["company_code"], "is_active": c["is_active"], "sales_agent": c["agent"],
        "sheet_agent": sheet_agent or None, "match": match, "score": score, "proposed": proposed,
    }


def _build_blocks(db: Session, rows: list[dict], rank: bool) -> list[dict]:
    live = [r for r in rows if not r["error"]]
    if not live:
        return []
    customers, tags = _customers(db)
    blocks: dict[str, dict] = {}
    for row in live:
        key = _name_key(row["tags"]["dealer"], tags)
        block = blocks.setdefault(key, {
            "key": key, "dealer": row["tags"]["dealer"], "alt_dealers": [], "company_sets": [],
            "agents": {}, "rows": [],
        })
        for alt in row["tags"]["alts"]:
            if alt not in block["alt_dealers"]:
                block["alt_dealers"].append(alt)
        block["company_sets"].append(frozenset(row["tags"]["companies"]))
        for code, agent in row["tags"]["companies"].items():
            if agent and code not in block["agents"]:
                block["agents"][code] = agent
        block["rows"].append(row)

    wanted: set[str] = set()
    for key, block in blocks.items():
        block["texts"] = [t for t in dict.fromkeys([key, *(_name_key(a, tags) for a in block["alt_dealers"])]) if t]
        wanted.update(block["texts"])
    by_norm: dict[str, list[dict]] = {}
    for c in customers:
        if c["norm"] in wanted:
            by_norm.setdefault(c["norm"], []).append(c)
    flags = engine._merge_flags(
        db, {(c["company_id"], c["code"].strip().lower()) for group in by_norm.values() for c in group if c["company_id"]}
    )
    by_company: dict[str, list[dict]] = {}
    for c in customers:
        if c["norm"]:
            by_company.setdefault(c["company_code"], []).append(c)

    ranked = 0
    for key, block in blocks.items():
        union = set().union(*block["company_sets"])
        block["companies"] = [c for c in COMPANY_ORDER if c in union]
        block["warnings"] = ["rows_disagree"] if len(set(block["company_sets"])) > 1 else []
        exact: dict[str, dict] = {}
        for text in block["texts"]:
            for c in by_norm.get(text, ()):
                survives, held = flags.get(c["id"], ("Y", "N"))
                if survives == "Y" and held == "N":
                    exact[c["id"]] = c
        accounts = [
            _account(c, "exact", 1.0, c["is_active"], block["agents"].get(c["company_code"]))
            for c in sorted(exact.values(), key=lambda c: (c["company_code"] or "", c["code"]))
        ]
        covered = {c["company_code"] for c in exact.values()}
        missing = [c for c in block["companies"] if c not in covered]
        if missing and rank and ranked < MAX_RANKED_BLOCKS:
            ranked += 1
            matchers = []
            for text in block["texts"]:
                m = SequenceMatcher(None)
                m.set_seq2(text)
                matchers.append(m)
            for code in missing:
                scored = []
                for c in by_company.get(code, ()):
                    if c["id"] in exact:
                        continue
                    best = 0.0
                    for m in matchers:
                        m.set_seq1(c["norm"])
                        if m.real_quick_ratio() < MIN_CANDIDATE_SCORE or m.quick_ratio() < MIN_CANDIDATE_SCORE:
                            continue
                        best = max(best, m.ratio())
                    if best >= MIN_CANDIDATE_SCORE:
                        scored.append((best, c))
                scored.sort(key=lambda sc: (-sc[0], sc[1]["name"], sc[1]["id"]))
                for score, c in scored[:MAX_CANDIDATES]:
                    accounts.append(_account(c, "candidate", round(score, 3), False, block["agents"].get(code)))
        block["accounts"] = accounts
        if not missing:
            block["status"] = "exact"
        elif not rank:  # an apply never ranks; the preview already showed the candidates
            block["status"] = "pick"
        else:
            block["status"] = "pick" if any(a["match"] == "candidate" for a in accounts) else "none"
    return list(blocks.values())


def _validate_confirmed(db: Session, confirmed: dict[str, list[str]]) -> None:
    ids = {i for v in confirmed.values() for i in v}
    for i in ids:
        try:
            uuid.UUID(i)
        except ValueError as exc:
            raise _unprocessable("A confirmed account is not valid.", "INVALID_CONFIRMED") from exc
    if not ids:
        return
    found = {str(r[0]) for r in db.query(Customer.id).filter(Customer.id.in_(ids))}
    if found != ids:
        raise _unprocessable("A confirmed account was not found.", "INVALID_CONFIRMED")


# ---------------------------------------------------------------- plan


def _contact_entry(row: dict) -> dict:
    companies = [c for c in COMPANY_ORDER if c in row["tags"]["companies"]]
    return {
        "line": row["line"], "name": row["name"], "phone": row["phone_text"], "in_crm": False,
        "contact_id": None, "role": row["tags"]["role"], "companies": companies,
        "template": "+".join(companies) + f" {row['tags']['role']}", "status": "skipped",
        "skip_reason": None, "changes": [], "warnings": [], "not_applied": [],
    }


def _plan(db: Session, rows: list[dict], confirmed: Optional[dict], skip: frozenset, rank: bool) -> dict:
    used = {c for r in rows if not r["error"] for c in r["tags"]["companies"]}
    world = _world(db, used) if used else None
    blocks = _build_blocks(db, rows, rank)
    if confirmed is None:  # a preview: every exact block with its proposed accounts
        confirmed = {b["key"]: [a["customer_id"] for a in b["accounts"] if a["proposed"]] for b in blocks if b["status"] == "exact"}
    else:
        _validate_confirmed(db, confirmed)

    phones = {r["phone"] for r in rows if not r["error"]}
    found, ambiguous = engine._find_contacts(db, phones, CONTACT_COLUMNS) if phones else ({}, set())
    snaps = snapshots(db, found.values()) if found else {}
    names = names_for(db, snaps.values()) if found else Names()
    media = {}
    links: dict[str, set] = {}
    customer_label: dict[str, str] = {}
    if found:
        ids = [str(c.id) for c in found.values()]
        from app.models.media import ContactMediaLimit

        media = {
            str(m.contact_id): m for m in db.query(ContactMediaLimit.contact_id, ContactMediaLimit.is_allowed).filter(
                ContactMediaLimit.contact_id.in_(ids), ContactMediaLimit.modality == TEMPLATE["media_modality"])
        }
        for cid, customer_id in db.query(RespondContactCustomer.contact_id, RespondContactCustomer.customer_id).filter(
            RespondContactCustomer.contact_id.in_(ids)
        ):
            links.setdefault(str(cid), set()).add(str(customer_id))
        wanted_ids = {i for s in links.values() for i in s} | {i for v in confirmed.values() for i in v}
        for b in blocks:
            for a in b["accounts"]:
                customer_label[a["customer_id"]] = f"{a['customer_code']} {a['customer_name']}".strip()
        for c in db.query(Customer.id, Customer.customer_code, Customer.customer_name).filter(
            Customer.id.in_(wanted_ids - set(customer_label))
        ) if wanted_ids - set(customer_label) else ():
            customer_label[str(c.id)] = f"{c.customer_code} {c.customer_name}".strip()

    out_blocks, plans = [], []
    desired_of: dict[str, engine.Desired] = {}
    for block in blocks:
        entries = []
        for row in block["rows"]:
            entry = _contact_entry(row)
            contact = found.get(row["phone"])
            if contact is None:
                entry["skip_reason"] = "ambiguous_phone" if row["phone"] in ambiguous else "not_in_crm"
            elif block["key"] not in confirmed:
                entry.update(in_crm=True, contact_id=str(contact.id), skip_reason="dealer_not_confirmed")
            else:
                cid = str(contact.id)
                comps = {c for c in row["tags"]["companies"]}
                d = engine.Desired(
                    phone=row["phone"], name=row["name"], rows=[row["line"]], companies=comps,
                    owner_companies=comps if row["tags"]["role"] == "owner" else set(),
                )
                snap = snaps[cid]
                changes, todo = engine._plan_contact(db, contact, snap, d, names, world, TEMPLATE, media.get(cid), skip)
                held = links.get(cid, set())
                add_links = [i for i in confirmed[block["key"]] if i not in held]
                after = sorted({*held, *confirmed[block["key"]]})
                if add_links:
                    changes.append({
                        "facet": "customers", "changed": True, "status": "add", "contact_id": cid,
                        "before": sorted(customer_label.get(i, "other account") for i in held),
                        "after": sorted(customer_label.get(i, "other account") for i in after),
                    })
                tpl = _template_sets(world, comps, row["tags"]["role"])
                warnings = []
                snap_locations = set(snap.stock.include or ()) if snap.stock else set()
                if (
                    set(snap.access_types) - tpl["types"] or set(snap.companies) - tpl["companies"]
                    or snap_locations - tpl["locations"] or set(snap.brands) - tpl["brands"]
                ):
                    warnings.append("holds_more")
                changed = [c for c in changes if c["changed"]]
                entry.update(
                    in_crm=True, contact_id=cid, skip_reason=None, warnings=warnings,
                    status="applied" if changed else "no_change",
                    changes=[{"facet": c["facet"], "before": c["before"], "after": c["after"]} for c in changed],
                    not_applied=sorted({c["facet"] for c in changes if c["status"] == "not_applied"}),
                )
                plans.append({
                    "plain": SimpleNamespace(id=cid, name=contact.name, phone_number=contact.phone_number),
                    "d": d, "todo": todo, "changed": changed, "add_links": add_links, "entry": entry,
                })
            entries.append(entry)
        out_blocks.append({
            "key": block["key"], "dealer": block["dealer"], "alt_dealers": block["alt_dealers"],
            "companies": block["companies"], "status": block["status"], "warnings": block["warnings"],
            "accounts": block["accounts"], "contacts": entries,
        })

    contacts = [c for b in out_blocks for c in b["contacts"]]
    errors = [{"line": r["line"], "reason": r["error"]} for r in rows if r["error"]]
    counts = {
        "rows": len(rows), "row_errors": len(errors),
        "contacts_found": sum(1 for c in contacts if c["in_crm"]),
        "not_in_crm": sum(1 for c in contacts if c["skip_reason"] == "not_in_crm"),
        "ambiguous": sum(1 for c in contacts if c["skip_reason"] == "ambiguous_phone"),
        "already_configured": sum(
            1 for c in found.values() if snaps[str(c.id)].access_types or links.get(str(c.id))
        ),
        "blocks": len(out_blocks),
        "blocks_exact": sum(1 for b in out_blocks if b["status"] == "exact"),
        "blocks_pick": sum(1 for b in out_blocks if b["status"] == "pick"),
        "blocks_none": sum(1 for b in out_blocks if b["status"] == "none"),
        "applied": sum(1 for c in contacts if c["status"] == "applied"),
        "no_change": sum(1 for c in contacts if c["status"] == "no_change"),
        "skipped": sum(1 for c in contacts if c["status"] == "skipped") + len(errors),
    }
    return {"counts": counts, "errors": errors, "blocks": out_blocks, "_plans": plans, "_confirmed": confirmed}


def run(
    db: Session, data: bytes, *, dry_run: bool, confirmed_raw: Optional[str], actor_id: Optional[str], skip: frozenset
) -> dict:
    """Preview (writes nothing) or apply (one transaction, one commit; any error rolls it all back)."""
    rows = parse_respond_csv(data)
    confirmed = parse_confirmed(confirmed_raw)
    if not dry_run and confirmed is None:
        raise _unprocessable("Confirmed accounts are required to apply.", "CONFIRMED_REQUIRED")
    try:
        result = _plan(db, rows, confirmed, skip, rank=dry_run)
        plans = result.pop("_plans")
        confirmed_used = result.pop("_confirmed")
        result = {"dry_run": dry_run, **result}
        if dry_run:
            return result
        for p in plans:
            if not p["changed"]:
                continue
            engine._apply_contact(db, p["plain"], p["d"], p["todo"], TEMPLATE, actor_id)
            for customer_id in p["add_links"]:
                link_customer(db, p["plain"].id, customer_id, source=LINK_SOURCE, linked_by=actor_id)
            audit_service.record(
                db,
                event=EVENT,
                entity_type="respond_contacts",
                entity_id=p["plain"].id,
                old_values={c["facet"]: c["before"] for c in p["changed"]},
                new_values={c["facet"]: c["after"] for c in p["changed"]},
                description="Contact access set from the Respond sheet upload",
            )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
