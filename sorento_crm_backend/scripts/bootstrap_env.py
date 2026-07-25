"""Provision an empty Postgres database into a runnable Sorento CRM schema.

This is the reproducible environment bootstrap: it is what CI uses to build a
test database, and what a brand-new environment (or a disaster-recovery restore)
needs before the app can start.

WHY THIS EXISTS RATHER THAN `alembic upgrade head`
--------------------------------------------------
The migration chain cannot build the schema from zero. Its first revision
(``001_add_is_responded_to_sla_tracking``) *alters* ``conversation_sla_tracking``,
and no migration ever creates that table — the original database was built by
SQLAlchemy ``create_all`` and every migration since has only ALTERed it. Running
``alembic upgrade head`` against an empty database therefore dies at revision
``008`` with "relation conversation_sla_tracking does not exist".

So the ORM models are the source of truth for the schema, exactly as they were
originally. This script makes that explicit and repeatable instead of implicit
and lost. Once the schema exists it is stamped at head so future migrations
apply normally.

Squashing the historical migrations into a real baseline revision would let
``alembic upgrade head`` work from zero and is the better long-term fix, but it
requires re-stamping existing databases — a separate, coordinated change.

USAGE
-----
    DATABASE_URL=postgresql://localhost/sorento_ci python -m scripts.bootstrap_env

Idempotent: safe to re-run against an already-bootstrapped database.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("bootstrap")


def _require_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("DATABASE_URL is not set")
        sys.exit(1)
    return url


def create_schema() -> None:
    """Create every table declared by the ORM models, plus the `scm` schema."""
    import app.models  # noqa: F401  — registers every model on Base.metadata
    from sqlalchemy import text

    from app.database import Base, engine

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS scm"))
        # pgvector / trigram are used by the embedding + entity-resolver paths.
        for ext in ("vector", "pg_trgm"):
            try:
                conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
            except Exception as exc:  # noqa: BLE001
                log.warning("extension %s unavailable: %s", ext, exc)

    Base.metadata.create_all(engine)
    log.info("schema created from ORM models")


def create_views() -> None:
    """Create the `scm` reporting views.

    The DDL lives in migration 274 as module-level constants; it is imported
    from there rather than duplicated so the migration stays the single source
    of truth for the view definitions.
    """
    import importlib.util
    from pathlib import Path

    from sqlalchemy import text

    from app.database import engine

    mig = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "274_scm_m0_views_reg.py"
    )
    spec = importlib.util.spec_from_file_location("_scm_views_mig", mig)
    module = importlib.util.module_from_spec(spec)
    # The migration imports `alembic.op` at module scope only inside functions,
    # so loading it for its constants is safe.
    spec.loader.exec_module(module)

    ordered = [
        module._ON_ORDER_V,
        module._COMMITTED_V,
        module._CONSUMPTION_V,
        module._RECEIPT_LEAD_V,
        module._NET_POSITION_V,
    ]
    with engine.begin() as conn:
        for ddl in ordered:
            # The migration's DDL uses bare CREATE VIEW; make re-runs idempotent.
            conn.execute(text(ddl.replace("CREATE VIEW", "CREATE OR REPLACE VIEW", 1)))
    log.info("scm views created (%d)", len(ordered))


def _seed_default_company() -> None:
    """Idempotently insert the fixed Sorento company row (mirrors migration 302).

    Needed because bootstrap builds the schema from the models and only *stamps*
    alembic at head — migration 302's data seed is never executed. Without this
    row the ``*_company_id_fkey`` constraints reject every owned insert once the
    scope layer auto-stamps the incumbent company.
    """
    from sqlalchemy import text

    from app.database import engine

    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(
            text(
                "INSERT INTO companies (id, name, code, is_active) "
                "VALUES ('00000000-0000-0000-0000-000000000001', 'Sorento', 'SRT', true) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        log.info("seeded default company (Sorento)")
    except Exception as exc:  # noqa: BLE001
        log.warning("default-company seed failed (continuing): %s", exc)
    finally:
        conn.close()


def seed_reference_data() -> None:
    """Run the app's own startup seeders.

    These are the same functions ``app.main`` invokes on boot, called directly so
    a database is fully seeded without having to start a server. Each is
    idempotent and independently guarded: one failing must not abort the rest.
    """
    from app.database import SessionLocal

    # Multi-company: the schema comes from create_all + `alembic stamp head`, so
    # migration 302's Sorento seed never runs here. Every owned table has a NOT
    # NULL company_id FK -> companies, and the test suite / seeders auto-stamp the
    # incumbent Sorento company, so that row MUST exist first or every owned insert
    # violates the FK. Seed it idempotently (fixed id, mirrors migration 302).
    _seed_default_company()

    steps = [
        # Roles + order statuses first: later seeders and RBAC grants depend on them.
        ("reference data", "app.services.reference_seed", "run"),
        ("rbac permissions", "app.rbac.permission_registry", "sync_permissions"),
        # Re-run so freshly synced permissions reach the admin roles.
        ("admin permission grants", "app.services.reference_seed", "run"),
        ("email event configs", "app.services.email_event_registry", "seed_event_configs"),
        ("mcp tool catalog", "app.services.mcp_tool_registry_service", "sync_catalog"),
        ("it support bootstrap", "app.services.it_support_bootstrap", "run"),
        ("record action bootstrap", "app.services.record_action_bootstrap", "run"),
    ]
    for label, module_path, func_name in steps:
        db = SessionLocal()
        try:
            module = __import__(module_path, fromlist=[func_name])
            result = getattr(module, func_name)(db)
            db.commit()
            log.info("seeded %s -> %s", label, result)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("seeder %r failed (continuing): %s", label, exc)
        finally:
            db.close()


def stamp_head() -> None:
    """Mark the database as being at the latest revision.

    The schema came from the models, which already reflect every migration, so
    the historical revisions must not be replayed.
    """
    from alembic import command
    from alembic.config import Config

    from pathlib import Path

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.stamp(cfg, "head")
    log.info("alembic stamped at head")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Create schema + views but skip reference-data seeding.",
    )
    args = parser.parse_args()

    url = _require_db_url()
    log.info("bootstrapping %s", url.rsplit("@", 1)[-1])

    create_schema()
    create_views()
    if not args.skip_seed:
        seed_reference_data()
    stamp_head()
    log.info("bootstrap complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
