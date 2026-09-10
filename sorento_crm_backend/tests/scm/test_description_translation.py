"""Text glossary S1 (#811) - UAC A-D (`documentation/plans/scm/text-glossary-acceptance-
criteria.md`). Written TEST-FIRST, before `app.services.scm.description_translation`
exists (`PLAN-text-glossary.md`, "Design" section).

Nothing is seeded (R6): every test writes its own `translation_memory` rows through
`translation_service.remember` or a direct `TranslationMemory` insert, `source_lang='zh'`,
`target_lang='en'`. `translation_service._ai_fill` is patched wherever a test must not
reach the model (the pattern `tests/scm/test_supplier_document_translations.py` already
uses).

Postgres only, via `tests._pg_fixture.blank_session` - a fresh scratch schema per test, so
CI's empty database never blocks the chain each test seeds for itself.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services import translation_service as tsvc

# The whole point of writing this file first: `description_translation` does not exist
# yet, so EVERY test below is red with `ModuleNotFoundError` until the coder creates it -
# not an import typo, not a fixture bug.
from app.services.scm import description_translation as dtsvc  # noqa: E402

from tests._pg_fixture import blank_session

pytestmark = pytest.mark.usefixtures("no_live_llm")

MARKER = "ZZDTXT"
_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tag() -> str:
    return uuid.uuid4().hex[:8].upper()


def _seed_aliases(db) -> None:
    """The same alias set `test_proforma_invoice_packing_lines.py` seeds for a Jinbaichuan
    world - only the migrations this suite's OWN world (products, supplier, category, uom)
    needs alongside the real reader."""
    conn = db.connection()
    _load("311_scm_purchasing_base").seed_import_field_aliases(conn)
    _load("375_scm_proforma_invoice").seed(conn)
    _load("428_scm_pi_cbm_adjust_revision").seed(conn)
    _load("483_supplier_doc_aliases").seed(conn)
    db.commit()


class World:
    """A category, a uom, and helpers for a supplier / product this suite owns."""

    def __init__(self, db):
        self.db = db
        tag = _tag()
        self.cat = ProductCategory(
            id=str(uuid.uuid4()), category_code=f"{MARKER}-CAT-{tag}", category_name="cat"
        )
        self.uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{MARKER}U"[:20], uom_name="pcs")
        db.add_all([self.cat, self.uom])
        db.flush()

    def supplier(self, name: str = "Supplier") -> Supplier:
        s = Supplier(
            id=str(uuid.uuid4()), supplier_code=f"{MARKER}-{_tag()}",
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


def _remember(db, source_text: str, target_text: str, *, target_lang: str = "en") -> None:
    """A memory row this suite owns, written directly (not through `remember()`) so an A5-
    style test proving `remember()` itself re-binds does not have to trust the thing it is
    proving. `source_lang` is always `zh` here - `A7` writes its own `ms` row by hand."""
    from app.models.translation_memory import SOURCE_MANUAL, TranslationMemory

    db.add(
        TranslationMemory(
            id=str(uuid.uuid4()), source_text=source_text, source_lang="zh",
            target_lang=target_lang, target_text=target_text, source=SOURCE_MANUAL,
        )
    )
    db.flush()


def _seed_pi(db, supplier_id: str, **over) -> "ProformaInvoice":  # noqa: F821
    from app.models.scm import ProformaInvoice

    tag = _tag()
    row = ProformaInvoice(
        id=str(uuid.uuid4()), supplier_id=supplier_id,
        pi_number=over.pop("pi_number", f"{MARKER}-PI-{tag}"), **over,
    )
    db.add(row)
    db.flush()
    return row


def _seed_pi_line(db, invoice, *, item_code: str, description: str, **over) -> "ProformaInvoiceLine":  # noqa: F821
    from app.models.scm import ProformaInvoiceLine

    row = ProformaInvoiceLine(
        id=str(uuid.uuid4()), invoice_id=invoice.id, line_no=over.pop("line_no", 1),
        item_code=item_code, description=description, qty=over.pop("qty", 1),
        **over,
    )
    db.add(row)
    db.flush()
    return row


def _seed_packing_row(db, invoice, *, item_code: str, description: str, row_no: int = 1, **over) -> "ProformaInvoicePackingLine":  # noqa: F821
    from app.models.scm import ProformaInvoicePackingLine

    row = ProformaInvoicePackingLine(
        id=str(uuid.uuid4()), proforma_invoice_id=invoice.id, row_no=row_no,
        item_code=item_code, description=description, qty=over.pop("qty", 1),
        match_state=over.pop("match_state", "unmatched"), **over,
    )
    db.add(row)
    db.flush()
    return row


# ============================================================================= A. Fill and re-bind


def test_a1_fill_reads_memory_and_never_asks_the_model_for_plain_english(db, monkeypatch):
    """A1 - three fresh ProformaInvoicePackingLine objects (盆, 连体马桶, BASIN) with memory
    rows for the first two; BASIN never reaches `_ai_fill` (R7). One `translate` call for
    the whole batch (spy on `translation_service.translate`)."""
    w = World(db)
    supplier = w.supplier()
    invoice = _seed_pi(db, str(supplier.id))
    _remember(db, "盆", "Basin")
    _remember(db, "连体马桶", "One-piece toilet")

    row1 = _seed_packing_row(db, invoice, item_code="C1", description="盆", row_no=1)
    row2 = _seed_packing_row(db, invoice, item_code="C2", description="连体马桶", row_no=2)
    row3 = _seed_packing_row(db, invoice, item_code="C3", description="BASIN", row_no=3)

    calls = []
    real_translate = tsvc.translate

    def _spy(db_, texts, **kw):
        calls.append(list(texts))
        return real_translate(db_, texts, **kw)

    monkeypatch.setattr(tsvc, "translate", _spy)
    ai_calls = []
    monkeypatch.setattr(
        tsvc, "_ai_fill",
        lambda db_, misses, **kw: ai_calls.append(list(misses)) or {},
    )

    dtsvc.fill(db, [row1, row2, row3])

    assert row1.description_en == "Basin"
    assert row2.description_en == "One-piece toilet"
    assert row3.description_en is None
    assert len(calls) == 1, "fill must make ONE translate() call for the whole batch"
    assert all("BASIN" not in c for c in ai_calls), "an English description must never reach the model (R7)"


def test_a2_fill_writes_an_ai_row_for_a_miss_the_ai_answers(db, monkeypatch):
    """A2 - `_ai_fill` answers a miss; `fill` sets `description_en` from the AI answer AND
    the memory now holds an `ai` row for it."""
    from app.models.translation_memory import SOURCE_AI, TranslationMemory

    w = World(db)
    supplier = w.supplier()
    invoice = _seed_pi(db, str(supplier.id))
    row = _seed_packing_row(db, invoice, item_code="C1", description="连体马桶", row_no=1)

    monkeypatch.setattr(
        tsvc, "_ai_fill",
        lambda db_, misses, **kw: {"连体马桶": "One-piece toilet"},
    )

    dtsvc.fill(db, [row])

    assert row.description_en == "One-piece toilet"
    memory_row = (
        db.query(TranslationMemory)
        .filter(TranslationMemory.source_text == "连体马桶", TranslationMemory.target_lang == "en")
        .one()
    )
    assert memory_row.source == SOURCE_AI


def test_a3_rebind_updates_every_matching_row_across_two_pis(db):
    """A3 - two PIs each with a `盆` line and one `盆` (padded) packing row, plus one
    `连体马桶` line. `rebind` touches every `盆` row/line, leaves `连体马桶` untouched, and
    returns the counts."""
    w = World(db)
    supplier = w.supplier()
    pi1 = _seed_pi(db, str(supplier.id))
    pi2 = _seed_pi(db, str(supplier.id))

    line1 = _seed_pi_line(db, pi1, item_code="C1", description="盆")
    row1 = _seed_packing_row(db, pi1, item_code="C1", description=" 盆 ", row_no=1)
    line2 = _seed_pi_line(db, pi2, item_code="C1", description="盆")
    row2 = _seed_packing_row(db, pi2, item_code="C1", description=" 盆 ", row_no=1)
    other_line = _seed_pi_line(db, pi1, item_code="C2", description="连体马桶", line_no=2)

    counts = dtsvc.rebind(db, "盆", "Basin")

    db.refresh(line1)
    db.refresh(row1)
    db.refresh(line2)
    db.refresh(row2)
    db.refresh(other_line)

    assert line1.description_en == "Basin"
    assert row1.description_en == "Basin"
    assert line2.description_en == "Basin"
    assert row2.description_en == "Basin"
    assert other_line.description_en is None
    assert counts == {"lines": 2, "packing_rows": 2}


def test_a4_rebind_to_none_clears_only_the_matching_rows(db):
    """A4 - `rebind(db, "盆", None)` sets `description_en` NULL on the same rows only."""
    w = World(db)
    supplier = w.supplier()
    pi1 = _seed_pi(db, str(supplier.id))
    line1 = _seed_pi_line(db, pi1, item_code="C1", description="盆")
    row1 = _seed_packing_row(db, pi1, item_code="C1", description=" 盆 ", row_no=1)
    other_line = _seed_pi_line(db, pi1, item_code="C2", description="连体马桶", line_no=2)

    dtsvc.rebind(db, "盆", "Basin")
    dtsvc.rebind(db, "盆", None)

    db.refresh(line1)
    db.refresh(row1)
    db.refresh(other_line)

    assert line1.description_en is None
    assert row1.description_en is None
    assert other_line.description_en is None


def test_a5_remember_rebinds_and_returns_written_and_rebound_counts(db):
    """A5 - `remember` re-binds (shape from A3) and returns `{"written": 1, "rebound":
    {"lines": 2, "packing_rows": 2}}` - `remember` used to return a bare int."""
    w = World(db)
    supplier = w.supplier()
    pi1 = _seed_pi(db, str(supplier.id))
    pi2 = _seed_pi(db, str(supplier.id))
    line1 = _seed_pi_line(db, pi1, item_code="C1", description="盆")
    row1 = _seed_packing_row(db, pi1, item_code="C1", description=" 盆 ", row_no=1)
    line2 = _seed_pi_line(db, pi2, item_code="C1", description="盆")
    row2 = _seed_packing_row(db, pi2, item_code="C1", description=" 盆 ", row_no=1)

    result = tsvc.remember(db, [{"source_text": "盆", "target_text": "Basin"}])

    assert result == {"written": 1, "rebound": {"lines": 2, "packing_rows": 2}}
    for row in (line1, row1, line2, row2):
        db.refresh(row)
        assert row.description_en == "Basin"


def test_a6_update_and_delete_memory_rebind_every_row(db):
    """A6 - `update_target_text` re-binds every row to the new English; `delete_memory`
    re-binds them to NULL."""
    from app.models.translation_memory import TranslationMemory

    w = World(db)
    supplier = w.supplier()
    pi1 = _seed_pi(db, str(supplier.id))
    line1 = _seed_pi_line(db, pi1, item_code="C1", description="盆")
    row1 = _seed_packing_row(db, pi1, item_code="C1", description=" 盆 ", row_no=1)
    _remember(db, "盆", "Basin")
    dtsvc.rebind(db, "盆", "Basin")
    db.commit()

    memory_row = (
        db.query(TranslationMemory)
        .filter(TranslationMemory.source_text == "盆", TranslationMemory.target_lang == "en")
        .one()
    )

    tsvc.update_target_text(db, memory_row.id, "Wash basin")
    db.refresh(line1)
    db.refresh(row1)
    assert line1.description_en == "Wash basin"
    assert row1.description_en == "Wash basin"

    tsvc.delete_memory(db, memory_row.id)
    db.refresh(line1)
    db.refresh(row1)
    assert line1.description_en is None
    assert row1.description_en is None


def test_a7_a_non_english_target_lang_never_touches_description_en(db):
    """A7 - a `盆` memory row with `target_lang='ms'` never touches `description_en` on
    `remember` / `update_target_text` / `delete_memory` (R5: only zh -> en re-binds)."""
    from app.models.translation_memory import TranslationMemory

    w = World(db)
    supplier = w.supplier()
    pi1 = _seed_pi(db, str(supplier.id))
    line1 = _seed_pi_line(db, pi1, item_code="C1", description="盆")

    result = tsvc.remember(
        db, [{"source_text": "盆", "target_text": "Besen"}], target_lang="ms"
    )
    db.refresh(line1)
    assert line1.description_en is None
    assert result["rebound"] == {"lines": 0, "packing_rows": 0}

    ms_row = (
        db.query(TranslationMemory)
        .filter(TranslationMemory.source_text == "盆", TranslationMemory.target_lang == "ms")
        .one()
    )
    tsvc.update_target_text(db, ms_row.id, "Besen baharu")
    db.refresh(line1)
    assert line1.description_en is None

    tsvc.delete_memory(db, ms_row.id)
    db.refresh(line1)
    assert line1.description_en is None


# ============================================================================= B. Fill on write


def test_b1_replace_packing_rows_fills_description_en_on_write(db, monkeypatch):
    """B1 - `replace_packing_rows` with rows named `盆`, `连体马桶`, `Unknown thing`, `BASIN`
    (memory holding the first two, `_ai_fill` -> `{}`): rows land Basin, One-piece toilet,
    NULL, NULL."""
    from app.services.scm.packing_list_reader import PackingLine
    from app.services.scm.proforma_invoice_packing_service import replace_packing_rows
    from app.models.scm import ProformaInvoicePackingLine

    w = World(db)
    supplier = w.supplier()
    invoice = _seed_pi(db, str(supplier.id))
    _remember(db, "盆", "Basin")
    _remember(db, "连体马桶", "One-piece toilet")
    monkeypatch.setattr(tsvc, "_ai_fill", lambda *a, **kw: {})

    lines = [
        PackingLine(row_number=1, item_code=f"{MARKER}-C1", qty=1.0, product_name="盆"),
        PackingLine(row_number=2, item_code=f"{MARKER}-C2", qty=1.0, product_name="连体马桶"),
        PackingLine(row_number=3, item_code=f"{MARKER}-C3", qty=1.0, product_name="Unknown thing"),
        PackingLine(row_number=4, item_code=f"{MARKER}-C4", qty=1.0, product_name="BASIN"),
    ]

    replace_packing_rows(db, invoice, lines, supplier_id=str(supplier.id))
    db.commit()

    rows = {
        r.item_code: r
        for r in db.query(ProformaInvoicePackingLine)
        .filter(ProformaInvoicePackingLine.proforma_invoice_id == invoice.id)
        .all()
    }
    assert rows[f"{MARKER}-C1"].description_en == "Basin"
    assert rows[f"{MARKER}-C2"].description_en == "One-piece toilet"
    assert rows[f"{MARKER}-C3"].description_en is None
    assert rows[f"{MARKER}-C4"].description_en is None


def test_b2_pi_apply_fills_description_en_for_the_line_the_memory_knows(db, monkeypatch):
    """B2 - PI apply through the real service function (the Jinbaichuan combined-file
    fixture, whose own lines read `连体马桶` / `盆`, `test_proforma_invoice_packing_lines.py`
    AC-B3) with a memory row for ONE of those texts writes `description_en` for every line
    carrying it and NULL for the rest."""
    from app.config import settings
    from app.models.scm import ProformaInvoiceLine
    from app.services.scm import supplier_document_service as doc_svc

    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)
    lane_fixtures = (
        Path(__file__).resolve().parents[3] / "documentation" / "plans" / "scm" / "fixtures"
    )
    jbc_bytes = (lane_fixtures / "Jinbaichuan_Invoice.xlsx").read_bytes()
    codes = [
        "SRTWC8366-RL-300", "SRTWC8366-RL-250", "CWB242", "CWB242海关样品",
        "SRTWC8152-SH-250-UF", "MWB243", "MWB243海关样品", "SRTWC286-SH-250-NEW",
    ]

    w = World(db)
    jbc = w.supplier("Jinbaichuan")
    for code in codes:
        w.product(code)
    _seed_aliases(db)
    _remember(db, "连体马桶", "One-piece toilet")

    out = doc_svc.apply(
        db, [("Jinbaichuan_Invoice.xlsx", jbc_bytes, None)],
        supplier_id=str(jbc.id), currency="RMB",
    )
    db.commit()
    invoice_id = out["proforma_invoice_ids"][0]

    lines = (
        db.query(ProformaInvoiceLine).filter(ProformaInvoiceLine.invoice_id == invoice_id).all()
    )
    by_desc = {}
    for ln in lines:
        by_desc.setdefault(ln.description, []).append(ln)

    for ln in by_desc.get("连体马桶", []):
        assert ln.description_en == "One-piece toilet"
    for ln in by_desc.get("盆", []):
        assert ln.description_en is None


def test_b3_line_update_refills_description_en_on_a_changed_description(db, monkeypatch):
    """B3 - the line-update write path (`update_invoice` -> `_write_lines`) that changes a
    line's `description` from `盆` to `连体马桶` re-fills and stores the new English; a
    change to an unknown text stores NULL."""
    from app.services.scm import proforma_invoice_service as pi_svc

    monkeypatch.setattr(tsvc, "_ai_fill", lambda *a, **kw: {})
    w = World(db)
    supplier = w.supplier()
    invoice = _seed_pi(db, str(supplier.id))
    line = _seed_pi_line(db, invoice, item_code="C1", description="盆")
    _remember(db, "连体马桶", "One-piece toilet")

    pi_svc.update_invoice(
        db, str(invoice.id),
        lines=[{"id": str(line.id), "item_code": "C1", "description": "连体马桶", "qty": 1}],
    )
    db.commit()
    db.refresh(line)
    assert line.description_en == "One-piece toilet"

    pi_svc.update_invoice(
        db, str(invoice.id),
        lines=[{"id": str(line.id), "item_code": "C1", "description": "未知文字", "qty": 1}],
    )
    db.commit()
    db.refresh(line)
    assert line.description_en is None


def test_b4_serialize_carries_description_en_on_every_line_and_packing_row(db):
    """B4 - `serialize` output: each line dict and each packing row dict carries
    `description_en`, present even when NULL."""
    from app.services.scm import proforma_invoice_service as pi_svc

    w = World(db)
    supplier = w.supplier()
    invoice = _seed_pi(db, str(supplier.id))
    line = _seed_pi_line(db, invoice, item_code="C1", description="盆")
    line.description_en = "Basin"
    _seed_packing_row(db, invoice, item_code="C2", description="连体马桶", row_no=1)
    db.commit()

    payload = pi_svc.serialize(db, invoice)

    line_dict = next(l for l in payload["lines"] if l["item_code"] == "C1")
    assert "description_en" in line_dict
    assert line_dict["description_en"] == "Basin"

    row_dict = next(r for r in payload["packing_lines"] if r["item_code"] == "C2")
    assert "description_en" in row_dict
    assert row_dict["description_en"] is None


def test_b5_translating_after_upload_never_shows_as_a_revision_change(db):
    """B5 - a translation added AFTER upload does not create a revision entry: the diff for
    a PI whose lines gained `description_en` (through a translation, not a real change to
    qty/price/description) reports no `changed` lines."""
    from app.services.scm import proforma_invoice_service as pi_svc

    w = World(db)
    supplier = w.supplier()
    previous = _seed_pi(db, str(supplier.id))
    _seed_pi_line(db, previous, item_code="C1", description="连体马桶", qty=10, unit_price=5)
    current = _seed_pi(db, str(supplier.id), revision_of_id=previous.id, revision_no=2)
    current_line = _seed_pi_line(
        db, current, item_code="C1", description="连体马桶", qty=10, unit_price=5
    )
    db.commit()

    before = pi_svc.serialize(db, current)
    assert before["diff"]["changes"] == []

    dtsvc.rebind(db, "连体马桶", "One-piece toilet")
    db.commit()
    db.refresh(current_line)
    assert current_line.description_en == "One-piece toilet"

    after = pi_svc.serialize(db, current)
    assert after["diff"]["changes"] == [], "filling description_en must not read as a revision change"


_MIGRATION_510_PATH = _VERSIONS / "510_pi_description_en.py"


def _migration_510_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_510_pi_description_en", _MIGRATION_510_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade_510(db) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_510_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.upgrade()


def _run_downgrade_510(db) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_510_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.downgrade()


def test_b6_migration_510_backfills_description_en_and_downgrade_drops_the_columns():
    """B6 - a line and a packing row with `description='盆'` written BEFORE the migration,
    and a memory row for `盆`, carry `description_en='Basin'` after upgrade; downgrade drops
    both columns and leaves `translation_memory` alone.

    Run the same way `tests/test_migration_466_shipment_line_description.py` runs its own
    migration - `upgrade()`/`downgrade()` invoked directly via `alembic.operations.Operations`
    against `pg_session()` (the real database, rolled back at teardown) - rather than a
    scratch schema (which cannot host a migration file that does not exist yet, `510_pi_
    description_en.py`, so the file's own absence is what this test is red on first)."""
    from sqlalchemy import text as sa_text

    from tests._pg_fixture import pg_session, unique_code

    with pg_session() as db:
        db.execute(sa_text(
            "ALTER TABLE scm.proforma_invoice_line DROP COLUMN IF EXISTS description_en"
        ))
        db.execute(sa_text(
            "ALTER TABLE scm.proforma_invoice_packing_line DROP COLUMN IF EXISTS description_en"
        ))
        db.flush()

        w = World(db)
        supplier = w.supplier()
        invoice = _seed_pi(db, str(supplier.id))
        db.execute(
            sa_text(
                "INSERT INTO scm.proforma_invoice_line (id, invoice_id, line_no, item_code, qty, description) "
                "VALUES (:id, :invoice_id, 1, :code, 1, '盆')"
            ),
            {"id": str(uuid.uuid4()), "invoice_id": invoice.id, "code": unique_code("CODE")},
        )
        db.execute(
            sa_text(
                "INSERT INTO scm.proforma_invoice_packing_line "
                "(id, proforma_invoice_id, row_no, item_code, qty, description, match_state) "
                "VALUES (:id, :invoice_id, 1, :code, 1, '盆', 'unmatched')"
            ),
            {"id": str(uuid.uuid4()), "invoice_id": invoice.id, "code": unique_code("CODE")},
        )
        _remember(db, "盆", "Basin")
        db.flush()

        _run_upgrade_510(db)
        db.expire_all()

        line_en, row_en = db.execute(sa_text(
            "SELECT "
            "(SELECT description_en FROM scm.proforma_invoice_line "
            " WHERE invoice_id = :inv AND description = '盆'), "
            "(SELECT description_en FROM scm.proforma_invoice_packing_line "
            " WHERE proforma_invoice_id = :inv AND description = '盆')"
        ), {"inv": invoice.id}).one()
        assert line_en == "Basin", "migration 510's backfill must fill from translation_memory"
        assert row_en == "Basin"

        _run_downgrade_510(db)
        db.expire_all()

        cols = {
            r[0] for r in db.execute(sa_text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'proforma_invoice_line' AND table_schema = 'scm' "
                "AND column_name = 'description_en'"
            )).fetchall()
        }
        assert not cols, "downgrade must drop proforma_invoice_line.description_en"

        memory_count = db.execute(sa_text(
            "SELECT count(*) FROM translation_memory WHERE source_text = '盆'"
        )).scalar()
        assert memory_count == 1, "downgrade must leave translation_memory alone"


