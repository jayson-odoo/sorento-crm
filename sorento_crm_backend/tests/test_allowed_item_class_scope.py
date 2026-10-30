"""TAG-BRAND-CLASS: a contact's ALLOWED item classes, one flat list under Brands (RED first).

PLAN: documentation/plans/contacts/PLAN-tag-brand-class-30oct.md (owner answers 30 Oct: Q1 (b)
an allow list that also works with All brands on, Q2 (a) one flat list reaching brandless
products too, Q3 (b) the per-brand picker of #1972 is retired).

`respond_contacts.allowed_item_class_codes` holds upper-cased class CODES (one option per code
across companies); `__NONE__` stands for "No class". NULL or [] = every class. The rule stays in
`contact_brand_scope.brand_predicate` and its Python twin; the scope is still a frozenset of
strings: a brand id per allowed brand, `class:<CODE>` per allowed class.

This replaces tests/test_item_class_scope.py (the per-brand `brand_class_ids` behaviour, retired).

World: tests/_brand_scope_seed.py (MOCHA and SORENTO brands, one product each plus an unbranded
one, default company) + classes SERENE and DIY + a SORENTO SERENE product and a SORENTO DIY
product + a second company (brandless, like Mocha) with a no-class product and a DIY product
(its own DIY row: same code, other company).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.product import Product
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._brand_scope_seed import branded_product, contact, db, world  # noqa: F401
from tests._mc_lookup_seed import product
from tests._pg_fixture import unique_code

NONE = "__NONE__"


def _svc():
    from app.services import contact_brand_scope

    return contact_brand_scope


def _item_class(db, code: str, company_id: str = DEFAULT_COMPANY_ID, name: str | None = None):
    from app.models.product import ItemClass

    row = ItemClass(
        id=str(uuid.uuid4()),
        item_class_code=code,
        item_class_name=name or f"ZZT {code}",
        company_id=company_id,
    )
    db.add(row)
    db.flush()
    return row


class ClassWorld:
    def __init__(self, db, world) -> None:
        from app.models.company import Company

        self.w = world
        # Codes unique per test run so parallel tests never share a class code.
        self.SERENE = unique_code("SERENE", alpha=True).upper()[:50]
        self.DIY = unique_code("DIY", alpha=True).upper()[:50]
        self.serene = _item_class(db, self.SERENE)
        self.diy = _item_class(db, self.DIY)
        self.p_serene = branded_product(db, unique_code("SER", alpha=True), world.sorento)
        self.p_serene.item_class_id = self.serene.id
        self.p_diy = branded_product(db, unique_code("DIY", alpha=True), world.sorento)
        self.p_diy.item_class_id = self.diy.id
        # A brandless second company, like Mocha.
        self.mch = str(uuid.uuid4())
        db.add(Company(id=self.mch, name="ZZT TBC Mocha", code=unique_code("TBC")[:20]))
        db.flush()
        self.mch_diy_class = _item_class(db, self.DIY, company_id=self.mch)
        self.p_mch_plain = product(db, company_id=self.mch, code=unique_code("MPL", alpha=True))
        self.p_mch_diy = product(db, company_id=self.mch, code=unique_code("MDY", alpha=True))
        self.p_mch_diy.item_class_id = self.mch_diy_class.id
        db.flush()
        self.codes = {
            "mocha": world.p_mocha.product_code,
            "sorento_noclass": world.p_sorento.product_code,
            "null_brand": world.p_null.product_code,
            "serene": self.p_serene.product_code,
            "diy": self.p_diy.product_code,
            "mch_plain": self.p_mch_plain.product_code,
            "mch_diy": self.p_mch_diy.product_code,
        }
        db.commit()

    def contact(self, db, brand_ids=None, classes=None, companies=None):
        c = contact(
            db,
            brand_ids=[str(b) for b in brand_ids] if brand_ids else None,
            companies=companies or [DEFAULT_COMPANY_ID, self.mch],
        )
        if classes is not None:
            db.execute(
                text("UPDATE respond_contacts SET allowed_item_class_codes = :c WHERE id = :i"),
                {"c": list(classes), "i": c.id},
            )
        db.commit()
        return c


@pytest.fixture
def cw(db, world) -> ClassWorld:
    from app.models.base import set_company_scope

    out = ClassWorld(db, world)
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, out.mch}))
    return out


def _visible(db, cw) -> set[str]:
    rows = db.query(Product.product_code).filter(Product.product_code.in_(list(cw.codes.values()))).all()
    by_code = {v: k for k, v in cw.codes.items()}
    return {by_code[r[0]] for r in rows}


def _stamp(db, scope) -> None:
    from app.models.base import set_brand_scope

    set_brand_scope(db, scope)


ALL = {"mocha", "sorento_noclass", "null_brand", "serene", "diy", "mch_plain", "mch_diy"}


# --------------------------------------------------------------------- storage


def test_allowed_item_class_codes_column_exists_and_defaults_to_null(db, cw) -> None:
    row = db.execute(
        text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'respond_contacts' "
            "AND column_name = 'allowed_item_class_codes'"
        )
    ).one_or_none()
    assert row is not None, "respond_contacts.allowed_item_class_codes does not exist"
    assert row[0] == "ARRAY" and row[1] == "YES", row
    assert db.execute(
        text("SELECT allowed_item_class_codes FROM respond_contacts WHERE id = :i"), {"i": cw.w.unscoped.id}
    ).scalar() is None


# --------------------------------------------------------------------- scope value


def test_no_brands_and_no_classes_is_unscoped(db, cw) -> None:
    """AC-4: deploy changes nobody."""
    assert _svc().contact_brand_scope(db, cw.contact(db).id) is None
    assert _svc().contact_brand_scope(db, cw.contact(db, classes=[]).id) is None


def test_brands_only_scope_is_exactly_the_brand_ids(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id, cw.w.mocha.id])
    assert _svc().contact_brand_scope(db, c.id) == frozenset({str(cw.w.sorento.id), str(cw.w.mocha.id)})


def test_all_brands_with_classes_is_scoped(db, cw) -> None:
    c = cw.contact(db, None, [NONE, cw.DIY])
    assert _svc().contact_brand_scope(db, c.id) == frozenset({f"class:{NONE}", f"class:{cw.DIY}"})


def test_stale_brand_class_ids_is_ignored(db, cw) -> None:
    """AC-12: the retired #1972 column is never read."""
    c = cw.contact(db, [cw.w.sorento.id])
    db.execute(
        text("UPDATE respond_contacts SET brand_class_ids = CAST(:m AS jsonb) WHERE id = :i"),
        {"m": f'{{"{cw.w.sorento.id}": ["{cw.serene.id}"]}}', "i": c.id},
    )
    db.commit()
    assert _svc().contact_brand_scope(db, c.id) == frozenset({str(cw.w.sorento.id)})


