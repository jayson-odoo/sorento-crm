"""S2-BE-2: plan-grain policy + run stamp + decision guards (AC-F01, F09, F10).

Contract: `documentation/plans/scm/PLAN-scm-front-planning.md` sections 5.1, 5.4, 6.4;
`UAC-scm-front-planning.md` AC-F01, AC-F09, AC-F10; `STAGE2-scm-front-planning-worknotes.md`
slice S2-BE-2.

**TDD red.** None of this exists yet:

* `system_settings.plan_grain` is not a column (rollout default "product").
* `scm.reorder_run.decision_grain` / `.front_planning_contract_version` are not columns.
* `reorder_run_service.create_run` does not stamp either.
* `summary_order_service.record_decision` and `decision_service.{accept,adjust,reject}
  _recommendation` / `bulk_accept` have no legacy-run or grain-mismatch guard at all.
* The run/report response contracts do not carry the new fields.

Names this file assumes the coder will use (pinned here so red and green agree on the same
contract): `SystemSetting.plan_grain` (`'product' | 'location'`, default `'product'`),
`ReorderRun.decision_grain`, `ReorderRun.front_planning_contract_version`, and the two
`AppException` codes `legacy_run_read_only` and `decision_grain_mismatch` (both 409).

Two fixture idioms, matching what each section actually needs:

* **Settings** (blank, isolated schema): `tests/test_settings_app_config_gate.py`'s pattern -
  `tests._pg_fixture.blank_session()` + a monkeypatched `UserPermissionService
  .check_user_has_permission` (route-level view gate; the POST route only needs a caller,
  no permission check).
* **SCM run/decision guards** (real, rolled-back savepoint DB, because `scm.*` views need the
  live schema): `tests/scm/conftest.py`'s `scm_app` + the `_company` / `_principal` idiom from
  `tests/scm/test_order_summary_routes.py`, and the marker-prefixed product/run/recommendation
  chain from `tests/scm/test_summary_order_service.py` / `tests/scm/test_m4_decisions.py`.

Every row is marker-prefixed (`ZZTPGP`) and seeded fresh per test; nothing is borrowed with
`LIMIT 1` off the shared prod-copy database, per PRINCIPLES.md / CLAUDE.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models.inventory import Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.procurement import Supplier
from app.models.scm import OrderSummaryRow, ReorderRecommendation, ReorderRun
from app.models.user import SystemSetting
from app.services.error_handler import AppException
from app.services.scm import decision_service as dsvc
from app.services.scm import reorder_run_service as run_svc
from app.services.scm import summary_order_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401  (fixture)

pytestmark = requires_pg

MARKER = "ZZTPGP"
_VIEW_PERM = "scm.dashboard.view"
_RUN_PERM = "scm.reorder.run"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str = "") -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


# =========================================================================== #
# section A - the admin plan-grain policy setting
# (blank_session + monkeypatched permission check, mirrors
#  tests/test_settings_app_config_gate.py)
# =========================================================================== #


SETTINGS_ENDPOINT = "/api/v1/user-management/settings/"
SETTINGS_GENERAL_ENDPOINT = "/api/v1/user-management/settings/general"
_SETTINGS_PERMISSION = "user_management.settings.view"


@pytest.fixture()
def blank_db():
    from tests._pg_fixture import blank_session

    with blank_session() as s:
        yield s


@pytest.fixture()
def settings_api(blank_db, monkeypatch):
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app
    from app.services.user_service import UserPermissionService

    user = {"id": str(uuid.uuid4()), "email": "plan-grain-caller@zzt.test"}
    allow: set[str] = {_SETTINGS_PERMISSION}

    def _override_db():
        yield blank_db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _seed_settings_row(db) -> None:
    db.add(SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co"))
    db.commit()


def test_settings_get_includes_plan_grain_defaulting_to_product(settings_api, blank_db):
    _seed_settings_row(blank_db)

    resp = settings_api.get(SETTINGS_ENDPOINT)

    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"]["plan_grain"] == "product"


def test_settings_post_general_persists_plan_grain(settings_api, blank_db):
    _seed_settings_row(blank_db)

    resp = settings_api.post(SETTINGS_GENERAL_ENDPOINT, json={"plan_grain": "location"})
    assert resp.status_code == 200, resp.text

    resp = settings_api.get(SETTINGS_ENDPOINT)
    assert resp.json()["settings"]["plan_grain"] == "location"


def test_settings_post_general_rejects_unknown_plan_grain_value(settings_api, blank_db):
    _seed_settings_row(blank_db)

    resp = settings_api.post(SETTINGS_GENERAL_ENDPOINT, json={"plan_grain": "foo"})

    assert resp.status_code == 422, resp.text


# `test_system_setting_model_has_no_plan_grain_column_yet_is_the_red_signal` lived here.
# It was the red marker for the missing column - `SystemSetting(..., plan_grain=...)`
# raising TypeError - and its own docstring said to delete it in the green step once the
# column exists, which migration 375 did. The behaviour it stood in for is covered by the
# three settings tests above.


# =========================================================================== #
# section B - create_run stamps decision_grain + contract version
# (real, rolled-back DB via pg_session; no HTTP, no auth - service-level)
# =========================================================================== #


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _get_or_create_settings(db) -> SystemSetting:
    settings = db.query(SystemSetting).first()
    if settings is None:
        settings = SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co")
        db.add(settings)
        db.flush()
    return settings


def test_create_run_stamps_default_policy_as_product(db):
    created = run_svc.create_run(db, [], enqueue=False)
    run = db.query(ReorderRun).filter(ReorderRun.id == created["run_id"]).one()

    assert run.decision_grain == "product"
    assert run.front_planning_contract_version == 1


def test_create_run_stamps_configured_location_policy(db):
    settings = _get_or_create_settings(db)
    settings.plan_grain = "location"
    db.commit()

    created = run_svc.create_run(db, [], enqueue=False)
    run = db.query(ReorderRun).filter(ReorderRun.id == created["run_id"]).one()

    assert run.decision_grain == "location"
    assert run.front_planning_contract_version == 1


def test_policy_change_after_creation_does_not_alter_an_existing_run(db):
    """AC-F10: a created run keeps its stamped grain even after the policy changes."""
    settings = _get_or_create_settings(db)
    settings.plan_grain = "product"
    db.commit()

    first = run_svc.create_run(db, [], enqueue=False)

    settings.plan_grain = "location"
    db.commit()

    second = run_svc.create_run(db, [], enqueue=False)

    first_run = db.query(ReorderRun).filter(ReorderRun.id == first["run_id"]).one()
    second_run = db.query(ReorderRun).filter(ReorderRun.id == second["run_id"]).one()

    assert first_run.decision_grain == "product", "the first run must not follow the later change"
    assert second_run.decision_grain == "location"


# =========================================================================== #
# fixture chain for the decision-guard sections (C/D/E): one product, one
# warehouse, one recommendation, one frozen order_summary_row.
# =========================================================================== #


def _category_and_uom(db):
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    return cat, uom


def _product(db, cat, uom):
    p = Product(
        id=_u(), product_code=_code("SKU"), product_name="plan grain product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0, is_active=True,
    )
    db.add(p)
    db.flush()
    return p


def _warehouse(db):
    wh = Warehouse(id=_u(), warehouse_code=_code("WH")[:30], warehouse_name="wh",
                    is_active=True, counts_as_available=True)
    db.add(wh)
    db.flush()
    return wh


def _supplier(db):
    s = Supplier(id=_u(), supplier_code=_code("S")[:30], supplier_name="plan grain supplier")
    db.add(s)
    db.flush()
    return s


def _run(db, *, decision_grain=None, contract_version=None, status="completed"):
    """A run, optionally stamped with the new columns.

    ``decision_grain=None`` (the default) is a LEGACY run - both new columns absent, which is
    exactly what a pre-Stage-2 run looks like and needs no kwarg at all, so it is red-safe
    regardless of whether the migration has landed. Passing an explicit grain constructs the
    row WITH the kwarg, which raises ``TypeError`` today (the column does not exist) - that is
    the correct red reason for every test that needs a specific stamped grain.
    """
    kwargs = dict(
        id=_u(), status=status, buy_scope="warehouse",
        started_at=datetime.utcnow(), source_system="scm", source_ref=_code("RUN"),
    )
    if decision_grain is not None:
        kwargs["decision_grain"] = decision_grain
    if contract_version is not None:
        kwargs["front_planning_contract_version"] = contract_version
    run = ReorderRun(**kwargs)
    db.add(run)
    db.flush()
    return run


def _recommendation(db, run, product, wh, qty=50):
    rec = ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=qty, status="proposed",
    )
    db.add(rec)
    db.flush()
    return rec


# =========================================================================== #
# section C - a legacy run (both new columns NULL) is read-only everywhere
# =========================================================================== #


def test_record_decision_refused_on_a_legacy_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db)  # legacy: no decision_grain, no contract version
    _recommendation(db, run, product, wh)
    supplier = _supplier(db)
    svc.write_rows(db, run.id)

    with pytest.raises(AppException) as exc:
        svc.record_decision(
            db, product.product_code, run_id=run.id,
            chosen_qty=10, supplier_code=supplier.supplier_code, actor="tester",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail.get("code") == "legacy_run_read_only"


def test_accept_recommendation_refused_on_a_legacy_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db)
    rec = _recommendation(db, run, product, wh)

    with pytest.raises(AppException) as exc:
        dsvc.accept_recommendation(db, rec.id, actor="tester")

    assert exc.value.status_code == 409
    assert exc.value.detail.get("code") == "legacy_run_read_only"


def test_adjust_recommendation_refused_on_a_legacy_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db)
    rec = _recommendation(db, run, product, wh)

    with pytest.raises(AppException) as exc:
        dsvc.adjust_recommendation(
            db, rec.id, override_qty=20, override_supplier_code=None,
            reason_text="legacy run test", actor="tester",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail.get("code") == "legacy_run_read_only"


# =========================================================================== #
# section D - a decision write in the OTHER stamped grain is rejected
# =========================================================================== #


def test_record_decision_refused_on_a_location_grain_run(db):
    """Product-grain decisions (`record_decision`) are rejected on a `location` run."""
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db, decision_grain="location", contract_version=1)
    _recommendation(db, run, product, wh)
    supplier = _supplier(db)
    svc.write_rows(db, run.id)

    with pytest.raises(AppException) as exc:
        svc.record_decision(
            db, product.product_code, run_id=run.id,
            chosen_qty=10, supplier_code=supplier.supplier_code, actor="tester",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail.get("code") == "decision_grain_mismatch"


def test_accept_recommendation_refused_on_a_product_grain_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db, decision_grain="product", contract_version=1)
    rec = _recommendation(db, run, product, wh)

    with pytest.raises(AppException) as exc:
        dsvc.accept_recommendation(db, rec.id, actor="tester")

    assert exc.value.status_code == 409
    assert exc.value.detail.get("code") == "decision_grain_mismatch"


def test_adjust_recommendation_refused_on_a_product_grain_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db, decision_grain="product", contract_version=1)
    rec = _recommendation(db, run, product, wh)

    with pytest.raises(AppException) as exc:
        dsvc.adjust_recommendation(
            db, rec.id, override_qty=20, override_supplier_code=None,
            reason_text="grain mismatch test", actor="tester",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail.get("code") == "decision_grain_mismatch"


def test_reject_recommendation_refused_on_a_product_grain_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db, decision_grain="product", contract_version=1)
    rec = _recommendation(db, run, product, wh)

    with pytest.raises(AppException) as exc:
        dsvc.reject_recommendation(db, rec.id, reason_text="grain mismatch test", actor="tester")

    assert exc.value.status_code == 409
    assert exc.value.detail.get("code") == "decision_grain_mismatch"


def test_bulk_accept_refused_on_a_product_grain_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db, decision_grain="product", contract_version=1)
    rec = _recommendation(db, run, product, wh)

    with pytest.raises(AppException) as exc:
        dsvc.bulk_accept(db, run.id, [rec.id], actor="tester")

    assert exc.value.status_code == 409
    assert exc.value.detail.get("code") == "decision_grain_mismatch"


# =========================================================================== #
# section E - matching grain still works (the guard rejects only the OTHER
# grain; on a match the existing happy path is untouched)
# =========================================================================== #


def test_record_decision_still_works_on_a_matching_product_grain_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db, decision_grain="product", contract_version=1)
    _recommendation(db, run, product, wh, qty=120)
    supplier = _supplier(db)
    svc.write_rows(db, run.id)

    out = svc.record_decision(
        db, product.product_code, run_id=run.id,
        chosen_qty=200, supplier_code=supplier.supplier_code, actor="mr loo",
    )

    assert out["chosen_qty"] == 200
    assert out["suggested_qty"] == 120


def test_accept_recommendation_still_works_on_a_matching_location_grain_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db, decision_grain="location", contract_version=1)
    rec = _recommendation(db, run, product, wh)

    out = dsvc.accept_recommendation(db, rec.id, actor="mr loo")

    assert out is not None
    assert rec.status == "accepted"


# =========================================================================== #
# section F - response contracts carry the new fields
# (real, rolled-back savepoint DB + TestClient, mirrors
#  tests/scm/test_order_summary_routes.py's `_company` / `_principal` idiom)
# =========================================================================== #


def _company(app, db) -> frozenset:
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope_resolver import apply_company_scope

    company_id = _u()
    db.add(Company(
        id=company_id, name=f"{MARKER} company {company_id[:8]}",
        code=_code("CO")[:50], is_active=True,
    ))
    db.flush()
    scope = frozenset({company_id})
    set_company_scope(db, scope)

    async def _scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _scope
    return scope


def _principal(app, db, gcu, gcuk, *, perms: list[str], name="Mr Loo") -> str:
    from app.models.user import User, UserPermission, UserRole, UserRoleAssignment, UserRolePermission

    uid = _u()
    db.add(User(id=uid, email=f"{uid}@zzt-pgp.test", name=name, status="ACTIVE"))
    role_code = _code("role")
    role = UserRole(id=_u(), slug=role_code.lower(), name=role_code)
    db.add(role)
    db.flush()
    for slug in perms:
        perm = db.query(UserPermission).filter(UserPermission.slug == slug).one_or_none()
        if perm is None:
            perm = UserPermission(id=_u(), slug=slug, name=slug)
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(id=_u(), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(user_id=uid, role_id=role.id))
    db.flush()

    principal = {"id": uid, "email": f"{uid}@zzt-pgp.test", "name": name}
    app.dependency_overrides[gcu] = lambda: principal
    app.dependency_overrides[gcuk] = lambda: principal
    return uid


def test_get_reorder_run_exposes_decision_grain_and_contract_version(scm_app):  # noqa: F811
    app, db, gcu, gcuk = scm_app
    _company(app, db)
    _principal(app, db, gcu, gcuk, perms=[_VIEW_PERM])

    created = run_svc.create_run(db, [], enqueue=False)

    client = TestClient(app)
    resp = client.get(f"/api/v1/scm/reorder-runs/{created['run_id']}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "decision_grain" in body
    assert "front_planning_contract_version" in body


def test_todays_reorder_run_exposes_decision_grain_and_contract_version(scm_app):  # noqa: F811
    app, db, gcu, gcuk = scm_app
    _company(app, db)
    _principal(app, db, gcu, gcuk, perms=[_VIEW_PERM])

    created = run_svc.create_run(db, [], enqueue=False)
    run = db.query(ReorderRun).filter(ReorderRun.id == created["run_id"]).one()
    run.status = "completed"
    run.started_at = datetime.utcnow()
    db.commit()

    client = TestClient(app)
    resp = client.get("/api/v1/scm/reorder-runs/today")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body is not None, "the just-completed run must be picked as today's run"
    assert "decision_grain" in body
    assert "front_planning_contract_version" in body


def test_order_summary_report_exposes_decision_grain_and_is_legacy(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db, decision_grain="product", contract_version=1)
    _recommendation(db, run, product, wh)
    svc.write_rows(db, run.id)

    report = svc.report(db, run_id=run.id)

    assert report["decision_grain"] == "product"
    assert report["is_legacy"] is False


def test_order_summary_report_marks_a_legacy_run(db):
    cat, uom = _category_and_uom(db)
    product = _product(db, cat, uom)
    wh = _warehouse(db)
    run = _run(db)  # legacy: no decision_grain
    _recommendation(db, run, product, wh)
    svc.write_rows(db, run.id)

    report = svc.report(db, run_id=run.id)

    assert report["is_legacy"] is True

# =========================================================================== #
# section G - the decision routes that were guarded nowhere (AC-F09, AC-F10)
# (real DB + TestClient, mirrors tests/scm/test_order_summary_routes.py's
#  HTTP-guard tests: the guard has to hold at the WIRE, not only in the service)
# =========================================================================== #
#
# `accept` / `adjust` / `reject` / `bulk-accept` were guarded from the start (sections
# C/D above). Three sibling writes on the same router were not, and each is a live
# route: `covered-decision` sets a recommendation status, `confirm-decisions`
# materialises draft POs out of staged ones, and `reset-decisions` wipes decisions and
# overrides. A guard the neighbouring route enforces and this one does not is worse
# than no guard, because the run reads as protected.


def _covered_recommendation(db, run, product, wh, qty=50):
    rec = ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="covered", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=qty, status="proposed",
    )
    db.add(rec)
    db.flush()
    return rec


@pytest.fixture()
def decision_api(scm_app):  # noqa: F811
    """A caller holding `scm.reorder.run`, with a company the seeded rows belong to."""
    app, db, gcu, gcuk = scm_app
    _company(app, db)
    _principal(app, db, gcu, gcuk, perms=[_VIEW_PERM, _RUN_PERM])
    cat, uom = _category_and_uom(db)
    return {
        "app": app, "db": db, "client": TestClient(app),
        "product": _product(db, cat, uom), "warehouse": _warehouse(db),
    }


def test_covered_decision_over_http_refuses_a_product_grain_run(decision_api):
    """A covered-by-stock answer is a LOCATION decision, so a product-grain run must
    refuse it the same way it refuses Accept - it is the same recommendation row."""
    f = decision_api
    run = _run(f["db"], decision_grain="product", contract_version=1)
    rec = _covered_recommendation(f["db"], run, f["product"], f["warehouse"])

    res = f["client"].post(
        f"/api/v1/scm/recommendations/{rec.id}/covered-decision",
        json={"choice": "buy"},
    )

    assert res.status_code == 409, res.text
    assert res.json()["code"] == "decision_grain_mismatch"
    assert rec.status == "proposed", "the refused write must not have landed"


def test_covered_decision_over_http_refuses_a_legacy_run(decision_api):
    f = decision_api
    run = _run(f["db"])  # legacy: no decision_grain, no contract version
    rec = _covered_recommendation(f["db"], run, f["product"], f["warehouse"])

    res = f["client"].post(
        f"/api/v1/scm/recommendations/{rec.id}/covered-decision",
        json={"choice": "use_stock"},
    )

    assert res.status_code == 409, res.text
    assert res.json()["code"] == "legacy_run_read_only"
    assert rec.status == "proposed"


def test_covered_decision_over_http_still_works_on_a_location_grain_run(decision_api):
    """The guard rejects only the other grain; the planner's own run still decides."""
    f = decision_api
    run = _run(f["db"], decision_grain="location", contract_version=1)
    rec = _covered_recommendation(f["db"], run, f["product"], f["warehouse"])

    res = f["client"].post(
        f"/api/v1/scm/recommendations/{rec.id}/covered-decision",
        json={"choice": "buy"},
    )

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "buy"


