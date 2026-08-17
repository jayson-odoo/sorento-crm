"""RED-phase pytest for `app/services/product_spec_verification.py` (PR 3, UAC group D).

Names, signatures and behaviour are pinned by the orchestrator contract note
(`pr3-contract.md`, "Model (AC-D.1)" + "Invalidation hook" + "Phase 2 - backend
service API") and by `documentation/plans/master-data/spec-authoring-verification-
acceptance-criteria.md` group D. Neither `app.services.product_spec_verification`
nor `app.models.product_spec.ProductSpecVerification` exists yet - the module-level
import below fails at collection, which IS the expected red state, mirroring
`tests/test_product_spec_authored_write.py`'s own note about
`app.services.product_spec_write` before PR 1 landed.

Fixture shape follows `tests/test_product_spec_authored_write.py` (`db` fixture,
`_fixtures`, `_product`) per the tester brief. Postgres only, via
`tests/_pg_fixture.py::blank_session` - every test seeds its own chain with a
`unique_code()`-prefixed code, never borrows a production row.

`actor` mappings mirror the shape `app.dependencies._decode_jwt_user` /
`_load_user_dict_from_db` hand every route: `{"id", "email", "name", ...}` - the
same shape `apply_spec_values`'s `actor: Mapping | None` already reads `.get("email")`
from. `verified_by_name` / `invalidated_by_name` are asserted as "actor's `name`,
falling back to `email` when `name` is absent" per the contract note's "a display
name helper (full name, else email)".
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import (
    ProductSpecException,
    ProductSpecifications,
    ProductSpecRegistry,
    ProductSpecVerification,
)
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_write import apply_spec_values
from app.services import product_spec_verification as psv
from tests._pg_fixture import blank_session, unique_code

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        _fixtures(s)
        yield s


def _fixtures(db):
    """Category (+ a second, differently-classed category), brand, UOM and a second
    company - mirrors `test_product_spec_authored_write.py::_fixtures` plus the
    extra class needed for the worklist grouping tests."""
    cat = ProductCategory(
        id=str(uuid.uuid4()), category_code="ZZT-VS-KS", category_name="ZZT-VS-KS",
        class_label="Kitchen Sink",
    )
    cat_b = ProductCategory(
        id=str(uuid.uuid4()), category_code="ZZT-VS-BD", category_name="ZZT-VS-BD",
        class_label="Bidet",
    )
    # A class only a discontinued code carries, and a category with no class at all -
    # both exist for the `classes` facet tests and are unused by every other fixture.
    cat_c = ProductCategory(
        id=str(uuid.uuid4()), category_code="ZZT-VS-SH", category_name="ZZT-VS-SH",
        class_label="Shower Set",
    )
    cat_none = ProductCategory(
        id=str(uuid.uuid4()), category_code="ZZT-VS-NC", category_name="ZZT-VS-NC",
        class_label=None,
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-VS-PCS", uom_name="Piece")
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-VS-SRT", brand_name="Sorento")
    second = Company(id=str(uuid.uuid4()), name="ZZT VS Second Co", code="ZZT-VS2")
    db.add_all([cat, cat_b, cat_c, cat_none, uom, brand, second])
    db.flush()
    backfill_category_signals(db)
    _REFS.update(
        {
            "cat": cat.id,
            "cat_b": cat_b.id,
            "cat_c": cat_c.id,
            "cat_none": cat_none.id,
            "uom": uom.id,
            "brand": brand.id,
            "company2": second.id,
        }
    )


def _product(
    db,
    code: str,
    description: str = "SORENTO CERAMIC KITCHEN SINK",
    *,
    name: str | None = None,
    category: str | None = None,
    company_id: str | None = None,
    discontinued: bool = False,
    product_id: str | None = None,
) -> Product:
    row = Product(
        # `product_id` is passed only where a test needs to know WHICH copy of a code
        # sorts lowest - "the lowest product id" is a real rule in this module.
        id=product_id or str(uuid.uuid4()),
        product_code=code,
        product_name=name or code,
        description=description,
        category_id=_REFS[category or "cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
        is_discontinued=discontinued,
    )
    if company_id is not None:
        row.company_id = company_id
    db.add(row)
    db.flush()
    return row


def _spec(db, product: Product, values: dict, provenance: dict | None = None) -> ProductSpecifications:
    """A spec row written directly rather than through `write_spec_row`, per the
    precedent at `tests/test_product_spec_search.py:983-984` (acceptable in tests) -
    these tests want arbitrary fixed `values`, not derivation's output."""
    row = ProductSpecifications(
        product_id=product.id,
        values=values,
        provenance=provenance
        or {k: {"source": "derived", "confidence": 1.0, "evidence": "test"} for k in values},
        status="derived",
        derived_hash="zzt-fixture-hash",
    )
    db.add(row)
    db.flush()
    return row


