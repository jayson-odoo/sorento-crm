"""Shared world for the SPARE-PART-ORDER-REQUEST red tests (Phase 2, test-first).

Contract: documentation/plans/purchasing/spare-part-order-request-12nov-acceptance-criteria.md
(UAC) + the "Build contract" section of PLAN-spare-part-order-request-12nov.md.

Test support only, no implementation. Postgres only (tests/_pg_fixture.py `blank_session`);
every row is seeded here, nothing borrowed (CI's database is empty).

What is real and what is stubbed:

* Real: every route, RBAC (users hold slugs through real roles, `admin` is a real role
  slug), the Form SLA orchestrator (stages, teams, tiers via `_forms_chain_support.sla_chain`),
  the OI number listener, audit rows.
* Stubbed: `NotificationService.create_with_channel_preferences` (recorded in `w.sent` as
  `(user_id, type, source_entity_id)`; it commits, and the purchasing notice is fired from an
  after_commit hook on a fresh session), `queue_service.enqueue_job` (recorded), Respond.io
  sends, and storage (the `so_line_attachments` backend, as `test_so_line_attachments.py`).

NAMED ASSUMPTIONS the coder works to (the brief left them open):

1. Service actor = the acting user's id (a str). `create` returns the `OrderInquiry`.
2. Service `data` = a plain dict, the JSON body as decoded (dates "YYYY-MM-DD", numbers as
   strings), the same dict the route would pass on.
3. Row attachments reuse the `so_line_attachment` attachment TYPE row (one upload path,
   UAC R4 "stored through the same attachment service"); the storage stub patches
   `app.services.so_line_attachments.get_backend` / `default_provider`.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from ._forms_chain_support import SORENTO, sla_chain, uid, unique_code, user
from ._pg_fixture import blank_session

KIND = "spare_part_request"
BASE = "/api/v1/project-sales"
SPR = f"{BASE}/spare-part-requests"
HEADERS = f"{BASE}/order-inquiry-headers"
WORKLIST = f"{BASE}/order-inquiries"
ROW_ATT = f"{BASE}/order-inquiry-rows"

CREATE = "procurement.spare_part_requests.create"
VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
ACTION = "projects.order_inquiry.action"
ACKNOWLEDGE = "projects.order_inquiries.acknowledge"

OI_RAISED_NOTICE = "project_order_inquiry_raised"

# A hardcoded, valid 1x1 PNG (the one test_so_line_attachments.py uses).
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ------------------------------------------------------------------ the module under test


def svc():
    """The service module, imported per call so each test fails on its own (red =
    ModuleNotFoundError until `app/services/spare_part_request_service.py` exists)."""
    from app.services import spare_part_request_service

    return spare_part_request_service


# ------------------------------------------------------------------ seeding


def role_grant(db, user_id: str, *slugs: str, role_slug: str | None = None) -> None:
    """A real role carrying `slugs` (created if missing), assigned to `user_id`."""
    from app.models.user import UserPermission, UserRole, UserRoleAssignment, UserRolePermission

    slug = role_slug or f"zzt-spr-{uid()[:10]}"
    role = db.query(UserRole).filter(UserRole.slug == slug).first()
    if role is None:
        role = UserRole(id=uid(), slug=slug, name=f"ZZT {slug}")
        db.add(role)
        db.flush()
    for perm_slug in slugs:
        perm = db.query(UserPermission).filter(UserPermission.slug == perm_slug).first()
        if perm is None:
            perm = UserPermission(id=uid(), slug=perm_slug, name=perm_slug)
            db.add(perm)
            db.flush()
        linked = (
            db.query(UserRolePermission)
            .filter(UserRolePermission.role_id == role.id, UserRolePermission.permission_id == perm.id)
            .first()
        )
        if linked is None:  # a migrated DB's own `admin` role may already carry it
            db.add(UserRolePermission(id=uid(), role_id=role.id, permission_id=perm.id))
            db.flush()
    db.add(UserRoleAssignment(id=uid(), user_id=user_id, role_id=role.id))
    db.flush()


def make_product(db, name: str):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    uom = UnitOfMeasure(id=uid(), uom_code=unique_code("U")[:20], uom_name="Piece")
    category = ProductCategory(id=uid(), category_code=unique_code("CAT"), category_name="ZZT spare cat")
    brand = Brand(id=uid(), brand_code=unique_code("BR"), brand_name="ZZT spare brand")
    db.add_all([uom, category, brand])
    db.flush()
    row = Product(
        id=uid(),
        product_code=unique_code("SP", alpha=True).upper(),
        product_name=f"ZZT {name}",
        description=f"ZZT {name}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=100,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def make_warehouse(db, code: str):
    from app.models.inventory import Warehouse

    row = Warehouse(
        id=uid(), warehouse_code=code, warehouse_name=code, location="ZZT",
        is_active=True, fulfilment_planning=True,
    )
    db.add(row)
    db.flush()
    return row


def seed_people_and_catalogue(db) -> SimpleNamespace:
    """Users, products and warehouses every spare-part test shares (no SLA stages)."""
    requester = user(db, "spr requester")
    role_grant(db, requester, CREATE)
    outsider = user(db, "spr outsider")  # holds the same slugs, sits on no stage team
    role_grant(db, outsider, VIEW, CREATE)
    admin = user(db, "spr admin")
    role_grant(db, admin, VIEW, CREATE, EDIT, ACTION, ACKNOWLEDGE, role_slug="admin")
    buyer = user(db, "spr purchasing")
    role_grant(db, buyer, VIEW, EDIT, ACTION, ACKNOWLEDGE, role_slug=f"purchasing-zzt-{uid()[:8]}")
    product_a = make_product(db, "pump seal 40mm")
    product_b = make_product(db, "door hinge set")
    loc_a = make_warehouse(db, unique_code("WA", alpha=True)[:20].upper())
    loc_b = make_warehouse(db, unique_code("WB", alpha=True)[:20].upper())
    return SimpleNamespace(
        requester=requester, outsider=outsider, admin=admin, buyer=buyer,
        product_a=product_a, product_b=product_b, loc_a=loc_a, loc_b=loc_b,
    )


ONE_STAGE = [
    {"start_event": "submitted", "resolve_event": "approved,rejected", "advance_on_event": "approved"},
]
#: Two levels, chained the NPA / SI way (`next_config_id` + `advance_on_event`); both resolve
#: on the same 'approved' / 'rejected' the service emits for every approval (contract).
#: Stage 2 starts only through the chain: its own start_event is never emitted.
TWO_STAGES = [
    {"start_event": "submitted", "resolve_event": "approved,rejected", "advance_on_event": "approved"},
    {"start_event": "spare_part_level_two", "resolve_event": "approved,rejected"},
]


def add_stages(w, stages) -> SimpleNamespace:
    """Configure the approval chain; every stage member holds VIEW + CREATE. The requester
    is ALSO a member of stage 1 (its tier-2 team), for A2 "never the requester"."""
    from app.models.access import AgentTeam, TeamMember

    chain = sla_chain(w.db, KIND, [dict(s) for s in stages])
    for stage in chain.stages:
        role_grant(w.db, stage.tier1, VIEW, CREATE)
        role_grant(w.db, stage.tier2, VIEW, CREATE)
    first = chain.stages[0]
    tier2_team = (
        w.db.query(AgentTeam)
        .filter(AgentTeam.code == first.team_set, AgentTeam.tier == 2)
        .one()
    )
    w.db.add(TeamMember(id=uid(), team_id=tier2_team.team_id, user_id=w.requester, sort_order=1))
    w.db.commit()
    w.chain = chain
    w.stage1 = chain.stages[0]
    w.stage2 = chain.stages[1] if len(chain.stages) > 1 else None
    return chain


# ------------------------------------------------------------------ request bodies


def line(product, location, qty="10", unit_price="25.00") -> dict:
    return {
        "product_id": str(product.id),
        "stock_location": location.warehouse_code if location is not None else None,
        "qty": qty,
        "unit_price": unit_price,
    }


def body(w, **over) -> dict:
    data: dict[str, Any] = {
        "currency": "MYR",
        "needed_by": "2026-12-15",
        "default_location": w.loc_a.warehouse_code,
        "reason": "Spare parts for the service van",
        "lines": [
            line(w.product_a, w.loc_a, qty="10", unit_price="25.00"),
            line(w.product_b, w.loc_b, qty="4", unit_price="12.50"),
        ],
    }
    data.update(over)
    return data


# ------------------------------------------------------------------ service-level flows


def as_inquiry(db, result):
    from app.models.project_so import OrderInquiry

    inquiry_id = result.id if hasattr(result, "id") else result["id"]
    db.expire_all()
    return db.query(OrderInquiry).filter(OrderInquiry.id == str(inquiry_id)).one()


def reload(db, inquiry):
    return as_inquiry(db, inquiry)


def rows_of(db, inquiry) -> list:
    from app.models.project_so import OrderInquiryRow

    db.expire_all()
    return (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.order_inquiry_id == str(inquiry.id))
        .order_by(OrderInquiryRow.qty.desc(), OrderInquiryRow.id)
        .all()
    )


def row_for(db, inquiry, product):
    found = [r for r in rows_of(db, inquiry) if str(r.product_id) == str(product.id)]
    assert len(found) == 1, f"expected one row for {product.product_code}, found {len(found)}"
    return found[0]


def create(w, **over):
    result = svc().create(w.db, body(w, **over), w.requester)
    w.db.commit()
    return as_inquiry(w.db, result)


def submitted(w, **over):
    inquiry = create(w, **over)
    svc().submit(w.db, inquiry, w.requester)
    w.db.commit()
    return reload(w.db, inquiry)


def approve(w, inquiry, actor, note=None):
    svc().approve(w.db, inquiry, actor, note=note)
    w.db.commit()
    return reload(w.db, inquiry)


def raised(w, **over):
    """Submitted and approved by stage 1's tier-1 member (one-stage chain = final)."""
    inquiry = submitted(w, **over)
    return approve(w, inquiry, w.stage1.tier1)


