"""AGENTIC-UNIFY PR 1: the AI panel reads as the staff member (backend half).

UAC: documentation/plans/chatbot/agentic-unify-pr1-acceptance-criteria.md, AC-5 to AC-20 and
AC-22 to AC-25. The shared key (settings.external_api_key, resolved through integration_api_keys
to the act-as user) plus `X-Staff-User: <user id>` makes a READ run as that staff member.

Everything here is a real dependency chain: real `get_current_user_or_api_key`, real
`apply_company_scope` router dependency (attached the way app/main.py attaches it), real RBAC
rows, real session tokens. Probe routes are mounted on a throw-away FastAPI app only where the
test needs to see `current_user` or the stamped scope itself; every parity and permission-gate
test goes through the real app and real routes.

Postgres only (`blank_session`); every company, user, role, permission and row is seeded here.

Regressions that must PASS today (and fail if broken): AC-8, AC-13 (session / plain-key halves),
AC-14, AC-25, and the "header ignored / unchanged" halves of AC-7 and AC-9.
"""
from __future__ import annotations

import importlib.util
import re
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from sqlalchemy import text

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.audit_context import get_actor
from app.config import settings
from app.database import get_db
from app.dependencies import (
    get_current_user_or_api_key,
    require_any_permission_with_api_key,
    require_permission_with_api_key,
)
from app.models.base import UNSET, get_company_scope
from app.models.company import Company, UserCompany
from app.models.integration import Integration
from app.models.user import (
    User,
    UserPermission,
    UserRole,
    UserRolePermission,
    UserRoleAssignment,
)
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.integration_key_service import IntegrationKeyService
from app.services.user_session_service import mint_session
from tests._mc_lookup_seed import order, product, stock, warehouse
from tests._pg_fixture import blank_session, unique_code

STAFF_HEADER = "X-Staff-User"
INVALID_CODE = "staff_identity_invalid"
SORENTO = DEFAULT_COMPANY_ID

ORDERS = "/api/v1/order-management/orders/"
STOCK_BALANCE = "/api/v1/inventory/stock/balance"
ORDERS_VIEW = "order_management.orders.view"
STOCK_VIEW = "inventory.stock.view"


def uid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Seeding                                                                     #
# --------------------------------------------------------------------------- #
def mk_company(db, name: str) -> str:
    row = Company(id=uid(), name=f"ZZT {name}", code=unique_code("CO")[:20])
    db.add(row)
    db.flush()
    return row.id


def _perm(db, slug: str) -> UserPermission:
    row = db.query(UserPermission).filter(UserPermission.slug == slug).first()
    if row is None:
        row = UserPermission(slug=slug, name=slug)
        db.add(row)
        db.flush()
    return row


def _role(db, slug: str) -> UserRole:
    row = db.query(UserRole).filter(UserRole.slug == slug).first()
    if row is None:
        row = UserRole(slug=slug, name=slug)
        db.add(row)
        db.flush()
    return row


def mk_user(
    db,
    name: str,
    *,
    perms=(),
    roles=(),
    status="ACTIVE",
    trashed=False,
    companies=(),
    last_active=None,
    contact_id=None,
    integration=False,
) -> str:
    user = User(
        id=uid(),
        email=f"{uid()}@zzt.test",
        name=f"ZZT {name}",
        status=status,
        is_trashed=trashed,
        last_active_company_id=last_active,
        respond_contact_id=contact_id,
        is_integration=integration,
    )
    db.add(user)
    db.flush()
    if perms:
        role = UserRole(slug=f"zzt-role-{uid()[:8]}", name=f"zzt role {uid()[:8]}")
        db.add(role)
        db.flush()
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
        for slug in perms:
            db.add(UserRolePermission(role_id=role.id, permission_id=_perm(db, slug).id))
    for slug in roles:
        db.add(UserRoleAssignment(user_id=user.id, role_id=_role(db, slug).id))
    for company_id in companies:
        db.add(UserCompany(user_id=user.id, company_id=company_id))
    db.flush()
    return user.id


def grant(db, user_id: str, perms) -> None:
    role = UserRole(slug=f"zzt-grant-{uid()[:8]}", name=f"zzt grant {uid()[:8]}")
    db.add(role)
    db.flush()
    db.add(UserRoleAssignment(user_id=user_id, role_id=role.id))
    for slug in perms:
        db.add(UserRolePermission(role_id=role.id, permission_id=_perm(db, slug).id))
    db.flush()


def mk_key(db, actas_id: str, type_: str = "mcp") -> tuple[str, Integration]:
    integration = Integration(name=unique_code("int"), type=type_, act_as_user_id=actas_id)
    db.add(integration)
    db.flush()
    return IntegrationKeyService(db).issue_key(integration), integration


def mk_contact_in(db, company_ids) -> tuple[str, str]:
    """A Respond contact that belongs to exactly `company_ids`. Returns (respond_io_id, space_id)."""
    suffix = uid()[:8]
    ws_id, space_id, contact_pk = uid(), f"zzt-space-{suffix}", uid()
    rid = f"zzt-rid-{suffix}"
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, name, api_key_ciphertext, created_at, updated_at) "
            "VALUES (:id, :sid, :name, :ck, now(), now())"
        ),
        {"id": ws_id, "sid": space_id, "name": f"zzt ws {suffix}", "ck": "zzt-cipher"},
    )
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, phone_number, respond_io_id, workspace_id, created_at, updated_at) "
            "VALUES (:id, :phone, :rid, :ws, now(), now())"
        ),
        {"id": contact_pk, "phone": f"+60{suffix}", "rid": rid, "ws": ws_id},
    )
    for company_id in company_ids:
        db.execute(
            text(
                "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id, created_at) "
                "VALUES (:id, :cid, :company, now())"
            ),
            {"id": uid(), "cid": contact_pk, "company": company_id},
        )
    db.flush()
    return rid, space_id


@pytest.fixture()
def env(monkeypatch):
    """Two companies (Sorento = A, a second = B), a superadmin act-as user behind the shared key."""
    register_company_scope_listeners()
    with blank_session() as db:
        e = SimpleNamespace(db=db, co_a=SORENTO, co_b=mk_company(db, "B"))
        e.actas = mk_user(db, "actas", roles=("superadmin",), integration=True)
        e.key, e.integration = mk_key(db, e.actas)
        monkeypatch.setattr(settings, "external_api_key", e.key)

        def use_actas(perms=(), roles=()):
            """Swap the shared key's act-as user for one holding exactly `perms` / `roles`."""
            e.actas = mk_user(db, "actas2", perms=perms, roles=roles, integration=True)
            e.key, e.integration = mk_key(db, e.actas)
            monkeypatch.setattr(settings, "external_api_key", e.key)
            return e

        e.use_actas = use_actas
        e.session = lambda user_id: {"Authorization": f"Bearer {mint_session(db, user_id).token}"}
        e.ident = lambda staff_id, key=None: {"X-API-Key": key or e.key, STAFF_HEADER: str(staff_id)}
        e.plain = lambda: {"X-API-Key": e.key}
        app.dependency_overrides[get_db] = lambda: db
        e.client = TestClient(app, raise_server_exceptions=False)
        try:
            yield e
        finally:
            app.dependency_overrides.pop(get_db, None)


# --------------------------------------------------------------------------- #
# Probe app: the same router-level dependencies as app/main.py                #
# --------------------------------------------------------------------------- #
def _scope_repr(scope):
    if scope is None:
        return "all"
    if scope is UNSET:
        return "unset"
    return sorted(scope)


