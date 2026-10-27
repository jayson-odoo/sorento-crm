"""Lane BULK-CONTACT-ACCESS: POST /api/v1/user-management/contacts/access-sheet.

UAC ``documentation/plans/contacts/bulk-contact-access-26oct-acceptance-criteria.md`` U1-U19.
RED tests written before any implementation: the route does not exist yet, so every test fails
on a 404 / missing key, the right red. Contract: PLAN-bulk-contact-access-26oct.md "API contract".

Postgres only (``blank_session``); every company, brand, warehouse, access type, agent, segment,
contact, customer and the actor are seeded here. Names and phones are invented (public repo).
Codes SRT (the incumbent company, seeded by tests/conftest.py), MCH, BRW, MWH, HQ, MOCHA-WH and the
access-type / agent / segment codes are the template's own and are seeded here.

Black-box: every assertion goes through the HTTP response (``response_model`` drops undeclared
fields) or a direct DB read of the contact's whole access set.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.access import (
    AccessAgent,
    ContactAccessType,
    ContactAgentAccess,
    MarketSegment,
    RespondContact,
    RespondContactCustomer,
    StockVisibilityPolicy,
)
from app.models.audit import AuditLog
from app.models.base import set_company_scope
from app.models.company import Company, RespondContactCompany
from app.models.media import ContactMediaLimit
from app.models.order import Customer
from app.models.product import Brand
from app.models.sales_agent import SalesAgent
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService

from tests._mc_lookup_seed import warehouse
from tests._pg_fixture import blank_session, unique_code

URL = "/api/v1/user-management/contacts/access-sheet"
EDIT = "user_management.contacts.edit"
AGENTS_EDIT = "user_management.access_agents.edit"
STOCK_EDIT = "inventory.stock.edit"
D1 = datetime(2026, 1, 1)
D2 = datetime(2026, 12, 31)
OLD1 = datetime(2025, 3, 1)
OLD2 = datetime(2025, 4, 1)
AGENT_CODES = ["general_enquiries", "order_enquiries", "incoming_stock_enquiries"]
EVENT = "contact.access_sheet"

SRT_TAG = "Sorento Sdn Bhd"
MCH_TAG = "Mocha Sdn Bhd"
OWNER = "Business Owner"
EMPLOYEE = "Employee"
DEALER = "ALPHA BATH SDN BHD"
KEY = "alpha bath"  # normalise_name(DEALER)


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def env():
    """Mutable request environment the overrides read on every call."""
    return {
        "granted": {EDIT, AGENTS_EDIT, STOCK_EDIT},
        "superadmin": True,
        "scope": frozenset({DEFAULT_COMPANY_ID}),
    }


@pytest.fixture
def actor(db):
    user = User(id=str(uuid.uuid4()), email=f"zzt-{uuid.uuid4().hex[:8]}@test.com", name="ZZT Admin")
    db.add(user)
    db.flush()
    return user.id


@pytest.fixture
def client(db, env, actor, monkeypatch):
    principal = {"id": actor, "email": "zzt-admin@test.com"}

    def _override_db():
        yield db

    async def _override_scope():
        set_company_scope(db, env["scope"])
        return env["scope"]

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in env["granted"],
    )
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: {"superadmin"} if env["superadmin"] else set(),
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def w(db, env):
    """The seeded world: SRT (incumbent), MCH, ZZX (tagged by no sheet row), ZZO (outside scope)."""
    srt = DEFAULT_COMPANY_ID
    mch, zzx, zzo = (str(uuid.uuid4()) for _ in range(3))
    allc = frozenset({srt, mch, zzx, zzo})
    set_company_scope(db, allc)
    db.add_all(
        [
            Company(id=mch, name="ZZT Mocha Co", code="MCH"),
            Company(id=zzx, name="ZZT Third Co", code="ZZX"),
            Company(id=zzo, name="ZZT Hidden Co", code="ZZO"),
        ]
    )
    db.flush()
    wh = {
        "BRW": warehouse(db, company_id=srt, code="BRW").id,
        "MWH": warehouse(db, company_id=srt, code="MWH").id,
        "HQ": warehouse(db, company_id=mch, code="HQ").id,
        "MOCHA-WH": warehouse(db, company_id=mch, code="MOCHA-WH").id,
        # decoys: same code in another company, and an unrelated warehouse in the template's company
        "X-BRW": warehouse(db, company_id=zzx, code="BRW").id,
        "SRT-OTHER": warehouse(db, company_id=srt, code="ZZT-OTHER").id,
    }
    types = {}
    for code in ("dealer", "cabana_dealer", "mocha_dealer", "end_user", "zzt_extra"):
        row = ContactAccessType(code=code, name=f"ZZT {code}", is_active=True, sort_order=1)
        db.add(row)
        types[code] = row
    for code in AGENT_CODES:
        db.add(AccessAgent(code=code, name=f"ZZT {code}"))
    seg_retail = MarketSegment(code="retail", name="ZZT retail", is_active=True, sort_order=1)
    seg_other = MarketSegment(code="zzt_project", name="ZZT project", is_active=True, sort_order=2)
    db.add_all([seg_retail, seg_other])
    db.flush()

    def brand(code, company, dealer, active=True):
        # Owner ruling 26 Oct 15:20: a brand is given by the upload through `dealer_company_id`,
        # NOT through the company that owns the brand row (MOCHA / IBORN are rows of SRT).
        row = Brand(brand_code=code, brand_name=f"ZZT {code}", is_active=active, company_id=company)
        if hasattr(Brand, "dealer_company_id"):  # red run: the column does not exist yet
            row.dealer_company_id = dealer
        db.add(row)
        db.flush()
        return row.id

    brands = {
        "S1": brand("ZSB-1", srt, srt),
        "S2": brand("ZSB-2", srt, srt),
        "S-OFF": brand("ZSB-OFF", srt, srt, active=False),
        "M1": brand("ZMB-1", srt, mch),  # a brand row of SRT whose dealers are MCH's
        "M2": brand("ZMB-2", srt, mch),
        "P1": brand("ZPB-1", srt, None),  # project brand: never given by the upload
        "OWN-MCH": brand("ZMB-OWN", mch, None),  # owned by MCH, dealer company NULL: not given
        "X1": brand("ZXB-1", zzx, None),
    }
    admin = db.query(User).first()
    world = SimpleNamespace(
        srt=srt, mch=mch, zzx=zzx, zzo=zzo, all=allc, wh=wh, brands=brands,
        co={"SRT": srt, "MCH": mch}, admin=admin.id if admin else None,
    )
    env["scope"] = frozenset({srt, mch, zzx})
    db.commit()
    return world


# ---------------------------------------------------------------- seeding helpers


def _all(db, w):
    set_company_scope(db, w.all)
    db.expire_all()


def _contact(db, w, n, *, types=(), companies=(), brand_ids=None, segments=(), warehouses=None,
             grants=(), phone=None, **flags):
    """A contact whose five switches start OPPOSITE the template, so every apply must flip them."""
    set_company_scope(db, w.all)
    row = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=phone or f"601000{n:05d}",
        name=f"ZZT Person {n}",
        brand_ids=brand_ids,
        packing_list_allowed=flags.pop("packing", True),
        chatbot_eta_offset_applied=flags.pop("eta", False),
        chatbot_stock_allowed=flags.pop("stock", False),
        chatbot_allowed=flags.pop("ai", False),
        escalation_allowed=flags.pop("escalation", True),
    )
    db.add(row)
    db.flush()
    row.access_types = [t for t in types]
    row.market_segments = list(segments)
    db.flush()
    for company_id in companies:
        db.add(RespondContactCompany(respond_contact_id=row.id, company_id=company_id))
    if warehouses is not None:
        db.add(StockVisibilityPolicy(contact_id=row.id, mode="detailed", warehouse_ids=list(warehouses)))
    for agent_code, allowed, vfrom, vto in grants:
        agent = db.query(AccessAgent).filter(AccessAgent.code == agent_code).one()
        db.add(
            ContactAgentAccess(
                respond_contact_id=row.id, respond_contact_phone=row.phone_number, agent_id=agent.id,
                is_allowed=allowed, valid_from=vfrom, valid_to=vto,
            )
        )
    db.flush()
    db.commit()
    return row.id


def _cust(db, w, company_id, name, *, code=None, active=True, agent=None, created=None):
    set_company_scope(db, w.all)
    agent_id = None
    if agent:
        sa = SalesAgent(sales_agent=agent, company_id=company_id)
        db.add(sa)
        db.flush()
        agent_id = sa.id
    row = Customer(
        customer_code=code or unique_code("ZZT-D"), customer_name=name, company_id=company_id,
        is_active=active, sales_agent_id=agent_id,
    )
    if created:
        row.created_at = created
    db.add(row)
    db.flush()
    db.commit()
    return row.id


def _dealer(db, w, name=DEALER, companies=("SRT", "MCH")):
    """One active exact account per named company. Returns {company code: customer id}."""
    return {c: _cust(db, w, w.co[c], name, agent=f"ZZT-AG-{c}") for c in companies}


def _types(db, *codes):
    return [db.query(ContactAccessType).filter(ContactAccessType.code == c).one() for c in codes]


def _segment(db, code):
    return db.query(MarketSegment).filter(MarketSegment.code == code).one()


# ---------------------------------------------------------------- sheet + request helpers


def _tags(dealer, companies, role, *, alt=None):
    parts = [dealer]
    for c in companies:
        parts.append(SRT_TAG if c == "SRT" else MCH_TAG)
        parts.append(f"ZZT AGENT {c}")
    if alt:
        parts.append(alt)
    parts.append(role)
    return ", ".join(parts)


def _sheet(rows, header=("First Name", "Last Name", "Phone Number", "Tags", "Email"), bom=False):
    """rows: (first name, phone text, tags text). Extra Respond columns stay empty."""
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(header)
    for name, phone, tags in rows:
        record = {"First Name": name, "Phone Number": phone, "Tags": tags}
        out.writerow([record.get(h, "") for h in header])
    text = buf.getvalue()
    return (("﻿" + text) if bom else text).encode("utf-8")


def _post(client, content, *, dry_run=True, confirmed=None, params=None):
    data = {"dry_run": "true" if dry_run else "false"}
    if confirmed is not None:
        data["confirmed"] = confirmed if isinstance(confirmed, str) else json.dumps(confirmed)
    return client.post(URL, files={"file": ("sheet.csv", content, "text/csv")}, data=data, params=params)


def _confirm_all(preview):
    return {
        b["key"]: [a["customer_id"] for a in b["accounts"] if a["match"] == "exact" and a["proposed"]]
        for b in preview["blocks"]
        if b["status"] == "exact"
    }


def _apply_all(client, content):
    """Dry run, confirm every exact block with its proposed accounts, apply. Returns (preview, result)."""
    pre = _post(client, content)
    assert pre.status_code == 200, pre.text
    preview = pre.json()
    res = _post(client, content, dry_run=False, confirmed=_confirm_all(preview))
    assert res.status_code == 200, res.text
    return preview, res.json()


def _by_name(body):
    return {c["name"]: c for b in body["blocks"] for c in b["contacts"]}


def _block(body, key=KEY):
    (block,) = [b for b in body["blocks"] if b["key"] == key]
    return block


# ---------------------------------------------------------------- DB readers


def _state(db, w, cid):
    _all(db, w)
    c = db.get(RespondContact, cid)
    pol = db.query(StockVisibilityPolicy).filter(StockVisibilityPolicy.contact_id == cid).first()
    grants = (
        db.query(ContactAgentAccess, AccessAgent)
        .join(AccessAgent, AccessAgent.id == ContactAgentAccess.agent_id)
        .filter(ContactAgentAccess.respond_contact_id == cid)
        .all()
    )
    return {
        "types": sorted(t.code for t in c.access_types),
        "companies": sorted(
            r.company_id for r in db.query(RespondContactCompany).filter(RespondContactCompany.respond_contact_id == cid)
        ),
        "brands": None if c.brand_ids is None else sorted(c.brand_ids),
        "segments": sorted(s.code for s in c.market_segments),
        "stock": None if pol is None else {
            "mode": pol.mode,
            "warehouses": None if pol.warehouse_ids is None else sorted(pol.warehouse_ids),
            "excluded": pol.excluded_warehouse_ids,
            "hide_zero": pol.hide_zero_locations,
        },
        "media": sorted(
            (m.modality, m.is_allowed)
            for m in db.query(ContactMediaLimit).filter(ContactMediaLimit.contact_id == cid)
        ),
        "grants": sorted((a.code, g.is_allowed, g.valid_from, g.valid_to) for g, a in grants),
        "packing": c.packing_list_allowed,
        "eta": c.chatbot_eta_offset_applied,
        "stock_on": c.chatbot_stock_allowed,
        "ai": c.chatbot_allowed,
        "escalation": c.escalation_allowed,
        "links": sorted(
            (r.customer_id, str(r.company_id))
            for r in db.query(RespondContactCustomer).filter(RespondContactCustomer.contact_id == cid)
        ),
    }


def _audits(db, w, cid=None):
    _all(db, w)
    q = db.query(AuditLog).filter(AuditLog.event == EVENT)
    if cid:
        q = q.filter(AuditLog.entity_id == cid)
    return q.all()


def _expected(w, companies, role):
    types = {"end_user"}
    brands, wh = set(), set()
    if role == OWNER:
        if "SRT" in companies:
            types |= {"dealer", "cabana_dealer"}
        if "MCH" in companies:
            types.add("mocha_dealer")
    if "SRT" in companies:
        brands |= {w.brands["S1"], w.brands["S2"]}
        wh |= {w.wh["BRW"], w.wh["MWH"]}
    if "MCH" in companies:
        brands |= {w.brands["M1"], w.brands["M2"]}
        wh |= {w.wh["HQ"], w.wh["MOCHA-WH"]}
    return {
        "types": sorted(types),
        "companies": sorted(w.co[c] for c in companies),
        "brands": sorted(brands),
        "warehouses": sorted(wh),
    }


# ================================================================ U1 parse


@pytest.mark.parametrize("missing", ["Phone Number", "Tags"])
def test_u1_missing_required_column_is_422_naming_it(client, w, missing):
    header = [h for h in ("First Name", "Phone Number", "Tags") if h != missing]
    resp = _post(client, _sheet([], header=header))
    assert resp.status_code == 422, resp.text
    assert missing in resp.text


def test_u1_bom_and_extra_columns_are_accepted(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))], bom=True)
    resp = _post(client, content)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["counts"]["rows"] == 1 and body["counts"]["row_errors"] == 0
    assert body["counts"]["contacts_found"] == 1


def test_u1_file_over_2mb_is_422(client, w):
    filler = "x" * 1000
    rows = [("ZZT Big", "+60100000001", f"{filler}") for _ in range(2200)]
    content = _sheet(rows)
    assert len(content) > 2 * 1024 * 1024
    assert _post(client, content).status_code == 422


def test_u1_more_than_2000_data_rows_is_422(client, w):
    rows = [("ZZT P", "+60100000001", _tags(DEALER, ["SRT"], OWNER)) for _ in range(2001)]
    content = _sheet(rows)
    assert len(content) < 2 * 1024 * 1024
    assert _post(client, content).status_code == 422


# ================================================================ U2 tags


def test_u2_back_to_back_brand_companies_with_no_agent(client, db, w):
    _dealer(db, w)
    cid = _contact(db, w, 1)
    tags = f"{DEALER}, {SRT_TAG}, {MCH_TAG}, {OWNER}"
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", tags)])).json()
    assert body["counts"]["row_errors"] == 0, body["errors"]
    block = _block(body)
    assert sorted(block["companies"]) == ["MCH", "SRT"]
    contact = _by_name(body)["ZZT Ann"]
    assert contact["role"] == "owner"
    assert sorted(contact["companies"]) == ["MCH", "SRT"]
    for account in block["accounts"]:
        assert account["sheet_agent"] in (None, "")  # no agent was named for either company
    assert contact["contact_id"] == cid


def test_u2_agent_alt_dealer_role_and_case_insensitive_tokens(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1)
    tags = f"{DEALER}, SORENTO SDN BHD, ZZT AGENT SRT, ALPHA BATHROOM TRADING, business owner"
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", tags)])).json()
    assert body["counts"]["row_errors"] == 0, body["errors"]
    block = _block(body)
    assert block["companies"] == ["SRT"]
    assert block["alt_dealers"] == ["ALPHA BATHROOM TRADING"]
    srt_account = [a for a in block["accounts"] if a["company_code"] == "SRT"][0]
    assert srt_account["sheet_agent"] == "ZZT AGENT SRT"
    assert _by_name(body)["ZZT Ann"]["role"] == "owner"


def test_u2_rows_with_no_company_role_or_phone_are_row_errors_and_never_applied(client, db, w):
    _dealer(db, w, companies=("SRT",))
    ids = [_contact(db, w, n) for n in (1, 2, 3)]
    before = [_state(db, w, c) for c in ids]
    content = _sheet(
        [
            ("ZZT NoCompany", "+60100000001", f"{DEALER}, {OWNER}"),
            ("ZZT NoRole", "+60100000002", f"{DEALER}, {SRT_TAG}, ZZT AGENT SRT"),
            ("ZZT NoPhone", "", _tags(DEALER, ["SRT"], OWNER)),
        ]
    )
    for dry_run, confirmed in ((True, None), (False, {})):
        resp = _post(client, content, dry_run=dry_run, confirmed=confirmed)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["counts"]["rows"] == 3
        assert body["counts"]["row_errors"] == 3
        assert len(body["errors"]) == 3
        assert all(e["line"] and e["reason"] for e in body["errors"])
        assert body["counts"]["applied"] == 0
    assert [_state(db, w, c) for c in ids] == before


# ================================================================ U3 phone match


def test_u3_phone_matches_on_digits_only(client, db, w):
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1, phone="60123456789")
    content = _sheet([("ZZT Ann", "+60 12-345 6789", _tags(DEALER, ["SRT"], OWNER))])
    contact = _by_name(_post(client, content).json())["ZZT Ann"]
    assert contact["in_crm"] is True
    assert contact["contact_id"] == cid


def test_u3_not_in_crm_and_ambiguous_phone_are_skipped_never_created(client, db, w):
    _dealer(db, w, companies=("SRT",))
    ok = _contact(db, w, 1)
    _contact(db, w, 2, phone="60100000009")
    _contact(db, w, 3, phone="+60100000009")  # same digits, second contact
    _all(db, w)
    total_before = db.query(RespondContact).count()
    tags = _tags(DEALER, ["SRT"], OWNER)
    content = _sheet(
        [
            ("ZZT Found", "+60100000001", tags),
            ("ZZT Ghost", "+60100000077", tags),
            ("ZZT Twin", "0100000009", tags),
        ]
    )
    preview, result = _apply_all(client, content)
    assert result["counts"]["not_in_crm"] == 1
    assert result["counts"]["ambiguous"] == 1
    assert result["counts"]["contacts_found"] == 1
    by = _by_name(result)
    assert by["ZZT Ghost"]["status"] == "skipped" and by["ZZT Ghost"]["skip_reason"] == "not_in_crm"
    assert by["ZZT Ghost"]["in_crm"] is False
    assert by["ZZT Twin"]["status"] == "skipped" and by["ZZT Twin"]["skip_reason"] == "ambiguous_phone"
    assert by["ZZT Found"]["status"] == "applied"
    _all(db, w)
    assert db.query(RespondContact).count() == total_before
    assert _state(db, w, ok)["types"]  # the found contact was configured


# ================================================================ U4-U6 template (6 combinations)


@pytest.mark.parametrize("role", [OWNER, EMPLOYEE])
@pytest.mark.parametrize("companies", [["SRT"], ["MCH"], ["SRT", "MCH"]], ids=["SRT", "MCH", "SRT+MCH"])
def test_u4_u6_template_per_company_and_role(client, db, w, companies, role):
    _dealer(db, w, companies=tuple(companies))
    cid = _contact(db, w, 1)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, companies, role))])
    _, result = _apply_all(client, content)
    want = _expected(w, companies, role)
    s = _state(db, w, cid)

    assert s["types"] == want["types"], "U4 access types"
    assert s["companies"] == want["companies"], "U5 companies = the row's companies"
    assert s["brands"] == want["brands"], "U5 brands = active brands whose dealer_company_id is a row company"
    assert s["stock"] == {
        "mode": "availability", "warehouses": want["warehouses"], "excluded": None, "hide_zero": False,
    }, "U5 locations by warehouse code per company"
    assert (s["packing"], s["eta"], s["stock_on"], s["ai"], s["escalation"]) == (False, True, True, True, False), "U6 switches"
    assert s["segments"] == ["retail"]
    assert ("image", True) in s["media"]
    assert s["grants"] == sorted((code, True, D1, D2) for code in AGENT_CODES), "U6 three grants, 2026 window"

    contact = _by_name(result)["ZZT Ann"]
    assert contact["status"] == "applied"
    assert contact["changes"], "an applied contact lists its changes"
    assert all({"facet", "before", "after"} <= set(c) for c in contact["changes"])
    expected_label = "+".join(companies) + (" owner" if role == OWNER else " employee")
    assert contact["template"] == expected_label


def test_u5_inactive_and_other_company_brands_never_added(client, db, w):
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1)
    _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    brands = _state(db, w, cid)["brands"]
    assert w.brands["S-OFF"] not in brands
    assert w.brands["M1"] not in brands and w.brands["X1"] not in brands
    assert w.brands["P1"] not in brands and w.brands["OWN-MCH"] not in brands


def test_u5_mocha_only_row_gets_exactly_the_mocha_dealer_brands(client, db, w):
    _dealer(db, w, companies=("MCH",))
    cid = _contact(db, w, 1)
    _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["MCH"], EMPLOYEE))]))
    assert _state(db, w, cid)["brands"] == sorted([w.brands["M1"], w.brands["M2"]])


def test_u7_a_brand_outside_the_template_is_kept_and_warns_holds_more(client, db, w):
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1, brand_ids=[w.brands["P1"]], types=_types(db, "end_user"))
    _, result = _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    assert _state(db, w, cid)["brands"] == sorted([w.brands["P1"], w.brands["S1"], w.brands["S2"]])
    assert "holds_more" in _by_name(result)["ZZT Ann"]["warnings"]


def test_u5_no_brand_for_the_companies_leaves_brands_untouched(client, db, w):
    _dealer(db, w, companies=("SRT",))
    set_company_scope(db, w.all)
    for bid in (w.brands["S1"], w.brands["S2"]):
        db.get(Brand, bid).is_active = False
    db.commit()
    kept = _contact(db, w, 1)
    _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    assert _state(db, w, kept)["brands"] is None


# ================================================================ U7 add only


def test_u7_add_only_keeps_what_the_contact_holds_and_warns_holds_more(client, db, w):
    _dealer(db, w, companies=("SRT",))
    cid = _contact(
        db, w, 1,
        types=_types(db, "zzt_extra", "end_user"),
        companies=[w.zzx],
        brand_ids=[w.brands["X1"]],
        segments=[_segment(db, "zzt_project")],
        warehouses=[w.wh["SRT-OTHER"]],
        grants=[("general_enquiries", True, OLD1, OLD2)],
    )
    _, result = _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    s = _state(db, w, cid)
    assert s["types"] == ["cabana_dealer", "dealer", "end_user", "zzt_extra"]
    assert s["companies"] == sorted([w.zzx, w.srt])
    assert s["brands"] == sorted([w.brands["X1"], w.brands["S1"], w.brands["S2"]])
    assert s["segments"] == ["retail", "zzt_project"]
    assert s["stock"]["warehouses"] == sorted([w.wh["SRT-OTHER"], w.wh["BRW"], w.wh["MWH"]])
    grants = {g[0]: g for g in s["grants"]}
    assert grants["general_enquiries"] == ("general_enquiries", True, OLD1, OLD2), "an existing grant is kept"
    assert grants["order_enquiries"] == ("order_enquiries", True, D1, D2)
    assert grants["incoming_stock_enquiries"] == ("incoming_stock_enquiries", True, D1, D2)
    # the switches are SET to the template, not added
    assert (s["packing"], s["eta"], s["stock_on"], s["ai"], s["escalation"]) == (False, True, True, True, False)
    assert "holds_more" in _by_name(result)["ZZT Ann"]["warnings"]


def test_u7_a_contact_within_its_template_gets_no_holds_more(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1, types=_types(db, "end_user"))
    _, result = _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    assert "holds_more" not in _by_name(result)["ZZT Ann"]["warnings"]


# ================================================================ U8-U10 dealer blocks and accounts


def test_u8_u10_exact_accounts_span_every_company_including_the_untagged_one(client, db, w):
    ids = {
        "SRT": _cust(db, w, w.srt, DEALER, agent="ZZT-AG-S"),
        "MCH": _cust(db, w, w.mch, "Alpha Bath Sdn. Bhd.", agent="ZZT-AG-M"),
        "ZZX": _cust(db, w, w.zzx, DEALER, agent="ZZT-AG-X"),  # a company the row does not tag
    }
    other = _cust(db, w, w.srt, "ALPHA BATHROOM TRADING SDN BHD")
    _contact(db, w, 1)
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])).json()
    block = _block(body)
    assert block["status"] == "exact"
    exact = {a["customer_id"]: a for a in block["accounts"] if a["match"] == "exact"}
    assert set(exact) == set(ids.values()), "every exact account of ANY company is proposed (Q4)"
    assert other not in exact
    assert all(a["proposed"] for a in exact.values()), "every exact account is ticked by default"
    assert {a["company_code"] for a in exact.values()} == {"SRT", "MCH", "ZZX"}


def test_u8_rows_whose_dealer_texts_normalise_equal_share_one_block(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1)
    _contact(db, w, 2)
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags("ALPHA BATH SDN BHD", ["SRT"], OWNER)),
            ("ZZT Bob", "+60100000002", _tags("Alpha Bath Sdn. Bhd.", ["SRT"], EMPLOYEE)),
        ]
    )
    body = _post(client, content).json()
    assert body["counts"]["blocks"] == 1
    assert len(body["blocks"]) == 1
    assert {c["name"] for c in body["blocks"][0]["contacts"]} == {"ZZT Ann", "ZZT Bob"}


def test_u8_merge_non_survivor_is_not_an_exact_account(client, db, w):
    code = unique_code("ZZT-MRG")
    survivor = _cust(db, w, w.srt, DEALER, code=code, created=datetime(2020, 1, 1))
    loser = _cust(db, w, w.srt, "Alpha Bath Sdn. Bhd.", code=code, created=datetime(2024, 1, 1))
    _contact(db, w, 1)
    block = _block(_post(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])).json())
    exact = {a["customer_id"] for a in block["accounts"] if a["match"] == "exact"}
    assert survivor in exact
    assert loser not in exact


def test_u8_held_merge_group_is_not_an_exact_account(client, db, w):
    code = unique_code("ZZT-HLD")
    a = _cust(db, w, w.srt, "HELD DEALER SDN BHD", code=code, created=datetime(2020, 1, 1))
    b = _cust(db, w, w.srt, "UNRELATED TRADING SDN BHD", code=code, created=datetime(2024, 1, 1))
    _contact(db, w, 1)
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", _tags("HELD DEALER SDN BHD", ["SRT"], OWNER))])).json()
    block = _block(body, "held dealer")
    exact = {x["customer_id"] for x in block["accounts"] if x["match"] == "exact"}
    assert a not in exact and b not in exact
    assert block["status"] != "exact"


def test_u9_u12_inactive_exact_is_listed_not_ticked_and_confirm_all_skips_it(client, db, w):
    active = _cust(db, w, w.srt, DEALER, agent="ZZT-AG-S")
    inactive = _cust(db, w, w.mch, DEALER, active=False)
    cid = _contact(db, w, 1)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])
    preview, result = _apply_all(client, content)
    accounts = {a["customer_id"]: a for a in _block(preview)["accounts"]}
    assert accounts[inactive]["is_active"] is False and accounts[inactive]["proposed"] is False
    assert accounts[active]["is_active"] is True and accounts[active]["proposed"] is True
    assert {"customer_code", "customer_name", "company_code", "sales_agent", "sheet_agent", "score"} <= set(accounts[active])
    assert "ZZT-AG-S" in str(accounts[active]["sales_agent"])
    assert [l[0] for l in _state(db, w, cid)["links"]] == [active]
    # U12: the sales agent on the customer is never written
    _all(db, w)
    assert db.get(Customer, active).sales_agent.sales_agent == "ZZT-AG-S"


def test_u9_pick_block_ranks_up_to_five_unticked_candidates_per_tagged_company(client, db, w):
    exact_srt = _cust(db, w, w.srt, DEALER)
    for suffix in ("S", "E", "X", "Y", "Z", "Q", "W"):
        _cust(db, w, w.mch, f"ALPHA BATH{suffix} SDN BHD")
    _contact(db, w, 1)
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT", "MCH"], OWNER))])).json()
    block = _block(body)
    assert block["status"] == "pick"
    assert body["counts"]["blocks_pick"] == 1 and body["counts"]["blocks_exact"] == 0
    mch = [a for a in block["accounts"] if a["company_code"] == "MCH"]
    assert 1 <= len(mch) <= 5
    assert all(a["match"] == "candidate" and a["proposed"] is False for a in mch)
    scores = [a["score"] for a in mch]
    assert scores == sorted(scores, reverse=True)
    assert exact_srt in {a["customer_id"] for a in block["accounts"] if a["match"] == "exact"}


def test_u9_block_with_no_account_or_candidate_is_none(client, db, w):
    _contact(db, w, 1)
    tags = _tags("QQQQ ZZZZ WWWW SDN BHD", ["SRT"], OWNER)
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", tags)])).json()
    block = _block(body, "qqqq zzzz wwww")
    assert block["status"] == "none"
    assert block["accounts"] == []
    assert body["counts"]["blocks_none"] == 1


def test_u9_rows_of_one_block_tagging_different_companies_warn_rows_disagree(client, db, w):
    _dealer(db, w)
    _contact(db, w, 1)
    _contact(db, w, 2)
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
            ("ZZT Bob", "+60100000002", _tags(DEALER, ["MCH"], OWNER)),
        ]
    )
    block = _block(_post(client, content).json())
    assert "rows_disagree" in block["warnings"]
    assert sorted(block["companies"]) == ["MCH", "SRT"]


# ================================================================ U11 confirmation and linking


def test_u11_unconfirmed_block_is_skipped_and_nothing_is_written(client, db, w):
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1)
    before = _state(db, w, cid)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])
    resp = _post(client, content, dry_run=False, confirmed={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    contact = _by_name(body)["ZZT Ann"]
    assert contact["status"] == "skipped" and contact["skip_reason"] == "dealer_not_confirmed"
    assert body["counts"]["applied"] == 0 and body["counts"]["skipped"] == 1
    assert _state(db, w, cid) == before
    assert _audits(db, w, cid) == []


def test_p1_confirmed_block_links_each_account_only_to_contacts_whose_row_tags_its_company(client, db, w):
    """BULK-ACCESS-PREVIEW P1 (owner 27 Oct, replaces U11's link-everything): per contact row."""
    ids = {
        "SRT": _cust(db, w, w.srt, DEALER),
        "MCH": _cust(db, w, w.mch, DEALER),
        "ZZX": _cust(db, w, w.zzx, DEALER),  # no row can tag ZZX: links to nobody
    }
    c1, c2 = _contact(db, w, 1), _contact(db, w, 2)
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
            ("ZZT Bob", "+60100000002", _tags(DEALER, ["SRT", "MCH"], EMPLOYEE)),
            ("ZZT Ghost", "+60100000077", _tags(DEALER, ["SRT"], EMPLOYEE)),
        ]
    )
    _apply_all(client, content)
    assert _state(db, w, c1)["links"] == [(ids["SRT"], w.srt)]
    assert _state(db, w, c2)["links"] == sorted([(ids["SRT"], w.srt), (ids["MCH"], w.mch)])


