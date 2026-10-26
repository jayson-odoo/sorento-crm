"""The contact access engine shared by `scripts/contact_bulk_setup.py` (the crew-run CLI over the
owner's 4 Oct dealer Excel) and `app/services/contact_access_sheet_service.py` (the in-app Respond
sheet upload, BULK-CONTACT-ACCESS). Moved out of the script, not rewritten: the script imports
every name back. `app/` never imports `scripts/`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import load_only

from app.models.access import (
    AccessAgent,
    ContactAgentAccess,
    RespondContact,
    StockVisibilityPolicy,
    respond_contact_access_types,
    respond_contact_market_segments,
)
from app.models.company import Company, RespondContactCompany
from app.models.inventory import Warehouse
from app.models.media import ContactMediaLimit
from app.services.contact_access_copy_service import (
    Names,
    StockOverride,
    locations_text,
)

# Only the contact columns this script reads: prod can lag main, and a column the script never
# uses must not make it fail.
CONTACT_COLUMNS = (
    RespondContact.id, RespondContact.name, RespondContact.phone_number, RespondContact.chatbot_profile,
    RespondContact.chatbot_stock_allowed, RespondContact.notify_salesman, RespondContact.packing_list_allowed,
    RespondContact.chatbot_eta_offset_applied, RespondContact.escalation_allowed,
)



@dataclass
class Desired:
    phone: str
    name: str
    rows: list = field(default_factory=list)
    companies: set = field(default_factory=set)
    owner_companies: set = field(default_factory=set)



def normalise_phone(value: Any) -> Optional[str]:
    """`+601` + 8 or 9 digits, or None when the value is not a Malaysian mobile number."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    digits = re.sub(r"\D", "", str(value))
    if digits.startswith("60"):
        pass
    elif digits.startswith("0"):
        digits = "6" + digits
    elif digits.startswith("1"):
        digits = "60" + digits  # a spreadsheet dropped the leading zero
    else:
        return None
    return "+" + digits if re.fullmatch(r"601\d{8,9}", digits) else None


def _find_contacts(db, phones, columns=CONTACT_COLUMNS) -> tuple[dict[str, RespondContact], set[str]]:
    """(normalised phone -> contact, ambiguous phones), matched on the digits of
    respond_contacts.phone_number. Two contacts with the same digits: neither is returned."""
    wanted = {p: re.sub(r"\D", "", p) for p in phones}
    if not wanted:
        return {}, set()
    digits = func.regexp_replace(RespondContact.phone_number, r"\D", "", "g")
    by_digits: dict[str, list[RespondContact]] = {}
    for contact, d in db.query(RespondContact, digits).options(load_only(*columns)).filter(
        digits.in_(set(wanted.values()))
    ).order_by(RespondContact.id):
        by_digits.setdefault(d, []).append(contact)
    found = {p: by_digits[d][0] for p, d in wanted.items() if len(by_digits.get(d, [])) == 1}
    ambiguous = {p for p, d in wanted.items() if len(by_digits.get(d, [])) > 1}
    return found, ambiguous


def _resolve_world(db, rules: dict) -> dict:
    codes = set(rules["companies"].values())
    companies = {
        c.code: c for c in db.query(Company.id, Company.code).filter(Company.code.in_(codes))
    }
    if set(companies) != codes:
        raise SystemExit("A company in the rules is missing from the database.")
    warehouses: dict[str, dict[str, Warehouse]] = {}
    for code, wanted in rules["locations"].items():
        rows = db.query(Warehouse.id, Warehouse.warehouse_code).filter(
            Warehouse.company_id == companies[code].id, Warehouse.warehouse_code.in_(wanted)
        ).all()
        if {w.warehouse_code for w in rows} != set(wanted):
            raise SystemExit(f"A stock location of company {code} in the rules is missing from the database.")
        warehouses[code] = {w.warehouse_code: w for w in rows}
    agents = {a.code: a for a in db.query(AccessAgent.id, AccessAgent.code).filter(AccessAgent.code.in_(rules["agents"]))}
    if set(agents) != set(rules["agents"]):
        raise SystemExit("An agent in the rules is missing from the database.")
    return {"companies": companies, "warehouses": warehouses, "agents": agents}


