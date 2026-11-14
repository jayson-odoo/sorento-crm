"""SEARCH-CHIPS round 2: trigram GIN indexes + a search clause the planner can serve from them.

Crew ruling: the Sales orders multi-value search seq-scanned `sales_orders` (13 s at 50 values on a
prod-size copy). A migration adds `gin_trgm_ops` indexes and the clause is rewritten so every OR arm
is indexable and the planner can take a BitmapOr (32 ms measured):

- no correlated EXISTS for the line/product arm or the agent arm, and the customer arm is not
  `customer.has(...)`: each becomes `<fk> = ANY(ARRAY(SELECT <target>.id ...))`;
- `sales_orders.so_number / debtor_name / project_label / po_ref / po_ref_key` keep one
  `(I)LIKE ANY` each.

Results must not change: tests/test_sales_order_search_chips.py stays green, and company scoping
still holds (covered here too). Red first: written before the migration and the rewrite exist.

Two substrates, both Postgres:
- `blank_session` (scratch schema built by create_all) for HTTP results and the clause shape;
- the lane's real migrated DB (`app.database.engine`, sorento_ci under `.env.ci-tests`) for the
  index catalogue and the plan, because the indexes come from the migration, not from the models.
Every row is seeded here and rolled back. Names are fake.
"""
from __future__ import annotations

import importlib.util
import re
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sales_agent import SalesAgent
from app.services.scm.po_ref import po_ref_key
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
LIST = "/api/v1/scm/sales-orders"

SO_COLUMNS = ["so_number", "debtor_name", "project_label", "po_ref", "po_ref_key"]
SHARED_COLUMNS = [("products", "product_code"), ("products", "product_name"),
                  ("customers", "customer_name")]
ALL_PAIRS = {("sales_orders", c) for c in SO_COLUMNS} | set(SHARED_COLUMNS)
PREFIX = "ix_search_trgm_"


def _u() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- #
# Locating and loading the migration module
# --------------------------------------------------------------------------- #

