"""CHAT-CLOSED-LISTS FILTER-OVER-HELD (CHAT-STATE r2 handoff, crew decision 18 Oct; TRAIN shapes,
synthetic codes).

CHAT-STATE card R1: a refine with a fragment (a spec, a size, a brand) keeps the held subject and
narrows it on that one axis. `narrow_held_family` skipped numeric values and brands, and when no
held member had the value it gave no answer, so the turn took the resolver's catalogue set (the
grader's `subject` check, cp0-fcd44fe521). Crew ruling (a): "held, none match" says so plainly
(owner CP0: say plainly what is not on record; a silent widen fails).
"""
from __future__ import annotations

import uuid

import app.main  # noqa: F401  isort:skip
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_spec_over_held import _fetched, _stock_ask, _turns
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

ROWS = (
    # code, parent, trap, width (mm), brand
    ("ZZTBS500", None, "s_trap", 500, "ZZB1"),
    ("ZZTBS500-60", "ZZTBS500", "s_trap", 600, "ZZB1"),
    ("ZZTBS500-60M", "ZZTBS500", "s_trap", 600, "ZZB2"),
    ("ZZTBS777", None, "p_trap", 600, "ZZB2"),  # outside the held family: never in the answer
)


def _seed(session_factory) -> dict[str, str]:
    db = session_factory()
    db.add_all([
        ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key="trap_type", label="Trap", data_type="enum",
            allowed_values=["s_trap", "p_trap"], synonyms={"p_trap": ["p trap"], "s_trap": ["s trap"]},
        ),
        ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="dim_width", label="Width", data_type="numeric", unit="mm"),
    ])
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("BS")[:50], category_name="ZZT Basin", class_label="Wash Basin",
        company_id=DEFAULT_COMPANY_ID,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=DEFAULT_COMPANY_ID)
    brands = {
        code: Brand(id=str(uuid.uuid4()), brand_code=unique_code(code)[:50], brand_name=f"{code} Brand", company_id=DEFAULT_COMPANY_ID)
        for code in ("ZZB1", "ZZB2")
    }
    db.add_all([cat, uom, *brands.values()])
    db.flush()
    ids: dict[str, str] = {"brand:" + code: b.brand_name for code, b in brands.items()}
    for code, parent, trap, width, brand in ROWS:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name {code}", category_id=cat.id, base_uom_id=uom.id,
            list_price=1, company_id=DEFAULT_COMPANY_ID, variant_of_id=ids.get(parent) if parent else None,
            brand_id=brands[brand].id,
        )
        db.add(p)
        db.flush()
        ids[code] = p.id
        db.add(ProductSpecifications(
            id=str(uuid.uuid4()), product_id=p.id,
            values={"class": {"value": "Wash Basin"}, "trap_type": {"value": trap}, "dim_width": {"value": width}},
        ))
    db.commit()
    return ids


HELD = {"raw": "ZZTBS500", "hint": "product", "canonical_code": "ZZTBS500", "current_message": True, "confident": True}


def _spec(raw: str, key: str, value) -> dict:
    return {"raw": raw, "hint": "specification", "canonical_code": None, "spec_key": key, "spec_value": value,
            "current_message": True, "confident": True}


def _refine(session_factory, stub_access, monkeypatch, text: str, *entities: dict):
    (_r1, _c1), (r2, c2) = _turns(
        session_factory, stub_access, monkeypatch, [("ZZTBS500", _stock_ask(HELD)), (text, _stock_ask(*entities))], gate=True,
    )
    return r2, c2


def test_a_numeric_size_over_the_held_product_narrows_its_family(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    r, calls = _refine(session_factory, stub_access, monkeypatch, "600mm?", _spec("600mm", "dim_width", 600))

    assert _fetched(calls) == sorted([ids["ZZTBS500-60"], ids["ZZTBS500-60M"]]), ((r.reply or {}).get("text"), calls)


def test_a_brand_over_the_held_product_narrows_its_family(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)
    brand = {"raw": "ZZB2", "hint": "brand", "canonical_code": ids["brand:ZZB2"], "current_message": True, "confident": True}

    r, calls = _refine(session_factory, stub_access, monkeypatch, "zzb2 one?", brand, _spec("600mm", "dim_width", 600))

    assert _fetched(calls) == [ids["ZZTBS500-60M"]], ((r.reply or {}).get("text"), calls)


def test_held_none_match_says_so_and_never_widens_to_the_catalogue(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    r, calls = _refine(session_factory, stub_access, monkeypatch, "p trap?", _spec("p trap", "trap_type", "p_trap"))

    assert ids["ZZTBS777"] not in _fetched(calls), calls
    text = (r.reply or {}).get("text") or ""
    assert "ZZTBS500" in text and "p trap" in text.lower(), text
