"""Shared world for the PORTAL-P4-REQUESTS Price Tag Request tests (slice S7).

Builds on `tests/_portal_p4_support.py` (`scene`: blank Postgres schema, real Bearer sessions, a real
PortalToken per contact, `enqueue_job` recorded). On top of it: a salesperson `rep` (linked contact, TWO
active sales agents with one debtor each, the price tag grants), a second salesperson `other`, and a real
product for the lines.

    P4_CONTROL=1 pytest tests/test_portal_p4_my_requests_price_tag.py ...

re-points `World.me` at the PORTAL (real token): a self-check of the steps against code that exists today,
so a red run can only mean "the my-requests surface is missing or wrong".

Slugs (app/rbac/permission_registry.py:819-829 and pp4_0001): dealer_kit.price_tag_requests.{view,view_own,
create,process}. `view_own` is NEW in this lane.
Paths: the portal price tag router's (`public/portal_price_tag.py`), identical under /api/v1/my-requests:
  /submissions/price_tag_request[/{id}[/submit|/approve|/request-changes|/review-comments|/collect|/revise]]
  /lookups/{debtors-for-agent,price-tag-items,product-combos/{pid},line-pricing}
The STAFF router is /api/v1/dealer-kit/price-tag-requests (`dealer_kit/price_tag_requests.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.models.order import Customer
from app.models.sales_agent import SalesAgent
from tests import _portal_p4_support as s
from tests import _ptag_r9_seed
from tests._portal_grant import grant_portal_forms, link_contact_company
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture, re-exported)

KIND = "price_tag_request"
STAFF = "/api/v1/dealer-kit/price-tag-requests"
SUB = f"/submissions/{KIND}"  # the same path under the portal and under /my-requests
LOOK = "/lookups"

P = "dealer_kit.price_tag_requests"
PT_VIEW, PT_VIEW_OWN, PT_CREATE, PT_PROCESS = f"{P}.view", f"{P}.view_own", f"{P}.create", f"{P}.process"
REP_PERMS = [PT_VIEW_OWN, PT_CREATE]
#: what seed_revisions / seed_sla read off a Spec
SPEC = SimpleNamespace(kind=KIND, final_status="new")


@dataclass
class Person:
    contact: object
    portal: s.Api
    actor: s.Actor
    agents: list
    customers: list  # one per agent
    me: s.Api  # /api/v1/my-requests as this person (the portal itself in control mode)

    @property
    def mine(self):
        return self.customers[0]


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

    def body(self, **over) -> dict:
        body = {
            "debtor_code": self.rep.mine.customer_code,
            "debtor_name": self.rep.mine.customer_name,
            "print_by": "office",
            "notes": "ZZT note",
            "lines": [{"line_type": "product", "product_id": self.product.id, "quantity": 2}],
        }
        body.update(over)
        return body

    def person(self, name: str, *, perms=REP_PERMS, n_agents: int = 1) -> Person:
        sc = self.sc
        contact, portal = s.own_contact(sc)
        link_contact_company(sc.db, contact.id)
        grant_portal_forms(sc.db, contact.id, [KIND])
        agents, customers = [], []
        for i in range(n_agents):
            agent = SalesAgent(
                id=s.uid(), sales_agent=f"ZZA-{s.uid()[:8]}".upper(), description=f"ZZT {name} {i}",
                is_active=True, contact_id=contact.id, company_id=self.company_id,
            )
            sc.db.add(agent)
            sc.db.flush()
            cust = Customer(
                id=s.uid(), company_id=self.company_id, customer_code=f"ZZT-{s.uid()[:6]}",
                customer_name=f"ZZT {name} debtor {i}", sales_agent_id=agent.id,
            )
            sc.db.add(cust)
            agents.append(agent)
            customers.append(cust)
        actor = s.make_user(sc.db, perms=perms, contact=contact, name=f"ZZT {name}")
        me = portal if s.CONTROL else s.my_api(sc, actor)
        return Person(contact=contact, portal=portal, actor=actor, agents=agents, customers=customers, me=me)


@pytest.fixture
def world(scene):  # noqa: F811
    product = _ptag_r9_seed.seed_product(scene.db)
    scene.db.flush()
    w = World(sc=scene, rep=None, other=None, product=product, company_id=s.SORENTO)
    w.rep = w.person("Rep", n_agents=2)  # PORTAL-MULTI-AGENT: the debtor picker spans every agent
    w.other = w.person("Other")
    scene.db.commit()
    return w


def pt_row(w: World, rid: str):
    from app.models.price_tag import PriceTagRequest

    w.sc.db.expire_all()
    return w.sc.db.query(PriceTagRequest).filter(PriceTagRequest.id == rid).one()


def create(api, w: World, **over) -> dict:
    return s.ok(api.call("POST", SUB, json=w.body(**over)), 201).json()


def submitted(api, w: World, **over) -> str:
    rid = create(api, w, **over)["id"]
    s.ok(api.call("POST", f"{SUB}/{rid}/submit"))
    return rid


def to_proof(w: World, rid: str) -> None:
    """Marketing (the admin approver) claims the request and sends the proof."""
    s.ok(w.sc.staff_call("POST", f"{STAFF}/{rid}/claim"))
    s.ok(w.sc.staff_call("POST", f"{STAFF}/{rid}/transition", json={"status": "proof_ready"}))


def integration_logs(w: World, rid: str) -> list:
    from app.models.integration import IntegrationLog

    w.sc.db.expire_all()
    return w.sc.db.query(IntegrationLog).filter(IntegrationLog.business_id == rid).all()