def _migration_path() -> Path:
    hits = []
    for path in sorted(VERSIONS.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "sales_orders" in src and "gin_trgm_ops" in src and "SEARCH-CHIPS" in src:
            hits.append(path)
    assert hits, ("no migration under alembic/versions mentions sales_orders + gin_trgm_ops + "
                  "SEARCH-CHIPS: the trigram index migration does not exist yet")
    assert len(hits) == 1, f"expected ONE SEARCH-CHIPS trigram migration, found {hits}"
    return hits[0]


def _load_migration():
    path = _migration_path()
    spec = importlib.util.spec_from_file_location(f"_search_trgm_mig_{uuid.uuid4().hex[:6]}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A recording stand-in for `alembic.op`, so upgrade()/downgrade() can be run without a database and
# every DDL they would issue is captured along with whether it ran inside `autocommit_block()`.

class _Recorder:
    def __init__(self):
        self.log: list[tuple[str, bool]] = []   # (sql, inside autocommit_block)
        self.autocommit = False

    def add(self, sql):
        self.log.append((re.sub(r"\s+", " ", str(sql)).strip(), self.autocommit))


class _FakeContext:
    def __init__(self, rec):
        self._rec = rec

    @contextmanager
    def autocommit_block(self):
        self._rec.autocommit = True
        try:
            yield
        finally:
            self._rec.autocommit = False


class _FakeBind:
    def __init__(self, rec):
        self._rec = rec

    def execute(self, sql, *_a, **_k):
        self._rec.add(sql)
        return MagicMock()

    def exec_driver_sql(self, sql, *_a, **_k):
        self._rec.add(sql)
        return MagicMock()

    def __getattr__(self, name):
        return MagicMock(name=f"bind.{name}")


class _FakeOp:
    def __init__(self, rec):
        self._rec = rec
        self._ctx = _FakeContext(rec)
        self._bind = _FakeBind(rec)

    def execute(self, sql, *_a, **_k):
        self._rec.add(sql)

    def get_context(self):
        return self._ctx

    def get_bind(self):
        return self._bind

    def create_index(self, name, table, columns, **kw):
        cols = ", ".join(str(c) for c in columns)
        ops = " ".join(str(v) for v in (kw.get("postgresql_ops") or {}).values())
        self._rec.add(
            "CREATE INDEX"
            + (" CONCURRENTLY" if kw.get("postgresql_concurrently") else "")
            + (" IF NOT EXISTS" if kw.get("if_not_exists") else "")
            + f" {name} ON {table} USING {kw.get('postgresql_using', 'btree')} ({cols} {ops})"
        )

    def drop_index(self, name, table_name=None, **kw):
        self._rec.add(
            "DROP INDEX"
            + (" CONCURRENTLY" if kw.get("postgresql_concurrently") else "")
            + (" IF EXISTS" if kw.get("if_exists") else "")
            + f" {name}"
        )

    def __getattr__(self, name):
        return MagicMock(name=f"op.{name}")


def _run(mig, monkeypatch, fn_name, covered=frozenset()):
    """Run upgrade()/downgrade() against the recording `op`. Returns the raw DDL log, the
    `_has_trgm_index` calls, and every (table, name, columns) tuple handed to
    `online_index.ensure_indexes_online` with whether it was handed over inside
    `autocommit_block()` (the owner rule of 27 Oct: indexes are built through that helper)."""
    from app.utils import online_index

    rec = _Recorder()
    monkeypatch.setattr(mig, "op", _FakeOp(rec))
    calls: list[tuple[str, str]] = []
    handed: list[tuple[tuple[str, str, str], bool]] = []

    def _fake_has(_bind, table, column):
        calls.append((table, column))
        return (table, column) in covered

    def _spy_ensure(_bind, indexes):
        handed.extend((tuple(t), rec.autocommit) for t in indexes)
        return True

    monkeypatch.setattr(mig, "_has_trgm_index", _fake_has)
    monkeypatch.setattr(online_index, "ensure_indexes_online", _spy_ensure)
    if hasattr(mig, "ensure_indexes_online"):  # imported by name rather than through the module
        monkeypatch.setattr(mig, "ensure_indexes_online", _spy_ensure)
    getattr(mig, fn_name)()
    return rec.log, calls, handed


def _trgm_tuple(t):
    """(table, column) a handed-over (table, name, columns) tuple builds a plain trigram index on."""
    table, _name, columns = t
    m = re.fullmatch(r'\s*USING gin\s*\(\s*"?(\w+)"?\s+gin_trgm_ops\s*\)\s*', columns, re.I)
    return (table, m.group(1)) if m else None


_CREATE = re.compile(
    r"CREATE INDEX (?P<conc>CONCURRENTLY )?(?P<ine>IF NOT EXISTS )?\"?(?P<name>\w+)\"? ON (?:ONLY )?"
    r"(?:\"?\w+\"?\.)?\"?(?P<table>\w+)\"? USING gin ?\( ?\"?(?P<column>\w+)\"? gin_trgm_ops ?\)",
    re.I,
)
_DROP = re.compile(
    r"DROP INDEX (?P<conc>CONCURRENTLY )?(?P<ie>IF EXISTS )?(?:\"?\w+\"?\.)?\"?(?P<name>\w+)\"?", re.I
)


def _creates(log):
    return [(m, auto) for sql, auto in log for m in [_CREATE.search(sql)] if m]


def _drops(log):
    return [(m, auto) for sql, auto in log for m in [_DROP.search(sql)] if m]


# --------------------------------------------------------------------------- #
# 1. The migration module: revision chain + the DDL it issues
# --------------------------------------------------------------------------- #

def test_m1_revision_id_fits_alembic_version_column():
    mig = _load_migration()
    assert isinstance(mig.revision, str) and mig.revision
    assert len(mig.revision) <= 32, mig.revision


def test_m1_is_an_ancestor_of_the_single_head_and_chains_onto_the_previous_head():
    """The head moves with every migration PR, so this never names it: it only asserts the
    chain has exactly ONE head and that this migration is on the path to it."""
    mig = _load_migration()
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(cfg)

    heads = script.get_heads()
    assert len(heads) == 1, heads
    ancestors = {rev.revision for rev in script.iterate_revisions(heads[0], "base")}
    assert mig.revision in ancestors, (mig.revision, heads[0])
    assert isinstance(mig.down_revision, str), "a single parent, not a merge"
    assert script.get_revision(mig.down_revision) is not None
    # The parent was a head before this migration: nothing else builds on it.
    children = [
        rev.revision for rev in script.walk_revisions()
        if mig.down_revision in (
            rev.down_revision if isinstance(rev.down_revision, tuple) else (rev.down_revision,)
        )
    ]
    assert children == [mig.revision], children


def test_m1_source_uses_concurrently_inside_autocommit_block():
    mig = _load_migration()
    src = _migration_path().read_text(encoding="utf-8")
    assert "autocommit_block" in src
    assert re.search(r"CONCURRENTLY", src), "indexes must be built CONCURRENTLY"
    assert re.search(r"CREATE EXTENSION IF NOT EXISTS pg_trgm", src, re.I)
    assert "IF NOT EXISTS" in src and "IF EXISTS" in src
    assert callable(getattr(mig, "_has_trgm_index", None))


def test_m1_upgrade_hands_every_index_to_online_index_when_none_exists(monkeypatch):
    """Round 3 (owner rule 27 Oct, `app/utils/online_index.py`): the build goes through
    `ensure_indexes_online` inside `autocommit_block()`, which itself always uses
    CREATE INDEX CONCURRENTLY IF NOT EXISTS under the migration limits; the migration issues no
    CREATE INDEX of its own."""
    mig = _load_migration()
    log, calls, handed = _run(mig, monkeypatch, "upgrade")

    assert any(re.search(r"CREATE EXTENSION IF NOT EXISTS \"?pg_trgm\"?", sql, re.I) for sql, _ in log), log
    assert not _creates(log), f"raw CREATE INDEX issued instead of online_index: {_creates(log)}"
    assert handed, "nothing handed to online_index.ensure_indexes_online"
    built = [_trgm_tuple(t) for t, _ in handed]
    assert None not in built, [t for t, _ in handed]
    assert set(built) == ALL_PAIRS, handed
    assert len(built) == len(ALL_PAIRS), "one index per column"
    for (table, name, _columns), inside in handed:
        assert inside, f"ensure_indexes_online called outside autocommit_block: {name}"
        assert name.startswith(PREFIX), name
        assert len(name) <= 63, name
    # The shared tables were checked before being indexed.
    assert set(SHARED_COLUMNS) <= set(calls), calls


def test_m1_upgrade_skips_shared_columns_already_covered(monkeypatch):
    """Prod may carry migration 169's idx_products_*_trgm / idx_customers_*_trgm: no duplicate."""
    mig = _load_migration()
    log, _, handed = _run(mig, monkeypatch, "upgrade", covered=frozenset(SHARED_COLUMNS))
    assert not _creates(log), _creates(log)
    assert {_trgm_tuple(t) for t, _ in handed} == {("sales_orders", c) for c in SO_COLUMNS}, handed


def test_m1_downgrade_drops_only_its_own_indexes_concurrently(monkeypatch):
    mig = _load_migration()
    _, _, handed = _run(mig, monkeypatch, "upgrade")
    created_names = {t[1] for t, _ in handed}
    assert created_names

    log, _, _ = _run(mig, monkeypatch, "downgrade")
    drops = _drops(log)
    assert drops, log
    for m, inside in drops:
        assert m["name"].startswith(PREFIX), f"drops an index it does not own: {m['name']}"
        assert m["conc"], f"not CONCURRENTLY: {m.group(0)}"
        assert m["ie"], f"no IF EXISTS: {m.group(0)}"
        assert inside, f"CONCURRENTLY outside autocommit_block: {m.group(0)}"
    assert created_names <= {m["name"] for m, _ in drops}
    assert not any(re.search(r"DROP EXTENSION", sql, re.I) for sql, _ in log), \
        "pg_trgm is shared with other features: never dropped"


# --------------------------------------------------------------------------- #
# 2. The real migrated DB: indexes present; the "already covered" helper
# --------------------------------------------------------------------------- #

_TRGM_COLUMNS_SQL = text("""
    SELECT t.relname AS tbl, a.attname AS col, c.relname AS idx
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_class t ON t.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    JOIN pg_opclass oc ON oc.oid = i.indclass[0]
    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = i.indkey[0]
    WHERE n.nspname = current_schema()
      AND oc.opcname = 'gin_trgm_ops'
      AND i.indnatts = 1
      AND t.relname = ANY(:tables)
""")


def _trgm_index_by_column(conn) -> dict[tuple[str, str], list[str]]:
    out: dict[tuple[str, str], list[str]] = {}
    for tbl, col, idx in conn.execute(
        _TRGM_COLUMNS_SQL, {"tables": ["sales_orders", "products", "customers"]}
    ):
        out.setdefault((tbl, col), []).append(idx)
    return out


@pytest.fixture(scope="module")
def search_indexes_applied():
    """The migration's own upgrade body, applied to the test DB first.

    CI and the release sweep build the test DB with `scripts.bootstrap_env` (create_all + stamp),
    so `so_search_trgm_0001` never runs there and its indexes do not exist. This runs the same
    steps the migration does (its `_has_trgm_index`, then `online_index.ensure_indexes_online`),
    which is a no-op on a DB alembic already migrated."""
    from app.database import engine
    from app.utils import online_index

    mig = _load_migration()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        wanted = online_index.SALES_ORDER_SEARCH_INDEXES + tuple(
            index for index in mig.SHARED_INDEXES
            if not mig._has_trgm_index(conn, index[0], mig._column(index[2]))
        )
        assert online_index.ensure_indexes_online(conn, wanted), "search indexes did not build"


def test_d2_migrated_db_has_a_plain_trgm_index_on_every_searched_column(search_indexes_applied):
    from app.database import engine

    with engine.connect() as conn:
        found = _trgm_index_by_column(conn)
    missing = sorted(pair for pair in ALL_PAIRS if pair not in found)
    assert not missing, f"no plain-column gin_trgm_ops index on {missing} (found {found})"


@pytest.fixture
def probe_conn():
    from app.database import engine

    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


def test_d2_has_trgm_index_decides_coverage_per_table_and_column(probe_conn):
    mig = _load_migration()
    a = f"zz_trgm_probe_a_{uuid.uuid4().hex[:8]}"
    b = f"zz_trgm_probe_b_{uuid.uuid4().hex[:8]}"
    c = probe_conn
    c.execute(text(f"CREATE TABLE {a} (id int primary key, trgm_col text, btree_col text, "
                   f"expr_col text, plain text, plain_x text)"))
    c.execute(text(f"CREATE TABLE {b} (id int primary key, plain text)"))
    c.execute(text(f"CREATE INDEX {a}_t ON {a} USING gin (trgm_col gin_trgm_ops)"))
    c.execute(text(f"CREATE INDEX {a}_b ON {a} (btree_col)"))
    # Migration 410's shape (prod carries one on customers.customer_name): an EXPRESSION index
    # serves the normalised resolver lookups, not `customer_name ILIKE ...`, so it does NOT cover
    # the column. Counting it as covered would leave prod's customers arm on a seq scan.
    c.execute(text(f"CREATE INDEX {a}_e ON {a} USING gin "
                   f"((lower(regexp_replace(expr_col, '[-\\s]+', '', 'g'))) gin_trgm_ops)"))
    c.execute(text(f"CREATE INDEX {a}_px ON {a} USING gin (plain_x gin_trgm_ops)"))
    c.execute(text(f"CREATE INDEX {b}_p ON {b} USING gin (plain gin_trgm_ops)"))

    assert mig._has_trgm_index(c, a, "trgm_col") is True
    assert mig._has_trgm_index(c, a, "btree_col") is False      # not a trigram index
    assert mig._has_trgm_index(c, a, "expr_col") is False       # expression, not the column
    assert mig._has_trgm_index(c, a, "plain") is False          # only plain_x / other table
    assert mig._has_trgm_index(c, b, "plain") is True


def test_d2_has_trgm_index_ignores_an_invalid_index(probe_conn):
    """An interrupted CONCURRENTLY build leaves an INVALID index the planner never uses. Counting it
    as covering the column would skip the build for good, and the search stays a seq scan."""
    mig = _load_migration()
    a = f"zz_trgm_probe_i_{uuid.uuid4().hex[:8]}"
    c = probe_conn
    c.execute(text(f"CREATE TABLE {a} (id int primary key, col text)"))
    c.execute(text(f"CREATE INDEX {a}_t ON {a} USING gin (col gin_trgm_ops)"))
    assert mig._has_trgm_index(c, a, "col") is True  # guard: valid, it counts
    c.execute(text(f"UPDATE pg_index SET indisvalid = false WHERE indexrelid = '{a}_t'::regclass"))
    assert mig._has_trgm_index(c, a, "col") is False


# --------------------------------------------------------------------------- #
# Round 3: the owner rule of 27 Oct for online index builds (app/utils/online_index.py)
# --------------------------------------------------------------------------- #

_SCRATCH_DDL = (
    'CREATE TABLE {s}.sales_orders (id uuid PRIMARY KEY, so_number varchar(100), '
    'debtor_name varchar(255), project_label text, po_ref varchar(255), po_ref_key varchar(255))',
    'CREATE TABLE {s}.products (id uuid PRIMARY KEY, product_code varchar(100), product_name varchar(255))',
    'CREATE TABLE {s}.customers (id uuid PRIMARY KEY, customer_name varchar(255))',
)


@contextmanager
def _scratch():
    """A committed scratch schema with the three searched tables, so the real upgrade (CONCURRENTLY
    needs autocommit) never touches the lane DB's own tables. `public` trails it on search_path
    for pg_trgm's operator class."""
    import os

    from app.database import engine

    schema = f"zzs_sotrgm_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        try:
            for ddl in _SCRATCH_DDL:
                conn.exec_driver_sql(ddl.format(s=f'"{schema}"'))
            yield schema, conn
        finally:
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def _scratch_index(conn, schema, name):
    """indisvalid of `name` in `schema`, or None when there is no such index."""
    return conn.execute(
        text("SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
             "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = :s AND c.relname = :n"),
        {"s": schema, "n": name},
    ).scalar()


def _scratch_trgm_names(conn, schema):
    return {r[0] for r in conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND indexname LIKE 'ix_search_trgm%'"),
        {"s": schema},
    )}


def _real_upgrade(mig, schema, step="upgrade"):
    """upgrade() as `alembic/env.py` runs it: a transactional MigrationContext on its own
    connection, search_path on the scratch schema. A 3 s lock_timeout is a safety net so a raw
    CONCURRENTLY build stuck behind live work fails instead of hanging the suite
    (`ensure_index_online` sets and restores its own limits around each build)."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from app.database import engine

    with engine.connect() as conn:
        try:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx), ctx.begin_transaction():
                conn.exec_driver_sql(f'SET search_path TO "{schema}", public')
                conn.exec_driver_sql("SET lock_timeout = '3s'")
                conn.exec_driver_sql("SET statement_timeout = '60s'")
                getattr(mig, step)()
        finally:
            conn.rollback()
            conn.exec_driver_sql("RESET search_path")
            conn.exec_driver_sql("RESET lock_timeout")
            conn.exec_driver_sql("RESET statement_timeout")
            conn.commit()


def test_o1_real_upgrade_builds_nothing_itself_and_hands_everything_to_online_index(monkeypatch):
    """Through a real alembic context: with `ensure_indexes_online` stubbed out, no ix_search_trgm_*
    index may appear, i.e. every build goes through the helper (and its limits / warning path)."""
    from app.utils import online_index

    mig = _load_migration()
    handed: list[tuple] = []
    monkeypatch.setattr(online_index, "ensure_indexes_online",
                        lambda _bind, indexes: handed.extend(indexes) or True)
    with _scratch() as (schema, conn):
        _real_upgrade(mig, schema)
        assert _scratch_trgm_names(conn, schema) == set(), "built outside online_index"
    assert {_trgm_tuple(tuple(t)) for t in handed} == ALL_PAIRS, handed


def test_o1_real_upgrade_builds_every_index_valid():
    """Coverage: unstubbed, the eight indexes come out VALID in the scratch schema."""
    mig = _load_migration()
    with _scratch() as (schema, conn):
        _real_upgrade(mig, schema)
        names = _scratch_trgm_names(conn, schema)
        assert len(names) == len(ALL_PAIRS), names
        assert all(_scratch_index(conn, schema, n) is True for n in names), names


@contextmanager
def _open_writer(schema, table):
    """Live work: a transaction that wrote a row to `table` and has not committed."""
    from app.database import engine

    with engine.connect() as other:
        tx = other.begin()
        other.exec_driver_sql(f"INSERT INTO \"{schema}\".{table} (id) VALUES ('{uuid.uuid4()}')")
        try:
            yield
        finally:
            tx.rollback()


def test_o1_a_build_stuck_behind_live_work_is_a_warning_not_an_error(monkeypatch, caplog):
    """The revision still SUCCEEDS when its sales_orders builds cannot finish: the leftover is
    gone or INVALID, a WARNING names it, and the retry script builds it on the next start."""
    import logging

    mig = _load_migration()
    monkeypatch.setenv("MIGRATION_LOCK_TIMEOUT", "300ms")
    caplog.set_level(logging.WARNING)
    with _scratch() as (schema, conn):
        with _open_writer(schema, "sales_orders"):
            _real_upgrade(mig, schema)  # must not raise
            for col in SO_COLUMNS:
                left = _scratch_index(conn, schema, f"{PREFIX}sales_orders_{col}")
                assert left is None or left is False, (col, left)
    warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(f"{PREFIX}sales_orders" in m for m in warned), warned


def test_o1_retry_script_carries_the_sales_orders_indexes(monkeypatch):
    """A build the migration could not finish is retried on the next backend start
    (`scripts/ensure_goods_chain_indexes.py`, run by start.sh), like il_0001/il_0002's."""
    from app.database import engine
    from app.utils import online_index
    from scripts import ensure_goods_chain_indexes as retry

    mig = _load_migration()
    _, _, handed = _run(mig, monkeypatch, "upgrade")
    mig_names = {t[1] for t, _ in handed if t[0] == "sales_orders"}
    assert len(mig_names) == len(SO_COLUMNS), handed

    captured: list[tuple] = []
    monkeypatch.setattr(online_index, "ensure_indexes_online",
                        lambda _bind, indexes: captured.extend(tuple(t) for t in indexes) or True)
    monkeypatch.setattr(online_index, "ensure_search_index_online", lambda _bind: True)
    assert retry.run(engine) is True
    retried = {t for t in captured if t[0] == "sales_orders" and t[1].startswith(PREFIX)}
    assert {_trgm_tuple(t) for t in retried} == {("sales_orders", c) for c in SO_COLUMNS}, captured
    assert {t[1] for t in retried} == mig_names, "retry and migration must name the same indexes"


# --------------------------------------------------------------------------- #
# Seeding (shared by the blank-schema and real-DB tests)
# --------------------------------------------------------------------------- #

def _so(db, number, **kw):
    row = SalesOrder(id=_u(), so_number=number, status=kw.pop("status", "open"),
                     order_date=kw.pop("order_date", date(2026, 6, 1)), **kw)
    db.add(row)
    db.flush()
    return row


def _line(db, so, product):
    db.add(SalesOrderLine(id=_u(), sales_order_id=so.id, product_id=product.id,
                          qty_ordered=1, qty_delivered=0, line_status="open",
                          company_id=so.company_id))
    db.flush()


def _product(db, tag, code, name, company_id=None):
    cat = ProductCategory(id=_u(), category_code=unique_code("CAT"), category_name=f"{tag} cat",
                          company_id=company_id)
    uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{tag} u",
                        company_id=company_id)
    db.add_all([cat, uom])
    db.flush()
    p = Product(id=_u(), product_code=code, product_name=name, category_id=cat.id,
                base_uom_id=uom.id, list_price=0, is_active=True, is_discontinued=False,
                company_id=company_id)
    db.add(p)
    db.flush()
    return p


