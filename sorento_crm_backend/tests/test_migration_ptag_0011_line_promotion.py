"""Migration ptag_0011 - promotion and manual price move to the LINE (D1, S6).

UAC: AC-S6-1, AC-S6-2, AC-S8-5. Written test-FIRST (PRINCIPLES.md Phase 2):
`alembic/versions/ptag_0011_line_promotion.py` does not exist, so
`_load_migration` raises `FileNotFoundError` the moment any test here calls
`_run_upgrade`/`_run_downgrade` - the whole file is red for that one reason.

Why this is tested by RUNNING the migration rather than asserting on the live
database: CI's database has no data, and the local one is a prod copy already
past this revision's lineage (`test_migration_ptag_0009_combos_tags.py`
explains the same thing at more length).

Today's models (`app/models/price_tag.py`) predate this migration - the line
has no `promotion_id`/`manual_sell_price` columns and the request still carries
its own - so `blank_session`'s `create_all` schema already IS the pre-migration
state and `_rewind_to_pre_migration` below is a no-op right now. It stops being
one the moment S6 edits the models, which is exactly when this file needs it:
without it `create_all` would hand every test a schema the migration's own DDL
never touched, and `upgrade()` would be asserting against a database that
already agrees with it.
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
    # THE red line: the file does not exist until S6 lands.
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
    """See module docstring: a no-op today, load-bearing once S6 edits the models."""
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
    db.flush()


# ---------------------------------------------------------------------------
# Seeding - every FK target created here, CI's database is empty.
# ---------------------------------------------------------------------------


def _product(db):
    from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

    stem = unique_code("PT11")
    category = ProductCategory(
        id=_uid(), category_code=stem, category_name=f"ZZT cat {stem}"
    )
    brand = Brand(id=_uid(), brand_code=stem[:50], brand_name=f"ZZT {stem}")
    uom = UnitOfMeasure(id=_uid(), uom_code=stem[:20], uom_name="Each")
    db.add_all([category, brand, uom])
    db.flush()
    product = Product(
        id=_uid(),
        company_id=SORENTO,
        product_code=stem,
        product_name=f"ZZT product {stem}",
        category_id=category.id,
        brand_id=brand.id,
        base_uom_id=uom.id,
        list_price=100.00,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _promotion(db):
    from app.models.marketing import Promotion

    promotion = Promotion(
        id=_uid(),
        description=unique_code("ZZT promo"),
        is_active=True,
        company_id=SORENTO,
    )
    db.add(promotion)
    db.flush()
    return promotion


def _contact(db):
    from app.models.access import RespondContact

    contact = RespondContact(
        id=_uid(), phone_number=f"+60{uuid.uuid4().hex[:9]}", name=unique_code("contact")
    )
    db.add(contact)
    db.flush()
    return contact


def _request_with_lines(db, *, promotion_id=None, line_count=3):
    from app.models.price_tag import PriceTagRequest, PriceTagRequestLine

    contact = _contact(db)
    request = PriceTagRequest(
        id=_uid(),
        company_id=SORENTO,
        contact_id=contact.id,
        doc_number=unique_code("PT")[:30],
        status="designing",
        promotion_id=promotion_id,
    )
    db.add(request)
    db.flush()
    line_ids: list[str] = []
    for index in range(line_count):
        product = _product(db)
        line = PriceTagRequestLine(
            id=_uid(),
            request_id=request.id,
            line_type="product",
            product_id=product.id,
            sort_order=index,
        )
        db.add(line)
        db.flush()
        line_ids.append(line.id)
    db.commit()
    return request.id, line_ids


# --------------------------------------------------------------------------- AC-S6-1


def test_upgrade_adds_line_columns_and_drops_header(db):
    _rewind_to_pre_migration(db)
    promotion = _promotion(db)
    _request_with_lines(db, promotion_id=promotion.id, line_count=1)

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
    promotion = _promotion(db)
    request_id, line_ids = _request_with_lines(
        db, promotion_id=promotion.id, line_count=3
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
    assert all(str(promotion_id) == promotion.id for promotion_id in rows), (
        "no line loses its promotion in the backfill"
    )


def test_downgrade_restores_header_from_first_line(db):
    _rewind_to_pre_migration(db)
    promotion = _promotion(db)
    request_id, _line_ids = _request_with_lines(
        db, promotion_id=promotion.id, line_count=2
    )
    _run_upgrade(db)

    _run_downgrade(db)

    stored = db.execute(
        text("SELECT promotion_id FROM price_tag_requests WHERE id = :r"),
        {"r": request_id},
    ).scalar()
    assert str(stored) == promotion.id


# --------------------------------------------------------------------------- AC-S8-5


def test_upgrade_splits_existing_open_tags(db):
    """A migration-time data step: every open group is split by the D6 builder.

    Seeds exactly what the combos slice leaves behind today - a line with one
    open choice group and ONE tag with empty `choices` - and expects the
    migration to leave TWO tags behind, each answering the group, so no "Open"
    tag survives into the new world where the designer never splits one by hand.
    """
    from app.models.price_tag import PriceTagRequestLinePart, PriceTagRequestTag

    _rewind_to_pre_migration(db)
    request_id, line_ids = _request_with_lines(db, line_count=1)
    line_id = line_ids[0]
    white = _product(db)
    black = _product(db)
    db.add(
        PriceTagRequestLinePart(
            id=_uid(),
            line_id=line_id,
            role="Basin",
            candidates=[white.id, black.id],
            sort_order=0,
        )
    )
    db.add(
        PriceTagRequestTag(id=_uid(), line_id=line_id, sort_order=0, quantity=1, choices={})
    )
    db.commit()

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
    assert {choices.get("Basin") for choices in choice_maps} == {
        str(white.id),
        str(black.id),
    }
    assert all(choices for choices in choice_maps), "no tag is left with empty choices"
