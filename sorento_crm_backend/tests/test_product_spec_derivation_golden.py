"""AC-A.2 - the catalogue reads the same after the hidden readers become rules.

The readable-rules change moves four hard-wired steps of `derive()` (class, brand, the
`L x W x H` block and the plausibility cap) into ordinary rule rows. Every one of them
decides what a product IS, so a transcription slip is not a failing unit test, it is
22,805 products silently re-read - and nothing on any screen would say so.

This is the proof that none of them moved. `tests/fixtures/spec_derivation_golden_sample.json`
holds a deterministic 2,000-code sample of the live catalogue: every category and every
brand is represented, plus the branches that are easy to get wrong (round and square
products whose columns are mis-keyed, trap spans that are not sizes, lone sizes,
implausible column values) and the codes named in the derivation tests and the plan.
Each entry carries the inputs derivation reads and the values, provenance and exceptions
the engine produced BEFORE the change.

Two variants, because the catalogue reads two ways:

  * `shipped` - the rules a database with no configured rules falls back to. What the
    test suite and a fresh install run.
  * `owned_class` - the live database's own 33 `class` rules, which REPLACE the shipped
    ones, plus the readers that used to run underneath them without appearing anywhere.
    That is the case the backfill migration (AC-A.6) has to preserve, and it is the one
    a golden built only from shipped rules would miss entirely.

Regenerate the fixture only with a measured reason.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecException, ProductSpecifications
from app.services.product_spec_derivation import derive, derive_all
from app.services.product_spec_registry import shipped_scopes
from tests._pg_fixture import blank_session

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "spec_derivation_golden_sample.json"


def _golden() -> dict:
    with _FIXTURE.open() as handle:
        return json.load(handle)


GOLDEN = _golden()


# --------------------------------------------------------------------------- #
# the sample, as rows
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def sample() -> list[dict]:
    return GOLDEN["products"]


@pytest.fixture
def db(sample):
    """The whole sample, inserted into a blank schema and derived once."""
    with blank_session() as session:
        _load_sample(session, sample)
        yield session


def _load_sample(db, sample: list[dict]) -> None:
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-GOLD-PCS", uom_name="Piece")
    db.add(uom)

    categories: dict[tuple, str] = {}
    brands: dict[str, str] = {}
    for entry in sample:
        key = (entry["category_code"], entry["class_label"])
        if entry["category_code"] and key not in categories:
            row = ProductCategory(
                id=str(uuid.uuid4()),
                category_code=entry["category_code"],
                category_name=entry["category_code"],
                class_label=entry["class_label"],
            )
            db.add(row)
            categories[key] = row.id
        name = entry["brand_name"]
        if name and name not in brands:
            row = Brand(id=str(uuid.uuid4()), brand_code=f"ZZT-B{len(brands)}", brand_name=name)
            db.add(row)
            brands[name] = row.id
    db.flush()

    for entry in sample:
        db.add(
            Product(
                id=str(uuid.uuid4()),
                product_code=entry["code"],
                product_name=entry["code"],
                description=entry["description"],
                category_id=categories.get((entry["category_code"], entry["class_label"])),
                base_uom_id=uom.id,
                brand_id=brands.get(entry["brand_name"]),
                list_price=Decimal("1.00"),
                dimensions_length=_decimal(entry["dimensions_length"]),
                dimensions_width=_decimal(entry["dimensions_width"]),
                dimensions_height=_decimal(entry["dimensions_height"]),
            )
        )
    db.flush()


def _decimal(raw):
    return None if raw is None else Decimal(raw)


def _normalise(obj):
    """JSON round trip, so a Decimal and its float compare equal."""
    return json.loads(json.dumps(obj, default=float, sort_keys=True))


def _exception_rows(rows) -> list[dict]:
    return sorted(
        (
            {
                "spec_key": row.spec_key,
                "reason": row.reason,
                "proposed": _normalise(row.proposed),
                "stored": _normalise(row.stored),
            }
            for row in rows
        ),
        key=lambda entry: (entry["spec_key"], entry["reason"], json.dumps(entry["proposed"])),
    )


def _expected_exceptions(entry: dict, variant: str) -> list[dict]:
    return sorted(
        (
            {
                "spec_key": flag["spec_key"],
                "reason": flag["reason"],
                "proposed": _normalise(flag["proposed"]),
                "stored": _normalise(flag["stored"]),
            }
            for flag in entry[variant]["exceptions"]
        ),
        key=lambda flag: (flag["spec_key"], flag["reason"], json.dumps(flag["proposed"])),
    )


def _report(differences: list[str]) -> str:
    head = differences[:20]
    tail = "" if len(differences) <= 20 else f"\n... and {len(differences) - 20} more"
    return "\n".join(head) + tail


# --------------------------------------------------------------------------- #
# AC-A.2
# --------------------------------------------------------------------------- #
def test_the_shipped_rules_derive_the_sample_exactly_as_before(db, sample):
    """`derive_all` over 2,000 real codes, value for value and evidence for evidence."""
    derive_all(db, codes=[entry["code"] for entry in sample])

    stored = {
        product.product_code: spec
        for spec, product in db.query(ProductSpecifications, Product)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .all()
    }
    exceptions: dict[str, list] = {}
    for row in db.query(ProductSpecException).all():
        exceptions.setdefault(row.product_code, []).append(row)

    differences: list[str] = []
    for entry in sample:
        code = entry["code"]
        spec = stored.get(code)
        if spec is None:
            differences.append(f"{code}: no spec row was written")
            continue
        expected = entry["shipped"]
        for key in sorted(set(expected["values"]) | set(spec.values or {})):
            was = _normalise(expected["values"].get(key))
            now = _normalise((spec.values or {}).get(key))
            if was != now:
                differences.append(f"{code} [{key}]: was {was}, now {now}")
        for key in sorted(set(expected["provenance"]) | set(spec.provenance or {})):
            was = _normalise(expected["provenance"].get(key))
            now = _normalise((spec.provenance or {}).get(key))
            if was != now:
                differences.append(f"{code} [{key}] provenance: was {was}, now {now}")
        was_flags = _expected_exceptions(entry, "shipped")
        now_flags = _exception_rows(exceptions.get(code, []))
        if was_flags != now_flags:
            differences.append(f"{code} exceptions: was {was_flags}, now {now_flags}")

    assert not differences, _report(differences)


class _Brand:
    def __init__(self, name: str) -> None:
        self.brand_name = name


class _Row:
    """The four attributes `derive` reads, without a session."""

    def __init__(self, **fields) -> None:
        self.__dict__.update(fields)


def _in_memory(entry: dict) -> tuple:
    product = _Row(
        product_code=entry["code"],
        description=entry["description"],
        dimensions_length=_decimal(entry["dimensions_length"]),
        dimensions_width=_decimal(entry["dimensions_width"]),
        dimensions_height=_decimal(entry["dimensions_height"]),
        brand=_Brand(entry["brand_name"]) if entry["brand_name"] else None,
    )
    category = (
        _Row(category_code=entry["category_code"], class_label=entry["class_label"])
        if entry["category_code"]
        else None
    )
    return product, category


def _compare(entry: dict, variant: str, result) -> list[str]:
    code = entry["code"]
    expected = entry[variant]
    differences: list[str] = []
    for key in sorted(set(expected["values"]) | set(result.values)):
        was = _normalise(expected["values"].get(key))
        now = _normalise(result.values.get(key))
        if was != now:
            differences.append(f"{code} [{key}]: was {was}, now {now}")
    for key in sorted(set(expected["provenance"]) | set(result.provenance)):
        was = _normalise(expected["provenance"].get(key))
        now = _normalise(result.provenance.get(key))
        if was != now:
            differences.append(f"{code} [{key}] provenance: was {was}, now {now}")
    return differences


def test_the_shipped_rules_derive_the_sample_exactly_as_before_without_a_database(sample):
    """The same 2,000 codes through `derive` itself, so a failure names the pure step."""
    from app.services.product_spec_derivation import shipped_rules

    rules = shipped_rules()
    scopes = shipped_scopes()
    differences: list[str] = []
    for entry in sample:
        product, category = _in_memory(entry)
        result = derive(product, category, rules_by_key=rules, scopes_by_key=scopes)
        differences.extend(_compare(entry, "shipped", result))

    assert not differences, _report(differences)