def _seed(db):
    tag = unique_code("SIX", alpha=True)
    widget = _product(db, tag, f"{tag}PWIDGET", f"{tag} Gizmo Widget")
    cust = Customer(id=_u(), customer_code=unique_code("CA"), customer_name=f"{tag} Fakeco Holdings")
    agent = SalesAgent(id=_u(), sales_agent=unique_code("AGT"), person_label=f"{tag} AGENTPERSON",
                       is_active=True)
    db.add_all([cust, agent])
    db.flush()
    s = dict(tag=tag, widget=widget, cust=cust, agent=agent)
    s["alpha"] = _so(db, f"{tag}-ALPHA")
    s["by_customer"] = _so(db, f"{tag}-FOXTROT", customer_id=cust.id)
    s["by_line"] = _so(db, f"{tag}-GOLF")
    _line(db, s["by_line"], widget)
    s["by_agent"] = _so(db, f"{tag}-HOTEL", sales_agent_id=agent.id)
    s["by_project"] = _so(db, f"{tag}-INDIA", project_label=f"{tag} BAMBOOPROJECT")
    s["by_po"] = _so(db, f"{tag}-JULIET", po_ref="PO-4500 123", po_ref_key=po_ref_key("PO-4500 123"))
    return s


def _capture(db):
    statements: list[tuple[str, object]] = []
    conn = db.connection()

    def _before(_conn, _cursor, statement, params, _context, _many):
        statements.append((statement, params))

    event.listen(conn, "before_cursor_execute", _before)
    return conn, _before, statements


