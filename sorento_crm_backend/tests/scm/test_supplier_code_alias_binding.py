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
from datetime import datetime, timedelta
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


def test_forgetting_an_alias_unbinds_the_proforma_lines_it_bound():
    """The other reader. A ruling reaches the stock list AND the invoice lines, so forgetting
    it has to reach both - a line still pointing at a product whose reason has been deleted is
    a binding nobody can account for, and the convert would carry it onto a container."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC286-SH")
        code = w.supplier_code("SRTWC286-SH-250UF")
        pi_svc.apply(db, _pi_workbook(code), supplier_id=str(w.supplier.id),
                     currency="CNY", source_ref="jinbaichuan.xlsx", actor="Ms Tee")
        created = alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(product.id), actor="Ms Tee",
        )
        assert [str(l.product_id) for l in _pi_lines(db, str(w.supplier.id))] == [
            str(product.id)
        ]

        out = alias_svc.delete(db, created["id"])

        assert out["deleted"] == 1
        assert out["rebound_invoice_lines"] == 1
        assert [l.product_id for l in _pi_lines(db, str(w.supplier.id))] == [None]


def test_forgetting_an_alias_the_ladder_can_still_answer_leaves_the_row_bound():
    """Forgetting a MANUAL agreement with the exact code is not the same as unbinding it: the
    ladder answers that code on its own, so the row keeps the product and only the recorded
    ruling goes."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-300-RL")
        code = w.supplier_code("SRTWC8357-RL-300")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        alias = db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).one()

        alias_svc.delete(db, str(alias.id))

        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [
            str(product.id)
        ]


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


