"""Migration `bcw_0001_brand_chatbot_weight` (owner console test of round 3 on PR #833, R1).

Replaces bcd_0001's `brands.is_chatbot_default` switch with a per-brand
`brands.chatbot_weight`. Seeds Sorento highest (1.5, the owner's own example value and
the brand preference already in `product_spec_registry.value_weights`): a brand that was
the default carries 1.5, and a company that had no default gets 1.5 on its Sorento rows.
Every other brand is 0. Then the switch column is dropped.

The body is plain idempotent SQL, so it also runs on the shared local database that
converges through `create_all` (backend CLAUDE.md). `pg_session` rolls every test back.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from tests._pg_fixture import pg_session, unique_code

# ALTER TABLE brands and an unbounded UPDATE on the shared schema: out of the xdist pool
# (tests/conftest.py `serial_ddl`; PR #833 round 5 S3).
pytestmark = pytest.mark.serial_ddl

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "bcw_0001_brand_chatbot_weight.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("zzt_migration_bcw_0001", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(_module(), direction)()


def _columns(db) -> set[str]:
    return {c["name"] for c in sa.inspect(db.connection()).get_columns("brands")}


def _company(db) -> str:
    return db.execute(text("SELECT id FROM companies ORDER BY created_at LIMIT 1")).scalar()


def _brand(db, name: str, *, company_id: str | None, default: bool = False) -> str:
    brand_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO brands (id, brand_code, brand_name, is_active, company_id, is_chatbot_default) "
            "VALUES (:id, :code, :name, true, :company, :default)"
        ),
        {"id": brand_id, "code": unique_code("BCW"), "name": name, "company": company_id, "default": default},
    )
    db.flush()
    return brand_id


def _weight(db, brand_id: str):
    return float(db.execute(text("SELECT chatbot_weight FROM brands WHERE id = :id"), {"id": brand_id}).scalar())


@pytest.fixture
def db():
    """A database in bcd_0001's shape: the switch column present, the weight absent."""
    with pg_session() as session:
        session.execute(text("UPDATE brands SET brand_name = brand_name || ' zzt-old' WHERE lower(brand_name) = 'sorento'"))
        session.execute(text("ALTER TABLE brands DROP COLUMN IF EXISTS chatbot_weight"))
        session.execute(text("ALTER TABLE brands ADD COLUMN IF NOT EXISTS is_chatbot_default BOOLEAN NOT NULL DEFAULT false"))
        session.execute(text("UPDATE brands SET is_chatbot_default = false"))
        yield session


def test_revision_id_fits_and_the_graph_has_one_head_that_descends_from_it():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    module = _module()
    assert len(module.revision) <= 32
    assert module.down_revision == "bcd_0001_brand_chatbot_default"
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())
    assert len(heads) == 1
    assert module.revision in {rev.revision for rev in script.walk_revisions(base="base", head=heads[0])}


def test_the_default_brand_becomes_the_highest_weight_and_the_switch_goes(db):
    company = _company(db)
    mocha = _brand(db, "Mocha", company_id=company, default=True)
    sorento = _brand(db, "Sorento", company_id=company)

    _run(db)

    assert "is_chatbot_default" not in _columns(db)
    col = next(c for c in sa.inspect(db.connection()).get_columns("brands") if c["name"] == "chatbot_weight")
    assert col["nullable"] is False
    # The company chose Mocha as its default in round 2; that choice is kept as the top weight.
    assert _weight(db, mocha) == 1.5
    assert _weight(db, sorento) == 0


def test_a_company_with_no_default_gets_sorento_highest(db):
    company = _company(db)
    sorento = _brand(db, "SORENTO", company_id=company)
    cabana = _brand(db, "Cabana", company_id=company)

    _run(db)

    assert _weight(db, sorento) == 1.5
    assert _weight(db, cabana) == 0


def test_the_body_runs_again_on_a_database_that_already_has_the_weight(db):
    """The shared local DB: `create_all` added `chatbot_weight`; staff already tuned one."""
    db.execute(text("ALTER TABLE brands ADD COLUMN IF NOT EXISTS chatbot_weight NUMERIC(6,2) NOT NULL DEFAULT 0"))
    company = _company(db)
    sorento = _brand(db, "Sorento", company_id=company)
    tuned = _brand(db, "Cabana", company_id=company)
    db.execute(text("UPDATE brands SET chatbot_weight = 0.5 WHERE id = :id"), {"id": tuned})

    _run(db)
    _run(db)

    assert _weight(db, tuned) == 0.5
    # A company whose staff already weighted a brand is left alone: no Sorento seed on top.
    assert _weight(db, sorento) == 0


def test_downgrade_restores_the_switch_on_the_top_weight(db):
    company = _company(db)
    sorento = _brand(db, "Sorento", company_id=company)
    _run(db)
    _run(db, "downgrade")
    assert "chatbot_weight" not in _columns(db)
    assert db.execute(text("SELECT is_chatbot_default FROM brands WHERE id = :id"), {"id": sorento}).scalar() is True