def _registry_key(
    db,
    key: str,
    *,
    data_type: str = "enum",
    allowed_values: list | None = None,
    applies_when: dict | None = None,
    is_active: bool = True,
) -> ProductSpecRegistry:
    row = ProductSpecRegistry(
        spec_key=key,
        label=key.replace("_", " ").title(),
        data_type=data_type,
        allowed_values=allowed_values or [],
        applies_when=applies_when or {},
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def _open_exception(db, code: str, *, spec_key: str = "material", reason: str = "human_override_conflict"):
    row = ProductSpecException(id=str(uuid.uuid4()), product_code=code, spec_key=spec_key, reason=reason)
    db.add(row)
    db.flush()
    return row


def _counts(coverage: dict) -> dict:
    """The two coverage numbers alone. `items` (the tooltip's list) has its own test."""
    return {"have": coverage["have"], "applicable": coverage["applicable"]}


def _verification_row(db, code: str, **overrides) -> ProductSpecVerification:
    """A verification row inserted BY HAND, bypassing `verify_code` - what M2-S5's
    "pinned by a pytest that inserts a supplier row by hand before the feature
    exists" and the state-derivation tests both need: a fixed, known row shape to
    read back, independent of the write path under test elsewhere."""
    defaults = dict(
        id=str(uuid.uuid4()),
        product_code=code,
        party=psv.PARTY_INTERNAL,
        verified_by_user_id=str(uuid.uuid4()),
        verified_by_name="Hand Seeded Verifier",
        verified_at=datetime(2026, 1, 1, 9, 0, 0),
        values_hash="0" * 64,
    )
    defaults.update(overrides)
    row = ProductSpecVerification(**defaults)
    db.add(row)
    db.flush()
    return row


_ACTOR = {"id": str(uuid.uuid4()), "email": "verifier@zzt.test", "name": "Verifier One"}
_ACTOR_NO_NAME = {"id": str(uuid.uuid4()), "email": "noname@zzt.test", "name": None}
_ACTOR_2 = {"id": str(uuid.uuid4()), "email": "withdrawer@zzt.test", "name": "Withdrawer Two"}

_BLOCK_KEYS = {
    "state",
    "verified_by_name",
    "verified_at",
    "invalidated_at",
    "invalidated_reason",
    "invalidated_by_name",
    "invalidated_diff",
}


# --------------------------------------------------------------------------- #
# AC-D.2 - state derivation, never re-hashed
# --------------------------------------------------------------------------- #
def test_no_verification_rows_reads_as_unverified(db):
    code = unique_code("VS-NOROWS")
    _product(db, code)

    block = psv.verification_block(db, code)

    assert set(block) == _BLOCK_KEYS, "VerificationBlock must carry exactly the FE contract's keys"
    assert block["state"] == psv.STATE_UNVERIFIED
    assert block["verified_by_name"] is None
    assert block["verified_at"] is None
    assert block["invalidated_at"] is None
    assert block["invalidated_reason"] is None
    assert block["invalidated_by_name"] is None
    assert block["invalidated_diff"] is None


def test_an_active_row_reads_as_verified_with_credit(db):
    code = unique_code("VS-ACTIVE")
    _product(db, code)
    when = datetime(2026, 1, 1, 9, 0, 0)
    _verification_row(db, code, verified_by_name="Jane Reviewer", verified_at=when)

    block = psv.verification_block(db, code)

    assert set(block) == _BLOCK_KEYS
    assert block["state"] == psv.STATE_VERIFIED
    assert block["verified_by_name"] == "Jane Reviewer"
    assert block["verified_at"] == when
    assert block["invalidated_at"] is None
    assert block["invalidated_reason"] is None
    assert block["invalidated_diff"] is None


def test_latest_row_invalidated_for_values_changed_reads_needs_reverify_with_diff_and_original_credit(db):
    code = unique_code("VS-NEEDSRV")
    _product(db, code)
    verified_when = datetime(2026, 1, 1, 9, 0, 0)
    invalidated_when = datetime(2026, 1, 2, 9, 0, 0)
    diff = {"changed": [{"spec_key": "material", "was": {"value": "ceramic"}, "now": {"value": "brass"}}]}
    _verification_row(
        db,
        code,
        verified_by_name="Jane Reviewer",
        verified_at=verified_when,
        invalidated_at=invalidated_when,
        invalidated_reason=psv.REASON_VALUES_CHANGED,
        invalidated_diff=diff,
        invalidated_by_user_id=None,
        invalidated_by_name=None,
    )

    block = psv.verification_block(db, code)

    assert block["state"] == psv.STATE_NEEDS_REVERIFY
    assert block["verified_by_name"] == "Jane Reviewer", "the original credit survives"
    assert block["verified_at"] == verified_when
    assert block["invalidated_at"] == invalidated_when
    assert block["invalidated_reason"] == psv.REASON_VALUES_CHANGED
    assert block["invalidated_diff"] == diff
    assert block["invalidated_by_name"] is None


def test_latest_row_invalidated_manual_unverify_reads_unverified_not_needs_reverify(db):
    code = unique_code("VS-MANUNV")
    _product(db, code)
    _verification_row(
        db,
        code,
        invalidated_at=datetime(2026, 1, 2, 9, 0, 0),
        invalidated_reason=psv.REASON_MANUAL_UNVERIFY,
        invalidated_diff=None,
        invalidated_by_user_id=str(uuid.uuid4()),
        invalidated_by_name="Someone Else",
    )

    block = psv.verification_block(db, code)

    assert block["state"] == psv.STATE_UNVERIFIED
    assert block["invalidated_diff"] is None


def test_verification_blocks_batch_matches_the_per_code_read(db):
    code_active = unique_code("VS-BATCH-A")
    code_bare = unique_code("VS-BATCH-B")
    _product(db, code_active)
    _product(db, code_bare)
    _verification_row(db, code_active, verified_by_name="Batch Reviewer")

    blocks = psv.verification_blocks(db, [code_active, code_bare])

    assert blocks[code_active]["state"] == psv.STATE_VERIFIED
    assert blocks[code_bare]["state"] == psv.STATE_UNVERIFIED
    assert blocks[code_active] == psv.verification_block(db, code_active)


# --------------------------------------------------------------------------- #
# AC-D.3 / M2-S5 - party-agnostic invalidation on a values change
# --------------------------------------------------------------------------- #
def test_invalidate_on_values_change_invalidates_every_active_row_regardless_of_party(db):
    """M2-S5's pin: a supplier row inserted BY HAND, before the feature exists, must
    still be invalidated by the same values-change hook that invalidates internal
    rows - invalidation is party-agnostic by construction, not by coincidence."""
    code = unique_code("VS-PARTY")
    _product(db, code)
    internal_row = _verification_row(db, code, party=psv.PARTY_INTERNAL, verified_by_name="Internal Reviewer")
    supplier_row = _verification_row(db, code, party="supplier", verified_by_name="Supplier Contact")
    db.commit()

    before = {"material": {"value": "ceramic"}}
    after = {"material": {"value": "brass"}}
    invalidated = psv.invalidate_on_values_change(db, code, before_values=before, after_values=after)
    db.commit()

    assert invalidated is True
    for row in (internal_row, supplier_row):
        db.refresh(row)
        assert row.invalidated_at is not None
        assert row.invalidated_reason == psv.REASON_VALUES_CHANGED
        assert row.invalidated_diff == {
            "changed": [{"spec_key": "material", "was": {"value": "ceramic"}, "now": {"value": "brass"}}]
        }
        assert row.invalidated_by_user_id is None, "no person did this"
        assert row.invalidated_by_name is None


def test_invalidate_on_values_change_is_a_no_op_when_the_canonical_hash_is_unchanged(db):
    code = unique_code("VS-NOCHANGE")
    _product(db, code)
    row = _verification_row(db, code)
    db.commit()

    same = {"material": {"value": "ceramic"}}
    invalidated = psv.invalidate_on_values_change(db, code, before_values=same, after_values=dict(same))
    db.commit()

    assert invalidated is False
    db.refresh(row)
    assert row.invalidated_at is None


def test_apply_spec_values_changing_a_value_invalidates_a_verified_code(db):
    """The hook wired into `apply_spec_values` (product_spec_write.py, after its
    write loop) - end to end, not the direct-call unit test above."""
    code = unique_code("VS-APPLYINV")
    _product(db, code, "SORENTO CERAMIC KITCHEN SINK")
    derive_for_code(db, code, commit=True)
    h1 = psv.current_values_hash(db, code)
    result = psv.verify_code(db, code, values_hash=h1, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    assert result["outcome"] == "verified"
    db.commit()

    apply_spec_values(db, code, [{"spec_key": "material", "op": "set", "value": "brass"}], actor=_ACTOR)

    block = psv.verification_block(db, code)
    assert block["state"] == psv.STATE_NEEDS_REVERIFY
    assert block["invalidated_reason"] == psv.REASON_VALUES_CHANGED
    changed_keys = {entry["spec_key"] for entry in block["invalidated_diff"]["changed"]}
    assert "material" in changed_keys
    assert block["invalidated_by_name"] is None, "a code write did this, not a person"


def test_apply_spec_values_setting_the_same_value_again_invalidates_nothing_further(db):
    code = unique_code("VS-SAMEVAL")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h1 = psv.current_values_hash(db, code)
    psv.verify_code(db, code, values_hash=h1, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    # "mounting" is never derived for a plain kitchen-sink description (established
    # by test_product_spec_authored_write.py's own non-conflicting-write test), so
    # this authored write is a clean values-change, isolated from AC-F.5's conflict
    # behaviour.
    apply_spec_values(db, code, [{"spec_key": "mounting", "op": "set", "value": "wall_hung"}], actor=_ACTOR)
    first = psv.verification_block(db, code)
    assert first["state"] == psv.STATE_NEEDS_REVERIFY
    first_invalidated_at = first["invalidated_at"]

    apply_spec_values(db, code, [{"spec_key": "mounting", "op": "set", "value": "wall_hung"}], actor=_ACTOR)
    second = psv.verification_block(db, code)

    assert second["invalidated_at"] == first_invalidated_at, (
        "re-applying the same value must not move the invalidation stamp - the "
        "canonical hash of the resulting values set has not changed"
    )


def test_derive_for_code_skip_path_does_not_invalidate_a_verified_code(db):
    """AC-D.3's other half: derivation's skip-if-unchanged early return
    (product_spec_derivation.py ~1267) must never reach the invalidation hook."""
    code = unique_code("VS-SKIP")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h1 = psv.current_values_hash(db, code)
    psv.verify_code(db, code, values_hash=h1, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    result = derive_for_code(db, code, commit=True)

    assert result["written"] == 0, "must take the skip path - unchanged input"
    block = psv.verification_block(db, code)
    assert block["state"] == psv.STATE_VERIFIED


def test_derive_for_code_that_changes_values_invalidates_a_verified_code(db):
    code = unique_code("VS-DERIVEINV")
    _product(db, code, "SORENTO CERAMIC KITCHEN SINK")
    derive_for_code(db, code, commit=True)
    h1 = psv.current_values_hash(db, code)
    psv.verify_code(db, code, values_hash=h1, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    product = db.query(Product).filter(Product.product_code == code).one()
    product.description = "SORENTO BRASS ANGLE VALVE"
    db.flush()
    derive_for_code(db, code, commit=True)

    block = psv.verification_block(db, code)
    assert block["state"] == psv.STATE_NEEDS_REVERIFY
    assert block["invalidated_reason"] == psv.REASON_VALUES_CHANGED


def test_derive_over_a_new_no_spec_copy_that_sorts_first_does_not_invalidate(db):
    """The before/after pair must come from the copy `current_values_hash` is defined
    on (the lowest product id holding a spec row), not from whichever copy iterates
    first. A verified code that gains a second company copy with no spec row yet -
    sorting FIRST in derivation's (company_id, id) order - must survive a re-derive
    that writes identical canonical values, rather than being withdrawn against an
    empty "before" (AC-D.3)."""
    code = unique_code("VS-NEWCOPY")
    with company_scope(db, None):
        _product(
            db,
            code,
            "SORENTO CERAMIC KITCHEN SINK",
            company_id=_REFS["company2"],
            product_id="ffffffff-0000-4000-8000-" + uuid.uuid4().hex[:12],
        )
        derive_for_code(db, code, commit=True)
    h1 = psv.current_values_hash(db, code)
    result = psv.verify_code(db, code, values_hash=h1, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    assert result["outcome"] == "verified"
    db.commit()

    # The default company's near-zero id sorts below `company2`'s random one, and the
    # low product id makes this copy the canonical read after it gains a spec row.
    with company_scope(db, None):
        _product(
            db,
            code,
            "SORENTO CERAMIC KITCHEN SINK",
            company_id=None,
            product_id="00000000-0000-4000-8000-" + uuid.uuid4().hex[:12],
        )
        derive_result = derive_for_code(db, code, commit=True)
    assert derive_result["written"] == 2, "the new copy forces a full write pass"

    block = psv.verification_block(db, code)
    assert block["state"] == psv.STATE_VERIFIED, (
        "identical canonical values re-written over a new empty copy must not "
        "withdraw the stamp"
    )


# --------------------------------------------------------------------------- #
# AC-D.4 - verify guards, same-transaction, distinguishable 409 taxonomy
# --------------------------------------------------------------------------- #
def test_verify_code_happy_path_inserts_one_row_with_values_hash(db):
    code = unique_code("VS-VERIFY-OK")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)

    result = psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    assert result["product_code"] == code
    assert result["outcome"] == "verified"
    assert result["values_hash"] == h
    assert result["verification"]["state"] == psv.STATE_VERIFIED
    rows = db.query(ProductSpecVerification).filter_by(product_code=code).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.party == psv.PARTY_INTERNAL
    assert row.values_hash == h
    assert row.verified_by_user_id == str(_ACTOR["id"])
    assert row.verified_by_name == _ACTOR["name"]
    assert row.invalidated_at is None


def test_verify_code_display_name_falls_back_to_email_when_the_actor_has_no_name(db):
    code = unique_code("VS-NONAME")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)

    psv.verify_code(db, code, values_hash=h, actor=_ACTOR_NO_NAME, party=psv.PARTY_INTERNAL)
    db.commit()

    row = db.query(ProductSpecVerification).filter_by(product_code=code).one()
    assert row.verified_by_name == _ACTOR_NO_NAME["email"]


def test_verify_code_wrong_hash_returns_values_changed_and_writes_nothing(db):
    code = unique_code("VS-STALEHASH")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    current = psv.current_values_hash(db, code)

    result = psv.verify_code(db, code, values_hash="0" * 64, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    assert result["outcome"] == "values_changed"
    assert result["values_hash"] == current, "the current hash is echoed so the caller can retry"
    assert db.query(ProductSpecVerification).filter_by(product_code=code).count() == 0


def test_verify_code_with_open_exceptions_verifies_normally(db):
    """Captain ruling 2026-08-17: there is no exceptions concept for the user, so
    there is no gate for one either. Open `ProductSpecException` rows stay as internal
    derivation data and do not stand between a reviewer and a code they have read."""
    code = unique_code("VS-OPENEXC")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    _open_exception(db, code)
    db.commit()

    result = psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    assert result["outcome"] == "verified"
    assert result["verification"]["state"] == psv.STATE_VERIFIED
    assert db.query(ProductSpecVerification).filter_by(product_code=code).count() == 1
    assert (
        db.query(ProductSpecException)
        .filter_by(product_code=code, resolved_at=None)
        .count()
        == 1
    ), "the exception row itself is untouched - it is derivation data, not a gate"


def test_verify_code_unknown_code_returns_not_found_never_raises(db):
    result = psv.verify_code(
        db, unique_code("VS-NOSUCH"), values_hash="x", actor=_ACTOR, party=psv.PARTY_INTERNAL
    )

    assert result["outcome"] == "not_found"


def test_verify_code_second_call_is_already_verified_with_exactly_one_active_row(db):
    """AC-D.4's concurrent-safety guarantee, exercised the way `blank_session`'s
    single outer transaction allows it to be: a genuinely concurrent two-session race
    is not achievable in this fixture (each `blank_session()` gets its own
    connection/transaction, invisible to any other until the outer transaction
    commits - which never happens here; see the identical note on
    `test_apply_spec_values_locks_existing_rows_with_for_update` in
    test_product_spec_authored_write.py). What IS pinned: a second `verify_code`
    call, committed after the first, must never leave a second active row - which is
    the observable contract AC-D.4 asks for, whichever internal path (the guard's own
    re-read, or a caught `IntegrityError` on the partial unique index) produces it."""
    code = unique_code("VS-DOUBLE")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    first = psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()
    assert first["outcome"] == "verified"

    second = psv.verify_code(db, code, values_hash=h, actor=_ACTOR_2, party=psv.PARTY_INTERNAL)
    db.commit()

    assert second["outcome"] == "already_verified"
    rows = db.query(ProductSpecVerification).filter_by(product_code=code, invalidated_at=None).all()
    assert len(rows) == 1
    assert rows[0].verified_by_user_id == str(_ACTOR["id"]), "the first verifier's stamp stands"


# --------------------------------------------------------------------------- #
# AC-D.16 - bulk verify, same guards, per-code outcomes
# --------------------------------------------------------------------------- #
def test_verify_codes_bulk_returns_per_code_outcomes_in_input_order(db):
    clean_code = unique_code("VS-BULK-CLEAN")
    exc_code = unique_code("VS-BULK-EXC")
    stale_code = unique_code("VS-BULK-STALE")
    unknown_code = unique_code("VS-BULK-UNKNOWN")

    _product(db, clean_code)
    _product(db, exc_code)
    _product(db, stale_code)
    derive_for_code(db, clean_code, commit=True)
    derive_for_code(db, exc_code, commit=True)
    derive_for_code(db, stale_code, commit=True)
    _open_exception(db, exc_code)
    db.commit()

    clean_hash = psv.current_values_hash(db, clean_code)
    exc_hash = psv.current_values_hash(db, exc_code)

    items = [
        {"product_code": clean_code, "values_hash": clean_hash},
        {"product_code": exc_code, "values_hash": exc_hash},
        {"product_code": stale_code, "values_hash": "0" * 64},
        {"product_code": unknown_code, "values_hash": "x"},
    ]
    results = psv.verify_codes_bulk(db, items, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    assert [r["product_code"] for r in results] == [clean_code, exc_code, stale_code, unknown_code]
    assert [r["outcome"] for r in results] == [
        "verified",
        # Open exceptions no longer refuse a verify (captain ruling 2026-08-17), so the
        # only skip a batch can report is a hash that moved, or a code that is not there.
        "verified",
        "values_changed",
        "not_found",
    ]
    assert db.query(ProductSpecVerification).filter_by(product_code=clean_code).count() == 1
    assert db.query(ProductSpecVerification).filter_by(product_code=exc_code).count() == 1
    assert db.query(ProductSpecVerification).filter_by(product_code=stale_code).count() == 0


# --------------------------------------------------------------------------- #
# AC-D.20 / D.21 / D.26 - unverify
# --------------------------------------------------------------------------- #
def test_unverify_a_verified_code_reads_unverified_not_needs_reverify_and_preserves_original_credit(db):
    code = unique_code("VS-UNV-1")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    result = psv.unverify_code(db, code, actor=_ACTOR_2, party=psv.PARTY_INTERNAL)
    db.commit()

    assert result["outcome"] == "unverified"
    assert result["verification"]["state"] == psv.STATE_UNVERIFIED
    row = db.query(ProductSpecVerification).filter_by(product_code=code).one()
    assert row.verified_by_name == _ACTOR["name"], "the original credit survives"
    assert row.verified_at is not None
    assert row.invalidated_reason == psv.REASON_MANUAL_UNVERIFY
    assert row.invalidated_by_user_id == str(_ACTOR_2["id"])
    assert row.invalidated_by_name == _ACTOR_2["name"]
    assert row.invalidated_diff is None, "a withdrawal has no diff"


def test_unverify_a_needs_reverify_code_overwrites_the_reason_and_clears_the_diff(db):
    code = unique_code("VS-UNV-NR")
    _product(db, code, "SORENTO CERAMIC KITCHEN SINK")
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()
    apply_spec_values(db, code, [{"spec_key": "mounting", "op": "set", "value": "wall_hung"}], actor=_ACTOR)
    pre = psv.verification_block(db, code)
    assert pre["state"] == psv.STATE_NEEDS_REVERIFY
    assert pre["invalidated_diff"] is not None

    result = psv.unverify_code(db, code, actor=_ACTOR_2, party=psv.PARTY_INTERNAL)
    db.commit()

    assert result["outcome"] == "unverified"
    row = db.query(ProductSpecVerification).filter_by(product_code=code).one()
    assert row.invalidated_reason == psv.REASON_MANUAL_UNVERIFY
    assert row.invalidated_diff is None
    assert row.invalidated_by_user_id == str(_ACTOR_2["id"])


def test_unverify_with_no_history_is_an_idempotent_no_op_not_an_error(db):
    code = unique_code("VS-UNV-NOHIST")
    _product(db, code)

    result = psv.unverify_code(db, code, actor=_ACTOR, party=psv.PARTY_INTERNAL)

    assert result["outcome"] == "no_change"
    assert result["verification"]["state"] == psv.STATE_UNVERIFIED


def test_unverify_an_already_withdrawn_code_is_a_no_op(db):
    code = unique_code("VS-UNV-ALREADY")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()
    psv.unverify_code(db, code, actor=_ACTOR_2, party=psv.PARTY_INTERNAL)
    db.commit()

    result = psv.unverify_code(db, code, actor=_ACTOR_2, party=psv.PARTY_INTERNAL)

    assert result["outcome"] == "no_change"


def test_reverify_after_a_withdrawal_inserts_a_new_row_and_leaves_the_withdrawn_one_intact(db):
    code = unique_code("VS-REVERIFY")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()
    psv.unverify_code(db, code, actor=_ACTOR_2, party=psv.PARTY_INTERNAL)
    db.commit()
    withdrawn = db.query(ProductSpecVerification).filter_by(product_code=code).one()
    withdrawn_id = withdrawn.id

    result = psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    assert result["outcome"] == "verified"
    rows = db.query(ProductSpecVerification).filter_by(product_code=code).all()
    assert len(rows) == 2
    old = next(r for r in rows if r.id == withdrawn_id)
    assert old.invalidated_reason == psv.REASON_MANUAL_UNVERIFY, "the withdrawn row is untouched"
    new = next(r for r in rows if r.id != withdrawn_id)
    assert new.invalidated_at is None


def test_internal_unverify_leaves_a_supplier_row_untouched(db):
    code = unique_code("VS-PARTYSAFE")
    _product(db, code)
    derive_for_code(db, code, commit=True)
    h = psv.current_values_hash(db, code)
    psv.verify_code(db, code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    supplier_row = _verification_row(db, code, party="supplier", verified_by_name="Supplier Contact")
    db.commit()

    psv.unverify_code(db, code, actor=_ACTOR_2, party=psv.PARTY_INTERNAL)
    db.commit()

    db.refresh(supplier_row)
    assert supplier_row.invalidated_at is None, "an internal withdrawal must not touch a supplier row"


def test_unverify_codes_bulk_mixed_outcomes(db):
    verified_code = unique_code("VS-UBULK-V")
    unverified_code = unique_code("VS-UBULK-U")
    _product(db, verified_code)
    _product(db, unverified_code)
    derive_for_code(db, verified_code, commit=True)
    h = psv.current_values_hash(db, verified_code)
    psv.verify_code(db, verified_code, values_hash=h, actor=_ACTOR, party=psv.PARTY_INTERNAL)
    db.commit()

    results = psv.unverify_codes_bulk(
        db, [verified_code, unverified_code], actor=_ACTOR_2, party=psv.PARTY_INTERNAL
    )
    db.commit()

    assert [r["product_code"] for r in results] == [verified_code, unverified_code]
    assert [r["outcome"] for r in results] == ["unverified", "no_change"]


# --------------------------------------------------------------------------- #
# AC-D.6 / D.7 / D.24 - the worklist
# --------------------------------------------------------------------------- #
@pytest.fixture
def worklist_codes(db):
    """One code in each state, plus a discontinued one and a class-B one, so the
    ordering/coverage/discontinued/summary/filter/sort tests can share a single
    fixture rather than rebuilding it per test."""
    _registry_key(db, "wl_material", data_type="enum", allowed_values=["ceramic", "brass"])
    _registry_key(db, "wl_mounting", data_type="enum", allowed_values=["wall_hung", "floor_standing"])
    _registry_key(db, "wl_shape", data_type="enum", allowed_values=["round", "square", "rectangular"])
    _registry_key(db, "wl_diameter", data_type="numeric", applies_when={"wl_shape": ["round", "square"]})
    _registry_key(db, "wl_legacy", data_type="enum", is_active=False)

    verified = _product(db, unique_code("WL-VERIFIED"), name="Verified Sink")
    _spec(db, verified, {"wl_material": {"value": "ceramic"}, "wl_mounting": {"value": "wall_hung"}})
    vh = psv.current_values_hash(db, verified.product_code)
    _verification_row(db, verified.product_code, values_hash=vh, verified_by_name="Reviewer One")

    needs_reverify = _product(db, unique_code("WL-NEEDSREVERIFY"), name="Needs Reverify Sink")
    _spec(db, needs_reverify, {"wl_material": {"value": "ceramic"}})
    _verification_row(
        db,
        needs_reverify.product_code,
        invalidated_at=datetime(2026, 1, 2, 9, 0, 0),
        invalidated_reason=psv.REASON_VALUES_CHANGED,
        invalidated_diff={
            "changed": [{"spec_key": "wl_material", "was": {"value": "brass"}, "now": {"value": "ceramic"}}]
        },
    )

    a1 = _product(db, unique_code("WL-A1"), name="Kitchen Sink A1")
    _spec(
        db,
        a1,
        {
            "wl_material": {"value": "ceramic"},
            "wl_mounting": {"value": "wall_hung"},
            "wl_shape": {"value": "rectangular"},
        },
    )
    _open_exception(db, a1.product_code, spec_key="wl_material")

    a2 = _product(db, unique_code("WL-A2"), name="SPECIAL Kitchen Fixture A2")
    _spec(db, a2, {"wl_shape": {"value": "round"}, "wl_diameter": {"value": 300}})

    b1 = _product(db, unique_code("WL-B1"), name="Bidet B1", category="cat_b")
    _spec(db, b1, {})

    discontinued = _product(db, unique_code("WL-DISC"), name="Discontinued Sink", discontinued=True)
    _spec(db, discontinued, {"wl_material": {"value": "ceramic"}})

    db.commit()
    return {
        "verified": verified.product_code,
        "needs_reverify": needs_reverify.product_code,
        "a1": a1.product_code,
        "a2": a2.product_code,
        "b1": b1.product_code,
        "discontinued": discontinued.product_code,
    }


def test_worklist_excludes_discontinued_codes_by_default_and_includes_them_on_request(db, worklist_codes):
    default = psv.worklist(db, page=1, limit=50)
    default_codes = {row["product_code"] for row in default["data"]}
    assert worklist_codes["discontinued"] not in default_codes

    included = psv.worklist(db, page=1, limit=50, include_discontinued=True)
    included_codes = {row["product_code"] for row in included["data"]}
    assert worklist_codes["discontinued"] in included_codes


def test_worklist_default_order_is_needs_reverify_then_unverified_by_class_then_code_then_verified(
    db, worklist_codes
):
    result = psv.worklist(db, page=1, limit=50)
    codes = [row["product_code"] for row in result["data"]]

    assert codes[0] == worklist_codes["needs_reverify"]
    assert codes[-1] == worklist_codes["verified"]
    assert set(codes[1:-1]) == {worklist_codes["a1"], worklist_codes["a2"], worklist_codes["b1"]}
    # a1 and a2 share a class_label ("Kitchen Sink"); grouped-by-class-then-code means
    # a1 must sort before a2 regardless of where the "Bidet" row (b1) lands relative
    # to that group - lexicographically deterministic since unique_code() keeps the
    # differing "A1"/"A2" segment ahead of the random suffix.
    assert codes.index(worklist_codes["a1"]) < codes.index(worklist_codes["a2"])


def test_worklist_row_carries_coverage_open_exceptions_and_values_hash(db, worklist_codes):
    result = psv.worklist(db, page=1, limit=50, include_discontinued=True)
    by_code = {row["product_code"]: row for row in result["data"]}

    a1 = by_code[worklist_codes["a1"]]
    assert _counts(a1["coverage"]) == {"have": 3, "applicable": 3}, (
        "wl_material + wl_mounting + wl_shape are applicable; wl_diameter's gate "
        "(shape in round/square) fails for 'rectangular'; wl_legacy is inactive"
    )
    assert a1["open_exceptions"] == 1
    assert a1["values_hash"] == psv.current_values_hash(db, worklist_codes["a1"])

    a2 = by_code[worklist_codes["a2"]]
    assert _counts(a2["coverage"]) == {"have": 2, "applicable": 4}, (
        "shape=round passes wl_diameter's gate, so all four active keys are applicable"
    )
    assert a2["open_exceptions"] == 0

    b1 = by_code[worklist_codes["b1"]]
    assert _counts(b1["coverage"]) == {"have": 0, "applicable": 3}

    verified = by_code[worklist_codes["verified"]]
    assert verified["verification"]["state"] == psv.STATE_VERIFIED
    assert verified["values_hash"] == psv.current_values_hash(db, worklist_codes["verified"])

    needs = by_code[worklist_codes["needs_reverify"]]
    assert needs["verification"]["state"] == psv.STATE_NEEDS_REVERIFY


def test_worklist_coverage_carries_the_itemised_keys_behind_the_have_over_applicable_figure(
    db, worklist_codes
):
    """Captain ruling 2026-08-17: the Coverage cell opens a tooltip listing the keys.

    Every APPLICABLE key is carried - filled ones with their stored entry, unfilled ones
    with `value: null`, because "we do not know this yet" is what the reviewer opened it
    for - and a key whose gate fails is absent entirely. Sorted by label, so the list
    reads the same way twice.
    """
    result = psv.worklist(db, page=1, limit=50)
    by_code = {row["product_code"]: row for row in result["data"]}

    a2 = by_code[worklist_codes["a2"]]["coverage"]
    assert len(a2["items"]) == a2["applicable"], (
        "the list and the denominator are the same rule; a count that disagreed with "
        "the list under it would be worse than either"
    )
    assert [item["spec_key"] for item in a2["items"]] == [
        "wl_diameter",
        "wl_material",
        "wl_mounting",
        "wl_shape",
    ], "sorted by label"
    by_key = {item["spec_key"]: item for item in a2["items"]}
    assert by_key["wl_shape"]["value"] == {"value": "round"}, "a filled key carries its entry"
    assert by_key["wl_diameter"]["value"] == {"value": 300}
    assert by_key["wl_material"]["value"] is None, "an unfilled applicable key is listed, empty"
    assert by_key["wl_mounting"]["value"] is None
    assert by_key["wl_material"]["label"] == "Wl Material", "the registry label, for a human"

    a1 = by_code[worklist_codes["a1"]]["coverage"]
    assert "wl_diameter" not in {item["spec_key"] for item in a1["items"]}, (
        "shape=rectangular fails wl_diameter's gate, so it is not applicable and not listed"
    )
    assert "wl_legacy" not in {item["spec_key"] for item in a1["items"]}, "inactive keys never apply"
    assert all(item["value"] is not None for item in a1["items"])


def test_worklist_summary_counts_the_default_filtered_set_and_ignores_only_the_state_filter(
    db, worklist_codes
):
    unfiltered = psv.worklist(db, page=1, limit=50)
    assert unfiltered["summary"] == {"total": 5, "verified": 1, "needs_reverify": 1, "unverified": 3}

    with_discontinued = psv.worklist(db, page=1, limit=50, include_discontinued=True)
    assert with_discontinued["summary"] == {
        "total": 6,
        "verified": 1,
        "needs_reverify": 1,
        "unverified": 4,
    }

    state_filtered = psv.worklist(db, page=1, limit=50, state="unverified")
    assert len(state_filtered["data"]) == 3
    assert state_filtered["summary"] == unfiltered["summary"], (
        "the state filter must not narrow the summary, or 'Verified N of M' lies "
        "under a state filter (AC-D.6)"
    )


def test_worklist_class_label_filter_narrows_both_data_and_summary(db, worklist_codes):
    result = psv.worklist(db, page=1, limit=50, class_label="Bidet")

    assert {row["product_code"] for row in result["data"]} == {worklist_codes["b1"]}
    assert result["summary"]["total"] == 1, "unlike state, class_label DOES narrow the summary"


def test_worklist_classes_lists_distinct_sorted_class_labels_and_never_null(db, worklist_codes):
    """The class filter's own options, so the dropdown has real data to offer.

    The registry's `class` key is deliberately open-vocabulary (empty allowed_values),
    so the labels have to come from the same expression the list itself groups by.
    """
    _product(db, unique_code("WL-NOCLASS"), name="Unclassified", category="cat_none")
    db.commit()

    result = psv.worklist(db, page=1, limit=50)

    assert result["classes"] == ["Bidet", "Kitchen Sink"], (
        "distinct, sorted, and a code whose category carries no class contributes nothing"
    )


def test_worklist_classes_survive_the_class_and_state_filters(db, worklist_codes):
    """Filtering to one class must not empty the dropdown that did the filtering."""
    filtered = psv.worklist(db, page=1, limit=50, class_label="Bidet", state="unverified")

    assert filtered["classes"] == ["Bidet", "Kitchen Sink"]
    assert {row["product_code"] for row in filtered["data"]} == {worklist_codes["b1"]}


def test_worklist_classes_exclude_a_class_only_a_discontinued_code_carries(db, worklist_codes):
    _product(db, unique_code("WL-DISC-SH"), name="Discontinued Shower", category="cat_c", discontinued=True)
    db.commit()

    assert "Shower Set" not in psv.worklist(db, page=1, limit=50)["classes"]
    assert "Shower Set" in psv.worklist(db, page=1, limit=50, include_discontinued=True)["classes"]


def test_worklist_query_searches_code_and_name(db, worklist_codes):
    by_code = psv.worklist(db, page=1, limit=50, query=worklist_codes["a1"])
    assert {row["product_code"] for row in by_code["data"]} == {worklist_codes["a1"]}

    by_name = psv.worklist(db, page=1, limit=50, query="SPECIAL")
    assert {row["product_code"] for row in by_name["data"]} == {worklist_codes["a2"]}


def test_worklist_sort_coverage_orders_by_have_ascending_then_descending(db, worklist_codes):
    ascending = psv.worklist(db, page=1, limit=50, state="unverified", sort="coverage", direction="asc")
    assert [row["product_code"] for row in ascending["data"]] == [
        worklist_codes["b1"],  # have=0
        worklist_codes["a2"],  # have=2
        worklist_codes["a1"],  # have=3
    ]

    descending = psv.worklist(db, page=1, limit=50, state="unverified", sort="coverage", direction="desc")
    assert [row["product_code"] for row in descending["data"]] == [
        worklist_codes["a1"],
        worklist_codes["a2"],
        worklist_codes["b1"],
    ]


def test_worklist_paginates_with_total_page_and_limit(db, worklist_codes):
    page1 = psv.worklist(db, page=1, limit=3)
    assert page1["pagination"] == {"total": 5, "page": 1, "limit": 3}
    assert len(page1["data"]) == 3

    page2 = psv.worklist(db, page=2, limit=3)
    assert page2["pagination"] == {"total": 5, "page": 2, "limit": 3}
    assert len(page2["data"]) == 2


def test_worklist_resolves_a_two_company_code_to_the_copy_in_the_callers_scope(db):
    code = unique_code("WL-XCOPY")
    with company_scope(db, None):
        p_default = _product(db, code, name="Cross Copy")
        p_company2 = _product(db, code, name="Cross Copy", company_id=_REFS["company2"])
    db.commit()

    with company_scope(db, frozenset({_REFS["company2"]})):
        result = psv.worklist(db, page=1, limit=50, query=code)

        assert len(result["data"]) == 1
        assert result["data"][0]["product_id"] == p_company2.id
        assert result["data"][0]["product_id"] != p_default.id


# --------------------------------------------------------------------------- #
# review round 2 - the writer lock, one hash source, the class gate
# --------------------------------------------------------------------------- #
def test_derive_for_code_writes_a_code_that_holds_no_spec_row_yet(db):
    """Smoke for the product-row lock `derive_for_code` now takes.

    The race it closes (two writers creating the FIRST spec row for a code at once)
    needs two concurrent transactions and is not unit-testable; what IS testable, and
    what a lock on the code's product rows rather than on its spec row could break, is
    the ordinary write of a code that has no spec row to lock.
    """
    code = unique_code("VS-LOCK-DERIVE")
    product = _product(db, code)
    assert db.query(ProductSpecifications).filter_by(product_id=product.id).count() == 0

    derive_for_code(db, code, commit=True)

    assert db.query(ProductSpecifications).filter_by(product_id=product.id).count() == 1


def test_apply_spec_values_writes_a_code_that_holds_no_spec_row_yet(db):
    """The other half of the same smoke: the authored write takes the same lock."""
    code = unique_code("VS-LOCK-APPLY")
    product = _product(db, code)
    assert db.query(ProductSpecifications).filter_by(product_id=product.id).count() == 0

    apply_spec_values(
        db, code, [{"spec_key": "mounting", "op": "set", "value": "wall_hung"}], actor=_ACTOR
    )

    spec = db.query(ProductSpecifications).filter_by(product_id=product.id).one()
    assert spec.values["mounting"]["value"] == "wall_hung"


def test_worklist_hashes_the_copy_the_verify_guard_hashes(db):
    """One answer to "what does this code currently say", whoever is asking.

    The listing de-duplicates to the lowest product id IN SCOPE; `current_values_hash`
    and `verify_code` read the lowest id of ALL companies. Where the copies have
    drifted, a row hashed from the scoped copy would be refused by the verify guard for
    ever, with a "changed while you were reviewing" that no reload can clear.
    """
    code = unique_code("WL-HASHSRC")
    low_id, high_id = sorted(str(uuid.uuid4()) for _ in range(2))
    with company_scope(db, None):
        low = _product(db, code, name="Hash Source", product_id=low_id)
        high = _product(
            db,
            code,
            name="Hash Source",
            product_id=high_id,
            company_id=_REFS["company2"],
        )
        _spec(db, low, {"wl_material": {"value": "ceramic"}})
        _spec(db, high, {"wl_material": {"value": "brass"}})
    db.commit()

    with company_scope(db, frozenset({_REFS["company2"]})):
        result = psv.worklist(db, page=1, limit=50, query=code)
        assert len(result["data"]) == 1
        row = result["data"][0]
        # Still the copy the caller can actually open ...
        assert row["product_id"] == high.id
        # ... but hashed from the copy the guard reads.
        assert row["values_hash"] == psv.current_values_hash(db, code)

        verified = psv.verify_code(db, code, values_hash=row["values_hash"], actor=_ACTOR)
    db.commit()

    assert verified["outcome"] == "verified", "the hash the list showed must be verifiable"


def test_worklist_skips_a_lowest_id_copy_that_has_no_spec_row_yet(db):
    """A copy created before the next write fans out has no spec row of its own.

    The guard hashes the lowest id that HAS a spec row; if the list hashed the lowest id
    regardless, a code whose lowest-id copy is still bare would echo hash({}) and every
    Verify from the list would be refused with values_changed until that copy caught up.
    """
    code = unique_code("WL-BARECOPY")
    low_id, high_id = sorted(str(uuid.uuid4()) for _ in range(2))
    with company_scope(db, None):
        _product(db, code, name="Bare Copy", product_id=low_id, company_id=_REFS["company2"])
        with_spec = _product(db, code, name="Bare Copy", product_id=high_id)
        _spec(db, with_spec, {"wl_material": {"value": "ceramic"}})
    db.commit()

    result = psv.worklist(db, page=1, limit=50, query=code)
    assert len(result["data"]) == 1
    row = result["data"][0]
    assert row["values_hash"] == psv.current_values_hash(db, code)
    assert row["values_hash"] != psv.canonical_values_hash({})

    verified = psv.verify_code(db, code, values_hash=row["values_hash"], actor=_ACTOR)
    db.commit()
    assert verified["outcome"] == "verified"


def test_applicable_counts_a_key_gated_on_a_class_the_category_supplies(db):
    """A gate on `class` reads the same class the Class column shows.

    Derivation only writes a `class` value when it reads one, so for most products the
    class comes from the category. A gate that looked only at `values['class']` failed
    for those products and told the reviewer a kitchen sink needs fewer specs than it
    does.
    """
    _registry_key(db, "cg_material", data_type="enum", allowed_values=["ceramic"])
    _registry_key(db, "cg_trap", data_type="enum", applies_when={"class": ["kitchen sink"]})

    sink = _product(db, unique_code("WL-CLASSGATE-KS"), name="Class Gate Sink")
    _spec(db, sink, {"cg_material": {"value": "ceramic"}})
    bidet = _product(db, unique_code("WL-CLASSGATE-BD"), name="Class Gate Bidet", category="cat_b")
    _spec(db, bidet, {"cg_material": {"value": "ceramic"}})
    db.commit()

    rows = {
        row["product_code"]: row
        for row in psv.worklist(db, page=1, limit=50, query="WL-CLASSGATE")["data"]
    }

    assert _counts(rows[sink.product_code]["coverage"]) == {"have": 1, "applicable": 2}, (
        "the category says Kitchen Sink, so the gated trap key counts"
    )
    assert _counts(rows[bidet.product_code]["coverage"]) == {"have": 1, "applicable": 1}, (
        "a Bidet does not carry the gated key"
    )
