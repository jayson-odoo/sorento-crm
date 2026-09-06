"""AC-F1, F4, F5, F6, F7 - classify, apply (proforma then packing list), price matching.

`blank_session` (a scratch schema, `create_all`) rather than `pg_session`: this suite's own
migration (`483_supplier_doc_aliases`) has not been run with `alembic upgrade head` against
the shared dev database, and seeding it here - the migration's own `seed()` function, same
convention `test_packing_list_kailu.py` section 4/5 use - is what proves the seed itself
works without touching a database another lane's tests are using at the same time.

No `attachment_types` row is seeded for either "Packing List" or "Proforma Invoice", on
purpose: `packing_list_service.file_supplier_document` (ex-`_file_the_upload`) treats a
missing type as a named gap and skips the Drive write entirely rather than raising, so this
suite never makes a live call to storage.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.models.procurement import InboundShipment, InboundShipmentLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.error_handler import AppException
from app.services.scm import supplier_document_service as svc
from tests._pg_fixture import blank_session

MARKER = "ZZSD"
_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _no_ai_translation(monkeypatch):
    """None of THIS file's tests are about the translation AI fill (that is
    `test_translation_service.py`'s job) - forcing no key here keeps every Chinese
    note/remark in the Jiexia fixtures untranslated (R16's own fallback: the source
    text alone) and, more importantly, keeps this suite off the network even though
    `.env` carries a real `OPENAI_API_KEY` for the app itself."""
    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_aliases(db) -> None:
    conn = db.connection()
    _load("311_scm_purchasing_base").seed_import_field_aliases(conn)
    _load("375_kailu_packing_list_aliases").seed(conn)
    _load("375_scm_proforma_invoice").seed(conn)
    _load("428_scm_pi_cbm_adjust_revision").seed(conn)
    _load("483_supplier_doc_aliases").seed(conn)
    db.commit()


def _pi_bytes() -> bytes:
    return (_FIXTURES / "jiexia_proforma_invoice_sample.xls").read_bytes()


def _pl_bytes() -> bytes:
    return (_FIXTURES / "jiexia_packing_list_sample.xls").read_bytes()


class World:
    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:8].upper()
        self.cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=f"{MARKER}-CAT-{tag}", category_name="cat"
        )
        self.uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{MARKER}U"[:20], uom_name="pcs")
        db.add_all([self.cat, self.uom])
        db.flush()
        self.supplier = Supplier(
            id=str(uuid.uuid4()), supplier_code=f"{MARKER}-S-{tag}",
            supplier_name="Jiexia Ceramics", is_active=True,
        )
        db.add(self.supplier)
        db.flush()

    def product(self, code: str) -> Product:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=code,
            category_id=self.cat.id, base_uom_id=self.uom.id, list_price=0,
            is_active=True, is_discontinued=False,
        )
        self.db.add(p)
        self.db.flush()
        return p


#: The two item codes the PI and the PL fixtures share (matched by product, not by the
#: supplier's own text - `SRTWCY8840` and `8840` sit on the PL only, in this real pair).
_SHARED_CODES = ["SRTWCX8840-S-RL", "SRTWCX8840-P-RL"]


def _seed_world(db) -> World:
    w = World(db)
    for code in _SHARED_CODES + ["SRTWCY8840", "8840"]:
        w.product(code)
    return w


def test_classify_reads_the_title_cell():
    assert svc.classify(_pi_bytes()) == "proforma_invoice"
    assert svc.classify(_pl_bytes()) == "packing_list"
    assert svc.classify(b"not a workbook at all") is None


def test_apply_writes_two_invoices_two_shipments_and_links_the_shared_codes():
    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_world(db)

        out = svc.apply(
            db,
            [
                ("发票 SORENTO-2026.7.26.xls", _pi_bytes(), None),
                ("装箱单 SORENTO-2026.7.26.xls", _pl_bytes(), None),
            ],
            supplier_id=str(w.supplier.id),
            currency="RMB",
        )
        db.commit()

        assert len(out["proforma_invoice_ids"]) == 2
        assert len(out["shipment_ids"]) == 2
        assert out["links_written"] >= 2  # at least the two shared codes

        shipments = (
            db.query(InboundShipment)
            .filter(InboundShipment.id.in_(out["shipment_ids"]))
            .order_by(InboundShipment.shipping_container_number)
            .all()
        )
        containers = sorted(s.shipping_container_number for s in shipments)
        assert containers == ["WHSU6243088", "WHSU6356079"]

        for s in shipments:
            # Header prefill (AC-F4): consignee and shipper reach every shipment, even
            # though the file only states them once.
            assert s.consignee == "SORENTO SDN BHD"
            assert s.shipper == "CHAOZHOU CHAOAN JIEXIA CERAMICS INDUSTRY CO.,LTD"
            # Neither fixture states 提单号 - so_ref stays unstated, and the manual field
            # is never derived from it.
            assert s.forwarder_order_ref is None
            assert s.bill_of_lading_number is None

        block1 = next(s for s in shipments if s.shipping_container_number == "WHSU6243088")
        assert block1.seal_number == "WHA4528193"
        assert "水箱空瓷" in (block1.notes or "")
        assert "备注" in (block1.notes or "")

        # Price matching (AC-F5): the two shared codes carry the PI's own price.
        priced_lines = (
            db.query(InboundShipmentLine)
            .filter(
                InboundShipmentLine.shipment_id == block1.id,
                InboundShipmentLine.unit_cost.isnot(None),
            )
            .all()
        )
        assert len(priced_lines) >= 2
        for ln in priced_lines:
            assert ln.currency == "CNY"  # RMB normalises to the ISO code


def test_apply_refuses_the_whole_batch_when_one_file_is_unclassifiable():
    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_world(db)

        with pytest.raises(AppException) as e:
            svc.apply(
                db,
                [
                    ("mystery.xls", b"not a workbook at all", None),
                    ("装箱单 SORENTO-2026.7.26.xls", _pl_bytes(), None),
                ],
                supplier_id=str(w.supplier.id),
            )
        assert e.value.status_code == 422
        assert "mystery.xls" in e.value.detail["message"]


def test_packing_list_uploaded_alone_then_proforma_invoice_links_afterwards():
    """PI after PL (R14): the packing list's shipments already exist; applying the proforma
    invoice afterwards still finds them and links the shared codes."""
    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_world(db)

        first = svc.apply(
            db, [("装箱单 SORENTO-2026.7.26.xls", _pl_bytes(), None)],
            supplier_id=str(w.supplier.id),
            currency="RMB",
        )
        db.commit()
        assert first["links_written"] == 0

        second = svc.apply(
            db, [("发票 SORENTO-2026.7.26.xls", _pi_bytes(), None)],
            supplier_id=str(w.supplier.id),
            currency="RMB",
        )
        db.commit()

        assert second["links_written"] >= 2