# ============================================================================= C. Downstream


def test_c1_convert_without_packing_rows_copies_description_en_onto_the_shipment_line(db):
    """C1 - convert a PI whose line has `description='盆'`, `description_en='Basin'` (no
    packing rows at all - the plain (product, supplier) grouping path,
    `proforma_invoice_service.py` around line 1906): `InboundShipmentLine.description` is
    `Basin`; a line with `description_en` NULL copies `description` unchanged."""
    from app.services.scm import proforma_invoice_service as pi_svc
    from app.models.procurement import InboundShipmentLine

    w = World(db)
    supplier = w.supplier()
    product_a = w.product(f"{MARKER}-{_tag()}")
    product_b = w.product(f"{MARKER}-{_tag()}")
    invoice = _seed_pi(db, str(supplier.id))
    line_a = _seed_pi_line(
        db, invoice, item_code=product_a.product_code, description="盆",
        qty=5, product_id=product_a.id,
    )
    line_a.description_en = "Basin"
    _seed_pi_line(
        db, invoice, item_code=product_b.product_code, description="连体马桶",
        qty=3, product_id=product_b.id, line_no=2,
    )
    db.commit()

    result = pi_svc.convert_to_draft_shipment(db, [str(invoice.id)], created_by=str(uuid.uuid4()))
    db.commit()

    ship_lines = (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == result["shipment_id"])
        .all()
    )
    line_a_ship = next(l for l in ship_lines if str(l.product_id) == str(product_a.id))
    line_b_ship = next(l for l in ship_lines if str(l.product_id) == str(product_b.id))
    assert line_a_ship.description == "Basin"
    assert line_b_ship.description == "连体马桶"


