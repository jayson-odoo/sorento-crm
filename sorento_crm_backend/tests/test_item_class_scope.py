"""ITEM-CLASS: contact access by item class nested inside brand (RED first).

PLAN: documentation/plans/products/PLAN-item-class-29oct.md D5/D6 (owner answers 29 Oct:
Q2 (a) per-brand class lists, Q3 a brand with no class list keeps every product including the
ones with no class, a brand limited to some classes hides products with no class).

`respond_contacts.brand_class_ids` is `{brand_id: [item_class_id, ...]}`. A brand absent from the
map, or mapped to [], keeps every class (today's brand rule). A class list only narrows a brand
that is already in `brand_ids`; an entry for any other brand is ignored. The rule stays in ONE
place, `contact_brand_scope.brand_predicate` (and its Python twin for the output guards), and
the scope still travels as a frozenset of strings so every existing carrier (session stamp,
RQ job args, turn ctx) passes it through unchanged.

World (tests/_brand_scope_seed.py): MOCHA and SORENTO brands, one product each plus an
unbranded one, all in the default company. This file adds two classes (SERENE, DIY) and three
SORENTO products: one SERENE, one DIY, and the world's own SORENTO product with no class.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.product import Product
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._brand_scope_seed import branded_product, contact, db, world  # noqa: F401
from tests._pg_fixture import unique_code


def _svc():
    from app.services import contact_brand_scope

    return contact_brand_scope


def _item_class(db, name: str):
    from app.models.product import ItemClass

    row = ItemClass(
        id=str(uuid.uuid4()),
        item_class_code=unique_code(name)[:50],
        item_class_name=f"ZZT {name}",
        company_id=DEFAULT_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


class ClassWorld:
    def __init__(self, db, world) -> None:
        self.w = world
        self.serene = _item_class(db, "SERENE")
        self.diy = _item_class(db, "DIY")
        self.p_serene = branded_product(db, unique_code("SER", alpha=True), world.sorento)
        self.p_serene.item_class_id = self.serene.id
        self.p_diy = branded_product(db, unique_code("DIY", alpha=True), world.sorento)
        self.p_diy.item_class_id = self.diy.id
        db.flush()
        self.codes = {
            "mocha": world.p_mocha.product_code,
            "sorento_noclass": world.p_sorento.product_code,
            "null_brand": world.p_null.product_code,
            "serene": self.p_serene.product_code,
            "diy": self.p_diy.product_code,
        }
        db.commit()

    def contact(self, db, brand_ids, brand_class_ids=None):
        c = contact(db, brand_ids=[str(b) for b in brand_ids] if brand_ids else None)
        if brand_class_ids is not None:
            from app.models.access import RespondContact

            db.query(RespondContact).filter(RespondContact.id == c.id).update(
                {"brand_class_ids": brand_class_ids}, synchronize_session=False
            )
        db.commit()
        return c


@pytest.fixture
def cw(db, world) -> ClassWorld:
    return ClassWorld(db, world)


def _visible(db, cw) -> set[str]:
    rows = db.query(Product.product_code).filter(Product.product_code.in_(list(cw.codes.values()))).all()
    by_code = {v: k for k, v in cw.codes.items()}
    return {by_code[r[0]] for r in rows}


def _stamp(db, scope) -> None:
    from app.models.base import set_brand_scope

    set_brand_scope(db, scope)


# --------------------------------------------------------------------- storage


def test_brand_class_ids_column_exists_and_defaults_to_null(db, cw) -> None:
    row = db.execute(
        text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'respond_contacts' "
            "AND column_name = 'brand_class_ids'"
        )
    ).one_or_none()
    assert row is not None, "respond_contacts.brand_class_ids does not exist"
    assert row[0] == "jsonb" and row[1] == "YES", row
    assert db.execute(
        text("SELECT brand_class_ids FROM respond_contacts WHERE id = :i"), {"i": cw.w.unscoped.id}
    ).scalar() is None


def test_products_carry_a_nullable_item_class_link(db, cw) -> None:
    row = db.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND table_name = 'products' AND column_name = 'item_class_id'"
        )
    ).one_or_none()
    assert row is not None and row[0] == "YES"


# --------------------------------------------------------------------- the session criterion


def test_brand_without_class_list_keeps_every_product_including_no_class(db, cw) -> None:
    """Q3: SORENTO with no class list = all its classes AND its products with no class."""
    c = cw.contact(db, [cw.w.sorento.id])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"sorento_noclass", "serene", "diy"}


def test_deploy_state_is_inert_scope_is_exactly_the_brand_ids(db, cw) -> None:
    """AC-10, owner 29 Oct ("inert to prod"): after the migration every contact has
    `brand_class_ids` NULL, and the first sync gives products a class. The scope must be the very
    value the pre-ITEM-CLASS code returned (`frozenset(brand_ids)`, no class tokens), and every
    product of an allowed brand stays visible whatever class it carries."""
    c = cw.contact(db, [cw.w.sorento.id, cw.w.mocha.id])
    scope = _svc().contact_brand_scope(db, c.id)
    assert scope == frozenset({str(cw.w.sorento.id), str(cw.w.mocha.id)})
    _stamp(db, scope)
    assert _visible(db, cw) == {"mocha", "sorento_noclass", "serene", "diy"}
    assert _svc().contact_brand_scope(db, cw.contact(db, None).id) is None


def test_brand_limited_to_one_class_shows_only_that_class(db, cw) -> None:
    """Q2 (a) + Q3: SORENTO limited to SERENE hides DIY and the SORENTO product with no class."""
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"serene"}


def test_two_classes_under_one_brand(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id), str(cw.diy.id)]})
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"serene", "diy"}


def test_class_limit_on_one_brand_leaves_the_other_brand_whole(db, cw) -> None:
    c = cw.contact(
        db, [cw.w.sorento.id, cw.w.mocha.id], {str(cw.w.sorento.id): [str(cw.serene.id)]}
    )
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"mocha", "serene"}


def test_class_pick_on_one_brand_does_not_open_that_class_on_another_brand(db, cw) -> None:
    """Classes are per company, not per brand: SERENE can also sit on a MOCHA product. A contact
    allowed SORENTO narrowed to SERENE must not see MOCHA's SERENE product (SQL and guard twin)."""
    p_mocha_serene = branded_product(db, unique_code("MSR", alpha=True), cw.w.mocha)
    p_mocha_serene.item_class_id = cw.serene.id
    db.commit()
    c = cw.contact(
        db, [cw.w.sorento.id, cw.w.mocha.id], {str(cw.w.sorento.id): [str(cw.serene.id)],
                                               str(cw.w.mocha.id): [str(cw.diy.id)]}
    )
    scope = _svc().contact_brand_scope(db, c.id)
    _stamp(db, scope)
    codes = [*cw.codes.values(), p_mocha_serene.product_code]
    rows = db.query(Product.product_code).filter(Product.product_code.in_(codes)).all()
    assert {r[0] for r in rows} == {cw.codes["serene"]}
    assert p_mocha_serene.product_code in _svc().out_of_scope_product_codes(db, scope, codes)
    assert str(p_mocha_serene.id) in _svc().out_of_scope_product_ids(db, scope, [p_mocha_serene.id])


