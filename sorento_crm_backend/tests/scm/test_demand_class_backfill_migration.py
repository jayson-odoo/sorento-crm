"""Migration 425: nothing is unclassified, and Friday's first upload still works.

QP1 refuses an SO upload naming an order whose class nothing can decide. That ruling has a
trap in it, and this file is the guard on the trap: the real AutoCount export carries no
order type column, so a book classifies through the DEBTOR'S MARKET SEGMENT alone. Stamping
the orders retail and leaving their customers unclassified would pass every existing test
and refuse the very next upload of the same book.

So 425 stamps both, and both halves are asserted here - together with the two exceptions
that make it safe to run: a customer who already states a segment is left alone, and the
downgrade puts a NULL back on exactly the rows the migration wrote and nothing else.

Postgres, in the shared blank schema, inside a rolled-back transaction. The migration's two
bookkeeping tables are schema-qualified, so they are rebound onto this session's scratch
`scm` schema the way `test_committed_v_migration_chain.py` rebinds the view - a test must
not create a real table in the live `scm` schema even for the length of a transaction.
"""
import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session
from tests.scm.conftest import requires_pg

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

MARKER = "ZZT425"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


@pytest.fixture()
def world():
    """A blank schema, the migration bound to it, and one company to hang rows off."""
    with blank_session() as db:
        scratch = db.execute(text("select current_schema()")).scalar()
        m425 = _load("425_sales_orders_class_backfill")
        m425._ORDERS = f'"{scratch}_scm".demand_class_backfill_425'
        m425._CUSTOMERS = f'"{scratch}_scm".market_segment_backfill_425'

        company = db.execute(text("select id from companies where code = 'SRT'")).scalar()
        db.execute(text(
            "INSERT INTO market_segments (id, code, name, is_active) "
            "VALUES (:i, 'project', 'Project', true) ON CONFLICT (code) DO NOTHING"
        ), {"i": _u()})
        db.flush()
        yield {"db": db, "m425": m425, "company": company}


def _customer(db, company, *, segment=None) -> tuple[str, str]:
    cid, code = _u(), _code("C")[:30]
    db.execute(text(
        "INSERT INTO customers (id, company_id, customer_code, customer_name, is_active, "
        "market_segment_code, created_at, updated_at) "
        "VALUES (:i, :co, :c, :c, true, :seg, now(), now())"
    ), {"i": cid, "co": company, "c": code, "seg": segment})
    db.flush()
    return cid, code


def _order(db, company, *, customer_id=None, debtor_code=None, demand_class=None,
           status="open") -> str:
    oid = _u()
    db.execute(text(
        "INSERT INTO sales_orders (id, company_id, so_number, status, demand_class, "
        "customer_id, debtor_code, created_at, updated_at) "
        "VALUES (:i, :co, :n, :s, :dc, :cu, :d, now(), now())"
    ), {"i": oid, "co": company, "n": _code("SO")[:50], "s": status, "dc": demand_class,
        "cu": customer_id, "d": debtor_code})
    db.flush()
    return oid


def _run(world, direction="upgrade") -> None:
    db = world["db"]
    conn = db.connection()
    ops = Operations(MigrationContext.configure(conn))
    import alembic.op as op_module

    op_module._proxy = ops
    getattr(world["m425"], direction)()


def _class_of(db, order_id):
    return db.execute(text("SELECT demand_class FROM sales_orders WHERE id = :i"),
                      {"i": order_id}).scalar()


def _segment_of(db, customer_id):
    return db.execute(text("SELECT market_segment_code FROM customers WHERE id = :i"),
                      {"i": customer_id}).scalar()


@requires_pg
def test_it_stamps_the_order_and_the_customer_that_order_names(world):
    """Both halves, which is the whole point: the order gets a class AND its debtor gets a
    segment, so the next upload of the same book classifies instead of being refused."""
    db, company = world["db"], world["company"]
    customer, _code_ = _customer(db, company)
    order = _order(db, company, customer_id=customer)

    _run(world)

    assert _class_of(db, order) == "retail"
    assert _segment_of(db, customer) == "retail"


