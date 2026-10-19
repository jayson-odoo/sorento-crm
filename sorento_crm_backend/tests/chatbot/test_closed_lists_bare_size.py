"""R6-1 BARE-SIZE-BY-DATA (SIZE-WRONG-KEY; crew rulings a21061914 (a), a22659272; ZZ data).

Owner rule: a BARE size (no dimension named) matches width OR length; a named dimension stays strict;
a WC's 200 / 300 is its trap length. All data, no key or class list in code: registry column
`matches_bare_size` (true for dim_width, dim_length) and trap_length.applies_when {"class": [<WC class>]}.

Seeding: the column is added by the coder's migration; the fixture here adds it with
`ADD COLUMN IF NOT EXISTS` on the test schema and sets it with raw SQL, so these tests do not depend on the
ORM model carrying it yet (a no-op once the column exists). The parser picks the reserved spec_key "size"
for a size given alone; a named dimension picks its own key.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

import app.main  # noqa: F401  isort:skip
from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_spec_over_held import _fetched, _stock_ask, _turns
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

BASIN, WC = "ZZ Wash Basin", "ZZ Water Closet"


def _registry(db, *, wc_scoped: bool = True) -> None:
    db.add_all([
        ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key="class", label="Class", data_type="enum", allowed_values=[],
            synonyms={BASIN: ["zzbasin"], WC: ["zzwc"]},
        ),
        *[
            ProductSpecRegistry(
                id=str(uuid.uuid4()), spec_key=key, label=label, data_type="numeric", unit="mm",
                synonyms={"_self": words}, applies_when=({"class": [WC]} if (key == "trap_length" and wc_scoped) else {}),
            )
            for key, label, words in (
                ("dim_width", "Width", ["width", "wide"]), ("dim_length", "Length", ["length", "long"]),
                ("dim_height", "Height", ["height", "tall"]), ("trap_length", "Trap outlet length", ["trap"]),
            )
        ],
    ])
    db.flush()
    db.execute(text("ALTER TABLE product_spec_registry ADD COLUMN IF NOT EXISTS matches_bare_size boolean NOT NULL DEFAULT false"))
    db.execute(text("UPDATE product_spec_registry SET matches_bare_size = true WHERE spec_key IN ('dim_width', 'dim_length')"))


def _seed(session_factory, rows, *, wc_scoped: bool = True) -> dict[str, str]:
    """rows: (code, class label, {key: JSON number}). family_code from the ORM listener, variant_of_id NULL."""
    db = session_factory()
    _registry(db, wc_scoped=wc_scoped)
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    cats = {
        label: ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code("C")[:50], category_name=label, class_label=label,
            company_id=DEFAULT_COMPANY_ID,
        )
        for label in {c for _code, c, _v in rows}
    }
    db.add_all([uom, *cats.values()])
    db.flush()
    wh = Warehouse(id=str(uuid.uuid4()), warehouse_code=unique_code("WH")[:20], warehouse_name="ZZT WH", company_id=DEFAULT_COMPANY_ID)
    db.add(wh)
    db.flush()
    ids: dict[str, str] = {}
    for code, label, values in rows:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name {code}", category_id=cats[label].id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID,
        )
        db.add(p)
        db.flush()
        ids[code] = p.id
        db.add(Stock(id=str(uuid.uuid4()), product_id=p.id, warehouse_id=wh.id, quantity_on_hand=5, company_id=DEFAULT_COMPANY_ID))
        db.add(ProductSpecifications(
            id=str(uuid.uuid4()), product_id=p.id,
            values={"class": {"value": label}, **{k: {"value": v} for k, v in values.items()}},
        ))
    db.commit()
    return ids


def _ent(raw: str, hint: str, **kw) -> dict:
    return {"raw": raw, "hint": hint, "canonical_code": None, "current_message": True, "confident": True, **kw}


def _spec(raw: str, key: str, value) -> dict:
    return _ent(raw, "specification", spec_key=key, spec_value=value)


def _ask(session_factory, stub_access, monkeypatch, text_: str, *entities: dict, held=None):
    turns = [(text_, _stock_ask(*entities))]
    if held:
        turns.insert(0, ("the held ones", _stock_ask(*[_ent(c, "product", canonical_code=c) for c in held])))
    out = _turns(session_factory, stub_access, monkeypatch, turns, gate=True)
    return out[-1]


BASINS = (
    ("ZZBS-W", BASIN, {"dim_width": 600, "dim_length": 450}),
    ("ZZBS-L", BASIN, {"dim_length": 600, "dim_width": 400}),
    ("ZZBS-H", BASIN, {"dim_height": 600}),
)
WCS = (
    ("ZZWC-T", WC, {"trap_length": 300, "dim_width": 400}),
    ("ZZWC-W", WC, {"dim_width": 300, "trap_length": 150}),
)


def test_a_bare_size_matches_width_or_length_never_height(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, BASINS)

    r, calls = _ask(session_factory, stub_access, monkeypatch, "need a 600mm zzbasin", _ent("zzbasin", "category"), _spec("600mm", "size", 600))

    assert _fetched(calls) == sorted([ids["ZZBS-W"], ids["ZZBS-L"]]), (r.reply, calls)


def test_guard_a_named_dimension_stays_strict(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, BASINS)

    r, calls = _ask(session_factory, stub_access, monkeypatch, "600mm wide zzbasin", _ent("zzbasin", "category"), _spec("600mm wide", "dim_width", 600))

    assert _fetched(calls) == [ids["ZZBS-W"]], (r.reply, calls)


def test_a_bare_size_on_a_class_that_scopes_a_key_reads_that_key(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, WCS)

    r, calls = _ask(session_factory, stub_access, monkeypatch, "any 300mm zzwc", _ent("zzwc", "category"), _spec("300mm", "size", 300))

    assert _fetched(calls) == [ids["ZZWC-T"]], (r.reply, calls)


def test_kill_control_without_the_registry_scope_the_pair_applies(session_factory, seeded, stub_access, monkeypatch):
    """The registry row decides, never the key's name: trap_length with applies_when {} is no class key."""
    ids = _seed(session_factory, WCS, wc_scoped=False)

    r, calls = _ask(session_factory, stub_access, monkeypatch, "any 300mm zzwc", _ent("zzwc", "category"), _spec("300mm", "size", 300))

    assert _fetched(calls) == [ids["ZZWC-W"]], (r.reply, calls)


