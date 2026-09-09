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
from app.models.procurement import Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.error_handler import AppException
from app.services.scm import supplier_document_service as svc
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.usefixtures("no_live_llm")

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


def _workbook(rows: list[list]) -> bytes:
    import openpyxl
    from io import BytesIO

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


def test_apply_gives_each_container_its_own_total_not_the_documents_grand_total():
    """Browser-test round, finding 2: applying the Jiexia proforma invoice used to
    leave BOTH containers reading the FILE's own grand TOTAL (209892) - the per-block
    `SUB TOTAL 1*40HQ` row was never recognised as a total at all (it does not equal
    the plain `TOTAL` label under normalisation), so nothing stopped the file-wide
    TOTAL row from landing on whichever document was `current` when it was read.
    Each invoice's own `total_amount` is its own block's SUB TOTAL now, which happens
    to equal its own line sum here - never the file's total, and never the OTHER
    container's total either."""
    from app.models.scm import ProformaInvoice
    from app.services.scm import proforma_invoice_service

    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_world(db)

        out = svc.apply(
            db,
            [("发票 SORENTO-2026.7.26.xls", _pi_bytes(), None)],
            supplier_id=str(w.supplier.id),
            currency="RMB",
        )
        db.commit()

        invoices = (
            db.query(ProformaInvoice)
            .filter(ProformaInvoice.id.in_(out["proforma_invoice_ids"]))
            .order_by(ProformaInvoice.total_amount)
            .all()
        )
        assert [float(inv.total_amount) for inv in invoices] == pytest.approx(
            [87710.0, 122182.0]
        )

        # Deleting one sibling does not touch the other's header (part of finding 2).
        first, second = invoices
        second_id, expected_second_total = str(second.id), float(second.total_amount)
        proforma_invoice_service.delete(db, str(first.id))
        db.commit()

        assert db.query(ProformaInvoice).filter(ProformaInvoice.id == first.id).first() is None
        remaining = db.query(ProformaInvoice).filter(ProformaInvoice.id == second_id).one()
        assert float(remaining.total_amount) == pytest.approx(expected_second_total)


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


def test_preview_price_matches_counts_by_product_not_line_counts():
    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_world(db)

        out = svc.preview(
            db,
            [
                ("发票 SORENTO-2026.7.26.xls", _pi_bytes()),
                ("装箱单 SORENTO-2026.7.26.xls", _pl_bytes()),
            ],
            supplier_id=str(w.supplier.id),
        )

        matches = {m["container_no"]: m for m in out["price_matches"]}
        # Block WHSU6243088: PI's 3 lines (two share ONE product) all resolve to a
        # product the packing list's own block also carries - matched 3, unmatched 0.
        assert matches["WHSU6243088"]["matched_lines"] == 3
        assert matches["WHSU6243088"]["unmatched_lines"] == 0
        assert matches["WHSU6243088"]["pi_number"] == "2026JXL0726"
        # Block WHSU6356079: PI's 2 lines, same product, both present on the packing
        # list's own block - matched 2, unmatched 0.
        assert matches["WHSU6356079"]["matched_lines"] == 2
        assert matches["WHSU6356079"]["unmatched_lines"] == 0

        # Neither file's OWN "blocks" leak the internal `_pi_match`/`_pl_match` keys.
        for f in out["files"]:
            assert "_pi_match" not in f
            assert "_pl_match" not in f


