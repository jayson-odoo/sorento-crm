"""S2: one code resolver, shared by attachment linking and promotion creation.

The two paths disagree TODAY, before product sets enter the picture:

- `product_attachments._resolve_product_codes` treats a code as a SUBSTRING and
  returns every match, deliberately.
- `promotions._resolve_product_codes` does EXACT match with a `+`-split fallback.

So the same flyer code can link an attachment and fail to create a promotion.
That is a live defect, and it is why this slice replaces both with one function
rather than teaching each of them about sets separately.

Set expansion sits BETWEEN exact and substring, so a set code cannot be shadowed
by an accidental substring hit on some unrelated product.

UAC group F. Plan: `documentation/plans/master-data/PLAN-product-sets.md` section 5.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.product_code_resolution import resolve_codes_to_products

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

# Distinctive enough that no real catalogue row can collide with a substring probe.
STEM = "ZZTPS"


def _uid(stem: str) -> str:
    return f"ZZT-{stem}-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def db() -> Session:
    """A session whose writes are DISCARDED, even when the code under test commits.

    `SessionLocal()` + `begin_nested()` is not enough and it silently leaks: the
    service calls `db.commit()`, which commits the OUTER transaction rather than
    releasing a savepoint, so the fixture's rollback has nothing left to undo and
    every ZZT row lands in the shared database for good. That is what happened
    here - 99 sets, 407 products and 204 companies had to be swept back out.

    Binding to a connection that already holds a transaction, with
    `join_transaction_mode="create_savepoint"`, is what makes a committing test
    safe: its commits land on a savepoint inside the outer transaction, visible
    to the test and to the code under it, and the outer rollback still discards
    everything. Same approach as `tests/_pg_fixture.blank_session`.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with company_scope(session, None):
            yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def world(db: Session):
    """One 8608-shaped family per company, with codes nothing real can match.

    `<STEM>WCX8608<n>` pedestal, `<STEM>WCY8608<n>` cistern, `<STEM>WC8608<n>-SC`
    seat cover, and the set code `<STEM>WC8608<n>-RL` that names all three and is
    NOT itself a product - which is the entire problem.
    """
    tag = uuid.uuid4().hex[:6].upper()
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    db.add_all([category, uom])
    db.flush()

    built = {}
    for key in ("a", "b"):
        company = Company(id=str(uuid.uuid4()), name=_uid(f"co-{key}"), code=_uid(f"C{key}")[:20])
        db.add(company)
        db.flush()

        def product(code: str, price: str) -> Product:
            row = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                category_id=category.id,
                base_uom_id=uom.id,
                list_price=Decimal(price),
                company_id=company.id,
            )
            db.add(row)
            db.flush()
            return row

        pedestal = product(f"{STEM}WCX8608{tag}", "1180.00")
        cistern = product(f"{STEM}WCY8608{tag}", "0.00")
        seat = product(f"{STEM}WC8608{tag}-SC", "85.00")

        product_set = ProductSet(
            id=str(uuid.uuid4()),
            set_code=f"{STEM}WC8608{tag}-RL",
            name=_uid("set"),
            company_id=company.id,
        )
        db.add(product_set)
        db.flush()
        for index, member in enumerate((pedestal, cistern, seat)):
            db.add(
                ProductSetMember(
                    id=str(uuid.uuid4()),
                    product_set_id=product_set.id,
                    product_id=member.id,
                    quantity=Decimal("1"),
                    contributes_to_price=(index == 0),
                    sort_order=index,
                )
            )
        db.flush()
        built[key] = {
            "company": company,
            "set": product_set,
            "pedestal": pedestal,
            "cistern": cistern,
            "seat": seat,
        }
    return built


def _codes(result) -> set[str]:
    return {match.product.product_code for match in result.matches}


def _resolve_in(db: Session, company, codes):
    """Resolve the way production does: inside exactly one company's scope.

    Both companies carry the same product codes - that is true of the real
    catalogue, where every code exists once under Sorento and once under Mocha -
    so an unscoped resolve legitimately returns two rows per code. The external
    paths are always scoped (the attachment pins the session to its own company),
    and these tests say so rather than asserting against an artificial
    all-companies read.
    """
    with company_scope(db, frozenset({str(company.id)})):
        return resolve_codes_to_products(db, codes)


