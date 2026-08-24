"""AC-P1 / AC-P3 - a proforma invoice becomes a document with priced lines, once.

TEST-FIRST: `app/services/scm/proforma_invoice_service.py`, `app/models/scm.py`'s
`ProformaInvoice`/`ProformaInvoiceLine`, and migration 375 do not exist yet at the time
this file is written. Every test is expected to be red until they land - either as an
ImportError (service/models absent) or as an empty alias resolver (migration not yet
applied to the shared dev database), never as a wrong number silently accepted.

Runs on the REAL Postgres database via `pg_session` (rolled back at teardown), like
`test_packing_list_import.py`, because the reader resolves its alias table from the DB
when no resolver is passed in - so this suite also proves migration 375 was actually run
with `alembic upgrade head`, not merely written.

Every row is seeded under the `ZZPI` marker; nothing is borrowed from an existing table.
"""
from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest

from app.models.procurement import ProductSupplier, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.error_handler import AppException
from app.services.scm import proforma_invoice_service as svc
from tests._pg_fixture import pg_session
from tests.scm.fixtures.proforma_shapes import (
    kailu_proforma_workbook,
    preloading_list_workbook,
)

MARKER = "ZZPI"


def workbook(rows: list[list]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class World:
    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:8].upper()
        self.tag = tag
        self.cat = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=f"{MARKER}-CAT-{tag}",
            category_name=f"{MARKER} category",
        )
        self.uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=f"{MARKER}-U-{tag}"[:20], uom_name="pcs"
        )
        db.add_all([self.cat, self.uom])
        db.flush()
        self.supplier = Supplier(
            id=str(uuid.uuid4()),
            supplier_code=f"{MARKER}-S-{tag}",
            supplier_name=f"{MARKER} supplier",
            is_active=True,
        )
        db.add(self.supplier)
        db.flush()
        self.products: dict[str, Product] = {}

    def product(self, key: str) -> Product:
        if key not in self.products:
            p = Product(
                id=str(uuid.uuid4()),
                product_code=f"{MARKER}-{key}-{self.tag}",
                product_name=key,
                category_id=self.cat.id,
                base_uom_id=self.uom.id,
                list_price=0,
                is_active=True,
                is_discontinued=False,
            )
            self.db.add(p)
            self.db.flush()
            self.products[key] = p
        return self.products[key]

    def code(self, key: str) -> str:
        return self.product(key).product_code

    def price_list(self, key: str, *, currency: str, supplier=None) -> None:
        p = self.product(key)
        self.db.add(
            ProductSupplier(
                id=str(uuid.uuid4()),
                product_id=p.id,
                supplier_id=(supplier or self.supplier).id,
                standard_lead_time_days=30,
                currency=currency,
                unit_cost=1,
            )
        )
        self.db.flush()


def _invoices(db, w: World):
    from app.models.scm import ProformaInvoice

    return (
        db.query(ProformaInvoice)
        .filter(ProformaInvoice.supplier_id == w.supplier.id)
        .order_by(ProformaInvoice.pi_number)
        .all()
    )


def _lines(db, invoice_id: str):
    from app.models.scm import ProformaInvoiceLine

    return (
        db.query(ProformaInvoiceLine)
        .filter(ProformaInvoiceLine.invoice_id == invoice_id)
        .order_by(ProformaInvoiceLine.line_no)
        .all()
    )


# --------------------------------------------------------------------------------- #
# AC-P1.1 / AC-P1.2 / AC-P2.2 - applying the pre-loading list
# --------------------------------------------------------------------------------- #


def test_applying_the_preloading_list_creates_5_documents_30_lines():
    with pg_session() as db:
        w = World(db)
        # Only a couple of the 30 lines are matched to a product we hold; the rest name
        # a supplier code this catalogue does not carry, on purpose (AC-P1.3).
        data = preloading_list_workbook(
            {"SRTWC287A-RL-250": w.code("A"), "CWB242": w.code("B")}
        )

        out = svc.apply(db, data, supplier_id=str(w.supplier.id))

        assert out["documents_created"] == 5
        invoices = _invoices(db, w)
        assert len(invoices) == 5
        assert sum(len(_lines(db, inv.id)) for inv in invoices) == 30
        for inv in invoices:
            assert inv.currency == "CNY"
            assert inv.invoice_date == date(2026, 7, 31)