def test_preview_price_matches_no_self_match_within_one_combined_file(monkeypatch):
    """A combined file's PI part and PL part are structurally tagged (`_pi_match` /
    `_pl_match`), never read off the same `blocks` list - so a PI-shaped block can never
    ALSO be counted as a packing-list block and matched against itself.

    Neither real fixture produces a genuinely combined file (Deviations, lane C), so this
    fabricates one `_file_preview` result the shape a combined file WOULD have - one PI
    document and one PL block sharing a container - and proves `preview()`'s aggregation
    produces exactly the one legitimate cross-match, not a second, self-referential entry
    the old "read both off one `blocks` list, keyed by the FILE's kind" logic would have.
    """
    with blank_session() as db:
        w = _seed_world(db)

        monkeypatch.setattr(
            svc,
            "_file_preview",
            # `**_attach` swallows `supplier_id`/`attach_to`/`block_attach`, which
            # `preview()` passes since attach resolution became per block (fix round 1).
            lambda db, name, data, **_attach: {
                "name": name,
                "kind": "combined",
                "blocks": [],
                "header": {"pi_number": None, "invoice_date": None, "consignee": None,
                           "shipper": None, "so_ref": None},
                "unmatched": [],
                "errors": [],
                "footer_note": None,
                "_pi_match": [
                    {"container_no": "ABCU1", "pi_number": "PI-1", "line_products": ["p1"]}
                ],
                "_pl_match": [{"container_no": "ABCU1", "products": {"p1"}}],
            },
        )

        out = svc.preview(db, [("both.xls", b"whatever")], supplier_id=str(w.supplier.id))

        assert out["price_matches"] == [
            {"container_no": "ABCU1", "pi_number": "PI-1", "matched_lines": 1, "unmatched_lines": 0}
        ]


# --- Nit, review round 1: classify()'s header-shape fallback for a titleless file ---------


def test_classify_falls_back_to_header_shape_when_titleless():
    with blank_session() as db:
        _seed_aliases(db)

        pl_bytes = _workbook([["产品型号", "数量"], ["SRT-1", 5]])
        assert svc.classify(pl_bytes, db) == "packing_list"

        pi_bytes = _workbook([["产品型号", "数量", "单价"], ["SRT-1", 5, 10]])
        assert svc.classify(pi_bytes, db) == "proforma_invoice"

        assert svc.classify(b"not a workbook at all", db) is None


# --- B3, review round 1: the route commits, so a second preview finds the memory --------


def test_preview_commits_so_a_second_preview_of_the_same_file_asks_the_model_once(monkeypatch):
    """`preview_supplier_documents`'s route now `db.commit()`s after the call - its
    own writes are `translation_service`'s AI-fill rows and `hit_count` bumps.
    Simulated here at the service level (the same `db.commit()` the route now
    calls, between two `preview()` calls on the SAME session): a live `TestClient`
    route test needs migration 483 run somewhere reachable, which it is not yet
    (Deviations, lane C). Without the commit, the first preview's AI-fill insert
    rolled back and the SAME miss asked the model again on the very next preview -
    this is the exact defect B3 names.
    """
    import json
    import uuid as _uuid
    from types import SimpleNamespace

    from app.config import settings
    from app.models.ai_assistant import AIAssistantConfig
    from app.services import translation_service as translation_svc

    class _FakeProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, **_kwargs):
            self.calls += 1
            user_content = messages[-1]["content"]
            lines = [
                ln.split(". ", 1)[1] if ". " in ln else ln
                for ln in user_content.rsplit("\n\n", 1)[-1].splitlines()
                if ln.strip()
            ]
            translations = [{"source": ln, "target": f"[{ln}]"} for ln in lines]
            return SimpleNamespace(content=json.dumps({"translations": translations}))

    fake = _FakeProvider()

    with blank_session() as db:
        _seed_aliases(db)
        w = _seed_world(db)
        # Re-enable AI for this one test - the file's own `_no_ai_translation` fixture
        # forces it off for every other test.
        monkeypatch.setattr(settings, "openai_api_key", "fake-key", raising=False)
        db.add(
            AIAssistantConfig(
                id=str(_uuid.uuid4()), provider="openai", model="gpt-4o-mini",
                temperature=0, system_prompt="", api_key_ciphertext="fake-key",
                enabled_tools=[], rag_enabled=True, is_enabled=True,
            )
        )
        db.flush()
        monkeypatch.setattr(translation_svc, "get_provider", lambda *a, **kw: fake)

        svc.preview(db, [("装箱单 SORENTO-2026.7.26.xls", _pl_bytes())], supplier_id=str(w.supplier.id))
        db.commit()  # what the route now does (B3) - without it, the AI row never lands

        svc.preview(db, [("装箱单 SORENTO-2026.7.26.xls", _pl_bytes())], supplier_id=str(w.supplier.id))
        db.commit()

        assert fake.calls == 1
