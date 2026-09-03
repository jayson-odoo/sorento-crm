"""GET /api/v1/procurement/suppliers/select - AC-D2 / AC-D5 (S4, PLAN-scm-pi-packing-list-feedback-3sep.md).

Three consumers share this feed (`getFulfilmentSuppliers` on the frontend): the PI upload
dialog, the loading plan container dialog, and the PI list filter. Before this slice it was
unordered, unpaged (`LIMIT 100`) and labelled by name only - two suppliers sharing a name
were indistinguishable, and a tenant with hundreds of suppliers could never reach the rest.

Ordered by `supplier_name, supplier_code` so a name collision still sorts deterministically
and the code (rendered by the FE as `<code> - <name>`) tells the rows apart. `page` is
OPTIONAL: passed, the endpoint pages (`limit`, default 50, max 100) and returns
`{items, has_more}`; omitted, it returns the legacy bare array (capped at 100) so any other
caller of this endpoint keeps working unchanged.

Postgres only, on a blank schema (empty - no real supplier rows to filter around).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_or_api_key
from app.main import app
from app.models.base import company_scope
from app.models.procurement import Supplier
from app.services.company_scope_resolver import apply_company_scope

from ._pg_fixture import blank_session

MARKER = "ZZT-SUP-SELECT"
URL = "/api/v1/procurement/suppliers/select"


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _supplier(db, company_id, code, name, *, is_active=True):
    row = Supplier(
        company_id=company_id,
        supplier_code=code,
        supplier_name=name,
        is_active=is_active,
    )
    db.add(row)
    return row


def _client(db) -> TestClient:
    actor = {"id": "zzt-user", "email": "zzt-sup-select@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    return TestClient(app)


@pytest.fixture
def seeded():
    """Three suppliers: a name collision (tie broken by code) plus one alphabetically
    first, so ordering has something to prove."""
    with blank_session() as db:
        company_id = _sorento(db)
        _supplier(db, company_id, f"{MARKER}-B2", "Zenith Factory")
        _supplier(db, company_id, f"{MARKER}-B1", "Zenith Factory")  # same name, lower code
        _supplier(db, company_id, f"{MARKER}-A1", "Ace Factory")
        db.flush()
        db.commit()
        client = _client(db)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client
        finally:
            app.dependency_overrides.clear()


def test_ordered_by_name_then_code(seeded):
    """AC-D2: `supplier_name, supplier_code` - the alphabetically-first name leads, and the
    two "Zenith Factory" rows tie-break on their code."""
    resp = seeded.get(URL, params={"query": MARKER})
    assert resp.status_code == 200
    codes = [row["supplier_code"] for row in resp.json()]
    assert codes == [f"{MARKER}-A1", f"{MARKER}-B1", f"{MARKER}-B2"]


def test_bare_array_when_page_omitted(seeded):
    """Backward compatible: no `page` -> the legacy bare array, not `{items, has_more}`."""
    resp = seeded.get(URL, params={"query": MARKER})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 3


def test_paged_shape_and_has_more(seeded):
    """AC-D2/AC-D5: `page` passed -> `{items, has_more}`; page 1 of limit=2 has more, page 2
    (the remainder) does not."""
    page1 = seeded.get(URL, params={"query": MARKER, "page": 1, "limit": 2})
    assert page1.status_code == 200
    body1 = page1.json()
    assert isinstance(body1, dict)
    assert len(body1["items"]) == 2
    assert body1["has_more"] is True
    assert [r["supplier_code"] for r in body1["items"]] == [f"{MARKER}-A1", f"{MARKER}-B1"]

    page2 = seeded.get(URL, params={"query": MARKER, "page": 2, "limit": 2})
    body2 = page2.json()
    assert len(body2["items"]) == 1
    assert body2["has_more"] is False
    assert body2["items"][0]["supplier_code"] == f"{MARKER}-B2"


def test_limit_default_and_cap(seeded):
    """`limit` defaults to 50 and is capped at 100 (422 past it)."""
    resp = seeded.get(URL, params={"query": MARKER, "page": 1})
    assert resp.status_code == 200
    assert resp.json()["has_more"] is False  # only 3 rows, well under the default 50

    over_cap = seeded.get(URL, params={"query": MARKER, "page": 1, "limit": 101})
    assert over_cap.status_code == 422


def test_inactive_supplier_excluded():
    """Unchanged from before this slice: only active suppliers are offered."""
    with blank_session() as db:
        company_id = _sorento(db)
        _supplier(db, company_id, f"{MARKER}-ACT", "Active Factory", is_active=True)
        _supplier(db, company_id, f"{MARKER}-OFF", "Retired Factory", is_active=False)
        db.flush()
        db.commit()
        client = _client(db)
        try:
            with company_scope(db, frozenset({company_id})):
                resp = client.get(URL, params={"query": MARKER})
                assert resp.status_code == 200
                codes = [row["supplier_code"] for row in resp.json()]
                assert codes == [f"{MARKER}-ACT"]
        finally:
            app.dependency_overrides.clear()