def test_applying_the_kailu_proforma_creates_1_document_19_lines():
    with pg_session() as db:
        w = World(db)
        data = kailu_proforma_workbook({"SRTWT7443": w.code("A")})

        out = svc.apply(db, data, supplier_id=str(w.supplier.id))

        assert out["documents_created"] == 1
        invoices = _invoices(db, w)
        assert len(invoices) == 1
        inv = invoices[0]
        assert inv.pi_number == "KL20260717"
        assert inv.invoice_date == date(2026, 7, 17)
        assert inv.currency == "CNY"

        lines = _lines(db, inv.id)
        assert len(lines) == 19
        po_refs = [ln.po_ref for ln in lines if ln.po_ref]
        assert po_refs == ["202605-S0060", "202605-S0084", "202605-S0060"]
        assert any(ln.item_code == "SRTWT8258\n-GM" for ln in lines)


# --------------------------------------------------------------------------------- #
# AC-P1.4 - idempotent by identity (company, supplier, pi_number)
# --------------------------------------------------------------------------------- #


def test_reuploading_the_same_file_replaces_the_lines_not_a_second_invoice():
    with pg_session() as db:
        w = World(db)
        data = kailu_proforma_workbook({"SRTWT7443": w.code("A")})

        first = svc.apply(db, data, supplier_id=str(w.supplier.id))
        second = svc.apply(db, data, supplier_id=str(w.supplier.id))

        assert first["documents_created"] == 1
        assert second["documents_created"] == 0
        assert second["documents_updated"] == 1

        invoices = _invoices(db, w)
        assert len(invoices) == 1
        assert len(_lines(db, invoices[0].id)) == 19


def test_two_suppliers_may_share_a_pi_number_without_colliding():
    # AC-P1.4's identity is (company, supplier, pi_number) - not pi_number alone.
    with pg_session() as db:
        w1 = World(db)
        w2 = World(db)
        data1 = kailu_proforma_workbook({"SRTWT7443": w1.code("A")})
        data2 = kailu_proforma_workbook({"SRTWT7443": w2.code("A")})

        svc.apply(db, data1, supplier_id=str(w1.supplier.id))
        svc.apply(db, data2, supplier_id=str(w2.supplier.id))

        assert len(_invoices(db, w1)) == 1
        assert len(_invoices(db, w2)) == 1
        assert _invoices(db, w1)[0].id != _invoices(db, w2)[0].id


# --------------------------------------------------------------------------------- #
# AC-P2.5 - a document with no stated number gets a derived, positional one
# --------------------------------------------------------------------------------- #


def test_an_unstated_document_number_is_derived_positionally_and_is_stable():
    with pg_session() as db:
        w = World(db)
        data = preloading_list_workbook(
            {"SRTWC287A-RL-250": w.code("A"), "CWB242": w.code("B")}
        )

        first = svc.apply(
            db, data, supplier_id=str(w.supplier.id), source_ref="2026-7-31.xlsx"
        )
        second = svc.apply(
            db, data, supplier_id=str(w.supplier.id), source_ref="2026-7-31.xlsx"
        )

        invoices = _invoices(db, w)
        assert {inv.pi_number for inv in invoices} == {
            f"PI-2026-7-31-{i}" for i in range(1, 6)
        }
        # Re-upload landed on the same 5 rows, not a second set.
        assert first["documents_created"] == 5
        assert second["documents_created"] == 0
        assert second["documents_updated"] == 5


# --------------------------------------------------------------------------------- #
# AC-P1.3 - product resolution is exact, case-insensitive, no fuzzy match
# --------------------------------------------------------------------------------- #


