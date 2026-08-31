"""AC-A.6 - a key somebody owns keeps the readers that used to run underneath it.

`configured_rules` prefers a key's stored rules over the shipped ones entirely ("change
one and they become yours"), and four readers used to run OUTSIDE that list: the
product's own column, the `L x W x H` block, the product name head and the category.
Making them ordinary rows would therefore SILENTLY REMOVE them from every key a human
has ever edited - `class` holds 33 hand-written rules on the live database, and after
the change with no backfill those 33 would be the whole of it.

So the migration puts them in, where they ran:

  * `dim_length` and its siblings get their column and size rows PREPENDED - the column
    outranked the text, and it must go on outranking it.
  * `class` and `brand` get theirs APPENDED - the name head and the category ran
    UNDER whatever rules a human wrote, and a category row on top would re-class the
    catalogue on the strength of a filing code (20,697 of 23,063 live products sit in a
    category that carries one).

A row with no stored rules is left alone: it inherits the shipped list at read time, as
it always has.

Driven through `upgrade()` / `downgrade()` against the real database inside a rolled-back
transaction, exactly as `test_migration_443_fulfilment_planning_flag_tba_date.py` does
and for the reason recorded there: this migration's statements are raw SQL against
`product_spec_registry`, and raw SQL does not resolve through `blank_session`'s
schema-translate map, so a scratch copy would prove nothing (or worse, alter the real
table while asserting against an empty one).
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.services.product_spec_derivation import shipped_rules
from tests._pg_fixture import pg_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "450_spec_rules_readable.py"
)

_HUMAN_CLASS_RULES = [
    {"match": "code_contains", "pattern": "SRTSC", "value": "Seat Cover"},
    {"match": "ends_with", "pattern": "BIDET SPRAY", "value": "Bidet"},
]
_HUMAN_LENGTH_RULES = [{"match": "regex", "pattern": r"\bL\s*(\d+)", "capture": 1}]


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_450", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    """Run the migration body against this session's connection.

    `op.get_bind()` needs a MigrationContext, so one is built over the test's own
    connection - everything it writes is inside the transaction `pg_session` rolls back.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _has_column(db) -> bool:
    return "max_value" in {
        column["name"] for column in inspect(db.get_bind()).get_columns("product_spec_registry")
    }


def _own(db, spec_key: str, rules: list, unit: str | None) -> None:
    """Make `spec_key` a key this business has edited, whatever the database holds."""
    existing = db.execute(
        text("SELECT id FROM product_spec_registry WHERE spec_key = :key"), {"key": spec_key}
    ).first()
    payload = {"key": spec_key, "rules": json.dumps(rules), "unit": unit}
    if existing is None:
        db.execute(
            text(
                "INSERT INTO product_spec_registry (id, spec_key, label, data_type, unit,"
                " derivation_rules) VALUES (:id, :key, :key, 'numeric', :unit,"
                " CAST(:rules AS jsonb))"
            ),
            {**payload, "id": str(uuid.uuid4())},
        )
    else:
        db.execute(
            text(
                "UPDATE product_spec_registry SET derivation_rules = CAST(:rules AS jsonb),"
                " unit = :unit WHERE spec_key = :key"
            ),
            payload,
        )


def _rules(db, spec_key: str) -> list:
    return db.execute(
        text("SELECT derivation_rules FROM product_spec_registry WHERE spec_key = :key"),
        {"key": spec_key},
    ).scalar()


def _max_value(db, spec_key: str):
    return db.execute(
        text("SELECT max_value FROM product_spec_registry WHERE spec_key = :key"),
        {"key": spec_key},
    ).scalar()


def _hidden(spec_key: str, matches: set[str]) -> list[dict]:
    return [rule for rule in shipped_rules()[spec_key] if rule["match"] in matches]


@pytest.fixture
def db():
    with pg_session() as session:
        if _has_column(session):
            _run(session, "downgrade")
        _own(session, "class", _HUMAN_CLASS_RULES, None)
        _own(session, "dim_length", _HUMAN_LENGTH_RULES, "mm")
        _own(session, "thickness", [], "mm")
        yield session


def test_an_owned_class_key_keeps_the_name_head_and_the_category(db):
    _run(db)

    stored = _rules(db, "class")
    # A human's own rules stay on top, their CODE row moved below their text rows: the
    # engine this migration lands with runs the list in order, and the engine it
    # replaces ran every text rule before any code rule wherever the row sat. Moving it
    # changes what neither engine derives and makes the screen true.
    assert stored[: len(_HUMAN_CLASS_RULES)] == [
        _HUMAN_CLASS_RULES[1],
        _HUMAN_CLASS_RULES[0],
    ]
    added = stored[len(_HUMAN_CLASS_RULES) :]
    assert [rule["match"] for rule in added] == ["name_head", "from_field"]
    assert all(rule["shipped_backfill"] is True for rule in added)
    # Pinned to the engine's own list rather than retyped, so the two cannot drift.
    assert [
        {k: v for k, v in rule.items() if k != "shipped_backfill"} for rule in added
    ] == _hidden("class", {"name_head", "from_field"})


def test_an_owned_dimension_key_keeps_the_column_above_the_text(db):
    _run(db)

    stored = _rules(db, "dim_length")
    added = stored[: len(stored) - len(_HUMAN_LENGTH_RULES)]
    assert stored[len(added) :] == _HUMAN_LENGTH_RULES, "a human's rules stay below the readers"
    assert added[0]["match"] == "from_field", "the column outranked the text and still does"
    assert all(rule["shipped_backfill"] is True for rule in added)
    assert [
        {k: v for k, v in rule.items() if k != "shipped_backfill"} for rule in added
    ] == [rule for rule in shipped_rules()["dim_length"] if rule.get("source") != "flyer"]


def test_a_key_nobody_edited_is_left_alone(db):
    _run(db)

    assert _rules(db, "thickness") == [], "an empty column inherits the shipped rules at read time"


def test_the_cap_is_seeded_on_millimetre_keys_only(db):
    _run(db)

    assert float(_max_value(db, "dim_length")) == 5000.0
    assert float(_max_value(db, "thickness")) == 5000.0
    assert _max_value(db, "class") is None


def test_the_downgrade_removes_only_what_it_added(db):
    _run(db)
    _run(db, "downgrade")

    assert not _has_column(db)
    # The rows it added are gone. The code row stays where it moved to: that IS where
    # the old engine ran it, so putting it back on top would be the reversal that
    # changes behaviour.
    assert _rules(db, "class") == [_HUMAN_CLASS_RULES[1], _HUMAN_CLASS_RULES[0]]
    assert _rules(db, "dim_length") == _HUMAN_LENGTH_RULES
    assert _rules(db, "thickness") == []
