"""Shared world for the Order Change Notice (OCN-ORDER-CHANGE-NOTICE) suites, red-first.

UAC: documentation/plans/procurement/ocn-order-change-notice-acceptance-criteria.md
Plan: documentation/plans/procurement/PLAN-ocn-order-change-notice-12nov.md

Built on the forms-chain world (tests/_forms_chain_support.py): one TestClient over the REAL
routes on the blank Postgres scratch schema, real RBAC through real roles (`grant`), the real
SLA orchestrator. Everything the OCN needs is seeded here (CI's database is empty): the
numbering rule the migration seeds, the four change types, a project, a customer, two
catalogue products, and one user per role in the chain.

Contract assumptions this harness makes (named in the tester report, beyond the brief):

* `order_change_notice_service.actor_from_slugs(user_id, slugs) -> Actor` (the NPA template's
  name, `new_product_application_service.actor_from_slugs`), the `actor` every move takes.
* `create_draft(db, actor=..., data=dict)` / `update(db, row, actor=..., data=dict)` take a
  plain dict (what the router passes as `body.model_dump(exclude_unset=True)`).
* HTTP bodies: reject-submitted / void / revise `{"reason"}`, approval-decision
  `{"action", "comments"}` (the PR body), done `{"cs_comment"}`; submit and
  send-for-approval take no body.
* Detail/list rows carry `change_type_name`, `risk_level`, `guide_text` flat.

Test support only: no implementation lives here. All names are invented.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ._forms_chain_support import SORENTO, grant, settings_row, sla_chain, user

KIND = "order_change_notice"
OCN = "/api/v1/procurement/order-change-notices"
PROJECT_PANEL = "/api/v1/project-sales/projects/{project_id}/order-change-notices"
SVC = "app.services.order_change_notice_service"

VIEW = "procurement.order_change_notices.view"
VIEW_OWN = "procurement.order_change_notices.view_own"
CREATE = "procurement.order_change_notices.create"
EDIT = "procurement.order_change_notices.edit"
DELETE = "procurement.order_change_notices.delete"
APPROVE = "procurement.order_change_notices.approve"
REPORT = "procurement.order_change_notices.report"
ALL_SLUGS = (VIEW, VIEW_OWN, CREATE, EDIT, DELETE, APPROVE, REPORT)

#: The PR chain's shape (tests/test_forms_chain_purchase_request.py), on the three team sets
#: the plan names: main (project_sales), approval (project_sales_manager), CS (customer_service).
STAGES = (
    dict(team_set_code="project_sales", start_event="submit",
         resolve_event="send_for_approval,reject_submitted,voided",
         advance_on_event="send_for_approval"),
    dict(team_set_code="project_sales_manager", start_event="send_for_approval",
         resolve_event="approved,approval_rejected,voided", advance_on_event="approved"),
    dict(team_set_code="customer_service", start_event="approved", resolve_event="resolved,voided"),
)

#: The four seeded change types (UAC A5): name -> risk level.
SEEDED_TYPES = {"Advance": "Low", "Exchange": "High", "Cancellation": "Highest", "Delay": "Low"}


def svc():
    """The service module, imported at call time so a missing module fails THE TEST that
    needs it (red for the right reason), not the collection of every file."""
    import importlib

    return importlib.import_module(SVC)


def uid() -> str:
    return str(uuid.uuid4())


def yy() -> str:
    return f"{date.today().year % 100:02d}"


def number_pattern() -> str:
    return rf"^OCN{yy()}-\d{{4}}$"


# ------------------------------------------------------------------ seeds


def numbering_rule(db, company_id=None):
    """The rule the migration seeds: `OCN{yy}-`, 4 digits, yearly."""
    from app.models.numbering import DocumentNumberingRule

    row = DocumentNumberingRule(
        id=uid(), company_id=company_id, doc_type=KIND, enabled=True,
        prefix_template="OCN{yy}-", number_digits=4, next_value=1, start_value=1,
        reset_policy="yearly",
    )
    db.add(row)
    db.flush()
    return row


def change_type(db, name: str, risk: str, *, active: bool = True, position: int = 0):
    from app.models.project_so import OrderChangeType

    row = OrderChangeType(
        id=uid(), name=name, risk_level=risk, guide_text=f"When to use {name}: guide text.",
        is_active=active, position=position,
    )
    db.add(row)
    db.flush()
    return row


def change_types(db) -> SimpleNamespace:
    out = {
        name.lower(): change_type(db, name, risk, position=i)
        for i, (name, risk) in enumerate(SEEDED_TYPES.items())
    }
    out["retired"] = change_type(db, "ZZT Retired type", "Low", active=False, position=9)
    return SimpleNamespace(**out)


def product(db, code: str):
    from ._sample_request_seed import make_product

    return make_product(db, code=code, name=f"ZZT tile {code}")


def customer(db, company_id: str = SORENTO, name: str = "Customer A"):
    from ._sample_request_seed import make_customer

    row = make_customer(db, company_id)
    row.customer_name = name
    db.flush()
    return row


def project(db, owner: str, title: str, company_id: str = SORENTO):
    from ._sample_request_seed import make_project

    return make_project(db, company_id, owner, title=title)


# ------------------------------------------------------------------ payloads


def payload(o, *, http: bool = True, **over) -> dict:
    """A draft that passes every submit rule with the project switch OFF.

    `http=True` gives JSON-safe strings; `http=False` gives the Python values a router hands
    the service after pydantic parsing.
    """
    def d(s):
        return s if http else date.fromisoformat(s)

    def n(s):
        return s if http else Decimal(s)

    body = {
        "change_type_id": o.types.delay.id,
        "customer_id": o.customer.id,
        "customer_name": "Customer A",
        "customer_po_no": "XT04/3871 (R1)",
        "so_no_text": "SO-ZZT-0001",
        "project_id": None,
        "sales_in_charge_user_id": o.sales_admin,
        "cs_in_charge_user_id": o.cs,
        "description": "Site not ready, delay the first drop by a month.",
        "ocn_date": d("2026-11-12"),
        "lines": [
            {
                "product_id": o.p1.id,
                "qty_before": n("100"),
                "qty_after": n("100"),
                "date_before": d("2026-12-01"),
                "date_after": d("2027-01-05"),
                "delivered_qty": n("0"),
                "remark": "First drop",
            }
        ],
    }
    body.update(over)
    return body


def actor(o, user_id: str):
    """The service actor for `user_id`, built from the slugs RBAC really resolves for them."""
    from app.services.user_service import UserPermissionService

    slugs = UserPermissionService(o.db).get_user_permission_slugs(user_id)
    return svc().actor_from_slugs(user_id, slugs)


def rows_of(body) -> list:
    """List rows from either list envelope (`{data, pagination}` or `{items, total}`)."""
    if isinstance(body, dict):
        for key in ("data", "items"):
            if isinstance(body.get(key), list):
                return body[key]
    raise AssertionError(f"no list rows in {body!r}")


# ------------------------------------------------------------------ the world


@pytest.fixture
def ocn(world):  # noqa: F811  (`world` comes from _forms_chain_support)
    """The OCN world on top of the forms-chain world: users per role, the seeds, a project."""
    from app.models.base import set_company_scope
    from app.services import project_seed_service

    db = world.db
    set_company_scope(db, frozenset({SORENTO}))
    project_seed_service.run(db, company_id=SORENTO)
    settings_row(db)
    numbering_rule(db)

    o = SimpleNamespace(world=world, db=db, client=world.client)
    o.raiser = user(db, "OCN raiser")
    grant(db, o.raiser, VIEW, CREATE)
    o.sales_admin = user(db, "OCN sales admin")
    grant(db, o.sales_admin, VIEW, CREATE, EDIT)
    o.manager = user(db, "OCN manager")
    grant(db, o.manager, VIEW, APPROVE)
    o.cs = user(db, "OCN customer service")
    grant(db, o.cs, VIEW, EDIT)
    o.viewer = user(db, "OCN viewer")
    grant(db, o.viewer, VIEW)
    o.own = user(db, "OCN own-scope user")
    grant(db, o.own, VIEW_OWN, CREATE)
    o.stranger = user(db, "OCN stranger")
    grant(db, o.stranger, "procurement.purchase_requests.view")

    o.types = change_types(db)
    o.p1 = product(db, "ABC123-RL")
    o.p2 = product(db, "ABC124-RL")
    o.customer = customer(db)
    o.project = project(db, o.raiser, "ZZT Project Alpha")
    o.other_project = project(db, o.raiser, "ZZT Project Beta")
    db.commit()

    def as_(user_id):
        return world.as_user(user_id)

    o.as_ = as_
    return o


@pytest.fixture
def sla(ocn):
    """The OCN's three stages on a real agent, team sets and tiers (PR chain shape)."""
    chain = sla_chain(ocn.db, KIND, [dict(s) for s in STAGES])
    main, approval, cs = chain.stages
    # Every stage member can act on the stage they hold.
    grant(ocn.db, main.tier1, VIEW, EDIT)
    grant(ocn.db, main.tier2, VIEW, EDIT)
    grant(ocn.db, approval.tier1, VIEW, APPROVE)
    grant(ocn.db, approval.tier2, VIEW, APPROVE)
    grant(ocn.db, cs.tier1, VIEW, EDIT)
    grant(ocn.db, cs.tier2, VIEW, EDIT)
    ocn.db.commit()
    return SimpleNamespace(chain=chain, main=main, approval=approval, cs=cs)