def _probe_client(db) -> TestClient:
    from app.api.v1.external.permissions import require_external_permission
    from app.services.analytics_connector.access import connector_call_gate
    from app.services.company_scope_resolver import apply_company_scope

    r = APIRouter()

    def snapshot(request: Request, user: dict, database) -> dict:
        actor = get_actor(database)
        return {
            "user": jsonable_encoder(user),
            "scope": _scope_repr(get_company_scope(database)),
            "actor": None
            if actor is None
            else {
                "actor_type": actor.actor_type,
                "user_id": actor.user_id,
                "integration_id": actor.integration_id,
            },
        }

    @r.api_route("/zzt/whoami", methods=["GET", "HEAD", "POST", "DELETE"])
    def whoami(request: Request, user=Depends(get_current_user_or_api_key), database=Depends(get_db)):
        return snapshot(request, user, database)

    # the two catalog `read_only` POST paths of the CRM (crm_lookup_resolve, crm_portal_link_get)
    @r.post("/lookup/resolve")
    def lookup_resolve(request: Request, user=Depends(get_current_user_or_api_key), database=Depends(get_db)):
        return snapshot(request, user, database)

    @r.post("/external/portal-tokens/")
    def portal_tokens(request: Request, user=Depends(get_current_user_or_api_key), database=Depends(get_db)):
        return snapshot(request, user, database)

    # an ordinary write path: not a catalog read
    @r.post("/zzt/write")
    def write(request: Request, user=Depends(get_current_user_or_api_key), database=Depends(get_db)):
        return snapshot(request, user, database)

    @r.get("/zzt/perm")
    def perm(user=Depends(require_permission_with_api_key("zzt.thing.view"))):
        return {"ok": True}

    @r.get("/zzt/any")
    def any_perm(user=Depends(require_any_permission_with_api_key(["zzt.a.view", "zzt.b.view"]))):
        return {"ok": True}

    @r.get("/zzt/ext")
    def ext(user=Depends(require_external_permission("zzt.thing.view"))):
        return {"ok": True}

    @r.get("/zzt/ext-integration")
    def ext_integration(user=Depends(require_external_permission("integration.zzt_thing"))):
        return {"ok": True}

    from app.api.v1.external.permissions import require_external_permission_for_path
    from app.modules.runtime.guards import require_module_enabled_with_api_key

    @r.get("/zzt/offlist")
    def offlist(request: Request, user=Depends(get_current_user_or_api_key), database=Depends(get_db)):
        return snapshot(request, user, database)

    @r.get("/zzt/ext-off/{entity}")
    def ext_off(
        entity: str,
        user=Depends(require_external_permission_for_path({"thing": "zzt.thing.view"}, param="entity")),
    ):
        return {"ok": True}

    @r.get("/zzt/permmod")
    def permmod(user=Depends(require_permission_with_api_key("order_management.orders.view"))):
        return {"ok": True}

    @r.get("/zzt/modguard", dependencies=[Depends(require_module_enabled_with_api_key("order"))])
    def modguard(user=Depends(get_current_user_or_api_key)):
        return {"ok": True}

    @r.get("/zzt/ext-path/{entity}")
    def ext_path(
        entity: str,
        user=Depends(
            require_external_permission_for_path(
                {"thing": "zzt.thing.view", "int": "integration.zzt_thing"}, param="entity"
            )
        ),
    ):
        return {"ok": True}

    probe = FastAPI()
    probe.include_router(
        r,
        prefix="/api/v1",
        dependencies=[Depends(connector_call_gate, scope="function"), Depends(apply_company_scope)],
    )
    probe.dependency_overrides[get_db] = lambda: db
    return TestClient(probe, raise_server_exceptions=False)


PROBE_READS = [
    ("GET", "/api/v1/zzt/whoami"),
    ("HEAD", "/api/v1/zzt/whoami"),
    ("GET", "/api/v1/zzt/perm"),
    ("GET", "/api/v1/zzt/any"),
    ("GET", "/api/v1/zzt/ext"),
    ("GET", "/api/v1/zzt/ext-integration"),
    ("GET", "/api/v1/zzt/ext-path/{}"),
    ("GET", "/api/v1/zzt/permmod"),
    ("GET", "/api/v1/zzt/modguard"),
]
#: `/api/v1/zzt/offlist` is deliberately never added: a read route off the list.


def _route_entry(sample, method, path):
    """One STAFF_READ_ROUTES entry in whatever shape the backend constant uses."""
    if isinstance(sample, tuple):
        return (method, path)
    return f"{method} {path}"


def _patch_staff_read_routes(monkeypatch, entries):
    from app.services import company_scope_resolver as resolver

    current = getattr(resolver, "STAFF_READ_ROUTES", None)
    if current is None:  # before the constant exists the probes are plain GETs
        return
    sample = next(iter(current), None)
    extra = {_route_entry(sample, m, p) for m, p in entries}
    monkeypatch.setattr(resolver, "STAFF_READ_ROUTES", frozenset(set(current) | extra))


@pytest.fixture()
def probe(env, monkeypatch):
    _patch_staff_read_routes(monkeypatch, PROBE_READS)
    return _probe_client(env.db)


def _text(resp) -> str:
    return resp.text


# =========================================================================== #
# AC-5  identity on GET, HEAD, and catalog read-only POST                     #
# =========================================================================== #
def _assert_identity(resp, env, staff):
    assert resp.status_code == 200, resp.text
    user = resp.json()["user"]
    assert user["id"] == staff, "AC-5: current_user['id'] must be the staff member"
    assert user["key_user_id"] == env.actas, "AC-5: current_user['key_user_id'] must be the act-as user"
    assert user["integration_id"] == env.integration.id
    assert user["integration_name"] == env.integration.name
    assert user["integration_type"] == env.integration.type
    assert user["auth_method"] == "integration_api_key"


def test_ac5_get_identity(env, probe):
    staff = mk_user(env.db, "staff")
    _assert_identity(probe.get("/api/v1/zzt/whoami", headers=env.ident(staff)), env, staff)


def test_ac5_head_identity_is_not_refused(env, probe):
    staff = mk_user(env.db, "staff")
    assert probe.head("/api/v1/zzt/whoami", headers=env.ident(staff)).status_code == 200
    # HEAD has no body to read, so pin the identity switch through the refusal path: the same
    # HEAD with an unknown id must be refused, proving the header is read on HEAD.
    bad = probe.head("/api/v1/zzt/whoami", headers=env.ident(uid()))
    assert bad.status_code == 403, "AC-5/AC-6: HEAD must honour the identity header"


@pytest.mark.parametrize("path", ["/api/v1/lookup/resolve", "/api/v1/external/portal-tokens/"])
def test_ac5_post_to_catalog_read_only_path_gets_identity(env, probe, path):
    staff = mk_user(env.db, "staff")
    _assert_identity(probe.post(path, headers=env.ident(staff)), env, staff)


# =========================================================================== #
# AC-6  fails closed                                                          #
# =========================================================================== #
@pytest.mark.parametrize("kind", ["malformed", "unknown", "inactive", "trashed", "empty"])
def test_ac6_bad_identity_is_403_never_act_as(env, probe, kind):
    if kind == "malformed":
        header = "not-a-uuid"
    elif kind == "unknown":
        header = uid()
    elif kind == "inactive":
        header = mk_user(env.db, "inactive", status="INACTIVE")
    elif kind == "trashed":
        header = mk_user(env.db, "trashed", trashed=True)
    else:
        header = ""
    resp = probe.get("/api/v1/zzt/whoami", headers={"X-API-Key": env.key, STAFF_HEADER: header})
    assert resp.status_code == 403, f"AC-6 {kind}: {resp.status_code} {resp.text}"
    assert INVALID_CODE in resp.text