def app_error(excinfo) -> int:
    return excinfo.value.status_code


def dec(value) -> Decimal:
    return Decimal(str(value))


# ------------------------------------------------------------------ the world


class World(SimpleNamespace):
    def as_user(self, user_id: str):
        self.state["user"] = user_id
        return self.client


@pytest.fixture
def sent(monkeypatch):
    """Every notification created: (user_id, type, source_entity_id)."""
    from app.services.notification_service import NotificationService

    calls: list = []

    def capture(self, *args, **kw):
        calls.append((kw.get("user_id"), kw.get("type"), kw.get("source_entity_id")))

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", capture)
    return calls


def stub_storage(monkeypatch) -> None:
    from app.services import so_line_attachments
    from app.services.storage_router import clear_signed_url_cache

    clear_signed_url_cache()
    backend = type(
        "StubBackend",
        (),
        {
            "upload_file": staticmethod(lambda **kw: ("stub/r2/key", "")),
            "download_file": staticmethod(lambda key: TINY_PNG),
            "get_signed_url": staticmethod(lambda key, expires_in=3600: f"https://signed.test/{key}"),
            "get_cloudfront_base_url": staticmethod(lambda key: f"https://cdn.test/{key}"),
            "get_cdn_base_url": staticmethod(lambda key: f"https://cdn.test/{key}"),
        },
    )()
    monkeypatch.setattr("app.services.storage_router.default_provider", lambda: "r2")
    monkeypatch.setattr("app.services.storage_router.get_backend", lambda p: backend)
    monkeypatch.setattr(so_line_attachments, "default_provider", lambda: "r2")
    monkeypatch.setattr(so_line_attachments, "get_backend", lambda p: backend)