def test_c2_convert_with_a_matched_packing_row_copies_description_en_onto_the_shipment_line(db):
    """C2 - the SAME target field via the OTHER convert path: a PI line WITH a matched
    packing row (`proforma_invoice_service.py` around line 1790) also reads
    `description_en or description` - the "converted packing list line" the UAC names is
    this same `InboundShipmentLine.description`, reached from the packing-row branch this
    time rather than the plain grouping branch C1 exercises."""
    from app.services.scm import proforma_invoice_service as pi_svc
    from app.models.procurement import InboundShipmentLine

    w = World(db)
    supplier = w.supplier()
    product_a = w.product(f"{MARKER}-{_tag()}")
    invoice = _seed_pi(db, str(supplier.id))
    line_a = _seed_pi_line(
        db, invoice, item_code=product_a.product_code, description="盆",
        qty=5, product_id=product_a.id,
    )
    line_a.description_en = "Basin"
    _seed_packing_row(
        db, invoice, item_code=product_a.product_code, description="盆", row_no=1,
        qty=5, product_id=product_a.id, match_state="matched",
        proforma_invoice_line_id=line_a.id,
    )
    db.commit()

    result = pi_svc.convert_to_draft_shipment(db, [str(invoice.id)], created_by=str(uuid.uuid4()))
    db.commit()

    ship_line = (
        db.query(InboundShipmentLine)
        .filter(InboundShipmentLine.shipment_id == result["shipment_id"])
        .one()
    )
    assert ship_line.description == "Basin"


