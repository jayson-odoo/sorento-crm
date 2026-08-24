"""Cross-company IDOR matrix (multi-company data isolation - Group D5-D11).

Drives the SERVICE layer under an explicit ``company_scope`` to prove the
``do_orm_execute`` filter turns every cross-company object reference into a clean
404 (never a leak) while same-company access still works, and that a create
payload can never smuggle a foreign ``company_id``:

 - AC-D6: a Sorento-scoped get / update / delete of a Mocha-owned row -> 404.
 - AC-D5/D7: the SAME row is readable / editable / deletable under Mocha scope.
 - AC-D11: a create payload carrying a foreign ``company_id`` is ignored - the
    row is stamped with the ACTIVE company, not the injected one.

Runs against the local Postgres dev DB inside a nested transaction that is ALWAYS
rolled back; every row carries a ``zzidor`` marker and a throwaway Mocha company
so it never touches real data and needs no unscoped DELETE (project memory:
"tests once wiped the dev DB"). ``commit`` is redirected to ``flush`` for the
duration so service methods that ``self.db.commit()`` stay inside the rolled-back
savepoint and never persist.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.company import Company
from app.services.company_scope import register_company_scope_listeners
from app.services.error_handler import AppException

# The scope listeners are installed at app/worker startup; install explicitly so
# this file enforces the same ORM filter when run in isolation.
register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

# Sorento is the backfill company every live row already belongs to.
SORENTO = "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT rolled back at teardown
    # Redirect commit -> flush so any service that commits stays inside the
    # rolled-back savepoint (no marker row ever persists).
    session.commit = session.flush  # type: ignore[method-assign]
    try:
        yield session
    finally:
        try:
            session.rollback()
        finally:
            session.close()


@pytest.fixture()
def mocha(db: Session) -> str:
    """A throwaway Mocha company (rolled back). A random id + marker code keeps it
    collision-proof against any stale committed row and per the DB-safety rule."""
    suffix = uuid.uuid4().hex[:8]
    c = Company(id=str(uuid.uuid4()), name=f"ZZIDOR Mocha {suffix}", code=f"ZIM{suffix}")
    db.add(c)
    db.flush()
    return c.id


def _seed_cat_uom(db: Session, company_id: str, suffix: str):
    cat_id, uom_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": cat_id, "code": f"ZZIDOR-CAT-{suffix}", "name": f"zzidor cat {suffix}", "cid": company_id},
    )
    db.execute(
        text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": uom_id, "code": f"ZZIDOR-UOM-{suffix}", "name": f"zzidor uom {suffix}", "cid": company_id},
    )
    return cat_id, uom_id


def _seed_warehouse(db: Session, company_id: str, code: str) -> str:
    wid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, company_id, created_at) "
            "VALUES (:id, :code, :name, true, :cid, now())"
        ),
        {"id": wid, "code": code, "name": f"zzidor wh {code}", "cid": company_id},
    )
    return wid


def _seed_product(db: Session, company_id: str, code: str, cat: str, uom: str) -> str:
    pid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO products (id, product_code, product_name, category_id, base_uom_id, list_price, "
            " currency, is_active, has_serial_tracking, has_batch_tracking, variant_link_manual, "
            " is_discontinued, company_id, created_at) "
            "VALUES (:id, :code, :name, :cat, :uom, 100, 'MYR', true, false, false, false, false, :cid, now())"
        ),
        {"id": pid, "code": code, "name": code, "cat": cat, "uom": uom, "cid": company_id},
    )
    return pid


# --------------------------------------------------------------------------- #
# Warehouse - get / update / delete matrix                                     #
# --------------------------------------------------------------------------- #
def test_warehouse_get_by_id_cross_company_is_404(db, mocha):
    from app.services.inventory_service import WarehouseService

    wid = _seed_warehouse(db, mocha, f"ZZIDOR-WH-{uuid.uuid4().hex[:8]}")
    db.flush()
    svc = WarehouseService(db)

    # AC-D6: Sorento-scoped read of a Mocha warehouse -> not found.
    with company_scope(db, frozenset({SORENTO})):
        with pytest.raises(AppException) as exc:
            svc.get_warehouse(wid)
    assert exc.value.status_code == 404

    # AC-D5: same-company read resolves.
    with company_scope(db, frozenset({mocha})):
        got = svc.get_warehouse(wid)
    assert got.id == wid


def test_warehouse_update_cross_company_is_404(db, mocha):
    from app.schemas.inventory import WarehouseUpdate
    from app.services.inventory_service import WarehouseService

    wid = _seed_warehouse(db, mocha, f"ZZIDOR-WH-{uuid.uuid4().hex[:8]}")
    db.flush()
    svc = WarehouseService(db)

    # AC-D6: cross-company PUT -> 404 (get_warehouse gates before any write).
    with company_scope(db, frozenset({SORENTO})):
        with pytest.raises(AppException) as exc:
            svc.update_warehouse(wid, WarehouseUpdate(warehouse_name="hijacked"))
    assert exc.value.status_code == 404

    # AC-D5: same-company edit succeeds.
    with company_scope(db, frozenset({mocha})):
        updated = svc.update_warehouse(wid, WarehouseUpdate(warehouse_name="zzidor renamed"))
    assert updated.warehouse_name == "zzidor renamed"


def test_warehouse_delete_cross_company_is_404_same_company_ok(db, mocha):
    from app.services.inventory_service import WarehouseService

    wid = _seed_warehouse(db, mocha, f"ZZIDOR-WH-{uuid.uuid4().hex[:8]}")
    db.flush()
    svc = WarehouseService(db)

    # AC-D6: cross-company DELETE -> 404, and the row survives.
    with company_scope(db, frozenset({SORENTO})):
        with pytest.raises(AppException) as exc:
            svc.delete_warehouse(wid)
    assert exc.value.status_code == 404
    still = db.execute(
        text("SELECT 1 FROM warehouses WHERE id = :id"), {"id": wid}
    ).first()
    assert still is not None  # cross-company delete did NOT touch it

    # AC-D7: same-company hard delete works.
    with company_scope(db, frozenset({mocha})):
        out = svc.delete_warehouse(wid)
    assert out["id"] == wid
    gone = db.execute(
        text("SELECT 1 FROM warehouses WHERE id = :id"), {"id": wid}
    ).first()
    assert gone is None


# --------------------------------------------------------------------------- #
# Product - cross-company get is 404                                           #
# --------------------------------------------------------------------------- #
def test_product_get_by_id_cross_company_is_404(db, mocha):
    from app.services.product_service import ProductService

    suffix = uuid.uuid4().hex[:8]
    cat, uom = _seed_cat_uom(db, mocha, suffix)
    pid = _seed_product(db, mocha, f"ZZIDORPROD{suffix}", cat, uom)
    db.flush()
    svc = ProductService(db)

    # AC-D6: Sorento can't see a Mocha product by its id.
    with company_scope(db, frozenset({SORENTO})):
        with pytest.raises(AppException) as exc:
            svc.get_product(pid)
    assert exc.value.status_code == 404

    # AC-D5: Mocha can.
    with company_scope(db, frozenset({mocha})):
        got = svc.get_product(pid)
    assert got.id == pid


# --------------------------------------------------------------------------- #
# AC-D11 - a foreign company_id in a create payload is ignored                 #
# --------------------------------------------------------------------------- #
def test_create_ignores_foreign_company_id_and_stamps_active(db, mocha):
    from app.schemas.inventory import WarehouseCreate
    from app.services.inventory_service import WarehouseService

    code = f"ZZIDOR-WH-{uuid.uuid4().hex[:8]}"

    # The create schema has no company_id field, so a client that stuffs one into
    # the JSON body has it silently dropped by Pydantic (extra=ignore).
    assert "company_id" not in WarehouseCreate.model_fields
    payload = WarehouseCreate.model_validate(
        {"warehouse_code": code, "warehouse_name": "zzidor", "company_id": SORENTO}
    )
    assert not hasattr(payload, "company_id")

    # Created under Mocha scope -> auto-stamped Mocha, NOT the injected Sorento.
    with company_scope(db, frozenset({mocha})):
        created = WarehouseService(db).create_warehouse(payload)
    assert created.company_id == mocha

    row = db.execute(
        text("SELECT company_id FROM warehouses WHERE id = :id"), {"id": created.id}
    ).first()
    assert str(row[0]) == mocha