# ------------------------------------------------------------------ the tiers


def test_ac_f2_a_set_code_resolves_to_every_member(db: Session, world):
    """AC-F.2 - the code on the flyer names three SKUs, and all three are linked."""
    a = world["a"]
    result = _resolve_in(db, a["company"], [a["set"].set_code])

    assert _codes(result) == {
        a["pedestal"].product_code,
        a["cistern"].product_code,
        a["seat"].product_code,
    }
    assert result.unmatched == []


def test_ac_f3_a_set_expansion_names_the_set_that_produced_it(db: Session, world):
    """AC-F.3 - provenance, so these links can be found and cleaned up later."""
    a = world["a"]
    result = _resolve_in(db, a["company"], [a["set"].set_code])

    assert {m.product_set_id for m in result.matches} == {a["set"].id}
    assert {m.via for m in result.matches} == {"product_set"}


def test_ac_f4_an_ordinary_code_carries_no_set_provenance(db: Session, world):
    """AC-F.4 - null set id is what distinguishes a human link from a fan-out."""
    a = world["a"]
    result = _resolve_in(db, a["company"], [a["cistern"].product_code])

    assert _codes(result) == {a["cistern"].product_code}
    assert [m.product_set_id for m in result.matches] == [None]
    assert [m.via for m in result.matches] == ["exact"]


def test_an_exact_product_code_beats_a_set_that_would_also_match(db: Session, world):
    """A real product wins its own code. Sets fill a gap; they do not shadow rows."""
    a = world["a"]
    # A set deliberately code-named after an existing product, which is a data
    # defect but must not silently redirect that product's own code.
    db.add(
        ProductSet(
            id=str(uuid.uuid4()),
            set_code=a["cistern"].product_code,
            name=_uid("shadow"),
            company_id=a["company"].id,
        )
    )
    db.flush()

    result = _resolve_in(db, a["company"], [a["cistern"].product_code])
    assert _codes(result) == {a["cistern"].product_code}
    assert [m.via for m in result.matches] == ["exact"]


def test_a_set_code_is_not_shadowed_by_a_substring_hit(db: Session, world):
    """Set expansion sits BEFORE substring, or a longer product code steals the set.

    `<set>-RL` is a substring of `<set>-RL-200`, so a substring-first resolver
    would answer with that one unrelated product instead of the set's members.
    """
    a = world["a"]
    decoy = Product(
        id=str(uuid.uuid4()),
        product_code=f"{a['set'].set_code}-200",
        product_name="decoy",
        category_id=a["pedestal"].category_id,
        base_uom_id=a["pedestal"].base_uom_id,
        list_price=Decimal("1.00"),
        company_id=a["company"].id,
    )
    db.add(decoy)
    db.flush()

    result = _resolve_in(db, a["company"], [a["set"].set_code])
    assert decoy.product_code not in _codes(result)
    assert _codes(result) == {
        a["pedestal"].product_code,
        a["cistern"].product_code,
        a["seat"].product_code,
    }


def test_substring_still_answers_a_partial_code(db: Session, world):
    """The attachments path's deliberate behaviour survives: a code is a substring.

    "WC7601 names MWC7601-RL-S12, IBWC7601-RL-S10 and every other product
    carrying it", and every match is returned because taking one arbitrarily left
    the rest silently uncovered.
    """
    a = world["a"]
    stem = a["pedestal"].product_code[:-2]  # a partial nobody holds exactly
    result = _resolve_in(db, a["company"], [stem])

    assert a["pedestal"].product_code in _codes(result)
    assert all(m.via == "substring" for m in result.matches)


def test_ac_f7_the_plus_split_fallback_survives(db: Session, world):
    """AC-F.7 - promotions' `A+B` behaviour must not be lost in the merge."""
    a = world["a"]
    combined = f"{a['pedestal'].product_code} + {a['seat'].product_code}"
    result = _resolve_in(db, a["company"], [combined])

    assert _codes(result) == {a["pedestal"].product_code, a["seat"].product_code}
    assert all(m.via == "plus_split" for m in result.matches)