def test_u11_only_the_confirmed_subset_is_linked_and_other_blocks_stay_skipped(client, db, w):
    keep = _cust(db, w, w.srt, DEALER)
    unticked = _cust(db, w, w.mch, DEALER)
    _cust(db, w, w.srt, "BETA TILES SDN BHD")
    c1, c2 = _contact(db, w, 1), _contact(db, w, 2)
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
            ("ZZT Bob", "+60100000002", _tags("BETA TILES SDN BHD", ["SRT"], OWNER)),
        ]
    )
    resp = _post(client, content, dry_run=False, confirmed={KEY: [keep]})
    assert resp.status_code == 200, resp.text
    by = _by_name(resp.json())
    assert by["ZZT Ann"]["status"] == "applied"
    assert by["ZZT Bob"]["skip_reason"] == "dealer_not_confirmed"
    assert [l[0] for l in _state(db, w, c1)["links"]] == [keep]
    assert unticked not in [l[0] for l in _state(db, w, c1)["links"]]
    assert _state(db, w, c2)["links"] == [] and _state(db, w, c2)["types"] == []


# ================================================================ U13 dry run, U14 one transaction


def test_u13_dry_run_writes_nothing_and_reports_what_apply_would_do(client, db, w):
    _dealer(db, w)
    ids = [_contact(db, w, 1), _contact(db, w, 2)]
    before = [_state(db, w, c) for c in ids]
    audits_before = len(_audits(db, w))
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT", "MCH"], OWNER)),
            ("ZZT Bob", "+60100000002", _tags(DEALER, ["SRT"], EMPLOYEE)),
        ]
    )
    resp = _post(client, content, dry_run=True)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["counts"]["applied"] == 2
    assert [c["status"] for c in _by_name(body).values()] == ["applied", "applied"]
    assert [_state(db, w, c) for c in ids] == before
    assert len(_audits(db, w)) == audits_before