def test_confirm_decisions_over_http_refuses_a_legacy_run(decision_api):
    """Materialising a legacy run's staged decisions into draft POs would make a plan
    that is supposed to be closed produce real purchasing work."""
    f = decision_api
    run = _run(f["db"])
    _recommendation(f["db"], run, f["product"], f["warehouse"])

    res = f["client"].post(
        f"/api/v1/scm/reorder-runs/{run.id}/confirm-decisions", json={"ids": []})

    assert res.status_code == 409, res.text
    assert res.json()["code"] == "legacy_run_read_only"


def test_confirm_decisions_over_http_refuses_a_product_grain_run(decision_api):
    """Confirm is the step that turns staged LOCATION decisions into draft POs, so a
    product-grain run refuses it - otherwise the guard on Accept is bypassed by whatever
    status a recommendation happens to carry."""
    f = decision_api
    run = _run(f["db"], decision_grain="product", contract_version=1)
    rec = _recommendation(f["db"], run, f["product"], f["warehouse"])
    rec.status = "accepted"
    f["db"].flush()

    res = f["client"].post(
        f"/api/v1/scm/reorder-runs/{run.id}/confirm-decisions", json={"ids": []})

    assert res.status_code == 409, res.text
    assert res.json()["code"] == "decision_grain_mismatch"


