"""SORENTO-TOWN Phase 0: `GET /api/v1/town/snapshot` (AC-2, AC-3, AC-4, AC-10).

The endpoint reads the snapshot the store tests cover, from the real local Redis
(`app.services.queue_service.redis_conn`), for the signed-in user's company (Sorento here) and
today's MYT date. Auth is the same override pattern `tests/test_sales_yearly_routes.py` uses.
"""
from __future__ import annotations

import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.models.base import set_company_scope
from app.models.user import User, UserRole, UserRoleAssignment
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from tests._pg_fixture import blank_session, unique_code
from tests.test_sales_yearly_routes import _client, _user as _plain_user
from tests.town._town_seed import AMOUNT_KEYS, FAKE_RM_FIGURES, all_keys, fake_full

URL = "/api/v1/town/snapshot"
SLUG = "sales.reports.view"
BUSINESS_TABLES = (
    "billing_documents", "billing_document_lines", "customers", "stock", "warehouses", "reorder_level",
    "purchase_requests", "quotation_documents", "products",
)


def _user(db, *companies):
    """A staff user: a signed-in principal holding one ordinary (non portal) role."""
    principal = _plain_user(db, *companies)
    _with_role(db, principal, "zzt_staff_role")
    return principal


def _today():
    return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, frozenset({DEFAULT_COMPANY_ID}))
        yield s


@pytest.fixture
def stored(db):
    """A full snapshot for Sorento + today (MYT) in Redis. Returns the version."""
    from app.services.queue_service import redis_conn
    from app.services.town.snapshot import store

    return store(redis_conn, DEFAULT_COMPANY_ID, _today(), fake_full(_today(), DEFAULT_COMPANY_ID))


@contextmanager
def _real_rbac_client(db, principal):
    """Like `_client` but permission checks run for real (role rows seeded by the test)."""
    def _override_db():
        yield db

    async def _scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _scope
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _with_role(db, principal, slug):
    role = db.query(UserRole).filter(UserRole.slug == slug).first()
    if role is None:
        role = UserRole(id=str(uuid.uuid4()), slug=slug, name=f"ZZT {slug} {uuid.uuid4().hex[:6]}")
        db.add(role)
        db.flush()
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=principal["id"], role_id=role.id))
    db.flush()


# --------------------------------------------------------------------------- AC-2


def test_ac2_serving_the_snapshot_reads_no_business_table(db, stored):
    """Kill test: have the route fall back to `build_snapshot(db, ...)` (or read any customer,
    billing, stock, warehouse, reorder, PR or quotation row) and this goes red. Auth, session,
    permission and company-grant statements are allowed; the guarantee is no business table.
    """
    from sqlalchemy import event, text

    principal = _user(db, DEFAULT_COMPANY_ID)
    seen: list[str] = []
    bind = db.get_bind()

    def record(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement.lower())

    event.listen(bind, "before_cursor_execute", record)
    try:
        # Recorder self-check: a business read IS caught, so an empty result below means something.
        db.execute(text("select 1 from billing_documents limit 1"))
        assert any("billing_documents" in s for s in seen)
        seen.clear()
        with _client(db, principal, allow=(SLUG,)) as client:
            ok = client.get(URL)
            wall = client.get(URL, params={"mode": "wallboard"})
        assert ok.status_code == 200 and wall.status_code == 200
        assert "today" in ok.json(), "must be the stored snapshot, not a pending placeholder"
    finally:
        event.remove(bind, "before_cursor_execute", record)
    pattern = re.compile(r"\b(" + "|".join(BUSINESS_TABLES) + r")\b")
    offenders = [s for s in seen if pattern.search(s)]
    assert offenders == [], offenders


# --------------------------------------------------------------------------- AC-3


def test_ac3_user_without_sales_reports_view_gets_counts_and_no_amount_in_the_body(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=()) as client:
        r = client.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert not (all_keys(body) & AMOUNT_KEYS)
    for figure in FAKE_RM_FIGURES:
        assert figure not in r.text
    assert body["today"]["invoice_count"] == 321
    assert body["shops"][0]["today_docs"] == 3


def test_a_redacted_shop_list_is_not_in_ranking_order(db):
    from app.services.queue_service import redis_conn
    from app.services.town.snapshot import store

    full = fake_full(_today(), DEFAULT_COMPANY_ID)
    full["shops"] = [
        {"key": f"ZZT-key-{i}", "code": f"C{i}", "name": f"N{i}", "account_label": f"L{i}", "kind": "shop",
         "rank": i, "ninety_day_amount": "1.00", "today_amount": "1.00", "today_docs": 1}
        for i in range(1, 9)
    ]
    store(redis_conn, DEFAULT_COMPANY_ID, _today(), full)
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=()) as client:
        first = [s["account_label"] for s in client.get(URL).json()["shops"]]
        again = [s["account_label"] for s in client.get(URL).json()["shops"]]
    assert first == again  # stable across refreshes
    assert first != [f"L{i}" for i in range(1, 9)]  # but not the ranking
    assert sorted(first) == sorted(f"L{i}" for i in range(1, 9))