def test_ac6_identity_header_with_a_non_shared_key_is_403(env, probe):
    """A valid integration key that is NOT the shared EXTERNAL_API_KEY may not claim an identity."""
    staff = mk_user(env.db, "staff")
    other_actas = mk_user(env.db, "other-actas", roles=("superadmin",), integration=True)
    other_key, _ = mk_key(env.db, other_actas)
    resp = probe.get("/api/v1/zzt/whoami", headers={"X-API-Key": other_key, STAFF_HEADER: staff})
    assert resp.status_code == 403, resp.text
    assert INVALID_CODE in resp.text


# =========================================================================== #
# AC-7  any other write ignores the header                                    #
# =========================================================================== #
@pytest.mark.parametrize("method,path", [("post", "/api/v1/zzt/write"), ("delete", "/api/v1/zzt/whoami")])
def test_ac7_other_writes_ignore_the_header(env, probe, method, path):
    staff = mk_user(env.db, "staff")
    resp = getattr(probe, method)(path, headers=env.ident(staff))
    assert resp.status_code == 200, resp.text
    user = resp.json()["user"]
    assert user["id"] == env.actas, "AC-7: a write stays attributed to act-as"
    assert resp.json()["scope"] == "all", "AC-7: a write keeps today's company scope"


def test_ac7_other_write_with_an_unknown_id_is_not_refused(env, probe):
    """Ignored means ignored: no identity validation on a write, so no new 403 either."""
    resp = probe.post("/api/v1/zzt/write", headers=env.ident(uid()))
    assert resp.status_code == 200, resp.text


# =========================================================================== #
# AC-8  no header, nothing changes (regression, passes today)                 #
# =========================================================================== #
def test_ac8_key_without_contact_reads_all_companies(env, probe):
    resp = probe.get("/api/v1/zzt/whoami", headers=env.plain())
    assert resp.status_code == 200
    assert resp.json()["scope"] == "all"
    assert resp.json()["user"]["id"] == env.actas


def test_ac8_key_with_contact_pair_reads_the_contacts_companies(env, probe):
    rid, space = mk_contact_in(env.db, [env.co_b])
    resp = probe.get(f"/api/v1/zzt/whoami?contact_id={rid}&space_id={space}", headers=env.plain())
    assert resp.json()["scope"] == [env.co_b]


def test_ac8_session_is_untouched(env, probe):
    staff = mk_user(env.db, "staff", companies=[env.co_a, env.co_b], last_active=env.co_b)
    resp = probe.get("/api/v1/zzt/whoami", headers=env.session(staff))
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["id"] == staff
    assert resp.json()["scope"] == [env.co_b]
    assert "key_user_id" not in resp.json()["user"]


# =========================================================================== #
# AC-9  the audit actor stays the integration                                 #
# =========================================================================== #
def test_ac9_audit_actor_on_an_identity_read_is_the_integration(env, probe):
    staff = mk_user(env.db, "staff")
    actor = probe.get("/api/v1/zzt/whoami", headers=env.ident(staff)).json()["actor"]
    assert actor == {
        "actor_type": "integration",
        "user_id": env.actas,
        "integration_id": env.integration.id,
    }, "AC-9: attribution stays the integration and act-as, not the staff member"


# =========================================================================== #
# AC-10 / AC-11 / AC-12  permission: staff AND act-as                         #
# =========================================================================== #
def _perm_status(env, probe, path, staff_perms, actas_perms, *, staff_roles=(), actas_roles=("superadmin",)):
    env.use_actas(perms=actas_perms, roles=actas_roles)
    staff = mk_user(env.db, "staff", perms=staff_perms, roles=staff_roles)
    return probe.get(path, headers=env.ident(staff)).status_code


def test_ac10_both_hold_passes(env, probe):
    assert _perm_status(env, probe, "/api/v1/zzt/perm", ["zzt.thing.view"], ["zzt.thing.view"], actas_roles=()) == 200


def test_ac10_staff_lacking_is_403_though_actas_holds(env, probe):
    assert _perm_status(env, probe, "/api/v1/zzt/perm", [], ["zzt.thing.view"], actas_roles=()) == 403
    assert _perm_status(env, probe, "/api/v1/zzt/perm", [], [], actas_roles=("superadmin",)) == 403


def test_ac10_actas_lacking_is_403_though_staff_holds(env, probe):
    assert _perm_status(env, probe, "/api/v1/zzt/perm", ["zzt.thing.view"], [], actas_roles=()) == 403


def test_ac10_plain_key_and_session_are_as_today(env, probe):
    env.use_actas(perms=["zzt.thing.view"])
    assert probe.get("/api/v1/zzt/perm", headers=env.plain()).status_code == 200
    holder = mk_user(env.db, "holder", perms=["zzt.thing.view"])
    nobody = mk_user(env.db, "nobody")
    assert probe.get("/api/v1/zzt/perm", headers=env.session(holder)).status_code == 200
    assert probe.get("/api/v1/zzt/perm", headers=env.session(nobody)).status_code == 403


def test_ac11_any_staff_one_slug_and_actas_one_slug_passes_even_if_not_the_same(env, probe):
    """New rule: staff holds at least one of the list AND act-as holds at least one."""
    path = "/api/v1/zzt/any"
    assert _perm_status(env, probe, path, ["zzt.b.view"], ["zzt.a.view"], actas_roles=()) == 200, (
        "AC-11: the two users need not share the slug"
    )
    assert _perm_status(env, probe, path, ["zzt.a.view"], ["zzt.a.view"], actas_roles=()) == 200


def test_ac11_any_actas_holding_none_is_403_though_staff_holds_one(env, probe):
    assert _perm_status(env, probe, "/api/v1/zzt/any", ["zzt.a.view"], [], actas_roles=()) == 403


def test_ac11_staff_lacking_any_slug_is_403_though_actas_holds(env, probe):
    assert _perm_status(env, probe, "/api/v1/zzt/any", [], ["zzt.a.view", "zzt.b.view"], actas_roles=()) == 403


def test_ac11_superadmin_staff_does_not_pass_an_actas_that_lacks_the_slugs(env, probe):
    assert (
        _perm_status(env, probe, "/api/v1/zzt/any", [], [], staff_roles=("superadmin",), actas_roles=()) == 403
    ), "AC-11: the superadmin shortcut applies per user, never lifts act-as"


def test_ac11_superadmin_staff_with_a_capable_actas_passes(env, probe):
    assert (
        _perm_status(env, probe, "/api/v1/zzt/any", [], ["zzt.a.view"], staff_roles=("superadmin",), actas_roles=())
        == 200
    )


def test_ac12_external_real_slug_needs_both_users(env, probe):
    path = "/api/v1/zzt/ext"
    assert _perm_status(env, probe, path, ["zzt.thing.view"], ["zzt.thing.view"], actas_roles=()) == 200
    assert _perm_status(env, probe, path, [], ["zzt.thing.view"], actas_roles=()) == 403
    assert _perm_status(env, probe, path, ["zzt.thing.view"], [], actas_roles=()) == 403


def test_ac12_external_integration_slug_is_checked_on_actas_only(env, probe):
    path = "/api/v1/zzt/ext-integration"
    assert _perm_status(env, probe, path, [], ["integration.zzt_thing"], actas_roles=()) == 200
    assert _perm_status(env, probe, path, [], [], actas_roles=()) == 403