def test_the_alias_list_is_newest_first_dismissed_included_and_scoped_to_one_supplier():
    """AC-C5: every alias for the supplier - a dismissal included - ordered `created_at
    desc`, and a second supplier's ruling never shows up on this one's list."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        other = World(db)
        product = w.product("SRTWC8357-RL")
        now = datetime(2026, 8, 27, 12, 0, 0)

        oldest = SupplierProductCodeAlias(
            id=_u(), supplier_id=w.supplier.id, supplier_code=w.supplier_code("OLDEST"),
            product_id=product.id, source="manual", matched_by="manual",
            created_by="Ms Tee", created_at=now - timedelta(days=2),
        )
        middle_dismissed = SupplierProductCodeAlias(
            id=_u(), supplier_id=w.supplier.id,
            supplier_code=w.supplier_code("DISMISSED-ONE"), product_id=None,
            source="dismissed", matched_by="dismissed", created_by="Mr Lim",
            created_at=now - timedelta(days=1),
        )
        newest = SupplierProductCodeAlias(
            id=_u(), supplier_id=w.supplier.id, supplier_code=w.supplier_code("NEWEST"),
            product_id=product.id, source="auto", matched_by="token_set",
            created_by=None, created_at=now,
        )
        elsewhere = SupplierProductCodeAlias(
            id=_u(), supplier_id=other.supplier.id,
            supplier_code=other.supplier_code("NEWEST"),
            product_id=other.product("SOMETHING-ELSE").id,
            source="manual", matched_by="manual", created_by="Ms Tee", created_at=now,
        )
        db.add_all([oldest, middle_dismissed, newest, elsewhere])
        db.flush()

        listed = alias_svc.list_for_supplier(db, str(w.supplier.id))

        assert [row["supplier_code"] for row in listed] == [
            newest.supplier_code, middle_dismissed.supplier_code, oldest.supplier_code,
        ]
        dismissed_row = listed[1]
        assert dismissed_row["source"] == "dismissed"
        assert dismissed_row["product_code"] is None
        assert dismissed_row["set_code"] is None
        assert dismissed_row["created_by"] == "Mr Lim"
        # A name, never a UUID (`_actor()` writes it that way; asserted here too, since this
        # is the surface the screen reads).
        for row in listed:
            if row["created_by"]:
                with pytest.raises(ValueError):
                    uuid.UUID(row["created_by"])


def test_the_alias_route_lists_newest_first_with_every_ac_c5_field(scm_app):
    """The same rule through the route. No `response_model` guards this endpoint, but the
    flat shape is asserted at the boundary anyway - it is the whole contract (R16)."""
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    product = w.product("SRTWC8357-RL")
    now = datetime(2026, 8, 27, 12, 0, 0)
    # Alphabetically first, chronologically OLDER - so a route still ordering by
    # `supplier_code` (the pre-S3 behaviour) would list this FIRST, the wrong way round.
    old = SupplierProductCodeAlias(
        id=_u(), supplier_id=w.supplier.id, supplier_code=w.supplier_code("AAA-OLDER"),
        product_id=product.id, source="manual", matched_by="manual",
        created_by="Ms Tee", created_at=now - timedelta(days=1),
    )
    new = SupplierProductCodeAlias(
        id=_u(), supplier_id=w.supplier.id, supplier_code=w.supplier_code("ZZZ-NEWER"),
        product_id=None, source="dismissed", matched_by="dismissed",
        created_by="Mr Lim", created_at=now,
    )
    db.add_all([old, new])
    db.commit()
    client = TestClient(app)

    resp = client.get(
        "/api/v1/scm/supplier-code-aliases", params={"supplier_id": str(w.supplier.id)}
    )

    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert [r["supplier_code"] for r in rows] == [new.supplier_code, old.supplier_code]
    for field in (
        "id", "supplier_code", "product_code", "product_name", "set_code", "set_name",
        "source", "matched_by", "created_by", "created_at",
    ):
        assert field in rows[0]
    assert rows[0]["created_by"] == "Mr Lim"
    assert rows[1]["created_by"] == "Ms Tee"


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


def test_the_codes_this_supplier_sent_that_bind_to_nothing_are_listed():
    """The durable surface. The upload dialog counts them and goes away; the loading plan is
    where somebody comes back to answer them, so the unbound rows have to be readable after
    the upload that created them."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-RL")
        bound = w.supplier_code("SRTWC8357-RL")
        orphan = w.supplier_code("NOTHING-LIKE-THIS")
        stock_svc.apply(
            db,
            _stock_workbook([
                [bound, "toilet", 10, 0, 0.17, None],
                [orphan, "mystery", 5, 2, 0.2, "no idea"],
            ]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )

        out = alias_svc.unmatched_for_supplier(db, str(w.supplier.id))

        assert [r["item_code"] for r in out] == [orphan]
        assert out[0]["qty_packed"] == 5
        assert out[0]["product_name"] == "mystery"


def test_a_line_bound_by_the_ladder_says_so_on_the_invoice():
    """An automatic bind has to be visible AS one. A screen that cannot tell a guess from a
    decision cannot ask anyone to check the guess."""
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-300-RL")
        code = w.supplier_code("SRTWC8357-RL-300")
        pi_svc.apply(db, _pi_workbook(code), supplier_id=str(w.supplier.id),
                     currency="CNY", source_ref="jinbaichuan.xlsx", actor="Ms Tee")
        from app.models.scm import ProformaInvoice

        invoice = db.query(ProformaInvoice).filter(
            ProformaInvoice.supplier_id == w.supplier.id
        ).one()

        line = pi_svc.serialize(db, invoice)["lines"][0]

        assert line["matched"] is True
        assert line["matched_by"] == "token_set"
        assert line["match_source"] == "auto"


def test_a_line_that_matched_exactly_claims_no_ladder_rung():
    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-RL")
        code = w.supplier_code("SRTWC8357-RL")
        pi_svc.apply(db, _pi_workbook(code), supplier_id=str(w.supplier.id),
                     currency="CNY", source_ref="jinbaichuan.xlsx", actor="Ms Tee")
        from app.models.scm import ProformaInvoice

        invoice = db.query(ProformaInvoice).filter(
            ProformaInvoice.supplier_id == w.supplier.id
        ).one()

        line = pi_svc.serialize(db, invoice)["lines"][0]

        assert line["matched"] is True
        assert line["matched_by"] is None
        assert line["match_source"] is None


# --------------------------------------------------------------------------------- #
# Dismissing a code: it leaves the queue and the ladder refuses it (R17)
# --------------------------------------------------------------------------------- #


def test_a_dismissed_code_leaves_the_queue():
    """"That is not one of ours." The queue is a to-do list, so a code somebody has ruled on
    stops being asked about - otherwise the same rows are re-read every week."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        orphan = w.supplier_code("NOTHING-LIKE-THIS")
        stock_svc.apply(
            db, _stock_workbook([[orphan, "mystery", 5, 0, 0.2, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        assert [r["item_code"] for r in
                alias_svc.unmatched_for_supplier(db, str(w.supplier.id))] == [orphan]

        out = alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=orphan, actor="Ms Tee"
        )

        assert out["source"] == "dismissed"
        assert out["product_id"] is None
        assert alias_svc.unmatched_for_supplier(db, str(w.supplier.id)) == []


def test_dismissing_a_code_unbinds_the_rows_it_was_bound_to():
    """A dismissal is not a match. A row still pointing at a product would keep offering the
    item to the plan, which is the opposite of what "not one of ours" means."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-300-RL")
        code = w.supplier_code("SRTWC8357-RL-300")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [
            str(product.id)
        ]

        out = alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=code, actor="Ms Tee"
        )

        assert out["rebound_stock_rows"] == 1
        assert [r.product_id for r in _held(db, str(w.supplier.id))] == [None]
        rows = db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).all()
        assert len(rows) == 1
        assert rows[0].source == "dismissed"
        assert rows[0].product_id is None


