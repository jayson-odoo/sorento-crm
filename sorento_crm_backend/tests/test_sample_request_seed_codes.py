"""The SR seed factory's codes never collide and always fit their columns.

`make_product` used to build its unit of measure as ``"ZZT" + 4 hex chars``: 65,536
possible codes, so a few hundred products in one CI database made a duplicate likely, and
release run 40058409549 died on ``uq_units_of_measure_company_uom_code``. A collision is
probabilistic, so there is no red run to reproduce; instead build 2,000 of every code the
factory makes and check each set is unique and within its column's length.
"""
from __future__ import annotations

from app.models.order import Customer
from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

from ._sample_request_seed import make_customer, make_product

N = 2_000


class _RecordingDb:
    """Keeps every row the factory adds and writes nothing: only the codes matter."""

    def __init__(self):
        self.rows: list = []

    def add(self, row):
        self.rows.append(row)

    def add_all(self, rows):
        self.rows.extend(rows)

    def flush(self):
        pass


def _assert_unique_and_fits(codes: list[str], column) -> None:
    assert len(set(codes)) == len(codes) == N
    limit = column.type.length
    assert max(len(c) for c in codes) <= limit, f"{column} holds {limit} chars"


def _codes(db: _RecordingDb, column) -> list[str]:
    return [getattr(r, column.key) for r in db.rows if isinstance(r, column.class_)]


def test_make_product_codes_are_unique_and_fit():
    db = _RecordingDb()
    for _ in range(N):
        make_product(db)
    for column in (
        UnitOfMeasure.uom_code,
        ProductCategory.category_code,
        Brand.brand_code,
        Product.product_code,
    ):
        _assert_unique_and_fits(_codes(db, column), column)


def test_make_customer_codes_are_unique_and_fit():
    db = _RecordingDb()
    for _ in range(N):
        make_customer(db, "company")
    _assert_unique_and_fits(_codes(db, Customer.customer_code), Customer.customer_code)