def test_c3_to_xlsx_prints_description_en_in_the_description_cell(db):
    """C3 - `to_xlsx` (the PI's own workbook export) prints `Basin` in the description cell
    for a line whose `description_en` is set."""
    import openpyxl
    from io import BytesIO

    from app.services.scm import proforma_invoice_service as pi_svc

    w = World(db)
    supplier = w.supplier()
    invoice = _seed_pi(db, str(supplier.id))
    line = _seed_pi_line(db, invoice, item_code="C1", description="盆", qty=1)
    line.description_en = "Basin"
    db.commit()

    payload = pi_svc.serialize(db, invoice)
    xlsx_bytes = pi_svc.to_xlsx(payload)

    wb = openpyxl.load_workbook(BytesIO(xlsx_bytes))
    ws = wb.active
    description_cells = [row[2] for row in ws.iter_rows(min_row=1, values_only=True)]
    assert "Basin" in description_cells
    assert "盆" not in description_cells


def test_c4_an_unmatched_row_lands_english_in_the_unplaced_rows_note(db):
    """C4 - an unmatched/dismissed packing row with `description='盆'`,
    `description_en='Basin'` and no code lands `Basin` in the shipment's unplaced-rows
    note, not `盆`."""
    from app.services.scm import proforma_invoice_service as pi_svc

    w = World(db)
    supplier = w.supplier()
    product_a = w.product(f"{MARKER}-{_tag()}")
    invoice = _seed_pi(db, str(supplier.id))
    # A real line so the convert has something to place - the unplaced row is a SEPARATE,
    # unmatched packing row with no code and no line of its own (AC-D3's own shape).
    _seed_pi_line(
        db, invoice, item_code=product_a.product_code, description="stub",
        qty=5, product_id=product_a.id,
    )
    unplaced = _seed_packing_row(
        db, invoice, item_code="", description="盆", row_no=1, match_state="unmatched",
    )
    unplaced.description_en = "Basin"
    db.commit()

    result = pi_svc.convert_to_draft_shipment(db, [str(invoice.id)], created_by=str(uuid.uuid4()))
    db.commit()

    from app.models.procurement import InboundShipment

    shipment = db.query(InboundShipment).filter(InboundShipment.id == result["shipment_id"]).one()
    assert shipment.notes and "Basin" in shipment.notes
    assert "盆" not in (shipment.notes or "")


