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

    R3 (Phase 3 security H2 / reviewer B3): the split must not throw away
    what already points at the open tag - a review comment anchored to it
    (`price_tag_review_comments.tag_id`) and a placement in the request's
    saved draft doc (keyed `{tag_id}-cN`). Both survive ONLY if the ORIGINAL
    tag id is kept for the FIRST candidate combination and the new siblings'
    placements are copied from the original's geometry - not "the open one
    gone", which is what `_split_open_tags` does today (`DELETE FROM
    price_tag_request_tags WHERE id = :id` before minting N fresh rows).
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
    original_tag_id = _uid()
    db.execute(
        text(
            "INSERT INTO price_tag_request_tags (id, line_id, sort_order, quantity, choices) "
            "VALUES (:i, :l, 0, 1, '{}'::jsonb)"
        ),
        {"i": original_tag_id, "l": line_id},
    )
    comment_id = _uid()
    db.execute(
        text(
            "INSERT INTO price_tag_review_comments (id, request_id, tag_id, round, body) "
            "VALUES (:i, :r, :t, 1, 'ZZT make the basin bigger')"
        ),
        {"i": comment_id, "r": request_id, "t": original_tag_id},
    )
    page_id = _uid()
    placement_id = f"{original_tag_id}-c0"
    doc = (
        '{"kind": "tag_sheet", "sheets": [{"id": "sheet-1", "tags": [{"id": "'
        + placement_id
        + '", "request_tag_id": "'
        + original_tag_id
        + '", "x_mm": 5, "y_mm": 5, "width_mm": 95, "height_mm": 44.5, "layers": []}]}]}'
    )
    db.execute(
        text(
            "INSERT INTO page (id, company_id, name, slug, kind, request_id, draft_doc) "
            "VALUES (:i, :co, 'ZZT Tags', :s, 'tag_sheet', :r, CAST(:d AS jsonb))"
        ),
        {"i": page_id, "co": SORENTO, "s": unique_code("sheet"), "r": request_id, "d": doc},
    )
    db.execute(
        text("UPDATE price_tag_requests SET page_id = :p WHERE id = :r"),
        {"p": page_id, "r": request_id},
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
    assert len(tags) == 2, "one tag per candidate"
    choice_maps = [dict(row.choices) for row in tags]
    assert {choices.get("Basin") for choices in choice_maps} == {white_id, black_id}
    assert all(choices for choices in choice_maps), "no tag is left with empty choices"

    # The ORIGINAL tag id survives, resolved to combination 0 (white, by
    # candidate order) - not deleted and replaced with two fresh ids.
    ids_by_choice = {choices.get("Basin"): str(row.id) for row, choices in zip(tags, choice_maps)}
    assert ids_by_choice[white_id] == original_tag_id, (
        "the tag that was already there keeps its id for the first candidate"
    )
    new_tag_id = ids_by_choice[black_id]
    assert new_tag_id != original_tag_id

    # The review comment still anchors to a REAL tag - the same one, since it
    # was never about "either basin", it was about the specific tag someone
    # commented on.
    stored_comment_tag_id = db.execute(
        text("SELECT tag_id FROM price_tag_review_comments WHERE id = :i"),
        {"i": comment_id},
    ).scalar()
    assert str(stored_comment_tag_id) == original_tag_id

    # The draft doc keeps the ORIGINAL placement (same id, same geometry,
    # still keyed to the original tag id) and gains a COPY for the new
    # sibling, not a doc that silently lost the second basin's tile.
    stored_doc = db.execute(
        text("SELECT draft_doc FROM page WHERE id = :i"), {"i": page_id}
    ).scalar()
    import json as _json

    doc_obj = _json.loads(stored_doc) if isinstance(stored_doc, str) else stored_doc
    placed = doc_obj["sheets"][0]["tags"]
    by_request_tag = {p["request_tag_id"]: p for p in placed}
    assert original_tag_id in by_request_tag, "the original placement is untouched"
    assert by_request_tag[original_tag_id]["id"] == placement_id
    assert by_request_tag[original_tag_id]["x_mm"] == 5
    assert new_tag_id in by_request_tag, (
        "the new sibling gets a COPY of the original's placement, not a blank tile"
    )
    assert by_request_tag[new_tag_id]["x_mm"] == 5
    assert by_request_tag[new_tag_id]["width_mm"] == 95


def test_upgrade_two_open_groups_same_combo_order_as_the_service_builder(db):
    """R14: `_split_open_tags`'s own `SELECT ... FROM price_tag_request_line_parts`
    carries no `ORDER BY` - with TWO open groups on one line, which group is
    treated as the outer loop of `itertools.product` depends on whatever
    order Postgres happens to return the two rows in. The service builder
    (`PriceTagRequestService._add_line_tags`) never has this problem: it
    reads `line.parts`, a relationship ordered by `sort_order` (the LOWER
    sort_order group is always outermost).

    Forced deterministic here by inserting the HIGHER-sort_order group
    (Basin, 1) BEFORE the LOWER one (Faucet, 0) - a plain heap scan of a
    fresh two-row table within one uncommitted transaction returns insertion
    order, so an un-ordered migration puts Basin outermost while the service
    convention puts Faucet outermost; the second tag minted (sort_order 1)
    is where the two orderings are guaranteed to diverge.
    """
    _rewind_to_pre_migration(db)
    request_id, line_ids = _request_with_lines(db, line_count=1)
    line_id = line_ids[0]
    silver_id = _product(db, "PT11FSIL")
    gold_id = _product(db, "PT11FGLD")
    white_id = _product(db, "PT11BWHT")
    black_id = _product(db, "PT11BBLK")

    # Basin (sort_order 1) inserted FIRST.
    db.execute(
        text(
            "INSERT INTO price_tag_request_line_parts "
            "(id, line_id, role, candidates, sort_order) "
            "VALUES (:i, :l, 'Basin', CAST(:c AS jsonb), 1)"
        ),
        {"i": _uid(), "l": line_id, "c": f'["{white_id}", "{black_id}"]'},
    )
    # Faucet (sort_order 0) inserted SECOND.
    db.execute(
        text(
            "INSERT INTO price_tag_request_line_parts "
            "(id, line_id, role, candidates, sort_order) "
            "VALUES (:i, :l, 'Faucet', CAST(:c AS jsonb), 0)"
        ),
        {"i": _uid(), "l": line_id, "c": f'["{silver_id}", "{gold_id}"]'},
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
            "SELECT choices FROM price_tag_request_tags "
            "WHERE line_id = :l ORDER BY sort_order"
        ),
        {"l": line_id},
    ).all()
    assert len(tags) == 4, "2 x 2 combinations"

    # Faucet (sort_order 0) outermost, Basin (sort_order 1) innermost - the
    # SAME convention `line.parts`' `order_by` gives the service builder.
    # The SECOND tag (index 1) is where an un-ordered read diverges: Faucet
    # outermost puts {silver, black} second; Basin outermost (today's bug)
    # puts {white, gold} second instead.
    assert dict(tags[1].choices) == {"Faucet": silver_id, "Basin": black_id}
