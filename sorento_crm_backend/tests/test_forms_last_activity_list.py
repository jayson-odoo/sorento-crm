"""FORMS-LAST-ACTIVITY Phase 2 red tests: list sort / filter / default / payload (U7-U12).

Six lists are driven over HTTP (dependency overrides, real routes and response models); workflow
submissions are driven at service level because their list route takes no sort or filter params
(the grid uses list-query). Rows are seeded with stamps OUT of created order, then the baseline
stamp is written through ``set_stamp``.

ASSUMPTION pinned by U8: stamps are naive UTC (same clock as audit_logs.changed_at) and the
from/to days are Malaysia (UTC+8) calendar days, inclusive.

Run: SORENTO_ENV_FILE=.env.ci-tests venv/bin/pytest tests/test_forms_last_activity_list.py -q
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests._last_activity_support import BY_KEY, FORMS, IDS, SORENTO, at, seed_user, set_stamp
from tests._pg_fixture import blank_session

HTTP_FORMS = [f for f in FORMS if f.url]
HTTP_IDS = [f.key for f in HTTP_FORMS]


@pytest.fixture
def db():
    from app.models.base import set_company_scope

    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


@pytest.fixture
def client(db, monkeypatch):
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.user_service import UserPermissionService

    user = seed_user(db, "Lister")
    actor = {"id": user.id, "email": user.email, "role": "staff"}
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"superadmin"})
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_permission_slugs",
        lambda self, uid: {
            "projects.sample_requests.view",
            "procurement.new_product_applications.view",
            "procurement.stock_inquiries.view",
            "procurement.purchase_requests.view",
            "procurement.sponsorship_forms.view",
            "complaint_management.complaints.view",
            "dealer_kit.price_tag_requests.view",
        },
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    async def _scope():
        set_company_scope(db, frozenset({SORENTO}))
        return frozenset({SORENTO})

    app.dependency_overrides[apply_company_scope] = _scope
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_current_user_or_api_key] = lambda: actor
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _seed_out_of_order(db, form):
    """Three rows: created a,b,c (oldest first) but stamped 2nd, 3rd, 1st."""
    rows = [form.seed(db, created_at=at(days=i)) for i in range(3)]
    stamps = [at(days=20), at(days=30), at(days=10)]
    for r, s in zip(rows, stamps):
        set_stamp(db, r, s)
    return rows  # rows[1] newest stamp, rows[0] middle, rows[2] oldest


def _ids(client, form, **params):
    if form.key == "sample_request":
        params.setdefault("status", "")  # an empty status param lists every status, not only the open set
    resp = client.get(form.url, params=params)
    assert resp.status_code == 200, resp.text
    return [str(r["id"]) for r in resp.json()[form.rows_key]], resp.json()


# --------------------------------------------------------------------------- U7 sort
@pytest.mark.parametrize("form", HTTP_FORMS, ids=HTTP_IDS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_u7_sorts_by_the_stored_last_activity_column(db, client, form, direction):
    rows = _seed_out_of_order(db, form)
    ids, _ = _ids(client, form, sort="last_activity_at", dir=direction)
    mine = [str(r.id) for r in (rows[2], rows[0], rows[1])]  # oldest stamp first
    ordered = [i for i in ids if i in mine]
    assert ordered == (mine if direction == "asc" else list(reversed(mine)))


@pytest.mark.parametrize("key", ["purchase_request", "stock_inquiry"])
def test_u7_ties_break_by_created_at_desc_and_page_two_continues_page_one(db, client, key):
    form = BY_KEY[key]
    same, other = at(days=40), at(days=5)
    rows = [form.seed(db, created_at=at(days=i)) for i in range(5)]
    for r, s in zip(rows, [same, same, same, other, at(days=50)]):
        set_stamp(db, r, s)
    expected = [str(rows[4].id)] + [str(rows[2].id), str(rows[1].id), str(rows[0].id)] + [str(rows[3].id)]
    full, _ = _ids(client, form, sort="last_activity_at", dir="desc", limit=50)
    assert full == expected, "ties on the stamp fall back to created_at desc"
    paged = []
    for page in (1, 2, 3):
        got, _ = _ids(client, form, sort="last_activity_at", dir="desc", limit=2, page=page)
        paged += got
    assert paged == expected, "pages must neither repeat nor skip a row"


# --------------------------------------------------------------------------- U9 default
@pytest.mark.parametrize("form", HTTP_FORMS, ids=HTTP_IDS)
def test_u9_default_sort_is_last_activity_desc(db, client, form):
    rows = _seed_out_of_order(db, form)
    ids, _ = _ids(client, form)
    expected = [str(rows[1].id), str(rows[0].id), str(rows[2].id)]
    assert [i for i in ids if i in expected] == expected


# --------------------------------------------------------------------------- U8 range filter
@pytest.mark.parametrize("form", HTTP_FORMS, ids=HTTP_IDS)
def test_u8_from_to_are_inclusive_malaysia_days(db, client, form):
    from datetime import datetime

    cases = {
        "before": datetime(2026, 3, 10, 15, 59),   # 10 Mar 23:59 MYT
        "first": datetime(2026, 3, 10, 16, 0),     # 11 Mar 00:00 MYT
        "last": datetime(2026, 3, 12, 15, 59),     # 12 Mar 23:59 MYT
        "after": datetime(2026, 3, 12, 16, 0),     # 13 Mar 00:00 MYT
    }
    seeded = {}
    for name, stamp in cases.items():
        seeded[name] = form.seed(db, created_at=at(days=-30))
        set_stamp(db, seeded[name], stamp)
    ids, _ = _ids(client, form, last_activity_from="2026-03-11", last_activity_to="2026-03-12")
    mine = {str(r.id): n for n, r in seeded.items()}
    assert sorted(mine[i] for i in ids if i in mine) == ["first", "last"]
    only_from, _ = _ids(client, form, last_activity_from="2026-03-12")
    assert sorted(mine[i] for i in only_from if i in mine) == ["after", "last"]


# --------------------------------------------------------------------------- U10 payload
@pytest.mark.parametrize("form", HTTP_FORMS, ids=HTTP_IDS)
def test_u10_each_row_returns_last_activity_at(db, client, form):
    row = form.seed(db)
    set_stamp(db, row, at(days=9))
    _, body = _ids(client, form)
    mine = next(r for r in body[form.rows_key] if str(r["id"]) == str(row.id))
    assert "last_activity_at" in mine, "response_model must declare last_activity_at"
    assert str(mine["last_activity_at"]).startswith("2026-03-10")


@pytest.mark.parametrize(
    "module, name",
    [
        ("app.schemas.complaints", "ComplaintResponse"),
        ("app.schemas.procurement", "PurchaseRequestHeaderListResponse"),
        ("app.schemas.procurement", "StockInquiryResponse"),
        ("app.api.v1.dealer_kit.price_tag_requests", "PriceTagRequestListItem"),
        ("app.schemas.workflow_forms", "WorkflowSubmissionOut"),
    ],
)
def test_u10_response_models_declare_the_field(module, name):
    import importlib

    model = getattr(importlib.import_module(module), name)
    assert "last_activity_at" in model.model_fields


# --------------------------------------------------------------------------- U11 stock inquiry
def test_u11_stock_inquiry_sorts_by_the_stored_column_not_coalesce(db, client):
    form = BY_KEY["stock_inquiry"]
    x = form.seed(db, created_at=at(days=-60), last_revised_at=at(days=4))   # coalesce = 5 Mar
    y = form.seed(db, created_at=at(days=90))                                   # coalesce = created
    set_stamp(db, x, at(days=200))  # stored: x is the newest
    set_stamp(db, y, at(days=100))
    ids, _ = _ids(client, form, sort="last_activity_at", dir="asc")
    mine = [i for i in ids if i in (str(x.id), str(y.id))]
    assert mine == [str(y.id), str(x.id)]  # coalesce(last_revised_at, created_at) would give x, y


# --------------------------------------------------------------------------- U12 workflow
def test_u12_workflow_submissions_sort_filter_default_and_payload(db):
    from app.services.workflow_forms_service import WorkflowFormsService

    form = BY_KEY["workflow_submission"]
    rows = _seed_out_of_order(db, form)
    svc = WorkflowFormsService(db)
    default = svc.list_submissions(limit=50)["data"]
    expected = [str(rows[1].id), str(rows[0].id), str(rows[2].id)]
    assert [str(r["id"]) for r in default if str(r["id"]) in expected] == expected, "default is last activity desc"
    assert "last_activity_at" in default[0] and "updated_at" in default[0]
    asc = svc.list_submissions(limit=50, sort_field="last_activity_at", sort_dir="asc")["data"]
    assert [str(r["id"]) for r in asc if str(r["id"]) in expected] == list(reversed(expected))
    ranged = svc.list_submissions(limit=50, last_activity_from="2026-03-20", last_activity_to="2026-03-21")["data"]
    assert [str(r["id"]) for r in ranged if str(r["id"]) in expected] == [str(rows[0].id)]