@requires_pg
def test_a_customer_named_only_by_a_debtor_code_is_stamped_too(world):
    """A history-absorbed order carries the code and no link. The book still names that
    debtor, so the segment has to reach it."""
    db, company = world["db"], world["company"]
    customer, code = _customer(db, company)
    order = _order(db, company, debtor_code=code)

    _run(world)

    assert _class_of(db, order) == "retail"
    assert _segment_of(db, customer) == "retail"


@requires_pg
def test_a_customer_of_another_company_holding_the_same_code_is_never_touched(world):
    """`customers.customer_code` is unique per COMPANY, not globally - fourteen debtor codes
    on the live book resolve to 123 rows across nine companies. Classifying another
    company's buyer off this company's order is the mis-prioritisation the column exists to
    prevent."""
    db, company = world["db"], world["company"]
    other = db.execute(text(
        "INSERT INTO companies (id, code, name, is_active) "
        "VALUES (:i, :c, :c, true) RETURNING id"
    ), {"i": _u(), "c": _code("CO")[:20]}).scalar()
    mine, code = _customer(db, company)
    theirs = db.execute(text(
        "INSERT INTO customers (id, company_id, customer_code, customer_name, is_active, "
        "created_at, updated_at) VALUES (:i, :co, :c, :c, true, now(), now()) RETURNING id"
    ), {"i": _u(), "co": other, "c": code}).scalar()
    _order(db, company, debtor_code=code)

    _run(world)

    assert _segment_of(db, mine) == "retail"
    assert _segment_of(db, theirs) is None, "another company's buyer was reclassified"


@requires_pg
def test_a_customer_who_already_states_a_segment_is_left_alone(world):
    """300-F004 on the live book states `project` and still has an unclassified order.
    Overwriting that would silently demote a project buyer on the strength of an order
    somebody forgot to classify."""
    db, company = world["db"], world["company"]
    customer, _c = _customer(db, company, segment="project")
    order = _order(db, company, customer_id=customer)

    _run(world)

    assert _class_of(db, order) == "retail", "the ORDER is still stamped"
    assert _segment_of(db, customer) == "project", "the customer's own answer stands"


@requires_pg
def test_a_closed_order_is_stamped_too(world):
    """No plan reads one, but every trailing-window report and classification study reads
    the same column - 11,006 closed rows on the dev copy would answer "unclassified" for
    ever."""
    db, company = world["db"], world["company"]
    customer, _c = _customer(db, company)
    order = _order(db, company, customer_id=customer, status="closed")

    _run(world)

    assert _class_of(db, order) == "retail"


@requires_pg
def test_the_downgrade_restores_only_what_the_upgrade_wrote(world):
    """The reason there are two bookkeeping tables. A row classified before this migration
    ran is somebody's decision, and "set every retail row to NULL" would delete it."""
    db, company = world["db"], world["company"]
    stamped_customer, _c1 = _customer(db, company)
    stamped_order = _order(db, company, customer_id=stamped_customer)

    _run(world)

    # Classified by somebody else, AFTER the migration ran and with the same words it
    # writes - so only the bookkeeping tables can tell the two apart. (Seeded here rather
    # than up front because the `retail` segment row does not exist until the migration
    # creates it: a blank schema carries no migration seeds.)
    prior_customer, _c2 = _customer(db, company, segment="retail")
    prior_order = _order(db, company, customer_id=prior_customer, demand_class="retail")

    _run(world, "downgrade")

    assert _class_of(db, stamped_order) is None
    assert _segment_of(db, stamped_customer) is None
    assert _class_of(db, prior_order) == "retail", "a prior classification was deleted"
    assert _segment_of(db, prior_customer) == "retail", "a prior segment was deleted"


@requires_pg
def test_running_it_twice_changes_nothing_more(world):
    """Idempotent: the second pass finds no NULL left to stamp, and the bookkeeping tables
    do not grow a duplicate."""
    db, company = world["db"], world["company"]
    customer, _c = _customer(db, company)
    order = _order(db, company, customer_id=customer)

    _run(world)
    _run(world)

    assert _class_of(db, order) == "retail"
    assert _segment_of(db, customer) == "retail"
    assert db.execute(text(
        f"SELECT count(*) FROM {world['m425']._ORDERS} WHERE sales_order_id = :i"
    ), {"i": order}).scalar() == 1