@pytest.fixture
def world(monkeypatch, sent):
    from fastapi.testclient import TestClient

    from app.main import app  # noqa: F401  first app import (circular import guard)
    from app.config import settings
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.models.base import set_company_scope
    from app.services import project_seed_service, queue_service, respond_messaging_service
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    jobs: list = []
    monkeypatch.setattr(
        queue_service,
        "enqueue_job",
        lambda fn, *a, **kw: jobs.append(fn) or SimpleNamespace(id=f"zzt-job-{len(jobs)}"),
    )
    monkeypatch.setattr(
        respond_messaging_service,
        "send_text_or_template",
        lambda *a, **kw: {"sent_as": "text", "window_state": "open", "response": {}, "request_payload": {}},
    )
    monkeypatch.setattr(settings, "idempotency_enabled", False, raising=False)
    register_order_inquiry_post_commit_dispatch()

    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        project_seed_service.run(db, company_id=SORENTO)
        seeded = seed_people_and_catalogue(db)
        db.commit()
        state: dict[str, Any] = {"user": seeded.requester}

        def actor():
            return {"id": state["user"], "email": f"{state['user']}@zzt.test", "role": "staff"}

        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = actor
        app.dependency_overrides[get_current_user_or_api_key] = actor
        app.dependency_overrides[apply_company_scope] = lambda: set_company_scope(
            db, frozenset({SORENTO})
        )
        try:
            client = TestClient(app)
            yield World(
                db=db, client=client, state=state, sent=sent, jobs=jobs,
                company_id=SORENTO, chain=None, stage1=None, stage2=None,
                **vars(seeded),
            )
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def staged(world):
    """The world with ONE approval stage configured for spare_part_request."""
    add_stages(world, ONE_STAGE)
    return world


@pytest.fixture
def two_staged(world):
    add_stages(world, TWO_STAGES)
    return world
