"""S1 - our own PI number (`documentation/plans/scm/scm-supplier-documents-pi-first-
acceptance-criteria.md`, section A).

TEST-FIRST (Phase 2): `scm.proforma_invoice.pi_number` is still the SUPPLIER's own number
verbatim (or the derived `PI-<file stem>-<block>` fallback) at the time this file is
written - `scm.proforma_invoice.supplier_ref` does not exist on the model yet. Every test
below is expected to be RED until S1 lands:

  * A1/A2/A3 fail with ``AttributeError`` (no ``ProformaInvoice.supplier_ref``) or with a
    wrong ``pi_number`` (still the supplier's own text, not ``PI-{yy}{month:02d}-{seq}``).
  * A4 fails with ``ImportError``/``AttributeError`` - the backfill function the migration
    is supposed to carry does not exist yet.

Postgres via ``blank_session`` (a scratch schema off ``Base.metadata``), same pattern as
``test_supplier_document_service.py``: this lane's own migration has not been run against
the shared dev database, so the alias seed functions are loaded and executed directly
against the scratch schema's connection.

Fixtures: the REAL 9 Sep files at ``documentation/plans/scm/fixtures/`` - Kailu's PI states
``货单号 KL20260730`` (AC-A2), Jinbaichuan's states no invoice number at all.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest

from app.config import settings
from app.models.numbering import DocumentNumberingRule
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.numbering_service import NumberingService
from app.services.scm import supplier_document_service as svc
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.usefixtures("no_live_llm")

MARKER = "ZZPIN"
_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
# Worktree root: tests/scm/test_x.py -> tests/scm -> tests -> sorento_crm_backend -> worktree root.
_LANE_FIXTURES = Path(__file__).resolve().parents[3] / "documentation" / "plans" / "scm" / "fixtures"

_DOC_TYPE = "proforma_invoice"


@pytest.fixture(autouse=True)
def _no_ai_translation(monkeypatch):
    """Off the network - same reasoning as `test_supplier_document_service.py`."""
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


def _kailu_bytes() -> bytes:
    return (_LANE_FIXTURES / "KAILU形式发票(Sorento)260730.xlsx").read_bytes()


def _jinbaichuan_bytes() -> bytes:
    return (_LANE_FIXTURES / "Jinbaichuan_Invoice.xlsx").read_bytes()


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


# The Kailu PI's own item codes (real 260730 fixture) - seeded so the line-match does not
# swamp `apply`'s currency/product resolution with an unrelated failure.
_KAILU_CODES = [
    "SRTWT7443", "SRTWT6801", "SRTWT7445-LV-WEPLS", "SRTWT7445-NEW", "SRTWT7438-BL",
    "SRTWT7301-BL", "SRTWT8237-BL", "SRTWT8250-BL", "SRTSC14-GM", "ACC-KT2001",
    "SRTWT7443-GM",
]
_JINBAICHUAN_CODES = [
    "SRTWC8366-RL-300", "SRTWC8366-RL-250", "CWB242", "CWB242海关样品",
    "SRTWC8152-SH-250-UF", "MWB243", "MWB243海关样品", "SRTWC286-SH-250-NEW",
]


def _expected_prefix(today: date | None = None) -> str:
    today = today or date.today()
    return f"PI-{today.year % 100:02d}{today.month:02d}-"


def _rule(db, company_id):
    return (
        db.query(DocumentNumberingRule)
        .filter(
            DocumentNumberingRule.doc_type == _DOC_TYPE,
            DocumentNumberingRule.company_id == company_id,
        )
        .one_or_none()
    )


def _company_scope(db):
    """The company `blank_session`'s scratch schema seeds automatically (`after_create` on
    `companies`) - read it back rather than inventing one, so every insert's auto-stamped
    `company_id` lands on the same row `NumberingService` is asked about."""
    from app.models.company import Company

    return db.query(Company.id).order_by(Company.name).first()[0]


# --------------------------------------------------------------------------------- AC-A1


def test_a1_two_pis_in_one_month_are_sequential_and_the_rule_is_created_on_the_spot():
    with blank_session() as db:
        _seed_aliases(db)
        w = World(db)
        supplier_a = w.supplier("Kailu")
        supplier_b = w.supplier("Jinbaichuan")
        for code in _KAILU_CODES:
            w.product(code)
        for code in _JINBAICHUAN_CODES:
            w.product(code)
        company_id = _company_scope(db)

        assert _rule(db, company_id) is None, "no proforma_invoice rule exists yet"

        first = svc.apply(
            db, [("KAILU-260730.xlsx", _kailu_bytes(), None)],
            supplier_id=str(supplier_a.id), currency="RMB",
        )
        db.commit()
        second = svc.apply(
            db, [("Jinbaichuan_Invoice.xlsx", _jinbaichuan_bytes(), None)],
            supplier_id=str(supplier_b.id), currency="RMB",
        )
        db.commit()

        from app.models.scm import ProformaInvoice

        inv_a = db.query(ProformaInvoice).filter(
            ProformaInvoice.id.in_(first["proforma_invoice_ids"])
        ).one()
        inv_b = db.query(ProformaInvoice).filter(
            ProformaInvoice.id.in_(second["proforma_invoice_ids"])
        ).one()

        prefix = _expected_prefix()
        assert inv_a.pi_number == f"{prefix}001", inv_a.pi_number
        assert inv_b.pi_number == f"{prefix}002", inv_b.pi_number

        rule = _rule(db, company_id)
        assert rule is not None, "applying a PI with no rule yet must create one"
        assert rule.prefix_template == "PI-{yy}{month:02d}-"
        assert rule.number_digits == 3
        assert rule.reset_policy == "monthly"


def test_a1_a_new_month_restarts_the_series_at_dash_001():
    """Same rule engine as `PL-{yy}{month:02d}-` (AC-A1): a fresh `reference_date` in the
    NEXT month resets `next_value` back to 1, the same behaviour `NumberingService` already
    gives every other monthly series. Exercised directly against the rule S1's own apply
    creates, rather than mocking `date.today()` inside `apply` itself."""
    with blank_session() as db:
        _seed_aliases(db)
        w = World(db)
        supplier = w.supplier("Kailu")
        for code in _KAILU_CODES:
            w.product(code)
        company_id = _company_scope(db)

        svc.apply(
            db, [("KAILU-260730.xlsx", _kailu_bytes(), None)],
            supplier_id=str(supplier.id), currency="RMB",
        )
        db.commit()
        assert _rule(db, company_id) is not None, "the rule must exist after one apply"

        today = date.today()
        next_month = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)

        number = NumberingService(db).get_next_number(
            _DOC_TYPE, reference_date=next_month, company_id=company_id
        )
        db.commit()

        assert number == f"{_expected_prefix(next_month)}001", number


# --------------------------------------------------------------------------------- AC-A2


def test_a2_kailu_states_its_own_reference_jinbaichuan_states_none():
    with blank_session() as db:
        _seed_aliases(db)
        w = World(db)
        kailu = w.supplier("Kailu")
        jinbaichuan = w.supplier("Jinbaichuan")
        for code in _KAILU_CODES:
            w.product(code)
        for code in _JINBAICHUAN_CODES:
            w.product(code)

        kailu_out = svc.apply(
            db, [("KAILU-260730.xlsx", _kailu_bytes(), None)],
            supplier_id=str(kailu.id), currency="RMB",
        )
        db.commit()
        jbc_out = svc.apply(
            db, [("Jinbaichuan_Invoice.xlsx", _jinbaichuan_bytes(), None)],
            supplier_id=str(jinbaichuan.id), currency="RMB",
        )
        db.commit()

        from app.models.scm import ProformaInvoice

        kailu_inv = db.query(ProformaInvoice).filter(
            ProformaInvoice.id.in_(kailu_out["proforma_invoice_ids"])
        ).one()
        jbc_inv = db.query(ProformaInvoice).filter(
            ProformaInvoice.id.in_(jbc_out["proforma_invoice_ids"])
        ).one()

        assert kailu_inv.supplier_ref == "KL20260730"
        assert jbc_inv.supplier_ref is None
        # `pi_number` is minted regardless of whether the file states a reference.
        assert jbc_inv.pi_number is not None
        assert jbc_inv.pi_number.startswith("PI-")


# --------------------------------------------------------------------------------- AC-A3


def test_a3_reupload_of_the_same_reference_updates_in_place_and_draws_no_second_number():
    with blank_session() as db:
        _seed_aliases(db)
        w = World(db)
        kailu = w.supplier("Kailu")
        for code in _KAILU_CODES:
            w.product(code)

        first = svc.apply(
            db, [("KAILU-260730.xlsx", _kailu_bytes(), None)],
            supplier_id=str(kailu.id), currency="RMB",
        )
        db.commit()

        second = svc.apply(
            db, [("KAILU-260730-resend.xlsx", _kailu_bytes(), None)],
            supplier_id=str(kailu.id), currency="RMB",
        )
        db.commit()

        from app.models.scm import ProformaInvoice

        assert set(first["proforma_invoice_ids"]) == set(second["proforma_invoice_ids"])
        rows = db.query(ProformaInvoice).filter(
            ProformaInvoice.supplier_id == kailu.id
        ).all()
        assert len(rows) == 1, "a re-upload by the same supplier_ref must not mint a second row"
        assert rows[0].pi_number == f"{_expected_prefix()}001"


def test_a3_a_file_stating_no_reference_is_always_created_fresh():
    """AC-A3's `supplier_ref_missing` refusal is retired (captain ruling 9 Sep): a
    document stating no reference has nothing to match against, so it is always
    created fresh rather than refused or matched onto an earlier row."""
    with blank_session() as db:
        _seed_aliases(db)
        w = World(db)
        jinbaichuan = w.supplier("Jinbaichuan")
        for code in _JINBAICHUAN_CODES:
            w.product(code)

        first = svc.apply(
            db, [("Jinbaichuan_Invoice.xlsx", _jinbaichuan_bytes(), None)],
            supplier_id=str(jinbaichuan.id), currency="RMB",
        )
        db.commit()

        second = svc.apply(
            db, [("Jinbaichuan_Invoice.xlsx", _jinbaichuan_bytes(), None)],
            supplier_id=str(jinbaichuan.id), currency="RMB",
        )
        db.commit()

        from app.models.scm import ProformaInvoice

        assert set(first["proforma_invoice_ids"]).isdisjoint(second["proforma_invoice_ids"]), (
            "a second ref-less apply must create a second PI, never match the first"
        )
        rows = db.query(ProformaInvoice).filter(
            ProformaInvoice.supplier_id == jinbaichuan.id
        ).all()
        assert len(rows) == 2

        prefix = _expected_prefix()
        first_row = db.query(ProformaInvoice).filter(
            ProformaInvoice.id.in_(first["proforma_invoice_ids"])
        ).one()
        second_row = db.query(ProformaInvoice).filter(
            ProformaInvoice.id.in_(second["proforma_invoice_ids"])
        ).one()
        assert first_row.pi_number == f"{prefix}001", "the first row is untouched by the second apply"
        assert second_row.pi_number == f"{prefix}002"


# --------------------------------------------------------------------------------- AC-A4


def test_a4_backfill_derives_supplier_ref_and_mints_pi_numbers_in_created_at_order():
    """Migration function under test: `app.services.scm.proforma_invoice_numbering_backfill
    .backfill_pi_numbers(connection)` (best-guess name, per the plan's own description -
    "every existing scm.proforma_invoice row gets supplier_ref = old pi_number ... then a
    new pi_number minted per company in created_at order"). Whatever module the coder lands
    it in, this import is expected to fail (ImportError) until S1's migration ships; the
    coder should either match this name or tell the tester the real one so this file can be
    corrected in the same slice.

    Three rows seeded directly (bypassing `apply`, so the OLD shape - `pi_number` holding
    the derived `PI-<stem>-<n>` name or the supplier's own text - is exactly what the
    migration meets on a real database): two in August, one in September, across company
    default and a second company.
    """
    with blank_session() as db:
        from app.models.company import Company
        from app.models.scm import ProformaInvoice

        w = World(db)
        supplier = w.supplier("Kailu")
        company_id = _company_scope(db)
        other_company_id = str(uuid.uuid4())
        db.add(Company(id=other_company_id, name=f"{MARKER}-other", code=f"{MARKER}OTH"))
        db.flush()

        from app.models.base import set_company_scope

        set_company_scope(db, frozenset({company_id, other_company_id}))

        row_aug1 = ProformaInvoice(
            id=str(uuid.uuid4()), supplier_id=supplier.id,
            pi_number="PI-somefile-1", company_id=company_id,
            created_at=datetime(2026, 8, 3, 9, 0, 0),
        )
        row_aug2 = ProformaInvoice(
            id=str(uuid.uuid4()), supplier_id=supplier.id,
            pi_number="KL20260805", company_id=company_id,
            created_at=datetime(2026, 8, 20, 9, 0, 0),
        )
        row_sep1 = ProformaInvoice(
            id=str(uuid.uuid4()), supplier_id=supplier.id,
            pi_number="PI-anotherfile-2", company_id=other_company_id,
            created_at=datetime(2026, 9, 2, 9, 0, 0),
        )
        db.add_all([row_aug1, row_aug2, row_sep1])
        db.commit()

        from app.services.scm.proforma_invoice_numbering_backfill import backfill_pi_numbers

        backfill_pi_numbers(db.connection())
        db.commit()
        db.expire_all()

        set_company_scope(db, None)
        aug1 = db.query(ProformaInvoice).filter(ProformaInvoice.id == row_aug1.id).one()
        aug2 = db.query(ProformaInvoice).filter(ProformaInvoice.id == row_aug2.id).one()
        sep1 = db.query(ProformaInvoice).filter(ProformaInvoice.id == row_sep1.id).one()

        # The derived name lost its supplier_ref; a stated-looking one kept it.
        assert aug1.supplier_ref is None
        assert aug2.supplier_ref == "KL20260805"
        assert sep1.supplier_ref is None

        assert aug1.pi_number == "PI-2608-001"
        assert aug2.pi_number == "PI-2608-002"
        # Different company -> its own series, starting at 001 regardless of the first
        # company's count.
        assert sep1.pi_number == "PI-2609-001"

        rule1 = _rule(db, company_id)
        rule2 = _rule(db, other_company_id)
        assert rule1 is not None and rule1.next_value == 3
        assert rule1.last_reset_key == "2026-08"
        assert rule2 is not None and rule2.next_value == 2
        assert rule2.last_reset_key == "2026-09"
