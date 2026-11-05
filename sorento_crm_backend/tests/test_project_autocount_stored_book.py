"""AC-QTSO-CRM round 4 (owner ruling R8): every stored AutoCount key also stores its book.

* `autocount_book VARCHAR(40)` on `projects.sales_orders` and `projects.quotation_documents`, added
  in migration `acqs_0001_project_ac_write` (edited in place, not merged yet).
* Filling it: a done SO / QT create stores the `book` that `/write-capabilities` names at write
  time, trimmed (NULL when SS names none); an adopted order's first done update stores the book
  segment of its core `source_ref` beside the key.
* Gate, for EVERY SO and QT (CRM-created or adopted): Update and Cancel are allowed only when the
  stored or derived book equals the book SS names now (trimmed, case-insensitive). A NULL stored
  book, or SS naming none or another book, answers 409 `ac_waiting` "Waiting for AutoCount" with no
  write call. This replaces R7's "CRM-created unaffected". Create has no key yet and is unaffected.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.models.order import SalesOrder
from tests._ac_write_support import (
    BASE,
    CAPS_PATH,
    DOC_KEY,
    QT_CREATE_PATH,
    SO_CREATE_PATH,
    EDIT,
    VIEW,
    WAITING,
    WRITE,
    add_amendment,
    add_issue,
    api_fixture,
    caps_with,
    delay_row,
    detail,
    done_body,
    fake_ss,  # noqa: F401  (fixture)
    put_in_autocount,
)

QT_KEY = 5001
SO_DOC = f"{SO_CREATE_PATH}/{DOC_KEY}"
QT_DOC = f"{QT_CREATE_PATH}/{QT_KEY}"
MISSING = "<missing>"

# (stored book, book SS names now): every one must wait, with no write call.
BLOCKED = [
    pytest.param("db3", "db1", id="different-book"),
    pytest.param(None, "db3", id="stored-null"),
    pytest.param("db3", MISSING, id="ss-names-none-missing"),
    pytest.param("db3", None, id="ss-names-none-null"),
    pytest.param("db3", "   ", id="ss-names-blank"),
]
ALLOWED = [pytest.param("db3", " DB3 ", id="trim-and-case")]


@pytest.fixture
def so_api(fake_ss):
    yield from api_fixture("so", [VIEW, EDIT, WRITE], switch=True)


@pytest.fixture
def qt_api(fake_ss):
    yield from api_fixture("qt", [VIEW, EDIT, WRITE], switch=True)


def _feed(fake_ss, named, *, cancel=True):
    body = {"capabilities": caps_with(cancel_doc=(cancel, None if cancel else "VENDOR_UNSUPPORTED"))}
    if named != MISSING:
        body["book"] = named
    fake_ss.answers[("GET", CAPS_PATH)] = (200, body)


def _non_get(fake_ss):
    return [r for r in fake_ss.writes() if r.method != "GET"]


# --------------------------------------------------------------------------- set-ups


def _so_in_autocount(db, world, stored):
    put_in_autocount(db, world)
    world.order.autocount_book = stored
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    return amendment


def _qt_in_autocount(db, world, stored, *, newer_issue=False):
    world.document.autocount_doc_no = "QT000777"
    world.document.autocount_doc_key = str(QT_KEY)
    world.document.autocount_last_modified = "2026-10-21T08:00:00"
    world.document.autocount_issue_id = world.issue.id
    world.document.autocount_book = stored
    if newer_issue:
        add_issue(db, world.company_id, world.document, world.scope, world.version, issue_no=2, accepted=True)
    db.commit()


def _so_answers(fake_ss):
    fake_ss.answers[("PATCH", SO_DOC)] = (200, done_body(last_modified="2026-11-05T11:00:00"))
    fake_ss.answers[("POST", f"{SO_DOC}/cancel")] = (200, done_body())


def _qt_answers(world, fake_ss):
    held = [detail(1, world.p1.product_code, "9", "180.00", "BRW-BB", None, 1)]
    fake_ss.answers[("GET", QT_DOC)] = (200, done_body(doc_key=QT_KEY, details=held))
    fake_ss.answers[("PATCH", QT_DOC)] = (200, done_body(doc_key=QT_KEY, details=held))
    fake_ss.answers[("POST", f"{QT_DOC}/lines")] = (200, done_body(doc_key=QT_KEY, details=held))
    fake_ss.answers[("POST", f"{QT_DOC}/cancel")] = (200, done_body(doc_key=QT_KEY))


def _so_update(client, amendment):
    return client.post(f"{BASE}/sales-orders/amendments/{amendment.id}/autocount")


def _so_cancel(client, world):
    return client.post(f"{BASE}/sales-orders/{world.order.id}/autocount/cancel")


def _qt_send(client, world):
    return client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount")


def _qt_cancel(client, world):
    return client.post(f"{BASE}/quotation-documents/{world.document.id}/autocount/cancel")


def _assert_waits(response):
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "ac_waiting"
    assert response.json()["message"] == WAITING


# --------------------------------------------------------------------------- 1, 2, 4: blocked


@pytest.mark.parametrize("stored,named", BLOCKED)
def test_so_update_and_cancel_wait_unless_the_stored_book_matches(so_api, fake_ss, stored, named):
    client, db, world = so_api
    amendment = _so_in_autocount(db, world, stored)
    _feed(fake_ss, named)
    _so_answers(fake_ss)

    _assert_waits(_so_update(client, amendment))
    _assert_waits(_so_cancel(client, world))
    assert _non_get(fake_ss) == []


@pytest.mark.parametrize("stored,named", BLOCKED)
def test_qt_update_and_cancel_wait_unless_the_stored_book_matches(qt_api, fake_ss, stored, named):
    client, db, world = qt_api
    _qt_in_autocount(db, world, stored, newer_issue=True)
    _feed(fake_ss, named)
    _qt_answers(world, fake_ss)

    _assert_waits(_qt_send(client, world))
    _assert_waits(_qt_cancel(client, world))
    assert _non_get(fake_ss) == []


# --------------------------------------------------------------------------- 3: allowed


@pytest.mark.parametrize("stored,named", ALLOWED)
def test_so_update_and_cancel_go_when_the_books_match_trimmed_and_case_insensitive(
    so_api, fake_ss, stored, named
):
    client, db, world = so_api
    amendment = _so_in_autocount(db, world, stored)
    _feed(fake_ss, named)
    _so_answers(fake_ss)

    assert _so_update(client, amendment).status_code == 200
    assert fake_ss.to("PATCH", SO_DOC)
    assert _so_cancel(client, world).status_code == 200
    assert fake_ss.to("POST", f"{SO_DOC}/cancel")


@pytest.mark.parametrize("stored,named", ALLOWED)
def test_qt_update_and_cancel_go_when_the_books_match(qt_api, fake_ss, stored, named):
    client, db, world = qt_api
    _qt_in_autocount(db, world, stored, newer_issue=True)
    _feed(fake_ss, named)
    _qt_answers(world, fake_ss)

    assert _qt_send(client, world).status_code == 200
    assert fake_ss.to("PATCH", QT_DOC)
    assert _qt_cancel(client, world).status_code == 200
    assert fake_ss.to("POST", f"{QT_DOC}/cancel")


# --------------------------------------------------------------------------- 5: a done create stores the book


@pytest.mark.parametrize(
    "named,stored",
    [(" db3 ", "db3"), (MISSING, None), (None, None), ("  ", None)],
    ids=["named-trimmed", "missing", "null", "blank"],
)
def test_a_done_so_create_stores_the_book_ss_names(so_api, fake_ss, named, stored):
    client, db, world = so_api
    _feed(fake_ss, named)
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (200, done_body(doc_no="SO412345"))

    response = client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

    assert response.status_code == 200, response.text
    db.refresh(world.order)
    assert world.order.autocount_doc_key == str(DOC_KEY)
    assert world.order.autocount_book == stored


@pytest.mark.parametrize(
    "named,stored",
    [(" db3 ", "db3"), (MISSING, None), (None, None), ("  ", None)],
    ids=["named-trimmed", "missing", "null", "blank"],
)
def test_a_done_qt_create_stores_the_book_ss_names(qt_api, fake_ss, named, stored):
    client, db, world = qt_api
    _feed(fake_ss, named)
    fake_ss.answers[("POST", QT_CREATE_PATH)] = (200, done_body(doc_no="QT000777", doc_key=QT_KEY))

    response = _qt_send(client, world)

    assert response.status_code == 200, response.text
    db.refresh(world.document)
    assert world.document.autocount_doc_key == str(QT_KEY)
    assert world.document.autocount_book == stored


def test_a_refused_create_stores_no_book(so_api, fake_ss):
    client, db, world = so_api
    _feed(fake_ss, "db3")
    fake_ss.answers[("POST", SO_CREATE_PATH)] = (
        422,
        {"outcome": "refused", "errorCode": "ITEM_NOT_FOUND", "message": "no such item", "warnings": [],
         "docKey": None, "docNo": None, "document": None},
    )

    client.post(f"{BASE}/sales-orders/{world.order.id}/autocount")

    db.refresh(world.order)
    assert world.order.autocount_book is None and world.order.autocount_doc_key is None


# --------------------------------------------------------------------------- 6: adopted first update


def test_an_adopted_orders_first_done_update_stores_its_source_ref_book(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    core = db.query(SalesOrder).filter(SalesOrder.id == world.order.so_id).one()
    core.source_ref = f"AED_SRT:{DOC_KEY}"
    world.order.autocount_doc_key = None
    world.order.autocount_book = None
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    _feed(fake_ss, "aed_srt")
    _so_answers(fake_ss)

    assert _so_update(client, amendment).status_code == 200

    db.refresh(world.order)
    assert world.order.autocount_doc_key == str(DOC_KEY)
    assert world.order.autocount_book == "AED_SRT"


def test_an_adopted_update_that_is_refused_stores_no_book(so_api, fake_ss):
    client, db, world = so_api
    put_in_autocount(db, world)
    core = db.query(SalesOrder).filter(SalesOrder.id == world.order.so_id).one()
    core.source_ref = f"AED_SRT:{DOC_KEY}"
    world.order.autocount_doc_key = None
    world.order.autocount_book = None
    amendment = add_amendment(db, world, [delay_row(world, world.line2, "2027-01-07")])
    db.commit()
    _feed(fake_ss, "AED_SRT")
    fake_ss.answers[("PATCH", SO_DOC)] = (
        422,
        {"outcome": "refused", "errorCode": "QTY_BELOW_TRANSFERRED", "message": "too low", "warnings": [],
         "docKey": None, "docNo": None, "document": None},
    )

    _so_update(client, amendment)

    db.refresh(world.order)
    assert world.order.autocount_book is None


# --------------------------------------------------------------------------- 8: the book is not on the wire


def _scalars(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield ("key", key)
            yield from _scalars(value)
    elif isinstance(node, list):
        for value in node:
            yield from _scalars(value)
    else:
        yield ("value", node)


def _no_book(payload, book):
    keys = {v for kind, v in _scalars(payload) if kind == "key"}
    values = {str(v) for kind, v in _scalars(payload) if kind == "value"}
    assert "autocount_book" not in keys, "the stored book must not be a raw payload key"
    assert book not in values, "the stored book value must not appear in a payload"


def test_no_sales_order_payload_leaks_the_stored_book(so_api):
    client, db, world = so_api
    _so_in_autocount(db, world, "db3-secret")

    listing = client.get(f"{BASE}/projects/{world.project.id}/sales-orders")
    detail_ = client.get(f"{BASE}/sales-orders/{world.order.id}")

    for response in (listing, detail_):
        assert response.status_code == 200, response.text
        _no_book(response.json(), "db3-secret")


def test_no_quotation_payload_leaks_the_stored_book(qt_api):
    client, db, world = qt_api
    _qt_in_autocount(db, world, "db3-secret")

    one = client.get(f"{BASE}/projects/{world.project.id}/quotation-documents/{world.document.id}")
    many = client.get(f"{BASE}/projects/{world.project.id}/quotation-documents")

    for response in (one, many):
        assert response.status_code == 200, response.text
        _no_book(response.json(), "db3-secret")


# --------------------------------------------------------------------------- 7: the migration


MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "acqs_0001_project_ac_write.py"
)
BOTH = ("sales_orders", "quotation_documents")


def _load_migration():
    spec = importlib.util.spec_from_file_location("acqs_0001_r8", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _book_columns(conn):
    return {
        row[0]: (row[1], row[2])
        for row in conn.exec_driver_sql(
            "SELECT table_name, data_type, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = 'projects' AND column_name = 'autocount_book' "
            "AND table_name IN ('sales_orders', 'quotation_documents')"
        ).fetchall()
    }


def test_the_migration_source_adds_autocount_book_to_both_tables_and_drops_it():
    source = MIGRATION.read_text()
    assert source.count("autocount_book") >= 4, "added and dropped on both tables"
    assert "VARCHAR(40)" in source
    for table in ("projects.sales_orders", "projects.quotation_documents"):
        assert table in source


def test_the_migration_upgrades_downgrades_and_upgrades_again_in_a_rolled_back_transaction():
    """Postgres DDL is transactional: run the real upgrade() / downgrade() functions on a real
    connection, assert the column on both tables after each step, and roll everything back so the
    shared database is untouched."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from app.database import engine

    module = _load_migration()
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            conn.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()
                first = _book_columns(conn)
                module.downgrade()
                gone = _book_columns(conn)
                module.upgrade()
                again = _book_columns(conn)
        finally:
            outer.rollback()

    for found in (first, again):
        assert set(found) == set(BOTH), found
        assert all(v == ("character varying", 40) for v in found.values()), found
    assert gone == {}, "downgrade must drop autocount_book from both tables"