def test_empty_class_list_means_every_class(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): []})
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"sorento_noclass", "serene", "diy"}


def test_class_list_for_a_brand_not_allowed_is_ignored(db, cw) -> None:
    """A class only narrows a brand already in `brand_ids`; it never grants a brand."""
    c = cw.contact(db, [cw.w.mocha.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"mocha"}


def test_class_list_without_any_brand_list_is_unscoped(db, cw) -> None:
    """`brand_ids` NULL = every brand; a stray class map does not scope the contact at all."""
    c = cw.contact(db, None, {str(cw.w.sorento.id): [str(cw.serene.id)]})
    assert _svc().contact_brand_scope(db, c.id) is None


def test_stale_class_id_fails_closed_for_that_brand(db, cw) -> None:
    """A deleted class leaves the brand limited to a class nothing carries: none of its products."""
    c = cw.contact(db, [cw.w.sorento.id, cw.w.mocha.id], {str(cw.w.sorento.id): [str(uuid.uuid4())]})
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"mocha"}


def test_scope_survives_a_round_trip_through_a_sorted_list(db, cw) -> None:
    """RQ export jobs carry the scope as `sorted(scope)` and rebuild a frozenset of strings."""
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    scope = _svc().contact_brand_scope(db, c.id)
    _stamp(db, frozenset(str(b) for b in sorted(scope)))
    assert _visible(db, cw) == {"serene"}


