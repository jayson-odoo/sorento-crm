"""Measures `MasterIngestService.ingest("products", ..., dry_run=True)` against
a real database - the harness for the AutoCount pull preview perf lane
(`PLAN-autocount-pull-preview-perf.md`, PP-9).

    venv/bin/python scripts/measure_pull_preview.py \\
        --dsn postgresql://user:pass@host:5432/dbname \\
        --company-code SRT

Prints record count, elapsed seconds, records/second and the number of SQL
statements issued (SQLAlchemy's own `before_cursor_execute` counter - the
same technique `tests/test_ingest_perf_round_5.py` and this lane's own
`tests/test_autocount_pull_preview_perf.py` (T5) use to pin a query count,
never internal cache state).

`--limit N` measures only the first N rows (`_build_products`' own
`ORDER BY p.product_code`, so a run is reproducible) - for a fast profiling
slice rather than the full ~11,900-row batch. `--profile PATH` wraps the
`ingest()` call in `cProfile` and writes `PATH` in `pstats` format (load with
`pstats.Stats(PATH)` or `snakeviz PATH`); omitted, profiling is skipped
entirely so the timed numbers this script exists for are never paid its
overhead by accident.

Read-only against the database: `dry_run=True` resolves and applies every
record exactly as a live sync would, then rolls the WHOLE transaction back -
the same guarantee `MasterIngestService.ingest` gives every other dry-run
caller (see that module's own docstring, "Dry run is a real run that is taken
back"). Never writes a row, never runs a migration.

`--dsn` is REQUIRED and used exactly as given - never `DATABASE_URL` from the
environment. A worktree's own `.env` overrides whatever the shell exports
(LESSONS-LEARNT ".env overrides env"), so trusting the environment here risks
silently measuring a different database than the one the caller named -
`scripts/build_fake_foundryx_data.py`'s own docstring makes the same point,
and this script reuses its `_build_products` rather than re-deriving the row
shape a second time.

Registers the SAME listener set `worker.py`'s own `__main__` does before
running any RQ job - company-scope + the product-spec after_insert/
after_update hooks (idempotent, `product_spec_change_listener.
register_product_spec_listeners`) - and deliberately NOT `register_audit_
listeners` / `register_embedding_change_listeners`: `worker.py` never
registers either (only `app/main.py`'s API startup_event does), so the real
`preview_autocount_pull` task this script stands in for pays neither cost.
Registering them here anyway would measure a workload nothing in production
ever actually runs.
"""
from __future__ import annotations

import argparse
import cProfile
import os
import pstats
import sys
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Same convention as `scripts/audit_attachment_key_collisions.py`: running this
# file directly (`python scripts/measure_pull_preview.py`) puts `scripts/`
# itself on `sys.path[0]`, not the backend root, so a bare `import app...` (or
# `from scripts...`) fails without this.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.build_fake_foundryx_data import _build_products  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dsn", required=True, help="Full SQLAlchemy/psycopg URL - never read from env"
    )
    parser.add_argument("--company-code", default="SRT", help="companies.code (default SRT)")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Measure only the first N rows (by product_code) instead of the whole company",
    )
    parser.add_argument(
        "--profile", type=str, default=None,
        help="Write a cProfile pstats dump to this path instead of a plain timed run",
    )
    args = parser.parse_args()

    # Late imports: `app.database`'s own module-level engine reads `DATABASE_URL`
    # from the environment/`.env` at import time, which is exactly what `--dsn`
    # exists to bypass - so this script builds its own engine/session instead of
    # importing `app.database.SessionLocal`.
    from app.models.company import Company
    from app.services.company_scope import register_company_scope_listeners
    from app.services.master_ingest_service import MasterIngestService
    from app.services.product_spec_change_listener import register_product_spec_listeners
    from app.services.product_spec_write import register_spec_write_backstop

    register_company_scope_listeners()
    register_product_spec_listeners()
    register_spec_write_backstop()

    engine = create_engine(args.dsn)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        company = db.query(Company).filter(Company.code == args.company_code).first()
        if company is None:
            raise SystemExit(f"no company with code {args.company_code!r} in this database")
        company_id = str(company.id)

        rows = _build_products(engine, args.company_code)
        if not rows:
            raise SystemExit(f"no products found for company {args.company_code!r}")
        if args.limit is not None:
            rows = rows[: args.limit]

        statements = 0

        def _count(conn, cursor, statement, *_a, **_kw):  # noqa: ANN001
            nonlocal statements
            statements += 1

        connection = db.get_bind()
        event.listen(connection, "before_cursor_execute", _count)
        profiler = cProfile.Profile() if args.profile else None
        try:
            started = time.monotonic()
            if profiler is not None:
                profiler.enable()
            result = MasterIngestService(db, company_id=company_id).ingest(
                "products", rows, dry_run=True
            )
            if profiler is not None:
                profiler.disable()
            elapsed = time.monotonic() - started
        finally:
            event.remove(connection, "before_cursor_execute", _count)

        if profiler is not None:
            pstats.Stats(profiler).dump_stats(args.profile)
            print(f"profile:    {args.profile}")

        records = len(result.records)
        rate = records / elapsed if elapsed else 0.0
        print(f"records:    {records}")
        print(f"seconds:    {elapsed:.1f}")
        print(f"rec/s:      {rate:.1f}")
        print(f"statements: {statements}")
        print(
            f"created={result.created} updated={result.updated} "
            f"failed={result.failed} retryable={result.retryable}"
        )
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
