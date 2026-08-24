"""Orchestration: resolve the sim DB, bootstrap it, wipe + reseed, run the engine, snapshot.

Nothing at module scope here imports ``app.*`` - every such import is inside a function
body, so ``__main__.py`` can set ``DATABASE_URL`` to the sim database BEFORE the first
``app.config`` import happens anywhere in the process. Importing this module is always
safe; CALLING its functions is only safe after that env var is set.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

DEFAULT_SIM_DB_NAME = "sorento_scm_sim"

_HERE = Path(__file__).resolve().parent
SNAPSHOT_PATH = _HERE / "snapshots" / "current.json"
BASELINE_PATH = _HERE / "baselines" / "baseline.json"

#: Every table the sim world writes to. TRUNCATE ... CASCADE is safe here ONLY because the
#: sim database is dedicated and provably empty of anything else (see ``guard_sim_db``) - 
#: CASCADE will also empty any FK-dependent table outside this list, and on a real database
#: that would be a disaster. Children before parents is not required for TRUNCATE (it locks
#: everything named + CASCADE-reached up front), but the list still reads parent-to-child
#: for a human skimming it.
_SIM_TABLES = [
    "scm.reorder_recommendation", "scm.reorder_run",
    "scm.reorder_level", "scm.reorder_policy",
    "scm.order_summary_row", "scm.demand_stat", "scm.item_classification",
    "scm.supplier_performance", "scm.currency_rate",
    "purchase_order_lines", "purchase_orders",
    "sales_order_lines", "sales_orders",
    "spo_allocations", "inbound_shipments",
    "order_lines", "orders",
    "stock", "product_suppliers", "products", "product_categories",
    "customers", "suppliers", "warehouses", "units_of_measure",
]


# ===========================================================================
# sim database resolution + the hard-fail guard
# ===========================================================================


def expected_db_name() -> str:
    return os.environ.get("SCM_SIM_DB_NAME", DEFAULT_SIM_DB_NAME)


def _read_env_file_database_url() -> Optional[str]:
    path = _HERE.parent.parent / ".env"
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith("DATABASE_URL"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def resolve_sim_database_url() -> str:
    """The URL this whole harness will use, ALREADY validated to name the sim database.

    ``SCM_SIM_DATABASE_URL`` wins outright when set (still validated below). Otherwise the
    sim URL is derived from the ambient ``DATABASE_URL`` (or the local ``.env``, same
    fallback ``tests/scm/conftest.py`` uses) by swapping only the database name.
    """
    from sqlalchemy.engine import make_url

    expected = expected_db_name()
    override = os.environ.get("SCM_SIM_DATABASE_URL")
    if override:
        url = override
    else:
        base = os.environ.get("DATABASE_URL") or _read_env_file_database_url()
        if not base:
            raise SystemExit(
                "[scm_sim] DATABASE_URL is not set and no .env was found. Set "
                "DATABASE_URL (any db on the target Postgres server) or "
                "SCM_SIM_DATABASE_URL (the full sim URL) explicitly."
            )
        url = str(make_url(base).set(database=expected))

    actual = make_url(url).database or ""
    if actual != expected:
        raise SystemExit(
            f"[scm_sim] REFUSING: resolved database name is {actual!r}, expected "
            f"{expected!r}. This harness must never run against anything but the "
            "dedicated sim database. Set SCM_SIM_DB_NAME to change the expected name, "
            "or fix SCM_SIM_DATABASE_URL / DATABASE_URL."
        )
    return url


def guard_sim_db() -> None:
    """Re-check, at the point of actually touching data, that ``settings.database_url``
    (which by now reflects whatever ``__main__.py`` put in the environment) still names the
    sim database. Cheap, and the last line of defence against a caller that imported this
    package without going through ``__main__.py``'s env-var dance."""
    from sqlalchemy.engine import make_url

    from app.config import settings

    name = make_url(settings.database_url).database or ""
    expected = expected_db_name()
    if name != expected:
        raise SystemExit(
            f"[scm_sim] REFUSING: the active database is {name!r}, expected "
            f"{expected!r}. Refusing to wipe or seed anything."
        )


# ===========================================================================
# init - provision the sim database from nothing
# ===========================================================================