def test_an_unmatched_item_code_is_named_and_still_persisted_with_no_product():
    # A synthetic minimal file with a MARKER-prefixed code, rather than one of the real
    # Kailu/Jinbaichuan codes: this suite runs against the shared prod-copy Postgres
    # (pg_session, rolled back), and several of the real supplier codes genuinely exist
    # in that catalogue - asserting "unmatched" against them would be an assertion about
    # the database's current contents, exactly what this suite's own conventions forbid.
    with pg_session() as db:
        w = World(db)
        data = workbook(
            [
                ["产品型号", "数量", "PRICE"],
                [f"{MARKER}-NOT-A-REAL-CODE", 5, 12.5],
            ]
        )

        result = svc.validate(db, data, supplier_id=str(w.supplier.id), currency="USD")
        assert any(f"{MARKER}-NOT-A-REAL-CODE" in warn for warn in result["warnings"])

        out = svc.apply(db, data, supplier_id=str(w.supplier.id), currency="USD")
        assert out["documents_created"] == 1

        inv = _invoices(db, w)[0]
        lines = _lines(db, inv.id)
        assert len(lines) == 1
        assert lines[0].item_code == f"{MARKER}-NOT-A-REAL-CODE"
        assert lines[0].product_id is None


def test_product_match_is_case_insensitive_but_never_fuzzy():
    with pg_session() as db:
        w = World(db)
        exact_but_wrong_case = w.code("A").swapcase()
        near_miss = w.code("A") + "X"
        data = kailu_proforma_workbook(
            {
                "SRTWT7443": exact_but_wrong_case,
                "SRTWT8203": near_miss,
            }
        )

        svc.apply(db, data, supplier_id=str(w.supplier.id))

        inv = _invoices(db, w)[0]
        lines = {ln.item_code: ln for ln in _lines(db, inv.id)}
        assert lines[exact_but_wrong_case].product_id == w.product("A").id
        assert lines[near_miss].product_id is None


# --------------------------------------------------------------------------------- #
# AC-P3 - currency resolution order: form > document > supplier price list > error
# --------------------------------------------------------------------------------- #


def _priced_no_currency_hint_file(item_code: str, qty: float, price: float) -> bytes:
    """One line, priced, with a header that carries no currency-implying text at all."""
    return workbook([["产品型号", "数量", "PRICE"], [item_code, qty, price]])


def test_a_currency_given_on_the_form_wins_over_the_document():
    with pg_session() as db:
        w = World(db)
        data = kailu_proforma_workbook({"SRTWT7443": w.code("A")})  # document says CNY

        out = svc.apply(
            db, data, supplier_id=str(w.supplier.id), currency="USD"
        )

        assert out["documents_created"] == 1
        assert _invoices(db, w)[0].currency == "USD"


def test_a_currency_stated_by_the_document_wins_absent_a_form_value():
    with pg_session() as db:
        w = World(db)
        data = kailu_proforma_workbook({"SRTWT7443": w.code("A")})

        svc.apply(db, data, supplier_id=str(w.supplier.id))

        assert _invoices(db, w)[0].currency == "CNY"


def test_the_suppliers_price_list_resolves_currency_when_the_document_is_silent():
    with pg_session() as db:
        w = World(db)
        w.price_list("A", currency="USD")
        data = _priced_no_currency_hint_file(w.code("A"), 5, 12.5)

        out = svc.apply(db, data, supplier_id=str(w.supplier.id))

        assert out["documents_created"] == 1
        assert _invoices(db, w)[0].currency == "USD"


def test_a_mixed_currency_price_list_resolves_to_none_not_a_majority():
    with pg_session() as db:
        w = World(db)
        w.price_list("A", currency="USD")
        w.price_list("B", currency="MYR")
        data = _priced_no_currency_hint_file(w.code("A"), 5, 12.5)

        result = svc.validate(db, data, supplier_id=str(w.supplier.id))

        assert result["valid"] is False
        assert any("curren" in e.lower() for e in result["errors"])

        with pytest.raises(AppException) as exc:
            svc.apply(db, data, supplier_id=str(w.supplier.id))
        assert exc.value.status_code == 422


