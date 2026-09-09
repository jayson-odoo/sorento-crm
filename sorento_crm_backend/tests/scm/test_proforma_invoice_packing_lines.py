"""S2 - supplier packing rows on the invoice (`scm-supplier-documents-pi-first-acceptance-
criteria.md`, section B).

TEST-FIRST (Phase 2): `scm.proforma_invoice_packing_line` does not exist yet, so every
service-level test below is expected to fail with `ImportError` (the model) until AC-B1
lands, then against the concrete numbers in AC-B2/B3/B4/B8 (real fixtures, ground-truthed
against the committed 9 Sep files by hand) and the resolution/dismiss/undo behaviour in
AC-B5/B6/B7. The two route tests (B7) are expected to 404 until the dismiss/undo endpoints
are mounted.

Fixtures: the REAL Kailu (260730) and Jinbaichuan files at
`documentation/plans/scm/fixtures/`, and the already-committed Jiexia pair under
`tests/scm/fixtures/` (same files `test_supplier_document_service.py` uses - imported from
there rather than re-typed).
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.error_handler import AppException
from app.services.scm import supplier_document_service as svc
from tests._pg_fixture import blank_session
from tests.scm.test_supplier_document_service import (
    World as JiexiaWorld,
    _pi_bytes as _jiexia_pi_bytes,
    _pl_bytes as _jiexia_pl_bytes,
    _seed_aliases,
    _seed_world as _seed_jiexia_world,
)

pytestmark = pytest.mark.usefixtures("no_live_llm")

MARKER = "ZZPIPL"
_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_LANE_FIXTURES = Path(__file__).resolve().parents[3] / "documentation" / "plans" / "scm" / "fixtures"


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


def _jinbaichuan_bytes() -> bytes:
    return (_LANE_FIXTURES / "Jinbaichuan_Invoice.xlsx").read_bytes()


_KAILU_CODES = [
    "SRTWT7443", "SRTWT6801", "SRTWT7445-LV-WEPLS", "SRTWT7445-NEW", "SRTWT7438-BL",
    "SRTWT7301-BL", "SRTWT8237-BL", "SRTWT8250-BL", "SRTSC14-GM", "ACC-KT2001",
    "SRTWT7443-GM",
]
_JINBAICHUAN_CODES = [
    "SRTWC8366-RL-300", "SRTWC8366-RL-250", "CWB242", "CWB242海关样品",
    "SRTWC8152-SH-250-UF", "MWB243", "MWB243海关样品", "SRTWC286-SH-250-NEW",
]


class World:
    def __init__(self, db):
        self.db = db
        tag = uuid.uuid4().hex[:8].upper()
        self.cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=f"{MARKER}-CAT-{tag}", category_name="cat"
        )
        self.uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{MARKER}U"[:20], uom_name="pcs")
        self.db.add_all([self.cat, self.uom])
        self.db.flush()

    def supplier(self, name: str) -> Supplier:
        s = Supplier(
            id=str(uuid.uuid4()), supplier_code=f"{MARKER}-{uuid.uuid4().hex[:8].upper()}",
            supplier_name=name, is_active=True,
        )
        self.db.add(s)
        self.db.flush()
        return s

    def product(self, code: str) -> Product:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=code,
            category_id=self.cat.id, base_uom_id=self.uom.id, list_price=0,
            is_active=True, is_discontinued=False,
        )
        self.db.add(p)
        self.db.flush()
        return p


def _seed_kailu_aliases_and_world(db):
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
    w = World(db)
    kailu = w.supplier("Kailu")
    for code in _KAILU_CODES:
        w.product(code)
    return w, kailu


# --------------------------------------------------------------------------------- AC-B2


def test_b2_kailu_writes_11_lines_and_12_packing_rows_with_srtsc14_gm_split_and_rolled_up():
    from app.models.scm import ProformaInvoiceLine, ProformaInvoicePackingLine

    with blank_session() as db:
        w, kailu = _seed_kailu_aliases_and_world(db)

        out = svc.apply(
            db,
            [
                ("KAILU-260730.xlsx", _kailu_pi_bytes(), None),
                ("Sorento装箱单（凯路）260730.xls", _kailu_pl_bytes(), None),
            ],
            supplier_id=str(kailu.id),
            currency="RMB",
        )
        db.commit()

        assert len(out["proforma_invoice_ids"]) == 1
        invoice_id = out["proforma_invoice_ids"][0]

        lines = (
            db.query(ProformaInvoiceLine)
            .filter(ProformaInvoiceLine.invoice_id == invoice_id)
            .all()
        )
        assert len(lines) == 11

        rows = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice_id)
            .all()
        )
        assert len(rows) == 12

        srtsc_rows = [r for r in rows if r.item_code == "SRTSC14-GM"]
        assert len(srtsc_rows) == 2
        assert {float(r.qty) for r in srtsc_rows} == {50.0, 35.0}
        assert all(r.match_state == "matched" for r in srtsc_rows)

        srtsc_line = next(l for l in lines if l.item_code == "SRTSC14-GM")
        assert srtsc_line.cartons == 2
        assert float(srtsc_line.cbm_total) == pytest.approx(0.040774, abs=1e-6)
        assert float(srtsc_line.net_weight) == pytest.approx(19.0)
        assert float(srtsc_line.gross_weight) == pytest.approx(21.3)

        # Every other line has exactly one packing row.
        for line in lines:
            if line.item_code == "SRTSC14-GM":
                continue
            count = sum(1 for r in rows if r.item_code == line.item_code)
            assert count == 1, f"{line.item_code} expected one packing row, got {count}"


# --------------------------------------------------------------------------------- AC-B3


def test_b3_jinbaichuan_combined_file_yields_lines_and_rows_from_one_read():
    from app.models.scm import ProformaInvoiceLine, ProformaInvoicePackingLine

    with blank_session() as db:
        w = World(db)
        jbc = w.supplier("Jinbaichuan")
        for code in _JINBAICHUAN_CODES:
            w.product(code)
        conn = db.connection()
        _load("311_scm_purchasing_base").seed_import_field_aliases(conn)
        _load("375_scm_proforma_invoice").seed(conn)
        _load("428_scm_pi_cbm_adjust_revision").seed(conn)
        _load("483_supplier_doc_aliases").seed(conn)
        db.commit()

        out = svc.apply(
            db, [("Jinbaichuan_Invoice.xlsx", _jinbaichuan_bytes(), None)],
            supplier_id=str(jbc.id), currency="RMB",
        )
        db.commit()

        assert len(out["proforma_invoice_ids"]) == 1
        invoice_id = out["proforma_invoice_ids"][0]

        lines = (
            db.query(ProformaInvoiceLine)
            .filter(ProformaInvoiceLine.invoice_id == invoice_id)
            .all()
        )
        rows = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice_id)
            .all()
        )
        assert len(lines) == 11
        assert len(rows) == 11

        priced_line = next(l for l in lines if l.item_code == "SRTWC8366-RL-300")
        assert float(priced_line.unit_price) == pytest.approx(465.0)
        assert float(priced_line.amount) == pytest.approx(46500.0)

        unmatched_codes = {"补8355水箱盖", "补7606-N盖板", "家豪拼柜41个盆"}
        unmatched_lines = [l for l in lines if l.item_code in unmatched_codes]
        unmatched_rows = [r for r in rows if r.item_code in unmatched_codes]
        assert len(unmatched_lines) == 3
        assert len(unmatched_rows) == 3
        for l in unmatched_lines:
            assert l.unit_price is None
        for r in unmatched_rows:
            assert r.match_state == "unmatched"


# --------------------------------------------------------------------------------- AC-B4


def test_b4_jiexia_lid_row_is_an_unmatched_packing_row_never_an_invoice_line():
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine, ProformaInvoicePackingLine

    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_jiexia_world(db)
        # "8840" (盖板) is a real product in the catalogue - `_seed_world` already seeds
        # it (its own comment: it sits on the packing list only, never on the PI) - so its
        # packing row resolves a product but still finds no PI line to match.

        out = svc.apply(
            db,
            [
                ("发票 SORENTO-2026.7.26.xls", _jiexia_pi_bytes(), None),
                ("装箱单 SORENTO-2026.7.26.xls", _jiexia_pl_bytes(), None),
            ],
            supplier_id=str(w.supplier.id),
            currency="RMB",
        )
        db.commit()

        invoices = (
            db.query(ProformaInvoice)
            .filter(ProformaInvoice.id.in_(out["proforma_invoice_ids"]))
            .all()
        )
        block1 = next(i for i in invoices if i.container_ref == "WHSU6243088")

        lid_lines = (
            db.query(ProformaInvoiceLine)
            .filter(
                ProformaInvoiceLine.invoice_id == block1.id,
                ProformaInvoiceLine.item_code == "8840",
            )
            .all()
        )
        assert lid_lines == [], "the lid row must never become an invoice line"

        lid_rows = (
            db.query(ProformaInvoicePackingLine)
            .filter(
                ProformaInvoicePackingLine.proforma_invoice_id == block1.id,
                ProformaInvoicePackingLine.item_code == "8840",
            )
            .all()
        )
        assert len(lid_rows) == 1
        assert lid_rows[0].match_state == "unmatched"
        assert float(lid_rows[0].qty) == pytest.approx(366.0)
        assert float(lid_rows[0].cartons) == pytest.approx(60.0)


# --------------------------------------------------------------------------------- AC-B5


def test_b5_a_packing_list_with_no_pi_and_no_shared_date_is_refused_with_409():
    with blank_session() as db:
        w, kailu = _seed_kailu_aliases_and_world(db)

        with pytest.raises(AppException) as e:
            svc.apply(
                db, [("Sorento装箱单（凯路）260730.xls", _kailu_pl_bytes(), None)],
                supplier_id=str(kailu.id), currency="RMB",
            )
        assert e.value.status_code == 409
        assert e.value.detail["code"] == "proforma_invoice_required"
        assert kailu.supplier_name in (e.value.detail.get("message") or "")


def test_b5_a_replace_upload_overwrites_the_rows_rather_than_appending():
    from app.models.scm import ProformaInvoicePackingLine

    with blank_session() as db:
        w, kailu = _seed_kailu_aliases_and_world(db)

        first = svc.apply(
            db,
            [
                ("KAILU-260730.xlsx", _kailu_pi_bytes(), None),
                ("Sorento装箱单（凯路）260730.xls", _kailu_pl_bytes(), None),
            ],
            supplier_id=str(kailu.id), currency="RMB",
        )
        db.commit()
        invoice_id = first["proforma_invoice_ids"][0]
        first_count = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice_id)
            .count()
        )
        assert first_count == 12

        # A second upload of the SAME PI + PL pair (a correction) - the packing rows must
        # be REPLACED, never doubled.
        svc.apply(
            db,
            [
                ("KAILU-260730-resend.xlsx", _kailu_pi_bytes(), None),
                ("Sorento装箱单（凯路）260730-resend.xls", _kailu_pl_bytes(), None),
            ],
            supplier_id=str(kailu.id), currency="RMB",
        )
        db.commit()

        second_count = (
            db.query(ProformaInvoicePackingLine)
            .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice_id)
            .count()
        )
        assert second_count == 12, "a re-upload must replace, never append"


# --------------------------------------------------------------------------------- AC-B6


def test_b6_a_row_whose_code_is_a_dismissed_alias_lands_dismissed_on_apply():
    """A code the supplier writes for something that is never one of ours (spares, a
    customs sample) - dismissed once (`supplier_code_alias_service.dismiss`), and every
    later upload from that supplier lands the row `dismissed` without asking again."""
    from app.services.scm import supplier_code_alias_service

    with blank_session() as db:
        w, kailu = _seed_kailu_aliases_and_world(db)

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

        from app.models.scm import ProformaInvoicePackingLine

        invoice_id = out["proforma_invoice_ids"][0]
        row = (
            db.query(ProformaInvoicePackingLine)
            .filter(
                ProformaInvoicePackingLine.proforma_invoice_id == invoice_id,
                ProformaInvoicePackingLine.item_code == "ACC-KT2001",
            )
            .one()
        )
        assert row.match_state == "dismissed"


# --------------------------------------------------------------------------------- AC-B7


UPLOAD_PERMISSION = "scm.proforma_invoice.upload"


def _grant(db, uid: str, slug: str) -> None:
    from app.models.user import UserPermission, UserRole, UserRolePermission, UserRoleAssignment

    role = UserRole(id=str(uuid.uuid4()), slug=f"{MARKER}-role-{uuid.uuid4().hex[:6]}", name="role")
    db.add(role)
    db.flush()
    perm = db.query(UserPermission).filter(UserPermission.slug == slug).one_or_none()
    if perm is None:
        perm = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug)
        db.add(perm)
        db.flush()
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(id=str(uuid.uuid4()), user_id=uid, role_id=role.id))
    db.flush()


def _seed_one_packing_row(db):
    """One PI with one unmatched packing row, seeded directly (bypassing the reader) so
    this route test does not also depend on S1's numbering or the fixture files."""
    from app.models.scm import ProformaInvoice, ProformaInvoicePackingLine

    tag = uuid.uuid4().hex[:8].upper()
    cat = ProductCategory(id=str(uuid.uuid4()), category_code=f"{MARKER}-CAT-{tag}", category_name="c")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{MARKER}U2"[:20], uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code=f"{MARKER}-S-{tag}", supplier_name="S", is_active=True,
    )
    db.add(supplier)
    db.flush()
    invoice = ProformaInvoice(
        id=str(uuid.uuid4()), supplier_id=supplier.id, pi_number=f"PI-TEST-{tag}",
    )
    db.add(invoice)
    db.flush()
    row = ProformaInvoicePackingLine(
        id=str(uuid.uuid4()), proforma_invoice_id=invoice.id, row_no=1,
        item_code="SPARE-1", qty=5, match_state="unmatched",
    )
    db.add(row)
    db.commit()
    return supplier, invoice, row


