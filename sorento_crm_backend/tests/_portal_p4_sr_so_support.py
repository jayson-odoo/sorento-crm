"""Shared world for the PORTAL-P4-REQUESTS Sample Request + Sales Opportunity tests (slices S4, S6).

Builds on `tests/_portal_p4_support.py` (`scene`: blank Postgres schema, real Bearer sessions, a
real PortalToken per contact, `enqueue_job` recorded). On top of it: a salesperson `rep` with a
linked contact and an active sales agent, a second salesperson (`other`) with their own agent, and
the status graphs the two forms need.

    P4_CONTROL=1 pytest tests/test_portal_p4_my_requests_sample_request.py ...

re-points `World.me` at the PORTAL (real token), a self-check of the steps against code that
exists today, so a red run can only mean "the my-requests surface is missing or wrong".

Slugs (verified in app/rbac/permission_registry.py and the staff routers):
  sample request  projects.sample_requests.{view,view_own,create,process}   (create, not add)
  opportunity     sales.opportunities.{view,view_own,add,edit,delete}
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from tests import _portal_p4_support as s
from tests._portal_grant import grant_portal_forms, link_contact_company
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture, re-exported)
from tests._sample_request_seed import full_payload, make_product

SR = "/api/v1/project-sales/sample-requests"
SO_STAFF = "/api/v1/sales/opportunities"
SR_PORTAL = "/submissions/sample_request"  # the same path under the portal and under /my-requests
SO_PORTAL = "/sales-opportunities"

SR_VIEW, SR_VIEW_OWN, SR_CREATE = (
    "projects.sample_requests.view",
    "projects.sample_requests.view_own",
    "projects.sample_requests.create",
)
SR_PROCESS = "projects.sample_requests.process"
SO_VIEW, SO_VIEW_OWN, SO_ADD, SO_EDIT, SO_DELETE = (
    "sales.opportunities.view",
    "sales.opportunities.view_own",
    "sales.opportunities.add",
    "sales.opportunities.edit",
    "sales.opportunities.delete",
)
REP_PERMS = [SR_VIEW_OWN, SR_CREATE, SO_VIEW_OWN, SO_ADD, SO_EDIT]


@dataclass
class Person:
    contact: object
    portal: s.Api  # the portal, real PortalToken of this contact
    actor: s.Actor
    agent: SalesAgent
    mine: Customer  # a customer of this person's agent
    me: s.Api  # /api/v1/my-requests as this person (the portal itself in control mode)


@dataclass
class World:
    sc: object
    rep: Person
    other: Person
    product: object
    company_id: str

    @property
    def client(self):
        return self.sc.client

    def staff(self, actor: s.Actor, method: str, path: str, **kw):
        return self.client.request(method, path, headers=actor.headers, **kw)

    def sr_body(self, **over) -> dict:
        return full_payload(product_id=self.product.id, **over)

    def so_body(self, **over) -> dict:
        body = {
            "title": f"ZZT deal {s.uid()[:6]}",
            "expected_amount": "500",
            "expected_close_date": (date.today() + timedelta(days=30)).isoformat(),
            "prospect_name": f"ZZT prospect {s.uid()[:6]}",
        }
        body.update(over)
        return body

    def person(self, name: str, *, perms=REP_PERMS, agent_code: str | None = None) -> Person:
        sc = self.sc
        contact, portal = s.own_contact(sc)
        link_contact_company(sc.db, contact.id)
        grant_portal_forms(sc.db, contact.id, ["sample_request", "sales_opportunity"])
        agent = SalesAgent(
            id=s.uid(), sales_agent=agent_code or f"ZZA-{s.uid()[:8]}".upper(), description=f"ZZT {name}",
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
    from app.services import project_seed_service
    from app.services.sales import sales_seed_service

    db = scene.db
    project_seed_service.run(db, company_id=s.SORENTO)
    sales_seed_service.run(db)
    product = make_product(db)
    db.flush()
    w = World(sc=scene, rep=None, other=None, product=product, company_id=s.SORENTO)
    w.rep = w.person("Rep", agent_code=f"ZZA-A-{s.uid()[:6]}".upper())
    w.other = w.person("Other", agent_code=f"ZZA-B-{s.uid()[:6]}".upper())
    db.commit()
    return w


def sr_row(w: World, sid: str):
    from app.models.sample_request import SampleRequest

    w.sc.db.expire_all()
    return w.sc.db.query(SampleRequest).filter(SampleRequest.id == sid).one()


def so_row(w: World, oid: str):
    from app.models.sales import SalesOpportunity

    w.sc.db.expire_all()
    return w.sc.db.query(SalesOpportunity).filter(SalesOpportunity.id == oid).one()
