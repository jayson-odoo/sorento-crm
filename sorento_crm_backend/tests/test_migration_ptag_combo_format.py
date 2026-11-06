"""Migration ptag_0015_combo_format (PRICETAG-COMBO-FORMAT S5 + S6).

UAC: documentation/plans/dealer-kit/pricetag-combo-format-acceptance-criteria.md, AC-26, AC-30.
Contract: `dealer_kit.tag_template.price_type` (nullable, CHECK list/selling/both) and the
two link tables trading `is_default` for `default_list` + `default_selling` with a partial
unique index each.

Written test-FIRST (PRINCIPLES.md Phase 2). The revision is looked up BY ID through alembic's
script directory, so whatever file name and `down_revision` the coder gives it, the whole file
is red with "revision not found" until it exists.

Pattern of `test_migration_ptag_0014_lpsp.py`: the blank schema is built by `create_all`, so
it already holds the POST shape; `_rewind` puts the pre-migration shape back by hand, then the
migration's own `upgrade()` / `downgrade()` runs inside the rolled-back transaction. Rows are
inserted with raw SQL, because the ORM models already describe the post shape.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests import _ptag_combo_seed as seed
from tests._pg_fixture import blank_session, unique_code

SORENTO = "00000000-0000-0000-0000-000000000001"
REVISION = "ptag_0015_combo_format"
BACKEND = Path(__file__).resolve().parents[1]


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


def _load():
    # THE red line: no such revision until the migration lands.
    script = _script_directory().get_revision(REVISION)
    if script is None:
        raise FileNotFoundError(f"alembic revision {REVISION} does not exist")
    return script.module


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
    """Back to production's shape before ptag_0015 (dropping a column drops its indexes)."""
    db.execute(text("ALTER TABLE tag_template DROP COLUMN IF EXISTS price_type"))
    for table, owner, old_index in (
        ("product_tag_template", "product_id", "uq_dealer_kit_product_tag_template_default"),
        ("combo_tag_template", "combo_id", "uq_dealer_kit_combo_tag_template_default"),
    ):
        db.execute(
            text(
                f"ALTER TABLE {table} DROP COLUMN IF EXISTS default_list, "
                "DROP COLUMN IF EXISTS default_selling, "
                "ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false"
            )
        )
        db.execute(
            text(f"CREATE UNIQUE INDEX IF NOT EXISTS {old_index} ON {table} ({owner}) WHERE is_default")
        )
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
            "SELECT pg_get_indexdef(i.indexrelid), pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i WHERE i.indrelid = to_regclass(:t) AND i.indisunique"
        ),
        {"t": table},
    ).all()
    return [{"def": r[0], "pred": r[1]} for r in rows]


# --------------------------------------------------------------------------- seeds (raw SQL)
def _template(db, name: str = "T") -> str:
    template_id = _uid()
    db.execute(
        text(
            "INSERT INTO tag_template (id, name, family, doc, print_size, company_id) "
            "VALUES (:i, :n, 'ala_carte', CAST('{}' AS jsonb), CAST('{}' AS jsonb), :co)"
        ),
        {"i": template_id, "n": unique_code(name), "co": SORENTO},
    )
    db.flush()
    return template_id


def _link(db, table: str, owner_col: str, owner_id: str, template_id: str, *, is_default=False) -> str:
    link_id = _uid()
    db.execute(
        text(
            f"INSERT INTO {table} (id, {owner_col}, template_id, is_default) "
            "VALUES (:i, :o, :t, :d)"
        ),
        {"i": link_id, "o": owner_id, "t": template_id, "d": is_default},
    )
    db.flush()
    return link_id


def _flags(db, table: str, link_id: str) -> tuple[bool, bool]:
    row = db.execute(
        text(f"SELECT default_list, default_selling FROM {table} WHERE id = :i"), {"i": link_id}
    ).one()
    return bool(row[0]), bool(row[1])


def _old_flag(db, table: str, link_id: str) -> bool:
    return bool(db.execute(text(f"SELECT is_default FROM {table} WHERE id = :i"), {"i": link_id}).scalar())


def _product_and_combo(db):
    host = seed.product(db, "ZZM15")
    return host, seed.combo(db, host, unique_code("ZZT 15 combo"))


# --------------------------------------------------------------------------- AC-26
def test_revision_id_fits_and_the_chain_has_a_single_head():
    """AC-26 / AC-30: id <= 32 chars, one alembic head."""
    module = _load()
    assert module.revision == REVISION
    assert len(module.revision) <= 32
    assert module.down_revision
    assert len(_script_directory().get_heads()) == 1


def test_upgrade_adds_a_nullable_checked_price_type_and_existing_rows_stay_null(db):
    """AC-26: nullable column, CHECK refuses 'x', rows that exist stay NULL."""
    _rewind(db)
    before = _template(db, "OLD")

    _run(db, "upgrade")

    column = _columns(db, "tag_template")["price_type"]
    assert column["notnull"] is False
    assert db.execute(text("SELECT price_type FROM tag_template WHERE id = :i"), {"i": before}).scalar() is None

    for value in ("list", "selling", "both", None):
        db.execute(
            text(
                "INSERT INTO tag_template (id, name, family, doc, print_size, company_id, price_type) "
                "VALUES (:i, :n, 'ala_carte', CAST('{}' AS jsonb), CAST('{}' AS jsonb), :co, :p)"
            ),
            {"i": _uid(), "n": unique_code("OK"), "co": SORENTO, "p": value},
        )
    savepoint = db.begin_nested()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO tag_template (id, name, family, doc, print_size, company_id, price_type) "
                "VALUES (:i, :n, 'ala_carte', CAST('{}' AS jsonb), CAST('{}' AS jsonb), :co, 'x')"
            ),
            {"i": _uid(), "n": unique_code("BAD"), "co": SORENTO},
        )
    savepoint.rollback()