# --------------------------------------------------------------------- the session criterion


def test_the_serene_case_all_brands_no_class_and_diy(db, cw) -> None:
    """AC-1 the owner's case: All brands, allowed "No class, DIY" -> no SERENE anywhere."""
    c = cw.contact(db, None, [NONE, cw.DIY])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == ALL - {"serene"}


def test_a_class_added_later_is_hidden_until_ticked(db, cw) -> None:
    """AC-2."""
    new = _item_class(db, unique_code("NEWCLS", alpha=True).upper()[:50])
    p_new = branded_product(db, unique_code("NEW", alpha=True), cw.w.sorento)
    p_new.item_class_id = new.id
    db.commit()
    c = cw.contact(db, None, [NONE, cw.DIY])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert db.query(Product.id).filter(Product.id == p_new.id).first() is None


def test_without_no_class_the_unclassed_products_are_hidden(db, cw) -> None:
    c = cw.contact(db, None, [cw.DIY])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"diy", "mch_diy"}


def test_one_code_covers_both_companies(db, cw) -> None:
    """AC-5: DIY is one option; the brandless company's DIY row passes too."""
    c = cw.contact(db, None, [cw.DIY])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert "mch_diy" in _visible(db, cw)


def test_codes_match_case_insensitively(db, cw) -> None:
    c = cw.contact(db, None, [cw.DIY.lower()])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"diy", "mch_diy"}


def test_brands_and_classes_stack(db, cw) -> None:
    """AC-3: SORENTO + DIY -> only SORENTO DIY in the restricted company; the brandless company
    is not restricted by the brand rule but the class rule still applies."""
    c = cw.contact(db, [cw.w.sorento.id], [cw.DIY])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"diy", "mch_diy"}


def test_brands_only_keeps_every_class(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"sorento_noclass", "serene", "diy", "mch_plain", "mch_diy"}


