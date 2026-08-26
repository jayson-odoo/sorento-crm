"""F11 / R16 - both readers bind through the ladder, and a human's pick re-binds what is
already on file.

TEST-FIRST: the readers still bind on an exact code and
`app/services/scm/supplier_code_alias_service.py` does not exist, so every test here is
expected to be red until they land.

The point of the slice is that a supplier's own spelling stops being a dead end: the stock
list and the proforma invoice go through ONE helper, and when somebody matches a code by
hand the rows already uploaded under it are bound in the same transaction - no re-upload,
because the loading plan and the PI convert are read off those rows.
"""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest

from app.models.scm import (
    ProformaInvoiceLine,
    SupplierInventory,
    SupplierProductCodeAlias,
)
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service as pi_svc
from app.services.scm import supplier_inventory_service as stock_svc
from tests._pg_fixture import pg_session
from tests.scm.test_supplier_code_matcher import MARKER, World, _u

HEADER = ["型号", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def _stock_workbook(rows) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(HEADER))
    for r in rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _held(db, supplier_id: str):
    return (
        db.query(SupplierInventory)
        .filter(SupplierInventory.supplier_id == supplier_id)
        .order_by(SupplierInventory.item_code)
        .all()
    )


# --------------------------------------------------------------------------------- #
# The stock list reads through the ladder
# --------------------------------------------------------------------------------- #


def test_a_stock_list_binds_a_token_reordered_code():
    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-300-RL")
        code = w.supplier_code("SRTWC8357-RL-300")

        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )

        rows = _held(db, str(w.supplier.id))
        assert [str(r.product_id) for r in rows] == [str(product.id)]


def test_a_stock_list_binds_a_trap_size_our_code_omits():
    with pg_session() as db:
        w = World(db)
        product = w.product(
            "SRTWC8357-RL", description="SORENTO ONE PIECE (RIMLESS) TOILET (S-TRAP 250MM)"
        )
        code = w.supplier_code("SRTWC8357-RL-250")

        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )

        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [
            str(product.id)
        ]


def test_a_stock_list_leaves_a_code_nothing_answers_unbound():
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-RL")
        code = w.supplier_code("NOTHING-LIKE-THIS")

        stock_svc.apply(
            db, _stock_workbook([[code, "mystery", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )

        assert [r.product_id for r in _held(db, str(w.supplier.id))] == [None]


# --------------------------------------------------------------------------------- #
# The proforma invoice reads through the same ladder
# --------------------------------------------------------------------------------- #


def _pi_workbook(code: str) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["品名", "编号", "产品数量", "单价", "总价", "其他"])
    ws.append(["TOILET", code, 100, 250, 25000, None])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pi_lines(db, supplier_id: str):
    from app.models.scm import ProformaInvoice

    return (
        db.query(ProformaInvoiceLine)
        .join(ProformaInvoice, ProformaInvoice.id == ProformaInvoiceLine.invoice_id)
        .filter(ProformaInvoice.supplier_id == supplier_id)
        .all()
    )


def test_a_proforma_invoice_binds_a_token_reordered_code():
    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-300-RL")
        code = w.supplier_code("SRTWC8357-RL-300")

        pi_svc.apply(db, _pi_workbook(code), supplier_id=str(w.supplier.id),
                     currency="CNY", source_ref="jinbaichuan.xlsx", actor="Ms Tee")

        assert [str(l.product_id) for l in _pi_lines(db, str(w.supplier.id))] == [
            str(product.id)
        ]


def test_a_proforma_invoice_leaves_a_glued_suffix_unbound():
    """`SRTWC286-SH-250UF` is the 250 AND a UF seat - the ladder refuses it, and the line
    lands with its unmatched reason for somebody to answer by hand."""
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC286-SH", description="SORENTO TOILET (S-TRAP 250MM)")
        code = w.supplier_code("SRTWC286-SH-250UF")

        pi_svc.apply(db, _pi_workbook(code), supplier_id=str(w.supplier.id),
                     currency="CNY", source_ref="jinbaichuan.xlsx", actor="Ms Tee")

        assert [l.product_id for l in _pi_lines(db, str(w.supplier.id))] == [None]


# --------------------------------------------------------------------------------- #
# A human's pick re-binds what is already on file
# --------------------------------------------------------------------------------- #


def test_matching_a_code_by_hand_binds_the_stock_rows_already_uploaded():
    """No re-upload. The loading plan is read off these rows, so an answer that only takes
    effect on the next upload is an answer nobody gets to use today."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC286-SH")
        code = w.supplier_code("SRTWC286-SH-250UF")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        assert [r.product_id for r in _held(db, str(w.supplier.id))] == [None]

        out = alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(product.id), actor="Ms Tee",
        )

        assert out["rebound_stock_rows"] == 1
        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [
            str(product.id)
        ]


def test_matching_a_code_by_hand_binds_the_proforma_lines_already_uploaded():
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC286-SH")
        code = w.supplier_code("SRTWC286-SH-250UF")
        pi_svc.apply(db, _pi_workbook(code), supplier_id=str(w.supplier.id),
                     currency="CNY", source_ref="jinbaichuan.xlsx", actor="Ms Tee")
        assert [l.product_id for l in _pi_lines(db, str(w.supplier.id))] == [None]

        out = alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(product.id), actor="Ms Tee",
        )

        assert out["rebound_invoice_lines"] == 1
        assert [str(l.product_id) for l in _pi_lines(db, str(w.supplier.id))] == [
            str(product.id)
        ]


def test_a_manual_pick_replaces_an_automatic_one_and_rebinds():
    """Correcting a guess. The auto alias is not left beside the manual one - one supplier
    code means one product, and two rows saying different things is the state the unique
    index exists to forbid."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-300-RL")
        right = w.product("SRTWC8357-RL-SPECIAL")
        code = w.supplier_code("SRTWC8357-RL-300")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        auto = db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).one()
        assert auto.source == "auto"

        alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(right.id), actor="Ms Tee",
        )

        rows = db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).all()
        assert len(rows) == 1
        assert rows[0].source == "manual"
        assert str(rows[0].product_id) == str(right.id)
        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [str(right.id)]