# =========================================================================== #
# AC-13  the gated KEY routes (regressions for session and plain key)         #
# =========================================================================== #
GATED = [
    ("crm_inventory_stock_balance_list", "/api/v1/inventory/stock/balance", ["inventory.stock.view"]),
    ("crm_incoming_stock_by_product", "/api/v1/incoming-stock/by-product", ["procurement.packing_lists.view"]),
    ("crm_incoming_stock_shipments", "/api/v1/incoming-stock/shipments", ["procurement.packing_lists.view"]),
    ("crm_incoming_stock_list", "/api/v1/incoming-stock/list", ["procurement.packing_lists.view"]),
    ("crm_procurement_po_placed_list", "/api/v1/procurement/purchase-orders/placed", ["scm.purchase_orders.view"]),
    ("crm_procurement_po_last_cost_list", "/api/v1/procurement/purchase-orders/last-cost", ["scm.purchase_orders.view"]),
    (
        "crm_procurement_spo_allocations_last_receipt_list",
        "/api/v1/procurement/spo-allocations/last-receipt",
        ["procurement.spo_allocations.view"],
    ),
    ("crm_procurement_grn_summary", "/api/v1/procurement/grn/summary", ["procurement.grn.view"]),
    (
        "crm_master_product_attachments_list",
        "/api/v1/master-data/product-attachments",
        ["master_data.product_attachments.view"],
    ),
    (
        "crm_purchase_request_by_number",
        "/api/v1/procurement/purchase-requests/by-number/ZZT-NONE",
        [
            "procurement.purchase_requests.view",
            "procurement.purchase_requests.view_own",
            "procurement.sponsorship_forms.view",
            "procurement.sponsorship_forms.view_own",
        ],
    ),
]
GATED_IDS = [g[0] for g in GATED]
#: What each gated route answers a caller who passes the gate, on an empty database and with no
#: parameters (measured): 200 for a list, 422 for a route with a required parameter, 404 for an
#: unknown number. Anything else (a 500 above all) is a defect, not "passed the gate".
EMPTY_DB_STATUS = {"crm_procurement_grn_summary": 422, "crm_purchase_request_by_number": 404}


@pytest.mark.parametrize("tool,path,slugs", GATED, ids=GATED_IDS)
def test_ac13_identity_staff_holding_nothing_is_403(env, tool, path, slugs):
    staff = mk_user(env.db, "nothing")
    resp = env.client.get(path, headers=env.ident(staff))
    assert resp.status_code == 403, f"{tool}: identity read by a holder of nothing got {resp.status_code}"


@pytest.mark.parametrize("tool,path,slugs", GATED, ids=GATED_IDS)
def test_ac13_identity_staff_holding_the_slug_passes_the_gate(env, tool, path, slugs):
    staff = mk_user(env.db, "holder", perms=slugs[:1])
    resp = env.client.get(path, headers=env.ident(staff))
    assert resp.status_code == EMPTY_DB_STATUS.get(tool, 200), f"{tool}: {resp.status_code} {resp.text[:200]}"


@pytest.mark.parametrize("tool,path,slugs", GATED, ids=GATED_IDS)
def test_ac13_session_and_plain_key_behave_as_today(env, tool, path, slugs):
    """Regression: no new gate for a session or a plain key (passes today)."""
    nobody = mk_user(env.db, "nobody")
    expected = EMPTY_DB_STATUS.get(tool, 200)
    assert env.client.get(path, headers=env.session(nobody)).status_code == expected, f"{tool} session"
    assert env.client.get(path, headers=env.plain()).status_code == expected, f"{tool} plain key"


# =========================================================================== #
# AC-14  pickers stay open to any staff (regression, passes today)            #
# =========================================================================== #
PICKERS = [
    ("GET", "/api/v1/master-data/products"),
    ("GET", "/api/v1/inventory/warehouses"),
    ("POST", "/api/v1/lookup/resolve"),
    ("GET", "/api/v1/system/tool-capabilities/summary"),
]


@pytest.mark.parametrize("method,path", PICKERS)
def test_ac14_pickers_are_open_to_staff_holding_nothing(env, method, path):
    staff = mk_user(env.db, "nothing")
    resp = env.client.request(method, path, headers=env.ident(staff))
    expected = 422 if method == "POST" else 200  # lookup/resolve with no body is a validation error
    assert resp.status_code == expected, f"{path}: {resp.status_code} {resp.text[:200]}"


# =========================================================================== #
# AC-15  own scope: session vs identity parity                                #
# =========================================================================== #
def _own_world(env):
    """Salesperson A (view_own, contact CA) and salesperson B (contact CB), both granted Sorento."""
    from tests._own_scope_support import contact

    db = env.db
    ca, cb = contact(db, "CA"), contact(db, "CB")
    a = mk_user(db, "own-a", companies=[SORENTO], last_active=SORENTO, contact_id=ca.id)
    b = mk_user(db, "own-b", companies=[SORENTO], last_active=SORENTO, contact_id=cb.id)
    return SimpleNamespace(a=a, b=b, ca=ca, cb=cb)


def _ids(resp) -> set:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["data"] if isinstance(body, dict) and "data" in body else body
    return {row["id"] for row in rows}


def test_ac15_complaints_list_parity_view_own(env):
    from app.models.complaints import Complaint

    w = _own_world(env)
    mine = Complaint(id=uid(), complaint_number=unique_code("CMP"), contact_id=w.ca.id, status="new")
    theirs = Complaint(id=uid(), complaint_number=unique_code("CMP"), contact_id=w.cb.id, status="new")
    nobody = Complaint(id=uid(), complaint_number=unique_code("CMP"), contact_id=None, status="new")
    env.db.add_all([mine, theirs, nobody])
    env.db.flush()
    perm = "complaint_management.complaints.view_own"
    holder = w.a
    grant(env.db, holder, [perm])

    path = "/api/v1/complaints-management/complaints/"
    via_session = _ids(env.client.get(path, params={"limit": 100}, headers=env.session(holder)))
    via_identity = _ids(env.client.get(path, params={"limit": 100}, headers=env.ident(holder)))
    assert mine.id in via_session and theirs.id not in via_session, "fixture: session baseline"
    assert via_identity == via_session, "AC-15: the panel returns the rows the session returns"
    assert mine.id in via_identity and theirs.id not in via_identity and nobody.id not in via_identity


def test_ac15_projects_list_and_detail_parity_view_own(env):
    from tests.test_portal_p2_own_scope_projects import _project

    w = _own_world(env)
    mine = _project(env.db, SORENTO, w.a)
    theirs = _project(env.db, SORENTO, w.b)
    holder = w.a
    grant(env.db, holder, ["projects.projects.view_own"])

    base = "/api/v1/project-sales/projects/"
    via_session = _ids(env.client.get(base, params={"limit": 100}, headers=env.session(holder)))
    via_identity = _ids(env.client.get(base, params={"limit": 100}, headers=env.ident(holder)))
    assert mine.id in via_session and theirs.id not in via_session, "fixture: session baseline"
    assert via_identity == via_session, "AC-15: projects list parity"
    own_detail = (
        env.client.get(f"{base}{mine.id}", headers=env.session(holder)).status_code,
        env.client.get(f"{base}{mine.id}", headers=env.ident(holder)).status_code,
    )
    foreign_detail = (
        env.client.get(f"{base}{theirs.id}", headers=env.session(holder)).status_code,
        env.client.get(f"{base}{theirs.id}", headers=env.ident(holder)).status_code,
    )
    assert own_detail == (200, 200), own_detail
    assert foreign_detail[0] == foreign_detail[1] == 404, f"AC-15: foreign project detail {foreign_detail}"