def test_u14_unknown_confirmed_id_is_422_and_writes_nothing_for_any_contact(client, db, w):
    good = _cust(db, w, w.srt, DEALER)
    _cust(db, w, w.srt, "BETA TILES SDN BHD")
    ids = [_contact(db, w, 1), _contact(db, w, 2)]
    before = [_state(db, w, c) for c in ids]
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
            ("ZZT Bob", "+60100000002", _tags("BETA TILES SDN BHD", ["SRT"], OWNER)),
        ]
    )
    bad = {KEY: [good], "beta tiles": [str(uuid.uuid4())]}
    resp = _post(client, content, dry_run=False, confirmed=bad)
    assert resp.status_code == 422, resp.text
    assert [_state(db, w, c) for c in ids] == before
    assert _audits(db, w) == []


def test_u14_malformed_confirmed_json_is_422(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])
    assert _post(client, content, dry_run=False, confirmed="{not json").status_code == 422


def test_u14_a_failure_mid_apply_rolls_back_every_contact(db, w, env, actor, monkeypatch):
    """The audit write is the per-contact side effect that runs last; the second one fails."""
    from app.services import audit_service

    _dealer(db, w, companies=("SRT",))
    ids = [_contact(db, w, 1), _contact(db, w, 2)]
    before = [_state(db, w, c) for c in ids]
    real = audit_service.record
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real(*a, **kw)

    monkeypatch.setattr(audit_service, "record", flaky)

    def _override_db():
        yield db

    async def _override_scope():
        set_company_scope(db, env["scope"])
        return env["scope"]

    principal = {"id": actor, "email": "zzt-admin@test.com"}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in env["granted"])
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"superadmin"})
    try:
        tc = TestClient(app, raise_server_exceptions=False)
        content = _sheet(
            [
                ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
                ("ZZT Bob", "+60100000002", _tags(DEALER, ["SRT"], EMPLOYEE)),
            ]
        )
        pre = _post(tc, content).json()
        resp = _post(tc, content, dry_run=False, confirmed=_confirm_all(pre))
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code >= 400, "a mid-apply error must not report success"
    assert [_state(db, w, c) for c in ids] == before, "nothing is half-applied"
    assert _audits(db, w) == []


