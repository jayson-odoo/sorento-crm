"""DOC-RELATIONS: SO <-> DO <-> billing document relations, from every side (red tests first).

Plan: documentation/plans/order-management/PLAN-doc-relations-27oct.md
UAC:  documentation/plans/order-management/doc-relations-27oct-acceptance-criteria.md

  R1  SO -> DOs: a DO line naming the SO by `from_doc_no` (type SO / NULL), a DO line whose
      `sales_order_line_id` is on the SO, or the DO header's `sales_order_id`; deleted and
      cancelled DOs left out (the Delivery tab's own predicate, `so_line_history`).
  R2  SO -> billing documents: a billing line resolved onto the SO's lines, transferred from the
      SO by number, or transferred from one of the SO's DOs by number; plus every credit/debit
      note against one of those. The SO427775 case: invoice from a DO whose lines never got a
      `sales_order_line_id`.
  R3  DO -> SOs and DO -> billing documents (and notes against them).
  R4  Billing document -> SOs and DOs (DO numbers resolved to the CRM row, plain number kept
      when it is not in the CRM); a note inherits its invoice's SO and DO.
  R5  Company scope: a same-numbered DO / document in another company never links.
  R6  Routes: `/related` on all three records, each kind masked (null) without its view slug,
      403 without the record's own slug; the billing list's `sales_order_id` widened and
      `delivery_order_id` added, server-side sortable.

Postgres only; every row seeded here (CI's database has none).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

# MUST be the first app import - resolves the circular import in app.modules.runtime.guards.
from app.main import app  # noqa: E402

from app.models.base import company_scope
from app.models.company import Company
from app.models.finance import BillingDocument, BillingDocumentLine
from app.models.inventory import Warehouse
from app.models.order import Order, OrderLine, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.company_scope import DEFAULT_COMPANY_ID

from ._pg_fixture import blank_session, unique_code

MARKER = "ZZDREL"
SO_VIEW = "scm.dashboard.view"
DO_VIEW = "order_management.orders.view"
BILL_VIEW = "finance.billing_documents.view"
ALL = (SO_VIEW, DO_VIEW, BILL_VIEW)


def _uid() -> str:
    return str(uuid.uuid4())


class _World:
    def __init__(self, db):
        self.db = db
        self.a = DEFAULT_COMPANY_ID
        suffix = uuid.uuid4().hex[:8]
        other = Company(id=_uid(), name=f"{MARKER} B {suffix}", code=f"ZR{suffix}")
        db.add(other)
        db.flush()
        self.b = str(other.id)
        self.product = self._product(self.a)
        self.product_b = self._product(self.b)
        self.wh = self._wh(self.a)
        self.wh_b = self._wh(self.b)
        self._seq = 0

    def _product(self, company_id):
        cat = ProductCategory(category_code=unique_code(MARKER)[:50], category_name="cat",
                              company_id=company_id)
        uom = UnitOfMeasure(uom_code=unique_code("U")[:20], uom_name="u", company_id=company_id)
        self.db.add_all([cat, uom])
        self.db.flush()
        p = Product(product_code=unique_code(MARKER), product_name=f"{MARKER} p",
                    category_id=cat.id, base_uom_id=uom.id, list_price=0, company_id=company_id)
        self.db.add(p)
        self.db.flush()
        return p

    def _wh(self, company_id):
        w = Warehouse(id=_uid(), warehouse_code=unique_code("WH")[:40], warehouse_name="wh",
                      is_active=True, company_id=company_id)
        self.db.add(w)
        self.db.flush()
        return w

    def so(self, number, *, company_id=None, lines=1, order_date=date(2026, 10, 14)):
        company_id = company_id or self.a
        so = SalesOrder(id=_uid(), so_number=number, status="open", company_id=company_id,
                        order_date=order_date)
        self.db.add(so)
        self.db.flush()
        product = self.product if company_id == self.a else self.product_b
        for _ in range(lines):
            self.db.add(SalesOrderLine(id=_uid(), sales_order_id=so.id, product_id=product.id,
                                       qty_ordered=10, qty_delivered=0, line_status="open",
                                       company_id=company_id))
        self.db.flush()
        self.db.refresh(so)
        return so

    def do(self, number, *, company_id=None, lines=(), cancelled=False, deleted=False,
           sales_order=None, order_date=date(2026, 10, 21)):
        """`lines`: dicts with from_doc_no / from_doc_type (default SO) / so_line."""
        company_id = company_id or self.a
        o = Order(id=_uid(), order_number=number, order_date=order_date, is_cancelled=cancelled,
                  company_id=company_id, sales_order_id=sales_order.id if sales_order else None)
        if deleted:
            o.deleted_at = datetime(2026, 10, 22)
        self.db.add(o)
        self.db.flush()
        product = self.product if company_id == self.a else self.product_b
        wh = self.wh if company_id == self.a else self.wh_b
        for seq, spec in enumerate(lines, start=1):
            so_line = spec.get("so_line")
            self.db.add(OrderLine(id=_uid(), order_id=o.id, product_id=product.id,
                                  warehouse_id=wh.id, quantity=spec.get("qty", 5),
                                  line_sequence=seq, from_doc_no=spec.get("from_doc_no"),
                                  from_doc_type=spec.get("from_doc_type", "SO"),
                                  sales_order_line_id=so_line.id if so_line else None,
                                  company_id=company_id))
        self.db.flush()
        return o

    def doc(self, doc_no, *, document_type="invoice", company_id=None, lines=(), against=None,
            against_doc_no=None, doc_date=date(2026, 10, 22), status="posted"):
        """`lines`: dicts with from_doc_type / from_doc_no / so_line."""
        company_id = company_id or self.a
        self._seq += 1
        row = BillingDocument(
            company_id=company_id, document_type=document_type, doc_no=doc_no, doc_date=doc_date,
            currency_code="MYR", currency_rate=1, net_total=Decimal("100"),
            tax_total=Decimal("0"), total=Decimal("100"), local_net_total=Decimal("100"),
            status=status, against_document_id=against.id if against else None,
            against_doc_no=against_doc_no or (against.doc_no if against else None),
            source_system="autocount", source_ref=f"{MARKER}:{doc_no}:{uuid.uuid4().hex[:6]}",
        )
        self.db.add(row)
        self.db.flush()
        for n, spec in enumerate(lines, start=1):
            so_line = spec.get("so_line")
            self.db.add(BillingDocumentLine(
                company_id=company_id, document_id=row.id, line_no=n, item_code="ITEM",
                quantity=Decimal("1"), net_amount=Decimal("100"), line_total=Decimal("100"),
                from_doc_type=spec.get("from_doc_type"), from_doc_no=spec.get("from_doc_no"),
                sales_order_line_id=so_line.id if so_line else None,
                source_ref=f"{row.source_ref}:{n}",
            ))
        self.db.flush()
        return row


@pytest.fixture
def world():
    with blank_session() as db:
        with company_scope(db, None):
            w = _World(db)
        db.commit()
        yield w


def _svc():
    from app.services import document_relations

    return document_relations


def _nos(items):
    return [i["doc_no"] for i in items]


def _so427775(w):
    """SO427775 shape: a DO whose lines name the SO by number only, and an invoice transferred
    from that DO whose lines therefore never resolved a `sales_order_line_id`."""
    so = w.so(f"{MARKER}-SO427775", lines=2)
    do = w.do(f"{MARKER}-202610-3905", lines=[{"from_doc_no": so.so_number}] * 4)
    iv = w.doc(f"{MARKER}-IV-202610-3905",
               lines=[{"from_doc_type": "DO", "from_doc_no": do.order_number}] * 2)
    return so, do, iv


# --------------------------------------------------------------------------- service (R1-R5)


def test_so427775_every_side_sees_the_other_two(world):
    so, do, iv = _so427775(world)
    rel = _svc()

    s = rel.relations_for_sales_order(world.db, so)
    assert _nos(s["delivery_orders"]) == [do.order_number]
    assert s["delivery_orders"][0]["id"] == str(do.id)
    assert _nos(s["billing_documents"]) == [iv.doc_no]
    assert s["billing_documents"][0]["id"] == str(iv.id)
    assert s["billing_documents"][0]["document_type"] == "invoice"
    assert s["sales_orders"] == []

    d = rel.relations_for_delivery_order(world.db, do)
    assert [(x["id"], x["doc_no"]) for x in d["sales_orders"]] == [(str(so.id), so.so_number)]
    assert _nos(d["billing_documents"]) == [iv.doc_no]
    assert d["delivery_orders"] == []

    b = rel.relations_for_billing_document(world.db, iv)
    assert [(x["id"], x["doc_no"]) for x in b["sales_orders"]] == [(str(so.id), so.so_number)]
    assert [(x["id"], x["doc_no"]) for x in b["delivery_orders"]] == [(str(do.id), do.order_number)]
    assert b["billing_documents"] == []


def test_item_shapes_carry_the_date(world):
    so, do, iv = _so427775(world)
    s = _svc().relations_for_sales_order(world.db, so)
    assert set(s["delivery_orders"][0]) >= {"id", "doc_no", "doc_date"}
    assert s["delivery_orders"][0]["doc_date"] == "2026-10-21"
    assert set(s["billing_documents"][0]) >= {"id", "doc_no", "doc_date", "document_type", "status"}
    b = _svc().relations_for_billing_document(world.db, iv)
    assert b["sales_orders"][0]["doc_date"] == "2026-10-14"


def test_invoice_transferred_from_the_so_directly(world):
    so = world.so(f"{MARKER}-SO-DIRECT")
    iv = world.doc(f"{MARKER}-IV-DIRECT", lines=[{"from_doc_type": "SO", "from_doc_no": so.so_number}])
    rel = _svc()
    assert _nos(rel.relations_for_sales_order(world.db, so)["billing_documents"]) == [iv.doc_no]
    b = rel.relations_for_billing_document(world.db, iv)
    assert _nos(b["sales_orders"]) == [so.so_number]
    assert b["delivery_orders"] == []


def test_resolved_so_line_link_still_counts(world):
    so = world.so(f"{MARKER}-SO-RES")
    iv = world.doc(f"{MARKER}-IV-RES", lines=[{"so_line": so.lines[0]}])
    assert _nos(_svc().relations_for_sales_order(world.db, so)["billing_documents"]) == [iv.doc_no]


def test_one_do_many_invoices(world):
    so = world.so(f"{MARKER}-SO-MANY")
    do = world.do(f"{MARKER}-DO-MANY", lines=[{"from_doc_no": so.so_number}])
    iv1 = world.doc(f"{MARKER}-IV-M1", lines=[{"from_doc_type": "DO", "from_doc_no": do.order_number}])
    iv2 = world.doc(f"{MARKER}-IV-M2", lines=[{"from_doc_type": "DO", "from_doc_no": do.order_number}],
                    doc_date=date(2026, 10, 23))
    rel = _svc()
    assert _nos(rel.relations_for_delivery_order(world.db, do)["billing_documents"]) == [iv1.doc_no, iv2.doc_no]
    assert _nos(rel.relations_for_sales_order(world.db, so)["billing_documents"]) == [iv1.doc_no, iv2.doc_no]


def test_credit_note_against_the_invoice_follows_it(world):
    so, do, iv = _so427775(world)
    cn = world.doc(f"{MARKER}-CN-1", document_type="credit_note", against=iv,
                   doc_date=date(2026, 10, 25))
    rel = _svc()
    assert _nos(rel.relations_for_sales_order(world.db, so)["billing_documents"]) == [iv.doc_no, cn.doc_no]
    assert _nos(rel.relations_for_delivery_order(world.db, do)["billing_documents"]) == [iv.doc_no, cn.doc_no]
    c = rel.relations_for_billing_document(world.db, cn)
    assert _nos(c["sales_orders"]) == [so.so_number]
    assert _nos(c["delivery_orders"]) == [do.order_number]
    assert _nos(c["billing_documents"]) == [iv.doc_no]
    # And the invoice names its note.
    assert _nos(rel.relations_for_billing_document(world.db, iv)["billing_documents"]) == [cn.doc_no]


def test_cash_sale_with_no_order_has_nothing_related(world):
    cs = world.doc(f"{MARKER}-CS-1", document_type="cash_sale", lines=[{}])
    assert _svc().relations_for_billing_document(world.db, cs) == {
        "sales_orders": [], "delivery_orders": [], "billing_documents": [],
    }


def test_do_number_not_in_the_crm_is_kept_without_an_id(world):
    iv = world.doc(f"{MARKER}-IV-GHOST", lines=[{"from_doc_type": "DO", "from_doc_no": "GHOST-DO-1"}])
    b = _svc().relations_for_billing_document(world.db, iv)
    assert [(d["id"], d["doc_no"], d["doc_date"]) for d in b["delivery_orders"]] == [
        (None, "GHOST-DO-1", None)
    ]


def test_do_linked_by_header_or_by_so_line(world):
    so = world.so(f"{MARKER}-SO-HDR")
    by_header = world.do(f"{MARKER}-DO-HDR", sales_order=so)
    by_line = world.do(f"{MARKER}-DO-LN", lines=[{"so_line": so.lines[0], "from_doc_no": None,
                                                   "from_doc_type": None}])
    rel = _svc()
    assert sorted(_nos(rel.relations_for_sales_order(world.db, so)["delivery_orders"])) == sorted(
        [by_header.order_number, by_line.order_number]
    )
    assert _nos(rel.relations_for_delivery_order(world.db, by_header)["sales_orders"]) == [so.so_number]
    assert _nos(rel.relations_for_delivery_order(world.db, by_line)["sales_orders"]) == [so.so_number]


def test_deleted_and_cancelled_dos_are_left_out_like_the_delivery_tab(world):
    so = world.so(f"{MARKER}-SO-GONE")
    world.do(f"{MARKER}-DO-DEL", lines=[{"from_doc_no": so.so_number}], deleted=True)
    world.do(f"{MARKER}-DO-CXL", lines=[{"from_doc_no": so.so_number}], cancelled=True)
    assert _svc().relations_for_sales_order(world.db, so)["delivery_orders"] == []


def test_another_companys_same_numbers_never_link(world):
    so, do, iv = _so427775(world)
    do_b = world.do(f"{MARKER}-DO-B", company_id=world.b, lines=[{"from_doc_no": so.so_number}])
    iv_b = world.doc(f"{MARKER}-IV-B", company_id=world.b,
                     lines=[{"from_doc_type": "DO", "from_doc_no": do.order_number}])
    so_b = world.so(so.so_number, company_id=world.b)
    rel = _svc()
    s = rel.relations_for_sales_order(world.db, so)
    assert do_b.order_number not in _nos(s["delivery_orders"])
    assert iv_b.doc_no not in _nos(s["billing_documents"])
    assert _nos(rel.relations_for_delivery_order(world.db, do)["billing_documents"]) == [iv.doc_no]
    # A DO in A naming the SO number resolves to A's order, never B's same-numbered one.
    assert [x["id"] for x in rel.relations_for_delivery_order(world.db, do)["sales_orders"]] == [str(so.id)]
    assert so_b.id not in {x["id"] for x in rel.relations_for_billing_document(world.db, iv)["sales_orders"]}


def test_a_so_typed_line_naming_a_do_number_is_not_a_do(world):
    so = world.so(f"{MARKER}-SO-T")
    do = world.do(f"{MARKER}-SAME-NO", lines=[{"from_doc_no": so.so_number}])
    iv = world.doc(f"{MARKER}-IV-T", lines=[{"from_doc_type": "SO", "from_doc_no": do.order_number}])
    assert _svc().relations_for_delivery_order(world.db, do)["billing_documents"] == []
    assert _svc().relations_for_billing_document(world.db, iv)["delivery_orders"] == []


# --------------------------------------------------------------------------- routes (R6)


def _client(db):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.services.company_scope_resolver import apply_company_scope

    user_id = _uid()
    actor = {"id": user_id, "email": f"{user_id}@zzdrel.test", "role": "user"}
    scope = frozenset({DEFAULT_COMPANY_ID})

    def _scope():
        from app.models.base import set_company_scope

        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = _scope
    return TestClient(app)


@pytest.fixture
def api(world, monkeypatch):
    from app.services.user_service import UserPermissionService

    def make(*slugs):
        granted = list(slugs)
        monkeypatch.setattr(
            UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in granted
        )
        monkeypatch.setattr(
            UserPermissionService, "get_user_permission_slugs", lambda self, uid: list(granted)
        )
        monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
        return _client(world.db)

    with company_scope(world.db, frozenset({DEFAULT_COMPANY_ID})):
        try:
            yield make
        finally:
            app.dependency_overrides.clear()


def _ok(res):
    assert res.status_code == 200, res.text
    return res.json()


class TestRelatedRoutes:
    def test_sales_order_related(self, world, api):
        so, do, iv = _so427775(world)
        body = _ok(api(*ALL).get(f"/api/v1/scm/sales-orders/{so.id}/related"))
        assert _nos(body["delivery_orders"]) == [do.order_number]
        assert _nos(body["billing_documents"]) == [iv.doc_no]

    def test_delivery_order_related(self, world, api):
        so, do, iv = _so427775(world)
        body = _ok(api(*ALL).get(f"/api/v1/order-management/orders/{do.id}/related"))
        assert _nos(body["sales_orders"]) == [so.so_number]
        assert _nos(body["billing_documents"]) == [iv.doc_no]

    def test_billing_document_related(self, world, api):
        so, do, iv = _so427775(world)
        body = _ok(api(*ALL).get(f"/api/v1/finance/billing-documents/{iv.id}/related"))
        assert _nos(body["sales_orders"]) == [so.so_number]
        assert [x["id"] for x in body["delivery_orders"]] == [str(do.id)]

    def test_rows_are_one_table_sorted_server_side(self, world, api):
        """Owner 27 Oct 15:51: Related is a table (Type, Number, Date, Status, Amount), every
        column sortable server side."""
        so, do, iv = _so427775(world)
        cn = world.doc(f"{MARKER}-CN-R", document_type="credit_note", against=iv,
                       doc_date=date(2026, 10, 25))
        client = api(*ALL)
        url = f"/api/v1/scm/sales-orders/{so.id}/related"
        rows = _ok(client.get(url))["rows"]
        # Default: date ascending.
        assert [r["doc_no"] for r in rows] == [do.order_number, iv.doc_no, cn.doc_no]
        assert set(rows[0]) >= {"kind", "type", "id", "doc_no", "doc_date", "status", "amount",
                                "currency_code"}
        assert [r["type"] for r in rows] == ["delivery_order", "invoice", "credit_note"]
        assert [r["kind"] for r in rows] == ["delivery_order", "billing_document", "billing_document"]
        assert rows[1]["amount"] == 100.0 and rows[1]["currency_code"] == "MYR"
        desc = _ok(client.get(url, params={"sort": "doc_date", "dir": "desc"}))["rows"]
        assert [r["doc_no"] for r in desc] == [cn.doc_no, iv.doc_no, do.order_number]
        by_type = _ok(client.get(url, params={"sort": "type", "dir": "asc"}))["rows"]
        assert [r["type"] for r in by_type] == ["credit_note", "delivery_order", "invoice"]
        assert client.get(url, params={"sort": "bogus"}).status_code == 422

    def test_rows_leave_out_a_masked_kind(self, world, api):
        so, do, iv = _so427775(world)
        rows = _ok(api(SO_VIEW, BILL_VIEW).get(f"/api/v1/scm/sales-orders/{so.id}/related"))["rows"]
        assert [r["kind"] for r in rows] == ["billing_document"]

    def test_each_kind_is_null_without_its_view_slug(self, world, api):
        so, do, iv = _so427775(world)
        body = _ok(api(SO_VIEW).get(f"/api/v1/scm/sales-orders/{so.id}/related"))
        assert body["delivery_orders"] is None
        assert body["billing_documents"] is None
        body = _ok(api(DO_VIEW).get(f"/api/v1/order-management/orders/{do.id}/related"))
        assert body["sales_orders"] is None
        assert body["billing_documents"] is None
        body = _ok(api(BILL_VIEW).get(f"/api/v1/finance/billing-documents/{iv.id}/related"))
        assert body["sales_orders"] is None
        assert body["delivery_orders"] is None

    @pytest.mark.parametrize(
        "path_of, missing",
        [
            (lambda so, do, iv: f"/api/v1/scm/sales-orders/{so.id}/related", SO_VIEW),
            (lambda so, do, iv: f"/api/v1/order-management/orders/{do.id}/related", DO_VIEW),
            (lambda so, do, iv: f"/api/v1/finance/billing-documents/{iv.id}/related", BILL_VIEW),
        ],
    )
    def test_403_without_the_records_own_slug(self, world, api, path_of, missing):
        so, do, iv = _so427775(world)
        granted = [s for s in ALL if s != missing]
        assert api(*granted).get(path_of(so, do, iv)).status_code == 403

    def test_another_companys_record_is_404(self, world, api):
        so_b = world.so(f"{MARKER}-SO-OTHER", company_id=world.b)
        do_b = world.do(f"{MARKER}-DO-OTHER", company_id=world.b)
        iv_b = world.doc(f"{MARKER}-IV-OTHER", company_id=world.b)
        client = api(*ALL)
        assert client.get(f"/api/v1/scm/sales-orders/{so_b.id}/related").status_code == 404
        assert client.get(f"/api/v1/order-management/orders/{do_b.id}/related").status_code == 404
        assert client.get(f"/api/v1/finance/billing-documents/{iv_b.id}/related").status_code == 404


class TestBillingListFilters:
    LIST = "/api/v1/finance/billing-documents"

    def test_sales_order_id_finds_the_invoice_through_its_do(self, world, api):
        so, do, iv = _so427775(world)
        cn = world.doc(f"{MARKER}-CN-L", document_type="credit_note", against=iv,
                       doc_date=date(2026, 10, 25))
        rows = _ok(api(BILL_VIEW).get(self.LIST, params={"sales_order_id": so.id}))["data"]
        assert sorted(r["doc_no"] for r in rows) == sorted([iv.doc_no, cn.doc_no])

    def test_delivery_order_id_lists_the_dos_documents_sorted_server_side(self, world, api):
        so = world.so(f"{MARKER}-SO-LS")
        do = world.do(f"{MARKER}-DO-LS", lines=[{"from_doc_no": so.so_number}])
        world.doc(f"{MARKER}-IV-B2", lines=[{"from_doc_type": "DO", "from_doc_no": do.order_number}])
        world.doc(f"{MARKER}-IV-A1", lines=[{"from_doc_type": "DO", "from_doc_no": do.order_number}])
        world.doc(f"{MARKER}-IV-UNRELATED", lines=[{}])
        client = api(BILL_VIEW)
        asc = _ok(client.get(self.LIST, params={"delivery_order_id": do.id, "sort": "doc_no", "dir": "asc"}))
        assert [r["doc_no"] for r in asc["data"]] == [f"{MARKER}-IV-A1", f"{MARKER}-IV-B2"]
        desc = _ok(client.get(self.LIST, params={"delivery_order_id": do.id, "sort": "doc_no", "dir": "desc"}))
        assert [r["doc_no"] for r in desc["data"]] == [f"{MARKER}-IV-B2", f"{MARKER}-IV-A1"]

    def test_delivery_order_id_must_be_a_uuid(self, world, api):
        assert api(BILL_VIEW).get(self.LIST, params={"delivery_order_id": "nope"}).status_code == 422

    def test_detail_related_carries_linked_delivery_orders(self, world, api):
        so, do, iv = _so427775(world)
        related = _ok(api(*ALL).get(f"{self.LIST}/{iv.id}"))["related"]
        assert related["delivery_orders"] == [
            {"id": str(do.id), "doc_no": do.order_number, "doc_date": "2026-10-21"}
        ]
        assert [s["doc_no"] for s in related["sales_orders"]] == [so.so_number]


    def test_detail_masks_orders_the_viewer_cannot_open(self, world, api):
        """Security review should-fix: the record's own related orders follow the `/related`
        mask, so a finance-only viewer gets no order ids it could not open."""
        so, do, iv = _so427775(world)
        related = _ok(api(BILL_VIEW).get(f"{self.LIST}/{iv.id}"))["related"]
        assert related["delivery_orders"] == []
        assert related["sales_orders"] == []
        related = _ok(api(BILL_VIEW, DO_VIEW).get(f"{self.LIST}/{iv.id}"))["related"]
        assert [d["doc_no"] for d in related["delivery_orders"]] == [do.order_number]
        assert related["sales_orders"] == []
        related = _ok(api(BILL_VIEW, SO_VIEW).get(f"{self.LIST}/{iv.id}"))["related"]
        assert related["delivery_orders"] == []
        assert [s["doc_no"] for s in related["sales_orders"]] == [so.so_number]

    def test_another_companys_order_ids_filter_to_nothing(self, world, api):
        so_b = world.so(f"{MARKER}-SO-XB", company_id=world.b)
        do_b = world.do(f"{MARKER}-DO-XB", company_id=world.b, lines=[{"from_doc_no": so_b.so_number}])
        world.doc(f"{MARKER}-IV-XB", company_id=world.b,
                  lines=[{"from_doc_type": "DO", "from_doc_no": do_b.order_number}])
        client = api(BILL_VIEW)
        assert _ok(client.get(self.LIST, params={"sales_order_id": so_b.id}))["data"] == []
        assert _ok(client.get(self.LIST, params={"delivery_order_id": do_b.id}))["data"] == []


def test_mask_respects_module_enablement(world, monkeypatch):
    """Security review nit: under the strict module guard a disabled module masks its kind even
    for a holder of the view slug, as `require_permission` would refuse the record itself."""
    from app.config import settings
    from app.services import document_relations as rel
    from app.services.user_service import UserPermissionService

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    monkeypatch.setattr(settings, "module_guard_strict", True, raising=False)
    monkeypatch.setattr("app.modules.runtime.installer.tenant_has_any_module_row", lambda db, t: True)
    monkeypatch.setattr(
        "app.modules.runtime.installer.is_module_enabled", lambda db, t, module: module != "finance"
    )
    monkeypatch.setattr(
        "app.modules.runtime.permission_module_map.module_for_permission",
        lambda slug: slug.split(".")[0],
    )
    assert rel.can_view(world.db, "u-1", rel.BILLING_DOCUMENT) is False
    assert rel.can_view(world.db, "u-1", rel.DELIVERY_ORDER) is True
