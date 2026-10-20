"""CHAT-CODE-LOOKUP gate ON x #1755 R5-1 / R5-2 (the ad0bff3167 merge resolution).

R5-2: a code that only holds the typed word reads `code X (name), holding "W"`; R5-1: a size
word's keys follow the data, the held family first. Both must survive the CODE LOOKUP gate
(`code_lookup=True`): the plain labelled path, the set-merged `_ranked` path, the engine call.
Synthetic ZZ codes, Postgres throwaway only."""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401  isort:skip
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.head import candidates
from app.services.chatbot.user_turn import UserTurn
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from tests._pg_fixture import blank_session, unique_code


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _mk(db, codes, specs=None) -> dict[str, str]:
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT cat", class_label="Water Closet",
        company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    db.add_all([cat, uom])
    db.flush()
    ids = {}
    for code in codes:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name of {code}", category_id=cat.id,
            base_uom_id=uom.id, list_price=1, company_id=DEFAULT_COMPANY_ID, is_searchable=True,
        )
        db.add(p)
        db.flush()
        ids[code] = p.id
        if specs and code in specs:
            db.add(ProductSpecifications(
                id=str(uuid.uuid4()), product_id=p.id, values={k: {"value": v} for k, v in specs[code].items()},
            ))
    db.flush()
    return ids


def _mk_set(db, code, member_ids, name) -> None:
    s = ProductSet(id=str(uuid.uuid4()), set_code=code, name=name, company_id=DEFAULT_COMPANY_ID, is_active=True)
    db.add(s)
    db.flush()
    for n, pid in enumerate(member_ids):
        db.add(ProductSetMember(id=str(uuid.uuid4()), product_set_id=s.id, product_id=pid, quantity=1, sort_order=n))
    db.flush()


def _entry(entries, gram):
    return next(e for e in entries if e.gram == gram)


def _item(entry, code):
    return next(i for i in entry.items if f" {code} " in f"{i} " or f" {code}(" in i)


def test_gate_on_a_code_that_only_holds_the_word_says_holding(db):
    _mk(db, ["ZZHOLD7788-A", "ZZEXACT5566", "ZZEXACT5566-B"])

    held = _entry(candidates.shortlist(db, "stock zzhold7788", code_lookup=True), "zzhold7788")
    both = _entry(candidates.shortlist(db, "stock zzexact5566", code_lookup=True), "zzexact5566")

    assert _item(held, "ZZHOLD7788-A") == 'code ZZHOLD7788-A (Name of ZZHOLD7788-A), holding "zzhold7788"'
    assert 'holding "zzexact5566"' in _item(both, "ZZEXACT5566-B")
    assert "holding" not in _item(both, "ZZEXACT5566")


def test_gate_on_set_merged_path_labels_holding(db):
    ids = _mk(db, ["ZZMRG3344", "ZZMRG3344-A", "ZZPEDA-ALPHA1", "ZZCIST-BETA2"])
    _mk_set(db, "ZZMRG3344-SET", [ids["ZZPEDA-ALPHA1"], ids["ZZCIST-BETA2"]], "Merge set")

    entry = _entry(candidates.shortlist(db, "stock zzmrg3344", code_lookup=True), "zzmrg3344")

    assert _item(entry, "ZZMRG3344-SET").startswith("set code ZZMRG3344-SET (Merge set)")
    assert _item(entry, "ZZMRG3344-A") == 'code ZZMRG3344-A (Name of ZZMRG3344-A), holding "zzmrg3344"'
    assert "holding" not in _item(entry, "ZZMRG3344")


def test_gate_on_near_code_line_is_unchanged(db):
    _mk(db, ["ZZNEAR90210-X"])

    entry = _entry(candidates.shortlist(db, "stock zznear90211-x", code_lookup=True), "zznear90211-x")

    line = _item(entry, "ZZNEAR90210-X")
    assert line.startswith("near code ZZNEAR90210-X (Name of ZZNEAR90210-X)"), entry.items
    assert "holding" not in line


def test_gate_on_listed_codes_and_pick_info_ignore_the_holding_suffix(db):
    _mk(db, ["ZZLIST4455", "ZZLIST4455-A"])

    entries = candidates.shortlist(db, "stock zzlist4455", code_lookup=True)

    assert 'holding "zzlist4455"' in _item(_entry(entries, "zzlist4455"), "ZZLIST4455-A")
    assert candidates.listed_codes(entries) == frozenset({"zzlist4455", "zzlist4455a"})
    info = candidates.pick_info(entries)["zzlist4455"]
    assert set(info["scores"]) == {"zzlist4455", "zzlist4455a"}
    assert sorted(info["holds"]) == ["zzlist4455", "zzlist4455a"]


MM_KEYS = ("board_thickness", "depth", "diameter", "dim_height", "dim_length", "dim_width", "trap_length")


def test_gate_on_candidate_lines_passes_held_ids_to_the_size_keys(db):
    for key in MM_KEYS:
        db.add(ProductSpecRegistry(id=str(uuid.uuid4()), spec_key=key, label=key.title(), data_type="numeric", unit="mm"))
    ids = _mk(
        db, ["ZZWC560-SH-UF", "ZZWC560-LF", "ZZWC701", "ZZWC702", "ZZWC703"],
        {
            "ZZWC560-SH-UF": {"trap_length": 120}, "ZZWC560-LF": {"trap_length": 150},
            "ZZWC701": {"dim_length": 150}, "ZZWC702": {"dim_length": 150}, "ZZWC703": {"dim_length": 150},
        },
    )

    lines, listed, info = engine_mod._candidate_lines(
        db, UserTurn(own_text="150mm zzwc701"), [ids["ZZWC560-SH-UF"]], code_lookup=True
    )

    size = next(ln for ln in lines if ln.startswith('- "150mm"'))
    assert size.startswith('- "150mm": spec trap_length = 150'), size
    assert any(ln.startswith('- "zzwc701": ') and "code ZZWC701 (" in ln for ln in lines), lines
    assert "zzwc701" in listed and "zzwc701" in info