def test_forgetting_an_alias_puts_the_rows_back_to_what_the_ladder_says():
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC286-SH")
        code = w.supplier_code("SRTWC286-SH-250UF")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        created = alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(product.id), actor="Ms Tee",
        )

        alias_svc.delete(db, created["id"])

        assert db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).count() == 0
        # The ladder cannot answer this code, so the row goes back to unbound rather than
        # keeping a binding whose reason has been deleted.
        assert [r.product_id for r in _held(db, str(w.supplier.id))] == [None]


def test_a_product_that_does_not_exist_is_refused():
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)

        with pytest.raises(AppException) as exc:
            alias_svc.create(
                db, supplier_id=str(w.supplier.id),
                supplier_code=w.supplier_code("ANYTHING"),
                product_id=str(uuid.uuid4()), actor="Ms Tee",
            )
        assert exc.value.status_code == 404


def test_the_supplier_s_aliases_are_listed_with_the_names_a_person_reads():
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC286-SH")
        code = w.supplier_code("SRTWC286-SH-250UF")
        alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(product.id), actor="Ms Tee",
        )

        listed = alias_svc.list_for_supplier(db, str(w.supplier.id))

        assert len(listed) == 1
        assert listed[0]["supplier_code"] == code
        assert listed[0]["product_code"] == product.product_code
        assert listed[0]["source"] == "manual"
        assert str(product.id) not in str(listed[0]["product_code"])


# --------------------------------------------------------------------------------- #
# The routes
# --------------------------------------------------------------------------------- #


def test_the_alias_routes_record_list_and_forget_a_match(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("SRTWC286-SH")
    code = w.supplier_code("SRTWC286-SH-250UF")
    stock_svc.apply(
        db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
        supplier_id=str(w.supplier.id), actor="Ms Tee",
    )
    db.commit()
    client = TestClient(app)

    created = client.post(
        "/api/v1/scm/supplier-code-aliases",
        json={
            "supplier_id": str(w.supplier.id),
            "supplier_code": code,
            "product_id": str(product.id),
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["product_code"] == product.product_code
    assert body["rebound_stock_rows"] == 1

    listed = client.get(
        "/api/v1/scm/supplier-code-aliases", params={"supplier_id": str(w.supplier.id)}
    )
    assert listed.status_code == 200, listed.text
    assert [a["supplier_code"] for a in listed.json()["data"]] == [code]

    removed = client.delete(f"/api/v1/scm/supplier-code-aliases/{body['id']}")
    assert removed.status_code == 200, removed.text
    assert client.get(
        "/api/v1/scm/supplier-code-aliases", params={"supplier_id": str(w.supplier.id)}
    ).json()["data"] == []


def test_recording_a_match_without_the_write_permission_is_403(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    w = World(db)
    db.commit()

    r = TestClient(app).post(
        "/api/v1/scm/supplier-code-aliases",
        json={
            "supplier_id": str(w.supplier.id),
            "supplier_code": w.supplier_code("ANYTHING"),
            "product_id": str(w.product("SRTWC286-SH").id),
        },
    )

    assert r.status_code == 403, r.text
