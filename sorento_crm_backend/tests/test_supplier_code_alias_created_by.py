"""S4 / AC-4.1, AC-4.2 - the Remembered table's "By" column is a person, never a UUID.

TEST-FIRST (`PLAN-scm-ui-feedback-14sep.md`, J4). Two defects, one column:

* `fulfilment.py`'s stock-list `apply` is the ONE call site in that router that hands
  `current_user.get("id")` down as `actor` instead of `_actor(current_user)` (name else
  email), so every alias the ladder remembers during an upload carries a UUID in
  `scm.supplier_product_code_alias.created_by`. AC-4.1.
* `supplier_code_alias_service.list_for_supplier` emits `created_by` verbatim, so the rows
  already on file go on printing that UUID at the buyer for as long as they exist. A
  serializer that resolves an id to the user's name is what retires them without a
  migration. AC-4.2.

Both are expected to be RED here: the first because the route still passes the id, the
second because the serializer has no resolution step at all.

Postgres, own seeds, no borrowed rows - the ladder's normalisation is SQL and CI's database
is empty.
"""
from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.models.scm import SupplierProductCodeAlias
from app.models.user import User
from app.services.scm import supplier_code_alias_service as alias_svc

from ._pg_fixture import pg_session
from .scm.conftest import requires_pg, scm_app  # noqa: F401  (scm_app is a fixture)
from .scm.test_outstanding_import_routes import as_company_user
from .scm.test_supplier_code_matcher import World

pytestmark = requires_pg

MARKER = "ZZBY"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#: The supplier's own header row, the one `supplier_inventory_reader` reads.
HEADER = ["型号", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def _u() -> str:
    return str(uuid.uuid4())


def _workbook(rows) -> bytes:
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(HEADER))
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _aliases(db, supplier_id: str) -> list[SupplierProductCodeAlias]:
    return (
        db.query(SupplierProductCodeAlias)
        .filter(SupplierProductCodeAlias.supplier_id == str(supplier_id))
        .all()
    )


# --------------------------------------------------------------------------------- #
# AC-4.1 - the upload writes a NAME
# --------------------------------------------------------------------------------- #


