"""Migration ptag_0009 - one tag per existing line, and every saved doc re-keyed.

UAC: AC-S3-1 (migration half) and AC-S3-7. Written test-FIRST (PRINCIPLES.md
Phase 2): `alembic/versions/ptag_0009_combos_tags.py` does not exist, so
`_load_migration` fails the whole file at collection.

Why this is tested by RUNNING the migration rather than by asserting on the live
database: CI's database has no data, so "does every line have a tag" proves
nothing there, and the local one is a prod copy that is already past this
revision's lineage. The risk this file exists for is real and one-way - step 2
walks EVERY `page.doc` and `page_version.doc` in production and
rewrites each placed tag's `request_line_id` into a `request_tag_id`. A doc that
comes out wrong is a design marketing has to redraw, and a doc that comes out
EMPTY looks exactly like a request nobody ever designed.

The blank schema is built by `create_all`, so it already carries the POST
migration model. The pre-migration state is therefore rebuilt by hand below
(`_rewind_to_pre_migration`) before `upgrade()` runs, which is the only honest
way to exercise a migration whose own DDL is the thing under test.
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
    / "ptag_0009_combos_tags.py"
)


def _load_migration():
    # THE red line: the file does not exist until S3 lands.
    spec = importlib.util.spec_from_file_location("ptag0009", MIGRATION)
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


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


def _rewind_to_pre_migration(db) -> None:
    """Put the scratch schema back to how production looks before ptag_0009.

    `create_all` gave us the post-migration model, so the new tables and columns
    are dropped and the retired ones restored. Anything the migration is
    supposed to CREATE must be absent here, or `upgrade()` would be asserting
    against a schema that already agrees with it.
    """
    db.execute(text("DROP TABLE IF EXISTS price_tag_request_tags CASCADE"))
    db.execute(text("DROP TABLE IF EXISTS price_tag_request_line_parts CASCADE"))
    db.execute(text("DROP TABLE IF EXISTS product_combo_parts CASCADE"))
    db.execute(text("DROP TABLE IF EXISTS product_combos CASCADE"))
    db.execute(
        text(
            "ALTER TABLE price_tag_request_lines "
            "DROP COLUMN IF EXISTS combo_id, "
            "DROP COLUMN IF EXISTS package_warning, "
            "ADD COLUMN IF NOT EXISTS alternatives JSONB, "
            "ADD COLUMN IF NOT EXISTS marketing_price_override NUMERIC(15,2), "
            "ADD COLUMN IF NOT EXISTS marketing_override_reason TEXT"
        )
    )
    db.execute(
        text(
            "ALTER TABLE system_settings "
            "DROP COLUMN IF EXISTS price_tag_guarded_classes"
        )
    )
    db.flush()


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
            "VALUES (:i, :co, :c, :n, :cat, :br, :uom, 1599.00)"
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


def _contact(db) -> str:
    """`price_tag_requests.contact_id` is NOT NULL, so the chain starts here."""
    contact_id = _uid()
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number, name) VALUES (:i, :p, :n)"),
        {"i": contact_id, "p": f"+60{uuid.uuid4().hex[:9]}", "n": unique_code("contact")},
    )
    db.flush()
    return contact_id


def _request_with_lines(db, count: int = 2) -> tuple[str, list[str]]:
    request_id = _uid()
    db.execute(
        text(
            "INSERT INTO price_tag_requests "
            "(id, company_id, contact_id, doc_number, status) "
            "VALUES (:i, :co, :ct, :d, 'designing')"
        ),
        {
            "i": request_id,
            "co": SORENTO,
            "ct": _contact(db),
            "d": unique_code("PT")[:40],
        },
    )
    line_ids: list[str] = []
    for index in range(count):
        line_id = _uid()
        db.execute(
            text(
                "INSERT INTO price_tag_request_lines "
                "(id, request_id, line_type, product_id, quantity, sort_order, "
                " marketing_price_override, marketing_override_reason) "
                "VALUES (:i, :r, 'product', :p, :q, :s, :o, :rn)"
            ),
            {
                "i": line_id,
                "r": request_id,
                "p": _product(db, f"PTAG{index}"),
                "q": index + 2,
                "s": index,
                "o": "1299.00" if index == 0 else None,
                "rn": "ZZT roadshow price" if index == 0 else None,
            },
        )
        line_ids.append(line_id)
    db.flush()
    return request_id, line_ids


def _placed(tag_id: str, line_id: str, copy: int | None = None) -> dict:
    return {
        "id": f"{tag_id}-c{copy}" if copy is not None else tag_id,
        "template_id": "tpl-1",
        "request_line_id": line_id,
        "x_mm": 5,
        "y_mm": 5,
        "width_mm": 95,
        "height_mm": 44.5,
        "layers": [],
    }


def _tag_sheet_doc(placed: list[dict]) -> dict:
    return {
        "kind": "tag_sheet",
        "imposition": {
            "preset": "auto",
            "page_width_mm": 210,
            "page_height_mm": 297,
            "bleed_mm": 3,
            "gap_mm": 2,
        },
        "sheets": [{"id": "sheet-1", "tags": placed}],
    }


# Bare table names on purpose: `blank_session` puts the scratch `_dealer_kit`
# schema on the search_path, and a literal `dealer_kit.page` in raw SQL resolves
# to the REAL schema instead - which on this machine is a prod copy, so the write
# would land on live data and the FK would point at a request that is not there.
def _page_with_docs(db, request_id: str, draft: dict, version_doc: dict) -> tuple[str, str]:
    page_id, version_id = _uid(), _uid()
    db.execute(
        text(
            "INSERT INTO page (id, name, slug, kind, request_id, draft_doc) "
            "VALUES (:i, 'ZZT sheet', :s, 'tag_sheet', :r, CAST(:d AS jsonb))"
        ),
        {"i": page_id, "s": unique_code("sheet"), "r": request_id, "d": _json(draft)},
    )
    db.execute(
        text(
            "INSERT INTO page_version (id, page_id, version, doc) "
            "VALUES (:i, :p, 1, CAST(:d AS jsonb))"
        ),
        {"i": version_id, "p": page_id, "d": _json(version_doc)},
    )
    db.flush()
    return page_id, version_id


def _json(value) -> str:
    import json

    return json.dumps(value)


def _read_json(db, sql: str, params: dict):
    import json

    raw = db.execute(text(sql), params).scalar()
    return json.loads(raw) if isinstance(raw, str) else raw


def _tags_of(db, line_id: str) -> list[dict]:
    """The line's tags, with `id` as a STRING.

    Raw SQL hands a uuid column back as `uuid.UUID`, and the document these ids
    are compared against holds JSON strings - so an un-cast id fails every
    `request_tag_id ==` check below while looking identical when printed. Every
    id this file creates goes through `_uid()`, which is `str(uuid.uuid4())`,
    for the same reason.
    """
    return [
        {**dict(row._mapping), "id": str(row._mapping["id"])}
        for row in db.execute(
            text(
                "SELECT id, line_id, sort_order, quantity, choices, "
                "       marketing_price_override, marketing_override_reason "
                "FROM price_tag_request_tags WHERE line_id = :l ORDER BY sort_order"
            ),
            {"l": line_id},
        )
    ]


# --------------------------------------------------------------------------- AC-S3-1


def test_migration_ptag_0009_one_tag_per_line_and_doc_rekey(db):
    """Every existing line gets one tag; the override moves; every saved doc re-keys.

    The three halves of migration step 2, on one seeded request that has both an
    autosaved draft and a saved version - both are read by the designer and only
    one of them is what the PDF prints, so a migration that fixed one and not the
    other would be invisible until an export came out blank.
    """
    _rewind_to_pre_migration(db)
    request_id, (line_a, line_b) = _request_with_lines(db, 2)

    # Line A has two COPIES on the sheet (quantity 2) and line B one.
    draft = _tag_sheet_doc(
        [
            _placed("t-a", line_a, 0),
            _placed("t-a", line_a, 1),
            _placed("t-b", line_b, 0),
        ]
    )
    version_doc = _tag_sheet_doc([_placed("t-a", line_a, 0), _placed("t-b", line_b, 0)])
    page_id, version_id = _page_with_docs(db, request_id, draft, version_doc)

    _run_upgrade(db)

    # One tag per line, quantity copied, the override moved off the line.
    tags_a = _tags_of(db, line_a)
    tags_b = _tags_of(db, line_b)
    assert len(tags_a) == 1 and len(tags_b) == 1
    assert tags_a[0]["quantity"] == 2
    assert tags_b[0]["quantity"] == 3
    assert str(tags_a[0]["marketing_price_override"]) == "1299.00"
    assert tags_a[0]["marketing_override_reason"] == "ZZT roadshow price"
    assert tags_b[0]["marketing_price_override"] is None
    assert tags_a[0]["choices"] == {}

    # Step 4: the line columns are gone.
    columns = {
        column["name"]
        for column in inspect(db.get_bind()).get_columns("price_tag_request_lines")
    }
    assert "alternatives" not in columns
    assert "marketing_price_override" not in columns
    assert "marketing_override_reason" not in columns
    assert {"combo_id", "package_warning"} <= columns

    # Step 2: both documents now key on the TAG, copies keeping their -cN suffix.
    for sql, params in (
        ("SELECT draft_doc FROM page WHERE id = :i", {"i": page_id}),
        ("SELECT doc FROM page_version WHERE id = :i", {"i": version_id}),
    ):
        doc = _read_json(db, sql, params)
        placed = doc["sheets"][0]["tags"]
        assert all("request_line_id" not in tag for tag in placed), (
            "a doc left keyed on the line opens as though nothing was ever drawn"
        )
        keyed = {tag["request_tag_id"] for tag in placed}
        assert keyed == {tags_a[0]["id"], tags_b[0]["id"]}
        # Geometry and copy ids survive untouched - the migration re-keys, it
        # does not re-arrange.
        assert {tag["id"] for tag in placed} >= {"t-a-c0", "t-b-c0"}
        assert all(tag["x_mm"] == 5 and tag["width_mm"] == 95 for tag in placed)


def test_migration_drops_a_placement_whose_line_no_longer_exists(db):
    """A stale placement is dropped from the doc, not left un-keyed.

    Prod docs are years old and a line deleted from a request leaves its tag
    behind in the JSON. Left in place it would carry no `request_tag_id` at all,
    and the designer would read a tag it can neither resolve nor delete.
    """
    _rewind_to_pre_migration(db)
    request_id, (line_a, _line_b) = _request_with_lines(db, 2)
    ghost_line_id = _uid()

    draft = _tag_sheet_doc([_placed("t-a", line_a, 0), _placed("t-ghost", ghost_line_id, 0)])
    page_id, _version_id = _page_with_docs(db, request_id, draft, _tag_sheet_doc([]))

    _run_upgrade(db)

    placed = _read_json(
        db, "SELECT draft_doc FROM page WHERE id = :i", {"i": page_id}
    )["sheets"][0]["tags"]
    assert len(placed) == 1
    assert placed[0]["request_tag_id"] == _tags_of(db, line_a)[0]["id"]


def test_migration_leaves_a_catalogue_doc_alone(db):
    """Only `kind = 'tag_sheet'` docs are rewritten.

    A catalogue page's doc has a completely different shape; walking it would at
    best be a no-op and at worst corrupt a published brochure.
    """
    _rewind_to_pre_migration(db)
    page_id = _uid()
    catalogue = {"kind": "catalogue", "blocks": [{"id": "b1", "kind": "collection"}]}
    db.execute(
        text(
            "INSERT INTO page (id, name, slug, kind, draft_doc) "
            "VALUES (:i, 'ZZT catalogue', :s, 'catalogue', CAST(:d AS jsonb))"
        ),
        {"i": page_id, "s": unique_code("cat"), "d": _json(catalogue)},
    )
    db.flush()

    _run_upgrade(db)

    assert (
        _read_json(db, "SELECT draft_doc FROM page WHERE id = :i", {"i": page_id})
        == catalogue
    )


def test_migration_seeds_the_guarded_classes_setting(db):
    """`system_settings.price_tag_guarded_classes` arrives with the two classes.

    A NULL here would make the S2 guard warn about nothing on every existing
    tenant, which reads as the feature not working rather than as a missing
    default.
    """
    # Seeded through the model, BEFORE the rewind: `system_settings` has a dozen
    # NOT NULL columns whose defaults are Python-side, so a raw INSERT would be
    # a losing game of naming them one at a time.
    from app.models.user import SystemSetting

    db.add(SystemSetting(id=_uid()))
    db.flush()
    _rewind_to_pre_migration(db)

    _run_upgrade(db)

    stored = db.execute(text("SELECT price_tag_guarded_classes FROM system_settings")).scalar()
    assert list(stored) == ["Bathroom Furniture", "Kitchen Sink"]


# --------------------------------------------------------------------------- AC-S3-7


def test_migration_remaps_r9_pins(db):
    """r9's review pins and pinned line data follow the line onto its tag.

    Skipped when r9 has not merged: whoever merges SECOND owns the remap (the
    plan's risk register), so on a main without `price_tag_review_comments` this
    step is a documented no-op and there is nothing to assert.
    """
    inspector = inspect(db.get_bind())
    if not inspector.has_table("price_tag_review_comments"):
        pytest.skip("r9 has not merged: the remap step is a no-op by design")
    if "pinned_tag_data" not in {
        column["name"] for column in inspector.get_columns("price_tag_request_lines")
    }:
        pytest.skip("r9 has not merged: no pinned_tag_data to remap")

    _rewind_to_pre_migration(db)
    request_id, (line_a, _line_b) = _request_with_lines(db, 2)

    comment_id = _uid()
    db.execute(
        text(
            "INSERT INTO price_tag_review_comments (id, request_id, line_id, body) "
            "VALUES (:i, :r, :l, 'ZZT make the basin bigger')"
        ),
        {"i": comment_id, "r": request_id, "l": line_a},
    )
    db.execute(
        text(
            "UPDATE price_tag_request_lines "
            "SET pinned_tag_data = CAST(:d AS jsonb) WHERE id = :l"
        ),
        {"d": _json({"line_id": line_a, "code": "ZZT-1"}), "l": line_a},
    )
    db.flush()

    _run_upgrade(db)

    tag_id = _tags_of(db, line_a)[0]["id"]
    assert (
        db.execute(
            text("SELECT tag_id FROM price_tag_review_comments WHERE id = :i"),
            {"i": comment_id},
        ).scalar()
        == tag_id
    ), "a pin anchored to a line must anchor to that line's tag"

    comment_columns = {
        column["name"]
        for column in inspect(db.get_bind()).get_columns("price_tag_review_comments")
    }
    assert "line_id" not in comment_columns

    pinned = _read_json(
        db, "SELECT pinned_tag_data FROM price_tag_request_tags WHERE id = :i", {"i": tag_id}
    )
    assert pinned is not None
    assert pinned.get("tag_id") == tag_id
    assert "line_id" not in pinned


# ---------------------------------------------------------------------------
# `_locate` - the branch production takes, which no other test in this file
# reaches (review S2)
# ---------------------------------------------------------------------------


def test_locate_finds_the_dealer_kit_schema_when_the_search_path_does_not(db):
    """Production reaches `page` as `dealer_kit.page`; these tests reach it bare.

    Every other test here runs with the scratch `_dealer_kit` schema ON the
    search_path, so `_locate` returns the bare name and the qualified branch -
    the only one production ever takes - is never executed. A typo there would
    make the whole doc rewrite a silent no-op on the real database and be caught
    by nothing.

    Read-only: `SET LOCAL` is scoped to this transaction, which the fixture
    rolls back.
    """
    module = _load_migration()
    conn = db.connection()

    # Bare first, which is what the rest of this file exercises.
    assert module._locate(conn, "page") == "page"

    # Now hide the scratch schema the way production's search_path does, leaving
    # the REAL `dealer_kit` schema as the only place `page` can be found.
    db.execute(text("SET LOCAL search_path TO public"))
    assert module._locate(conn, "page") == "dealer_kit.page"
    assert module._locate(conn, "page_version") == "dealer_kit.page_version"

    # A table that is in neither place is None, not a guess.
    assert module._locate(conn, "zzt_table_that_does_not_exist") is None