# ---------------------------------------------------------------- plan


def _change(contact, d: Desired, facet, before, after, status, changed) -> dict:
    return {
        "contact_id": str(contact.id), "phone": d.phone, "contact": contact.name or "",
        "excel_rows": d.rows, "facet": facet, "before": before, "after": after,
        "status": status, "changed": changed,
    }


def _plan_contact(
    db, contact, snap, d: Desired, names: Names, world: dict, rules: dict, media_row,
    skip: frozenset = frozenset(),
) -> tuple[list[dict], dict]:
    """The change rows for one contact and the write instructions the apply step follows.

    The 26 Oct sheet template adds to the 4 Oct rules: an owner type may be a LIST per company,
    `world["brands"]` (company code -> brand ids) switches the brands facet on, `rules["stock_union"]`
    makes the include list add-only, and `skip` names facets the caller may not set (reported as
    status `not_applied`, never written)."""
    out: list[dict] = []
    todo: dict[str, Any] = {}
    company_code_of = {str(c.id): code for code, c in world["companies"].items()}

    def company_label(cid: str) -> str:
        return company_code_of.get(cid) or names.companies.get(cid, (None, None))[0] or "other company"

    # access types
    owner_types = {
        t for c in d.owner_companies for t in ([rules["owner_types"][c]] if isinstance(rules["owner_types"][c], str) else rules["owner_types"][c])
    }
    want_types = {rules["base_type"], *owner_types}
    missing_types = sorted(want_types - set(snap.access_types))
    out.append(_change(contact, d, "access_types", list(snap.access_types), sorted(want_types | set(snap.access_types)),
                       "add" if missing_types else "already", bool(missing_types)))
    todo["types"] = missing_types

    # companies
    want_ids = {str(world["companies"][c].id) for c in d.companies}
    missing_ids = sorted(want_ids - set(snap.companies))
    out.append(_change(contact, d, "companies", sorted(company_label(c) for c in snap.companies),
                       sorted(company_label(c) for c in want_ids | set(snap.companies)),
                       "add" if missing_ids else "already", bool(missing_ids)))
    todo["companies"] = missing_ids

    # stock override: SET
    include_ids = sorted(str(world["warehouses"][c][code].id) for c in d.companies for code in rules["locations"][c])
    keep_all = bool(rules.get("stock_union")) and snap.stock is not None and snap.stock.include is None
    if rules.get("stock_union") and snap.stock is not None and snap.stock.include is not None:
        include_ids = sorted({*include_ids, *snap.stock.include})
    code_of = {str(w.id): w.warehouse_code for per in world["warehouses"].values() for w in per.values()}
    shown = Names(warehouses={**names.warehouses, **code_of})
    cur = snap.stock
    hide = cur.hide_zero if cur else False
    mode_changed = cur is None or cur.mode != rules["stock_mode"]
    loc_changed = cur is None or (not keep_all and cur.include != tuple(include_ids)) or cur.exclude is not None
    out.append(_change(contact, d, "stock_mode", cur.mode if cur else None, rules["stock_mode"],
                       "set" if mode_changed else "already", mode_changed))
    out.append(_change(contact, d, "stock_locations", locations_text(cur, shown),
                       locations_text(StockOverride(rules["stock_mode"], None if keep_all else tuple(include_ids), None, hide), shown),
                       "set" if loc_changed else "already", loc_changed))
    todo["stock"] = (mode_changed or loc_changed, None if keep_all else include_ids, hide)

    # brands (sheet template only): NULL -> the template set; a set list -> union, never removed
    if "brands" in world:
        want_brands = sorted({b for c in d.companies for b in world["brands"].get(c, ())})
        held_brands = list(snap.brands)
        label = {**names.brands, **world.get("brand_names", {})}
        add_brands = sorted(set(want_brands) - set(held_brands)) if want_brands else []
        if add_brands:
            after_brands = sorted({*held_brands, *want_brands})
            out.append(_change(contact, d, "brands", sorted(label.get(b, "other brand") for b in held_brands),
                               sorted(label.get(b, "other brand") for b in after_brands), "add", True))
            todo["brands"] = after_brands
        else:
            out.append(_change(contact, d, "brands", sorted(label.get(b, "other brand") for b in held_brands),
                               sorted(label.get(b, "other brand") for b in held_brands), "already", False))

    # market segment
    seg = rules["segment"]
    seg_missing = seg not in snap.segments
    out.append(_change(contact, d, "market_segments", list(snap.segments), sorted({*snap.segments, seg}),
                       "add" if seg_missing else "already", seg_missing))
    todo["segment"] = seg if seg_missing else None

    # media
    modality = rules["media_modality"]
    if media_row is None:
        out.append(_change(contact, d, "media", None, f"{modality} allowed", "add", True))
        todo["media"] = "create"
    elif not media_row.is_allowed:
        out.append(_change(contact, d, "media", f"{modality} not allowed", f"{modality} allowed", "set", True))
        todo["media"] = "allow"
    else:
        out.append(_change(contact, d, "media", f"{modality} allowed", f"{modality} allowed", "already", False))
        todo["media"] = None

    # agents: add the missing, never touch an existing grant
    adds, kept, held = [], [], []
    for code in rules["agents"]:
        agent = world["agents"][code]
        grant = snap.agents.get(str(agent.id))
        if grant is None:
            adds.append(agent)
            continue
        same = (grant.is_allowed, grant.valid_from, grant.valid_to) == (True, rules["agent_valid_from"], rules["agent_valid_to"])
        (held if same else kept).append(code)
    before_agents = sorted(g.agent_code for g in snap.agents.values())
    after_agents = sorted({*before_agents, *(a.code for a in adds)})
    status = "kept" if kept else "add" if adds else "already"
    out.append(_change(contact, d, "agent_access", before_agents,
                       after_agents + [f"kept as is: {c}" for c in sorted(kept)], status, bool(adds)))
    todo["agents"] = adds

    # switches
    todo["switches"] = {}
    for col_name, value in [*((c, True) for c in rules["switches_on"]), *((c, False) for c in rules["switches_off"])]:
        current = bool(getattr(contact, col_name))
        differs = current != value
        out.append(_change(contact, d, col_name, current, value, "set" if differs else "already", differs))
        if differs:
            todo["switches"][col_name] = value
    if skip:
        for r in out:
            if r["facet"] in skip and r["changed"]:
                r["changed"], r["status"] = False, "not_applied"
        if "companies" in skip:
            todo["companies"] = []
        if skip & {"stock_check_mode", "stock_locations"}:
            todo["stock"] = (False, include_ids, hide)
        if "agent_access" in skip:
            todo["agents"] = []
    return out, todo


