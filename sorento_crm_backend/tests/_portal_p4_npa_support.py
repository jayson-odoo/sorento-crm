"""Shared world for the PORTAL-P4-REQUESTS New Product Application tests (slice S5).

Builds on `tests/_portal_p4_support.py` (`scene`: blank Postgres schema, real Bearer sessions, a real
PortalToken per contact). On top of it: a salesperson `rep` (linked contact, active sales agent with one
debtor, the NPA grants) and a second salesperson `other`.

    P4_CONTROL=1 pytest tests/test_portal_p4_my_requests_npa.py ...

re-points `World.me` at the PORTAL (real token): a self-check of the steps against code that exists today,
so a red run can only mean "the my-requests surface is missing or wrong".

Slugs (verified in app/rbac/permission_registry.py:266-269 and app/services/new_product_application_service.py:44-48):
  procurement.new_product_applications.{view,view_own,create,approve,open_code}   (create, not add)
Paths (the portal router's, `public/portal_new_product_application.py:BASE/OWN`), identical under /my-requests:
  /submissions/new_product_application[/{id}[/submit|/revise|/cancel|/download]]
  /new-product-application/{inquiries,prefill,customers,lookups/brands}
  /attachments (generic portal upload, kind=new_product_application)
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from tests import _portal_p4_support as s
from tests._portal_grant import grant_portal_forms, link_contact_company
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture, re-exported)

KIND = "new_product_application"
NPA = "/api/v1/procurement/new-product-applications"  # the staff router
SUB = f"/submissions/{KIND}"  # the same path under the portal and under /my-requests
OWN = "/new-product-application"
ATT = "/attachments"

P = "procurement.new_product_applications"
NPA_VIEW, NPA_VIEW_OWN, NPA_CREATE = f"{P}.view", f"{P}.view_own", f"{P}.create"
NPA_APPROVE, NPA_OPEN = f"{P}.approve", f"{P}.open_code"
REP_PERMS = [NPA_VIEW_OWN, NPA_CREATE]


@dataclass
class Person:
    contact: object
    portal: s.Api
    actor: s.Actor
    agent: SalesAgent
    mine: Customer
    me: s.Api  # /api/v1/my-requests as this person (the portal itself in control mode)


@dataclass
class World:
    sc: object
    rep: Person
    other: Person
    company_id: str

    @property
    def client(self):
        return self.sc.client

    def staff(self, actor: s.Actor, method: str, path: str, **kw):
        return self.client.request(method, path, headers=actor.headers, **kw)

    def line(self, **over) -> dict:
        body = {"proposed_code": f"ZZT-{s.uid()[:6]}", "description": "ZZT kitchen sink", "expected_qty": "5"}
        body.update(over)
        return body

    def body(self, **over) -> dict:
        body = {"customer_name": "ZZT typed customer", "project_name": "ZZT project", "lines": [self.line()]}
        body.update(over)
        return body

    def inquiry(self, who: Person, **over):
        from app.models.procurement import StockInquiry

        row = StockInquiry(
            id=s.uid(), inquiry_number=f"SI26-Z{s.uid()[:4]}", product_code="ZZT-XY-1",
            item_description="ZZT sink, nanograin", project_customer="ZZT DEVELOPER SDN BHD",
            project_name="ZZT RESIDENCE", quantity="55", delivery_date="2028-01-17",
            purchasing_response="Please apply for a new code.", status="responded",
            contact_id=who.contact.id, space_id=self.sc.space_id,
        )
        for k, v in over.items():
            setattr(row, k, v)
        self.sc.db.add(row)
        self.sc.db.commit()
        return row

    def person(self, name: str, *, perms=REP_PERMS) -> Person:
        sc = self.sc
        contact, portal = s.own_contact(sc)
        link_contact_company(sc.db, contact.id)
        grant_portal_forms(sc.db, contact.id, [KIND])
        agent = SalesAgent(
            id=s.uid(), sales_agent=f"ZZA-{s.uid()[:8]}".upper(), description=f"ZZT {name}",
            is_active=True, contact_id=contact.id, company_id=self.company_id,
        )
        sc.db.add(agent)
        sc.db.flush()
        mine = Customer(
            id=s.uid(), company_id=self.company_id, customer_code=f"ZZT-{s.uid()[:6]}",
            customer_name=f"ZZT {name} debtor", sales_agent_id=agent.id,
        )
        sc.db.add(mine)
        actor = s.make_user(sc.db, perms=perms, contact=contact, name=f"ZZT {name}")
        me = portal if s.CONTROL else s.my_api(sc, actor)
        return Person(contact=contact, portal=portal, actor=actor, agent=agent, mine=mine, me=me)


@pytest.fixture
def world(scene):  # noqa: F811
    w = World(sc=scene, rep=None, other=None, company_id=s.SORENTO)
    w.rep = w.person("Rep")
    w.other = w.person("Other")
    scene.db.commit()
    return w


def npa_row(w: World, aid: str):
    from app.models.new_product_application import NewProductApplication

    w.sc.db.expire_all()
    return w.sc.db.query(NewProductApplication).filter(NewProductApplication.id == aid).one()


def create(api, w: World, **over) -> dict:
    return s.ok(api.call("POST", SUB, json=w.body(**over)), 201).json()