def test_priced_lines_with_no_currency_anywhere_are_refused_not_stored():
    with pg_session() as db:
        w = World(db)
        data = _priced_no_currency_hint_file(w.code("A"), 5, 12.5)

        result = svc.validate(db, data, supplier_id=str(w.supplier.id))
        assert result["valid"] is False
        assert any("curren" in e.lower() for e in result["errors"])

        with pytest.raises(AppException) as exc:
            svc.apply(db, data, supplier_id=str(w.supplier.id))
        assert exc.value.status_code == 422

        assert _invoices(db, w) == []


def test_a_currency_the_form_states_but_nobody_recognises_is_refused():
    """A typo in the currency box must not fall through to the document.

    Falling through succeeds - the file is read, the invoice is written, in CNY - and the
    operator is never told that the code they typed was ignored. The only visible symptom
    is a variance report in the wrong money weeks later.
    """
    with pg_session() as db:
        w = World(db)
        data = kailu_proforma_workbook({"SRTWT7443": w.code("A")})  # document says CNY

        with pytest.raises(AppException) as exc:
            svc.apply(db, data, supplier_id=str(w.supplier.id), currency="RMBB")

        assert exc.value.status_code == 422
        assert "RMBB" in str(exc.value.detail)
        assert _invoices(db, w) == []


# --------------------------------------------------------------------------------- #
# AC-P1.1 / AC-P1.2 - the header and line fields the document states actually land
# --------------------------------------------------------------------------------- #


def test_the_container_bill_of_lading_uom_and_description_reach_the_row():
    """The Kailu shape states neither a container nor a B/L, so a document that DOES state
    them is built here - otherwise "never invented" is the only half of AC-P1.1 under test
    and the labelled cells could stop reaching the header without anything failing."""
    with pg_session() as db:
        w = World(db)
        data = workbook(
            [
                [f"货柜号：{MARKER}U7", None, f"提单号：BL-{MARKER}-1"],
                ["产品型号", "品名", "数量", "单位", "PRICE"],
                [w.code("A"), "连体马桶", 12, "PCS", 33.5],
            ]
        )

        svc.apply(db, data, supplier_id=str(w.supplier.id), currency="CNY")

        inv = _invoices(db, w)[0]
        assert inv.container_ref == f"{MARKER}U7"
        assert inv.bl_ref == f"BL-{MARKER}-1"

        line = _lines(db, inv.id)[0]
        assert line.uom == "PCS"
        assert line.description == "连体马桶"
        assert float(line.unit_price) == 33.5
        assert line.product_id == w.product("A").id


def test_a_document_that_states_no_container_leaves_both_references_null():
    # AC-P1.1's other half: nullable, never invented.
    with pg_session() as db:
        w = World(db)
        data = kailu_proforma_workbook({"SRTWT7443": w.code("A")})

        svc.apply(db, data, supplier_id=str(w.supplier.id))

        inv = _invoices(db, w)[0]
        assert inv.container_ref is None
        assert inv.bl_ref is None


# --------------------------------------------------------------------------------- #
# AC-P2.5 - a derived number stays distinct however long the file's name is
# --------------------------------------------------------------------------------- #


def test_a_very_long_filename_still_gives_five_distinct_invoice_numbers():
    """`pi_number` is `String(100)`. Truncating the COMPOSED name pushes the block index off
    the end, so all five blocks derive one identical number and each one overwrites the last
  - five invoices arrive as one, and the file looks like it imported fine."""
    with pg_session() as db:
        w = World(db)
        long_name = ("2026-07-31 SORENTO PRE LOADING LIST FOR KLANG " * 4) + ".xlsx"
        assert len(long_name) > 100
        data = preloading_list_workbook(
            {"SRTWC287A-RL-250": w.code("A"), "CWB242": w.code("B")}
        )

        out = svc.apply(db, data, supplier_id=str(w.supplier.id), source_ref=long_name)

        assert out["documents_created"] == 5
        numbers = {inv.pi_number for inv in _invoices(db, w)}
        assert len(numbers) == 5
        assert all(len(n) <= 100 for n in numbers)