# ============================================================================= D. Routes


UPLOAD_PERMISSION = "scm.proforma_invoice.upload"


def _grant(db, uid: str, slug: str) -> None:
    from app.models.user import UserPermission, UserRole, UserRolePermission, UserRoleAssignment
    from app.services.user_service import invalidate_rbac_cache

    # `name` carries a UNIQUE constraint (`user_roles_name_key`), so two `_grant()` calls in
    # one test (D2 grants both the write and the read permission) need distinct names, not
    # just distinct slugs.
    tag = _tag()
    role = UserRole(id=str(uuid.uuid4()), slug=f"{MARKER}-role-{tag}", name=f"role-{tag}")
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
    # `check_user_has_permission` caches its answer for `_RBAC_CACHE_TTL` seconds
    # (`app/services/user_service.py`); a test that already probed this user's grant (D1's
    # own "denied without the permission" step) has that "no" cached, and this write would
    # otherwise still read as denied for up to 30s.
    invalidate_rbac_cache(uid)


def _seed_route_pi(db, marker: str = MARKER):
    """A PI with two lines sharing `盆` as their description, on TWO invoices (like A3's
    shape) - what D2 needs to prove a route write reaches every PI on file, not just the
    one in the URL."""
    from app.models.scm import ProformaInvoice, ProformaInvoiceLine

    tag = uuid.uuid4().hex[:8].upper()
    cat = ProductCategory(id=str(uuid.uuid4()), category_code=f"{marker}-CAT-{tag}", category_name="c")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=f"{marker}U2"[:20], uom_name="pcs")
    db.add_all([cat, uom])
    db.flush()
    supplier = Supplier(
        id=str(uuid.uuid4()), supplier_code=f"{marker}-S-{tag}", supplier_name="S", is_active=True,
    )
    db.add(supplier)
    db.flush()
    invoice1 = ProformaInvoice(id=str(uuid.uuid4()), supplier_id=supplier.id, pi_number=f"PI-{tag}-1")
    invoice2 = ProformaInvoice(id=str(uuid.uuid4()), supplier_id=supplier.id, pi_number=f"PI-{tag}-2")
    db.add_all([invoice1, invoice2])
    db.flush()
    line1 = ProformaInvoiceLine(
        id=str(uuid.uuid4()), invoice_id=invoice1.id, line_no=1, item_code="C1",
        description="盆", qty=1,
    )
    line2 = ProformaInvoiceLine(
        id=str(uuid.uuid4()), invoice_id=invoice2.id, line_no=1, item_code="C1",
        description="盆", qty=1,
    )
    db.add_all([line1, line2])
    db.commit()
    return invoice1, invoice2, line1, line2