def test_ac15_purchase_request_by_number_parity(env):
    from app.models.procurement import PurchaseRequestHeader

    w = _own_world(env)
    number = unique_code("PR")[:40]
    row = PurchaseRequestHeader(
        id=uid(), request_type="purchase_request", request_number=number,
        request_date=date(2026, 10, 1), customer_name="ZZT cust", status="submitted",
        contact_id=w.ca.id,
    )
    env.db.add(row)
    env.db.flush()
    holder = w.a
    grant(env.db, holder, ["procurement.purchase_requests.view_own"])
    path = f"/api/v1/procurement/purchase-requests/by-number/{number}"
    s = env.client.get(path, headers=env.session(holder))
    i = env.client.get(path, headers=env.ident(holder))
    assert (i.status_code, i.json() if i.status_code == 200 else None) == (
        s.status_code, s.json() if s.status_code == 200 else None
    ), f"AC-15: by-number parity session={s.status_code} identity={i.status_code}"
    # a limited user for whom the session refuses a number must not read more through the panel
    other = w.b
    grant(env.db, other, ["procurement.purchase_requests.view_own"])
    s2 = env.client.get(path, headers=env.session(other))
    i2 = env.client.get(path, headers=env.ident(other))
    assert s2.status_code != 200 and i2.status_code == s2.status_code, (
        f"AC-15: someone else's request by number: session={s2.status_code} identity={i2.status_code}"
    )


# =========================================================================== #
# AC-16 / AC-17 / AC-18  company scope                                        #
# =========================================================================== #
def test_ac16_identity_scope_is_the_staffs_active_company_like_a_session(env, probe):
    staff = mk_user(env.db, "two-co", companies=[env.co_a, env.co_b], last_active=env.co_b)
    session = probe.get("/api/v1/zzt/whoami", headers=env.session(staff)).json()["scope"]
    identity = probe.get("/api/v1/zzt/whoami", headers=env.ident(staff)).json()["scope"]
    assert session == [env.co_b]
    assert identity == session, "AC-16: resolved exactly as a session resolves it"


def test_ac16_a_superadmin_staff_is_narrowed_to_their_active_company(env, probe):
    staff = mk_user(env.db, "super", roles=("superadmin",), last_active=env.co_a)
    session = probe.get("/api/v1/zzt/whoami", headers=env.session(staff)).json()["scope"]
    identity = probe.get("/api/v1/zzt/whoami", headers=env.ident(staff)).json()["scope"]
    assert session == [env.co_a]
    assert identity == [env.co_a], "AC-16: not 'all', not the key's scope"


def _seed_two_company_rows(env):
    db = env.db
    rows = SimpleNamespace()
    for tag, company in (("a", env.co_a), ("b", env.co_b)):
        prod = product(db, company_id=company, code=unique_code(f"P{tag.upper()}"))
        wh = warehouse(db, company_id=company)
        stock(db, company_id=company, product_id=prod.id, warehouse_id=wh.id, on_hand=7)
        setattr(rows, f"code_{tag}", prod.product_code)
        setattr(rows, f"order_{tag}", order(db, company_id=company, number=unique_code(f"ORD{tag.upper()}")).order_number)
    return rows


def _rows_parity(env, path, a_marker, b_marker, perms):
    staff = mk_user(env.db, "reader", perms=perms, companies=[env.co_a, env.co_b], last_active=env.co_a)
    session = env.client.get(path, params={"limit": 500, "top_n": 50}, headers=env.session(staff))
    identity = env.client.get(path, params={"limit": 500, "top_n": 50}, headers=env.ident(staff))
    assert session.status_code == 200, session.text[:300]
    assert a_marker in session.text and b_marker not in session.text, "fixture: session baseline"
    assert identity.status_code == 200, identity.text[:300]
    assert a_marker in identity.text, "AC-16: the active company's row is present"
    assert b_marker not in identity.text, "AC-16: the other company's row is absent"


def test_ac16_orders_rows_match_the_session(env):
    rows = _seed_two_company_rows(env)
    _rows_parity(env, ORDERS, rows.order_a, rows.order_b, [ORDERS_VIEW])


def test_ac16_stock_balance_rows_match_the_session(env):
    rows = _seed_two_company_rows(env)
    _rows_parity(env, STOCK_BALANCE, rows.code_a, rows.code_b, [STOCK_VIEW])


def test_ac16_purchase_orders_rows_match_the_session(env):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    db = env.db
    codes = {}
    for tag, company in (("a", env.co_a), ("b", env.co_b)):
        prod = product(db, company_id=company, code=unique_code(f"PO{tag.upper()}"))
        wh = warehouse(db, company_id=company)
        po = PurchaseOrder(
            id=uid(), po_number=unique_code("PO"), status="active", issue_date=date(2026, 6, 1),
            expected_date=date(2026, 12, 1), company_id=company,
        )
        db.add(po)
        db.flush()
        db.add(PurchaseOrderLine(
            id=uid(), purchase_order_id=po.id, product_id=prod.id, warehouse_id=wh.id, qty_ordered=5,
            qty_received=0, unit_cost=3, line_total=15, expected_date=date(2026, 12, 1),
            line_status="open", company_id=company,
        ))
        codes[tag] = prod.product_code
    db.flush()
    _rows_parity(env, "/api/v1/procurement/purchase-orders/last-cost", codes["a"], codes["b"], ["scm.purchase_orders.view"])


def test_ac17_a_staff_member_with_no_grants_reads_nothing(env, probe):
    rows = _seed_two_company_rows(env)
    staff = mk_user(env.db, "no-grants", perms=[ORDERS_VIEW])
    assert probe.get("/api/v1/zzt/whoami", headers=env.ident(staff)).json()["scope"] == "unset"
    resp = env.client.get(ORDERS, params={"limit": 500}, headers=env.ident(staff))
    assert resp.status_code == 200, resp.text[:300]
    assert rows.order_a not in resp.text and rows.order_b not in resp.text, "AC-17: zero rows, never all"


def test_ac17_a_bad_id_never_widens_to_all_companies(env):
    rows = _seed_two_company_rows(env)
    resp = env.client.get(ORDERS, params={"limit": 500}, headers=env.ident(uid()))
    assert rows.order_a not in resp.text and rows.order_b not in resp.text, "AC-17"
    assert resp.status_code == 403, resp.text[:300]


def test_ac17_a_bad_id_scope_is_empty_not_all(env, probe):
    """The scope resolver itself, with the id the dependency would refuse: zero rows, not None."""
    from app.services.company_scope_resolver import resolve_company_scope

    scope = resolve_company_scope(_request(env, {"X-API-Key": env.key, STAFF_HEADER: uid()}), env.db)
    assert scope is not None and scope != "all", "AC-17: a bad id must never resolve to every company"
    assert scope is UNSET or scope == frozenset()


def _request(env, headers, query=""):
    return Request(
        {
            "type": "http", "method": "GET", "path": "/api/v1/zzt/whoami",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "query_string": query.encode(),
        }
    )


def test_ac18_a_non_blank_contact_pair_with_the_header_is_403(env, probe):
    """AC-6 (replaces the old intersection rule): the panel always blanks the pair."""
    staff = mk_user(env.db, "two-co", companies=[env.co_a, env.co_b], last_active=env.co_a)
    rid, space = mk_contact_in(env.db, [env.co_a, env.co_b])
    resp = probe.get(f"/api/v1/zzt/whoami?contact_id={rid}&space_id={space}", headers=env.ident(staff))
    assert resp.status_code == 403, f"AC-6: contact pair with the header got {resp.status_code}"
    assert INVALID_CODE in resp.text


def test_ac18_a_non_blank_contact_pair_with_the_header_reads_zero_rows(env):
    rows = _seed_two_company_rows(env)
    staff = mk_user(env.db, "reader", perms=[ORDERS_VIEW], companies=[env.co_a, env.co_b], last_active=env.co_a)
    rid, space = mk_contact_in(env.db, [env.co_a, env.co_b])
    resp = env.client.get(ORDERS, params={"contact_id": rid, "space_id": space}, headers=env.ident(staff))
    assert resp.status_code == 403, f"AC-6: got {resp.status_code}"
    assert rows.order_a not in resp.text and rows.order_b not in resp.text


