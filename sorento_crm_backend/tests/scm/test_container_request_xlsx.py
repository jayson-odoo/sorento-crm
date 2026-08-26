"""F4 - the container request goes back to the supplier as THEIR OWN sheet, with our column.

`PLAN-scm-fulfilment-feedback.md` section 3 (F4), AC-C1 / C2 / C3 / C5. Ms Tee's ask, in her
words: "send them the same sheet back with the quantity to load filled in". So the test that
matters most is the ROUND TRIP - whatever we hand back has to be a file this system can read
again, because the supplier's next stock list is very often the file we sent them with the
numbers changed. If the export drifted out of the reader's shape, that loop would break in the
one place nobody looks.

The alias rows are reference data (migration 311 / `bootstrap_env`); `require_aliases` fails
rather than skips when they are missing, for the reason stated there.
"""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest

from app.models.email_outbox import EmailOutbox
from app.services.scm import container_request_xlsx as svc
from app.services.scm import supplier_notice_service as notices
from app.services.scm.supplier_inventory_reader import read_workbook
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import require_aliases
from tests.scm.test_loading_plan import World

MARKER = "ZZCX"

#: The supplier's own header, as the July JINBAICHUAN file writes it (migration 311's seeds).
HEADER = ["序号", "型号", "商标", "规格", "品名", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def workbook(rows: list[list]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def sheet(data: bytes) -> list[tuple]:
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(data), data_only=True)
    return [tuple(r) for r in wb.active.iter_rows(values_only=True)]


def _world(db) -> World:
    require_aliases(db, "supplier_inventory")
    return World(db)


def _uploaded(w: World, keys: list[str]) -> bytes:
    """The supplier's file as they sent it: a title line, their header, their rows."""
    rows: list[list] = [[f"{MARKER} 库存明细", None, None, None, None, None, None, None, None]]
    rows.append(list(HEADER))
    for i, key in enumerate(keys, start=1):
        p = w.product(key)
        rows.append([i, p.product_code, "SORENTO", "600mm", p.product_name, 120, 340, 0.21, ""])
    return workbook(rows)


def _line(w: World, key: str, qty: float) -> dict:
    p = w.product(key)
    return {"item_code": p.product_code, "product_name": p.product_name, "qty": qty}


# --------------------------------------------------------------------------- #
# their sheet, our column
# --------------------------------------------------------------------------- #


def test_the_export_reads_back_through_the_stock_list_reader(monkeypatch):
    # AC-C2, and the point of the whole slice: the supplier answers with the file we sent
    # them. An export the reader cannot parse breaks the loop silently.
    with pg_session() as db:
        w = _world(db)
        monkeypatch.setattr(svc, "_uploaded_sheet", lambda _db, _sid: _uploaded(w, ["A", "B"]))

        data = svc.build(db, supplier={"supplier_code": "JBC", "supplier_name": "JBC"},
                         supplier_id=str(w.supplier.id), lines=[_line(w, "A", 500)])

        out = read_workbook(data, db=db)
        assert out.ok, out.missing_columns
        assert [r.item_code for r in out.rows] == [
            w.product("A").product_code,
            w.product("B").product_code,
        ]
        assert out.rows[0].qty_packed == 120
        assert out.rows[0].qty_unfinished == 340
        assert out.rows[0].cbm_per_unit == 0.21


def test_their_header_row_is_kept_as_uploaded_with_our_column_appended():
    # AC-C2. Their spellings, their order, their title line above it - plus one column at the
    # end. Anything else and the file stops looking like the one they wrote.
    with pg_session() as db:
        w = _world(db)
        rows = sheet(
            svc._with_qty_to_load(_uploaded(w, ["A"]), db=db, lines=[_line(w, "A", 500)])
        )

        assert rows[0][0] == f"{MARKER} 库存明细"
        assert list(rows[1][: len(HEADER)]) == HEADER
        assert rows[1][len(HEADER)] == svc.QTY_TO_LOAD_HEADER
        assert rows[2][len(HEADER)] == 500


def test_a_requested_product_the_stock_list_never_named_is_appended_below():
    # AC-C2. It is still something we are asking them to pack; dropping it because their own
    # sheet has no line for it is how an ask goes out short.
    with pg_session() as db:
        w = _world(db)
        rows = sheet(
            svc._with_qty_to_load(
                _uploaded(w, ["A"]),
                db=db,
                lines=[_line(w, "A", 500), _line(w, "NEW", 80)],
            )
        )

        codes = [r[1] for r in rows]
        assert codes.index(w.product("NEW").product_code) > codes.index(
            w.product("A").product_code
        )
        appended = next(r for r in rows if r[1] == w.product("NEW").product_code)
        assert appended[len(HEADER)] == 80


def test_a_row_we_are_not_asking_for_has_an_empty_qty_cell():
    # AC-C3. A zero reads as "pack none of these", which is a different instruction from
    # "we did not ask about these" - and the supplier acts on the difference.
    with pg_session() as db:
        w = _world(db)
        rows = sheet(
            svc._with_qty_to_load(_uploaded(w, ["A", "B"]), db=db, lines=[_line(w, "A", 500)])
        )

        b = next(r for r in rows if r[1] == w.product("B").product_code)
        assert b[len(HEADER)] is None


def test_a_zero_quantity_line_is_an_empty_cell_too():
    # AC-C3, the other half: the grid can send a reviewed line at zero.
    with pg_session() as db:
        w = _world(db)
        rows = sheet(
            svc._with_qty_to_load(_uploaded(w, ["A"]), db=db, lines=[_line(w, "A", 0)])
        )

        assert rows[2][len(HEADER)] is None


# --------------------------------------------------------------------------- #
# no stock list at all
# --------------------------------------------------------------------------- #


def test_without_a_retained_sheet_the_export_falls_back_to_our_own_columns(monkeypatch):
    # AC-C5. There is no sheet of theirs to answer in, so the file states what we know:
    # the item, the name, what they told us they hold, and what to load.
    with pg_session() as db:
        w = _world(db)
        w.stock("A", packed=120, unfinished=340)
        monkeypatch.setattr(svc, "_uploaded_sheet", lambda _db, _sid: None)

        data = svc.build(db, supplier={"supplier_code": "JBC", "supplier_name": "JBC"},
                         supplier_id=str(w.supplier.id), lines=[_line(w, "A", 500)])

        rows = sheet(data)
        assert list(rows[0]) == svc.FALLBACK_HEADER
        assert rows[1][0] == w.product("A").product_code
        assert rows[1][2] == 120
        assert rows[1][3] == 340
        assert rows[1][4] == 500


def test_the_fallback_export_reads_back_through_the_stock_list_reader(monkeypatch):
    # AC-C2's round trip again, on the branch that has no file to copy: the fallback layout
    # is not allowed to be the one shape the reader cannot take back.
    with pg_session() as db:
        w = _world(db)
        w.stock("A", packed=120, unfinished=340)
        monkeypatch.setattr(svc, "_uploaded_sheet", lambda _db, _sid: None)

        data = svc.build(db, supplier={"supplier_code": "JBC", "supplier_name": "JBC"},
                         supplier_id=str(w.supplier.id), lines=[_line(w, "A", 500)])

        out = read_workbook(data, db=db)
        assert out.ok, out.missing_columns
        assert [r.item_code for r in out.rows] == [w.product("A").product_code]
        assert out.rows[0].qty_packed == 120
        assert out.rows[0].qty_unfinished == 340


def test_an_unreadable_retained_sheet_falls_back_rather_than_failing_the_send(monkeypatch):
    # The send must not die because a stored file is corrupt: the request itself is the point,
    # and a fallback sheet still says what to pack.
    with pg_session() as db:
        w = _world(db)
        monkeypatch.setattr(svc, "_uploaded_sheet", lambda _db, _sid: b"not a workbook")

        data = svc.build(db, supplier={"supplier_code": "JBC", "supplier_name": "JBC"},
                         supplier_id=str(w.supplier.id), lines=[_line(w, "A", 500)])

        assert list(sheet(data)[0]) == svc.FALLBACK_HEADER


def test_a_sheet_whose_header_we_cannot_find_falls_back(monkeypatch):
    # No item-code column means no row to write a quantity against, so their layout cannot
    # carry our ask at all.
    with pg_session() as db:
        w = _world(db)
        monkeypatch.setattr(
            svc, "_uploaded_sheet", lambda _db, _sid: workbook([["a", "b"], [1, 2]])
        )

        data = svc.build(db, supplier={"supplier_code": "JBC", "supplier_name": "JBC"},
                         supplier_id=str(w.supplier.id), lines=[_line(w, "A", 500)])

        assert list(sheet(data)[0]) == svc.FALLBACK_HEADER


# --------------------------------------------------------------------------- #
# filename
# --------------------------------------------------------------------------- #


def test_the_filename_names_the_supplier_and_the_day():
    # AC-C1: `container-request-{supplier}-{stamp}.xlsx`, beside the PDF of the same stem.
    name = svc.filename({"supplier_code": "JBC 01/A", "supplier_name": "x"})
    assert name.startswith("container-request-JBC-01-A-")
    assert name.endswith(".xlsx")


# --------------------------------------------------------------------------- #
# what the send does with it
# --------------------------------------------------------------------------- #


@pytest.fixture
def _no_pdf_no_storage(monkeypatch):
    """Render and object store stubbed - the same stub S8's own suite uses."""
    monkeypatch.setattr(notices, "render_document", lambda html: b"%PDF-1.4 stub")
    monkeypatch.setattr(notices, "_store", lambda data, filename: ("s3", f"exports/t/{filename}"))


def test_a_sent_request_keeps_the_sheet_beside_its_pdf(_no_pdf_no_storage):
    # AC-C1. Two files, one act: the notice records where both of them went.
    with pg_session() as db:
        w = _world(db)
        w.supplier.email = f"{MARKER}@example.test"
        db.flush()

        out = notices.request_and_notify(
            db,
            supplier_id=str(w.supplier.id),
            lines=[{"product_id": str(w.product("A").id), "qty": 500}],
        )

        notice = out["notices"][0]
        assert notice["has_document"] is True
        assert notice["has_xlsx"] is True
        assert notice["xlsx_filename"].endswith(".xlsx")


def test_the_email_carries_both_files_not_two_emails(_no_pdf_no_storage):
    # AC-C1: one email. The PDF rides the outbox row's own columns and the sheet rides the
    # metadata the drainer reads, so the supplier gets one message with two attachments.
    with pg_session() as db:
        w = _world(db)
        w.supplier.email = f"{MARKER}-{uuid.uuid4().hex[:6]}@example.test"
        db.flush()

        notices.request_and_notify(
            db,
            supplier_id=str(w.supplier.id),
            lines=[{"product_id": str(w.product("A").id), "qty": 500}],
        )

        rows = (
            db.query(EmailOutbox)
            .filter(EmailOutbox.recipient_email == w.supplier.email)
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.attachment_filename.endswith(".pdf")
        extra = row.metadata_json["extra_attachments"]
        assert len(extra) == 1
        assert extra[0]["filename"].endswith(".xlsx")


def test_the_drainer_reads_both_attachments_off_one_row(monkeypatch):
    # The half of AC-C1 the outbox row alone cannot prove: what actually gets attached.
    from app.tasks import email_outbox_tasks

    class _Backend:
        def download_file(self, key):
            return f"bytes:{key}".encode()

    monkeypatch.setattr(
        "app.services.storage_router.get_backend", lambda provider: _Backend()
    )
    row = EmailOutbox(
        event_key="supplier_loading_notice",
        recipient_email="x@example.test",
        subject="s",
        body_text="b",
        attachment_filename="request.pdf",
        attachment_storage_provider="s3",
        attachment_storage_key="exports/t/request.pdf",
        metadata_json={
            "extra_attachments": [
                {
                    "filename": "request.xlsx",
                    "storage_provider": "s3",
                    "storage_key": "exports/t/request.xlsx",
                }
            ]
        },
    )

    out = email_outbox_tasks._attachments_for(row)

    assert [a[0] for a in out] == ["request.pdf", "request.xlsx"]
    assert out[1][1] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_an_email_with_no_attachment_at_all_still_reads_as_none(monkeypatch):
    # Guard: every other event in the system sends no file, and `None` (not `[]`) is what
    # `send_mime_email` has always been handed for those.
    from app.tasks import email_outbox_tasks

    row = EmailOutbox(
        event_key="x", recipient_email="x@example.test", subject="s", body_text="b"
    )

    assert email_outbox_tasks._attachments_for(row) is None