# --------------------------------------------------------------------------- #
# 3. Clause shape (blank schema, through the route like B8)
# --------------------------------------------------------------------------- #

@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _searching_sql(client, db, pairs) -> list[str]:
    conn, hook, statements = _capture(db)
    try:
        resp = get(client, LIST, pairs)
    finally:
        event.remove(conn, "before_cursor_execute", hook)
    assert resp.status_code == 200, resp.text
    return [st for st, _ in statements if re.search(r"\bsales_orders\b", st)
            and re.search(r"\bilike\b", st, re.I)]


def test_c3_baseline_list_sql_has_no_exists_without_a_search(client, db):
    """Guard: the list without a search carries no EXISTS, so any EXISTS below is the search's."""
    conn, hook, statements = _capture(db)
    try:
        resp = get(client, LIST, [("limit", 50)])
    finally:
        event.remove(conn, "before_cursor_execute", hook)
    assert resp.status_code == 200, resp.text
    listing = [st for st, _ in statements if re.search(r"\bFROM\b[^;]*\bsales_orders\b", st)]
    assert listing
    assert not any(re.search(r"\bEXISTS\b", st, re.I) for st in listing), listing


def test_c3_search_clause_uses_any_array_subselects_and_no_exists(client, db):
    sqls = _searching_sql(client, db, [("limit", 50), ("query", "ZZA1"), ("query", "ZZB2")])
    assert sqls, "the search statement was not captured"
    # `func.array(select(...).scalar_subquery())` renders `ANY (array((SELECT ...)))`: both spellings
    # are the ARRAY(subquery) constructor to Postgres, so the regexes accept the extra parenthesis.
    for st in sqls:
        assert not re.search(r"\bEXISTS\b", st, re.I), f"correlated EXISTS still in the search:\n{st}"
        assert re.search(r"\bcustomer_id\s*=\s*ANY\s*\(\s*ARRAY\s*\(\s*\(?\s*SELECT\s+[\w\".]*\bcustomers\.id\b",
                         st, re.I), st
        assert re.search(r"\bsales_agent_id\s*=\s*ANY\s*\(\s*ARRAY\s*\(\s*\(?\s*SELECT\s+[\w\".]*\bsales_agents\.id\b",
                         st, re.I), st
        assert re.search(r"\bsales_orders\.id\s*=\s*ANY\s*\(\s*ARRAY\s*\(\s*\(?\s*SELECT\s+[\w\".]*"
                         r"\bsales_order_lines\.sales_order_id\b", st, re.I), st
        assert re.search(r"\bproduct_id\s*=\s*ANY\s*\(\s*ARRAY\s*\(\s*\(?\s*SELECT\s+[\w\".]*\bproducts\.id\b",
                         st, re.I), st
        for col in ["so_number", "debtor_name", "project_label", "po_ref"]:
            n = len(re.findall(rf"\bsales_orders\.{col}\s+ILIKE\s+ANY\b", st, re.I))
            assert n == 1, f"{col}: {n} ILIKE ANY\n{st}"
        n = len(re.findall(r"\bsales_orders\.po_ref_key\s+I?LIKE\s+ANY\b", st, re.I))
        assert n == 1, f"po_ref_key: {n} LIKE ANY\n{st}"


