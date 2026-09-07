"""AC-G2 - the supplier-documents preview shows English beside Chinese for an
unmatched line's description, a matched line's remark, a block note and the file's
footer; an edited cell writes a manual row that the NEXT preview reads back (R16,
purchasing consolidation batch, lane C).

`blank_session` for the same reason `test_supplier_document_service.py` uses it: this
suite's own migration (`483_supplier_doc_aliases`) has not been run with `alembic
upgrade head` against the shared dev database. The AI provider is ALWAYS stubbed - the
Jiexia packing list fixture's own text is real Chinese, so an unstubbed run would make
a genuine call to the key `.env` carries for the app itself.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.ai_assistant import AIAssistantConfig
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.procurement import Supplier
from app.services import translation_service as tsvc
from app.services.scm import supplier_document_service as svc
from tests._pg_fixture import blank_session

# Reused verbatim from `test_supplier_document_service.py` rather than imported: that
# module seeds every PL code as a KNOWN product (AC-F5's price-matching scenario), which
# leaves this suite's own unmatched-description case with nothing to prove - this file
# seeds its OWN, smaller world instead.
import importlib.util

pytestmark = pytest.mark.usefixtures("no_live_llm")

MARKER = "ZZSDT"
_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


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


def _pl_bytes() -> bytes:
    return (_FIXTURES / "jiexia_packing_list_sample.xls").read_bytes()


def _configure_ai(db) -> AIAssistantConfig:
    cfg = AIAssistantConfig(
        id=str(uuid.uuid4()),
        provider="openai",
        model="gpt-4o-mini",
        temperature=0,
        system_prompt="",
        api_key_ciphertext="fake-key",
        enabled_tools=[],
        rag_enabled=True,
        is_enabled=True,
    )
    db.add(cfg)
    db.flush()
    return cfg


class _FakeProvider:
    def __init__(self, answers: dict[str, str]):
        self.answers = answers
        self.calls: list[list[dict]] = []

    def chat(self, messages, **_kwargs):
        self.calls.append(messages)
        user_content = messages[-1]["content"]
        lines = [
            ln.split(". ", 1)[1] if ". " in ln else ln
            for ln in user_content.rsplit("\n\n", 1)[-1].splitlines()
            if ln.strip()
        ]
        translations = [
            {"source": ln, "target": self.answers.get(ln, f"[{ln}]")} for ln in lines
        ]
        return SimpleNamespace(content=json.dumps({"translations": translations}))


def _stub_provider(monkeypatch, answers: dict[str, str]) -> _FakeProvider:
    fake = _FakeProvider(answers)
    monkeypatch.setattr(tsvc, "get_provider", lambda *a, **kw: fake)
    return fake


class World:
    """Products for only THREE of the packing list's four codes, so the fourth
    (`SRTWCY8840`, product_name '水箱') is unmatched and its description is what
    this suite's preview is about."""

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
        for code in ("SRTWCX8840-S-RL", "SRTWCX8840-P-RL", "8840"):
            self.db.add(
                Product(
                    id=str(uuid.uuid4()), product_code=code, product_name=code,
                    category_id=self.cat.id, base_uom_id=self.uom.id, list_price=0,
                    is_active=True, is_discontinued=False,
                )
            )
        db.flush()


def _pl_block1(preview: dict) -> dict:
    file = next(f for f in preview["files"] if f["kind"] == "packing_list")
    return next(b for b in file["blocks"] if b["container_no"] == "WHSU6243088")


def test_preview_shows_english_beside_chinese_for_the_unmatched_description(db, monkeypatch):
    _seed_aliases(db)
    w = World(db)
    _configure_ai(db)
    _stub_provider(monkeypatch, {"水箱": "Water tank", "纸箱：2个": "Carton: 2 pieces"})

    preview = svc.preview(
        db, [("装箱单.xls", _pl_bytes())], supplier_id=str(w.supplier.id)
    )

    block1 = _pl_block1(preview)
    unmatched_line = next(
        ln for ln in block1["lines"] if ln["item_code"] == "SRTWCY8840"
    )
    assert unmatched_line["matched"] is False
    assert unmatched_line["description"] == "水箱"
    assert unmatched_line["description_en"] == "Water tank"
    assert unmatched_line["description_en_source"] == "ai"

    # A MATCHED line's own description is never surfaced here - ruling 5 of the 3 Sep
    # batch says the product master name covers it, not this screen.
    assert all(
        ln["description"] is None for ln in block1["lines"] if ln["matched"]
    )

    note_texts = {n["text"] for n in block1["notes"]}
    assert "840 水箱空瓷：1个 （ 外箱贴: 空瓷）" in note_texts
    footer_item = next(
        f for f in preview["files"] if f["kind"] == "packing_list"
    )["footer_note"]
    assert footer_item is not None
    assert footer_item["text"].startswith("备注：")


def test_an_edited_cell_writes_manual_and_the_next_preview_reads_it_back(db, monkeypatch):
    _seed_aliases(db)
    w = World(db)
    _configure_ai(db)
    _stub_provider(monkeypatch, {"水箱": "Water tank"})

    first = svc.preview(db, [("装箱单.xls", _pl_bytes())], supplier_id=str(w.supplier.id))
    db.commit()
    line = next(
        ln for ln in _pl_block1(first)["lines"] if ln["item_code"] == "SRTWCY8840"
    )
    assert line["description_en_source"] == "ai"

    # The operator corrects the AI's guess in the preview - `apply`'s own
    # `translations` payload is what writes this, tested end to end in
    # `test_supplier_document_service.py`; this proves the memory side of the
    # round trip on its own.
    tsvc.remember(db, [{"source_text": "水箱", "target_text": "Water storage tank"}])
    db.commit()

    fake = _stub_provider(monkeypatch, {})  # the model must not be asked again
    second = svc.preview(db, [("装箱单.xls", _pl_bytes())], supplier_id=str(w.supplier.id))
    line2 = next(
        ln for ln in _pl_block1(second)["lines"] if ln["item_code"] == "SRTWCY8840"
    )
    assert line2["description_en"] == "Water storage tank"
    assert line2["description_en_source"] == "manual"
    assert fake.calls == []
