"""PORTAL-P4-REQUESTS S0-A: the staff routes of Stock Inquiry, Complaint, Purchase Request and
Sponsorship Form answer "only theirs" to a `view_own` holder (UAC P4-1 to P4-6, P4-17).

LIMITED = holds the form's `view_own` and not its `view`. "Theirs" = row.contact_id equals the
user's `respond_contact_id` (a requestor named on someone else's row does not count).
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text

from app.models.base import company_scope
from app.models.complaints import Complaint
from app.models.procurement import PurchaseRequestHeader, StockInquiry
from app.rbac.permission_registry import PERMISSION_REGISTRY

from ._own_scope_support import MARKER, acting, contact, sorento, uid, user
from ._pg_fixture import blank_session

SI, CMP, PR_URL = (
    "/api/v1/procurement/stock-inquiries",
    "/api/v1/complaints-management/complaints",
    "/api/v1/procurement/purchase-requests",
)

KINDS = {
    "stock_inquiry": ("procurement.stock_inquiries", SI),
    "complaint": ("complaint_management.complaints", CMP),
    "purchase_request": ("procurement.purchase_requests", PR_URL),
    "sponsorship_form": ("procurement.sponsorship_forms", PR_URL),
}
VIEW = {k: f"{p}.view" for k, (p, _) in KINDS.items()}
OWN = {k: f"{p}.view_own" for k, (p, _) in KINDS.items()}
ALL_SLUGS = {e["slug"] for e in PERMISSION_REGISTRY}


def limited(*kinds: str) -> set:
    """Every slug a user could hold except the four `view`s, plus the named kinds' `view_own`.

    Holding all the other slugs matters: a refused route must be refused by the scope rule, not
    because the test user happened to lack the route's own permission.
    """
    return (ALL_SLUGS - set(VIEW.values()) - set(OWN.values())) | {OWN[k] for k in kinds}


@pytest.fixture()
def scene():
    with blank_session() as db:
        company_id = sorento(db)
        ca, cb = contact(db, "CA Test Salesperson A"), contact(db, "CB Test Salesperson B")
        a, b = user(db, "Test Salesperson A", ca.id), user(db, "Test Salesperson B", cb.id)
        loner = user(db, "Test No Contact")
        with company_scope(db, frozenset({company_id})):
            yield db, a, b, loner, ca, cb


def _row(db, kind: str, contact_id: str, *, draft: bool = False, named_contact_id: str | None = None) -> str:
    """One row of `kind` submitted by `contact_id`; `named_contact_id` is the requestor."""
    rid, number = uid(), f"{MARKER}-{uid()[:8]}"
    status = "draft" if draft else "submitted"
    stamp = datetime.utcnow() if draft else None
    if kind == "stock_inquiry":
        db.add(StockInquiry(
            id=rid, inquiry_number=number, status="draft" if draft else "pending_purchasing",
            contact_id=contact_id, space_id="zzt-space", portal_draft_at=stamp,
            salesperson="Test Salesperson", salesperson_contact_id=named_contact_id or contact_id,
            product_code="TEST-CODE", item_description="Test item", quantity="1",
        ))
    elif kind == "complaint":
        db.add(Complaint(
            id=rid, complaint_number=number, status="draft" if draft else "submitted",
            contact_id=contact_id, space_id="zzt-space", portal_draft_at=stamp,
        ))
    else:
        db.add(PurchaseRequestHeader(
            id=rid, request_number=number, request_type=kind, status=status, source="portal",
            contact_id=contact_id, space_id="zzt-space", portal_draft_at=stamp,
            requested_by="Test Salesperson", requested_by_contact_id=named_contact_id or contact_id,
            project_title="Test project", purpose="Test purpose",
        ))
    db.flush()
    return rid


def _ids(client, url: str, **params) -> set:
    response = client.get(url + "/", params={"limit": 200, **params})
    assert response.status_code == 200, (response.status_code, response.text)
    return {r["id"] for r in response.json()["data"]}


def _list_params(kind: str) -> dict:
    return {"request_type": kind} if kind in ("purchase_request", "sponsorship_form") else {}


# ------------------------------------------------------------------ P4-1, P4-2


@pytest.mark.parametrize("kind", list(KINDS))
def test_p4_1_limited_list_is_only_their_rows_drafts_included_with_matching_total(scene, kind):
    db, a, b, _, ca, cb = scene
    mine = _row(db, kind, ca.id)
    mine_draft = _row(db, kind, ca.id, draft=True)
    theirs = _row(db, kind, cb.id)
    theirs_draft = _row(db, kind, cb.id, draft=True)
    named_on_theirs = _row(db, kind, cb.id, named_contact_id=ca.id)  # requestor A, submitter B: not A's
    with acting(db, a, limited(kind)) as client:
        response = client.get(KINDS[kind][1] + "/", params={"limit": 200, **_list_params(kind)})
        assert response.status_code == 200, (response.status_code, response.text)
        body = response.json()
        got = {r["id"] for r in body["data"]}
        assert got == {mine, mine_draft}, got & {theirs, theirs_draft, named_on_theirs}
        assert body["pagination"]["total"] == 2


@pytest.mark.parametrize("kind", list(KINDS))
def test_p4_2_limited_detail_and_revisions_own_200_foreign_404(scene, kind):
    db, a, b, _, ca, cb = scene
    mine = _row(db, kind, ca.id)
    theirs = _row(db, kind, cb.id)
    base = KINDS[kind][1]
    with acting(db, a, limited(kind)) as client:
        assert client.get(f"{base}/{mine}").status_code == 200
        assert client.get(f"{base}/{theirs}").status_code == 404
        if kind != "complaint":  # the complaint router has no revisions route today
            assert client.get(f"{base}/{mine}/revisions").status_code == 200
            assert client.get(f"{base}/{theirs}/revisions").status_code == 404


def test_p4_1_purchase_request_and_sponsorship_scope_by_the_rows_kind_slug(scene):
    db, a, b, _, ca, cb = scene
    pr = _row(db, "purchase_request", ca.id)
    sf = _row(db, "sponsorship_form", ca.id)
    with acting(db, a, limited("purchase_request")) as client:
        assert _ids(client, PR_URL) == {pr}
        assert client.get(f"{PR_URL}/{pr}").status_code == 200
        assert client.get(f"{PR_URL}/{sf}").status_code in (403, 404)
    with acting(db, a, limited("sponsorship_form")) as client:
        assert _ids(client, PR_URL) == {sf}
        assert client.get(f"{PR_URL}/{sf}").status_code == 200
        assert client.get(f"{PR_URL}/{pr}").status_code in (403, 404)


# ------------------------------------------------------------------ P4-4 (unchanged for staff)


@pytest.mark.parametrize("kind", list(KINDS))
def test_p4_4_view_holder_sees_every_row_even_with_view_own(scene, kind):
    db, a, b, _, ca, cb = scene
    mine, theirs = _row(db, kind, ca.id), _row(db, kind, cb.id)
    base = KINDS[kind][1]
    perms = limited(kind) | {VIEW[kind]}
    with acting(db, a, perms) as client:
        assert {mine, theirs} <= _ids(client, base, **_list_params(kind))
        assert client.get(f"{base}/{theirs}").status_code == 200


# ------------------------------------------------------------------ P4-5


@pytest.mark.parametrize("kind", list(KINDS))
def test_p4_5_no_linked_contact_sees_nothing(scene, kind):
    db, a, b, loner, ca, cb = scene
    row = _row(db, kind, ca.id)
    base = KINDS[kind][1]
    with acting(db, loner, limited(kind)) as client:
        assert _ids(client, base, **_list_params(kind)) == set()
        assert client.get(f"{base}/{row}").status_code == 404


# ------------------------------------------------------------------ P4-3: every other route is refused

# The routes a limited user may reach on each router: list, detail, revisions. Anything else
# on these routers answers 403. A route added later is refused by default, so it must be
# classified here before it can be reached.
ALLOWED = {
    "stock_inquiry": {("GET", ""), ("GET", "/{inquiry_id}"), ("GET", "/{inquiry_id}/revisions")},
    "purchase_request": {("GET", ""), ("GET", "/{request_id}"), ("GET", "/{request_id}/revisions")},
    "complaint": {("GET", ""), ("GET", "/{complaint_id}")},
}
ROUTERS = {"stock_inquiry": SI, "purchase_request": PR_URL, "complaint": CMP}


def _routes(base: str):
    from app.main import app

    seen = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path_format.startswith(base):
            rest = route.path_format[len(base):].rstrip("/")
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                seen.append((method, rest))
    return sorted(set(seen))


@pytest.mark.parametrize("router_kind", list(ROUTERS))
def test_p4_3_every_route_but_list_detail_revisions_answers_403(scene, router_kind):
    db, a, b, _, ca, cb = scene
    base = ROUTERS[router_kind]
    # Own row, so a 403 can only come from the scope rule, not from "someone else's row".
    kind = "purchase_request" if router_kind == "purchase_request" else router_kind
    own = _row(db, kind, ca.id)
    number = f"{MARKER}-x"
    routes = _routes(base)
    assert routes, base
    leaked = []
    with acting(db, a, limited(kind)) as client:
        for method, rest in routes:
            if (method, rest) in ALLOWED[router_kind]:
                continue
            path = rest
            for name in ("inquiry_id", "request_id", "complaint_id"):
                path = path.replace("{" + name + "}", own)
            path = path.replace("{number}", number)
            while "{" in path:
                start = path.index("{")
                path = path[:start] + uid() + path[path.index("}") + 1:]
            kwargs = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
            if method == "DELETE" and path.endswith("/bulk"):
                kwargs = {"json": {"ids": [own]}}
            response = client.request(method, base + path, **kwargs)
            if response.status_code != 403:
                leaked.append(f"{method} {rest or '/'} -> {response.status_code}")
    assert not leaked, "\n".join(leaked)


def test_p4_3_the_allowed_set_is_still_what_the_routers_carry():
    """A route removed or renamed must be re-classified, not silently dropped from ALLOWED."""
    for router_kind, base in ROUTERS.items():
        carried = set(_routes(base))
        assert ALLOWED[router_kind] <= carried, ALLOWED[router_kind] - carried


# ------------------------------------------------------------------ P4-6: form comments

COMMENTS = "/api/v1/form-comments"


@pytest.fixture()
def no_whatsapp(monkeypatch):
    from app.services.form_comment_service import FormCommentService

    monkeypatch.setattr(FormCommentService, "_notify_submitter", lambda self, *a, **k: "no_whatsapp")


@pytest.mark.parametrize("kind", list(KINDS))
def test_p4_6_limited_reads_and_posts_comments_on_their_own_row_foreign_is_404(scene, no_whatsapp, kind):
    db, a, b, _, ca, cb = scene
    mine, theirs = _row(db, kind, ca.id), _row(db, kind, cb.id)
    with acting(db, a, limited(kind)) as client:
        assert client.get(f"{COMMENTS}/{kind}/{mine}").status_code == 200
        posted = client.post(f"{COMMENTS}/{kind}/{mine}", data={"body": "Test comment"})
        assert posted.status_code == 201, (posted.status_code, posted.text)
        assert client.get(f"{COMMENTS}/{kind}/{theirs}").status_code == 404
        assert client.post(f"{COMMENTS}/{kind}/{theirs}", data={"body": "Test comment"}).status_code == 404


# ------------------------------------------------------------------ P4-17: impersonation


def test_p4_17_admin_viewing_as_the_salesperson_gets_exactly_their_list(scene, monkeypatch):
    """Real auth path: the admin's session resolves, X-Impersonate-User-Id swaps in the target,
    the target's REAL role grants decide LIMITED. An ended session falls back to the admin."""
    from fastapi.testclient import TestClient

    from app import dependencies
    from app.database import get_db
    from app.main import app
    from app.models.impersonation import ImpersonationSession
    from app.services.company_scope_resolver import apply_company_scope

    from .test_portal_p3_role_menu import _user as role_user

    db, _, _, _, ca, cb = scene
    # Real roles: salesperson holds the four view_own slugs; admin is a plain admin.
    admin = role_user(db, ["admin"])
    cs = contact(db, "CS Test Salesperson C")
    sp = role_user(db, ["salesperson"], contact=cs)
    sp_role = db.execute(text("select id from user_roles where slug = 'salesperson'")).scalar()
    for slug in OWN.values():
        pid = db.execute(text("select id from user_permissions where slug = :s"), {"s": slug}).scalar()
        if pid is None:
            pid = uid()
            db.execute(text(
                "insert into user_permissions (id, slug, name, description, created_at) "
                "values (:i, :s, :s, :s, now())"), {"i": pid, "s": slug})
        db.execute(text(
            "insert into user_role_permissions (id, role_id, permission_id, assigned_at) "
            "values (gen_random_uuid()::text, :r, :p, now()) on conflict (role_id, permission_id) do nothing"),
            {"r": sp_role, "p": pid})
    db.flush()
    mine = _row(db, "stock_inquiry", cs.id)
    theirs = _row(db, "stock_inquiry", cb.id)
    session_row = ImpersonationSession(id=uid(), admin_user_id=admin.id, target_user_id=sp.id)
    db.add(session_row)
    db.flush()

    monkeypatch.setattr(dependencies, "_resolve_session_to_user", lambda token, request, db_: {"id": admin.id, "status": "ACTIVE"})
    monkeypatch.setattr(dependencies, "_stamp_session_actor", lambda *a, **k: None)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[apply_company_scope] = lambda: None
    headers = {"Authorization": "Bearer zzt", "X-Impersonate-User-Id": sp.id}
    try:
        client = TestClient(app)
        viewing = client.get(SI + "/", params={"limit": 200}, headers=headers)
        assert viewing.status_code == 200, viewing.text
        assert {r["id"] for r in viewing.json()["data"]} == {mine}
        assert client.get(f"{SI}/{theirs}", headers=headers).status_code == 404

        session_row.ended_at = datetime.utcnow()
        db.flush()
        ended = client.get(SI + "/", params={"limit": 200}, headers=headers)
        assert ended.status_code == 200, ended.text
        assert {mine, theirs} <= {r["id"] for r in ended.json()["data"]}
    finally:
        app.dependency_overrides.clear()