# --------------------------------------------------------------------------- #
# Results unchanged, company scoping included (green before and after: guards)
# --------------------------------------------------------------------------- #

OTHER_CO = "00000000-0000-0000-0000-00000000c0b2"


@pytest.fixture
def two_companies(db):
    s = _seed(db)
    tag = s["tag"]
    db.add(Company(id=OTHER_CO, name="ZZT Otherco", code=unique_code("OCO")[:20]))
    db.flush()
    foreign_product = _product(db, tag, f"{tag}PFOREIGN", f"{tag} Foreignwidget", company_id=OTHER_CO)
    foreign_cust = Customer(id=_u(), customer_code=unique_code("CF"),
                            customer_name=f"{tag} Foreignco Pty", company_id=OTHER_CO)
    db.add(foreign_cust)
    db.flush()
    # An order of the OTHER company that every search arm would match.
    s["other_order"] = _so(db, f"{tag}-OTHERCO", company_id=OTHER_CO, customer_id=foreign_cust.id,
                           sales_agent_id=s["agent"].id, debtor_name=f"{tag} Acme Foreign",
                           project_label=f"{tag} BAMBOOPROJECT", po_ref="PO-4500 123",
                           po_ref_key=po_ref_key("PO-4500 123"))
    _line(db, s["other_order"], foreign_product)
    _line(db, s["other_order"], s["widget"])
    s["foreign_product"], s["foreign_cust"] = foreign_product, foreign_cust
    return s


