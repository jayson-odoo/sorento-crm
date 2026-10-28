"""PORTAL-P4-REQUESTS red tests: a LIMITED salesperson (holds `<kind>.view_own`, not `.view`) on the CRM
My Requests pages follows their CONTACT's company, as the portal does, not the user's single active
company (crew answer a94723506 (a), owner direction).

World: companies A (Sorento, the user's active company) and B. The salesperson's contact, sales agent
and debtors, and every request they own, sit in B. Another salesperson's rows in B must stay hidden;
a staff `.view` holder keeps the one-active-company rule (sees A only).

Postgres only (`blank_session`), every row seeded here.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.models.company import Company
from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from tests import _portal_p4_support as s
from tests import _ptag_r9_seed
from tests._portal_grant import grant_portal_forms, link_contact_company
from tests._portal_p4_support import scene  # noqa: F401  (fixture)
from tests._pg_fixture import unique_code
from tests._sample_request_seed import full_payload, make_product

SI = "/api/v1/procurement/stock-inquiries"
NPA = "/api/v1/procurement/new-product-applications"
PT = "/api/v1/dealer-kit/price-tag-requests"
SR = "/api/v1/project-sales/sample-requests"
SO = "/api/v1/sales/opportunities"
KINDS = ["stock_inquiry", "new_product_application", "price_tag_request", "sample_request", "sales_opportunity"]

REP_PERMS = [
    "procurement.stock_inquiries.view_own", "procurement.stock_inquiries.add",
    "procurement.new_product_applications.view_own", "procurement.new_product_applications.create",
    "dealer_kit.price_tag_requests.view_own", "dealer_kit.price_tag_requests.create",
    "projects.sample_requests.view_own", "projects.sample_requests.create",
    "sales.opportunities.view_own", "sales.opportunities.add", "sales.opportunities.edit",
]
STAFF_PERMS = [
    "procurement.stock_inquiries.view", "procurement.new_product_applications.view",
    "dealer_kit.price_tag_requests.view", "projects.sample_requests.view", "sales.opportunities.view",
]


@dataclass
class Person:
    contact: object
    portal: s.Api
    actor: s.Actor
    customer: Customer
    company_id: str = ""


@dataclass
class W:
    sc: object
    company_b: str
    product: object
    pt_product: object
    products_a: tuple  # (sample request product, price tag product) in company A
    rep: Person  # active company A, contact + rows in B
    other: Person  # another salesperson in B
    home: Person  # a salesperson in A (the control's A row)
    staff: s.Actor  # `.view` holder, active company A

    def get(self, who, path, **kw):
        actor = who.actor if isinstance(who, Person) else who
        return self.sc.client.get(path, headers=actor.headers, **kw)

    def my(self, who: Person, path, **kw):
        return self.sc.client.get(f"{s.MY}{path}", headers=who.actor.headers, **kw)


def _person(sc, company_id: str, name: str, perms) -> Person:
    contact, portal = s.own_contact(sc)
    link_contact_company(sc.db, contact.id, company_id)
    grant_portal_forms(sc.db, contact.id, KINDS)
    agent = SalesAgent(
        id=s.uid(), sales_agent=f"ZZA-{s.uid()[:8]}".upper(), description=f"ZZT {name}",
        is_active=True, contact_id=contact.id, company_id=company_id,
    )
    sc.db.add(agent)
    sc.db.flush()
    cust = Customer(
        id=s.uid(), company_id=company_id, customer_code=f"ZZT-{s.uid()[:6]}",
        customer_name=f"ZZT {name} debtor", sales_agent_id=agent.id,
    )
    sc.db.add(cust)
    sc.db.flush()
    actor = s.make_user(sc.db, perms=perms, contact=contact, name=f"ZZT {name}")
    return Person(contact=contact, portal=portal, actor=actor, customer=cust, company_id=company_id)


@pytest.fixture
def w(scene):  # noqa: F811
    from app.services import project_seed_service
    from app.services.sales import sales_seed_service

    db = scene.db
    b = Company(id=s.uid(), name="ZZT Mocha", code=unique_code("ZB")[:50])
    db.add(b)
    db.flush()
    project_seed_service.run(db, company_id=s.SORENTO)
    project_seed_service.run(db, company_id=b.id)
    sales_seed_service.run(db)
    product = make_product(db)
    pt_product = _ptag_r9_seed.seed_product(db)
    for prod in (product, pt_product):  # the contact's company owns the catalogue they order from
        for obj in (prod, prod.category, prod.brand, prod.base_uom):
            if hasattr(obj, "company_id"):
                obj.company_id = b.id
    db.flush()
    rep = _person(scene, b.id, "Rep", REP_PERMS)
    other = _person(scene, b.id, "Other", REP_PERMS)
    home = _person(scene, s.SORENTO, "Home", REP_PERMS)
    staff = s.make_user(db, perms=STAFF_PERMS, name="ZZT Staff A")
    db.commit()
    return W(sc=scene, company_b=b.id, product=product, pt_product=pt_product, products_a=(make_product(db), _ptag_r9_seed.seed_product(db)), rep=rep, other=other, home=home, staff=staff)


# ---- row creation through the portal (the contact's own company, B for rep / other) ---------------

def _si(p: Person, w: W) -> str:
    body = s.SPECS["stock_inquiry"].body(w.sc, contact=p.contact)
    return s.ok(p.portal.create("stock_inquiry", body)).json()["id"]


def _npa(p: Person, w: W) -> str:
    body = {"customer_name": "ZZT typed customer", "project_name": "ZZT project",
            "lines": [{"proposed_code": f"ZZT-{s.uid()[:6]}", "description": "ZZT sink", "expected_qty": "5"}]}
    return s.ok(p.portal.call("POST", "/submissions/new_product_application", json=body), 201).json()["id"]


def _pt(p: Person, w: W) -> str:
    body = {"debtor_code": p.customer.customer_code, "debtor_name": p.customer.customer_name,
            "print_by": "office", "notes": "ZZT",
            "lines": [{"line_type": "product", "product_id": (w.pt_product if p.company_id == w.company_b else w.products_a[1]).id, "quantity": 2}]}
    return s.ok(p.portal.call("POST", "/submissions/price_tag_request", json=body), 201).json()["id"]


def _sr(p: Person, w: W) -> str:
    body = full_payload(product_id=(w.product if p.company_id == w.company_b else w.products_a[0]).id)
    return s.ok(p.portal.call("POST", "/submissions/sample_request", json=body), 201).json()["id"]


def _so(p: Person, w: W) -> str:
    body = {"title": f"ZZT deal {s.uid()[:6]}", "expected_amount": "500",
            "expected_close_date": "2030-01-01", "prospect_name": f"ZZT prospect {s.uid()[:6]}"}
    return s.ok(p.portal.call("POST", "/sales-opportunities", json=body), 201).json()["id"]


#: id, create-through-portal, staff list path, staff list rows key, staff detail path
FORMS = {
    "si": (_si, SI, "data", SI),
    "npa": (_npa, NPA, "items", NPA),
    "pt": (_pt, PT, "data", PT),
    "sr": (_sr, SR, "data", SR),
    "so": (_so, SO, "data", SO),
}


def _ids(r) -> set:
    body = s.ok(r).json()
    rows = body.get("data") if body.get("data") is not None else body.get("items")
    return {x["id"] for x in rows}


@pytest.mark.parametrize("form", list(FORMS))
def test_p4_cs_limited_salesperson_list_shows_own_rows_in_the_contacts_company(w, form):
    create, path, _, _ = FORMS[form]
    own = create(w.rep, w)
    assert own in _ids(w.get(w.rep, path)), "own row in company B hidden under active company A"


@pytest.mark.parametrize("form", list(FORMS))
def test_p4_cs_limited_salesperson_own_detail_in_the_contacts_company_is_200(w, form):
    create, _, _, detail = FORMS[form]
    own = create(w.rep, w)
    r = w.get(w.rep, f"{detail}/{own}")
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    assert r.json()["id"] == own


@pytest.mark.parametrize("form", list(FORMS))
def test_p4_cs_guard_another_contacts_rows_in_the_same_company_stay_invisible(w, form):
    create, path, _, detail = FORMS[form]
    mine = create(w.rep, w)
    foreign = create(w.other, w)
    got = _ids(w.get(w.rep, path))
    assert mine in got, "own row hidden (widening absent)"
    assert foreign not in got, "widening leaked another contact's row"
    assert w.get(w.rep, f"{detail}/{foreign}").status_code == 404


def test_p4_cs_price_tag_debtor_picker_returns_the_contacts_company_debtors(w):
    portal = {d["customer_code"] for d in s.ok(w.rep.portal.call("GET", "/lookups/debtors-for-agent")).json()}
    assert w.rep.customer.customer_code in portal  # portal control: the picker is not empty there
    mine = {d["customer_code"] for d in s.ok(w.my(w.rep, "/lookups/debtors-for-agent")).json()}
    assert mine == portal, f"my-requests debtors {mine} != portal {portal}"
    assert w.other.customer.customer_code not in mine


def test_p4_cs_sample_request_customer_picker_matches_the_portal(w):
    portal = s.ok(w.rep.portal.call("GET", "/sample-request/customers")).json()
    mine = s.ok(w.my(w.rep, "/sample-request/customers")).json()
    assert mine == portal and portal, f"portal={portal!r} my={mine!r}"


def test_p4_cs_npa_customer_picker_matches_the_portal(w):
    portal = s.ok(w.rep.portal.call("GET", "/new-product-application/customers")).json()
    mine = s.ok(w.my(w.rep, "/new-product-application/customers")).json()
    assert mine == portal and portal, f"portal={portal!r} my={mine!r}"


@pytest.mark.parametrize("form", [f for f in FORMS if f != "si"])  # stock inquiries carry no company_id
def test_p4_cs_control_view_holder_keeps_the_one_active_company_rule(w, form):
    create, path, _, _ = FORMS[form]
    in_a, in_b = create(w.home, w), create(w.rep, w)
    if form in ("pt", "sr"):  # the staff default list is submitted rows only
        kind = {"pt": "price_tag_request", "sr": "sample_request"}[form]
        for who, rid in ((w.home, in_a), (w.rep, in_b)):
            s.ok(who.portal.call("POST", f"/submissions/{kind}/{rid}/submit"))
    got = _ids(w.get(w.staff, path))
    assert in_a in got and in_b not in got, f"A row seen={in_a in got}; B row leaked={in_b in got}"