# --------------------------------------------------------------------------------- #
# Paging over the list has to be walkable, and every row of one upload ties on created_at
# --------------------------------------------------------------------------------- #


def test_walking_the_list_a_page_at_a_time_shows_each_invoice_exactly_once():
    """All five invoices of one stacked file share `created_at` to the microsecond, because it
    defaults to `now()` and that is the TRANSACTION timestamp. Ordering on it alone leaves the
    page boundary undefined, and a caller walking the offsets can be handed one invoice twice
    and never shown another."""
    with pg_session() as db:
        w = World(db)
        data = preloading_list_workbook(
            {"SRTWC287A-RL-250": w.code("A"), "CWB242": w.code("B")}
        )
        svc.apply(db, data, supplier_id=str(w.supplier.id))
        stamps = {inv.created_at for inv in _invoices(db, w)}
        assert len(stamps) == 1, "the tie this test exists for is not present"

        first = svc.list_for_supplier(db, supplier_id=str(w.supplier.id), limit=2, offset=0)
        second = svc.list_for_supplier(db, supplier_id=str(w.supplier.id), limit=2, offset=2)
        third = svc.list_for_supplier(db, supplier_id=str(w.supplier.id), limit=2, offset=4)

        assert first["total"] == 5
        walked = [r["id"] for r in first["data"] + second["data"] + third["data"]]
        assert len(walked) == 5
        assert len(set(walked)) == 5


# --------------------------------------------------------------------------------- #
# Company isolation - the supplier lookup is raw SQL and has to scope itself
# --------------------------------------------------------------------------------- #


def test_a_supplier_of_another_company_is_refused():
    """`suppliers` is an owned table and this lookup is raw SQL, which the ORM's company
    filter never sees. Unscoped, an operator could file a proforma against another
    company's supplier - and the preview would show that supplier's name back as
    confirmation that it was the right one."""
    from app.models.base import set_company_scope
    from app.models.company import Company

    with pg_session() as db:
        set_company_scope(db, None)
        a = Company(id=str(uuid.uuid4()), code=f"{MARKER}A{uuid.uuid4().hex[:6]}".upper(),
                    name=f"{MARKER} company A")
        b = Company(id=str(uuid.uuid4()), code=f"{MARKER}B{uuid.uuid4().hex[:6]}".upper(),
                    name=f"{MARKER} company B")
        db.add_all([a, b])
        db.flush()

        ours = Supplier(
            id=str(uuid.uuid4()), company_id=a.id,
            supplier_code=f"{MARKER}-SA-{uuid.uuid4().hex[:8]}",
            supplier_name=f"{MARKER} ours", is_active=True,
        )
        theirs = Supplier(
            id=str(uuid.uuid4()), company_id=b.id,
            supplier_code=f"{MARKER}-SB-{uuid.uuid4().hex[:8]}",
            supplier_name=f"{MARKER} theirs", is_active=True,
        )
        db.add_all([ours, theirs])
        db.flush()

        set_company_scope(db, frozenset({a.id}))

        svc.assert_supplier(db, str(ours.id))  # ours resolves

        with pytest.raises(AppException) as exc:
            svc.assert_supplier(db, str(theirs.id))
        assert exc.value.status_code == 422

        # And their name never leaks through the summary either.
        assert svc._supplier_label(db, str(theirs.id)) == (None, None)


def test_a_supplier_id_that_is_not_an_id_at_all_is_a_422_not_a_500():
    with pg_session() as db:
        with pytest.raises(AppException) as exc:
            svc.assert_supplier(db, "not-a-uuid")
        assert exc.value.status_code == 422
