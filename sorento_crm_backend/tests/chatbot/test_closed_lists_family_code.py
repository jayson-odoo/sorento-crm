"""C2 FAMILY-BY-FAMILY-CODE (crew PRIORITY 19 Oct; the real data shape, synthetic codes).

Held-family narrowing read a family only from `variant_of_id`, which real products do not carry
(2 of 15,439 on the dev copy); what they carry is `family_code`, derived from the product code by
the ORM listener. Rule: a held product's family is the searchable products of the SAME company with
the SAME non-null family_code, plus the existing variant graph. "none on record" is said only when
no member of that family carries every named value (C1 safety).

Fixtures are in the real shape: variant_of_id NULL everywhere, family_code from the listener
(ZZWC286), trap_type s_trap / p_trap in product_specifications.values.
"""
from __future__ import annotations

import uuid

import app.main  # noqa: F401  isort:skip
from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import session_factory  # noqa: F401
from tests.chatbot.test_closed_lists_spec_over_held import _fetched, _stock_ask, _turns
from tests.chatbot.test_engine import seeded, stub_access  # noqa: F401

OTHER_COMPANY = "00000000-0000-0000-0000-000000000002"

ROWS = (
    # code, trap, brand
    ("ZZWC286-UF", "s_trap", "ZZB1"),  # the held product: no other code starts with it, so only itself is held
    ("ZZWC286-SH", "s_trap", "ZZB1"),
    ("ZZWC286-SH-P", "p_trap", "ZZB1"),
    ("ZZWC286-SH-NEW-P", "p_trap", "ZZB1"),
    ("ZZWC286-SH-150", "s_trap", "ZZB1"),
    ("ZZWC900-P", "p_trap", "ZZB2"),  # another family: never offered for the held family
)


def _seed(session_factory, *, unsearchable: tuple[str, ...] = (), manual_null: tuple[str, ...] = (), other_company: bool = False) -> dict[str, str]:
    db = session_factory()
    db.add_all([
        ProductSpecRegistry(
            id=str(uuid.uuid4()), spec_key="trap_type", label="Trap", data_type="enum",
            allowed_values=["s_trap", "p_trap"], synonyms={"p_trap": ["p trap"], "s_trap": ["s trap"]},
        ),
        ProductSpecRegistry(id=str(uuid.uuid4()), spec_key="dim_width", label="Width", data_type="numeric", unit="mm"),
    ])
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("WC")[:50], category_name="ZZT WC", class_label="Water Closet",
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

    def add(code, trap, brand, *, category, base_uom, company_id, **flags) -> None:
        p = Product(
            id=str(uuid.uuid4()), product_code=code, product_name=f"Name {code}", category_id=category.id,
            base_uom_id=base_uom.id, list_price=1, company_id=company_id, brand_id=brand.id if brand else None, **flags,
        )
        db.add(p)
        db.flush()
        ids[code] = p.id
        db.add(ProductSpecifications(
            id=str(uuid.uuid4()), product_id=p.id,
            values={"class": {"value": "Water Closet"}, "trap_type": {"value": trap}, "dim_width": {"value": 600}},
        ))

    for code, trap, brand in ROWS:
        flags: dict = {}
        if code in unsearchable:
            flags["is_searchable"] = False
        if code in manual_null:
            flags["family_code_manual"] = True
            flags["family_code"] = None
        add(code, trap, brands[brand], category=cat, base_uom=uom, company_id=DEFAULT_COMPANY_ID, **flags)
    if other_company:
        db.add(Company(id=OTHER_COMPANY, name="Other", code=unique_code("OTH")[:20]))
        db.flush()
        ocat = ProductCategory(
            id=str(uuid.uuid4()), category_code=unique_code("WC")[:50], category_name="ZZT WC O", class_label="Water Closet",
            company_id=OTHER_COMPANY,
        )
        ouom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each", company_id=OTHER_COMPANY)
        db.add_all([ocat, ouom])
        db.flush()
        add("ZZWC286-SH-OT", "p_trap", None, category=ocat, base_uom=ouom, company_id=OTHER_COMPANY)
    db.commit()
    return ids


HELD = {"raw": "ZZWC286-UF", "hint": "product", "canonical_code": "ZZWC286-UF", "current_message": True, "confident": True}


def _spec(raw: str, key: str, value) -> dict:
    return {"raw": raw, "hint": "specification", "canonical_code": None, "spec_key": key, "spec_value": value,
            "current_message": True, "confident": True}


def _refine(session_factory, stub_access, monkeypatch, text: str, *entities: dict):
    (_r1, _c1), (r2, c2) = _turns(
        session_factory, stub_access, monkeypatch, [("ZZWC286-UF", _stock_ask(HELD)), (text, _stock_ask(*entities))], gate=True,
    )
    return r2, c2


def _text(r) -> str:
    return (r.reply or {}).get("text") or ""



P_TRAP = _spec("p trap", "trap_type", "p_trap")


def test_a_spec_over_the_held_product_narrows_its_family_code_siblings(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    r, calls = _refine(session_factory, stub_access, monkeypatch, "p trap?", P_TRAP)

    assert _fetched(calls) == sorted([ids["ZZWC286-SH-P"], ids["ZZWC286-SH-NEW-P"]]), (_text(r), calls)
    assert "none on record" not in _text(r), _text(r)


def test_a_brand_over_the_held_product_keeps_the_family_codes_members_of_that_brand(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)
    brand = {"raw": "ZZB1", "hint": "brand", "canonical_code": ids["brand:ZZB1"], "current_message": True, "confident": True}

    r, calls = _refine(session_factory, stub_access, monkeypatch, "zzb1 one?", brand, _spec("600mm", "dim_width", 600))

    assert _fetched(calls) == sorted(ids[c] for c in ("ZZWC286-UF", "ZZWC286-SH", "ZZWC286-SH-P", "ZZWC286-SH-NEW-P", "ZZWC286-SH-150")), (_text(r), calls)


def test_guard_the_same_family_code_in_another_company_never_joins_the_family(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, other_company=True)

    r, calls = _refine(session_factory, stub_access, monkeypatch, "p trap?", P_TRAP)

    assert ids["ZZWC286-SH-OT"] not in _fetched(calls), (_text(r), calls)


def test_guard_a_non_searchable_family_member_is_never_offered(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, unsearchable=("ZZWC286-SH-NEW-P",))

    r, calls = _refine(session_factory, stub_access, monkeypatch, "p trap?", P_TRAP)

    assert ids["ZZWC286-SH-NEW-P"] not in _fetched(calls), (_text(r), calls)


def test_guard_a_held_product_with_no_family_code_has_only_itself_as_family(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory, manual_null=("ZZWC286-UF",))

    r, calls = _refine(session_factory, stub_access, monkeypatch, "p trap?", P_TRAP)

    assert not {ids["ZZWC286-SH-P"], ids["ZZWC286-SH-NEW-P"]} & set(_fetched(calls)), calls
    assert "ZZWC286-UF" in _text(r) and "p trap" in _text(r).lower(), _text(r)


def test_guard_a_value_no_family_member_carries_still_gets_the_plain_none_line(session_factory, seeded, stub_access, monkeypatch):
    ids = _seed(session_factory)

    r, calls = _refine(session_factory, stub_access, monkeypatch, "900mm?", _spec("900mm", "dim_width", 900))

    assert set(_fetched(calls)) <= {ids["ZZWC286-UF"]}, calls
    assert "ZZWC286-UF" in _text(r) and "900" in _text(r), _text(r)