def test_a_stock_list_upload_stamps_the_uploaders_name_not_their_id(scm_app):
    """The alias the ladder remembers during an upload is provenance a person reads.

    The code below is our own `SRTWC8357-300-RL` with its tokens reordered, which binds on
    the token-set rung rather than exactly - so the matcher REMEMBERS it, and the row it
    writes is the one whose `created_by` the Remembered table prints.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    world = World(db)
    world.product("SRTWC8357-300-RL")
    code = world.supplier_code("SRTWC8357-RL-300")
    supplier_id = str(world.supplier.id)
    db.flush()

    principal = app.dependency_overrides[gcu]()
    response = TestClient(app).post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "toilet", 10, 0, 0.17, None]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    assert response.status_code == 200, response.text
    written = _aliases(db, supplier_id)
    assert written, "the token-reordered code should have been remembered"
    stamped = {row.created_by for row in written}
    assert principal["id"] not in stamped, (
        "the upload stamped the caller's UUID into created_by - the Remembered table's "
        f"By column would print {principal['id']}"
    )
    assert stamped == {principal.get("name") or principal["email"]}


def test_the_snapshot_row_still_records_the_uploaders_id(scm_app):
    """The two provenance columns answer two different questions (security review, S4).

    `supplier_product_code_alias.created_by` is read by a PERSON off the Remembered table, so
    it holds the name. `supplier_inventory.uploaded_by` is a principal reference - it is what
    an audit trail joins back to a user row - so it holds the id, and swapping a name into it
    would silently break that join for every future upload.
    """
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    world = World(db)
    world.product("SRTWC8357-300-RL")
    code = world.supplier_code("SRTWC8357-RL-300")
    supplier_id = str(world.supplier.id)
    db.flush()

    principal = app.dependency_overrides[gcu]()
    response = TestClient(app).post(
        "/api/v1/scm/supplier-inventory/apply",
        files={"file": ("stock.xlsx", _workbook([[code, "toilet", 10, 0, 0.17, None]]), _XLSX)},
        data={"supplier_id": supplier_id},
    )

    assert response.status_code == 200, response.text
    stamped_on_stock = {
        row[0]
        for row in db.execute(
            text(
                "SELECT uploaded_by FROM scm.supplier_inventory WHERE supplier_id = :s"
            ),
            {"s": supplier_id},
        ).all()
    }
    assert stamped_on_stock == {principal["id"]}
    assert {row.created_by for row in _aliases(db, supplier_id)} == {
        principal.get("name") or principal["email"]
    }


# --------------------------------------------------------------------------------- #
# AC-4.2 - the rows already on file read as people
# --------------------------------------------------------------------------------- #


def _alias_row(db, world: World, code: str, product, created_by):
    row = SupplierProductCodeAlias(
        id=_u(),
        supplier_id=str(world.supplier.id),
        supplier_code=code,
        product_id=str(product.id),
        source="auto",
        matched_by="token_set",
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def _by_code(db, world: World) -> dict:
    return {
        row["supplier_code"]: row
        for row in alias_svc.list_for_supplier(db, str(world.supplier.id))
    }


def test_a_stored_user_id_lists_as_that_users_name():
    """The rows an earlier upload already stamped with a UUID. No migration rewrites them,
    so the serializer is what makes them readable."""
    with pg_session() as db:
        world = World(db)
        product = world.product("SRTWC8357-300-RL")
        user_id = _u()
        db.add(User(id=user_id, email=f"{user_id}@zzby.test", name=f"{MARKER} Ms Tee"))
        db.flush()
        code = world.supplier_code("A-NAMED-USER")
        _alias_row(db, world, code, product, user_id)

        assert _by_code(db, world)[code]["created_by"] == f"{MARKER} Ms Tee"


def test_a_user_with_no_name_lists_as_their_email():
    """A principal created by an import has an address and nothing else; the address is
    still a person, and it is what `_actor` itself would have written."""
    with pg_session() as db:
        world = World(db)
        product = world.product("SRTWC8357-300-RL")
        user_id = _u()
        db.add(User(id=user_id, email=f"{user_id}@zzby.test", name=None))
        db.flush()
        code = world.supplier_code("A-NAMELESS-USER")
        _alias_row(db, world, code, product, user_id)

        assert _by_code(db, world)[code]["created_by"] == f"{user_id}@zzby.test"


def test_an_id_matching_no_user_lists_as_nothing_rather_than_as_a_uuid():
    """A deleted account. `None` renders as the dash - which says "we do not know" - where
    the raw id says nothing at all and reads as a bug."""
    with pg_session() as db:
        world = World(db)
        product = world.product("SRTWC8357-300-RL")
        code = world.supplier_code("A-STRANGER")
        _alias_row(db, world, code, product, _u())

        assert _by_code(db, world)[code]["created_by"] is None


def test_a_plain_name_passes_through_untouched():
    """Refresh matching and the PI upload path already write a name, and the resolution
    must not touch what is already right."""
    with pg_session() as db:
        world = World(db)
        product = world.product("SRTWC8357-300-RL")
        code = world.supplier_code("ALREADY-A-NAME")
        _alias_row(db, world, code, product, "Ms Tee")

        assert _by_code(db, world)[code]["created_by"] == "Ms Tee"


def test_the_names_are_resolved_in_one_query_for_the_whole_list():
    """Per-row resolution is an N+1 on a supplier whose memory runs to hundreds of rulings,
    which is the shape the loading plan's own tab opens with.

    Counted with a statement listener rather than by reading the code, so the assertion
    survives a refactor of HOW the query is issued.
    """
    with pg_session() as db:
        world = World(db)
        product = world.product("SRTWC8357-300-RL")
        ids = []
        for index in range(3):
            user_id = _u()
            db.add(
                User(id=user_id, email=f"{user_id}@zzby.test", name=f"{MARKER} User {index}")
            )
            ids.append(user_id)
        db.flush()
        for index, user_id in enumerate(ids):
            _alias_row(
                db, world, world.supplier_code(f"MANY-{index}"), product, user_id
            )
        # A plain name and an unknown id in the same page, so the counted query is the one
        # that handles the real mixture rather than a uniform list.
        _alias_row(db, world, world.supplier_code("MANY-NAME"), product, "Ms Tee")
        _alias_row(db, world, world.supplier_code("MANY-GONE"), product, _u())

        statements: list[str] = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _record)
        try:
            rows = alias_svc.list_for_supplier(db, str(world.supplier.id))
        finally:
            event.remove(engine, "before_cursor_execute", _record)

        assert len(rows) == 5
        # The listener is real, so "no users query" cannot be the silent answer to a
        # listener that never fired.
        assert any("supplier_product_code_alias" in s for s in statements), statements
        # Matched on the TABLE, not on one spelling of the SQL: the resolution is an ORM
        # query now (`actor_labels`), and SQLAlchemy renders `FROM users` on its own line
        # where the hand-written statement had it after a space.
        user_queries = [s for s in statements if re.search(r"\bFROM users\b", s)]
        assert len(user_queries) == 1, user_queries