def test_d1_the_route_needs_upload_permission_and_404s_an_unknown_invoice(scm_app):
    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    client = TestClient(app)

    invoice1, _invoice2, _l1, _l2 = _seed_route_pi(db)

    denied = client.put(
        f"/api/v1/scm/proforma-invoices/{invoice1.id}/translations",
        json={"source_text": "盆", "target_text": "Basin"},
    )
    assert denied.status_code == 403

    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, UPLOAD_PERMISSION)

    unknown = client.put(
        "/api/v1/scm/proforma-invoices/00000000-0000-0000-0000-000000000000/translations",
        json={"source_text": "盆", "target_text": "Basin"},
    )
    assert unknown.status_code == 404

    non_uuid = client.put(
        "/api/v1/scm/proforma-invoices/not-a-uuid/translations",
        json={"source_text": "盆", "target_text": "Basin"},
    )
    assert non_uuid.status_code == 404


def test_d2_success_body_and_every_matching_row_on_file_updates(scm_app):
    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, UPLOAD_PERMISSION)
    # The read-back below goes through `GET /scm/proforma-invoices/{id}`, gated on
    # `scm.dashboard.view` (`_READ` in `app/api/v1/scm/proforma_invoices.py`) - a
    # DIFFERENT slug from the write route's `scm.proforma_invoice.upload`. D2 is proving
    # the write's effect is visible on read, not proving the write route's own gate (that
    # is D1) - the read side needs its own grant.
    _grant(db, uid, "scm.dashboard.view")
    client = TestClient(app)

    invoice1, invoice2, line1, line2 = _seed_route_pi(db)

    r = client.put(
        f"/api/v1/scm/proforma-invoices/{invoice1.id}/translations",
        json={"source_text": "盆", "target_text": "Basin"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_text"] == "盆"
    assert body["target_text"] == "Basin"
    assert body["source"] == "manual"
    assert body["rebound"] == {"lines": 2, "packing_rows": 0}

    detail = client.get(f"/api/v1/scm/proforma-invoices/{invoice1.id}").json()
    detail_line = next(l for l in detail["lines"] if l["id"] == str(line1.id))
    assert detail_line["description_en"] == "Basin"

    db.expire_all()
    db.refresh(line2)
    assert line2.description_en == "Basin", "a second, unrelated PI sharing the same text must update too"


def test_d3_blank_source_or_target_text_is_422_and_writes_nothing(scm_app):
    from tests.scm.test_outstanding_import_routes import as_company_user

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, UPLOAD_PERMISSION)
    client = TestClient(app)

    invoice1, _invoice2, _l1, _l2 = _seed_route_pi(db)

    blank_target = client.put(
        f"/api/v1/scm/proforma-invoices/{invoice1.id}/translations",
        json={"source_text": "盆", "target_text": ""},
    )
    assert blank_target.status_code == 422
    assert "target_text" in str(blank_target.json())

    blank_source = client.put(
        f"/api/v1/scm/proforma-invoices/{invoice1.id}/translations",
        json={"source_text": "", "target_text": "Basin"},
    )
    assert blank_source.status_code == 422
    assert "source_text" in str(blank_source.json())

    from app.models.translation_memory import TranslationMemory

    assert (
        db.query(TranslationMemory).filter(TranslationMemory.source_text == "盆").count() == 0
    )


def test_d4_a_second_put_overwrites_manual_over_an_existing_ai_row(scm_app):
    from tests.scm.test_outstanding_import_routes import as_company_user
    from app.models.translation_memory import SOURCE_AI, TranslationMemory

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    _grant(db, uid, UPLOAD_PERMISSION)
    client = TestClient(app)

    invoice1, _invoice2, _l1, _l2 = _seed_route_pi(db)
    db.add(
        TranslationMemory(
            id=str(uuid.uuid4()), source_text="盆", source_lang="zh", target_lang="en",
            target_text="Bowl", source=SOURCE_AI,
        )
    )
    db.commit()

    first = client.put(
        f"/api/v1/scm/proforma-invoices/{invoice1.id}/translations",
        json={"source_text": "盆", "target_text": "Basin"},
    )
    assert first.status_code == 200, first.text
    second = client.put(
        f"/api/v1/scm/proforma-invoices/{invoice1.id}/translations",
        json={"source_text": "盆", "target_text": "Wash basin"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["source"] == "manual"

    rows = db.query(TranslationMemory).filter(TranslationMemory.source_text == "盆").all()
    assert len(rows) == 1, "a second PUT for the same text must overwrite, never duplicate"
    assert rows[0].source == "manual"
    assert rows[0].target_text == "Wash basin"


def test_d5a_the_admin_edit_route_rebinds_the_rows(db, monkeypatch):
    """D5, first half - `PUT /system/translations/{id}` (existing route, unchanged shape)
    re-binds every matching row too, the same as A6 through the direct service call."""
    from fastapi import Depends

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.models.base import set_company_scope
    from app.models.user import User
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService
    from app.main import app

    w = World(db)
    supplier = w.supplier()
    invoice = _seed_pi(db, str(supplier.id))
    line = _seed_pi_line(db, invoice, item_code="C1", description="盆")
    _remember(db, "盆", "Basin")
    dtsvc.rebind(db, "盆", "Basin")
    db.commit()

    from app.models.translation_memory import TranslationMemory

    memory_row = (
        db.query(TranslationMemory)
        .filter(TranslationMemory.source_text == "盆", TranslationMemory.target_lang == "en")
        .one()
    )

    # A REAL row: `sla_form_actions.requested_by_id` (and the admin route's own
    # `created_by`) are FKs to `users`, and a fabricated uuid trips an unrelated
    # IntegrityError that reads as "another action is pending" (form_action_service's
    # own catch-all) rather than the FK violation it actually is.
    actor_row = User(id=str(uuid.uuid4()), email="zzt-actor@example.test", name="Ada Actor")
    db.add(actor_row)
    db.flush()
    actor = {"id": actor_row.id, "email": actor_row.email, "name": actor_row.name}

    def _override_get_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[apply_company_scope] = _override_scope
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_current_user_or_api_key] = lambda: actor
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True,
    )
    try:
        with TestClient(app) as client:
            r = client.put(
                f"/api/v1/system/translations/{memory_row.id}",
                json={"target_text": "Wash basin"},
            )
            assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    db.refresh(line)
    assert line.description_en == "Wash basin"


def test_d5b_the_deferred_delete_action_rebinds_the_rows_to_none(db, monkeypatch):
    """D5, second half - the deferred `translation_memory.delete` action, when it lapses,
    re-binds the rows to NULL (through the SAME pending-actions harness
    `tests/test_pending_actions.py` uses for every other deferred delete)."""
    from datetime import datetime, timedelta

    from fastapi import Depends

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.models.base import set_company_scope
    from app.models.sla import SlaFormAction
    from app.models.user import User
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService
    from app.main import app

    w = World(db)
    supplier = w.supplier()
    invoice = _seed_pi(db, str(supplier.id))
    line = _seed_pi_line(db, invoice, item_code="C1", description="盆")
    _remember(db, "盆", "Basin")
    dtsvc.rebind(db, "盆", "Basin")
    db.commit()

    from app.models.translation_memory import TranslationMemory

    memory_row = (
        db.query(TranslationMemory)
        .filter(TranslationMemory.source_text == "盆", TranslationMemory.target_lang == "en")
        .one()
    )

    # A REAL row - `sla_form_actions.requested_by_id` is a FK to `users` (see D5a's own
    # note on the same trap).
    actor_row = User(id=str(uuid.uuid4()), email="zzt-actor2@example.test", name="Bo Actor")
    db.add(actor_row)
    db.flush()
    actor = {"id": actor_row.id, "email": actor_row.email, "name": actor_row.name}

    def _override_get_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[apply_company_scope] = _override_scope
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_current_user_or_api_key] = lambda: actor
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True,
    )
    try:
        with TestClient(app) as client:
            parked = client.post(
                "/api/v1/pending-actions",
                json={
                    "action_key": "translation_memory.delete",
                    "entity_type": "translation_memory",
                    "entity_id": str(memory_row.id),
                    "payload": {},
                },
            )
            assert parked.status_code in (200, 201, 202), parked.text
            action_id = parked.json()["id"]

            db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
                {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
                synchronize_session=False,
            )
            db.commit()

            current = client.get(
                "/api/v1/pending-actions/current",
                params={"entity_type": "translation_memory", "entity_id": str(memory_row.id)},
            )
            assert current.status_code == 200, current.text
            assert current.json()["last_outcome"]["status"] == "committed"
    finally:
        app.dependency_overrides.clear()

    db.refresh(line)
    assert line.description_en is None