def _ensure_database_exists(url: str, db_name: str) -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    maintenance_url = make_url(url).set(database="postgres")
    eng = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
            ).first()
            if exists:
                print(f"[scm_sim] database {db_name!r} already exists")
                return
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            print(f"[scm_sim] created database {db_name!r}")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"[scm_sim] could not create database {db_name!r}: {exc}\n"
            "If the Postgres role lacks CREATEDB, create it by hand: "
            f"createdb {db_name}"
        ) from exc
    finally:
        eng.dispose()


def _fix_committed_v() -> None:
    """Bring ``scm.committed_v`` current past migration 337.

    Delegates to ``scripts.bootstrap_env._fix_committed_v`` - CI's from-zero bootstrap
    hit the exact same staleness (it also only replays 274/311/327/337), so the fix is
    owned there and the sim reuses it rather than keeping a second copy that can drift.
    """
    from scripts.bootstrap_env import _fix_committed_v as _bootstrap_fix_committed_v

    _bootstrap_fix_committed_v()
    print("[scm_sim] scm.committed_v is current (demand_origin rule present)")


def _ensure_wide_alembic_version_table() -> None:
    """``command.stamp()`` creates ``alembic_version`` itself, with alembic's own default
    ``VARCHAR(32)`` column, if the table does not already exist. Every real deployment of
    this repo has that column manually widened to 255 (some revision ids, e.g.
    ``352_scm_product_lifecycle_decision``, are longer than 32 chars) - a fact
    ``bootstrap_env.py`` does not itself account for, so a truly-from-zero bootstrap hits
    the same ``StringDataRightTruncation`` this pre-creates a way around. Pre-creating the
    table with the wider column is a no-op on a database that already has one (``stamp()``
    checks existence first and never touches an existing table)."""
    from sqlalchemy import text

    from app.database import engine

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(255) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        ))


