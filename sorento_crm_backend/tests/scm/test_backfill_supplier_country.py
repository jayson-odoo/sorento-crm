"""`scripts/backfill_supplier_country.py` (S2, PLAN-local-supplier-oi-routing.md, AC-2.11).

RED for Phase 2: the script does not exist yet. Shaped after
`scripts/backfill_product_supplier_from_last_po.py`'s `run(db, *, apply=False) -> dict`
contract (same dry-run-by-default / `--apply` / idempotent shape, same reason -
`tests/scm/test_supplier_last_po_s15.py` already proves that shape works for a sweep this
size) rather than a bare CLI script with no importable body.

Contract this file drives: `scripts.backfill_supplier_country.run(db, *, apply=False) ->
dict` with keys `matched` (suppliers with no country whose name matches the heuristic),
`changed` (rows actually written - 0 on a dry run), `samples` (supplier codes/names). The
heuristic: `SDN BHD` / `SDN. BHD.` / `(KL)` / `MALAYSIA`, case-insensitive, whitespace
tolerant, matched only where `country_id IS NULL` - a supplier already carrying a country
(even a non-Malaysian one) is never touched.

An empty scratch schema, not the shared DB - the sweep runs over every no-country
supplier under company scope, and counting that against real production data would make
an exact assertion impossible (same reasoning as the S15 backfill's own test file).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.procurement import Supplier
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZTBSC"


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def my(db):
    from app.models.country import Country

    country = Country(id=_u(), code="MY", name="Malaysia")
    db.add(country)
    db.flush()
    return country


@pytest.fixture()
def cn(db):
    from app.models.country import Country

    country = Country(id=_u(), code="CN", name="China")
    db.add(country)
    db.flush()
    return country


def _supplier(db, name, *, country_id=None):
    s = Supplier(
        id=_u(), supplier_code=unique_code(MARKER)[:30], supplier_name=name,
        country_id=country_id,
    )
    db.add(s)
    db.flush()
    return s


def _seed_scenario(db, cn_country):
    """The six suppliers AC-2.11 names, one per matcher plus the two guards."""
    return {
        "foo": _supplier(db, "FOO SDN BHD"),
        "bar": _supplier(db, "BAR SDN. BHD."),
        "baz": _supplier(db, "BAZ (KL) SDN BHD"),
        "qux": _supplier(db, "QUX MALAYSIA"),
        "chaozhou": _supplier(db, "CHAOZHOU X CO LTD"),
        "already_cn": _supplier(db, "ALREADY SDN BHD CN SUPPLIER", country_id=cn_country.id),
    }


def test_dry_run_apply_idempotent_never_overwrites(db, my, cn):
    from scripts.backfill_supplier_country import run as backfill_run

    suppliers = _seed_scenario(db, cn)

    dry = backfill_run(db, apply=False)
    assert dry["matched"] == 4
    assert dry["changed"] == 0
    # No writes on a dry run: every matched supplier is still country-less.
    db.expire_all()
    for key in ("foo", "bar", "baz", "qux"):
        assert db.query(Supplier).filter(Supplier.id == suppliers[key].id).one().country_id is None
    assert db.query(Supplier).filter(Supplier.id == suppliers["chaozhou"].id).one().country_id is None
    assert db.query(Supplier).filter(Supplier.id == suppliers["already_cn"].id).one().country_id == cn.id

    applied = backfill_run(db, apply=True)
    assert applied["matched"] == 4
    assert applied["changed"] == 4

    db.expire_all()
    for key in ("foo", "bar", "baz", "qux"):
        assert db.query(Supplier).filter(Supplier.id == suppliers[key].id).one().country_id == my.id
    # Never matched, never touched.
    assert db.query(Supplier).filter(Supplier.id == suppliers["chaozhou"].id).one().country_id is None
    # Already had a country (China): never overwritten to MY.
    assert db.query(Supplier).filter(Supplier.id == suppliers["already_cn"].id).one().country_id == cn.id

    second = backfill_run(db, apply=True)
    assert second["matched"] == 0
    assert second["changed"] == 0