# ================================================================ U15-U17 result, audit, idempotency


def test_u16_one_audit_row_per_changed_contact_none_for_unchanged(client, db, w, actor):
    from app import audit_context

    # get_current_user stamps the actor in production; the test client overrides it.
    audit_context.stamp_actor(audit_context.AuditActor(actor_type="user", user_id=actor), db=db)
    try:
        _dealer(db, w, companies=("SRT",))
        c1, c2 = _contact(db, w, 1), _contact(db, w, 2)
        tags = _tags(DEALER, ["SRT"], OWNER)
        _apply_all(client, _sheet([("ZZT Ann", "+60100000001", tags)]))
        assert len(_audits(db, w, c1)) == 1 and _audits(db, w, c2) == []
        _, result = _apply_all(
            client, _sheet([("ZZT Ann", "+60100000001", tags), ("ZZT Bob", "+60100000002", tags)])
        )
        by = _by_name(result)
        assert by["ZZT Ann"]["status"] == "no_change" and by["ZZT Bob"]["status"] == "applied"
        assert len(_audits(db, w, c1)) == 1, "no audit row for an unchanged contact"
        (row,) = _audits(db, w, c2)
        assert row.entity_id == c2
        assert str(row.user_id) == actor
        assert row.new_values, "before/after per facet are recorded"
    finally:
        audit_context.clear_actor(db)


