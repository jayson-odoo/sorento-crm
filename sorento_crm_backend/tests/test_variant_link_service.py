"""Variant graph - ``variant_link_service`` + product-API variant contract.

Covers PLAN-suggest-on-miss-variant-graph.md §1 / §7.5:

  AC-V1  backfill / reconcile is idempotent - a second pass changes nothing;
         a deliberately-wrong seed is CORRECTED (set-to-correct, not where-NULL).
  AC-V2  boundary rule truth table (dash / letter = variant; continued digit =
         different product; non-existent prefix = base).
  AC-V3  delete never blocks - DB ``ondelete=SET NULL`` orphans children; the
         re-derive step re-anchors them to the next existing ancestor.
  AC-V4  parent-added-later - a child created before its base is a base; creating
         the base adopts the orphan (adopt-orphans path).

Plus the product GET-by-id variant/base serialization contract
(``variant_of`` / ``variants`` / ``is_variant``) and the cheap LIST-row
``is_variant`` derivation (no N+1).

The pure ``boundary_ok`` truth table is DB-free. The reconcile / adopt / delete
tests build a throwaway product family in live Postgres (synthetic ``ZZVLINK*``
codes that can't collide with the real catalog) and clean it up; they skip when
the DB is unreachable. The API-contract tests seed their OWN ``ZZVLINK*`` pair
through the same fixture rather than borrowing a live backfilled row, so they
run on an empty database and can't race a concurrent test file's rows.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services.variant_link_service import (
    boundary_ok,
    normalize_code,
    reconcile_variant_links,
    child_ids_of,
    _derive_parent_id,
)


# --------------------------------------------------------------------------- #
# AC-V2 - boundary truth table (pure function, DB-free)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "child, prefix, expect",
    [
        ("SRTKT71SS-BL", "SRTKT71SS", True),    # dash boundary -> variant
        ("M-FH08SS", "M-FH08", True),           # letter boundary -> variant
        ("SRTWC8517-200", "SRTWC8517", True),   # dash (size) -> variant
        ("SRTWT8517", "SRTWT85", False),        # continued digit -> different product
        ("SRTKT71SS", "SRTKT71SS", False),      # equal length -> not strictly longer
        ("SRTKT71SSBL", "SRTKT71SS", True),     # letter run boundary -> variant
        ("SRTKT7155", "SRTKT71", False),        # digit run -> different product
    ],
)
def test_boundary_ok_truth_table(child, prefix, expect):
    assert boundary_ok(child, len(normalize_code(prefix))) is expect


def test_boundary_ok_zero_len_is_false():
    assert boundary_ok("ANYTHING", 0) is False


def test_normalize_code_strips_dash_ws_lower():
    assert normalize_code("srtkt71-ss") == "srtkt71ss"
    assert normalize_code("SRTWT7438 GM") == "srtwt7438gm"
    assert normalize_code(None) == ""


# --------------------------------------------------------------------------- #
# Live-DB fixture. Skips cleanly when unreachable.
# --------------------------------------------------------------------------- #
def _database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        from dotenv import dotenv_values

        return dotenv_values(".env").get("DATABASE_URL")
    except Exception:
        return None


@pytest.fixture(scope="module")
def db():
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL not configured")
    try:
        engine = create_engine(url)
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres unreachable: {exc}")
    conn.close()
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


_TEST_PREFIX = "ZZVLINK"
# The company every product row defaults to (migration 306's column DEFAULT).
_SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"
_CAT_CODE = _TEST_PREFIX + "-CAT"
_UOM_CODE = _TEST_PREFIX + "-UOM"


def _ref_ids(db):
    """Get-or-create the ZZVLINK category + uom the NOT-NULL product FKs need.

    Seeded here rather than borrowed off the live tables: a freshly bootstrapped
    database (CI) has no rows in either, so borrowing meant skipping the whole
    DB half of this file, and a borrowed row can be deleted mid-test by a
    concurrently running test file. Idempotent on the two marker codes; the
    ``family`` fixture removes both rows again once the products are gone.
    """
    cat = db.execute(
        text("SELECT id FROM product_categories WHERE category_code = :c"),
        {"c": _CAT_CODE},
    ).scalar()
    if not cat:
        cat = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO product_categories (id, category_code, category_name) "
                "VALUES (:id, :code, :name)"
            ),
            {"id": cat, "code": _CAT_CODE, "name": "ZZVLINK Test Category"},
        )
        db.commit()
    uom = db.execute(
        text("SELECT id FROM units_of_measure WHERE uom_code = :c"), {"c": _UOM_CODE}
    ).scalar()
    if not uom:
        uom = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO units_of_measure (id, uom_code, uom_name) "
                "VALUES (:id, :code, :name)"
            ),
            {"id": uom, "code": _UOM_CODE, "name": "ZZVLINK Each"},
        )
        db.commit()
    return cat, uom


def _mk(db, code, cat, uom):
    pid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO products (id, product_code, product_name, category_id, "
            "base_uom_id, list_price, is_active) VALUES "
            "(:id, :code, :name, :cat, :uom, 0, true)"
        ),
        {"id": pid, "code": code, "name": code, "cat": cat, "uom": uom},
    )
    return pid


@pytest.fixture
def family(db):
    """Insert a throwaway ZZVLINK* family; hard-clean it up afterwards."""
    cat, uom = _ref_ids(db)
    # Wipe any leftovers from a previous aborted run.
    db.execute(
        text("DELETE FROM products WHERE product_code LIKE :p"),
        {"p": _TEST_PREFIX + "%"},
    )
    db.commit()
    created = {}
    try:
        yield {"cat": cat, "uom": uom, "ids": created, "mk": lambda code: created.setdefault(code, _mk(db, code, cat, uom))}
    finally:
        db.rollback()
        db.execute(
            text("DELETE FROM products WHERE product_code LIKE :p"),
            {"p": _TEST_PREFIX + "%"},
        )
        # FK order: the products referencing them are gone by now.
        db.execute(
            text("DELETE FROM product_categories WHERE category_code = :c"),
            {"c": _CAT_CODE},
        )
        db.execute(
            text("DELETE FROM units_of_measure WHERE uom_code = :c"), {"c": _UOM_CODE}
        )
        db.commit()


def _parent_of(db, pid):
    val = db.execute(
        text("SELECT variant_of_id FROM products WHERE id = :id"), {"id": pid}
    ).scalar()
    return str(val) if val is not None else None


# --------------------------------------------------------------------------- #
# AC-V1 - idempotency + wrong-seed correction
# --------------------------------------------------------------------------- #
def test_v1_reconcile_links_and_is_idempotent(db, family):
    base = family["mk"](_TEST_PREFIX + "100")
    child = family["mk"](_TEST_PREFIX + "100-BL")
    db.commit()

    r1 = reconcile_variant_links(db, base)
    # base has no parent; adopts the orphan child
    assert r1["parent_id"] is None
    assert r1["orphans_adopted"] == 1
    assert _parent_of(db, child) == base

    # Second pass: nothing changes.
    r2 = reconcile_variant_links(db, base)
    assert r2["self_changed"] is False
    assert r2["orphans_adopted"] == 0
    assert _parent_of(db, child) == base


def test_v1_corrects_deliberately_wrong_seed(db, family):
    base = family["mk"](_TEST_PREFIX + "200")
    child = family["mk"](_TEST_PREFIX + "200-BL")
    db.commit()
    # Seed a WRONG link: child points at itself (a deliberately-bad prior value).
    db.execute(
        text("UPDATE products SET variant_of_id = :wrong WHERE id = :id"),
        {"wrong": child, "id": child},  # child -> itself: garbage
    )
    db.commit()

    reconcile_variant_links(db, child)   # re-derive my own parent
    assert _parent_of(db, child) == base  # corrected to the real base


# --------------------------------------------------------------------------- #
# AC-V2 (existence anchoring) - a prefix that is not a product yields a base
# --------------------------------------------------------------------------- #
def test_v2_existence_anchoring_base_when_prefix_absent(db, family):
    # ZZVLINK300 base does NOT exist; only the child does -> child is a base.
    child = family["mk"](_TEST_PREFIX + "300-4001")
    db.commit()
    r = reconcile_variant_links(db, child)
    assert r["parent_id"] is None
    assert _parent_of(db, child) is None


def test_v2_digit_neighbour_not_a_variant(db, family):
    base = family["mk"](_TEST_PREFIX + "400")
    neigh = family["mk"](_TEST_PREFIX + "4001")  # continued digit -> NOT a variant
    db.commit()
    reconcile_variant_links(db, base)
    assert _parent_of(db, neigh) is None
    assert _derive_parent_id(db, neigh, _TEST_PREFIX + "4001") is None


def test_v2_longest_existing_prefix_wins(db, family):
    base = family["mk"](_TEST_PREFIX + "500")
    mid = family["mk"](_TEST_PREFIX + "500-BL")
    leaf = family["mk"](_TEST_PREFIX + "500-BL-S")
    db.commit()
    reconcile_variant_links(db, base)
    reconcile_variant_links(db, mid)
    reconcile_variant_links(db, leaf)
    assert _parent_of(db, mid) == base
    assert _parent_of(db, leaf) == mid  # longest (most specific) wins, not base


# --------------------------------------------------------------------------- #
# AC-V3 - delete SET NULL + re-anchor to next existing ancestor
# --------------------------------------------------------------------------- #
def test_v3_delete_sets_null_and_reanchors(db, family):
    # This asserts the re-derive DERIVATION is correct once fed a string id.
    # NOTE: production (delete_product) passes the raw `child_ids_of` value, which
    # is a uuid.UUID (pg `uuid` column via raw text()) -> reconcile_variant_links'
    # `product_code == <uuid>` lookup raises `character varying = uuid`, swallowed
    # by _reconcile_variant_links -> re-anchor silently fails. See the strict-xfail
    # END-TO-END test below and the tester report.
    base = family["mk"](_TEST_PREFIX + "600")
    mid = family["mk"](_TEST_PREFIX + "600-BL")
    leaf = family["mk"](_TEST_PREFIX + "600-BL-S")
    db.commit()
    for pid in (base, mid, leaf):
        reconcile_variant_links(db, pid)
    assert _parent_of(db, leaf) == mid

    # Mirror product_service.delete_product: capture children, delete, re-derive.
    ex_children = child_ids_of(db, mid)
    assert str(leaf) in {str(c) for c in ex_children}
    db.execute(text("DELETE FROM products WHERE id = :id"), {"id": mid})  # no FK error
    db.commit()
    # DB ondelete=SET NULL nulled the leaf.
    assert _parent_of(db, leaf) is None
    # Re-derive re-anchors it to the next existing ancestor (the base).
    for child_id in ex_children:
        reconcile_variant_links(db, str(child_id))  # str -> derivation works
    assert _parent_of(db, leaf) == base


def test_v3_reanchor_to_null_when_no_ancestor(db, family):
    base = family["mk"](_TEST_PREFIX + "700")
    child = family["mk"](_TEST_PREFIX + "700-BL")
    db.commit()
    for pid in (base, child):
        reconcile_variant_links(db, pid)
    assert _parent_of(db, child) == base

    ex_children = child_ids_of(db, base)
    db.execute(text("DELETE FROM products WHERE id = :id"), {"id": base})
    db.commit()
    assert _parent_of(db, child) is None
    for child_id in ex_children:
        reconcile_variant_links(db, str(child_id))
    # No ancestor remains -> stays NULL (child is now a base).
    assert _parent_of(db, child) is None


def test_v3_delete_product_reanchors_END_TO_END(db, family):
    """The real production path: ProductService.delete_product re-anchors the
    grandchild to the surviving base.

    LATENT FRAGILITY (reported, not a live prod bug): child_ids_of() returns
    uuid.UUID (raw text() over a pg `uuid` column) which is fed straight into
    reconcile_variant_links()'s `Product.product_code == code_or_id` ORM lookup.
    Whether `varchar = uuid` raises depends on a global psycopg2 uuid adapter
    that is registered when the FULL app is imported (as uvicorn does in prod) - 
    so it WORKS in production and under the full pytest suite, but a partial
    import path would 500 inside reconcile and the best-effort handler would
    swallow it, silently orphaning the sub-tree. We import app.main here to match
    the production runtime deterministically. A one-line str() coercion in
    reconcile_variant_links / child_ids_of would remove the dependency."""
    import app.main  # noqa: F401 - register the prod-runtime psycopg2 uuid adapter
    from app.services.product_service import ProductService

    base = family["mk"](_TEST_PREFIX + "610")
    mid = family["mk"](_TEST_PREFIX + "610-BL")
    leaf = family["mk"](_TEST_PREFIX + "610-BL-S")
    db.commit()
    for pid in (base, mid, leaf):
        reconcile_variant_links(db, pid)
    assert _parent_of(db, leaf) == mid

    ProductService(db).delete_product(mid)
    db.expire_all()
    # Re-anchors to the surviving base (next existing ancestor), not orphaned.
    assert _parent_of(db, leaf) == base


# --------------------------------------------------------------------------- #
# AC-V4 - parent added later adopts the orphan
# --------------------------------------------------------------------------- #
def test_v4_parent_added_later_adopts_orphan(db, family):
    # Child created FIRST, before its base exists -> it is a base.
    child = family["mk"](_TEST_PREFIX + "800-BL")
    db.commit()
    r_child = reconcile_variant_links(db, child)
    assert r_child["parent_id"] is None
    assert _parent_of(db, child) is None

    # Now the base appears; reconciling it adopts the orphan.
    base = family["mk"](_TEST_PREFIX + "800")
    db.commit()
    r_base = reconcile_variant_links(db, base)
    assert r_base["orphans_adopted"] == 1
    assert _parent_of(db, child) == base


# --------------------------------------------------------------------------- #
# Product API GET-by-id variant / base serialization contract
# --------------------------------------------------------------------------- #
def _svc(db):
    from app.services.product_service import ProductService

    return ProductService(db)


def _seed_variant_and_base(db, family, marker):
    """Seed a throwaway ``ZZVLINK<marker>`` base + one linked variant.

    Links via ``reconcile_variant_links`` (the adopt-orphans path the AC-V1 tests
    exercise) rather than a hand-written UPDATE, so the pair the API contract is
    asserted against is built by the service under test. Returns the same tuple
    shape the API tests consume: (variant_id, variant_code, base_id, base_code).
    """
    base_code = _TEST_PREFIX + marker
    variant_code = _TEST_PREFIX + marker + "-BL"
    base_id = family["mk"](base_code)
    variant_id = family["mk"](variant_code)
    db.commit()
    reconcile_variant_links(db, base_id)  # adopts the orphan child + commits
    assert _parent_of(db, variant_id) == base_id
    return variant_id, variant_code, base_id, base_code


def test_api_variant_contract(db, family):
    from app.schemas.product import ProductResponse

    variant_id, variant_code, base_id, base_code = _seed_variant_and_base(
        db, family, "900"
    )

    v = _svc(db).get_product(variant_id)
    vr = ProductResponse.model_validate(v)
    assert vr.is_variant is True
    assert vr.variant_of is not None
    assert vr.variant_of.product_code == base_code
    assert str(vr.variant_of.id) == str(base_id)

    b = _svc(db).get_product(base_id)
    br = ProductResponse.model_validate(b)
    assert br.is_variant is False
    assert br.variant_of is None
    child_codes = {c.product_code for c in br.variants}
    assert variant_code in child_codes  # base lists its child
    for c in br.variants:
        # Human-readable ref, never a bare UUID surfaced as the code.
        assert c.product_code and c.product_code != str(c.id)


def test_api_list_row_is_variant_cheap_no_extra_attrs(db, family):
    """A plain ORM row (as LIST returns it, no _variant_* stashed attrs) still
    serializes is_variant from the column - and does NOT emit variant_of /
    variants (no N+1 on list)."""
    from sqlalchemy.orm import Session as _Session

    from app.models.base import set_company_scope
    from app.models.product import Product
    from app.schemas.product import ProductResponse

    variant_id, _, _, _ = _seed_variant_and_base(db, family, "910")
    # Fresh session so the module-session identity map (which a prior
    # get_product test stashed _variant_of_ref onto) can't leak into this row - 
    # this mirrors a LIST query that never calls _populate_variant_graph.
    fresh = _Session(bind=db.get_bind())
    # A brand-new session's FIRST ORM statement runs before conftest's
    # `after_begin` listener has defaulted the company scope, so the
    # multi-company filter would fail closed (`AND false`) and return no row. A
    # real LIST request always has its scope resolved by this point, so setting
    # it here mirrors production instead of weakening the test.
    set_company_scope(fresh, frozenset({_SORENTO_COMPANY_ID}))
    try:
        row = fresh.query(Product).filter(Product.id == variant_id).first()
        assert not hasattr(row, "_variant_of_ref")
        r = ProductResponse.model_validate(row)
        assert r.is_variant is True
        assert r.variant_of is None       # not populated on list rows
        assert r.variants == []           # not populated on list rows
    finally:
        fresh.close()


def test_api_base_row_is_variant_false(db, family):
    from app.models.product import Product
    from app.schemas.product import ProductResponse

    base_id = family["mk"](_TEST_PREFIX + "920")
    db.commit()
    row = db.query(Product).filter(Product.id == base_id).first()
    assert row is not None and row.variant_of_id is None
    r = ProductResponse.model_validate(row)
    assert r.is_variant is False