def test_dismissing_a_code_unbinds_the_proforma_lines_it_bound():
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC286-SH")
        code = w.supplier_code("SRTWC286-SH-250UF")
        pi_svc.apply(db, _pi_workbook(code), supplier_id=str(w.supplier.id),
                     currency="CNY", source_ref="jinbaichuan.xlsx", actor="Ms Tee")
        alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(product.id), actor="Ms Tee",
        )
        assert [str(l.product_id) for l in _pi_lines(db, str(w.supplier.id))] == [
            str(product.id)
        ]

        out = alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=code, actor="Ms Tee"
        )

        assert out["rebound_invoice_lines"] == 1
        assert [l.product_id for l in _pi_lines(db, str(w.supplier.id))] == [None]


def test_the_ladder_refuses_a_dismissed_code():
    """Rung 0 is what somebody DECIDED, and "none of ours" is a decision. Without this the
    next upload binds the code again and the dismissal reads as if it never happened."""
    from app.services.scm import supplier_code_alias_service as alias_svc
    from app.services.scm import supplier_code_matcher

    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-RL")
        code = w.supplier_code("SRTWC8357-RL")
        alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=code, actor="Ms Tee"
        )

        found = supplier_code_matcher.resolve(db, str(w.supplier.id), [code])

        assert found == {}


def test_a_stock_list_re_uploaded_after_a_dismissal_stays_unbound():
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        w.product("SRTWC8357-RL")
        code = w.supplier_code("SRTWC8357-RL")
        alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=code, actor="Ms Tee"
        )

        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )

        assert [r.product_id for r in _held(db, str(w.supplier.id))] == [None]


def test_a_dismissal_is_listed_with_no_product_so_it_can_be_undone():
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        code = w.supplier_code("NOTHING-LIKE-THIS")
        alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=code, actor="Ms Tee"
        )

        listed = alias_svc.list_for_supplier(db, str(w.supplier.id))

        assert len(listed) == 1
        assert listed[0]["supplier_code"] == code
        assert listed[0]["source"] == "dismissed"
        assert listed[0]["product_code"] is None
        assert listed[0]["product_name"] is None


def test_forgetting_a_dismissal_puts_the_code_back_in_the_queue():
    """Undo, and nothing more: the code is asked about again and the ladder answers it again
    on the next upload."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        orphan = w.supplier_code("NOTHING-LIKE-THIS")
        stock_svc.apply(
            db, _stock_workbook([[orphan, "mystery", 5, 0, 0.2, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        dismissed = alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=orphan, actor="Ms Tee"
        )
        assert alias_svc.unmatched_for_supplier(db, str(w.supplier.id)) == []

        alias_svc.delete(db, dismissed["id"])

        assert db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).count() == 0
        assert [r["item_code"] for r in
                alias_svc.unmatched_for_supplier(db, str(w.supplier.id))] == [orphan]


def test_dismissing_a_code_replaces_the_match_recorded_for_it():
    """One supplier code carries one ruling. A dismissal beside a match is two rows saying
    different things, which is the state the identity index exists to forbid."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC286-SH")
        code = w.supplier_code("SRTWC286-SH-250UF")
        alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(product.id), actor="Ms Tee",
        )

        alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=code, actor="Ms Tee"
        )

        rows = db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).all()
        assert len(rows) == 1
        assert rows[0].source == "dismissed"
        assert rows[0].matched_by == "dismissed"
        assert rows[0].product_id is None