def test_ac18_a_blank_pair_counts_as_no_pair_and_passes(env, probe):
    """The panel sends `contact_id=&space_id=`."""
    staff = mk_user(env.db, "two-co", companies=[env.co_a, env.co_b], last_active=env.co_a)
    resp = probe.get("/api/v1/zzt/whoami?contact_id=&space_id=", headers=env.ident(staff))
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["id"] == staff
    assert resp.json()["scope"] == [env.co_a]


def test_ac18_a_blank_pair_on_a_real_route_reads_the_active_company(env):
    rows = _seed_two_company_rows(env)
    staff = mk_user(env.db, "reader", perms=[ORDERS_VIEW], companies=[env.co_a, env.co_b], last_active=env.co_a)
    resp = env.client.get(ORDERS, params={"contact_id": "", "space_id": ""}, headers=env.ident(staff))
    assert resp.status_code == 200, resp.text[:300]
    assert rows.order_a in resp.text and rows.order_b not in resp.text


# =========================================================================== #
# AC-19 / AC-20  record context (route half; the panel half is in                #
# test_ai_panel_staff_identity.py)                                             #
# =========================================================================== #
RECORD_KINDS = {
    "stock_inquiry": ["procurement.stock_inquiries.view", "procurement.stock_inquiries.view_own"],
    "purchase_request": ["procurement.purchase_requests.view", "procurement.purchase_requests.view_own"],
    "sponsorship_form": ["procurement.sponsorship_forms.view", "procurement.sponsorship_forms.view_own"],
    "complaint": ["complaint_management.complaints.view", "complaint_management.complaints.view_own"],
}


def _record_row(db, kind: str, contact_id=None) -> str:
    from app.models.complaints import Complaint
    from app.models.procurement import PurchaseRequestHeader, StockInquiry

    if kind == "stock_inquiry":
        row = StockInquiry(id=uid(), inquiry_number=unique_code("SI")[:40], status="submitted", contact_id=contact_id)
    elif kind == "complaint":
        row = Complaint(id=uid(), complaint_number=unique_code("CMP"), status="approved", contact_id=contact_id)
    else:
        row = PurchaseRequestHeader(
            id=uid(), request_type=kind, request_number=unique_code("PR")[:40], customer_name="ZZT cust",
            status="submitted", contact_id=contact_id,
        )
    db.add(row)
    db.flush()
    return row.id


@pytest.mark.parametrize("kind", sorted(RECORD_KINDS))
def test_ac19_record_context_route_needs_a_view_permission(env, kind):
    row_id = _record_row(env.db, kind)
    nobody = mk_user(env.db, "nobody", companies=[SORENTO], last_active=SORENTO)
    path = f"/api/v1/assistant/record-context/{kind}/{row_id}"
    assert env.client.get(path, headers=env.session(nobody)).status_code == 403, f"{kind}: no permission"


@pytest.mark.parametrize("kind", sorted(RECORD_KINDS))
def test_ac19_record_context_route_view_holder_reads(env, kind):
    row_id = _record_row(env.db, kind)
    holder = mk_user(env.db, "viewer", perms=RECORD_KINDS[kind][:1], companies=[SORENTO], last_active=SORENTO)
    path = f"/api/v1/assistant/record-context/{kind}/{row_id}"
    resp = env.client.get(path, headers=env.session(holder))
    assert resp.status_code == 200, f"{kind}: {resp.status_code} {resp.text[:200]}"


@pytest.mark.parametrize("kind", sorted(RECORD_KINDS))
def test_ac20_record_context_route_view_own_reads_only_their_record(env, kind):
    w = _own_world(env)
    mine = _record_row(env.db, kind, contact_id=w.ca.id)
    theirs = _record_row(env.db, kind, contact_id=w.cb.id)
    holder = w.a
    grant(env.db, holder, RECORD_KINDS[kind][1:])
    headers = env.session(holder)
    ok = env.client.get(f"/api/v1/assistant/record-context/{kind}/{mine}", headers=headers)
    foreign = env.client.get(f"/api/v1/assistant/record-context/{kind}/{theirs}", headers=headers)
    assert ok.status_code == 200, f"{kind}: own record {ok.status_code} {ok.text[:200]}"
    assert foreign.status_code in (403, 404), f"{kind}: someone else's record answered {foreign.status_code}"


# =========================================================================== #
# AC-22  guard: every catalog read tool is refused to a staff holding nothing,   #
# or named in an explicit allow-list with its reason                           #
# =========================================================================== #
ALLOW_OPEN = {
    # open pickers (owner ruling L10, dependencies.py:499-505)
    "crm_master_products_list": "open picker: products list",
    "crm_inventory_warehouses_list": "open picker: warehouses",
    "crm_lookup_resolve": "open picker: dropdown keyword resolve",
    "crm_system_tool_capabilities_summary": "open: tool capabilities",
}


def _catalog():
    path = Path(__file__).resolve().parents[2] / "sorento_crm_mcp" / "sorento_crm_mcp" / "catalog.py"
    spec = importlib.util.spec_from_file_location("zzt_unify_catalog", path)
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules["zzt_unify_catalog"] = module  # dataclass needs the module registered while it executes
    spec.loader.exec_module(module)
    return module.CATALOG


def _read_tools():
    return [
        s for s in _catalog()
        if (s.method == "GET" or s.read_only) and s.path.startswith("/api/v1/") and not s.external
    ]


def test_ac22_allow_list_names_only_real_catalog_reads():
    names = {s.name for s in _read_tools()}
    assert set(ALLOW_OPEN) <= names, f"stale allow-list entries: {sorted(set(ALLOW_OPEN) - names)}"


def test_ac22_every_catalog_read_is_refused_to_a_staff_member_holding_nothing(env):
    staff = mk_user(env.db, "nothing", companies=[SORENTO], last_active=SORENTO)
    open_tools = []
    for spec in _read_tools():
        if spec.name in ALLOW_OPEN:
            continue
        url = re.sub(r"\{[^}]+\}", uid(), spec.path)
        resp = env.client.request(spec.method, url, headers=env.ident(staff))
        if resp.status_code != 403:
            open_tools.append(f"{spec.name} {spec.method} {spec.path} -> {resp.status_code}")
    assert not open_tools, (
        "AC-22: these catalog reads answered a staff member who holds nothing; gate them or add them "
        "to ALLOW_OPEN with a reason:\n  " + "\n  ".join(open_tools)
    )


# =========================================================================== #
# AC-25  chatbot lanes, agent loop and n8n send no identity header            #
# =========================================================================== #
def test_ac25_no_other_mcp_client_in_the_backend_sends_a_staff_identity():
    services = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in services.rglob("*.py"):
        if path.name == "ai_assistant_service.py":
            continue
        src = path.read_text()
        if "MCPRuntimeClient(" not in src:
            continue
        for args in re.findall(r"MCPRuntimeClient\((.*?)\)\n", src, flags=re.S):
            if "staff" in args:
                offenders.append(f"{path.relative_to(services)}: {args.strip()[:80]}")
    assert not offenders, f"AC-25: only the AI panel may mark a staff call: {offenders}"


def test_ac25_a_plain_key_call_with_other_headers_behaves_as_today(env, probe):
    """n8n sends X-Source / X-Tool-Name and no identity header: unchanged principal and scope."""
    resp = probe.get("/api/v1/zzt/whoami", headers={**env.plain(), "X-Source": "n8n", "X-Tool-Name": "crm_x"})
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == env.actas
    assert resp.json()["scope"] == "all"
    assert resp.json()["actor"]["actor_type"] == "integration"


# =========================================================================== #
# AC-12  crm_portal_link_get's external route: a real slug needs the staff member #
# =========================================================================== #
PORTAL_LINK = "/api/v1/external/portal-tokens/"
PORTAL_SLUG = "user_management.contacts.portal_link"


