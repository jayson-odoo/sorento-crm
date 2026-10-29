"""Migration `chan_alias_0001_sales_channel` (CHAT-CHANNEL-LOOKUPSET, AC-CCL-1 / AC-CCL-2).

Seeds lookup set `sales_channel_alias` with options `dealer` / `project` and the owner's starter keywords
(29 Oct 2026: "retail" = Dealer; 经销商 / 零售 / peruncit). Insert-only and idempotent: a second run adds no
duplicate and keeps what the owner entered since. Loaded by file path (the `_run_migration` idiom, see
`tests/test_migration_511_attribute_first_lookup_sets.py`), against a Postgres blank schema, never sqlite.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.services.reports.ask import SALES_CHANNELS
from tests._pg_fixture import blank_session

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "chan_alias_0001_sales_channel.py"
SET_KEY = "sales_channel_alias"
EXPECTED = {
    "dealer": {"retail", "retailer", "经销商", "零售", "peruncit"},
    "project": {"project team"},
}


def _load_migration():
    assert MIGRATION.exists(), f"{MIGRATION} does not exist yet"
    spec = importlib.util.spec_from_file_location("chan_alias_0001_sales_channel", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _keywords(db) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for value, keyword in db.execute(
        text(
            "SELECT o.value, k.keyword FROM lookup_sets s JOIN lookup_options o ON o.set_id = s.id "
            "LEFT JOIN lookup_option_keywords k ON k.option_id = o.id WHERE s.set_key = :key AND s.is_active "
            "AND o.is_active ORDER BY o.value, k.keyword"
        ),
        {"key": SET_KEY},
    ):
        out.setdefault(value, [])
        if keyword is not None:
            out[value].append(keyword)
    return out


def _set_count(db) -> int:
    return db.execute(text("SELECT count(*) FROM lookup_sets WHERE set_key = :key"), {"key": SET_KEY}).scalar()


def test_the_revision_id_is_under_32_characters_and_chains_onto_the_one_head():
    module = _load_migration()
    assert len(module.revision) <= 32, (module.revision, len(module.revision))
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    script_dir = ScriptDirectory.from_config(cfg)
    known = {rev.revision for rev in script_dir.walk_revisions()}
    parents = module.down_revision if isinstance(module.down_revision, tuple) else (module.down_revision,)
    assert all(p in known for p in parents), parents
    heads = script_dir.get_heads()
    assert len(heads) == 1, heads
    assert module.revision in {rev.revision for rev in script_dir.iterate_revisions(heads[0], "base")}


def test_option_values_stay_inside_the_sales_channels():
    module = _load_migration()
    assert {value for value, _label, _sort in module.OPTIONS} <= set(SALES_CHANNELS)
    assert set(module.KEYWORDS) <= set(SALES_CHANNELS)


def test_upgrade_seeds_the_set_options_and_keywords_and_downgrade_removes_them():
    module = _load_migration()
    with blank_session() as db:
        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            module.upgrade()
        got = _keywords(db)
        assert {v: set(k) for v, k in got.items()} == EXPECTED, got
        assert _set_count(db) == 1

        with Operations.context(ctx):
            module.downgrade()
        assert _set_count(db) == 0
        assert _keywords(db) == {}


def test_a_second_upgrade_adds_no_duplicate_and_keeps_the_owners_edits():
    module = _load_migration()
    with blank_session() as db:
        ctx = MigrationContext.configure(db.connection())
        with Operations.context(ctx):
            module.upgrade()
        # The owner adds a keyword and renames the set on Master Data > Lookup sets.
        db.execute(
            text(
                "INSERT INTO lookup_option_keywords (id, option_id, keyword, locale) "
                "SELECT gen_random_uuid(), o.id, 'kedai', NULL FROM lookup_options o "
                "JOIN lookup_sets s ON s.id = o.set_id WHERE s.set_key = :key AND o.value = 'dealer'"
            ),
            {"key": SET_KEY},
        )
        db.execute(text("UPDATE lookup_sets SET name = 'Owner Name' WHERE set_key = :key"), {"key": SET_KEY})
        with Operations.context(ctx):
            module.upgrade()

        got = _keywords(db)
        assert sorted(got["dealer"]) == sorted([*EXPECTED["dealer"], "kedai"]), got
        assert got["project"] == ["project team"], got
        assert _set_count(db) == 1
        assert db.execute(text("SELECT name FROM lookup_sets WHERE set_key = :key"), {"key": SET_KEY}).scalar() == "Owner Name"
