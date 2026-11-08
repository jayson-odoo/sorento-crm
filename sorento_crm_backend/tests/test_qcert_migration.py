"""qcert_0001_quote_certificates: columns and table of the quotation Certification tab (UAC test 10).

Driven through `upgrade()`/`downgrade()` over a BLANK schema, the way test_migration_ptag_0005 does:
`create_all` builds today's model, so the objects are dropped first to rewind to the old shape.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from tests._pg_fixture import blank_session

_BACKEND = Path(__file__).resolve().parent.parent
_MIGRATION_PATH = _BACKEND / "alembic" / "versions" / "qcert_0001_quote_certificates.py"
TABLE = "quotation_document_certificates"
CP_COLUMNS = {"model_code", "model_code_source", "boxes"}


def _module():
    spec = importlib.util.spec_from_file_location("zzt_migration_qcert_0001", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _state(db):
    insp = inspect(db.get_bind())
    cp = {c["name"] for c in insp.get_columns("certificate_products")}
    issues = {c["name"] for c in insp.get_columns("quotation_issues", schema="projects")}
    return cp, "certificates" in issues, insp.has_table(TABLE, schema="projects")


@pytest.fixture
def db():
    with blank_session() as session:
        for col in CP_COLUMNS:
            session.execute(text(f"ALTER TABLE certificate_products DROP COLUMN IF EXISTS {col}"))
        session.execute(text("ALTER TABLE projects.quotation_issues DROP COLUMN IF EXISTS certificates"))
        session.execute(text(f"DROP TABLE IF EXISTS projects.{TABLE}"))
        yield session


def test_10_upgrade_adds_everything_and_is_idempotent(db):
    _run(db, "upgrade")
    _run(db, "upgrade")
    cp, issue_col, table = _state(db)
    assert CP_COLUMNS <= cp and issue_col and table
    cols = {c["name"] for c in inspect(db.get_bind()).get_columns(TABLE, schema="projects")}
    assert {"id", "company_id", "document_id", "certificate_id", "included", "source",
            "send_to_customer", "boxes", "created_at", "created_by", "updated_at"} <= cols


def test_10_downgrade_removes_everything_and_is_idempotent(db):
    _run(db, "upgrade")
    _run(db, "downgrade")
    _run(db, "downgrade")
    cp, issue_col, table = _state(db)
    assert not (CP_COLUMNS & cp) and not issue_col and not table
    _run(db, "upgrade")
    assert _state(db)[2]


def test_10_the_new_table_is_unique_per_document_and_certificate(db):
    _run(db, "upgrade")
    uniques = inspect(db.get_bind()).get_unique_constraints(TABLE, schema="projects")
    indexes = inspect(db.get_bind()).get_indexes(TABLE, schema="projects")
    sets = [set(u["column_names"]) for u in uniques] + [set(i["column_names"]) for i in indexes if i.get("unique")]
    assert {"document_id", "certificate_id"} in sets


def test_10_there_is_a_single_alembic_head_and_it_is_ours_or_a_descendant():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1
    revisions = {r.revision for r in script.walk_revisions()}
    assert "qcert_0001_quote_certificates" in revisions
    assert len("qcert_0001_quote_certificates") <= 32