def test_ac12_portal_link_route_is_gated_on_the_staffs_real_slug(env):
    holder = mk_user(env.db, "holder", perms=[PORTAL_SLUG])
    nothing = mk_user(env.db, "nothing")
    ok = env.client.post(PORTAL_LINK, json={}, headers=env.ident(holder))
    refused = env.client.post(PORTAL_LINK, json={}, headers=env.ident(nothing))
    assert ok.status_code != 403, f"holder of {PORTAL_SLUG} must pass the gate, got {ok.status_code}"
    assert refused.status_code == 403, f"a holder of nothing got {refused.status_code}"


# =========================================================================== #
# AC-12  require_external_permission_for_path with the identity header        #
# =========================================================================== #
def test_ac12_for_path_real_slug_needs_both_users(env, probe):
    path = "/api/v1/zzt/ext-path/thing"
    assert _perm_status(env, probe, path, ["zzt.thing.view"], ["zzt.thing.view"], actas_roles=()) == 200
    assert _perm_status(env, probe, path, [], ["zzt.thing.view"], actas_roles=()) == 403, "staff lacks the slug"
    assert _perm_status(env, probe, path, ["zzt.thing.view"], [], actas_roles=()) == 403, "act-as lacks it"


def test_ac12_for_path_integration_slug_is_checked_on_actas_only(env, probe):
    path = "/api/v1/zzt/ext-path/int"
    assert _perm_status(env, probe, path, [], ["integration.zzt_thing"], actas_roles=()) == 200
    assert _perm_status(env, probe, path, [], [], actas_roles=()) == 403


# =========================================================================== #
# STAFF_READ_ROUTES is pinned against the catalog                             #
# =========================================================================== #
def _norm_route(method: str, path: str) -> tuple[str, str]:
    return method.upper(), re.sub(r"\{[^}]+\}", "{}", path).rstrip("/")


def test_staff_read_routes_equal_the_catalogs_reads_under_api_v1():
    from app.services.company_scope_resolver import STAFF_READ_ROUTES

    expected = {
        _norm_route(s.method, s.path)
        for s in _catalog()
        if (s.method == "GET" or s.read_only) and s.path.startswith("/api/v1/")
    }
    actual = set()
    for entry in STAFF_READ_ROUTES:
        method, path = entry if isinstance(entry, tuple) else entry.split(None, 1)
        actual.add(_norm_route(method, path))
    assert actual == expected, (
        f"STAFF_READ_ROUTES must be exactly the catalog reads under /api/v1/: "
        f"missing {sorted(expected - actual)}, stray {sorted(actual - expected)}"
    )


def test_ac2_the_catalog_has_exactly_one_external_read_and_it_is_the_guide_tool():
    """A future hand-written CRM read (flagged `external`, skipped by the AC-22 guard and by the
    compiled-tool forwarding) must fail here until it is handled."""
    external_reads = sorted(s.name for s in _catalog() if (s.method == "GET" or s.read_only) and s.external)
    assert external_reads == ["user_guides_read"]


# =========================================================================== #
# AC-6  more ways to fail closed                                              #
# =========================================================================== #
def test_ac6_a_read_off_the_list_is_403_and_scope_unset(env, probe):
    staff = mk_user(env.db, "staff", companies=[SORENTO], last_active=SORENTO)
    resp = probe.get("/api/v1/zzt/offlist", headers=env.ident(staff))
    assert resp.status_code == 403, f"AC-6: header on an off-list read got {resp.status_code}"
    assert INVALID_CODE in resp.text
    from app.services.company_scope_resolver import resolve_company_scope

    req = _request(env, {"X-API-Key": env.key, STAFF_HEADER: staff})
    req.scope["path"] = "/api/v1/zzt/offlist"
    assert resolve_company_scope(req, env.db) is UNSET, "AC-6: an off-list read has no scope at all"


def test_ac6_a_write_off_the_list_still_ignores_the_header(env, probe):
    staff = mk_user(env.db, "staff")
    resp = probe.post("/api/v1/zzt/write", headers=env.ident(staff))
    assert resp.status_code == 200 and resp.json()["user"]["id"] == env.actas


def test_ac6_naming_an_integration_user_is_403(env, probe):
    other = mk_user(env.db, "an-integration", integration=True)
    resp = probe.get("/api/v1/zzt/whoami", headers=env.ident(other))
    assert resp.status_code == 403, f"AC-6: an is_integration user may not be named, got {resp.status_code}"
    assert INVALID_CODE in resp.text


# =========================================================================== #
# AC-27  naming a stronger user gains nothing act-as lacks                    #
# =========================================================================== #
def test_ac27_audit_logs_stay_403_when_a_superadmin_is_named(env):
    env.use_actas(perms=["zzt.unrelated.view"])
    boss = mk_user(env.db, "boss", roles=("superadmin",), companies=[SORENTO], last_active=SORENTO)
    assert env.client.get("/api/v1/audit/logs/", headers=env.plain()).status_code == 403, "fixture: plain key"
    named = env.client.get("/api/v1/audit/logs/", headers=env.ident(boss))
    assert named.status_code == 403, f"AC-27: naming a superadmin lifted the audit gate ({named.status_code})"


def test_ac27_tickets_view_all_is_not_lent_by_the_named_user(env):
    from app.models.tickets import Ticket

    env.use_actas(perms=["tickets.tickets.view"])
    other = mk_user(env.db, "other", companies=[SORENTO], last_active=SORENTO)
    boss = mk_user(
        env.db, "boss", perms=["tickets.tickets.view", "tickets.tickets.view_all"],
        companies=[SORENTO], last_active=SORENTO,
    )
    env.db.add(Ticket(title="ZZT secret", raised_by=other, raised_by_kind="user"))
    env.db.flush()
    path = "/api/v1/tickets-management/tickets"
    plain = env.client.get(path, headers=env.plain())
    named = env.client.get(path, headers=env.ident(boss))
    assert plain.status_code == 200, "fixture: plain key"
    assert plain.json()["pagination"]["total"] == 0, "fixture: act-as has no view_all"
    assert named.status_code == 403, f"AC-27: tickets are off the list, got {named.status_code}"


def _incoming_has_field_access(resp) -> bool:
    assert resp.status_code == 200, resp.text[:300]
    return "field_access" in resp.json()


def test_ac27_incoming_clearance_is_not_lifted_by_staff_alone(env):
    env.use_actas(perms=["procurement.packing_lists.view"])
    holder = mk_user(
        env.db, "holder", perms=["procurement.packing_lists.view", "procurement.packing_lists.view_clearance"],
        companies=[SORENTO], last_active=SORENTO,
    )
    path = "/api/v1/incoming-stock/list"
    assert _incoming_has_field_access(env.client.get(path, headers=env.plain())), "fixture: plain key is gated"
    assert _incoming_has_field_access(env.client.get(path, headers=env.ident(holder))), (
        "AC-27: staff holding clearance with an act-as lacking it must stay gated"
    )


def test_ac27_incoming_clearance_is_lifted_when_both_users_hold_it(env):
    both = ["procurement.packing_lists.view", "procurement.packing_lists.view_clearance"]
    env.use_actas(perms=both)
    holder = mk_user(env.db, "holder", perms=both, companies=[SORENTO], last_active=SORENTO)
    assert not _incoming_has_field_access(
        env.client.get("/api/v1/incoming-stock/list", headers=env.ident(holder))
    ), "AC-27: both users hold clearance, so the gate lifts"


def _disable_module(monkeypatch, module):
    from app.modules.runtime import guards, installer

    monkeypatch.setattr(settings, "module_guard_strict", True, raising=False)
    for target in (installer, guards):
        monkeypatch.setattr(target, "tenant_has_any_module_row", lambda db_, tenant: True)
        monkeypatch.setattr(target, "is_module_enabled", lambda db_, tenant, mod: mod != module)