def test_u17_same_sheet_again_is_zero_applied_and_every_contact_no_change(client, db, w):
    _dealer(db, w)
    ids = [_contact(db, w, 1), _contact(db, w, 2)]
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT", "MCH"], OWNER)),
            ("ZZT Bob", "+60100000002", _tags(DEALER, ["SRT", "MCH"], EMPLOYEE)),
        ]
    )
    _, first = _apply_all(client, content)
    assert first["counts"]["applied"] == 2
    state = [_state(db, w, c) for c in ids]
    audits = len(_audits(db, w))
    _, second = _apply_all(client, content)
    assert second["counts"]["applied"] == 0
    assert second["counts"]["no_change"] == 2
    assert all(c["status"] == "no_change" and c["changes"] == [] for c in _by_name(second).values())
    assert [_state(db, w, c) for c in ids] == state
    assert len(_audits(db, w)) == audits


# ================================================================ U18 permission and facets


def test_u18_without_contacts_edit_is_403(client, db, w, env):
    env["granted"] = {AGENTS_EDIT, STOCK_EDIT}
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])
    assert _post(client, content).status_code == 403
    assert _post(client, content, dry_run=False, confirmed={}).status_code == 403


def test_u18_non_superadmin_companies_are_not_applied_and_listed(client, db, w, env):
    env["superadmin"] = False
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1)
    _, result = _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    s = _state(db, w, cid)
    assert s["companies"] == []
    assert "dealer" in s["types"], "the facets the caller may set are still written"
    contact = _by_name(result)["ZZT Ann"]
    assert "companies" in contact["not_applied"]
    assert contact["status"] == "applied"