# --------------------------------------------------------------------------- AC-30
def test_upgrade_backfills_is_default_into_both_flags_and_drops_the_old_column(db):
    """AC-30: `is_default = true` -> both flags true; others false; same for combos."""
    _rewind(db)
    host, combo = _product_and_combo(db)
    a, b, c = _template(db, "A"), _template(db, "B"), _template(db, "C")
    p_default = _link(db, "product_tag_template", "product_id", host.id, a, is_default=True)
    p_other = _link(db, "product_tag_template", "product_id", host.id, b)
    c_default = _link(db, "combo_tag_template", "combo_id", combo.id, b, is_default=True)
    c_other = _link(db, "combo_tag_template", "combo_id", combo.id, c)

    _run(db, "upgrade")

    assert _flags(db, "product_tag_template", p_default) == (True, True)
    assert _flags(db, "product_tag_template", p_other) == (False, False)
    assert _flags(db, "combo_tag_template", c_default) == (True, True)
    assert _flags(db, "combo_tag_template", c_other) == (False, False)
    for table in ("product_tag_template", "combo_tag_template"):
        columns = _columns(db, table)
        assert "is_default" not in columns, table
        for name in ("default_list", "default_selling"):
            assert columns[name]["notnull"] is True, (table, name)
            assert "false" in (columns[name]["default"] or "").lower(), (table, name)


@pytest.mark.parametrize(
    "table, owner_col, index_stem",
    [
        ("product_tag_template", "product_id", "uq_dealer_kit_product_tag_template_default"),
        ("combo_tag_template", "combo_id", "uq_dealer_kit_combo_tag_template_default"),
    ],
)
def test_one_default_per_type_per_owner(db, table, owner_col, index_stem):
    """AC-30: a second default_list (or default_selling) row for one owner is refused."""
    _rewind(db)
    _run(db, "upgrade")
    host, combo = _product_and_combo(db)
    owner = host.id if owner_col == "product_id" else combo.id
    a, b = _template(db, "A"), _template(db, "B")

    indexes = _unique_indexes(db, table)
    for flag in ("default_list", "default_selling"):
        assert any(
            owner_col in i["def"] and i["pred"] and flag in i["pred"] for i in indexes
        ), (flag, indexes)
    names = {i["def"] for i in indexes}
    assert any(f"{index_stem}_list" in d for d in names) and any(f"{index_stem}_selling" in d for d in names)

    def insert(template_id, **flags):
        db.execute(
            text(
                f"INSERT INTO {table} (id, {owner_col}, template_id, default_list, default_selling) "
                "VALUES (:i, :o, :t, :l, :s)"
            ),
            {"i": _uid(), "o": owner, "t": template_id, "l": flags.get("l", False), "s": flags.get("s", False)},
        )
        db.flush()

    insert(a, l=True)
    for flags in ({"l": True}, {"s": True, "l": True}):
        savepoint = db.begin_nested()
        with pytest.raises(IntegrityError):
            insert(b, **flags)
        savepoint.rollback()
    insert(b, s=True)  # the SP default may differ from the LP default
    savepoint = db.begin_nested()
    with pytest.raises(IntegrityError):
        insert(_template(db, "C"), s=True)
    savepoint.rollback()


def test_downgrade_restores_is_default_and_drops_the_new_columns(db):
    """AC-26 / AC-30: `is_default = default_selling`, or `default_list` where the owner has no
    `default_selling` row; the new columns go; upgrading again is clean."""
    _rewind(db)
    _run(db, "upgrade")
    host_a, combo = _product_and_combo(db)
    host_b = seed.product(db, "ZZM15B")
    host_c = seed.product(db, "ZZM15C")
    t = [_template(db, f"T{i}") for i in range(5)]

    def link(table, col, owner, template_id, l, s):
        link_id = _uid()
        db.execute(
            text(
                f"INSERT INTO {table} (id, {col}, template_id, default_list, default_selling) "
                "VALUES (:i, :o, :t, :l, :s)"
            ),
            {"i": link_id, "o": owner, "t": template_id, "l": l, "s": s},
        )
        db.flush()
        return link_id

    # product A: separate LP and SP defaults -> the SP one becomes is_default
    a_list = link("product_tag_template", "product_id", host_a.id, t[0], True, False)
    a_sell = link("product_tag_template", "product_id", host_a.id, t[1], False, True)
    # product B: only an LP default -> it becomes is_default
    b_list = link("product_tag_template", "product_id", host_b.id, t[2], True, False)
    # product C: one row holding both -> is_default
    c_both = link("product_tag_template", "product_id", host_c.id, t[3], True, True)
    # combo: only an SP default
    k_sell = link("combo_tag_template", "combo_id", combo.id, t[4], False, True)

    _run(db, "downgrade")

    assert _old_flag(db, "product_tag_template", a_sell) is True
    assert _old_flag(db, "product_tag_template", a_list) is False
    assert _old_flag(db, "product_tag_template", b_list) is True
    assert _old_flag(db, "product_tag_template", c_both) is True
    assert _old_flag(db, "combo_tag_template", k_sell) is True
    for table in ("product_tag_template", "combo_tag_template"):
        columns = _columns(db, table)
        assert "default_list" not in columns and "default_selling" not in columns, table
        assert columns["is_default"]["notnull"] is True
    assert "price_type" not in _columns(db, "tag_template")

    _run(db, "upgrade")
    assert _flags(db, "product_tag_template", a_sell) == (True, True)
    assert "price_type" in _columns(db, "tag_template")