def test_other_company_products_still_pass(db, cw) -> None:
    """BRAND-SCOPE-PER-COMPANY stays: only companies owning a scoped brand are restricted."""
    from app.models.company import Company
    from tests._mc_lookup_seed import product

    other = Company(id=str(uuid.uuid4()), name="ZZT ICL other", code=f"ZIC{uuid.uuid4().hex[:6]}")
    db.add(other)
    db.flush()
    foreign = product(db, company_id=other.id, code=unique_code("FRN", alpha=True))
    db.commit()
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    scope = _svc().contact_brand_scope(db, c.id)
    from app.models.base import set_company_scope

    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID, str(other.id)}))
    pred = _svc().brand_predicate(scope, Product.brand_id, Product.company_id, Product.item_class_id)
    codes = {
        r[0]
        for r in db.query(Product.product_code)
        .filter(Product.product_code.in_([*cw.codes.values(), foreign.product_code]))
        .filter(pred)
    }
    assert codes == {cw.codes["serene"], foreign.product_code}


# --------------------------------------------------------------------- output guards / line clauses


def test_out_of_scope_codes_honour_the_class(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    scope = _svc().contact_brand_scope(db, c.id)
    out = _svc().out_of_scope_product_codes(db, scope, list(cw.codes.values()))
    assert out == {cw.codes[k] for k in ("mocha", "sorento_noclass", "null_brand", "diy")}


def test_out_of_scope_ids_honour_the_class(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    scope = _svc().contact_brand_scope(db, c.id)
    out = _svc().out_of_scope_product_ids(db, scope, [cw.p_serene.id, cw.p_diy.id, cw.w.p_sorento.id])
    assert out == {str(cw.p_diy.id), str(cw.w.p_sorento.id)}


def test_line_clauses_keep_only_in_class_lines(db, cw) -> None:
    """`product_in_scope_clauses` (sums over lines without selecting Product) honours the class."""
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    products = Product.__table__
    from sqlalchemy import select

    clauses = _svc().product_in_scope_clauses(db, products.c.id)
    rows = db.execute(
        select(products.c.product_code).where(products.c.product_code.in_(list(cw.codes.values())), *clauses)
    ).all()
    assert {r[0] for r in rows} == {cw.codes["serene"]}


def test_in_scope_product_codes_honour_the_class(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _svc().in_scope_product_codes(db, list(cw.codes.values())) == {cw.codes["serene"]}


# --------------------------------------------------------------------- the settings card


def test_settings_card_reads_classes_per_brand(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    out = _svc().get_contact_brands(db, c.id)
    assert out["brand_ids"] == [str(cw.w.sorento.id)]
    assert out["brand_class_ids"] == {str(cw.w.sorento.id): [str(cw.serene.id)]}
    assert out["item_classes"] == [{"id": str(cw.serene.id), "item_class_name": cw.serene.item_class_name}]


def test_settings_card_writes_classes_and_drops_classes_of_removed_brands(db, cw) -> None:
    c = cw.contact(db, [cw.w.sorento.id, cw.w.mocha.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    out = _svc().set_contact_brands(
        db, c.id, [str(cw.w.mocha.id)], {str(cw.w.sorento.id): [str(cw.serene.id)]}
    )
    assert out["brand_ids"] == [str(cw.w.mocha.id)]
    assert out["brand_class_ids"] == {}
    stored = db.execute(
        text("SELECT brand_class_ids FROM respond_contacts WHERE id = :i"), {"i": c.id}
    ).scalar()
    assert not stored


def test_settings_card_stores_a_class_list(db, cw) -> None:
    c = cw.contact(db, None)
    out = _svc().set_contact_brands(
        db, c.id, [str(cw.w.sorento.id)], {str(cw.w.sorento.id): [str(cw.diy.id), str(cw.serene.id)]}
    )
    assert sorted(out["brand_class_ids"][str(cw.w.sorento.id)]) == sorted([str(cw.diy.id), str(cw.serene.id)])
    _stamp(db, _svc().contact_brand_scope(db, c.id))
    assert _visible(db, cw) == {"serene", "diy"}


def test_settings_card_without_classes_keeps_the_old_call_shape(db, cw) -> None:
    """The two-argument call (brands only) still works and clears any class list."""
    c = cw.contact(db, [cw.w.sorento.id], {str(cw.w.sorento.id): [str(cw.serene.id)]})
    out = _svc().set_contact_brands(db, c.id, [str(cw.w.sorento.id)])
    assert out["brand_class_ids"] == {}


def test_settings_card_refuses_an_unknown_class(db, cw) -> None:
    from app.services.error_handler import AppException

    c = cw.contact(db, None)
    with pytest.raises(AppException) as err:
        _svc().set_contact_brands(db, c.id, [str(cw.w.sorento.id)], {str(cw.w.sorento.id): [str(uuid.uuid4())]})
    assert err.value.status_code == 422