def test_u18_without_stock_edit_locations_are_not_applied(client, db, w, env):
    env["granted"] = {EDIT, AGENTS_EDIT}
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1)
    _, result = _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    assert _state(db, w, cid)["stock"] is None
    assert {"stock_check_mode", "stock_locations"} <= set(_by_name(result)["ZZT Ann"]["not_applied"])


def test_u18_without_agents_edit_grants_are_not_applied(client, db, w, env):
    env["granted"] = {EDIT, STOCK_EDIT}
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1)
    _, result = _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    assert _state(db, w, cid)["grants"] == []
    assert "agent_access" in _by_name(result)["ZZT Ann"]["not_applied"]


# ================================================================ U19 scope


def test_u19_customers_outside_the_callers_scope_are_never_proposed(client, db, w):
    visible = _cust(db, w, w.srt, DEALER)
    hidden = _cust(db, w, w.zzo, DEALER)
    _contact(db, w, 1)
    block = _block(_post(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])).json())
    ids = {a["customer_id"] for a in block["accounts"]}
    assert visible in ids
    assert hidden not in ids


def test_u19_a_confirmed_id_outside_scope_is_422_and_nothing_is_written(client, db, w):
    _cust(db, w, w.srt, DEALER)
    hidden = _cust(db, w, w.zzo, DEALER)
    cid = _contact(db, w, 1)
    before = _state(db, w, cid)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])
    resp = _post(client, content, dry_run=False, confirmed={KEY: [hidden]})
    assert resp.status_code == 422, resp.text
    assert _state(db, w, cid) == before
    assert _audits(db, w) == []


# ================================================================ ROUND 2 (UAC rewrite 26 Oct): U8 name key


TAG_TEXTS = ["A/C I", "A/C II", "A/C III", "A/C IV", "BRAVAT", "IBORN", "PROJECT-CASH"]


def _tag_fillers(db, w, tags=TAG_TEXTS, bases=10, company=None):
    """Account tags are DATA: a bracket text on >= 10 different base names. Seed that many bases."""
    for tag in tags:
        for i in range(bases):
            _cust(db, w, company or w.srt, f"ZZT FILLER {unique_code('F', alpha=True)[-6:]} {i} SDN BHD [{tag}]")


def _exact(body, key):
    return {a["customer_id"] for a in _block(body, key)["accounts"] if a["match"] == "exact"}


def _preview_for(client, dealer, companies=("SRT",)):
    return _post(client, _sheet([("ZZT Ann", "+60100000001", _tags(dealer, list(companies), OWNER))])).json()


def test_u8_ampersand_dealer_matches_only_the_spaced_ampersand_accounts(client, db, w):
    _tag_fillers(db, w)
    a = _cust(db, w, w.srt, "J & Y WORLD HARDWARE SDN BHD [A/C I]")
    b = _cust(db, w, w.srt, "J & Y WORLD HARDWARE SDN BHD [A/C III]")
    other = [
        _cust(db, w, w.srt, "J & M LIGHTING SDN BHD [A/C I]"),
        _cust(db, w, w.srt, "J & W TIMBER SDN BHD"),
    ]
    _contact(db, w, 1)
    body = _preview_for(client, "J&Y WORLD HARDWARE")
    exact = _exact(body, "j y world hardware")
    assert exact == {a, b}
    assert not (exact & set(other))


def test_u8_a_branch_in_brackets_is_part_of_the_name(client, db, w):
    _tag_fillers(db, w)
    ipoh = _cust(db, w, w.srt, "SUPER CERAMIC TILES (JLN IPOH) SDN BHD [A/C I]")
    jb = _cust(db, w, w.srt, "SUPER CERAMIC TILES (JB) SDN BHD [A/C I]")
    klang = _cust(db, w, w.srt, "SUPER CERAMIC TILES (KLANG) SDN BHD [A/C I]")
    _contact(db, w, 1)
    body = _preview_for(client, "Super ceramic tiles (Jln Ipoh)")
    (block,) = body["blocks"]
    exact = {a["customer_id"] for a in block["accounts"] if a["match"] == "exact"}
    assert exact == {ipoh}
    assert jb not in exact and klang not in exact


def test_u8_every_account_tag_form_is_dropped_so_all_accounts_are_exact(client, db, w):
    _tag_fillers(db, w)
    names = [
        "ALPHA BATH SDN BHD [A/C I]", "ALPHA BATH SDN BHD [A/C II]", "ALPHA BATH SDN BHD [A/C III]",
        "ALPHA BATH SDN BHD [A/C IV]", "ALPHA BATH SDN BHD (BRAVAT)", "ALPHA BATH SDN BHD - [IBORN]",
        "ALPHA BATH SDN BHD (PROJECT-CASH)",
    ]
    ids = {_cust(db, w, w.srt, n) for n in names}
    _contact(db, w, 1)
    body = _preview_for(client, DEALER)
    assert _exact(body, KEY) == ids


@pytest.mark.parametrize("bases, dropped", [(8, True), (7, False)])
def test_u8_a_bracket_text_is_a_tag_only_on_eight_or_more_base_names(client, db, w, bases, dropped):
    # the dealer's own account is one of the `bases` base names carrying the bracket text
    _tag_fillers(db, w, tags=["ZZ ODD TAG"], bases=bases - 1)
    own = _cust(db, w, w.srt, "NINE BASE TILES SDN BHD [ZZ ODD TAG]")
    _contact(db, w, 1)
    body = _preview_for(client, "NINE BASE TILES SDN BHD")
    block = [b for b in body["blocks"] if b["dealer"].startswith("NINE BASE")][0]
    exact = {a["customer_id"] for a in block["accounts"] if a["match"] == "exact"}
    assert (own in exact) is dropped


# ================================================================ ROUND 2: U14 confirmed required, U14a limits


def test_u14_apply_without_confirmed_is_422_and_writes_nothing(client, db, w):
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1)
    before = _state(db, w, cid)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])
    resp = _post(client, content, dry_run=False)
    assert resp.status_code == 422, resp.text
    assert _state(db, w, cid) == before
    assert _audits(db, w) == []


def test_u14_empty_confirmed_skips_every_contact_as_dealer_not_confirmed(client, db, w):
    _dealer(db, w, companies=("SRT",))
    ids = [_contact(db, w, 1), _contact(db, w, 2)]
    before = [_state(db, w, c) for c in ids]
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
            ("ZZT Bob", "+60100000002", _tags(DEALER, ["SRT"], EMPLOYEE)),
        ]
    )
    body = _post(client, content, dry_run=False, confirmed={}).json()
    assert {c["skip_reason"] for c in _by_name(body).values()} == {"dealer_not_confirmed"}
    assert body["counts"]["applied"] == 0 and body["counts"]["skipped"] == 2
    assert [_state(db, w, c) for c in ids] == before