def test_a_held_basin_family_with_a_bare_size_narrows_by_width_or_length(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, (
        ("ZZBF1-A", BASIN, {"dim_width": 500, "dim_length": 400}),
        ("ZZBF1-B", BASIN, {"dim_length": 600}),
        ("ZZBF1-C", BASIN, {"dim_width": 600}),
        ("ZZBF1-D", BASIN, {"dim_height": 600}),
    ))

    r, calls = _ask(session_factory, stub_access, monkeypatch, "600mm one pls", _spec("600mm", "size", 600), held=["ZZBF1-A"])

    assert _fetched(calls) == sorted([ids["ZZBF1-B"], ids["ZZBF1-C"]]), (r.reply, calls)


def test_a_held_wc_with_a_bare_size_reads_its_class_key(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, (
        ("ZZWF2-A", WC, {"trap_length": 150}),
        ("ZZWF2-B", WC, {"trap_length": 300}),
        ("ZZWF2-C", WC, {"dim_width": 300}),
    ))

    r, calls = _ask(session_factory, stub_access, monkeypatch, "300mm?", _spec("300mm", "size", 300), held=["ZZWF2-A"])

    assert _fetched(calls) == [ids["ZZWF2-B"]], (r.reply, calls)


def test_q3_a_named_length_no_wc_holds_falls_to_the_class_key_that_shares_its_phrase(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, (
        ("ZZWQ-A", WC, {"trap_length": 200}),
        ("ZZWQ-B", WC, {"trap_length": 200}),
        ("ZZWQ-C", WC, {"trap_length": 300}),
    ))

    r, calls = _ask(session_factory, stub_access, monkeypatch, "length 200mm zzwc", _ent("zzwc", "category"), _spec("length 200mm", "dim_length", 200))

    assert _fetched(calls) == sorted([ids["ZZWQ-A"], ids["ZZWQ-B"]]), (r.reply, calls)


def test_guard_q3_a_named_length_some_wc_holds_stays_strict(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, (
        ("ZZWQ-A", WC, {"trap_length": 200}),
        ("ZZWQ-D", WC, {"dim_length": 200}),
    ))

    r, calls = _ask(session_factory, stub_access, monkeypatch, "length 200mm zzwc", _ent("zzwc", "category"), _spec("length 200mm", "dim_length", 200))

    assert _fetched(calls) == [ids["ZZWQ-D"]], (r.reply, calls)


def test_the_candidate_line_offers_the_bare_size_first(session_factory, seeded):
    from app.models.base import set_company_scope
    from app.services.chatbot.head import candidates

    _seed(session_factory, BASINS)
    db = session_factory()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    lines = candidates.candidate_lines(candidates.shortlist(db, "need a 600mm zzbasin"))

    line = next(ln for ln in lines if ln.startswith('- "600mm"'))
    assert line.startswith('- "600mm": size 600 mm (no dimension named); spec '), lines


# --- R6-5 S2: a contact that hides dim_width ----------------------------------------------------


def test_a_hidden_dim_width_leaves_dim_length_alone_in_the_bare_size_or(session_factory, seeded, stub_access, monkeypatch):
    """The hidden-key drop compared the entry key ("size" / "any:...") only, so a hidden dimension
    stayed a leg of the OR and the contact saw a product that matches only through it."""
    from app.services import spec_visibility

    ids = _seed(session_factory, BASINS)
    real = spec_visibility.hidden_keys
    monkeypatch.setattr(spec_visibility, "hidden_keys", lambda policy, registry_keys: real(policy, registry_keys) | frozenset({"dim_width"}))

    r, calls = _ask(session_factory, stub_access, monkeypatch, "need a 600mm zzbasin", _ent("zzbasin", "category"), _spec("600mm", "size", 600))

    assert ids["ZZBS-W"] not in _fetched(calls), (r.reply, calls)
    assert _fetched(calls) == [ids["ZZBS-L"]], (r.reply, calls)


# --- R6-5 N3: a bare-size miss line carries the unit --------------------------------------------


def test_a_bare_size_miss_line_carries_the_unit(session_factory, seeded, stub_access, monkeypatch):
    """"700 zz wash basins" said no unit; the any-key set's unit comes from its members."""
    _seed(session_factory, BASINS)

    r, calls = _ask(session_factory, stub_access, monkeypatch, "need a 700mm zzbasin", _ent("zzbasin", "category"), _spec("700mm", "size", 700))

    text_ = (r.reply or {}).get("text") or ""
    assert "700" in text_, text_
    assert "700 mm" in text_, text_
