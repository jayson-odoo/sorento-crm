"""RED tests B3: migration `pc_0001_product_costing` (PRODUCT-COSTING, Phase 2). AC-ER-05, AC-AX-04.

APPROACH (same as tests/test_cost_price_permissions.py): load the migration file by path and run
its `upgrade()` / `downgrade()` through an alembic `Operations` context bound to a
`blank_session()` connection, inside the transaction the fixture rolls back. The scratch schema
is built from the ORM models, so once `app/models/costing.py` exists the six lane tables are
already there; each test therefore DROPS them first (DDL is transactional in Postgres, and the
drop is qualified with `current_schema()` so it can never reach a real table), then runs the
migration's own DDL.

ASSUMED MIGRATION INTERFACE (alembic/versions/pc_0001_product_costing.py):
    revision == "pc_0001_product_costing" (<= 32 chars); it is the SINGLE alembic head.
    upgrade() / downgrade() as contract section 2.
    seed_exchange_rates(connection) -> int   the idempotent seed step upgrade() calls: inserts one
        exchange_rates row per scm.currency_rate row (effective_from = as_of, else today) with
        ON CONFLICT DO NOTHING and returns the number of rows it inserted (0 on a rerun).
        Test-facing name; upgrade() must call it, so the rerun test exercises the real SQL.

`scm.currency_rate` is seeded in the scratch scm schema (ORM) AND, when the real table exists,
in the real one inside the rolled-back transaction, so the seed works whether the migration
names the table schema-qualified (as production does) or through search_path.

Not tested here: the `products.cost.view` grants (owned by #2319), only that the row exists.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests._pg_fixture import blank_session, unique_code
from tests.support.costing_env import CostingEnv

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION_PATH = BACKEND / "alembic" / "versions" / "pc_0001_product_costing.py"
MANAGE = "products.party_costing.manage"
COST_VIEW = "products.cost.view"
LANE_TABLES = (
    "customer_costing_products",
    "customer_costing_profiles",
    "costing_product_overrides",
    "costing_category_rules",
    "costing_settings",
    "exchange_rates",
)


def _module():
    spec = importlib.util.spec_from_file_location("zzt_migration_pc0001", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, module, direction: str) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _schema(db) -> str:
    return db.execute(text("SELECT current_schema()")).scalar()


def _drop_lane_tables(db) -> None:
    schema = _schema(db)
    for table in LANE_TABLES:
        db.execute(text(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE'))


def _tables_present(db) -> set[str]:
    rows = db.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")
    ).scalars().all()
    return {t for t in rows if t in LANE_TABLES}


def _role(db, slug):
    from app.models.user import UserRole

    row = UserRole(id=str(uuid.uuid4()), slug=slug, name=slug, description="",
                   is_protected=False, is_default=False)
    db.add(row)
    db.flush()
    return row


def _perm(db, slug):
    from app.models.user import UserPermission

    row = db.query(UserPermission).filter_by(slug=slug).one_or_none()
    if row is None:
        row = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
        db.add(row)
        db.flush()
    return row


def _grant(db, role_id, perm_id):
    from app.models.user import UserRolePermission

    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_id))
    db.flush()


def _slugs(db, role_id) -> set[str]:
    rows = db.execute(
        text("SELECT p.slug FROM user_role_permissions rp JOIN user_permissions p ON p.id = rp.permission_id "
             "WHERE rp.role_id = :r"),
        {"r": role_id},
    ).scalars().all()
    return set(rows)


def _insert(db, table: str, **cols) -> None:
    """Raw INSERT in a savepoint, so an IntegrityError leaves the transaction usable."""
    names = ", ".join(cols)
    binds = ", ".join(f":{k}" for k in cols)
    with db.begin_nested():
        db.execute(text(f"INSERT INTO {table} ({names}) VALUES ({binds})"), cols)


def _refuses(db, table: str, **cols) -> None:
    with pytest.raises(IntegrityError):
        _insert(db, table, **cols)


SRT = "00000000-0000-0000-0000-000000000001"
NOW = date(2026, 11, 11)


# ------------------------------------------------------------------ revision


def test_migration_file_has_the_pinned_revision_and_is_the_single_head():
    assert MIGRATION_PATH.exists(), f"missing {MIGRATION_PATH}"
    module = _module()
    assert module.revision == "pc_0001_product_costing"
    assert len(module.revision) <= 32
    assert module.down_revision  # chained onto main's head

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["pc_0001_product_costing"]


# ------------------------------------------------------------------ tables and constraints


def test_upgrade_creates_the_six_lane_tables():
    with blank_session() as db:
        _drop_lane_tables(db)
        assert _tables_present(db) == set()
        _run(db, _module(), "upgrade")
        assert _tables_present(db) == set(LANE_TABLES)


def test_exchange_rates_constraints_unique_pair_and_positive_rate():
    with blank_session() as db:
        _drop_lane_tables(db)
        _run(db, _module(), "upgrade")
        base = dict(id=str(uuid.uuid4()), currency="RMB", rate_to_base=0.625,
                    effective_from=date(2026, 11, 1), created_at=NOW, updated_at=NOW)
        _insert(db, "exchange_rates", **base)
        _refuses(db, "exchange_rates", **{**base, "id": str(uuid.uuid4())})  # same (currency, date)
        _insert(db, "exchange_rates", **{**base, "id": str(uuid.uuid4()), "effective_from": date(2026, 12, 1)})
        _refuses(db, "exchange_rates", **{**base, "id": str(uuid.uuid4()), "currency": "USD", "rate_to_base": 0})
        _refuses(db, "exchange_rates", **{**base, "id": str(uuid.uuid4()), "currency": "USD", "rate_to_base": -1})
        _refuses(db, "exchange_rates", **{**base, "id": str(uuid.uuid4()), "currency": "USD", "effective_from": None})


def test_costing_settings_and_category_rule_constraints():
    with blank_session() as db:
        e = CostingEnv(db)
        cat = e.category("MigCat")
        db.flush()
        _drop_lane_tables(db)
        _run(db, _module(), "upgrade")

        s = dict(id=str(uuid.uuid4()), company_id=SRT, sst_factor=1.1, default_method="primary", updated_at=NOW)
        _refuses(db, "costing_settings", **{**s, "sst_factor": 0})
        _refuses(db, "costing_settings", **{**s, "default_method": "selected"})  # never a company default
        _refuses(db, "costing_settings", **{**s, "default_method": "bogus"})
        for method in ("primary", "average", "last_po"):
            with db.begin_nested():
                db.execute(text("DELETE FROM costing_settings"))
            _insert(db, "costing_settings", **{**s, "id": str(uuid.uuid4()), "default_method": method})
        _refuses(db, "costing_settings", **{**s, "id": str(uuid.uuid4())})  # one row per company

        r = dict(category_id=cat.id, company_id=SRT, mode="add", value=8, updated_at=NOW)
        _refuses(db, "costing_category_rules", **{**r, "mode": "divide"})
        _refuses(db, "costing_category_rules", **{**r, "value": 0})
        _insert(db, "costing_category_rules", **r)
        _refuses(db, "costing_category_rules", **r)  # category is the primary key


def test_product_override_constraints():
    with blank_session() as db:
        e = CostingEnv(db)
        cat = e.category("MigCat")
        p = e.item("ZZ-MIG-1", category=cat, list_price="10")
        sup = e.source("SUP-MIG")
        db.flush()
        _drop_lane_tables(db)
        _run(db, _module(), "upgrade")

        o = dict(product_id=p.id, company_id=SRT, updated_at=NOW)
        # mode and value come together or not at all
        _refuses(db, "costing_product_overrides", **{**o, "transport_mode": "add"})
        _refuses(db, "costing_product_overrides", **{**o, "transport_value": 8})
        _refuses(db, "costing_product_overrides", **{**o, "transport_mode": "add", "transport_value": 0})
        _refuses(db, "costing_product_overrides", **{**o, "transport_mode": "halve", "transport_value": 2})
        # Only 'selected' may carry a supplier. 'selected' with a NULL supplier is allowed at the
        # DB level on purpose (contract section 2): ON DELETE SET NULL on the supplier must not
        # fail; the row then reads `selected_not_linked`. The API still refuses SETTING
        # 'selected' without a supplier (test_costing_page_save).
        _refuses(db, "costing_product_overrides", **{**o, "cost_method": "average", "cost_method_supplier_id": sup.id})
        _refuses(db, "costing_product_overrides", **{**o, "cost_method": "bogus"})
        _insert(db, "costing_product_overrides",
                **{**o, "cost_method": "selected", "cost_method_supplier_id": sup.id,
                   "transport_mode": "multiply", "transport_value": 1.07})


def test_party_profile_and_party_product_constraints():
    with blank_session() as db:
        e = CostingEnv(db)
        cat = e.category("MigCat")
        p = e.item("ZZ-MIG-2", category=cat, list_price="10")
        c = e.customer(code=unique_code("MIG")[:30], name="MIG PARTY")
        db.flush()
        _drop_lane_tables(db)
        _run(db, _module(), "upgrade")

        pr = dict(customer_id=c.id, company_id=SRT, markup_pct=8, is_active=True,
                  created_at=NOW, updated_at=NOW)
        _refuses(db, "customer_costing_profiles", **{**pr, "markup_pct": -1})
        _refuses(db, "customer_costing_profiles", **{**pr, "markup_pct": None})
        _refuses(db, "customer_costing_profiles", **{**pr, "cost_method": "selected"})  # LC-06
        _insert(db, "customer_costing_profiles", **{**pr, "cost_method": "average"})
        _refuses(db, "customer_costing_profiles", **pr)  # one profile per customer

        pp = dict(id=str(uuid.uuid4()), company_id=SRT, customer_id=c.id, product_id=p.id,
                  markup_pct=None, added_at=NOW, updated_at=NOW)
        _refuses(db, "customer_costing_products", **{**pp, "markup_pct": -0.5})
        _insert(db, "customer_costing_products", **pp)
        _refuses(db, "customer_costing_products", **{**pp, "id": str(uuid.uuid4())})  # (customer, product) unique


# ------------------------------------------------------------------ AC-ER-05 seed


def _seed_legacy_rates(db):
    """Two legacy rows (one with as_of, one without) in the scratch scm table, mirrored into the
    real one (rolled back) when it exists."""
    from app.models.scm import CurrencyRate

    db.add(CurrencyRate(currency="ZZA", rate_to_base=4.4, as_of=date(2026, 8, 1)))
    db.add(CurrencyRate(currency="ZZB", rate_to_base=0.625, as_of=None))
    db.flush()
    if db.execute(text("SELECT to_regclass('scm.currency_rate')")).scalar():
        for cur, rate, as_of in (("ZZA", 4.4, date(2026, 8, 1)), ("ZZB", 0.625, None)):
            with db.begin_nested():
                db.execute(
                    text("INSERT INTO scm.currency_rate (currency, rate_to_base, as_of) VALUES (:c, :r, :a) "
                         "ON CONFLICT (currency) DO NOTHING"),
                    {"c": cur, "r": rate, "a": as_of},
                )


def _dated(db):
    return {
        r[0]: (float(r[1]), r[2])
        for r in db.execute(
            text("SELECT currency, rate_to_base, effective_from FROM exchange_rates WHERE currency IN ('ZZA','ZZB')")
        ).all()
    }


def test_ac_er_05_seed_one_dated_row_per_scm_currency_rate_and_rerun_adds_nothing():
    with blank_session() as db:
        _seed_legacy_rates(db)
        _drop_lane_tables(db)
        module = _module()
        _run(db, module, "upgrade")

        got = _dated(db)
        assert set(got) == {"ZZA", "ZZB"}
        assert got["ZZA"] == (pytest.approx(4.4), date(2026, 8, 1))  # effective_from = as_of
        assert got["ZZB"][0] == pytest.approx(0.625)
        assert abs((got["ZZB"][1] - date.today()).days) <= 1  # no as_of -> the migration date

        before = db.execute(text("SELECT count(*) FROM exchange_rates")).scalar()
        inserted = module.seed_exchange_rates(db.connection())
        assert inserted == 0
        assert db.execute(text("SELECT count(*) FROM exchange_rates")).scalar() == before
        assert _dated(db) == got


def test_ac_er_05_the_legacy_table_is_left_in_place_and_untouched():
    with blank_session() as db:
        _seed_legacy_rates(db)
        _drop_lane_tables(db)
        _run(db, _module(), "upgrade")
        n = db.execute(text("SELECT count(*) FROM scm.currency_rate WHERE currency IN ('ZZA','ZZB')")).scalar()
        assert n == 2


# ------------------------------------------------------------------ AC-AX-04 grants


def test_ac_ax_04_manage_is_granted_by_role_slug_to_admin_and_director_only():
    with blank_session() as db:
        roles = {slug: _role(db, slug) for slug in (
            "admin", "director", "purchasing_manager", "purchasing", "purchasing_executive",
            "sales", "dealer", "superadmin")}
        extra = _role(db, unique_code("pcother"))
        _drop_lane_tables(db)
        module = _module()
        _run(db, module, "upgrade")

        for slug in ("admin", "director"):
            assert MANAGE in _slugs(db, roles[slug].id), slug
        for slug in ("purchasing_manager", "purchasing", "purchasing_executive", "sales", "dealer",
                     "superadmin"):
            assert MANAGE not in _slugs(db, roles[slug].id), slug  # superadmin passes by bypass
        assert MANAGE not in _slugs(db, extra.id)
        # nothing is revoked or granted beyond the manage slug
        assert _slugs(db, roles["admin"].id) - {MANAGE, COST_VIEW} == set()


def test_ac_ax_04_cost_view_row_is_inserted_granted_to_admin_and_director_and_never_duplicated():
    with blank_session() as db:
        director = _role(db, "director")
        purchasing = _role(db, "purchasing_manager")
        _drop_lane_tables(db)
        module = _module()
        _run(db, module, "upgrade")
        assert db.execute(text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": COST_VIEW}).scalar() == 1
        assert COST_VIEW in _slugs(db, director.id)
        assert COST_VIEW not in _slugs(db, purchasing.id)  # nobody else
        _run(db, module, "upgrade")  # a rerun adds neither a row nor a grant
        assert db.execute(text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": COST_VIEW}).scalar() == 1
        assert db.execute(
            text("SELECT count(*) FROM user_role_permissions rp JOIN user_permissions p ON p.id = rp.permission_id "
                 "WHERE p.slug = :s AND rp.role_id = :r"), {"s": COST_VIEW, "r": director.id}).scalar() == 1


def test_ac_ax_04_an_existing_cost_view_row_and_its_grants_are_left_alone():
    with blank_session() as db:
        role = _role(db, unique_code("pcbuyer"))
        _grant(db, role.id, _perm(db, COST_VIEW).id)
        _drop_lane_tables(db)
        _run(db, _module(), "upgrade")
        assert db.execute(text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": COST_VIEW}).scalar() == 1
        assert COST_VIEW in _slugs(db, role.id)


def test_ac_ax_04_manage_slug_is_in_the_permission_registry():
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert MANAGE in {p["slug"] for p in PERMISSION_REGISTRY}


# ------------------------------------------------------------------ downgrade


def test_downgrade_removes_only_what_upgrade_added():
    with blank_session() as db:
        admin = _role(db, "admin")
        keeper = _role(db, unique_code("pckeep"))
        cv = _perm(db, COST_VIEW)
        _grant(db, keeper.id, cv.id)
        _drop_lane_tables(db)
        module = _module()
        _run(db, module, "upgrade")
        assert _tables_present(db) == set(LANE_TABLES)
        assert MANAGE in _slugs(db, admin.id)

        _run(db, module, "downgrade")
        assert _tables_present(db) == set()
        assert db.execute(text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": MANAGE}).scalar() == 0
        assert db.execute(
            text("SELECT count(*) FROM user_role_permissions rp JOIN user_permissions p ON p.id = rp.permission_id "
                 "WHERE p.slug = :s"), {"s": MANAGE}).scalar() == 0
        # products.cost.view and its grants belong to #2319 and survive, the ones this upgrade made too
        assert COST_VIEW in _slugs(db, keeper.id)
        assert COST_VIEW in _slugs(db, admin.id)
        assert db.execute(text("SELECT count(*) FROM user_permissions WHERE slug = :s"), {"s": COST_VIEW}).scalar() == 1
