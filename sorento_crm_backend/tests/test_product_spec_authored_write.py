"""`apply_spec_values` against a real Postgres schema - the authored write path.

Contract: PR1-CONTRACT.md section 1.5. UAC: AC-F.2, AC-F.4, AC-F.5, AC-F.12, AC-D.17
(the PR-1 half - the authored-key flag filter).

Fixture shape follows `tests/test_product_spec_derivation.py` (`db` fixture, `_fixtures`,
`_product`) per the tester brief. `app.services.product_spec_write` does not exist yet,
so the module-level import below fails at collection - that IS the expected red state.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecException, ProductSpecifications
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_derivation import derive_for_code
from app.services.product_spec_write import apply_spec_values
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        _fixtures(s)
        yield s


def _fixtures(db):
    """Category, brand and UOM every product row needs, plus a second company for
    the fan-out tests - mirrors `test_product_spec_derivation.py::_fixtures`."""
    cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-AW-KS", category_name="ZZT-AW-KS")
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-AW-PCS", uom_name="Piece")
    brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-AW-SRT", brand_name="Sorento")
    second = Company(id=str(uuid.uuid4()), name="ZZT AW Second Co", code="ZZT-AW2")
    db.add_all([cat, uom, brand, second])
    db.flush()
    backfill_category_signals(db)
    _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id, "company2": second.id})


def _product(
    db,
    code: str,
    description: str = "SORENTO CERAMIC KITCHEN SINK",
    *,
    length=None,
    width=None,
    height=None,
    company_id=None,
) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=description,
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
        dimensions_length=length,
        dimensions_width=width,
        dimensions_height=height,
    )
    if company_id is not None:
        row.company_id = company_id
    db.add(row)
    db.flush()
    return row


def _specs_for(db, code: str) -> list[ProductSpecifications]:
    return (
        db.query(ProductSpecifications)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(Product.product_code == code)
        .all()
    )


def _one_spec(db, code: str) -> ProductSpecifications:
    rows = _specs_for(db, code)
    assert len(rows) == 1, f"expected exactly one row for {code}, found {len(rows)}"
    return rows[0]


def _open_exceptions(db, code: str) -> list[ProductSpecException]:
    return (
        db.query(ProductSpecException)
        .filter(
            ProductSpecException.product_code == code,
            ProductSpecException.resolved_at.is_(None),
        )
        .all()
    )


def _open_reasons(db, code: str) -> set[str]:
    return {e.reason for e in _open_exceptions(db, code)}


_ACTOR = {"email": "spec-tester@zzt.test"}


# --------------------------------------------------------------------------- #
# AC-F.4 - fan-out to every company copy
# --------------------------------------------------------------------------- #
def test_a_hand_set_value_fans_out_to_every_company_copy(db):
    with company_scope(db, None):
        _product(db, "ZZT-AW-FANOUT-1")
        _product(db, "ZZT-AW-FANOUT-1", company_id=_REFS["company2"])
        derive_for_code(db, "ZZT-AW-FANOUT-1")

        apply_spec_values(
            db,
            "ZZT-AW-FANOUT-1",
            [{"spec_key": "material", "op": "set", "value": "brass"}],
            actor=_ACTOR,
        )

        specs = _specs_for(db, "ZZT-AW-FANOUT-1")
        assert len(specs) == 2
        assert all(s.values["material"]["value"] == "brass" for s in specs)
        assert all(s.provenance["material"]["source"] == "human" for s in specs)


def test_fan_out_does_not_require_the_caller_to_hold_the_all_companies_scope(db):
    """The contract puts `with company_scope(db, None):` INSIDE apply_spec_values, so
    it must fan out even when the caller is sitting in the default (single-company)
    scope - unlike `derive_for_code`, which deliberately stays inside its caller's
    scope."""
    with company_scope(db, None):
        _product(db, "ZZT-AW-FANOUT-2")
        _product(db, "ZZT-AW-FANOUT-2", company_id=_REFS["company2"])
        derive_for_code(db, "ZZT-AW-FANOUT-2")

    # Back to the default (Sorento-only) scope for the call under test.
    apply_spec_values(
        db,
        "ZZT-AW-FANOUT-2",
        [{"spec_key": "material", "op": "set", "value": "brass"}],
        actor=_ACTOR,
    )

    with company_scope(db, None):
        specs = _specs_for(db, "ZZT-AW-FANOUT-2")
        assert len(specs) == 2
        assert all(s.values["material"]["value"] == "brass" for s in specs)


# --------------------------------------------------------------------------- #
# AC-F.12 - derived_hash cleared, re-derived in the same call
# --------------------------------------------------------------------------- #
def test_a_conflicting_authored_write_surfaces_its_exception_in_the_same_call(db):
    """AC-F.12 - derived_hash is cleared on write and the code is re-derived in the
    same transaction, so a conflict is visible without a second call. Without the
    clear, derivation's skip-if-unchanged path (product_spec_derivation.py:1262)
    would suppress the conflict computation entirely."""
    _product(db, "ZZT-AW-HASH-1")
    derive_for_code(db, "ZZT-AW-HASH-1")
    assert _one_spec(db, "ZZT-AW-HASH-1").values["material"]["value"] == "ceramic"
    assert _open_reasons(db, "ZZT-AW-HASH-1") == set()

    apply_spec_values(
        db,
        "ZZT-AW-HASH-1",
        [{"spec_key": "material", "op": "set", "value": "brass"}],
        actor=_ACTOR,
    )

    spec = _one_spec(db, "ZZT-AW-HASH-1")
    assert spec.values["material"]["value"] == "brass", "the authored value stays in force"
    assert "human_override_conflict" in _open_reasons(db, "ZZT-AW-HASH-1")


def test_a_non_conflicting_authored_write_leaves_no_exception(db):
    _product(db, "ZZT-AW-HASH-2")
    derive_for_code(db, "ZZT-AW-HASH-2")

    apply_spec_values(
        db,
        "ZZT-AW-HASH-2",
        [{"spec_key": "mounting", "op": "set", "value": "wall_hung"}],
        actor=_ACTOR,
    )

    assert _open_reasons(db, "ZZT-AW-HASH-2") == set()


# --------------------------------------------------------------------------- #
# AC-F.2 - a tombstone survives a LATER, separate derive_for_code call
# --------------------------------------------------------------------------- #
def test_a_tombstoned_key_does_not_reappear_on_a_later_derive(db):
    _product(db, "ZZT-AW-TOMB-1")
    derive_for_code(db, "ZZT-AW-TOMB-1")
    assert _one_spec(db, "ZZT-AW-TOMB-1").values["material"]["value"] == "ceramic"

    apply_spec_values(
        db,
        "ZZT-AW-TOMB-1",
        [{"spec_key": "material", "op": "absent"}],
        actor=_ACTOR,
    )

    spec = _one_spec(db, "ZZT-AW-TOMB-1")
    assert "material" not in spec.values
    assert spec.provenance["material"]["source"] == "human"
    assert spec.provenance["material"]["absent"] is True

    # A later, independent derive_for_code run must not resurrect it.
    derive_for_code(db, "ZZT-AW-TOMB-1")
    spec_after = _one_spec(db, "ZZT-AW-TOMB-1")
    assert "material" not in spec_after.values
    assert spec_after.provenance["material"]["absent"] is True


# --------------------------------------------------------------------------- #
# revert hands the key back to derivation
# --------------------------------------------------------------------------- #
def test_revert_hands_the_key_back_to_derivation(db):
    """The op that is broken today: the old clear route relied on a derive_for_code
    call that takes the derived_hash skip path and never actually restores anything."""
    _product(db, "ZZT-AW-REVERT-1")
    derive_for_code(db, "ZZT-AW-REVERT-1")

    apply_spec_values(
        db,
        "ZZT-AW-REVERT-1",
        [{"spec_key": "material", "op": "set", "value": "brass"}],
        actor=_ACTOR,
    )
    assert _one_spec(db, "ZZT-AW-REVERT-1").values["material"]["value"] == "brass"

    apply_spec_values(
        db,
        "ZZT-AW-REVERT-1",
        [{"spec_key": "material", "op": "revert"}],
        actor=_ACTOR,
    )

    spec = _one_spec(db, "ZZT-AW-REVERT-1")
    assert spec.values["material"]["value"] == "ceramic", "reverted to what derivation reads"
    assert spec.provenance["material"]["source"] == "derived"
    assert _open_reasons(db, "ZZT-AW-REVERT-1") == set(), "no lingering conflict once reverted"


def test_revert_removes_the_key_from_both_values_and_provenance_when_derivation_has_nothing(db):
    # "is_smart" is never derived for a plain kitchen sink description, so reverting
    # a hand-set value for it must leave the key absent from both maps entirely,
    # not merely reset to some default.
    _product(db, "ZZT-AW-REVERT-2")
    derive_for_code(db, "ZZT-AW-REVERT-2")
    assert "is_smart" not in _one_spec(db, "ZZT-AW-REVERT-2").values

    apply_spec_values(
        db,
        "ZZT-AW-REVERT-2",
        [{"spec_key": "is_smart", "op": "set", "value": True}],
        actor=_ACTOR,
    )
    assert _one_spec(db, "ZZT-AW-REVERT-2").values["is_smart"]["value"] is True

    apply_spec_values(
        db,
        "ZZT-AW-REVERT-2",
        [{"spec_key": "is_smart", "op": "revert"}],
        actor=_ACTOR,
    )

    spec = _one_spec(db, "ZZT-AW-REVERT-2")
    assert "is_smart" not in spec.values
    assert "is_smart" not in spec.provenance


# --------------------------------------------------------------------------- #
# AC-F.5 - one conflict per CODE, not once per company copy
# --------------------------------------------------------------------------- #
def test_a_conflict_is_raised_once_per_code_never_once_per_company_copy(db):
    with company_scope(db, None):
        _product(db, "ZZT-AW-ONCE-1")
        _product(db, "ZZT-AW-ONCE-1", company_id=_REFS["company2"])
        derive_for_code(db, "ZZT-AW-ONCE-1")

        apply_spec_values(
            db,
            "ZZT-AW-ONCE-1",
            [{"spec_key": "material", "op": "set", "value": "brass"}],
            actor=_ACTOR,
        )

        conflicts = [
            e
            for e in _open_exceptions(db, "ZZT-AW-ONCE-1")
            if e.reason == "human_override_conflict"
        ]
        assert len(conflicts) == 1


# --------------------------------------------------------------------------- #
# AC-D.17 - THE FLAG FILTER (the PR-1 half): an authored key's flag stops re-raising
# --------------------------------------------------------------------------- #
def test_authoring_the_flagged_key_suppresses_its_exception_and_reverting_brings_it_back(db):
    """The 1500x1500 shape - length == width is the fingerprint of a round or square
    product forced into rectangular columns (product_spec_derivation.py:1042-1051),
    pinned by test_product_spec_derivation.py::test_equal_length_and_width_is_flagged.
    """
    _product(
        db,
        "ZZT-AW-SHAPE-1",
        "SORENTO ART BASIN",
        length=Decimal("1500"),
        width=Decimal("1500"),
        height=Decimal("140"),
    )
    derive_for_code(db, "ZZT-AW-SHAPE-1")
    assert "shape_mismatch" in _open_reasons(db, "ZZT-AW-SHAPE-1")

    apply_spec_values(
        db,
        "ZZT-AW-SHAPE-1",
        [{"spec_key": "shape", "op": "set", "value": "square"}],
        actor=_ACTOR,
    )
    assert "shape_mismatch" not in _open_reasons(db, "ZZT-AW-SHAPE-1"), (
        "answering shape by hand must stop the flag re-raising on the same re-derive"
    )

    apply_spec_values(
        db,
        "ZZT-AW-SHAPE-1",
        [{"spec_key": "shape", "op": "revert"}],
        actor=_ACTOR,
    )
    assert "shape_mismatch" in _open_reasons(db, "ZZT-AW-SHAPE-1"), (
        "handing the key back to derivation must let the flag come back"
    )


def test_a_tombstone_on_the_flagged_key_also_suppresses_the_flag(db):
    """A tombstone is an answer too - its provenance source is in AUTHORED_SOURCES."""
    _product(
        db,
        "ZZT-AW-SHAPE-2",
        "SORENTO ART BASIN",
        length=Decimal("1500"),
        width=Decimal("1500"),
        height=Decimal("140"),
    )
    derive_for_code(db, "ZZT-AW-SHAPE-2")
    assert "shape_mismatch" in _open_reasons(db, "ZZT-AW-SHAPE-2")

    apply_spec_values(
        db,
        "ZZT-AW-SHAPE-2",
        [{"spec_key": "shape", "op": "absent"}],
        actor=_ACTOR,
    )

    assert "shape_mismatch" not in _open_reasons(db, "ZZT-AW-SHAPE-2")


# --------------------------------------------------------------------------- #
# Batch - one call, several entries, one re-derive
# --------------------------------------------------------------------------- #
def test_a_batch_call_applies_every_entry(db):
    _product(db, "ZZT-AW-BATCH-1")
    derive_for_code(db, "ZZT-AW-BATCH-1")

    result = apply_spec_values(
        db,
        "ZZT-AW-BATCH-1",
        [
            {"spec_key": "material", "op": "set", "value": "brass"},
            {"spec_key": "mounting", "op": "set", "value": "wall_hung"},
        ],
        actor=_ACTOR,
    )

    spec = _one_spec(db, "ZZT-AW-BATCH-1")
    assert spec.values["material"]["value"] == "brass"
    assert spec.values["mounting"]["value"] == "wall_hung"
    assert result["rows_written"] == 1
    assert set(result["spec_keys"]) == {"material", "mounting"}


def test_a_batch_call_re_derives_exactly_once(db, monkeypatch):
    """AC-B.9's rationale, exercised at PR1's ground floor: N calls would cost N
    re-derives; one batch call must cost exactly one.

    The seed is committed BEFORE the spy is installed, on purpose: whenever an
    earlier test in the process has already called register_product_spec_listeners()
    (any test that boots the FastAPI app does), a still-pending Product insert is
    collected by that listener and re-derived again in its own after_commit hook -
    a second, genuine call that has nothing to do with the batch under test, and
    would otherwise get counted by the spy below and fail this assertion for the
    wrong reason (order-dependent: green per file, red in CI's single-process run).
    Committing here first means nothing is pending on the Product row when
    apply_spec_values commits, so the spy only ever sees calls apply_spec_values
    itself made.
    """
    import app.services.product_spec_derivation as derivation

    _product(db, "ZZT-AW-BATCH-2")
    derive_for_code(db, "ZZT-AW-BATCH-2")
    db.commit()

    calls: list[str] = []
    original = derivation.derive_for_code

    def _counting(*args, **kwargs):
        calls.append("call")
        return original(*args, **kwargs)

    monkeypatch.setattr(derivation, "derive_for_code", _counting)

    apply_spec_values(
        db,
        "ZZT-AW-BATCH-2",
        [
            {"spec_key": "material", "op": "set", "value": "brass"},
            {"spec_key": "mounting", "op": "set", "value": "wall_hung"},
        ],
        actor=_ACTOR,
    )

    assert len(calls) == 1, "a batch of two entries must re-derive exactly once, not per key"


# --------------------------------------------------------------------------- #
# not-found
# --------------------------------------------------------------------------- #
def test_a_code_with_no_product_rows_raises_the_apps_not_found_error(db):
    from app.services.error_handler import AppException

    with pytest.raises(AppException):
        apply_spec_values(
            db,
            "ZZT-AW-DOES-NOT-EXIST",
            [{"spec_key": "material", "op": "set", "value": "brass"}],
            actor=_ACTOR,
        )


def test_a_code_with_no_product_rows_raises_not_found_even_with_an_empty_batch(db):
    """N1 - the contract's empty-batch return (`{"rows_written": 0, ...}`) sits INSIDE
    the all-companies scope, AFTER the not-found check, so an unknown code 404s
    whether or not the caller had anything to write. A 404-or-200 that turns on the
    length of the batch is a contract nobody can code against."""
    from app.services.error_handler import AppException

    with pytest.raises(AppException):
        apply_spec_values(db, "ZZT-AW-EMPTY-DOES-NOT-EXIST", [], actor=_ACTOR)


# --------------------------------------------------------------------------- #
# source: supplier, end to end (coverage the coder flagged as still missing)
# --------------------------------------------------------------------------- #
def test_source_supplier_writes_through_apply_spec_values_end_to_end(db):
    """M2-S1 - 'supplier' is reserved now but must already behave exactly like
    'human' through the real write path: authored status, survives re-derivation,
    boosted like a human entry (asserted separately in
    test_product_spec_search_boost.py).

    "mounting" rather than "material", deliberately: derivation never produces a
    value for "mounting" from a plain kitchen-sink description (same choice
    `test_a_non_conflicting_authored_write_leaves_no_exception` makes), so this
    isolates the source label from AC-F.5's conflict behaviour, which is pinned
    separately."""
    _product(db, "ZZT-AW-SUPPLIER-1")
    derive_for_code(db, "ZZT-AW-SUPPLIER-1")
    assert "mounting" not in _one_spec(db, "ZZT-AW-SUPPLIER-1").values

    apply_spec_values(
        db,
        "ZZT-AW-SUPPLIER-1",
        [{"spec_key": "mounting", "op": "set", "value": "wall_hung", "source": "supplier"}],
        actor=_ACTOR,
    )

    spec = _one_spec(db, "ZZT-AW-SUPPLIER-1")
    assert spec.values["mounting"]["value"] == "wall_hung"
    assert spec.provenance["mounting"]["source"] == "supplier"
    assert spec.status == "authored"
    assert _open_reasons(db, "ZZT-AW-SUPPLIER-1") == set()

    # A later, independent derive must not resurrect anything - the same promise a
    # human-sourced entry gets.
    derive_for_code(db, "ZZT-AW-SUPPLIER-1")
    spec_after = _one_spec(db, "ZZT-AW-SUPPLIER-1")
    assert spec_after.values["mounting"]["value"] == "wall_hung"
    assert spec_after.provenance["mounting"]["source"] == "supplier"


# --------------------------------------------------------------------------- #
# a batch mixing set / absent / revert in one call (coverage the coder flagged)
# --------------------------------------------------------------------------- #
def test_a_batch_mixing_set_absent_and_revert_applies_all_three_ops_in_one_call(db):
    _product(db, "ZZT-AW-MIX-1")
    derive_for_code(db, "ZZT-AW-MIX-1")

    # First hand-set two keys so absent/revert in the batch under test have something
    # to act on.
    apply_spec_values(
        db,
        "ZZT-AW-MIX-1",
        [
            {"spec_key": "mounting", "op": "set", "value": "wall_hung"},
            {"spec_key": "is_smart", "op": "set", "value": True},
        ],
        actor=_ACTOR,
    )

    result = apply_spec_values(
        db,
        "ZZT-AW-MIX-1",
        [
            {"spec_key": "material", "op": "set", "value": "brass"},
            {"spec_key": "mounting", "op": "absent"},
            {"spec_key": "is_smart", "op": "revert"},
        ],
        actor=_ACTOR,
    )

    spec = _one_spec(db, "ZZT-AW-MIX-1")
    assert spec.values["material"]["value"] == "brass", "set applied"
    assert "mounting" not in spec.values, "absent removed the value"
    assert spec.provenance["mounting"]["absent"] is True
    assert "is_smart" not in spec.values, "revert removed the value entirely"
    assert "is_smart" not in spec.provenance
    assert set(result["spec_keys"]) == {"material", "mounting", "is_smart"}


# --------------------------------------------------------------------------- #
# a code whose company copies start with diverging stored values
# --------------------------------------------------------------------------- #
def test_a_batch_write_converges_company_copies_that_started_diverged(db):
    """M3 measured zero diverging company copies in production - the UAC's own
    instruction is that every test must manufacture the changed case rather than
    rely on finding one. Two copies are hand-diverged (direct assignment, acceptable
    in tests per tests/test_product_spec_search.py:983-984) to set up the starting
    condition apply_spec_values must not be able to produce on its own; the write
    under test then converges both."""
    with company_scope(db, None):
        p1 = _product(db, "ZZT-AW-DIVERGE-1")
        p2 = _product(db, "ZZT-AW-DIVERGE-1", company_id=_REFS["company2"])
        derive_for_code(db, "ZZT-AW-DIVERGE-1")

        spec1 = db.query(ProductSpecifications).filter_by(product_id=p1.id).first()
        spec2 = db.query(ProductSpecifications).filter_by(product_id=p2.id).first()
        spec1.values = {**spec1.values, "material": {"value": "brass"}}
        spec1.provenance = {
            **spec1.provenance,
            "material": {"source": "human", "confidence": 1.0, "evidence": "old copy 1"},
        }
        spec2.values = {**spec2.values, "material": {"value": "steel"}}
        spec2.provenance = {
            **spec2.provenance,
            "material": {"source": "human", "confidence": 1.0, "evidence": "old copy 2"},
        }
        db.flush()

        apply_spec_values(
            db,
            "ZZT-AW-DIVERGE-1",
            [{"spec_key": "material", "op": "set", "value": "ceramic"}],
            actor=_ACTOR,
        )

        specs = _specs_for(db, "ZZT-AW-DIVERGE-1")
        assert len(specs) == 2
        assert all(s.values["material"]["value"] == "ceramic" for s in specs), (
            "apply_spec_values overwrites both copies identically, converging the "
            "divergence they started with"
        )
        assert all(s.provenance["material"]["source"] == "human" for s in specs)


# --------------------------------------------------------------------------- #
# 6b.4 - the row lock apply_spec_values takes on the existing-rows read
# --------------------------------------------------------------------------- #
def test_apply_spec_values_locks_existing_rows_with_for_update(db):
    """A genuinely deterministic two-session interleaving test is not achievable
    inside `blank_session`'s fixture: every write in a test lives in ONE uncommitted
    outer transaction on one connection (rolled back at teardown), so a second real
    session opened against the same blank schema would not even see the row to
    contend for it - there is nothing to lock against, and a test built around
    "sleep, then check" would be passing by timing, which CLAUDE.md rules out
    explicitly. Stated plainly per the tester brief rather than skipped silently.

    What IS asserted: the SELECT that reads existing spec rows is compiled with
    `FOR UPDATE`, which is the actual mechanism a real lost update between two
    sessions would be blocked by.
    """
    from sqlalchemy import event

    _product(db, "ZZT-AW-LOCK-1")
    derive_for_code(db, "ZZT-AW-LOCK-1")

    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", _capture)
    try:
        apply_spec_values(
            db,
            "ZZT-AW-LOCK-1",
            [{"spec_key": "material", "op": "set", "value": "brass"}],
            actor=_ACTOR,
        )
    finally:
        event.remove(bind, "before_cursor_execute", _capture)

    locked = [
        s
        for s in statements
        if "for update" in s.lower() and "product_specifications" in s.lower()
    ]
    assert locked, "the existing-rows read in apply_spec_values must take FOR UPDATE"