def test_u14a_tags_cell_over_1000_chars_is_a_row_error(client, db, w):
    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1)
    before = _state(db, w, cid)
    tags = _tags(DEALER, ["SRT"], OWNER) + ", " + "x" * 1000
    assert len(tags) > 1000
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", tags)])).json()
    assert body["counts"]["row_errors"] == 1 and len(body["errors"]) == 1
    assert _state(db, w, cid) == before


@pytest.mark.parametrize("alts, is_error", [(5, False), (6, True)])
def test_u14a_more_than_five_alt_dealer_texts_is_a_row_error(client, db, w, alts, is_error):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1)
    tags = f"{DEALER}, {SRT_TAG}, ZZT AGENT SRT, " + ", ".join(f"ALT DEALER {i}" for i in range(alts)) + f", {OWNER}"
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", tags)])).json()
    assert body["counts"]["row_errors"] == (1 if is_error else 0), body["errors"]


def test_u14a_a_csv_field_over_the_parser_limit_is_422_not_500(client, db, w):
    _contact(db, w, 1)
    huge = "y" * 140_000  # over Python's csv field limit (131072)
    content = _sheet([("ZZT Ann", "+60100000001", huge)])
    assert len(content) < 2 * 1024 * 1024
    resp = _post(TestClient(app, raise_server_exceptions=False), content)
    assert resp.status_code == 422, resp.text[:300]
    low = resp.text.lower()
    assert "select " not in low and "psycopg" not in low and "sqlalchemy" not in low


# ================================================================ ROUND 2: U14b honest changes, U15, U16


def test_u14b_null_brands_show_as_every_brand_before(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1, brand_ids=None)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])
    contact = _by_name(_post(client, content).json())["ZZT Ann"]
    (change,) = [c for c in contact["changes"] if c["facet"] == "brands"]
    assert change["before"] == "every brand"
    assert "ZZT ZSB-1" in str(change["after"])


def test_u14b_a_facet_the_caller_cannot_set_is_no_change_no_audit_and_not_listed(client, db, w, env):
    env["granted"] = {EDIT, AGENTS_EDIT}  # no inventory.stock.edit
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])
    _, first = _apply_all(client, content)
    contact = _by_name(first)["ZZT Ann"]
    assert {"stock_check_mode", "stock_locations"} <= set(contact["not_applied"])
    assert not {c["facet"] for c in contact["changes"]} & {"stock_check_mode", "stock_locations"}
    audits = len(_audits(db, w))
    _, second = _apply_all(client, content)
    assert _by_name(second)["ZZT Ann"]["status"] == "no_change"
    assert second["counts"]["applied"] == 0
    assert len(_audits(db, w)) == audits


def test_u15_a_row_error_counts_in_skipped(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1)
    _contact(db, w, 2)
    content = _sheet(
        [
            ("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
            ("ZZT NoRole", "+60100000002", f"{DEALER}, {SRT_TAG}, ZZT AGENT SRT"),
        ]
    )
    _, result = _apply_all(client, content)
    assert result["counts"]["row_errors"] == 1
    assert result["counts"]["applied"] == 1
    assert result["counts"]["skipped"] == 1


def test_u16_the_audit_row_keeps_the_requests_full_audit_context(client, db, w, actor):
    from app import audit_context

    _dealer(db, w, companies=("SRT",))
    cid = _contact(db, w, 1)
    session_id = str(uuid.uuid4())
    audit_context.stamp_actor(
        audit_context.AuditActor(
            actor_type="user", user_id=actor, real_user_id=actor, auth_method="password",
            session_id=session_id, ip_address="203.0.113.7", user_agent="zzt-agent/1.0",
        ),
        db=db,
    )
    try:
        _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    finally:
        audit_context.clear_actor(db)
    (row,) = _audits(db, w, cid)
    assert str(row.user_id) == actor
    assert row.auth_method == "password"
    assert str(row.session_id) == session_id
    assert row.ip_address == "203.0.113.7"
    assert row.user_agent == "zzt-agent/1.0"


# ================================================================ ROUND 2 addendum: U19a one ACTIVE company, grants widening

GRANTS = {"company_scope": "grants"}


def _grant(db, user_id, *company_ids):
    from app.models.company import UserCompany

    for company_id in company_ids:
        db.add(UserCompany(user_id=user_id, company_id=company_id))
    db.flush()
    db.commit()


def test_u19a_a_user_granted_srt_and_mch_with_srt_active_resolves_mocha_under_grants(client, db, w, env, actor):
    env["superadmin"] = False
    env["scope"] = frozenset({w.srt})  # staff requests run under ONE active company
    _grant(db, actor, w.srt, w.mch)
    ids = _dealer(db, w)
    cid = _contact(db, w, 1)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT", "MCH"], OWNER))])
    pre = _post(client, content, params=GRANTS)
    assert pre.status_code == 200, pre.text
    block = _block(pre.json())
    assert block["status"] == "exact"
    assert {a["customer_id"] for a in block["accounts"] if a["match"] == "exact" and a["proposed"]} == set(ids.values())
    res = _post(client, content, dry_run=False, confirmed=_confirm_all(pre.json()), params=GRANTS)
    assert res.status_code == 200, res.text
    s = _state(db, w, cid)
    assert s["stock"]["warehouses"] == sorted([w.wh["BRW"], w.wh["MWH"], w.wh["HQ"], w.wh["MOCHA-WH"]])
    assert sorted(l[0] for l in s["links"]) == sorted(ids.values())


def test_u19a_a_user_granted_srt_only_gets_422_naming_mocha_not_500(client, db, w, env, actor):
    env["superadmin"] = False
    env["scope"] = frozenset({w.srt})
    _grant(db, actor, w.srt)
    _dealer(db, w)
    cid = _contact(db, w, 1)
    before = _state(db, w, cid)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["MCH"], OWNER))])
    tc = TestClient(app, raise_server_exceptions=False)
    for dry_run, confirmed in ((True, None), (False, {})):
        resp = _post(tc, content, dry_run=dry_run, confirmed=confirmed, params=GRANTS)
        assert resp.status_code == 422, resp.text[:400]
        assert "MCH" in resp.text or "Mocha" in resp.text
    assert _state(db, w, cid) == before
    assert _audits(db, w) == []


# ================================================================ ROUND 3: U8 suffix-only segment, U13 already_configured, apply never ranks


def test_u8_a_suffix_only_bracket_is_always_dropped_even_when_rare(client, db, w):
    _tag_fillers(db, w, tags=["A/C I"])
    acct = _cust(db, w, w.srt, "ALPHA BATH (M) SDN BHD [A/C I]")  # "(M)" sits on this one base name only
    _contact(db, w, 1)
    body = _preview_for(client, DEALER)
    assert acct in _exact(body, KEY)


def test_u13_already_configured_counts_found_contacts_holding_any_type_or_link(client, db, w):
    from app.models.access import RespondContactCustomer

    cust = _cust(db, w, w.srt, DEALER)
    typed = _contact(db, w, 1, types=_types(db, "end_user"))
    linked = _contact(db, w, 2)
    _contact(db, w, 3)
    set_company_scope(db, w.all)
    db.add(RespondContactCustomer(contact_id=linked, customer_id=cust, company_id=w.srt, source="manual"))
    db.commit()
    tags = _tags(DEALER, ["SRT"], OWNER)
    content = _sheet(
        [("ZZT Ann", "+60100000001", tags), ("ZZT Bob", "+60100000002", tags), ("ZZT Cy", "+60100000003", tags)]
    )
    body = _post(client, content).json()
    assert body["counts"]["contacts_found"] == 3
    assert body["counts"]["already_configured"] == 2
    assert typed and linked