def _sync_legacy_columns(tables: tuple[str, ...]) -> None:
    """Add to the sim database any column the REAL database has on ``tables`` that the
    model-built schema lacks, using the real column's data type. Additive only, never
    drops or retypes, idempotent."""
    from sqlalchemy import create_engine, text

    from app.database import engine

    real_url = _read_env_file_database_url()
    if not real_url:
        print("[scm_sim] WARNING: no real DATABASE_URL in .env; skipping legacy column sync")
        return
    real = create_engine(real_url)
    try:
        for table in tables:
            with real.connect() as rc:
                real_cols = {
                    r[0]: r[1] for r in rc.execute(text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = :t AND table_schema = 'public'"), {"t": table})
                }
            with engine.begin() as conn:
                sim_cols = {
                    r[0] for r in conn.execute(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :t AND table_schema = 'public'"), {"t": table})
                }
                missing = {c: dt for c, dt in real_cols.items() if c not in sim_cols}
                for col, dtype in sorted(missing.items()):
                    conn.execute(text(
                        f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "{col}" {dtype}'
                    ))
                if missing:
                    print(f"[scm_sim] {table}: added legacy columns {sorted(missing)}")
                else:
                    print(f"[scm_sim] {table}: no legacy columns missing")
    finally:
        real.dispose()


def _sync_model_columns() -> None:
    """Add to the sim database any column the MODELS declare that its tables lack.

    ``create_all`` creates missing TABLES but never alters an existing one, so every
    merge that adds a column to an existing model leaves the sim database one column
    behind and the next seed dies on an INSERT naming it. This is the mirror of
    ``_sync_legacy_columns`` (which covers the opposite case: columns only the real
    database has). Additive only, never drops or retypes, idempotent.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateColumn

    import app.models  # noqa: F401 - populate Base.metadata with every model
    from app.database import Base, engine

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names(schema="public"))
    added: list[str] = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.schema not in (None, "public") or table.name not in existing_tables:
                continue
            have = {c["name"] for c in inspector.get_columns(table.name, schema="public")}
            for column in table.columns:
                if column.name in have:
                    continue
                ddl = CreateColumn(column).compile(engine).string
                # A NOT NULL column with no default cannot be added to a populated table;
                # the sim database is reseeded from empty every run, so relaxing it here
                # keeps the seed honest without inventing a value.
                ddl = ddl.replace(" NOT NULL", "") if column.server_default is None else ddl
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS {ddl}'))
                added.append(f"{table.name}.{column.name}")
    if added:
        print(f"[scm_sim] model columns added to the sim database: {sorted(added)}")
    else:
        print("[scm_sim] sim database columns match the models")


def _apply_migration_only_ddl() -> None:
    """``create_all`` builds tables from the MODELS. Columns/tables that exist only in a
    migration (no model mapping) are silently absent, and the affected endpoints 500 at
    read time. Known cases, found by running the real UI against a fresh sim database:
    351 (``scm.reorder_policy.margin_floor_pct`` etc.), 352
    (``scm.product_lifecycle_decision``), and the ``product_suppliers.min_order_quantity``
    / ``.is_primary`` legacy columns. All three are owned by
    ``scripts.bootstrap_env.apply_migration_only_ddl`` - CI's from-zero bootstrap needs the
    exact same schema, so the DDL lives there and the sim reuses it rather than keeping a
    second copy that can drift.
    """
    from scripts.bootstrap_env import apply_migration_only_ddl as _bootstrap_apply_ddl

    _bootstrap_apply_ddl()

    # Legacy columns with no model mapping AND no migration either: the two named above
    # are hardcoded in bootstrap because CI has no real database to read from. The sim
    # DOES have one, so also sync the FULL column set for the affected tables from the
    # real dev database's schema - not just the two known names - in case a future
    # legacy column is added there and read by raw SQL before anyone models it.
    _sync_legacy_columns(("product_suppliers",))


def _copy_menu_gating_tables() -> None:
    """The sidebar is gated by TWO things the bootstrap does not seed, and both live in
    whatever database the serving process is on: the full ``user_permissions`` catalog
    (a superadmin's slug list is ``SELECT slug FROM user_permissions`` - an empty catalog
    means an empty sidebar even for a superadmin) and ``tenant_modules`` (menu groups with
    a ``moduleKey`` hide when the tenant has no enabled row). Copy both, plus the module
    catalog/bundles they reference, from the real dev database. Idempotent."""
    import json

    from sqlalchemy import create_engine, text

    sim_url = os.environ["DATABASE_URL"]
    real_url = _read_env_file_database_url()
    if not real_url:
        raise SystemExit("[scm_sim] cannot copy menu gating tables: no DATABASE_URL in .env")
    conflict = {
        "user_permissions": "(slug)",
        "app_modules_catalog": "(module_key)",
        "app_module_bundles": "(id)",
        "tenant_modules": "(id)",
    }
    real = create_engine(real_url)
    sim = create_engine(sim_url)
    try:
        for table, conflict_key in conflict.items():
            with real.connect() as rc:
                rows = [dict(r) for r in rc.execute(text(f"SELECT * FROM {table}")).mappings()]
                jsonb_cols = {
                    r[0] for r in rc.execute(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :t AND data_type = 'jsonb'"), {"t": table})
                }
            if not rows:
                print(f"[scm_sim] {table}: nothing to copy")
                continue
            cols = list(rows[0].keys())
            collist = ", ".join(cols)
            params = ", ".join(
                f"CAST(:{c} AS jsonb)" if c in jsonb_cols else f":{c}" for c in cols
            )
            with sim.begin() as sc:
                for r in rows:
                    for c in jsonb_cols:
                        if r.get(c) is not None and not isinstance(r[c], str):
                            r[c] = json.dumps(
                                list(r[c]) if isinstance(r[c], (list, tuple)) else r[c]
                            )
                    sc.execute(text(
                        f"INSERT INTO {table} ({collist}) VALUES ({params}) "
                        f"ON CONFLICT {conflict_key} DO NOTHING"), r)
                count = sc.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            print(f"[scm_sim] {table}: {count} rows present after copy")
    finally:
        real.dispose()
        sim.dispose()


def cmd_init() -> None:
    """Create the sim database (if missing) and bootstrap it into a runnable schema."""
    url = os.environ["DATABASE_URL"]  # __main__.py has already resolved + set this
    db_name = expected_db_name()
    _ensure_database_exists(url, db_name)

    from scripts.bootstrap_env import (
        _seed_default_company,
        create_schema,
        create_views,
        seed_scm_module_data,
        stamp_head,
    )

    guard_sim_db()
    create_schema()
    create_views()
    _seed_default_company()
    seed_scm_module_data()
    _ensure_wide_alembic_version_table()
    stamp_head()
    _fix_committed_v()
    _apply_migration_only_ddl()
    _sync_model_columns()
    print(f"[scm_sim] sim database {db_name!r} is ready.")
    print("[scm_sim] REMINDER: run `python -m scripts.scm_sim seed-auth` next if you plan "
          "to `serve` this database - it has no users/roles yet, so nothing can log in "
          "against it until that has run.")


# ===========================================================================
# reset - wipe every sim-world table (dedicated DB -> a blunt TRUNCATE is fine)
# ===========================================================================


def reset_sim_db() -> None:
    from sqlalchemy import text

    from app.database import engine

    guard_sim_db()
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {', '.join(_SIM_TABLES)} CASCADE"))


# ===========================================================================
# run - wipe, reseed, run the engine under the pinned clock, snapshot
# ===========================================================================


def _run_engine(db, scenarios) -> str:
    """Pin the engine's clock to ``AS_OF`` and drive one full plan over the sim world."""
    from datetime import date as _real_date
    from unittest.mock import patch

    from app.services.scm import reorder_run_service as svc

    from scripts.scm_sim.world import AS_OF, WH_DEALER, WH_PROJECT

    class _FrozenDate(_real_date):
        @classmethod
        def today(cls):
            return AS_OF

    codes = [s.code for s in scenarios]
    with patch("app.services.scm.reorder_run_service.date", _FrozenDate):
        created = svc.create_run(
            db, [WH_DEALER, WH_PROJECT], buy_scope="warehouse", enqueue=False,
            product_codes=codes,
        )
        result = svc.run_reorder(created["run_id"], db=db)

    if result.get("status") != "completed":
        raise SystemExit(
            f"[scm_sim] RUN FAILED (run_id={created['run_id']}): "
            f"{result.get('error') or '(no error_text - check the run row)'}"
        )
    print(f"[scm_sim] run {created['run_id']} completed: "
          f"{ {k: v for k, v in result.items() if k not in ('run_id', 'status')} }")
    return created["run_id"]


def _read_planning_mode_before_reset() -> str:
    """The wipe-and-reseed would otherwise silently revert the company's planning mode
    to auto on every run (ensure_reorder_policy_defaults recreates the global row) - so
    the buyer's Policies-page toggle would never survive a Run. Read it first, restore
    after seeding. Defaults to auto when the table is empty (first init)."""
    from sqlalchemy import text

    from app.database import engine

    try:
        with engine.connect() as conn:
            pt = conn.execute(text(
                "SELECT policy_type FROM scm.reorder_policy "
                "WHERE scope_type = 'global' AND is_active ORDER BY priority DESC NULLS LAST LIMIT 1"
            )).scalar()
    except Exception:
        return "auto"
    return "manual" if pt == "reorder_level" else "auto"


def _restore_planning_mode(db, mode: str) -> None:
    """The global row may not exist yet at this point (the engine's own
    ensure_reorder_policy_defaults creates it mid-run otherwise) - create it first, or
    the UPDATE silently hits zero rows and the run reverts to auto anyway."""
    from sqlalchemy import text

    from app.services.scm import reorder_engine

    if mode != "manual":
        return
    reorder_engine.ensure_reorder_policy_defaults(db)
    updated = db.execute(text(
        "UPDATE scm.reorder_policy SET policy_type = 'reorder_level' "
        "WHERE scope_type = 'global'"
    )).rowcount
    if not updated:
        raise SystemExit("[scm_sim] planning-mode restore matched no global policy row")
    print("[scm_sim] planning mode preserved across reseed: manual")


def run_once(*, scenario_code: Optional[str] = None, bless: bool = False) -> dict:
    """Wipe, reseed (all scenarios, or one with ``--scenario``), run, snapshot, write JSON.

    Returns ``{"run_id": ..., "snapshot": {...}}``.
    """
    from app.database import SessionLocal
    from app.models.base import set_company_scope
    from app.services.company_scope import register_company_scope_listeners

    from scripts.scm_sim.scenarios import BY_CODE, SCENARIOS
    from scripts.scm_sim.snapshot import build_snapshot
    from scripts.scm_sim.world import SORENTO_COMPANY_ID, seed_all

    guard_sim_db()
    register_company_scope_listeners()
    planning_mode = _read_planning_mode_before_reset()
    reset_sim_db()

    if scenario_code:
        if scenario_code not in BY_CODE:
            raise SystemExit(f"[scm_sim] unknown scenario code {scenario_code!r}")
        scenarios = [BY_CODE[scenario_code]]
    else:
        scenarios = SCENARIOS

    db = SessionLocal()
    try:
        set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
        seed_all(db, scenarios)
        db.commit()

        _restore_planning_mode(db, planning_mode)
        db.commit()

        run_id = _run_engine(db, scenarios)
        db.commit()

        snapshot = build_snapshot(db, run_id, scenarios)
    finally:
        db.close()

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(SNAPSHOT_PATH, snapshot)
    print(f"[scm_sim] wrote {SNAPSHOT_PATH}")

    if bless:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _write_json(BASELINE_PATH, snapshot)
        print(f"[scm_sim] blessed baseline -> {BASELINE_PATH}")

    _print_run_summary(snapshot)
    return {"run_id": run_id, "snapshot": snapshot}


def _print_run_summary(snapshot: dict) -> None:
    """One skimmable line per scenario: rec_type + rounded_qty, or NONE."""
    from scripts.scm_sim.snapshot import META_KEY

    print("\n=== per-scenario summary ===")
    for code, entry in snapshot.items():
        if code == META_KEY:
            print(f"  {'planning_mode':<12} {entry.get('planning_mode')}")
            continue
        recs = entry.get("recommendations") or []
        if not recs:
            print(f"  {code:<12} NONE")
            continue
        parts = [f"{r.get('rec_type')}={r.get('rounded_qty')}" for r in recs]
        print(f"  {code:<12} {', '.join(parts)}")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ===========================================================================
# serve - run app.main:app against the sim database so the real UI can see it
# ===========================================================================


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


#: The port the committed FE production build's ``NEXT_PUBLIC_API_URL`` is baked to (a
#: `next build` bakes env vars into the client bundle - there is no runtime override). Only
#: at THIS port does an existing FE deployment (":3060") point at whatever this command
#: serves; any other port needs its own frontend pointed at it by hand.
FE_BAKED_API_PORT = 8060


def cmd_serve(port: int) -> None:
    """Serve ``app.main:app`` against the sim database on ``port``, in the foreground.

    Never kills or touches another process: if something is already listening on
    ``port``, this refuses to start rather than fight over it - stop it yourself first
    (or pick a different ``--port``). Blocks until Ctrl-C.
    """
    guard_sim_db()
    if _port_in_use(port):
        raise SystemExit(
            f"[scm_sim] port {port} is already in use - refusing to start (this harness "
            f"never stops another process). Stop whatever is listening on :{port} first, "
            "or pass a different --port."
        )

    import uvicorn

    db_name = expected_db_name()
    print(f"[scm_sim] serving app.main:app on :{port}, connected to the sim database "
          f"{db_name!r}.")
    if port == FE_BAKED_API_PORT:
        print(f"[scm_sim] this IS the port the :3060 FE build is baked to call - open "
              "http://localhost:3060 now and every page (Reorder Planning, dashboard, ...) "
              "shows the SIM world.")
    else:
        print(f"[scm_sim] the :3060 FE build is baked to call :{FE_BAKED_API_PORT}, not "
              f":{port} - point a frontend's NEXT_PUBLIC_API_URL at :{port} yourself, or "
              f"re-run with --port {FE_BAKED_API_PORT} (only if that port is free) to reuse "
              "the existing :3060 UI.")
    print("[scm_sim] Ctrl-C to stop. Remember to switch your normal backend back on "
          "afterwards - this process never touches it.")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)


# ===========================================================================
# seed-auth - copy the minimum auth chain to use the sim-backed API as yourself
# ===========================================================================

#: Only these two role slugs bypass RBAC entirely (see the docstring below) - copying any
#: other role would need its actual `user_role_permissions` grants too, which this harness
#: deliberately does not carry.
_BYPASS_ROLE_SLUGS = ("superadmin", "admin")

def cmd_seed_auth() -> None:
    """Copy the auth chain needed to use the sim-backed API AS a real superadmin/admin
    user - READ-ONLY against the real dev database (``.env``'s own ``DATABASE_URL``),
    upsert-only (idempotent, by id) against the sim database.

    What actually gates a request here - investigated against the real code, not assumed:

  - **RBAC bypass, not grants.** ``UserPermissionService.check_user_has_permission``
      returns ``True`` outright for any user holding a role slug in
      ``{"superadmin", "admin"}`` - no ``user_permissions`` / ``user_role_permissions`` row
      is ever consulted for that user (``app/services/user_service.py``). So the minimal
      correct chain is ``users`` + the qualifying ``user_role_assignments`` row +
      ``user_roles`` row - permission-grant rows are not needed and are not copied.
  - **Module guard no-ops in local dev.** ``require_module_enabled_with_api_key`` returns
      immediately when ``settings.module_guard_strict`` is off (the default, and unset in
      this repo's ``.env``), before it ever looks at a role or a tenant-module row. This
      function checks and prints which case applies rather than assuming it.
  - **Auth is an opaque per-row session token, not a stateless JWT.** ``get_current_user``
      looks the exact ``user_sessions.token`` up in THIS PROCESS's own database on every
      request (``app/services/user_session_service.py``) - a token minted against the real
      dev database will never resolve against the sim database's own (separate, and after
      ``init``, empty) ``user_sessions`` table. So this function also copies each qualifying
      user's currently-active (non-revoked, unexpired) real sessions - that is what actually
      lets an already-logged-in browser keep working when pointed at the sim-backed
      process. No token is ever minted or printed here: a session token is a live
      credential, and credentials must never land in stdout, transcripts, or logs. For
      browserless verification use the X-API-Key act-as path from ``.env``.

    Safe to re-run: every table is upserted by primary key id.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    guard_sim_db()
    sim_url = os.environ["DATABASE_URL"]  # __main__.py has already resolved + set this

    real_url = _read_env_file_database_url()
    if not real_url:
        raise SystemExit(
            "[scm_sim] no DATABASE_URL found in .env - cannot read the real dev database "
            "to copy auth from."
        )
    if (make_url(real_url).database or "") == expected_db_name():
        raise SystemExit(
            "[scm_sim] .env's DATABASE_URL already names the sim database - point it back "
            "at the real dev database first (this command reads FROM .env, not from "
            "whatever this process itself is connected to)."
        )

    from app.config import settings

    if settings.module_guard_strict:
        print("[scm_sim] MODULE_GUARD_STRICT is ON - the superadmin/admin role-slug bypass "
              "in require_module_enabled_with_api_key still applies to whichever users get "
              "copied below, so this is still safe; a user copied for any OTHER role would "
              "additionally need a tenant-module row, which this command does not seed.")
    else:
        print("[scm_sim] MODULE_GUARD_STRICT is off - the module guard no-ops for every "
              "user; no tenant/module rows are needed.")

    real_engine = create_engine(real_url)
    sim_engine = create_engine(sim_url)
    try:
        with real_engine.connect() as rconn:
            rows = rconn.execute(text("""
                SELECT u.id AS user_id, u.email, u.password, u.name, u.contact_number,
                       u.status, u.last_sign_in_at, u.email_verified_at,
                       u.is_trashed AS user_is_trashed, u.is_protected AS user_is_protected,
                       u.is_integration,
                       r.id AS role_id, r.slug AS role_slug, r.name AS role_name,
                       r.description AS role_description,
                       r.is_trashed AS role_is_trashed, r.is_protected AS role_is_protected,
                       r.is_default AS role_is_default,
                       ura.id AS assignment_id, ura.assigned_at
                FROM users u
                JOIN user_role_assignments ura ON ura.user_id = u.id
                JOIN user_roles r ON r.id = ura.role_id
                WHERE r.slug = ANY(:slugs) AND u.is_trashed = false
            """), {"slugs": list(_BYPASS_ROLE_SLUGS)}).mappings().all()

            if not rows:
                print("[scm_sim] no superadmin/admin users found in the real database - "
                      "nothing to copy.")
                return

            users = {r["user_id"]: dict(r) for r in rows}
            roles = {r["role_id"]: dict(r) for r in rows}
            assignments = {r["assignment_id"]: dict(r) for r in rows}
            user_ids = list(users.keys())

            sessions = rconn.execute(text("""
                SELECT id, token, user_id, expires_at, revoked_at, rolling, user_agent,
                       ip_address, last_seen_at, created_at
                FROM user_sessions
                WHERE user_id = ANY(:ids) AND revoked_at IS NULL AND expires_at > now()
            """), {"ids": user_ids}).mappings().all()

        from scripts.scm_sim.world import SORENTO_COMPANY_ID

        with sim_engine.begin() as sconn:
            for u in users.values():
                sconn.execute(text("""
                    INSERT INTO users (id, email, password, name, contact_number, status,
                                        last_sign_in_at, email_verified_at, is_trashed,
                                        is_protected, is_integration, last_active_company_id,
                                        respond_synced, daily_sla_summary_subscribed)
                    VALUES (:user_id, :email, :password, :name, :contact_number, :status,
                            :last_sign_in_at, :email_verified_at, :user_is_trashed,
                            :user_is_protected, :is_integration, :company_id,
                            'pending', true)
                    ON CONFLICT (id) DO UPDATE SET
                        email = EXCLUDED.email, password = EXCLUDED.password,
                        name = EXCLUDED.name, contact_number = EXCLUDED.contact_number,
                        status = EXCLUDED.status, last_sign_in_at = EXCLUDED.last_sign_in_at,
                        email_verified_at = EXCLUDED.email_verified_at,
                        is_trashed = EXCLUDED.is_trashed,
                        is_protected = EXCLUDED.is_protected,
                        is_integration = EXCLUDED.is_integration,
                        last_active_company_id = EXCLUDED.last_active_company_id
                """), {**u, "company_id": SORENTO_COMPANY_ID})

            for r in roles.values():
                sconn.execute(text("""
                    INSERT INTO user_roles (id, slug, name, description, is_trashed,
                                             is_protected, is_default)
                    VALUES (:role_id, :role_slug, :role_name, :role_description,
                            :role_is_trashed, :role_is_protected, :role_is_default)
                    ON CONFLICT (id) DO UPDATE SET
                        slug = EXCLUDED.slug, name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        is_trashed = EXCLUDED.is_trashed,
                        is_protected = EXCLUDED.is_protected,
                        is_default = EXCLUDED.is_default
                """), r)

            for a in assignments.values():
                sconn.execute(text("""
                    INSERT INTO user_role_assignments (id, user_id, role_id, assigned_at)
                    VALUES (:assignment_id, :user_id, :role_id, :assigned_at)
                    ON CONFLICT (id) DO UPDATE SET
                        user_id = EXCLUDED.user_id, role_id = EXCLUDED.role_id,
                        assigned_at = EXCLUDED.assigned_at
                """), a)

            for s in sessions:
                sconn.execute(text("""
                    INSERT INTO user_sessions (id, token, user_id, expires_at, revoked_at,
                                                rolling, user_agent, ip_address,
                                                last_seen_at, created_at)
                    VALUES (:id, :token, :user_id, :expires_at, :revoked_at, :rolling,
                            :user_agent, :ip_address, :last_seen_at, :created_at)
                    ON CONFLICT (id) DO UPDATE SET
                        token = EXCLUDED.token, expires_at = EXCLUDED.expires_at,
                        revoked_at = EXCLUDED.revoked_at, rolling = EXCLUDED.rolling,
                        user_agent = EXCLUDED.user_agent, ip_address = EXCLUDED.ip_address,
                        last_seen_at = EXCLUDED.last_seen_at
                """), dict(s))
    finally:
        real_engine.dispose()
        sim_engine.dispose()

    print(f"[scm_sim] copied {len(users)} superadmin/admin user(s), {len(roles)} role(s), "
          f"{len(sessions)} active real session(s) into the sim database.")
    _copy_menu_gating_tables()
    print("[scm_sim] no tokens are printed by design: your logged-in browser session "
          "works as-is against a sim-backed process; for curl use the X-API-Key act-as "
          "credentials from .env.")


def _uid() -> str:
    import uuid

    return str(uuid.uuid4())
