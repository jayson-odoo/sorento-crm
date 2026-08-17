"""AC-F.13 - the bypass backstop.

A write to `spec.values` / `spec.provenance` / `spec.rendered_text` made AROUND the
service (`write_spec_row`) must be detected and logged, post-commit. It is a backstop,
not the primary path (PR1-CONTRACT.md section 5): it never raises and never blocks the
write, and a write made THROUGH `write_spec_row` must produce no warning at all.

`app.services.product_spec_write` does not exist yet, so every import below fails at
collection - that IS the expected red state.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal

import pytest

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_write import register_spec_write_backstop, write_spec_row
from tests._pg_fixture import blank_session

_REFS: dict = {}


@pytest.fixture
def db():
    with blank_session() as s:
        cat = ProductCategory(id=str(uuid.uuid4()), category_code="ZZT-BS-KS", category_name="ZZT-BS-KS")
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-BS-PCS", uom_name="Piece")
        brand = Brand(id=str(uuid.uuid4()), brand_code="ZZT-BS-SRT", brand_name="SORENTO")
        s.add_all([cat, uom, brand])
        s.flush()
        backfill_category_signals(s)
        _REFS.update({"cat": cat.id, "uom": uom.id, "brand": brand.id})
        yield s


def _product(db, code: str) -> Product:
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description="SORENTO CERAMIC KITCHEN SINK",
        category_id=_REFS["cat"],
        base_uom_id=_REFS["uom"],
        brand_id=_REFS["brand"],
        list_price=Decimal("1.00"),
    )
    db.add(row)
    db.flush()
    return row


def _bare_spec(db, product: Product) -> ProductSpecifications:
    spec = ProductSpecifications(product_id=product.id, values={}, provenance={})
    db.add(spec)
    db.commit()
    return spec


def _warning_records(caplog) -> list:
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_bypass_write_around_the_service_is_logged_as_a_warning(db, caplog):
    register_spec_write_backstop()
    product = _product(db, "ZZT-BS-1")
    spec = _bare_spec(db, product)

    with caplog.at_level(logging.WARNING):
        spec.values = {"material": {"value": "brass"}}
        db.commit()

    assert _warning_records(caplog), "an assignment made around write_spec_row must be logged"


def test_a_bypass_write_to_provenance_alone_is_also_caught(db, caplog):
    register_spec_write_backstop()
    product = _product(db, "ZZT-BS-2")
    spec = _bare_spec(db, product)

    with caplog.at_level(logging.WARNING):
        spec.provenance = {"material": {"source": "human", "confidence": 1.0, "evidence": "x"}}
        db.commit()

    assert _warning_records(caplog)


def test_a_bypass_write_to_rendered_text_alone_is_also_caught(db, caplog):
    register_spec_write_backstop()
    product = _product(db, "ZZT-BS-3")
    spec = _bare_spec(db, product)

    with caplog.at_level(logging.WARNING):
        spec.rendered_text = "Brass. Ceramic."
        db.commit()

    assert _warning_records(caplog)


def test_a_write_through_write_spec_row_produces_no_bypass_warning(db, caplog):
    register_spec_write_backstop()
    product = _product(db, "ZZT-BS-4")
    spec = _bare_spec(db, product)

    with caplog.at_level(logging.WARNING):
        write_spec_row(spec, values={"material": {"value": "brass"}}, provenance={})
        db.commit()

    assert not _warning_records(caplog), "the sanctioned path must never trip the backstop"


def test_the_backstop_never_raises_even_when_logging_itself_fails(db, monkeypatch):
    """Post-commit side effects are best-effort (PRINCIPLES.md): a failure inside the
    backstop's own warning call must not surface to the caller, or a routine commit
    that happens to be a bypass would start failing requests that used to succeed.
    """
    register_spec_write_backstop()

    def _boom(self, *args, **kwargs):
        raise RuntimeError("simulated logging failure")

    monkeypatch.setattr(logging.Logger, "warning", _boom)

    product = _product(db, "ZZT-BS-5")
    spec = _bare_spec(db, product)

    spec.values = {"material": {"value": "brass"}}
    db.commit()  # must not raise, even though every logger.warning() call now explodes


def test_registering_the_backstop_twice_is_a_no_op(db, caplog):
    """Guarded by a module-global flag, like register_product_spec_listeners - so
    calling it again (as every test file and both processes do) never double-logs."""
    register_spec_write_backstop()
    register_spec_write_backstop()

    product = _product(db, "ZZT-BS-6")
    spec = _bare_spec(db, product)

    with caplog.at_level(logging.WARNING):
        spec.values = {"material": {"value": "brass"}}
        db.commit()

    warnings = _warning_records(caplog)
    assert len(warnings) == 1, "a double-registered listener must not log the same bypass twice"


# --------------------------------------------------------------------------- #
# 6b.2 - the sanctioned mark is per WRITE, not per flush
# --------------------------------------------------------------------------- #
def test_write_spec_row_followed_by_a_hand_assignment_before_commit_is_reported(db, caplog):
    """A future contributor writing `write_spec_row(...)` and then hand-patching one
    field on the same row before commit must still trip the backstop: the row no
    longer carries exactly what the sanctioned write put there, so it is not the
    sanctioned write that reaches the database - a mark that survived unconditionally
    to the next flush would let this through unreported."""
    register_spec_write_backstop()
    product = _product(db, "ZZT-BS-7")
    spec = _bare_spec(db, product)

    with caplog.at_level(logging.WARNING):
        write_spec_row(spec, values={"material": {"value": "brass"}}, provenance={})
        spec.values = {"material": {"value": "steel"}}  # hand assignment AFTER the sanctioned write
        db.commit()

    assert _warning_records(caplog), (
        "a hand assignment made after write_spec_row, before the same commit, must still be caught"
    )


def test_two_consecutive_sanctioned_writes_across_two_commits_produce_no_warning(db, caplog):
    """The mirror image of the test above: two GENUINE write_spec_row calls, each
    followed by its own commit, must never warn - the per-write mark must not become
    a false positive on the second sanctioned write just because it happened after
    the first one."""
    register_spec_write_backstop()
    product = _product(db, "ZZT-BS-8")
    spec = _bare_spec(db, product)

    with caplog.at_level(logging.WARNING):
        write_spec_row(spec, values={"material": {"value": "brass"}}, provenance={})
        db.commit()
        write_spec_row(spec, values={"material": {"value": "ceramic"}}, provenance={})
        db.commit()

    assert not _warning_records(caplog), "two consecutive sanctioned writes must never warn"


# --------------------------------------------------------------------------- #
# 6b.3 - _collect is best-effort, like _report
# --------------------------------------------------------------------------- #
def test_a_failure_inside_collect_does_not_fail_the_flush(db, monkeypatch):
    """`_collect` (the before_flush half) must be wrapped in try/except like `_report`
    (the after_commit half): reading attribute history can itself raise, and a
    diagnostic that fails the write it only meant to observe inverts its own purpose."""
    import app.services.product_spec_write as write_module

    register_spec_write_backstop()
    product = _product(db, "ZZT-BS-10")
    spec = _bare_spec(db, product)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated inspection failure inside _collect")

    monkeypatch.setattr(write_module, "_is_sanctioned", _boom)

    spec.values = {"material": {"value": "brass"}}
    db.commit()  # must not raise even though _is_sanctioned blows up inside before_flush