# ------------------------------------------------------------------ HTTP helpers


def create(o, user_id=None, **over):
    res = o.as_(user_id or o.raiser).post(OCN, json=payload(o, **over))
    assert res.status_code in (200, 201), res.text
    return res.json()


def move(o, ocn_id: str, action: str, user_id: str, json=None, headers=None):
    return o.as_(user_id).post(f"{OCN}/{ocn_id}/{action}", json=json, headers=headers)


def get(o, ocn_id: str, user_id=None):
    return o.as_(user_id or o.viewer).get(f"{OCN}/{ocn_id}")


def ok(res):
    assert res.status_code == 200, res.text
    return res.json()


def submitted(o, **over) -> dict:
    d = create(o, **over)
    ok(move(o, d["id"], "submit", o.raiser))
    return d


def pending(o, **over) -> dict:
    d = submitted(o, **over)
    ok(move(o, d["id"], "send-for-approval", o.sales_admin))
    return d


def approved(o, **over) -> dict:
    d = pending(o, **over)
    ok(move(o, d["id"], "approval-decision", o.manager, json={"action": "approved", "comments": None}))
    return d


def load(o, ocn_id: str):
    from app.models.project_so import OrderChangeNotice

    o.db.expire_all()
    return o.db.query(OrderChangeNotice).filter(OrderChangeNotice.id == ocn_id).one()