def test_u13_apply_never_ranks_and_reports_a_non_exact_block_as_pick(client, db, w, monkeypatch):
    from app.services import contact_access_sheet_service as svc

    exact_srt = _cust(db, w, w.srt, DEALER)
    for suffix in ("S", "E", "X"):
        _cust(db, w, w.mch, f"ALPHA BATH{suffix} SDN BHD")  # similar MCH names: the preview ranks these
    cid = _contact(db, w, 1)
    content = _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT", "MCH"], OWNER))])
    pre = _post(client, content).json()
    assert _block(pre)["status"] == "pick"

    class NoRanking:
        def __init__(self, *a, **kw):
            raise AssertionError("apply must not rank candidates")

    monkeypatch.setattr(svc, "SequenceMatcher", NoRanking)
    resp = _post(client, content, dry_run=False, confirmed={KEY: [exact_srt]})
    assert resp.status_code == 200, resp.text
    assert _block(resp.json())["status"] == "pick"
    assert [l[0] for l in _state(db, w, cid)["links"]] == [exact_srt]


# ================================================================ BULK-ACCESS-PREVIEW (owner rulings 27 Oct)
# UAC documentation/plans/contacts/bulk-access-preview-27oct-acceptance-criteria.md P1-P6.


def _yoo(db, w):
    """The real card's shape, invented names: three MCH and three SRT accounts of one dealer."""
    _tag_fillers(db, w, tags=["A/C I", "A/C II", "A/C III"])
    return {
        c: [_cust(db, w, w.co[c], f"{DEALER} [A/C {n}]", code=unique_code(f"{c}{n}")) for n in ("I", "II", "III")]
        for c in ("MCH", "SRT")
    }


def _two_contacts_sheet():
    return _sheet(
        [
            ("ZZT Shi", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
            ("ZZT Wong", "+60100000002", _tags(DEALER, ["SRT", "MCH"], OWNER)),
        ]
    )


def test_p1_sorento_only_row_gets_only_the_srt_accounts_and_both_row_gets_all_six(client, db, w):
    accts = _yoo(db, w)
    shi, wong = _contact(db, w, 1), _contact(db, w, 2)
    preview, result = _apply_all(client, _two_contacts_sheet())
    assert sorted(l[0] for l in _state(db, w, shi)["links"]) == sorted(accts["SRT"])
    assert sorted(l[0] for l in _state(db, w, wong)["links"]) == sorted(accts["SRT"] + accts["MCH"])
    # the preview's change shows the same thing the apply wrote
    by = _by_name(preview)
    (links,) = [c for c in by["ZZT Shi"]["changes"] if c["facet"] == "customers"]
    assert len(links["after"]) == 3 and all("[A/C" in label for label in links["after"])
    assert not any(code in " ".join(links["after"]) for code in ("MCHI", "MCHII", "MCHIII"))


def test_p1_the_same_sheet_again_is_no_change_for_every_contact(client, db, w):
    _yoo(db, w)
    _contact(db, w, 1)
    _contact(db, w, 2)
    _apply_all(client, _two_contacts_sheet())
    _, again = _apply_all(client, _two_contacts_sheet())
    assert again["counts"]["applied"] == 0
    assert {c["status"] for c in _by_name(again).values()} == {"no_change"}


def test_p1_an_account_of_a_company_no_row_can_tag_links_to_nobody(client, db, w):
    srt = _cust(db, w, w.srt, DEALER)
    zzx = _cust(db, w, w.zzx, DEALER)
    cid = _contact(db, w, 1)
    preview, _ = _apply_all(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))]))
    accounts = {a["customer_id"]: a for a in _block(preview)["accounts"]}
    assert accounts[zzx]["links_to"] == []
    assert accounts[srt]["links_to"] == ["ZZT Ann"]
    assert [l[0] for l in _state(db, w, cid)["links"]] == [srt]


def test_p3_links_to_names_every_found_contact_whose_row_tags_the_company(client, db, w):
    accts = _yoo(db, w)
    _contact(db, w, 1)
    _contact(db, w, 2)
    content = _sheet(
        [
            ("ZZT Shi", "+60100000001", _tags(DEALER, ["SRT"], OWNER)),
            ("ZZT Wong", "+60100000002", _tags(DEALER, ["SRT", "MCH"], OWNER)),
            ("ZZT Ghost", "+60100000077", _tags(DEALER, ["SRT", "MCH"], EMPLOYEE)),  # not in the CRM
        ]
    )
    accounts = {a["customer_id"]: a for a in _block(_post(client, content).json())["accounts"]}
    for i in accts["SRT"]:
        assert accounts[i]["links_to"] == ["ZZT Shi", "ZZT Wong"]
    for i in accts["MCH"]:
        assert accounts[i]["links_to"] == ["ZZT Wong"]


def test_p2_p4_a_link_outside_the_rows_companies_is_kept_and_listed(client, db, w):
    from app.services.contact_customer_service import link_customer

    accts = _yoo(db, w)
    shi = _contact(db, w, 1)
    set_company_scope(db, w.all)
    link_customer(db, shi, accts["MCH"][0])  # the wrong link the first import made
    db.commit()
    _contact(db, w, 2)
    preview, result = _apply_all(client, _two_contacts_sheet())
    for body in (preview, result):
        shi_entry = _by_name(body)["ZZT Shi"]
        assert len(shi_entry["outside_links"]) == 1
        assert "[A/C I]" in shi_entry["outside_links"][0] and "MCH" in shi_entry["outside_links"][0]
        assert _by_name(body)["ZZT Wong"]["outside_links"] == []
    links = sorted(l[0] for l in _state(db, w, shi)["links"])
    assert links == sorted([accts["MCH"][0], *accts["SRT"]]), "apply is add-only: the MCH link stays"


def test_p4_outside_links_show_even_when_nothing_else_changes(client, db, w):
    from app.services.contact_customer_service import link_customer

    accts = _yoo(db, w)
    shi = _contact(db, w, 1)
    _contact(db, w, 2)
    _apply_all(client, _two_contacts_sheet())
    set_company_scope(db, w.all)
    link_customer(db, shi, accts["MCH"][1])
    db.commit()
    body = _post(client, _two_contacts_sheet()).json()
    entry = _by_name(body)["ZZT Shi"]
    assert entry["status"] == "no_change"
    assert len(entry["outside_links"]) == 1 and "[A/C II]" in entry["outside_links"][0]


def test_p6_holds_more_lists_what_is_extra_per_facet(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(
        db, w, 1,
        types=_types(db, "zzt_extra", "end_user"),
        companies=[w.zzx],
        brand_ids=[w.brands["X1"], w.brands["S1"]],
        warehouses=[w.wh["SRT-OTHER"], w.wh["BRW"]],
    )
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])).json()
    entry = _by_name(body)["ZZT Ann"]
    assert "holds_more" in entry["warnings"]
    items = {h["facet"]: h["items"] for h in entry["holds_more_items"]}
    assert items == {
        "access_types": ["zzt_extra"],
        "companies": ["ZZX"],
        "stock_locations": ["ZZT-OTHER"],
        "brands": ["ZZT ZXB-1"],
    }


def test_p6_a_contact_within_its_template_has_no_holds_more_items(client, db, w):
    _dealer(db, w, companies=("SRT",))
    _contact(db, w, 1, types=_types(db, "end_user"))
    body = _post(client, _sheet([("ZZT Ann", "+60100000001", _tags(DEALER, ["SRT"], OWNER))])).json()
    entry = _by_name(body)["ZZT Ann"]
    assert entry["holds_more_items"] == [] and "holds_more" not in entry["warnings"]