def test_reset_decisions_over_http_refuses_a_legacy_run(decision_api):
    """A legacy run's decisions are history: the demo reset may not rewrite them."""
    f = decision_api
    run = _run(f["db"])
    rec = _recommendation(f["db"], run, f["product"], f["warehouse"])
    rec.status = "accepted"
    f["db"].flush()

    res = f["client"].post(f"/api/v1/scm/reorder-runs/{run.id}/reset-decisions")

    assert res.status_code == 409, res.text
    assert res.json()["code"] == "legacy_run_read_only"
    assert rec.status == "accepted", "the refused reset must not have cleared anything"


def test_reset_decisions_over_http_still_works_on_a_current_run(decision_api):
    """Reset is not a decision, so it is refused for being LEGACY only - never for being
    the other grain. A product-grain run's location recommendations are read-only, and
    putting their status back to as-generated undoes nothing anybody decided."""
    f = decision_api
    run = _run(f["db"], decision_grain="product", contract_version=1)
    rec = _recommendation(f["db"], run, f["product"], f["warehouse"])
    rec.status = "accepted"
    f["db"].flush()

    res = f["client"].post(f"/api/v1/scm/reorder-runs/{run.id}/reset-decisions")

    assert res.status_code == 200, res.text
    assert res.json()["decisions_cleared"] == 1
    assert rec.status == "proposed"


# No new gated GET under app.api.v1.user_management: the plan-grain policy field rides the
# EXISTING `GET /settings/` blob and `POST/PUT /settings/general` (sections A above), covered
# already by tests/test_user_management_read_gates.py's exact-42-route set - that suite is the
# regression guard and needs no duplicate here (worknotes §0.4).
