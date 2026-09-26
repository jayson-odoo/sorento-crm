"""Lane C, PLAN-order-sheet-oi-reports-22sep.md (AC-C1/AC-C2/AC-C6): the plan view's THIRD
export - "OI worksheet Excel" - goes through the SAME `POST /api/v1/scm/order-summary/export`
route the order sheet and the low stock report already use, with a new `format` value
(`oi_worksheet`). Modelled line-for-line on `test_order_sheet_export_downloads.py`'s own
route coverage - same in-flight guard, same stale sweep, same enqueue-failure->failed+503,
same API-key rejection - because the contract SAYS this is the existing pipeline gaining a
third `kind`, not a new one.

Every case posts `format: "oi_worksheet"`; today the route's own format guard
(`fmt not in ("pdf", "xlsx", LOW_STOCK_FORMAT)`) refuses it with 422 before anything else
runs, so every case here is red for THAT reason - not a fixture bug - until the coder adds
the new format branch.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.scm.conftest import SORENTO_COMPANY_ID, as_user, requires_pg, seed_user
from tests.scm.test_m3_run import _client
from tests.scm.test_order_sheet_export_downloads import _seed_run

pytestmark = requires_pg

MARKER = "ZZTOIWS"


def _u() -> str:
    return str(uuid.uuid4())


def _grant_permission(db, user_id: str, permission_slug: str) -> None:
    """Grants `permission_slug` to `user_id` through a throwaway role, so a test can hold
    a permission the seeded role (e.g. "purchasing") does not carry, without mutating that
    shared role for every other test in the suite."""
    from app.models.user import UserRole, UserRoleAssignment, UserRolePermission

    perm_id = db.execute(text(
        "SELECT id FROM user_permissions WHERE slug = :s"
    ), {"s": permission_slug}).scalar()
    assert perm_id, f"permission {permission_slug} not seeded"
    role_id = _u()
    db.add(UserRole(id=role_id, slug=f"{MARKER}-grant-{role_id[:8]}",
                    name=f"{MARKER} grant {role_id[:8]}"))
    db.flush()
    db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
    db.add(UserRolePermission(role_id=role_id, permission_id=perm_id))
    db.flush()


#: Fix round 1 (security review): `oi_worksheet` additionally requires the OI worklist's
#: own view permission - see `app/api/v1/projects/order_inquiries.py`'s `VIEW` constant.
OI_WORKLIST_VIEW = "projects.projects.view"


def _client_with_oi_view(scm_app):
    """Purchasing PLUS the OI worklist's own view permission - what every case below that
    exercises the `oi_worksheet` format needs now that it is gated on both. The seeded
    "purchasing" role does NOT carry `projects.projects.view` (measured against the test
    database), so every pre-existing case in this file needs the grant to keep exercising
    the route the way it did before that gate landed."""
    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, "purchasing")
    _grant_permission(db, uid, OI_WORKLIST_VIEW)
    as_user(app, gcu, gcuak, uid)
    return app, db


# =========================================================================== #
# AC-C1/AC-C2: the POST route accepts the new format
# =========================================================================== #

def test_c1_export_post_creates_download_row_and_enqueues_the_worksheet_task(
    scm_app, monkeypatch,
):
    from app.services import queue_service

    app, db = _client_with_oi_view(scm_app)
    run_id = _seed_run(db)
    db.flush()

    calls: list[dict] = []

    def _fake_enqueue(func, *args, **kwargs):
        calls.append({"func": func, "args": args, "kwargs": kwargs})
        return type("J", (), {"id": "fake-job-id"})()

    monkeypatch.setattr(queue_service, "enqueue_job", _fake_enqueue)

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending", body
    assert body["kind"] == "oi_worksheet_xlsx", body

    row = db.execute(text(
        "SELECT kind, source_entity_type, source_entity_id::text AS source_entity_id, "
        "       filename, status, user_id "
        "FROM user_downloads WHERE id = :id"
    ), {"id": body["id"]}).mappings().first()
    assert row is not None, "no user_downloads row was created"
    assert row["kind"] == "oi_worksheet_xlsx"
    assert row["source_entity_type"] == "reorder_run"
    assert row["source_entity_id"] == run_id
    assert row["filename"], "no filename was stamped"
    assert row["filename"].startswith("oi-worksheet-"), row["filename"]
    assert row["filename"].endswith(".xlsx"), row["filename"]

    assert len(calls) == 1, f"expected exactly one enqueue, got {calls}"
    call = calls[0]
    assert call["func"].__name__ == "generate_oi_worksheet", call["func"]
    assert call["args"] == (body["id"], run_id, row["user_id"]), call["args"]
    assert call["kwargs"] == {"queue_name": "imports", "job_timeout": 600}, call["kwargs"]


def test_c1_export_post_answers_409_while_a_worksheet_is_in_flight(scm_app, monkeypatch):
    """AC-C1/AC-16b's own pattern: a second click while one worksheet render is queued
    starts nothing, and the toast names both the report and My Downloads."""
    from app.services import queue_service

    app, db = _client_with_oi_view(scm_app)
    run_id = _seed_run(db)
    db.flush()

    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        first = c.post("/api/v1/scm/order-summary/export",
                       json={"run_id": run_id, "format": "oi_worksheet"})
        assert first.status_code == 200, first.text

        second = c.post("/api/v1/scm/order-summary/export",
                        json={"run_id": run_id, "format": "oi_worksheet"})

    assert second.status_code == 409, second.text
    assert "OI worksheet" in second.text, second.text
    assert "My Downloads" in second.text, second.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads "
        "WHERE source_entity_id = :r AND kind = 'oi_worksheet_xlsx'"
    ), {"r": run_id}).scalar()
    assert count == 1, f"a second in-flight request let a second row through: {count}"


def test_c1_export_post_marks_failed_and_503_when_enqueue_raises(scm_app, monkeypatch):
    from app.services import queue_service

    app, db = _client_with_oi_view(scm_app)
    run_id = _seed_run(db)
    db.flush()

    def _boom(*a, **k):
        raise RuntimeError("redis is away")

    monkeypatch.setattr(queue_service, "enqueue_job", _boom)

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 503, resp.text
    row = db.execute(text(
        "SELECT status, error FROM user_downloads WHERE source_entity_id = :r "
        "AND kind = 'oi_worksheet_xlsx'"
    ), {"r": run_id}).mappings().first()
    assert row is not None, "no download row was created before the enqueue attempt"
    assert row["status"] == "failed", row["status"]
    assert row["error"], "no error message was recorded"


def test_c1_export_post_rejects_api_key_only_principal(scm_app):
    from app.models.integration import Integration, IntegrationApiKey  # noqa: F401
    from app.models.user import User, UserRoleAssignment
    from app.services.integration_key_service import IntegrationKeyService

    app, db, _gcu, _gcuak = scm_app
    run_id = _seed_run(db)

    user = User(email=f"{_u()}@integrations.local", name="ZZTOIWS integration",
               status="ACTIVE", is_integration=True)
    db.add(user)
    db.flush()
    role_id = db.execute(text(
        "SELECT id FROM user_roles WHERE slug = 'purchasing'"
    )).scalar()
    assert role_id, "role 'purchasing' not seeded"
    db.add(UserRoleAssignment(user_id=user.id, role_id=role_id))
    integration = Integration(name=f"ZZTOIWS-{_u()[:8]}", type="autocount_esb",
                              act_as_user_id=user.id, is_active=True)
    db.add(integration)
    db.flush()
    key = IntegrationKeyService(db).issue_key(integration)
    db.flush()

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      headers={"X-API-Key": key},
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code in (401, 403), resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE source_entity_id = :r"
    ), {"r": run_id}).scalar()
    assert count == 0, "an API-key-only caller was allowed to create a download row"


def test_c1_export_in_flight_guard_sweeps_a_stale_row_first(scm_app, monkeypatch):
    from app.services import queue_service
    from app.services.download_service import DownloadService, _STALE_AFTER

    app, db, gcu, gcuak = scm_app
    uid = seed_user(db, "purchasing")
    _grant_permission(db, uid, OI_WORKLIST_VIEW)
    as_user(app, gcu, gcuak, uid)
    run_id = _seed_run(db)
    db.flush()

    stale = DownloadService(db).create(
        user_id=uid, kind="oi_worksheet_xlsx", source_entity_type="reorder_run",
        source_entity_id=run_id, filename="oi-worksheet-stale.xlsx",
    )
    old_created_at = (
        datetime.now(timezone.utc).replace(tzinfo=None) - _STALE_AFTER - timedelta(minutes=5)
    )
    db.execute(text(
        "UPDATE user_downloads SET created_at = :ts WHERE id = :id"
    ), {"ts": old_created_at, "id": str(stale.id)})
    db.flush()

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 200, (
        f"a stale pending row must not block a fresh export: {resp.text}"
    )
    stale_row = db.execute(text(
        "SELECT status FROM user_downloads WHERE id = :id"
    ), {"id": str(stale.id)}).mappings().first()
    assert stale_row["status"] == "failed", (
        f"the stale row must be swept to failed, not left pending: {stale_row['status']}"
    )


# =========================================================================== #
# AC-C6: the cap
# =========================================================================== #

def test_c6_the_order_sheets_2000_row_cap_does_not_apply_to_the_worksheet(
    scm_app, monkeypatch,
):
    """The worksheet's row set is OI rows, not order-sheet rows - the contract is
    explicit that it must NOT reuse `summary_order_service.MAX_EXPORT_ROWS` (2000). A run
    with 2,001 frozen `scm.order_summary_row` rows (which the order sheet's OWN format
    would refuse, `test_export_refuses_above_2000_rows_to_order`) but no OI rows at all
    must still queue a worksheet successfully."""
    from app.services import queue_service
    from tests.scm.conftest import SORENTO_COMPANY_ID

    app, db_ = _client_with_oi_view(scm_app)
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    marker = f"ZZTOIWSCAP{_u()[:6]}"
    cat_id = db_.execute(text(
        "INSERT INTO product_categories (id, category_code, category_name) "
        "VALUES (gen_random_uuid(), :c, :c) RETURNING id"
    ), {"c": marker}).scalar()
    uom_id = db_.execute(text(
        "INSERT INTO units_of_measure (id, uom_code, uom_name) "
        "VALUES (gen_random_uuid(), :c, :c) RETURNING id"
    ), {"c": marker[:20]}).scalar()
    run_id = db_.execute(text(
        "INSERT INTO scm.reorder_run (id, status, include_market, company_id, created_at) "
        "VALUES (gen_random_uuid(), 'completed', false, :co, now()) RETURNING id"
    ), {"co": SORENTO_COMPANY_ID}).scalar()
    db_.execute(text("""
        INSERT INTO products (id, product_code, product_name, category_id, base_uom_id,
                              list_price, company_id)
        SELECT gen_random_uuid(), :marker || '-' || s, :marker || ' ' || s, :cat, :uom, 0, :co
        FROM generate_series(1, 2001) AS s
    """), {"marker": marker, "cat": cat_id, "uom": uom_id, "co": SORENTO_COMPANY_ID})
    db_.execute(text("""
        INSERT INTO scm.order_summary_row (
            id, run_id, product_id, as_of, on_hand, project_demand, dealer_outstanding,
            qty_on_order, qty_in_transit, shortfall, suggested_qty, chosen_qty,
            project_demand_line_count, dealer_outstanding_line_count, computed_at,
            company_id
        )
        SELECT gen_random_uuid(), :run, p.id, CURRENT_DATE, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, now(),
               :co
        FROM products p WHERE p.product_code LIKE :like
    """), {"run": run_id, "like": f"{marker}-%", "co": SORENTO_COMPANY_ID})
    db_.commit()

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export", json={
            "run_id": str(run_id), "format": "oi_worksheet",
        })

    assert resp.status_code == 200, (
        "the worksheet must not inherit the order sheet's 2,000-row cap: " + resp.text
    )


def test_c6_refuses_above_the_worksheets_own_row_cap_before_creating_a_download_row(
    scm_app, monkeypatch,
):
    """AC-C6: 'the cap follows the worklist export's own cap ... refuses with "Narrow the
    plan first" before creating a download row'. No such cap exists in
    `order_inquiry_worklist_service` today (greped, none found) - the coder's own number to
    pick. This proves the QUALITATIVE behaviour without pinning that number: patched at
    `app.services.scm.demand.run_scope_oi_rows`'s own source, matching this module's
    established house style of resolving `enqueue_job` (and the task functions) via a
    function-local import specifically so a test CAN patch the source (see
    `test_order_sheet_export_downloads.py`'s own comment on that pattern) - 50,000 rows is
    unambiguously too many for any xlsx cap a person would pick.

    ASSUMPTION flagged to the coder/captain: if the route instead counts the worksheet's
    rows through a different query (e.g. a `COUNT` inside
    `order_inquiry_worklist_service` rather than calling `run_scope_oi_rows` a second
    time), this patch target needs to move to match - the qualitative assertions below
    (422, the refusal text, no row created) stay right either way.
    """
    from app.services import queue_service
    from app.services.scm import demand

    app, db = _client_with_oi_view(scm_app)
    run_id = _seed_run(db)
    db.flush()

    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not enqueue on a guard failure")))
    monkeypatch.setattr(
        demand, "run_scope_oi_rows",
        lambda *a, **k: [
            {"row_id": str(_u()), "product_id": str(_u()), "so_number": None, "qty": 1,
             "delivery_date": None, "customer_name": None, "project_title": None,
             "project_label": None}
            for _ in range(50_000)
        ],
    )

    before = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 422, resp.text
    assert "Narrow the plan first" in resp.text, resp.text
    after = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()
    assert after == before, "a guard failure left a download row behind"


# =========================================================================== #
# Fix round 1 (security review): `product_ids` reaches `run_scope_oi_rows`
# UNCHANGED - `run.product_ids or None` widened a scope that resolved to nothing
# (`[]`) into "no filter" (every product).
# =========================================================================== #

def test_fr1_product_ids_empty_list_reaches_run_scope_oi_rows_as_empty_not_none(
    scm_app, monkeypatch,
):
    from app.services import queue_service
    from app.services.scm import demand

    app, db = _client_with_oi_view(scm_app)
    run_id = _seed_run(db, product_ids=[])
    db.flush()

    calls: list = []
    real = demand.run_scope_oi_rows

    def _spy(db_, product_ids, **kw):
        calls.append(product_ids)
        return real(db_, product_ids, **kw)

    monkeypatch.setattr(demand, "run_scope_oi_rows", _spy)
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 200, resp.text
    assert calls == [[]], (
        f"product_ids=[] must reach run_scope_oi_rows as [], never widened to None "
        f"('every product'): {calls}"
    )


def test_fr1_product_ids_null_reaches_run_scope_oi_rows_as_none(scm_app, monkeypatch):
    from app.services import queue_service
    from app.services.scm import demand

    app, db = _client_with_oi_view(scm_app)
    run_id = _seed_run(db)  # product_ids left NULL - "no scope was asked for"
    db.flush()

    calls: list = []
    real = demand.run_scope_oi_rows

    def _spy(db_, product_ids, **kw):
        calls.append(product_ids)
        return real(db_, product_ids, **kw)

    monkeypatch.setattr(demand, "run_scope_oi_rows", _spy)
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 200, resp.text
    assert calls == [None], f"product_ids=NULL must reach run_scope_oi_rows as None: {calls}"


# =========================================================================== #
# Fix round 1 (security review): the OI worklist's own view permission is
# required for this format, on top of `scm.dashboard.view`.
# =========================================================================== #

def test_fr1_dashboard_only_permission_403s_for_oi_worksheet_but_order_sheet_still_works(
    scm_app, monkeypatch,
):
    from app.services import queue_service

    app, db = _client(scm_app, "purchasing")  # scm.dashboard.view only, no OI grant
    run_id = _seed_run(db)
    db.flush()
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        worksheet_resp = c.post("/api/v1/scm/order-summary/export",
                                json={"run_id": run_id, "format": "oi_worksheet"})
        order_sheet_resp = c.post("/api/v1/scm/order-summary/export",
                                  json={"run_id": run_id, "format": "xlsx"})

    assert worksheet_resp.status_code == 403, worksheet_resp.text
    assert order_sheet_resp.status_code == 200, order_sheet_resp.text
    count = db.execute(text(
        "SELECT count(*) FROM user_downloads WHERE source_entity_id = :r "
        "AND kind = 'oi_worksheet_xlsx'"
    ), {"r": run_id}).scalar()
    assert count == 0, "a caller without the OI view permission got a worksheet download row"


def test_fr1_both_permissions_grant_200_for_oi_worksheet(scm_app, monkeypatch):
    from app.services import queue_service

    app, db = _client_with_oi_view(scm_app)  # scm.dashboard.view + projects.projects.view
    run_id = _seed_run(db)
    db.flush()
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 200, resp.text


# =========================================================================== #
# Fix round 1 (security review): cross-company.
# =========================================================================== #

def test_fr1_a_company_bs_run_id_404s_before_any_download_row_is_created(
    scm_app, monkeypatch,
):
    from app.models.company import Company
    from app.services import queue_service

    app, db = _client_with_oi_view(scm_app)  # company A (SORENTO_COMPANY_ID)
    other_company_id = _u()
    db.add(Company(id=other_company_id, name=f"{MARKER}-other-{other_company_id[:8]}",
                   code=f"ZZTB{other_company_id[:6]}".upper(), is_active=True))
    db.flush()
    run_id = _seed_run(db, company_id=other_company_id)  # company B's run
    db.flush()

    monkeypatch.setattr(
        queue_service, "enqueue_job",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not enqueue")),
    )
    before = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 404, resp.text
    after = db.execute(text("SELECT count(*) FROM user_downloads")).scalar()
    assert after == before, "a cross-company run left a download row behind"


# =========================================================================== #
# Fix round 2, item 1: `so_numbers=[]` means "not narrowed" (Lane A fix round 4,
# `fix/order-sheet-cells`), matching `_planning_rows` - the same rule
# `product_ids` does NOT get (that one stays empty-means-nothing).
# =========================================================================== #

def test_fr2_so_numbers_empty_list_exports_every_in_window_row(scm_app, monkeypatch):
    from app.models.inventory import Warehouse
    from app.models.product import Product
    from app.services import queue_service
    from app.services.scm import demand
    from tests.scm.test_m3_run import _mk_product, _mk_warehouse
    from tests.scm.test_oi_worksheet_row_scope import _engine_row

    app, db = _client_with_oi_view(scm_app)
    marker = f"ZZTOIWSFR2A-{_u()[:8]}"
    pid = _mk_product(db, marker)
    wid = _mk_warehouse(db, marker)
    db.flush()
    product = db.get(Product, pid)
    wh = db.get(Warehouse, wid)
    leg = _engine_row(db, product=product, wh=wh, qty=7, delivery=date(2026, 10, 1))
    run_id = _seed_run(db, product_ids=[pid], so_numbers=[])
    db.flush()

    calls: list = []
    real = demand.run_scope_oi_rows

    def _spy(db_, product_ids, **kw):
        result = real(db_, product_ids, **kw)
        calls.append(result)
        return result

    monkeypatch.setattr(demand, "run_scope_oi_rows", _spy)
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 200, resp.text
    ids = {r["row_id"] for r in calls[0]}
    assert leg["row"].id in ids, (
        f"so_numbers=[] must not narrow to nothing - the run's in-window row is missing: "
        f"{calls}"
    )


def test_fr2_so_numbers_one_so_exports_only_that_sos_rows(scm_app, monkeypatch):
    from app.models.inventory import Warehouse
    from app.models.product import Product
    from app.services import queue_service
    from app.services.scm import demand
    from tests.scm.test_m3_run import _mk_product, _mk_warehouse
    from tests.scm.test_oi_worksheet_row_scope import _engine_row

    app, db = _client_with_oi_view(scm_app)
    marker = f"ZZTOIWSFR2B-{_u()[:8]}"
    pid = _mk_product(db, marker)
    wid = _mk_warehouse(db, marker)
    db.flush()
    product = db.get(Product, pid)
    wh = db.get(Warehouse, wid)
    picked_so = f"{marker}-SO-PICKED"
    other_so = f"{marker}-SO-OTHER"
    leg_picked = _engine_row(db, product=product, wh=wh, qty=7, delivery=date(2026, 10, 1),
                             so_number=picked_so)
    leg_other = _engine_row(db, product=product, wh=wh, qty=9, delivery=date(2026, 10, 1),
                            so_number=other_so)
    run_id = _seed_run(db, product_ids=[pid], so_numbers=[picked_so])
    db.flush()

    calls: list = []
    real = demand.run_scope_oi_rows

    def _spy(db_, product_ids, **kw):
        result = real(db_, product_ids, **kw)
        calls.append(result)
        return result

    monkeypatch.setattr(demand, "run_scope_oi_rows", _spy)
    monkeypatch.setattr(queue_service, "enqueue_job",
                        lambda *a, **k: type("J", (), {"id": "x"})())

    with TestClient(app) as c:
        resp = c.post("/api/v1/scm/order-summary/export",
                      json={"run_id": run_id, "format": "oi_worksheet"})

    assert resp.status_code == 200, resp.text
    ids = {r["row_id"] for r in calls[0]}
    assert leg_picked["row"].id in ids, calls
    assert leg_other["row"].id not in ids, calls