def test_ac3_redacted_body_has_no_dealer_identity_ranking_or_customer_id(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=()) as client:
        r = client.get(URL)
    body = r.json()
    for shop in body["shops"]:
        assert not ({"name", "code", "rank"} & set(shop))
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", r.text.replace(DEFAULT_COMPANY_ID, ""))
    for text in ("ZZT Tiling One", "ZZT-S001", "ZZT Stall Three"):
        assert text not in r.text


def test_ac3_sales_reports_view_holder_gets_amounts(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:
        r = client.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["today"]["amount"] == "512345.60"
    assert body["shops"][0]["today_amount"] == "20111.40"
    assert body["shops"][0]["ninety_day_amount"] == "123456.78"


@pytest.mark.parametrize("role", ["admin", "superadmin"])
def test_ac3_admin_and_superadmin_get_amounts_without_the_slug(db, stored, role):
    principal = _user(db, DEFAULT_COMPANY_ID)
    _with_role(db, principal, role)
    with _real_rbac_client(db, principal) as client:
        r = client.get(URL)
    assert r.status_code == 200
    assert r.json()["today"]["amount"] == "512345.60"


def test_ac3_a_signed_in_user_with_no_role_at_all_is_refused(db, stored):
    principal = _plain_user(db, DEFAULT_COMPANY_ID)
    with _real_rbac_client(db, principal) as client:
        r = client.get(URL)
    assert r.status_code == 403


def test_a_portal_contact_session_is_refused(db, stored):
    principal = _plain_user(db, DEFAULT_COMPANY_ID)
    _with_role(db, principal, "portal_user")
    with _real_rbac_client(db, principal) as client:
        r = client.get(URL)
    assert r.status_code == 403


def test_a_salesperson_only_session_is_refused(db, stored):
    from app.models.access import RespondContact

    contact = RespondContact(id=str(uuid.uuid4()), phone_number=f"+0{uuid.uuid4().int % 10**10}")
    db.add(contact)
    db.flush()
    principal = _plain_user(db, DEFAULT_COMPANY_ID)
    db.query(User).filter(User.id == principal["id"]).update({"respond_contact_id": contact.id})
    _with_role(db, principal, "salesperson")
    _with_role(db, principal, "portal_user")
    with _real_rbac_client(db, principal) as client:
        r = client.get(URL)
    assert r.status_code == 403


# --------------------------------------------------------------------------- AC-4


def test_ac4_wallboard_mode_has_no_name_or_code(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:
        r = client.get(URL, params={"mode": "wallboard"})
        personal = client.get(URL)
    assert r.status_code == 200
    body = r.json()
    for shop in body["shops"]:
        assert "name" not in shop and "code" not in shop
        assert {"rank", "kind", "account_label", "today_docs"} <= set(shop)
    for text in ("ZZT Tiling One", "ZZT-S001", "ZZT Stall Three"):
        assert text not in r.text
    assert body["today"]["amount"] == "512345.60"  # wallboard strips names only; amounts follow the holder
    assert "name" in personal.json()["shops"][0]  # the signed-in personal view keeps names


def test_ac4_wallboard_for_a_non_holder_has_neither_names_nor_amounts(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=()) as client:
        r = client.get(URL, params={"mode": "wallboard"})
    body = r.json()
    assert not (all_keys(body) & (AMOUNT_KEYS | {"name", "code"}))


# --------------------------------------------------------------------------- headers, ETag, pending


def test_response_is_the_stored_gzip_with_contract_headers_and_an_etag(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:
        r = client.get(URL)
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["cache-control"].replace(" ", "") == "private,no-cache"
    assert r.headers["etag"] == f'"{stored}-full"'


def test_etag_differs_by_variant_and_wallboard(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:
        full = client.get(URL).headers["etag"]
        full_wb = client.get(URL, params={"mode": "wallboard"}).headers["etag"]
    with _client(db, principal, allow=()) as client:
        red = client.get(URL).headers["etag"]
        red_wb = client.get(URL, params={"mode": "wallboard"}).headers["etag"]
    assert full == f'"{stored}-full"'
    assert full_wb == f'"{stored}-full-wb"'
    assert red == f'"{stored}-redacted"'
    assert red_wb == f'"{stored}-redacted-wb"'
    assert len({full, full_wb, red, red_wb}) == 4


def test_same_if_none_match_answers_304_with_an_empty_body(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:
        etag = client.get(URL).headers["etag"]
        again = client.get(URL, headers={"If-None-Match": etag})
        other_variant = client.get(URL, params={"mode": "wallboard"}, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert other_variant.status_code == 200  # the full ETag does not validate the wallboard body


def test_a_redacted_users_etag_does_not_validate_a_full_body(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=()) as client:
        red_etag = client.get(URL).headers["etag"]
    with _client(db, principal, allow=(SLUG,)) as client:
        r = client.get(URL, headers={"If-None-Match": red_etag})
    assert r.status_code == 200
    assert r.json()["today"]["amount"] == "512345.60"


def test_a_new_snapshot_version_is_a_new_etag_not_a_304(db, stored):
    from app.services.queue_service import redis_conn
    from app.services.town.snapshot import store

    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:
        old = client.get(URL).headers["etag"]
        changed = fake_full(_today(), DEFAULT_COMPANY_ID)
        changed["today"]["invoice_count"] = 238
        store(redis_conn, DEFAULT_COMPANY_ID, _today(), changed)
        r = client.get(URL, headers={"If-None-Match": old})
    assert r.status_code == 200
    assert r.json()["today"]["invoice_count"] == 238


def test_no_snapshot_stored_yet_answers_200_pending(db):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:
        r = client.get(URL)
    assert r.status_code == 200
    assert r.json() == {"pending": True}


# --------------------------------------------------------------------------- AC-10, auth


def _wait_for_a_fresh_minute():
    """The limiter is a per-epoch-minute counter; start early in a minute so 31 calls share one."""
    while time.time() % 60 > 45:
        time.sleep(1)


def test_ac10_the_31st_request_within_a_minute_is_429(db):
    from app.services.queue_service import redis_conn

    principal = _user(db, DEFAULT_COMPANY_ID)
    _wait_for_a_fresh_minute()
    with _client(db, principal, allow=(SLUG,)) as client:
        codes = [client.get(URL).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30
    assert codes[30] == 429
    keys = list(redis_conn.scan_iter(match=f"town:rl:{principal['id']}:*"))
    assert len(keys) == 1
    assert 0 < redis_conn.ttl(keys[0]) <= 120


def test_ac10_the_limit_is_per_user(db):
    first = _user(db, DEFAULT_COMPANY_ID)
    second = _user(db, DEFAULT_COMPANY_ID)
    _wait_for_a_fresh_minute()
    with _client(db, first, allow=(SLUG,)) as client:
        assert [client.get(URL).status_code for _ in range(31)][-1] == 429
    with _client(db, second, allow=(SLUG,)) as client:
        assert client.get(URL).status_code == 200


def test_unauthenticated_request_is_401():
    app.dependency_overrides.clear()
    r = TestClient(app).get(URL)
    assert r.status_code == 401


# --------------------------------------------------------------------------- isolation (route level)


def _bearer(user_id):
    """A token the real company scope resolver accepts (its JWT path)."""
    from jose import jwt

    from app.config import settings

    return {"Authorization": "Bearer " + jwt.encode({"sub": user_id}, settings.jwt_secret, algorithm=settings.jwt_algorithm)}


@contextmanager
def _resolver_client(db, principal, allow=(SLUG,)):
    """The real `apply_company_scope` (not overridden): the scope comes from the bearer's user grants."""
    from app.services.user_service import UserPermissionService

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    original = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in allow
    try:
        yield TestClient(app)
    finally:
        UserPermissionService.check_user_has_permission = original
        app.dependency_overrides.clear()


def test_a_user_granted_only_company_a_gets_a_and_never_b(db):
    from app.services.queue_service import redis_conn
    from app.services.town.snapshot import store
    from tests._mc_lookup_seed import MOCHA_ID, seed_mocha

    seed_mocha(db)
    principal = _user(db, MOCHA_ID)
    store(redis_conn, DEFAULT_COMPANY_ID, _today(), fake_full(_today(), DEFAULT_COMPANY_ID))
    store(redis_conn, MOCHA_ID, _today(), fake_full(_today(), MOCHA_ID))
    with _resolver_client(db, principal) as client:
        r = client.get(URL, headers=_bearer(principal["id"]))
    assert r.status_code == 200
    assert r.json()["company_id"] == MOCHA_ID
    assert DEFAULT_COMPANY_ID not in r.text


def test_a_user_with_no_company_grant_gets_400(db):
    principal = _user(db)
    with _resolver_client(db, principal) as client:
        r = client.get(URL, headers=_bearer(principal["id"]))
    assert r.status_code == 400


def test_an_api_key_alone_is_401(db, stored):
    app.dependency_overrides.clear()
    r = TestClient(app).get(URL, headers={"X-API-Key": "ZZT-not-a-session"})
    assert r.status_code == 401


def test_a_portal_token_is_401(db, stored):
    from datetime import timedelta

    from app.models.portal import PortalToken

    token = f"ZZT-{uuid.uuid4().hex}"
    db.add(PortalToken(id=str(uuid.uuid4()), token=token, contact_id=str(uuid.uuid4()),
                       space_id="ZZT-space", expires_at=datetime.utcnow() + timedelta(days=1)))
    db.flush()
    with _resolver_client(db, None) as client:
        app.dependency_overrides.pop(get_current_user, None)
        r = client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_a_staff_session_with_the_shared_key_header_is_refused(db, stored):
    principal = _user(db, DEFAULT_COMPANY_ID)
    with _client(db, principal, allow=(SLUG,)) as client:
        r = client.get(URL, headers={"X-API-Key": "ZZT-anything"})
    assert r.status_code == 400
