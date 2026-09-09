"""S4 - convert writes one shipment line per matched packing row (`scm-supplier-documents-
pi-first-acceptance-criteria.md`, section D, AC-D2/D3).

TEST-FIRST (Phase 2): depends on S2's packing table (AC-B1) AND S1's numbering, so this file
is red today for TWO independent reasons in sequence - first `ImportError` on `Proforma
InvoicePackingLine` (S2 not built yet), then, once that lands, on the grouping key itself:
`convert_to_draft_shipment` still groups by `(product, supplier)` (migration 374's unique
index), so Kailu's SRTSC14-GM (50 @ 50/ctn + 35 @ 35/ctn) converts to ONE 85-unit shipment
line today, not two.

Same real Kailu fixtures as `test_proforma_invoice_packing_lines.py`.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.models.procurement import InboundShipmentLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import supplier_document_service as svc
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.usefixtures("no_live_llm")

MARKER = "ZZPICP"
_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_LANE_FIXTURES = Path(__file__).resolve().parents[3] / "documentation" / "plans" / "scm" / "fixtures"

_KAILU_CODES = [
    "SRTWT7443", "SRTWT6801", "SRTWT7445-LV-WEPLS", "SRTWT7445-NEW", "SRTWT7438-BL",
    "SRTWT7301-BL", "SRTWT8237-BL", "SRTWT8250-BL", "SRTSC14-GM", "ACC-KT2001",
    "SRTWT7443-GM",
]


@pytest.fixture(autouse=True)
def _no_ai_translation(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _kailu_pi_bytes() -> bytes:
    return (_LANE_FIXTURES / "KAILU形式发票(Sorento)260730.xlsx").read_bytes()


def _kailu_pl_bytes() -> bytes:
    return (_LANE_FIXTURES / "Sorento装箱单（凯路）260730.xls").read_bytes()


def _seed_kailu(db):
    conn = db.connection()
    _load("311_scm_purchasing_base").seed_import_field_aliases(conn)
    _load("375_kailu_packing_list_aliases").seed(conn)
    _load("375_scm_proforma_invoice").seed(conn)
    _load("428_scm_pi_cbm_adjust_revision").seed(conn)
    _load("483_supplier_doc_aliases").seed(conn)
    from sqlalchemy import text as _text
    conn.execute(_text(
        "INSERT INTO import_field_alias (doc_type, field, alias, locale) "
        "VALUES ('packing_list','invoice_date','Date','en') "
        "ON CONFLICT (doc_type, field, alias) DO NOTHING"
    ))
    db.commit()

    tag = uuid.uuid4().hex[:8].upper()
    cat = ProductCategory(id=str(uuid.uuid4()), category_code=f"{MARKER}-CAT-{tag}", category_name="c")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{MARKER}U"[:20], uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    kailu = Supplier(
        id=str(uuid.uuid4()), supplier_code=f"{MARKER}-{tag}", supplier_name="Kailu", is_active=True,
    )
    db.add(kailu)
    db.flush()
    for code in _KAILU_CODES:
        db.add(
            Product(
                id=str(uuid.uuid4()), product_code=code, product_name=code,
                category_id=cat.id, base_uom_id=uom.id, list_price=0,
                is_active=True, is_discontinued=False,
            )
        )
    db.flush()
    return kailu


def test_d2_convert_writes_12_shipment_lines_with_srtsc14_gm_split_whole():
    from app.services.scm import proforma_invoice_service

    with blank_session() as db:
        kailu = _seed_kailu(db)

        out = svc.apply(
            db,
            [
                ("KAILU-260730.xlsx", _kailu_pi_bytes(), None),
                ("Sorento装箱单（凯路）260730.xls", _kailu_pl_bytes(), None),
            ],
            supplier_id=str(kailu.id), currency="RMB",
        )
        db.commit()
        invoice_id = out["proforma_invoice_ids"][0]

        result = proforma_invoice_service.convert_to_draft_shipment(
            db, [invoice_id], created_by=str(uuid.uuid4()),
        )
        db.commit()

        lines = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == result["shipment_id"])
            .all()
        )
        assert len(lines) == 12, f"expected 12 shipment lines, got {len(lines)}"

        srtsc_product_id = (
            db.query(Product.id).filter(Product.product_code == "SRTSC14-GM").scalar()
        )
        srtsc_lines = [l for l in lines if str(l.product_id) == str(srtsc_product_id)]
        assert len(srtsc_lines) == 2, "SRTSC14-GM must land as TWO shipment lines, not one"
        quantities = sorted(int(l.quantity_shipped) for l in srtsc_lines)
        assert quantities == [35, 50]

        for line in srtsc_lines:
            assert int(line.cartons_count) == 1
            assert float(line.unit_cost) == pytest.approx(36.0)
            assert line.currency == "CNY"  # RMB normalises to the ISO code

        pcs_per_ctn = sorted(float(l.pcs_per_carton) for l in srtsc_lines)
        assert pcs_per_ctn == [35.0, 50.0]


# NOTE (AC-D2's "no-rows fallback" clause): a PI applied WITHOUT a packing list already
# converts one shipment line per PI line today (`convert_to_draft_shipment`'s existing
# (product, supplier) grouping) - that path is a no-op under S4 and already GREEN, so it
# is deliberately not asserted here as a red test. The coder must not regress it while
# adding the packing-row grouping above; `test_d2_convert_writes_12_shipment_lines_...`
# above is the one that pins the new behaviour.


def test_d3_dismissed_and_unmatched_rows_never_become_shipment_lines_but_are_noted():
    from app.services.scm import proforma_invoice_service, supplier_code_alias_service

    with blank_session() as db:
        kailu = _seed_kailu(db)

        # ACC-KT2001 dismissed BEFORE apply, so its packing row lands `dismissed` (AC-B6)
        # rather than `matched`.
        supplier_code_alias_service.dismiss(
            db, supplier_id=str(kailu.id), supplier_code="ACC-KT2001", actor="tester"
        )
        db.commit()

        out = svc.apply(
            db,
            [
                ("KAILU-260730.xlsx", _kailu_pi_bytes(), None),
                ("Sorento装箱单（凯路）260730.xls", _kailu_pl_bytes(), None),
            ],
            supplier_id=str(kailu.id), currency="RMB",
        )
        db.commit()
        invoice_id = out["proforma_invoice_ids"][0]

        result = proforma_invoice_service.convert_to_draft_shipment(
            db, [invoice_id], created_by=str(uuid.uuid4()),
        )
        db.commit()

        acc_product_id = (
            db.query(Product.id).filter(Product.product_code == "ACC-KT2001").scalar()
        )
        lines = (
            db.query(InboundShipmentLine)
            .filter(InboundShipmentLine.shipment_id == result["shipment_id"])
            .all()
        )
        assert not any(str(l.product_id) == str(acc_product_id) for l in lines), (
            "a dismissed packing row must never become a shipment line"
        )
        assert len(lines) == 11, "12 rows minus the one dismissed row"

        from app.models.procurement import InboundShipment

        shipment = db.query(InboundShipment).filter(
            InboundShipment.id == result["shipment_id"]
        ).one()
        assert "Supplier packing list also lists:" in (shipment.notes or "")
        assert "ACC-KT2001" in (shipment.notes or "")
