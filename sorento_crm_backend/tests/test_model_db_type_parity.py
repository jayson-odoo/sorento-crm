"""Catch model <-> database column-type drift for uuid columns.

The bug class (see migration 301): a model column is typed pg ``UUID`` but the
real column in a long-lived, incrementally-migrated database is still ``varchar``.
The ORM then emits ``WHERE col = $1::uuid`` and Postgres rejects ``varchar = uuid``
at runtime — exactly what broke ``user_sessions.id`` in production. It never
showed in CI because CI builds its database with ``create_all`` straight from the
models, so the columns are uuid by construction; the drift only exists on a
database that was built by running migrations over time.

Two guards:

1. ``test_known_uuid_columns_are_typed_uuid_in_models`` — cheap, DB-free. Pins the
   columns that were flipped ``String -> UUID`` (commit 2d0ced269 / migration 301)
   as still uuid in the models, so an accidental revert to ``String`` (it has
   flip-flopped before) fails loudly in CI.

2. ``test_uuid_model_columns_are_uuid_in_the_database`` — walks every pg-UUID model
   column and asserts the connected database agrees. A no-op against a fresh
   ``create_all`` database (CI), but the intended way to catch real drift is to
   point ``DATABASE_URL`` at a production mirror and run it there.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID

import app.models  # noqa: F401  — registers every model on Base.metadata
from app.database import Base

# The columns migration 301 converges. If the model reverts any of these to
# String, test #1 fails before the mismatch can reach a database.
KNOWN_UUID_COLUMNS: list[tuple[str, str]] = [
    ("attachments", "entity_id"),
    ("attachments", "uploaded_by"),
    ("attachments", "deleted_by"),
    ("audit_logs", "user_id"),
    ("orders", "created_by"),
    ("orders", "updated_by"),
    ("orders", "billing_address_id"),
    ("orders", "shipping_address_id"),
    ("products", "created_by"),
    ("products", "updated_by"),
    ("brands", "created_by"),
    ("customers", "created_by"),
    ("product_categories", "created_by"),
    ("promotions", "created_by"),
    ("marketing_campaigns", "created_by"),
    ("inbound_shipments", "created_by"),
    ("spo_allocations", "created_by"),
    ("picking_headers", "picked_by_user_id"),
    ("picking_headers", "inspected_by_user_id"),
    ("picking_headers", "source_entity_id"),
    ("stock", "zone_id"),
    ("warehouses", "manager_id"),
    ("user_sessions", "id"),
]


def _model_column(table_name: str, column_name: str):
    table = Base.metadata.tables.get(table_name)
    if table is None:
        return None
    return table.columns.get(column_name)


def test_known_uuid_columns_are_typed_uuid_in_models():
    """Regression pin for the flip-flop-prone 23 columns (migration 301)."""
    wrong = []
    for tname, cname in KNOWN_UUID_COLUMNS:
        col = _model_column(tname, cname)
        if col is None:
            wrong.append(f"{tname}.{cname}: column missing from the model")
        elif not isinstance(col.type, PGUUID):
            wrong.append(f"{tname}.{cname}: model type is {col.type!r}, expected pg UUID")
    assert not wrong, (
        "These columns must stay pg UUID in the models (migration 301 converts the "
        "database to match). A revert to String reintroduces the uuid=varchar break:\n  "
        + "\n  ".join(wrong)
    )


def _expected_uuid_columns() -> list[tuple[str, str]]:
    return [
        (table.name, col.name)
        for table in Base.metadata.tables.values()
        for col in table.columns
        if isinstance(col.type, PGUUID)
    ]


def test_uuid_model_columns_are_uuid_in_the_database():
    """Every pg-UUID model column must be uuid in the connected database.

    Skips unless DATABASE_URL points at a reachable Postgres. Trivially green on a
    create_all database; run against a production mirror to catch real drift.
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("DIRECT_URL")
    if not url or not url.startswith(("postgresql", "postgres:")):
        pytest.skip("needs a Postgres DATABASE_URL")
    engine = create_engine(url)
    try:
        existing = set(inspect(engine).get_table_names(schema="public"))
    except Exception as exc:  # unreachable DB — nothing to assert against
        pytest.skip(f"database not reachable: {exc}")

    mismatches: list[str] = []
    with engine.connect() as conn:
        for tname, cname in _expected_uuid_columns():
            if tname not in existing:
                continue
            data_type = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
                ),
                {"t": tname, "c": cname},
            ).scalar()
            if data_type is not None and data_type != "uuid":
                mismatches.append(f"{tname}.{cname}: model=uuid db={data_type}")

    assert not mismatches, (
        "The model declares these columns uuid but the database has them as another "
        "type — the ORM will emit `= $1::uuid` and Postgres will reject it at runtime. "
        "Apply migration 301 (or convert the column):\n  " + "\n  ".join(sorted(mismatches))
    )