def test_scope_survives_a_round_trip_through_a_sorted_list(db, cw) -> None:
    """RQ export jobs carry the scope as `sorted(scope)` and rebuild a frozenset of strings."""
    c = cw.contact(db, None, [NONE, cw.DIY])
    scope = _svc().contact_brand_scope(db, c.id)
    _stamp(db, frozenset(str(b) for b in sorted(scope)))
    assert _visible(db, cw) == ALL - {"serene"}


def test_project_forecast_is_denied_to_a_class_scoped_contact(db, cw) -> None:
    """A figure with no product dimension would include SERENE: denied, as for brand scope."""
    scope = _svc().contact_brand_scope(db, cw.contact(db, None, [NONE]).id)
    assert _svc().brand_scope_allows_tool("crm_project_forecast", scope) is False


# --------------------------------------------------------------------- output guards / line clauses


def test_out_of_scope_codes_honour_the_classes(db, cw) -> None:
    scope = _svc().contact_brand_scope(db, cw.contact(db, None, [NONE, cw.DIY]).id)
    assert _svc().out_of_scope_product_codes(db, scope, list(cw.codes.values())) == {cw.codes["serene"]}


def test_out_of_scope_ids_honour_the_classes(db, cw) -> None:
    scope = _svc().contact_brand_scope(db, cw.contact(db, None, [cw.DIY]).id)
    out = _svc().out_of_scope_product_ids(
        db, scope, [cw.p_serene.id, cw.p_diy.id, cw.w.p_sorento.id, cw.p_mch_diy.id]
    )
    assert out == {str(cw.p_serene.id), str(cw.w.p_sorento.id)}


def test_line_clauses_drop_serene_lines(db, cw) -> None:
    from sqlalchemy import select

    _stamp(db, _svc().contact_brand_scope(db, cw.contact(db, None, [NONE, cw.DIY]).id))
    products = Product.__table__
    clauses = _svc().product_in_scope_clauses(db, products.c.id)
    rows = db.execute(
        select(products.c.product_code).where(products.c.product_code.in_(list(cw.codes.values())), *clauses)
    ).all()
    assert cw.codes["serene"] not in {r[0] for r in rows}
    assert cw.codes["diy"] in {r[0] for r in rows}


def test_in_scope_product_codes_honour_the_classes(db, cw) -> None:
    _stamp(db, _svc().contact_brand_scope(db, cw.contact(db, None, [NONE, cw.DIY]).id))
    out = _svc().in_scope_product_codes(db, [cw.codes["serene"], cw.codes["diy"], cw.codes["mocha"]])
    assert out == {cw.codes["diy"], cw.codes["mocha"]}


# --------------------------------------------------------------------- the settings card


def test_settings_card_reads_the_allowed_codes_and_the_options(db, cw) -> None:
    c = cw.contact(db, None, [NONE, cw.DIY])
    out = _svc().get_contact_brands(db, c.id)
    assert out["brand_ids"] == []
    assert out["allowed_item_class_codes"] == [NONE, cw.DIY]
    assert "brand_class_ids" not in out
    options = out["item_class_options"]
    assert options[0] == {"code": NONE, "name": "No class"}
    codes = [o["code"] for o in options]
    assert codes.count(cw.DIY) == 1  # one option per code across companies
    assert cw.SERENE in codes


def test_settings_card_writes_codes_upper_cased_and_deduplicated(db, cw) -> None:
    c = cw.contact(db)
    out = _svc().set_contact_brands(db, c.id, [], [cw.DIY.lower(), NONE, cw.DIY])
    assert out["allowed_item_class_codes"] == [NONE, cw.DIY]
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == ALL - {"serene"}


def test_settings_card_empty_list_stores_null(db, cw) -> None:
    c = cw.contact(db, None, [cw.DIY])
    _svc().set_contact_brands(db, c.id, [], [])
    assert db.execute(
        text("SELECT allowed_item_class_codes FROM respond_contacts WHERE id = :i"), {"i": c.id}
    ).scalar() is None


def test_settings_card_brands_only_call_keeps_the_classes(db, cw) -> None:
    """Brand edits never drop the class list (it no longer hangs off a brand)."""
    c = cw.contact(db, None, [cw.DIY])
    out = _svc().set_contact_brands(db, c.id, [str(cw.w.sorento.id)])
    assert out["allowed_item_class_codes"] == [cw.DIY]


def test_settings_card_refuses_an_unknown_code(db, cw) -> None:
    from app.services.error_handler import AppException

    c = cw.contact(db)
    with pytest.raises(AppException) as err:
        _svc().set_contact_brands(db, c.id, [], ["ZZT-NO-SUCH-CLASS"])
    assert err.value.status_code == 422