def test_ac_f6_a_code_naming_nothing_is_reported_not_dropped(db: Session, world):
    """AC-F.6 - silence is the failure this whole feature exists to remove."""
    result = resolve_codes_to_products(db, ["ZZT-NO-SUCH-CODE-AT-ALL"])
    assert result.matches == []
    assert result.unmatched == ["ZZT-NO-SUCH-CODE-AT-ALL"]


def test_blank_and_duplicate_codes_are_absorbed(db: Session, world):
    """A caller passing the same code twice gets one answer, not two links."""
    a = world["a"]
    result = _resolve_in(
        db, a["company"], [a["cistern"].product_code, "  ", a["cistern"].product_code, ""]
    )
    assert len(result.matches) == 1
    assert result.unmatched == []


def test_a_set_code_is_matched_case_and_space_insensitively(db: Session, world):
    """n8n reads codes off a PDF, so the casing and spacing are whatever printed."""
    a = world["a"]
    scruffy = f" {a['set'].set_code.lower()} "
    result = _resolve_in(db, a["company"], [scruffy])
    assert len(result.matches) == 3


# ------------------------------------------------------------------ isolation


def test_ac_f8_a_set_resolves_only_within_the_scoped_company(db: Session, world):
    """AC-F.8 - an attachment pinned to one company never links another's members."""
    a, b = world["a"], world["b"]

    result = _resolve_in(db, b["company"], [b["set"].set_code])

    # By ROW, never by code. Both companies carry identical product codes - that
    # is the whole reason sets are company-scoped - so comparing code strings
    # would pass no matter which company's rows came back.
    resolved_ids = {m.product.id for m in result.matches}
    assert resolved_ids == {
        b["pedestal"].id,
        b["cistern"].id,
        b["seat"].id,
    }
    assert a["pedestal"].id not in resolved_ids


def test_the_other_companys_set_code_is_unmatched_not_borrowed(db: Session, world):
    """Fail-closed: an unknown-here code is reported, never silently satisfied."""
    a, b = world["a"], world["b"]
    # Give company A's set a code company B does not carry at all.
    a["set"].set_code = f"{STEM}-ONLY-A-{uuid.uuid4().hex[:6]}"
    db.flush()

    result = _resolve_in(db, b["company"], [a["set"].set_code])

    assert result.matches == []
    assert result.unmatched == [a["set"].set_code]


# ------------------------------------------------------- the callers agree now


def test_ac_f1_both_external_paths_use_this_one_function(db: Session, world):
    """AC-F.1 - one helper, one behaviour, asserted at the import site.

    Guards the actual regression: someone re-adding a private `_resolve_product_codes`
    to either router is what let the two drift apart in the first place.
    """
    from app.api.v1.external import product_attachments, promotions

    assert product_attachments._resolve_codes is resolve_codes_to_products
    assert promotions._resolve_codes is resolve_codes_to_products


# --------------------------------------------- the provenance column is written


def test_the_link_schema_carries_set_provenance_to_the_row():
    """AC-F.3 - the value has to survive the schema, or the column is never set.

    `ProductAttachmentService` builds the row from `model_dump()`, so a field the
    schema does not declare is dropped silently between the router and the table -
    the same class of defect as `response_model` dropping an undeclared field on
    the way out.
    """
    from app.schemas.product import ProductAttachmentCreate

    payload = ProductAttachmentCreate(
        product_id=str(uuid.uuid4()),
        attachment_id=str(uuid.uuid4()),
        linked_via_set_id="set-123",
    )
    assert payload.model_dump()["linked_via_set_id"] == "set-123"


def test_both_link_tables_can_hold_set_provenance(db: Session, world):
    """AC-F.3 / AC-F.4 - the column exists on both, and NULL is a legal answer."""
    from sqlalchemy import inspect as sa_inspect

    from app.models.marketing import PromotionProduct
    from app.models.product import ProductAttachment

    for model in (ProductAttachment, PromotionProduct):
        assert "linked_via_set_id" in sa_inspect(model).columns
        column = sa_inspect(model).columns["linked_via_set_id"]
        assert column.nullable, "a hand-made link legitimately has no set"