def _apply_contact(db, contact, d: Desired, todo: dict, rules: dict, actor_id: Optional[str]) -> None:
    cid = contact.id  # `contact` is plain (id, name, phone_number), never an expired entity
    if todo["types"]:
        db.execute(respond_contact_access_types.insert(), [{"contact_id": cid, "access_type_code": c} for c in todo["types"]])
    for company_id in todo["companies"]:
        db.add(RespondContactCompany(respond_contact_id=cid, company_id=company_id))
    changed, include_ids, hide = todo["stock"]
    if changed:
        row = db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == cid).first()
        if row is None:
            row = StockVisibilityPolicy(contact_id=cid)
            db.add(row)
        row.mode = rules["stock_mode"]
        if include_ids is not None:
            row.warehouse_ids = list(include_ids)
        row.excluded_warehouse_ids = None
        row.hide_zero_locations = hide
    if todo.get("brands"):
        db.query(RespondContact).filter(RespondContact.id == cid).update(
            {"brand_ids": todo["brands"]}, synchronize_session=False
        )
    if todo["segment"]:
        db.execute(respond_contact_market_segments.insert(), [{"contact_id": cid, "segment_code": todo["segment"]}])
    if todo["media"] == "create":
        db.add(ContactMediaLimit(contact_id=cid, modality=rules["media_modality"], is_allowed=True, updated_by=actor_id))
    elif todo["media"] == "allow":
        db.query(ContactMediaLimit).filter(
            ContactMediaLimit.contact_id == cid, ContactMediaLimit.modality == rules["media_modality"]
        ).update({"is_allowed": True, "updated_by": actor_id}, synchronize_session=False)
    for agent in todo["agents"]:
        db.add(ContactAgentAccess(
            respond_contact_id=cid, respond_contact_phone=contact.phone_number, respond_contact_name=contact.name,
            agent_id=str(agent.id), is_allowed=True, valid_from=rules["agent_valid_from"],
            valid_to=rules["agent_valid_to"], created_by=actor_id,
        ))
    if todo["switches"]:
        db.query(RespondContact).filter(RespondContact.id == cid).update(
            todo["switches"], synchronize_session=False
        )
    db.flush()



