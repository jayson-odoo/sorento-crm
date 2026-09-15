"""Migration ptag_0011 - promotion and manual price move to the LINE (D1, S6).

UAC: AC-S6-1, AC-S6-2, AC-S8-5. `blank_session()`'s `create_all` now builds the
POST-migration model (the coder's S6-S9 slice landed), so - exactly like
`test_migration_ptag_0009_combos_tags.py` - the pre-migration state has to be
rebuilt by hand: raw SQL, since the ORM no longer carries
`PriceTagRequest.promotion_id` or has ever carried the line's own two columns
before this revision ran.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "ptag_0011_line_promotion.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("ptag0011", MIGRATION)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()
    return module


def _run_downgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.downgrade()
    return module


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _rewind_to_pre_migration(db) -> None:
    """Put the scratch schema back to how production looks before ptag_0011.

    `create_all` gives us the POST state - the line already has its own
    `promotion_id`/`manual_sell_price` and the header has neither - so the
    migration's own DDL is put back under test the same way ptag_0009's test
    does: drop what the migration adds, restore what it removes.
    """
    db.execute(
        text(
            "ALTER TABLE price_tag_request_lines "
            "DROP COLUMN IF EXISTS promotion_id, "
            "DROP COLUMN IF EXISTS manual_sell_price"
        )
    )
    db.execute(
        text(
            "ALTER TABLE price_tag_requests "
            "ADD COLUMN IF NOT EXISTS promotion_id UUID "
            "REFERENCES promotions(id) ON DELETE SET NULL"
        )
    )
    db.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_price_tag_requests_promotion_id "
            "ON price_tag_requests (promotion_id)"
        )
    )
    db.flush()


# ---------------------------------------------------------------------------
# Seeding - raw SQL throughout (the ORM has no header promotion_id and, before
# upgrade() runs, no line promotion_id either). Mirrors
# `test_migration_ptag_0009_combos_tags.py`'s `_product`/`_contact` shape.
# ---------------------------------------------------------------------------


def _product(db, stem: str) -> str:
    code = unique_code(stem)
    category_id, brand_id, uom_id, product_id = (_uid() for _ in range(4))
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name) "
            "VALUES (:i, :c, :n)"
        ),
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
            "INSERT INTO products "
            "(id, company_id, product_code, product_name, category_id, brand_id, "
            " base_uom_id, list_price) "
            "VALUES (:i, :co, :c, :n, :cat, :br, :uom, 100.00)"
        ),
        {
            "i": product_id,
            "co": SORENTO,
            "c": code,
            "n": f"ZZT product {code}",
            "cat": category_id,
            "br": brand_id,
            "uom": uom_id,
        },
    )
    db.flush()
    return product_id


def _promotion(db) -> str:
    promotion_id = _uid()
    db.execute(
        text(
            "INSERT INTO promotions (id, description, is_active, company_id) "
            "VALUES (:i, :d, true, :co)"
        ),
        {"i": promotion_id, "d": unique_code("ZZT promo"), "co": SORENTO},
    )
    db.flush()
    return promotion_id


def _contact(db) -> str:
    contact_id = _uid()
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number, name) VALUES (:i, :p, :n)"),
        {"i": contact_id, "p": f"+60{uuid.uuid4().hex[:9]}", "n": unique_code("contact")},
    )
    db.flush()
    return contact_id


def _request_with_lines(db, *, promotion_id=None, line_count=3) -> tuple[str, list[str]]:
    request_id = _uid()
    db.execute(
        text(
            "INSERT INTO price_tag_requests "
            "(id, company_id, contact_id, doc_number, status, promotion_id) "
            "VALUES (:i, :co, :ct, :d, 'designing', :p)"
        ),
        {
            "i": request_id,
            "co": SORENTO,
            "ct": _contact(db),
            "d": unique_code("PT11")[:40],
            "p": promotion_id,
        },
    )
    line_ids: list[str] = []
    for index in range(line_count):
        line_id = _uid()
        db.execute(
            text(
                "INSERT INTO price_tag_request_lines "
                "(id, request_id, line_type, product_id, sort_order) "
                "VALUES (:i, :r, 'product', :p, :s)"
            ),
            {"i": line_id, "r": request_id, "p": _product(db, "PT11"), "s": index},
        )
        line_ids.append(line_id)
    db.flush()
    return request_id, line_ids


# --------------------------------------------------------------------------- AC-S6-1


def test_upgrade_adds_line_columns_and_drops_header(db):
    _rewind_to_pre_migration(db)
    promotion_id = _promotion(db)
    _request_with_lines(db, promotion_id=promotion_id, line_count=1)

    _run_upgrade(db)

    line_columns = {
        column["name"]
        for column in inspect(db.get_bind()).get_columns("price_tag_request_lines")
    }
    assert "promotion_id" in line_columns
    assert "manual_sell_price" in line_columns

    request_columns = {
        column["name"]
        for column in inspect(db.get_bind()).get_columns("price_tag_requests")
    }
    assert "promotion_id" not in request_columns

    fks = inspect(db.get_bind()).get_foreign_keys("price_tag_request_lines")
    promo_fk = next(
        fk for fk in fks if fk["constrained_columns"] == ["promotion_id"]
    )
    assert promo_fk["referred_table"] == "promotions"
    assert (promo_fk.get("options") or {}).get("ondelete") == "SET NULL"


# --------------------------------------------------------------------------- AC-S6-2


def test_backfill_copies_header_promotion_to_every_line(db):
    _rewind_to_pre_migration(db)
    promotion_id = _promotion(db)
    request_id, line_ids = _request_with_lines(
        db, promotion_id=promotion_id, line_count=3
    )

    _run_upgrade(db)

    rows = (
        db.execute(
            text(
                "SELECT promotion_id FROM price_tag_request_lines WHERE request_id = :r"
            ),
            {"r": request_id},
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert all(str(promotion_id_seen) == promotion_id for promotion_id_seen in rows), (
        "no line loses its promotion in the backfill"
    )


def test_downgrade_restores_header_from_first_line(db):
    _rewind_to_pre_migration(db)
    promotion_id = _promotion(db)
    request_id, _line_ids = _request_with_lines(
        db, promotion_id=promotion_id, line_count=2
    )
    _run_upgrade(db)

    _run_downgrade(db)

    stored = db.execute(
        text("SELECT promotion_id FROM price_tag_requests WHERE id = :r"),
        {"r": request_id},
    ).scalar()
    assert str(stored) == promotion_id


# --------------------------------------------------------------------------- AC-S8-5


def test_upgrade_splits_existing_open_tags(db):
    """A migration-time data step: every open group is split by the D6 builder.

    Seeds exactly what the combos slice leaves behind pre-D6 - a line with one
    open choice group and ONE tag with empty `choices` - and expects the
    migration to leave TWO tags behind, each answering the group, so no "Open"
    tag survives into the new world where the designer never splits one by
    hand.
    """
    _rewind_to_pre_migration(db)
    request_id, line_ids = _request_with_lines(db, line_count=1)
    line_id = line_ids[0]
    white_id = _product(db, "PT11WH")
    black_id = _product(db, "PT11BK")

    db.execute(
        text(
            "INSERT INTO price_tag_request_line_parts "
            "(id, line_id, role, candidates, sort_order) "
            "VALUES (:i, :l, 'Basin', CAST(:c AS jsonb), 0)"
        ),
        {"i": _uid(), "l": line_id, "c": f'["{white_id}", "{black_id}"]'},
    )
    db.execute(
        text(
            "INSERT INTO price_tag_request_tags (id, line_id, sort_order, quantity, choices) "
            "VALUES (:i, :l, 0, 1, '{}'::jsonb)"
        ),
        {"i": _uid(), "l": line_id},
    )
    db.flush()

    _run_upgrade(db)

    tags = db.execute(
        text(
            "SELECT id, choices FROM price_tag_request_tags "
            "WHERE line_id = :l ORDER BY sort_order"
        ),
        {"l": line_id},
    ).all()
    assert len(tags) == 2, "one tag per candidate, the open one gone"
    choice_maps = [dict(row.choices) for row in tags]
    assert {choices.get("Basin") for choices in choice_maps} == {white_id, black_id}
    assert all(choices for choices in choice_maps), "no tag is left with empty choices"
