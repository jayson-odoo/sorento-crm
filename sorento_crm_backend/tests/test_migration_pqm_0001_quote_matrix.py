"""Migration `pqm_0001_quote_matrix`: the downgrade must survive several open requests on one
issue (normal since feedback no longer blocks a second submit).

Runs the real migration functions against the real ``projects`` tables INSIDE one transaction
that is always rolled back (Postgres DDL is transactional), with FK triggers off so two request
rows can be seeded without building a project chain.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import engine

BACKEND = Path(__file__).resolve().parents[1]


def _load():
    files = sorted((BACKEND / "alembic" / "versions").glob("pqm_0001*.py"))
    assert len(files) == 1, files
    spec = importlib.util.spec_from_file_location("_pqm_0001_test", files[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downgrade_then_upgrade_with_two_open_requests_on_one_issue():
    module = _load()
    issue_id, company_id = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.connect() as conn:
        try:
            ctx = MigrationContext.configure(conn)
            conn.exec_driver_sql("SET LOCAL session_replication_role = replica")
            for minutes in (10, 0):
                conn.execute(
                    sa.text(
                        "INSERT INTO projects.quotation_amendment_requests "
                        "(id, company_id, issue_id, status, submitted_at) "
                        "VALUES (:id, :c, :i, 'open', now() - make_interval(mins => :m))"
                    ),
                    {"id": str(uuid.uuid4()), "c": company_id, "i": issue_id, "m": minutes},
                )
            with Operations.context(ctx):
                module.downgrade()
                statuses = [
                    r[0]
                    for r in conn.execute(
                        sa.text(
                            "SELECT status FROM projects.quotation_amendment_requests "
                            "WHERE issue_id = :i ORDER BY submitted_at"
                        ),
                        {"i": issue_id},
                    )
                ]
                assert statuses == ["superseded", "open"]  # only the newest stays open
                module.upgrade()
            has_cells = conn.execute(
                sa.text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'projects' "
                    "AND table_name = 'quotation_lines' AND column_name = 'qty_cells'"
                )
            ).scalar()
            assert has_cells == 1
        finally:
            conn.rollback()