def _numbers(client, values):
    resp = get(client, LIST, [("limit", 200), *[("query", v) for v in values]])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pagination"]["total"] == len(body["data"]), "count and rows disagree"
    return {r["so_number"] for r in body["data"]}


def test_r_every_arm_still_finds_its_row(client, two_companies):
    s = two_companies
    got = _numbers(client, [f"{s['tag']}-ALPHA", "Fakeco Holdings", "Gizmo Widget", "AGENTPERSON",
                            "BAMBOOPROJECT", "po 4500-123"])
    assert got == {s[k].so_number for k in
                   ("alpha", "by_customer", "by_line", "by_agent", "by_project", "by_po")}


def test_r_another_companys_order_never_leaks_through_any_arm(client, two_companies):
    s = two_companies
    values = [f"{s['tag']}-OTHERCO", "Foreignco", "Foreignwidget", s["foreign_product"].product_code,
              "Acme Foreign", s["widget"].product_code, "AGENTPERSON", "BAMBOOPROJECT", "po 4500-123"]
    assert s["other_order"].so_number not in _numbers(client, values)


@pytest.mark.parametrize("which", ["customer", "product"])
def test_r_own_order_pointing_at_another_companys_party_is_not_found_by_its_name(
        client, db, two_companies, which):
    """Reviewer probe: an order in the user's own company whose customer_id / line points at
    ANOTHER company's customer / product. Searching by that foreign name finds nothing: no row
    AND total 0 (before the rewrite the rows query found it while the count said 0)."""
    s = two_companies
    own = _so(db, f"{s['tag']}-CROSS", customer_id=s["foreign_cust"].id)
    _line(db, own, s["foreign_product"])
    value = {"customer": "Foreignco Pty", "product": "Foreignwidget"}[which]
    resp = get(client, LIST, [("limit", 200), ("query", value)])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["so_number"] for r in body["data"]] == [], body["data"]
    assert body["pagination"]["total"] == 0


