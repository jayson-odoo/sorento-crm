"""Stock list bare model codes - the SERVICE half (S3, `PLAN-stock-list-bare-model-codes.md`).

TEST-FIRST (Phase 2): `supplier_inventory_service` does not yet build a `WordList` for the
chosen supplier, so AC-S1/AC-S2 are expected to be RED - either a `ModuleNotFoundError`
seeding word rows, or an assertion that a bare code composed and bound where today it is
kept verbatim and unmatched. AC-S3 is a guard-rail rather than a red test: it is expected to
PASS now (the matcher is untouched) and to start failing the moment a slice edits it.

Every product/supplier/word row is seeded by this file under its own marker-prefixed codes,
per `tests/scm/test_supplier_inventory_service.py`'s own rule - the CI database starts empty.
"""
from __future__ import annotations

import subprocess
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest

from app.services.scm import supplier_inventory_service as svc
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import MARKER, require_aliases

HEADER = ["型号", "品名", "商标", "规格", "包装好库存", "空瓷", "体积(cbm)", "备注"]


def workbook(rows, header=None) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(header or HEADER))
    for r in rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class Codes:
    def __init__(self):
        tag = uuid.uuid4().hex[:8].upper()
        self.known = f"{MARKER}-SIBC-{tag}"
        self.supplier = f"{MARKER}-CRSIBC-{tag}"


def seed(db, codes: Codes, *, product_code: str | None = None) -> str:
    """The one catalogue product and the one supplier this file names. Returns supplier id."""
    from app.models.procurement import Supplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    require_aliases(db, "supplier_inventory")

    cat = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=f"{MARKER}-CATBC-{uuid.uuid4().hex[:8]}".upper(),
        category_name=f"{MARKER} bare-code category",
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()),
        uom_code=f"{MARKER}-UBC-{uuid.uuid4().hex[:6]}".upper(),
        uom_name="pcs",
    )
    db.add_all([cat, uom])
    db.flush()
    db.add(
        Product(
            id=str(uuid.uuid4()),
            product_code=product_code or codes.known,
            product_name=product_code or codes.known,
            category_id=cat.id,
            base_uom_id=uom.id,
            list_price=0,
            is_active=True,
            is_discontinued=False,
        )
    )
    supplier = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=codes.supplier,
        supplier_name=f"{MARKER} bare-code supplier",
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return str(supplier.id)


def _seed_shared_words(db) -> None:
    """The D7 seed's shape, restated by hand (not read off the migration) - the exact rows
    `SRTWB7055` needs: SORENTO -> SRT, 盆 -> WB."""
    from app.models.import_alias import ImportFieldAlias
    from app.services.scm.supplier_code_composer import WORD_DOC_TYPE

    db.add_all(
        [
            ImportFieldAlias(
                id=str(uuid.uuid4()), doc_type=WORD_DOC_TYPE, field="SRT",
                alias="SORENTO", supplier_id=None,
            ),
            ImportFieldAlias(
                id=str(uuid.uuid4()), doc_type=WORD_DOC_TYPE, field="WB",
                alias="盆", supplier_id=None,
            ),
        ]
    )
    db.flush()


def held(db, supplier_id: str):
    from app.models.scm import SupplierInventory

    return (
        db.query(SupplierInventory)
        .filter(SupplierInventory.supplier_id == supplier_id)
        .order_by(SupplierInventory.item_code)
        .all()
    )


def test_ac_s1_a_bare_code_file_binds_via_the_exact_rung_and_writes_no_alias():
    with pg_session() as db:
        from app.models.scm import SupplierProductCodeAlias

        codes = Codes()
        supplier_id = seed(db, codes, product_code="SRTWB7055")
        _seed_shared_words(db)
        data = workbook([["-7055", "盆", "SORENTO", None, 5, 0, 0.2, ""]])

        out = svc.apply(db, data, supplier_id=supplier_id, as_of=date(2026, 9, 14))

        assert out["rows_written"] == 1
        row = held(db, supplier_id)[0]
        assert row.item_code == "SRTWB7055"
        assert row.product_id is not None

        remembered = (
            db.query(SupplierProductCodeAlias)
            .filter(
                SupplierProductCodeAlias.supplier_id == supplier_id,
                SupplierProductCodeAlias.supplier_code == "SRTWB7055",
            )
            .count()
        )
        assert remembered == 0


def test_ac_s2_a_letter_led_fixture_is_identical_with_or_without_a_word_list():
    codes = Codes()

    def run(seed_words_flag: bool):
        with pg_session() as db:
            supplier_id = seed(db, codes)
            if seed_words_flag:
                _seed_shared_words(db)
            data = workbook([[codes.known, "座厕", "SORENTO", None, 120, 340, 0.21, ""]])

            out = svc.apply(db, data, supplier_id=supplier_id, as_of=date(2026, 7, 31))

            row = held(db, supplier_id)[0]
            return (
                out["rows_written"],
                out["summary"]["items_matched"],
                row.item_code,
                row.product_id,
                float(row.qty_packed),
                float(row.qty_unfinished),
            )

    without_words = run(False)
    with_words = run(True)

    assert without_words == with_words


def test_ac_s3_supplier_code_matcher_has_no_diff_in_the_pr():
    repo_root = Path(__file__).resolve().parents[2]
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available in this environment")

    result = subprocess.run(
        ["git", "diff", "origin/main", "--", "app/services/scm/supplier_code_matcher.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"git diff against origin/main failed: {result.stderr.strip()}")

    assert result.stdout.strip() == "", (
        "supplier_code_matcher.py has a diff against origin/main - the plan's out-of-scope "
        "line says this file is never touched:\n" + result.stdout
    )