def test_a_dismissal_carrying_a_product_is_refused_by_the_database():
    """The check is in the DATABASE because the two columns are one fact: `dismissed` means
    exactly "no product", and a row that says both is unreadable by every screen."""
    from sqlalchemy.exc import IntegrityError

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC286-SH")

        db.add(
            SupplierProductCodeAlias(
                id=str(uuid.uuid4()), supplier_id=str(w.supplier.id),
                supplier_code=w.supplier_code("ANYTHING"), product_id=str(product.id),
                source="dismissed", matched_by="dismissed",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_a_match_with_no_product_is_refused_by_the_database():
    from sqlalchemy.exc import IntegrityError

    with pg_session() as db:
        w = World(db)

        db.add(
            SupplierProductCodeAlias(
                id=str(uuid.uuid4()), supplier_id=str(w.supplier.id),
                supplier_code=w.supplier_code("ANYTHING"), product_id=None,
                source="manual", matched_by="manual",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_the_dismiss_route_records_it_and_forget_puts_it_back(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    code = w.supplier_code("NOTHING-LIKE-THIS")
    stock_svc.apply(
        db, _stock_workbook([[code, "mystery", 5, 0, 0.2, None]]),
        supplier_id=str(w.supplier.id), actor="Ms Tee",
    )
    db.commit()
    client = TestClient(app)

    dismissed = client.post(
        "/api/v1/scm/supplier-code-aliases/dismiss",
        json={"supplier_id": str(w.supplier.id), "supplier_code": code},
    )
    assert dismissed.status_code == 201, dismissed.text
    body = dismissed.json()
    assert body["source"] == "dismissed"
    assert body["product_id"] is None
    assert body["supplier_code"] == code
    assert body["rebound_stock_rows"] == 1

    assert client.get(
        "/api/v1/scm/supplier-code-aliases/unmatched",
        params={"supplier_id": str(w.supplier.id)},
    ).json()["data"] == []
    listed = client.get(
        "/api/v1/scm/supplier-code-aliases", params={"supplier_id": str(w.supplier.id)}
    ).json()["data"]
    assert [a["source"] for a in listed] == ["dismissed"]

    removed = client.delete(f"/api/v1/scm/supplier-code-aliases/{body['id']}")
    assert removed.status_code == 200, removed.text
    assert [
        r["item_code"]
        for r in client.get(
            "/api/v1/scm/supplier-code-aliases/unmatched",
            params={"supplier_id": str(w.supplier.id)},
        ).json()["data"]
    ] == [code]


def test_dismissing_without_the_write_permission_is_403(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    w = World(db)
    db.commit()

    r = TestClient(app).post(
        "/api/v1/scm/supplier-code-aliases/dismiss",
        json={
            "supplier_id": str(w.supplier.id),
            "supplier_code": w.supplier_code("ANYTHING"),
        },
    )

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------------- #
# Refresh matching: the ladder runs again over what is still unbound (R18)
# --------------------------------------------------------------------------------- #


def test_rematch_binds_a_product_added_after_the_upload():
    """The catalogue moves after the file lands. A product created (or an alias recorded)
    the day after the stock list was uploaded leaves the rows sitting unbound for a code the
    ladder can now answer, and re-uploading a file to make the catalogue catch up is a
    ceremony, not a decision."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        code = w.supplier_code("SRTWC8357-RL-300")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        pi_svc.apply(db, _pi_workbook(code), supplier_id=str(w.supplier.id),
                     currency="CNY", source_ref="jinbaichuan.xlsx", actor="Ms Tee")
        assert [r.product_id for r in _held(db, str(w.supplier.id))] == [None]
        assert [l.product_id for l in _pi_lines(db, str(w.supplier.id))] == [None]

        # The catalogue catches up.
        product = w.product("SRTWC8357-300-RL")

        out = alias_svc.rematch(db, supplier_id=str(w.supplier.id), actor="Ms Tee")

        assert out == {
            "inventory_bound": 1,
            "invoice_lines_bound": 1,
            "still_unmatched": 0,
        }
        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [
            str(product.id)
        ]
        assert [str(l.product_id) for l in _pi_lines(db, str(w.supplier.id))] == [
            str(product.id)
        ]
        # Written down exactly as an upload writes it, so the next file reads a decision.
        alias = db.query(SupplierProductCodeAlias).filter(
            SupplierProductCodeAlias.supplier_id == w.supplier.id
        ).one()
        assert alias.source == "auto"
        assert alias.matched_by == "token_set"


def test_rematch_leaves_a_dismissed_code_where_it_is():
    """"Not one of ours" is an answer, and an answer is not re-asked. Binding it here would
    undo the ruling on the next click of a button whose whole point is that it is safe."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        code = w.supplier_code("SRTWC8357-RL-300")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        alias_svc.dismiss(
            db, supplier_id=str(w.supplier.id), supplier_code=code, actor="Ms Tee"
        )
        w.product("SRTWC8357-300-RL")

        out = alias_svc.rematch(db, supplier_id=str(w.supplier.id), actor="Ms Tee")

        assert out["inventory_bound"] == 0
        assert [r.product_id for r in _held(db, str(w.supplier.id))] == [None]
        # And it is not counted as work left to do either - it has been answered.
        assert out["still_unmatched"] == 0


def test_rematch_honours_a_manual_alias():
    """Rung 0 first, here as everywhere: a person's own pick is what the rows bind to, not
    whatever the derived rungs would have said about the same code."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        code = w.supplier_code("SRTWC8357-RL-300")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        w.product("SRTWC8357-300-RL")  # what the token-set rung would answer
        right = w.product("SRTWC8357-RL-SPECIAL")  # what Ms Tee says it is
        alias_svc.create(
            db, supplier_id=str(w.supplier.id), supplier_code=code,
            product_id=str(right.id), actor="Ms Tee",
        )
        # Staged directly: `create` re-binds the rows itself, so an unbound row under a code
        # already ruled on has to be put back by hand to be re-matched at all.
        db.query(SupplierInventory).filter(
            SupplierInventory.supplier_id == w.supplier.id
        ).update({"product_id": None}, synchronize_session=False)

        out = alias_svc.rematch(db, supplier_id=str(w.supplier.id), actor="Ms Tee")

        assert out["inventory_bound"] == 1
        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [
            str(right.id)
        ]


def test_rematch_does_not_touch_a_row_already_bound():
    """It answers what is unanswered. A row that already carries a product is not re-derived,
    because re-deriving a settled binding is a chance to disagree with it."""
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        product = w.product("SRTWC8357-RL")
        code = w.supplier_code("SRTWC8357-RL")
        stock_svc.apply(
            db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [
            str(product.id)
        ]

        out = alias_svc.rematch(db, supplier_id=str(w.supplier.id), actor="Ms Tee")

        assert out == {
            "inventory_bound": 0,
            "invoice_lines_bound": 0,
            "still_unmatched": 0,
        }
        assert [str(r.product_id) for r in _held(db, str(w.supplier.id))] == [
            str(product.id)
        ]


def test_rematch_counts_what_it_could_not_answer():
    from app.services.scm import supplier_code_alias_service as alias_svc

    with pg_session() as db:
        w = World(db)
        code = w.supplier_code("SRTWC8357-RL-300")
        orphan = w.supplier_code("NOTHING-LIKE-THIS")
        stock_svc.apply(
            db,
            _stock_workbook([
                [code, "toilet", 10, 0, 0.17, None],
                [orphan, "mystery", 5, 0, 0.2, None],
            ]),
            supplier_id=str(w.supplier.id), actor="Ms Tee",
        )
        w.product("SRTWC8357-300-RL")

        out = alias_svc.rematch(db, supplier_id=str(w.supplier.id), actor="Ms Tee")

        assert out["inventory_bound"] == 1
        assert out["still_unmatched"] == 1


def test_the_rematch_route_reports_what_it_bound(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = World(db)
    code = w.supplier_code("SRTWC8357-RL-300")
    stock_svc.apply(
        db, _stock_workbook([[code, "toilet", 10, 0, 0.17, None]]),
        supplier_id=str(w.supplier.id), actor="Ms Tee",
    )
    w.product("SRTWC8357-300-RL")
    db.commit()
    client = TestClient(app)

    r = client.post(
        "/api/v1/scm/supplier-code-aliases/rematch",
        json={"supplier_id": str(w.supplier.id)},
    )

    assert r.status_code == 200, r.text
    # Asserted through the ROUTE, because a `response_model` silently drops what it does not
    # declare and the toast is written from these three numbers.
    assert r.json() == {
        "inventory_bound": 1,
        "invoice_lines_bound": 0,
        "still_unmatched": 0,
    }
    assert client.get(
        "/api/v1/scm/supplier-code-aliases/unmatched",
        params={"supplier_id": str(w.supplier.id)},
    ).json()["data"] == []


def test_rematching_without_the_write_permission_is_403(scm_app):
    from fastapi.testclient import TestClient

    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    w = World(db)
    db.commit()

    r = TestClient(app).post(
        "/api/v1/scm/supplier-code-aliases/rematch",
        json={"supplier_id": str(w.supplier.id)},
    )

    assert r.status_code == 403, r.text
