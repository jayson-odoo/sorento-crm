"""Migration ptag_0014_lpsp (PRICETAG-LPSP S1, AC-6).

UAC: documentation/plans/dealer-kit/pricetag-lpsp-acceptance-criteria.md.

Adds `price_tag_request_lines.price_type` (backfilled from the request's `price_mode`),
`dealer_kit.product_tag_template.is_default` and `dealer_kit.combo_tag_template`. Downgrade drops
all of it.

Run on the blank scratch schema inside a rolled-back transaction (Postgres DDL is
transactional). While the models are not yet updated the schema holds the PRE state and
`_rewind` is a no-op; once they land `create_all` builds the POST state and `_rewind` puts the
pre-migration shape back by hand, as `test_migration_ptag_0011_line_promotion.py` does.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"

MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "ptag_0014_lpsp.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("ptag0014", MIGRATION)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, fn: str):
    module = _load()
    with Operations.context(MigrationContext.configure(db.connection())):
        getattr(module, fn)()
    return module


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _rewind(db) -> None:
    """Back to production's shape before ptag_0014 (dropping a column drops its indexes
    and CHECK with it)."""
    db.execute(text("DROP TABLE IF EXISTS combo_tag_template"))
    db.execute(text("ALTER TABLE product_tag_template DROP COLUMN IF EXISTS is_default"))
    db.execute(text("ALTER TABLE price_tag_request_lines DROP COLUMN IF EXISTS price_type"))
    db.flush()


def _columns(db, table: str) -> dict[str, dict]:
    rows = db.execute(
        text(
            "SELECT a.attname AS name, a.attnotnull AS notnull, "
            "       pg_get_expr(d.adbin, d.adrelid) AS dflt "
            "FROM pg_attribute a "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE a.attrelid = to_regclass(:t) AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"t": table},
    ).all()
    return {r.name: {"notnull": r.notnull, "default": r.dflt} for r in rows}


def _unique_indexes(db, table: str) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT pg_get_indexdef(i.indexrelid) AS def, pg_get_expr(i.indpred, i.indrelid) AS pred "
            "FROM pg_index i WHERE i.indrelid = to_regclass(:t) AND i.indisunique"
        ),
        {"t": table},
    ).all()
    return [{"def": r[0], "pred": r[1]} for r in rows]


# --------------------------------------------------------------------------- seeds
def _product(db, stem: str) -> str:
    code = unique_code(stem)
    category_id, brand_id, uom_id, product_id = (_uid() for _ in range(4))
    db.execute(
        text("INSERT INTO product_categories (id, category_code, category_name) VALUES (:i, :c, :n)"),
        {"i": category_id, "c": code[:50], "n": f"ZZT cat {code}"},
    )
    db.execute(
        text("INSERT INTO brands (id, brand_code, brand_name) VALUES (:i, :c, :n)"),
        {"i": brand_id, "c": code[:50], "n": f"ZZT {code}"},
    )
    db.execute(
        text("INSERT INTO units_of_measure (id, uom_code, uom_name) VALUES (:i, :c, 'Each')"),
        {"i": uom_id, "c": code[:20]},
    )
    db.execute(
        text(
            "INSERT INTO products (id, company_id, product_code, product_name, category_id, "
            "brand_id, base_uom_id, list_price) "
            "VALUES (:i, :co, :c, :n, :cat, :br, :uom, 100.00)"
        ),
        {"i": product_id, "co": SORENTO, "c": code, "n": f"ZZT {code}",
         "cat": category_id, "br": brand_id, "uom": uom_id},
    )
    db.flush()
    return product_id


def _contact(db) -> str:
    contact_id = _uid()
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number, name) VALUES (:i, :p, :n)"),
        {"i": contact_id, "p": f"+60{uuid.uuid4().hex[:9]}", "n": unique_code("contact")},
    )
    db.flush()
    return contact_id


def _request(db, price_mode: str, line_count: int = 2) -> tuple[str, list[str]]:
    request_id = _uid()
    db.execute(
        text(
            "INSERT INTO price_tag_requests (id, company_id, contact_id, doc_number, status, price_mode) "
            "VALUES (:i, :co, :ct, :d, 'designing', :m)"
        ),
        {"i": request_id, "co": SORENTO, "ct": _contact(db),
         "d": unique_code("PT14")[:40], "m": price_mode},
    )
    line_ids = []
    for index in range(line_count):
        line_id = _uid()
        db.execute(
            text(
                "INSERT INTO price_tag_request_lines (id, request_id, line_type, product_id, sort_order) "
                "VALUES (:i, :r, 'product', :p, :s)"
            ),
            {"i": line_id, "r": request_id, "p": _product(db, "PT14"), "s": index},
        )
        line_ids.append(line_id)
    db.flush()
    return request_id, line_ids


# --------------------------------------------------------------------------- tests
def test_revision_id_fits_and_chains():
    module = _load()
    assert module.revision == "ptag_0014_lpsp"
    assert len(module.revision) <= 32
    assert module.down_revision


def test_upgrade_adds_the_columns_and_the_table(db):
    _rewind(db)
    _run(db, "upgrade")

    line = _columns(db, "price_tag_request_lines")
    assert "price_type" in line
    assert line["price_type"]["notnull"] is False

    link = _columns(db, "product_tag_template")
    assert link["is_default"]["notnull"] is True
    assert "false" in (link["is_default"]["default"] or "").lower()

    combo = _columns(db, "combo_tag_template")
    for name in ("id", "combo_id", "template_id", "is_default", "created_by", "created_at"):
        assert name in combo, name
    assert combo["combo_id"]["notnull"] and combo["template_id"]["notnull"]
    assert combo["is_default"]["notnull"] is True


def test_upgrade_adds_the_default_uniqueness_rules(db):
    _rewind(db)
    _run(db, "upgrade")

    product_unique = _unique_indexes(db, "product_tag_template")
    assert any(
        "product_id" in i["def"] and i["pred"] and "is_default" in i["pred"]
        for i in product_unique
    ), product_unique

    combo_unique = _unique_indexes(db, "combo_tag_template")
    assert any("combo_id" in i["def"] and "template_id" in i["def"] and not i["pred"]
               for i in combo_unique), combo_unique
    assert any(
        "combo_id" in i["def"] and i["pred"] and "is_default" in i["pred"]
        for i in combo_unique
    ), combo_unique


def test_backfill_copies_each_requests_mode_to_its_lines(db):
    _rewind(db)
    _, list_lines = _request(db, "list", 2)
    _, selling_lines = _request(db, "selling", 3)

    _run(db, "upgrade")

    def types(ids):
        return db.execute(
            text("SELECT price_type FROM price_tag_request_lines WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": ids},
        ).scalars().all()

    assert types(list_lines) == ["list", "list"]
    assert types(selling_lines) == ["selling"] * 3


def test_price_type_only_allows_list_or_selling(db):
    _rewind(db)
    _run(db, "upgrade")
    request_id, _ = _request(db, "list", 0)
    for value in ("list", "selling", None):
        db.execute(
            text(
                "INSERT INTO price_tag_request_lines (id, request_id, line_type, product_id, sort_order, price_type) "
                "VALUES (:i, :r, 'product', :p, 0, :t)"
            ),
            {"i": _uid(), "r": request_id, "p": _product(db, "PT14C"), "t": value},
        )
    savepoint = db.begin_nested()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO price_tag_request_lines (id, request_id, line_type, product_id, sort_order, price_type) "
                "VALUES (:i, :r, 'product', :p, 0, 'bogus')"
            ),
            {"i": _uid(), "r": request_id, "p": _product(db, "PT14D")},
        )
    savepoint.rollback()


def test_deleting_a_combo_or_a_template_removes_its_link(db):
    from app.models.dealer_kit import TagTemplate
    from tests import _ptag_combo_seed as seed

    _rewind(db)
    _run(db, "upgrade")
    host = seed.product(db, "ZZM14")
    combo = seed.combo(db, host, "ZZT 14 combo")
    template = TagTemplate(id=_uid(), name=unique_code("T14"), family="ala_carte",
                           doc={"layers": [], "width_mm": 80, "height_mm": 50},
                           print_size={"width_mm": 80, "height_mm": 50}, company_id=SORENTO)
    db.add(template)
    db.flush()
    db.execute(
        text("INSERT INTO combo_tag_template (id, combo_id, template_id) VALUES (:i, :c, :t)"),
        {"i": _uid(), "c": combo.id, "t": template.id},
    )
    db.flush()
    assert db.execute(text("SELECT count(*) FROM combo_tag_template")).scalar() == 1

    db.execute(text("DELETE FROM product_combos WHERE id = :c"), {"c": combo.id})
    assert db.execute(text("SELECT count(*) FROM combo_tag_template")).scalar() == 0


def test_downgrade_drops_everything_it_added(db):
    _rewind(db)
    _run(db, "upgrade")
    _run(db, "downgrade")

    assert "price_type" not in _columns(db, "price_tag_request_lines")
    assert "is_default" not in _columns(db, "product_tag_template")
    assert db.execute(text("SELECT to_regclass('combo_tag_template') IS NULL")).scalar() is True
    # the pre-existing columns are untouched
    assert "show_promo_price" in _columns(db, "price_tag_request_lines")
    assert "template_id" in _columns(db, "product_tag_template")


def test_upgrade_is_idempotent_on_a_create_all_schema(db):
    """A database converged through `create_all` already holds the new shape."""
    _run(db, "upgrade")
    _run(db, "upgrade")
    assert "price_type" in _columns(db, "price_tag_request_lines")
    assert "is_default" in _columns(db, "product_tag_template")
    assert db.execute(text("SELECT to_regclass('combo_tag_template') IS NOT NULL")).scalar() is True