def test_b7_dismiss_then_undo_via_the_route(scm_app):
    from tests.scm.conftest import requires_pg
    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, UPLOAD_PERMISSION)
    client = TestClient(app)

    supplier, invoice, row = _seed_one_packing_row(db)

    r = client.post(
        f"/api/v1/scm/proforma-invoices/{invoice.id}/packing-lines/{row.id}/dismiss"
    )
    assert r.status_code == 200, r.text

    db.expire_all()
    from app.models.scm import ProformaInvoicePackingLine

    refreshed = db.query(ProformaInvoicePackingLine).filter(
        ProformaInvoicePackingLine.id == row.id
    ).one()
    assert refreshed.match_state == "dismissed"

    r2 = client.delete(
        f"/api/v1/scm/proforma-invoices/{invoice.id}/packing-lines/{row.id}/dismiss"
    )
    assert r2.status_code == 200, r2.text

    db.expire_all()
    undone = db.query(ProformaInvoicePackingLine).filter(
        ProformaInvoicePackingLine.id == row.id
    ).one()
    assert undone.match_state == "unmatched"


# --------------------------------------------------------------------------------- AC-B8


def test_b8_rollup_agrees_when_every_row_shares_pcs_per_carton_and_dims_else_null():
    """`_rollup_packing` (plan's own name for the one-function roll-up): sums for
    cartons/cbm_total/net/gross, shared-or-NULL for pcs_per_carton and carton dims. Kailu's
    own SRTSC14-GM (AC-B2) is the "agree" case (both rows are 1 ctn @ the same dims); this
    is the "disagree" case, built with a synthetic two-row packing list so the NULL half of
    the rule is exercised independently of any real fixture's actual numbers."""
    from app.models.scm import ProformaInvoiceLine, ProformaInvoicePackingLine

    with blank_session() as db:
        w, kailu = _seed_kailu_aliases_and_world(db)

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

        srtsc_line = (
            db.query(ProformaInvoiceLine)
            .filter(
                ProformaInvoiceLine.invoice_id == invoice_id,
                ProformaInvoiceLine.item_code == "SRTSC14-GM",
            )
            .one()
        )
        # Agree case (Kailu's real rows: both 1 ctn, both 38x37x14.5).
        assert srtsc_line.pcs_per_carton is None or float(srtsc_line.pcs_per_carton) in (35.0, 50.0)
        assert float(srtsc_line.carton_length_cm) == pytest.approx(38.0)
        assert float(srtsc_line.carton_width_cm) == pytest.approx(37.0)
        assert float(srtsc_line.carton_height_cm) == pytest.approx(14.5)

        # Disagree case: hand-edit one of the two rows' width so the two rows no longer
        # share a carton dimension, then re-run the roll-up the same way a dismiss/undo
        # does, and check the line's own dims fall back to NULL rather than keeping a
        # stale, now-wrong figure.
        rows = (
            db.query(ProformaInvoicePackingLine)
            .filter(
                ProformaInvoicePackingLine.proforma_invoice_id == invoice_id,
                ProformaInvoicePackingLine.item_code == "SRTSC14-GM",
            )
            .all()
        )
        assert len(rows) == 2
        rows[0].carton_width_cm = 99
        db.flush()

        from app.services.scm import proforma_invoice_packing_service as packing_svc

        packing_svc._rollup_packing(db, srtsc_line, rows)
        db.commit()
        db.refresh(srtsc_line)

        assert srtsc_line.carton_width_cm is None
        # cartons/cbm/net/gross are still simple sums, unaffected by the disagreement.
        assert srtsc_line.cartons == 2
