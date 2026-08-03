"""S3 - turning what a consumer typed into a product, or honestly into nothing.

AC-C16 to AC-C18. A consumer reads a model code off a receipt, a box, or the underside of a
tap, and types it into a phone. What arrives is `SRTWC8152`, or `WC189-G2`, or
`SRTWC8517-200mm`, or "the tap in my kitchen". None of those is a `products.product_code`.

**The ladder answers with a state, for the same reason the dealer resolver does.** Callers
that receive a score invent thresholds, and the threshold somebody invents eventually
pre-fills the wrong variant. A wrong variant is a wrong warranty term on the line - the
`SRTWC8152` family covers three real products, and their parts differ.

  exact       one product, certain. Safe to pre-fill.
  ambiguous   a real base code matching SEVERAL variants. `product_id` stays NULL and the
              KIND answers instead (ADR-0010). This is the common case, not an error.
  candidates  nothing exact, but near neighbours worth showing CS.
  unmatched   nothing to go on.

**Why `ambiguous` is not a failure.** `SRTWC8152` matching three variants is the receipt
being accurate and the catalogue being granular. ADR-0010 exists precisely so cover is
decidable without the variant. Collapsing `ambiguous` into `unmatched` throws away a
perfectly good Kind resolution; collapsing it into `exact` by picking the first match is how
the wrong part's warranty term lands on the line.

**The rungs, in order, each one measured against a real thing a consumer typed:**

1. exact code
2. dash-strip           `SRTWC8152RLRG` for `SRTWC8152-RL-RG`
3. `SRT` prefix         `WC189-G2` for `SRTWC189-G2` - the box prints the short form
4. trailing unit        `SRTWC8517-200mm` for `SRTWC8517-200`
5. base-code prefix     `SRTWC8152` covering the whole family -> ambiguous
6. trigram neighbours   candidates only, never exact

Order matters and is asserted: a later rung must never overrule an earlier one, or a typo
that happens to trigram-match well beats an exact hit.

Run: venv/bin/python -m pytest tests/test_product_resolution.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid

import pytest

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402,F401

from app.models.product import Product  # noqa: E402

from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

MODULE = "app.services.product_resolution_service"

STATE_EXACT = "exact"
STATE_AMBIGUOUS = "ambiguous"
STATE_CANDIDATES = "candidates"
STATE_UNMATCHED = "unmatched"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _module():
    if importlib.util.find_spec(MODULE) is None:
        raise AssertionError(
            f"{MODULE} does not exist. The ladder belongs in one place: the consumer "
            "portal, the CS review screen and the extract endpoint must reach the same "
            "product for the same typed code, or the ledger disagrees with itself."
        )
    return importlib.import_module(MODULE)


def _fn(module, name: str, signature: str):
    fn = getattr(module, name, None)
    assert callable(fn), f"{module.__name__}.{name}{signature} must exist."
    return fn


def _seed_refs(db):
    """Category and UoM are NOT NULL FKs on products. Postgres enforces what sqlite
    ignored, so these are real rows rather than invented UUIDs.
    """
    from app.models.product import ProductCategory, UnitOfMeasure

    category = ProductCategory(
        id=str(uuid.uuid4()),
        category_code=f"{TEST_PREFIX}-CAT-{uuid.uuid4().hex[:6]}",
        category_name=f"{TEST_PREFIX} Sanitary",
    )
    uom = UnitOfMeasure(
        id=str(uuid.uuid4()),
        uom_code=f"{TEST_PREFIX}-U{uuid.uuid4().hex[:4]}",
        uom_name="Unit",
    )
    db.add_all([category, uom])
    db.flush()
    return category, uom


def _product(db, code: str, *, refs=None) -> Product:
    category, uom = refs or _seed_refs(db)
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=f"{TEST_PREFIX} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=0,
    )
    db.add(row)
    db.flush()
    return row


def _resolve(db, typed: str):
    return _fn(_module(), "resolve_product", "(db, typed_code)")(db, typed)


# ================================================================== rung 1: exact


def test_an_exact_code_resolves(db):
    target = _product(db, "SRTWC8152-RL-RG")
    result = _resolve(db, "SRTWC8152-RL-RG")
    assert result.state == STATE_EXACT
    assert result.product_id == str(target.id)


def test_case_does_not_matter(db):
    """Nobody types a model code in the case the catalogue stores it."""
    _product(db, "SRTWC8152-RL-RG")
    assert _resolve(db, "srtwc8152-rl-rg").state == STATE_EXACT


def test_surrounding_whitespace_does_not_matter(db):
    _product(db, "SRTWC8152-RL-RG")
    assert _resolve(db, "  SRTWC8152-RL-RG  ").state == STATE_EXACT


# ============================================================ rung 2: dash-strip


def test_a_code_typed_without_its_dashes_resolves(db):
    """Consumers read the dashes and do not type them. This costs nothing to support
    and there is no ambiguity: the catalogue's own codes are unique without dashes too.
    """
    target = _product(db, "SRTWC8152-RL-RG")
    result = _resolve(db, "SRTWC8152RLRG")
    assert result.state == STATE_EXACT
    assert result.product_id == str(target.id)


def test_dash_stripping_that_becomes_ambiguous_is_not_exact(db):
    """If removing punctuation makes two real products identical, the punctuation was
    the thing that distinguished them and dropping it cannot be a confident answer.
    """
    refs = _seed_refs(db)
    _product(db, "SRTWC-8152", refs=refs)
    _product(db, "SRT-WC8152", refs=refs)
    assert _resolve(db, "SRTWC8152").state != STATE_EXACT


# ========================================================== rung 3: the SRT prefix


def test_the_short_form_printed_on_the_box_resolves(db):
    """`WC189-G2` is `SRTWC189-G2`. The carton prints the short form and the catalogue
    stores the long one, so a consumer copying the box is right and unmatched.
    """
    target = _product(db, "SRTWC189-G2")
    result = _resolve(db, "WC189-G2")
    assert result.state == STATE_EXACT
    assert result.product_id == str(target.id)


def test_the_prefix_is_added_not_removed(db):
    """Adding `SRT` to what the consumer typed is safe: it only ever narrows to the
    Sorento catalogue. STRIPPING it from stored codes would collide every `SRTWCnnn`
    with a hypothetical `WCnnn` from another brand.
    """
    refs = _seed_refs(db)
    _product(db, "SRTWC189-G2", refs=refs)
    _product(db, "WC189-G2", refs=refs)
    result = _resolve(db, "WC189-G2")
    assert result.state == STATE_EXACT, "The literal code exists; the prefix rung must not fire."
    assert result.product_code == "WC189-G2"


# ======================================================= rung 4: the trailing unit


def test_a_trailing_unit_is_stripped(db):
    """`SRTWC8517-200mm` is `SRTWC8517-200`. The 200 is part of the code; the `mm` is
    the consumer being helpful.
    """
    target = _product(db, "SRTWC8517-200")
    result = _resolve(db, "SRTWC8517-200mm")
    assert result.state == STATE_EXACT
    assert result.product_id == str(target.id)


def test_a_unit_that_is_part_of_the_code_is_not_stripped_away(db):
    """The rung must not fire when the literal code exists. Stripping first would make
    a real product unreachable by its own code.
    """
    _product(db, "SRTSK-300MM")
    result = _resolve(db, "SRTSK-300MM")
    assert result.state == STATE_EXACT
    assert result.product_code == "SRTSK-300MM"


# ========================================================= rung 5: the base family


def test_a_base_code_matching_several_variants_is_ambiguous_not_exact(db):
    """THE case ADR-0010 was written for, and the reason `product_id` is nullable.

    Three real products, one base code. Picking one puts another part's warranty term
    on the line; refusing to answer throws away a Kind that resolves perfectly well.
    """
    refs = _seed_refs(db)
    for code in ("SRTWC8152-RL-RG", "SRTWC8152-SH", "SRTWC8152-300-RL"):
        _product(db, code, refs=refs)
    result = _resolve(db, "SRTWC8152")
    assert result.state == STATE_AMBIGUOUS
    assert result.product_id is None, "An ambiguous base code must not pre-fill a variant."
    assert len(result.candidates) == 3


def test_a_base_code_matching_exactly_one_variant_resolves(db):
    """One member is not a family. Withholding the answer here would cost the consumer
    an edit for nothing.
    """
    target = _product(db, "SRTWC9001-RL")
    result = _resolve(db, "SRTWC9001")
    assert result.state == STATE_EXACT
    assert result.product_id == str(target.id)


def test_the_ambiguous_candidates_are_ordered_the_same_way_every_time(db):
    """CS reads this list. A list that reshuffles between page loads is a list nobody
    trusts, and two identical receipts must produce identical screens.
    """
    refs = _seed_refs(db)
    for code in ("SRTWC8152-SH", "SRTWC8152-RL-RG", "SRTWC8152-300-RL"):
        _product(db, code, refs=refs)
    first = _resolve(db, "SRTWC8152")
    second = _resolve(db, "SRTWC8152")
    assert [c["product_code"] for c in first.candidates] == [
        c["product_code"] for c in second.candidates
    ]


def test_a_base_code_never_pre_fills_even_with_a_single_char_difference(db):
    """`SRTWC8152` must not reach `SRTWC8153`. Prefix matching is a family rule, not a
    fuzzy one, and one digit is a different product with a different warranty.
    """
    _product(db, "SRTWC8153-RL")
    result = _resolve(db, "SRTWC8152")
    assert result.state != STATE_EXACT
    assert result.product_id is None


# ================================================== rung 6: neighbours, never exact


def test_a_near_miss_offers_candidates_and_never_resolves(db):
    """A typo is worth showing CS and never worth asserting. Same tradeoff as the
    dealer resolver, and for the same reason: a confident wrong answer costs more than
    an honest miss.
    """
    _product(db, "SRTWC8152-RL-RG")
    result = _resolve(db, "SRTWC8155-RL-RG")
    assert result.state != STATE_EXACT
    assert result.product_id is None


def test_free_text_that_is_not_a_code_matches_nothing(db):
    """AC-C16. "the tap in my kitchen" is a valid thing to submit and an invalid thing
    to resolve. The line still lodges; the Kind chooser is what answers it.
    """
    _product(db, "SRTWC8152-RL-RG")
    for typed in ("the tap in my kitchen", "toilet", ""):
        result = _resolve(db, typed)
        assert result.state == STATE_UNMATCHED
        assert result.product_id is None


def test_nothing_typed_is_unmatched_rather_than_an_error(db):
    _product(db, "SRTWC8152-RL-RG")
    assert _resolve(db, None).state == STATE_UNMATCHED


def test_an_empty_catalogue_is_unmatched_rather_than_a_crash(db):
    assert _resolve(db, "SRTWC8152").state == STATE_UNMATCHED


# ========================================================== what the caller receives


def test_the_typed_text_always_survives(db):
    """Whatever the verdict, what the consumer typed is kept. It is the only thing CS
    can act on when every rung misses.
    """
    _product(db, "SRTWC8152-RL-RG")
    for typed in ("SRTWC8152-RL-RG", "SRTWC8155", "the tap in my kitchen"):
        assert _resolve(db, typed).typed_code == typed


def test_an_inactive_product_is_not_offered(db):
    """A discontinued product is still a real thing a consumer owns, but pre-filling an
    inactive row sends CS to a catalogue entry they cannot act on.
    """
    row = _product(db, "SRTWC8152-RL-RG")
    row.is_active = False
    db.flush()
    assert _resolve(db, "SRTWC8152-RL-RG").state != STATE_EXACT


def test_a_rung_never_overrules_an_earlier_one(db):
    """The ordering assertion, as one test.

    The literal code exists, AND a dash-stripped form of another product would also
    match, AND trigram neighbours abound. Rung 1 wins.
    """
    refs = _seed_refs(db)
    target = _product(db, "SRTWC8152", refs=refs)
    _product(db, "SRT-WC-8152", refs=refs)
    _product(db, "SRTWC8152-RL-RG", refs=refs)
    result = _resolve(db, "SRTWC8152")
    assert result.state == STATE_EXACT
    assert result.product_id == str(target.id)