def test_ac27_module_check_via_require_permission_asks_act_as_too(env, probe, monkeypatch):
    env.use_actas(perms=["order_management.orders.view"], roles=())
    boss = mk_user(env.db, "boss", roles=("superadmin",))
    _disable_module(monkeypatch, "order")
    resp = probe.get("/api/v1/zzt/permmod", headers=env.ident(boss))
    assert resp.status_code == 403, f"AC-27: a superadmin staff lifted a disabled module, got {resp.status_code}"


def test_ac27_module_guard_asks_act_as_too(env, probe, monkeypatch):
    env.use_actas(perms=["order_management.orders.view"], roles=())
    boss = mk_user(env.db, "boss", roles=("superadmin",))
    _disable_module(monkeypatch, "order")
    resp = probe.get("/api/v1/zzt/modguard", headers=env.ident(boss))
    assert resp.status_code == 403, f"AC-27: guards.py module guard lifted by the named superadmin, got {resp.status_code}"


@pytest.mark.parametrize("path", ["/api/v1/scm/low-stock-report", "/api/v1/sales/analysis"])
def test_ac27_contact_attributed_reads_cannot_name_a_user(env, path):
    staff = mk_user(
        env.db, "staff", roles=("superadmin",), companies=[SORENTO], last_active=SORENTO
    )
    bare = env.client.get(path, headers=env.ident(staff))
    assert bare.status_code in (403, 422), f"AC-27: no contact got {bare.status_code}"
    rid, space = mk_contact_in(env.db, [SORENTO])
    paired = env.client.get(path, params={"contact_id": rid, "space_id": space}, headers=env.ident(staff))
    assert paired.status_code == 403, f"AC-27: a named user cannot be attributed, got {paired.status_code}"


# =========================================================================== #
# AC-9  the backend logs the named user                                       #
# =========================================================================== #
def test_ac9_the_named_user_is_logged_on_an_identity_read(env, probe, caplog):
    import logging

    staff = mk_user(env.db, "staff")
    with caplog.at_level(logging.INFO):
        assert probe.get("/api/v1/zzt/whoami", headers=env.ident(staff)).status_code == 200
    assert any(staff in rec.getMessage() for rec in caplog.records), (
        "AC-9: no log line names the staff user id on an identity read"
    )


# =========================================================================== #
# Pins: handler checks that read a user's slugs or role (AC-27)               #
# =========================================================================== #
def test_ac27_external_for_path_off_the_list_is_403_staff_identity_invalid(env, probe):
    staff = mk_user(env.db, "staff", perms=["zzt.thing.view"])
    env.use_actas(perms=["zzt.thing.view"])
    resp = probe.get("/api/v1/zzt/ext-off/thing", headers=env.ident(staff))
    assert resp.status_code == 403, resp.text
    assert INVALID_CODE in resp.text, "an unlisted read must be refused as an identity, not as a missing slug"


def _project_with_a_customer(env, phone: str):
    from app.models.projects import ProjectSalesProfile
    from tests._mc_lookup_seed import customer
    from tests.test_portal_p2_own_scope_projects import _project

    cust = customer(env.db, company_id=SORENTO)
    cust.phone_number = phone
    project = _project(env.db, SORENTO, None)
    env.db.add(ProjectSalesProfile(project_id=project.id, customer_id=cust.id))
    env.db.flush()
    return project


def _listed_phone(resp, project_id):
    assert resp.status_code == 200, resp.text[:300]
    (row,) = [r for r in resp.json()["data"] if r["id"] == project_id]
    return row["customer_phone"]


def test_ac27_project_field_gate_needs_the_slug_on_both_users(env):
    """`_reader_permissions` (projects.py:266): the customer phone is behind
    `order_management.customers.view`; a named staff member holding it does not lend it."""
    env.use_actas(perms=["projects.projects.view"])
    project = _project_with_a_customer(env, "0312345678")
    staff = mk_user(
        env.db, "staff", perms=["projects.projects.view", "order_management.customers.view"],
        companies=[SORENTO], last_active=SORENTO,
    )
    path = "/api/v1/project-sales/projects/"
    session = env.client.get(path, params={"limit": 100}, headers=env.session(staff))
    assert _listed_phone(session, project.id) == "0312345678", "fixture: the session sees the phone"
    identity = env.client.get(path, params={"limit": 100}, headers=env.ident(staff))
    assert _listed_phone(identity, project.id) is None, "AC-27: act-as lacks the slug, so the field stays gated"
    detail = env.client.get(f"{path}{project.id}", headers=env.ident(staff))
    assert detail.status_code == 200 and detail.json()["customer_phone"] is None


def test_ac27_project_field_gate_opens_when_both_users_hold_the_slug(env):
    both = ["projects.projects.view", "order_management.customers.view"]
    env.use_actas(perms=both)
    project = _project_with_a_customer(env, "0312345678")
    staff = mk_user(env.db, "staff", perms=both, companies=[SORENTO], last_active=SORENTO)
    identity = env.client.get("/api/v1/project-sales/projects/", params={"limit": 100}, headers=env.ident(staff))
    assert _listed_phone(identity, project.id) == "0312345678"


def test_ac27_current_stock_list_does_not_widen_to_a_named_superadmins_grants(env):
    """attachments.py:664: no actor on an identity read, so the shared-attachment widening
    (resources_service.py:1469) stays off. The link is to another company's product."""
    from app.models.resources import Attachment
    from tests._mc_lookup_seed import attachment_type, product, product_attachment

    env.use_actas(perms=["inventory.stock.view"])
    kind = attachment_type(env.db, name="Stock List")
    shared = Attachment(
        id=uid(), original_filename="ZZT-stock.pdf", stored_filename="ZZT-stock.pdf",
        file_path="https://cdn.test/zzt-stock.pdf", attachment_type_id=kind.id, is_deleted=False, company_id=None,
    )
    env.db.add(shared)
    env.db.flush()
    other = product(env.db, company_id=env.co_b, code=unique_code("PB"))
    product_attachment(env.db, company_id=env.co_b, product_id=other.id, attachment_id=shared.id)
    boss = mk_user(env.db, "boss", roles=("superadmin",), last_active=env.co_a)

    path = "/api/v1/resource-management/attachments/current-stock-list"
    session = env.client.get(path, headers=env.session(boss))
    assert session.status_code == 200, session.text[:300]
    assert other.product_code in session.text, "fixture: a superadmin session sees the other company's link"
    identity = env.client.get(path, headers=env.ident(boss))
    assert identity.status_code == 200, identity.text[:300]
    assert other.product_code not in identity.text, "AC-27: the widening follows the grants of nobody on an identity read"


@pytest.mark.parametrize(
    "fn,slug", [("require_invoiced_access", "sales.reports.view"), ("require_unpaid_access", "finance.billing_documents.view")]
)
def test_ac27_the_invoiced_and_unpaid_gates_ask_both_users(env, fn, slug):
    from app.services.error_handler import AppException
    from app.services.sales import invoiced_sales

    gate = getattr(invoiced_sales, fn)
    staff = mk_user(env.db, "staff", perms=[slug])
    lacking = mk_user(env.db, "actas-lacking")
    holding = mk_user(env.db, "actas-holding", perms=[slug])
    with pytest.raises(AppException) as err:
        gate(env.db, {"id": staff, "key_user_id": lacking})
    assert err.value.status_code == 403
    gate(env.db, {"id": staff, "key_user_id": holding})  # both hold it: passes
    with pytest.raises(AppException):
        gate(env.db, {"id": lacking, "key_user_id": holding})
