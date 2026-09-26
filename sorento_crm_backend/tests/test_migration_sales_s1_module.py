"""S1 (#1267): the `sales` module, its Postgres schema, `sales.reports.view` and the
chatbot wiring the migration ships.

UAC: AC-R3-2 (one module: bootstrap, manifest entry, permission map), AC-R4-8 (`CREATE
SCHEMA IF NOT EXISTS sales`, idempotent, env.py untouched), AC-R4-10 / AC-R5-11 (no table
of this plan outside `sales`, and S1 adds none), AC-S1-19 (the tool on the order domain's
live row, single head), plus the DoD grant sweep (PRINCIPLES DoD 3) and the module being
enabled wherever `order` already is, so the menu item is not born hidden.

A `test_migration_*` file: it runs real DDL, so CI runs it serially (LESSONS 97).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from tests._pg_fixture import blank_session

_VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"
_FILE = _VERSIONS / "sales_s1_reports_module.py"
SLUG = "sales.reports.view"
TOOL = "crm_sales_analysis"


def _load():
    import sys

    alembic_dir = str(_VERSIONS.parent)
    if alembic_dir not in sys.path:
        sys.path.insert(0, alembic_dir)
    spec = importlib.util.spec_from_file_location("_zzt_sales_s1", _FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, module, direction="upgrade"):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _seed_roles_and_order_domain(db):
    db.execute(sa.text(
        "INSERT INTO user_roles (id, slug, name) VALUES "
        "(gen_random_uuid()::text, 'admin', 'Admin'), "
        "(gen_random_uuid()::text, 'superadmin', 'Superadmin'), "
        "(gen_random_uuid()::text, 'sales_executive_zzt', 'Sales exec')"
    ))
    import importlib.util as iu

    spec = iu.spec_from_file_location("_zzt_s0", _VERSIONS / "chatbot_rearch_s0.py")
    import sys

    sys.path.insert(0, str(_VERSIONS.parent))
    s0 = iu.module_from_spec(spec)
    spec.loader.exec_module(s0)
    s0.seed_domains_and_kinds(db.connection())
    db.execute(sa.text(
        "INSERT INTO app_modules_catalog (id, module_key, display_name, dependencies) "
        "VALUES (gen_random_uuid(), 'order', 'Order', '[]'::jsonb) ON CONFLICT DO NOTHING"
    ))
    db.execute(sa.text(
        "INSERT INTO tenant_modules (id, tenant_id, module_key, enabled) "
        "VALUES (gen_random_uuid(), '__default__', 'order', true)"
    ))


# --------------------------------------------------------------- the module files


def test_ac_r3_2_one_sales_module():
    from app.modules.runtime.module_manifest import MODULE_MANIFEST
    from app.modules.runtime.permission_module_map import module_for_permission
    from app.modules.sales import bootstrap

    assert bootstrap.MODULE_KEY == "sales"
    assert "sales" in MODULE_MANIFEST
    assert {"base", "order"} <= set(MODULE_MANIFEST["sales"].dependencies)
    assert module_for_permission(SLUG) == "sales"


def test_the_slug_is_in_the_permission_registry():
    from app.rbac.permission_registry import PERMISSION_REGISTRY as PERMISSIONS

    slugs = {p["slug"] for p in PERMISSIONS}
    assert SLUG in slugs


def test_ac_r4_10_the_purge_file_ships_empty_and_no_model_lives_in_sales():
    import json

    from app.database import Base

    purge = Path(__file__).resolve().parents[2] / "sorento_crm_frontend" / "modules" / "sales" / "purge_tables.json"
    assert json.loads(purge.read_text()) == []
    in_sales = [t.fullname for t in Base.metadata.tables.values() if t.schema == "sales"]
    # AC-R5-11: this plan adds no table; any later one must sit in `sales` (none yet).
    assert in_sales == []
    new_public = [t.fullname for t in Base.metadata.tables.values()
                  if t.name.startswith("sales_report") or t.name.startswith("report_subscription")]
    assert new_public == []


def test_ac_r4_8_env_py_is_unchanged_and_filters_by_model_schemas():
    env = (_VERSIONS.parent / "env.py").read_text()
    assert "include_schemas=True" in env
    assert "sales" not in env


# ------------------------------------------------------------------- the migration


def test_ac_r4_8_single_head_and_a_short_revision_id():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _load()
    assert len(module.revision) <= 32
    script = ScriptDirectory.from_config(Config(str(_VERSIONS.parent.parent / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    walked = {rev.revision for rev in script.walk_revisions()}
    assert module.revision in walked


def test_ac_r4_8_upgrade_creates_the_schema_grants_the_slug_and_enables_the_module():
    module = _load()
    with blank_session() as db:
        _seed_roles_and_order_domain(db)
        _run(db, module)
        _run(db, module)  # idempotent: a second run (after #1260's) is a no-op

        schemas = {r[0] for r in db.execute(sa.text("SELECT nspname FROM pg_namespace"))}
        assert "sales" in schemas

        granted = {r[0] for r in db.execute(sa.text(
            "SELECT r.slug FROM user_role_permissions urp "
            "JOIN user_roles r ON r.id = urp.role_id "
            "JOIN user_permissions p ON p.id = urp.permission_id WHERE p.slug = :s"), {"s": SLUG})}
        assert granted == {"admin", "superadmin"}

        catalog = db.execute(sa.text(
            "SELECT count(*) FROM app_modules_catalog WHERE module_key = 'sales'")).scalar()
        assert catalog == 1
        enabled = db.execute(sa.text(
            "SELECT enabled FROM tenant_modules WHERE tenant_id = '__default__' "
            "AND module_key = 'sales'")).scalar()
        assert enabled is True


def test_ac_s1_19_the_tool_and_intent_join_the_live_order_row_once():
    module = _load()
    with blank_session() as db:
        _seed_roles_and_order_domain(db)
        _run(db, module)
        _run(db, module)
        tools = db.execute(sa.text("SELECT tools FROM chatbot_domains WHERE name = 'order'")).scalar()
        assert tools.count(TOOL) == 1
        assert tools[0] != TOOL, "never tools[0]: the pick is an override"


def test_ac_s1_19_the_seed_rows_carry_the_same_tool():
    from app.services.chatbot.lanes.business.fetch import CHATBOT_READ_ONLY_TOOLS
    from app.services.chatbot.turn import policy_rows
    from app.services.mcp_tool_domains import CHATBOT_TOOL_DOMAINS as TOOL_DOMAINS

    order = next(r for r in policy_rows.DEFAULT_DOMAIN_ROWS if r["name"] == "order")
    assert TOOL in order["tools"] and order["tools"][0] != TOOL
    assert TOOL in CHATBOT_READ_ONLY_TOOLS
    assert TOOL in policy_rows.DATE_PARAM_TOOLS
    assert TOOL_DOMAINS[TOOL] == "order"


def test_the_parser_prompt_with_the_sales_analysis_words_is_production_after_upgrade():
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

    module = _load()
    with blank_session() as db:
        _seed_roles_and_order_domain(db)
        _run(db, module)
        label = db.query(AIPromptLabel).filter_by(name="chatbot_semantic_parser", label="production").one()
        version = db.query(AIPromptVersion).filter_by(id=label.version_id).one()
        assert 'order_status "sales_analysis"' in version.template
        assert '"sales_basis"' in version.template