# --------------------------------------------------------------------------- #
# 4. Plan: the migrated DB can serve the search from the trigram indexes
# --------------------------------------------------------------------------- #

@pytest.fixture
def real_db():
    """A rolled-back session on the lane's migrated DB, in the all-companies scope (`None`).

    Why not the Sorento scope: on a near-empty table the planner always prefers
    `ix_sales_orders_company_id` + a Filter over a BitmapOr (measured, even with 400 analysed
    rows and `enable_seqscan = off`), so the plan would say nothing about the search arms. In
    prod Sorento is the incumbent company, so that predicate is not selective there. With no
    company predicate the ONLY alternative to a seq scan is a BitmapOr over every OR arm, which is
    exactly the property under test: one non-indexable arm (a correlated EXISTS) forces the
    seq scan back. Inserts still stamp the incumbent company under `None`."""
    import app.main  # noqa: F401  registers the company-scope + lookup listeners
    from app.database import engine
    from app.models.base import set_company_scope

    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    set_company_scope(session, None)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


def test_p4_count_query_uses_bitmap_trgm_indexes_not_a_seq_scan(search_indexes_applied, real_db):
    from app.services.scm.sales_order_service import SalesOrderService

    db = real_db
    db.execute(text("SET LOCAL enable_seqscan = off"))
    forced = "\n".join(r[0] for r in db.execute(
        text("EXPLAIN SELECT id FROM sales_orders WHERE id = '00000000-0000-0000-0000-000000000000'")))
    if "Seq Scan" in forced:
        pytest.skip(f"planner cannot be forced off a seq scan here:\n{forced}")

    s = _seed(db)
    found = _trgm_index_by_column(db.connection())
    so_index_names = [n for c in SO_COLUMNS for n in found.get(("sales_orders", c), [])]

    conn, hook, statements = _capture(db)
    try:
        SalesOrderService(db).list(page=1, limit=50, sort=None, direction="asc",
                                   query=[f"{s['tag']}-ALPHA", "Gizmo Widget", "AGENTPERSON"],
                                   status=None, priority=None)
    finally:
        event.remove(conn, "before_cursor_execute", hook)
    counts = [(st, p) for st, p in statements if re.match(r"\s*SELECT count\(\*\)", st, re.I)]
    assert counts, [st[:120] for st, _ in statements]
    statement, params = counts[0]

    plan = "\n".join(r[0] for r in db.connection().exec_driver_sql("EXPLAIN " + statement, params))
    assert "Seq Scan on sales_orders" not in plan, plan
    assert "BitmapOr" in plan, plan
    assert so_index_names, f"no trigram index on sales_orders to plan with ({found})"
    for name in so_index_names:
        assert name in plan, f"{name} not used:\n{plan}"