# Copied from PR #1475 (head dff1718a1), app/services/customer_merge.py `_NAME_SUFFIXES` and
# `normalise_name`, and app/services/customer_identity.py `SURVIVOR_ORDER_SQL`: that PR is not
# on main and this one file is what runs against prod, so it carries its own copy of the rules.
_NAME_SUFFIXES = frozenset(
    {
        "sdn", "bhd", "berhad", "sendirian", "plt", "llp", "m",
        "enterprise", "enterprises", "ent", "trading", "co", "company",
    }
)
CASH_CODE_PREFIXES = ("301-",)


def normalise_name(name: Optional[str]) -> str:
    """The core of a business name (PR #1475 dff1718a1 customer_merge.normalise_name)."""

    def _words(text_: str) -> list[str]:
        return re.sub(r"[^a-z0-9]+", " ", text_).split()

    raw = (name or "").lower()
    text_ = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", raw)
    text_ = re.sub(r"[\[(][^\])]*$", " ", text_)
    text_ = re.split(r"\s+-\s+", text_, maxsplit=1)[0]
    text_ = text_.split("&", 1)[0]
    words = _words(text_)
    if words and words[0] == "the":
        words = words[1:]
    while words and words[-1] in _NAME_SUFFIXES:
        words.pop()
    return " ".join(words) or " ".join(_words(raw))


def _merge_flags(db, keys: set) -> dict[str, tuple[str, str]]:
    """customer id -> (survives_merge, held), Y/N, for every member of the (company, code) groups
    named in `keys`. One read-only query. Group = company + lower(btrim(code)); survivor order is
    SURVIVOR_ORDER_SQL: code-form integration ref, then any ref, then oldest created_at, then id."""
    keys = {k for k in keys if k[1]}
    if not keys:
        return {}
    ordered = sorted(keys)
    rows = db.execute(
        text(
            """
            SELECT c.id::text, c.company_id::text, lower(btrim(c.customer_code)), c.customer_name, c.created_at,
              EXISTS (
                SELECT 1 FROM integration_references r
                WHERE r.entity_type = 'customers' AND r.entity_id = c.id::text
                  AND lower(btrim(regexp_replace(r.source_ref, '^[^:]*:', ''))) = lower(btrim(c.customer_code))
              ),
              EXISTS (
                SELECT 1 FROM integration_references r
                WHERE r.entity_type = 'customers' AND r.entity_id = c.id::text
              )
            FROM customers c
            WHERE (c.company_id::text, lower(btrim(c.customer_code))) IN (
              SELECT * FROM unnest(CAST(:cids AS text[]), CAST(:codes AS text[])))
            """
        ),
        {"cids": [k[0] for k in ordered], "codes": [k[1] for k in ordered]},
    ).all()
    groups: dict[tuple, list] = {}
    for row in rows:
        groups.setdefault((row[1], row[2]), []).append(row)
    out: dict[str, tuple[str, str]] = {}
    for (_, code), members in groups.items():
        members.sort(key=lambda m: (not m[5], not m[6], m[4] is None, m[4] or datetime.min, m[0]))
        survivor = members[0]
        held = (
            len(members) > 1
            and not code.startswith(CASH_CODE_PREFIXES)
            and any(normalise_name(m[3]) != normalise_name(survivor[3]) for m in members[1:])
        )
        for m in members:
            out[m[0]] = ("Y" if m is survivor else "N", "Y" if held else "N")
    return out



def _score(a: str, b: str) -> float:
    return SequenceMatcher(None, a.casefold().strip(), b.casefold().strip()).ratio()
