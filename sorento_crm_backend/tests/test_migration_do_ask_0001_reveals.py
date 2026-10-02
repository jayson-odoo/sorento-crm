"""DO-ASK-SIMPLIFY rule 2: every contact that exists at deploy keeps the five DO fields.

Owner, 2 Oct 2026: all current respond contacts are internal, so each one is granted the five
`delivery_orders.*` reveal keys by the migration; a contact created afterwards starts hidden
(no row). Pinned against the migration's own function, the way
`test_migration_selfref_0001_n8n_sales_view.py` pins its grant: every contact gains the five,
a DO switch already off is switched on (owner rule change, 2 Oct 2026), a contact
created afterwards has none, running it twice changes nothing, and the
downgrade removes only these five keys.

A `test_migration_*` file: CI runs it serially (LESSONS 97).
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "do_ask_0001_reveals.py"
)
KEYS = {
    "delivery_orders.status",
    "delivery_orders.pickup_time",
    "delivery_orders.transporter",
    "delivery_orders.driver",
    "delivery_orders.lorry_plate",
}


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_do_ask_0001", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contact(db) -> str:
    contact_id = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number) VALUES (:id, :phone)"),
        {"id": contact_id, "phone": f"+60{uuid.uuid4().int % 10**10:010d}"},
    )
    return contact_id


def _rows(db, contact_id: str) -> dict[str, bool]:
    rows = db.execute(
        text("SELECT field_key, granted FROM contact_field_reveals WHERE respond_contact_id = :c"),
        {"c": contact_id},
    ).fetchall()
    return {key: granted for key, granted in rows}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def test_the_revision_id_fits_and_names_a_parent():
    module = _migration_module()
    assert module.revision == "do_ask_0001_reveals"
    assert len(module.revision) <= 32
    assert isinstance(module.down_revision, str)


def test_every_existing_contact_gains_the_five_keys(db):
    a, b = _contact(db), _contact(db)

    _migration_module().seed_do_reveals(db.connection())

    assert _rows(db, a) == {key: True for key in KEYS}
    assert _rows(db, b) == {key: True for key in KEYS}


def test_an_existing_contact_ends_with_every_do_field_switched_on(db):
    """Owner rule change (2 Oct 2026): every EXISTING contact defaults to ALL DO-ask fields
    revealed, so no current user sees any change. A DO switch already off on an existing
    contact (an earlier seed, a test copy) is switched on; the owner adjusts afterwards."""
    contact = _contact(db)
    db.execute(
        text(
            "INSERT INTO contact_field_reveals (id, respond_contact_id, field_key, granted) "
            "VALUES (:id, :c, 'delivery_orders.driver', false)"
        ),
        {"id": str(uuid.uuid4()), "c": contact},
    )

    _migration_module().seed_do_reveals(db.connection())

    assert _rows(db, contact) == {key: True for key in KEYS}


def test_a_contact_created_after_the_migration_has_no_do_field(db):
    """The new-contact default stays as built: no row, so every DO field is hidden."""
    _migration_module().seed_do_reveals(db.connection())
    later = _contact(db)
    assert _rows(db, later) == {}


def test_other_keys_are_untouched(db):
    contact = _contact(db)
    db.execute(
        text(
            "INSERT INTO contact_field_reveals (id, respond_contact_id, field_key, granted) "
            "VALUES (:id, :c, 'purchase_orders.cost', false)"
        ),
        {"id": str(uuid.uuid4()), "c": contact},
    )

    _migration_module().seed_do_reveals(db.connection())

    assert _rows(db, contact)["purchase_orders.cost"] is False


def test_running_it_twice_changes_nothing(db):
    contact = _contact(db)

    _migration_module().seed_do_reveals(db.connection())
    _migration_module().seed_do_reveals(db.connection())

    count = db.execute(
        text("SELECT count(*) FROM contact_field_reveals WHERE respond_contact_id = :c"), {"c": contact}
    ).scalar()
    assert count == 5


def test_downgrade_removes_only_the_five_keys(db):
    contact = _contact(db)
    db.execute(
        text(
            "INSERT INTO contact_field_reveals (id, respond_contact_id, field_key, granted) "
            "VALUES (:id, :c, 'purchase_orders.cost', true)"
        ),
        {"id": str(uuid.uuid4()), "c": contact},
    )
    module = _migration_module()
    module.seed_do_reveals(db.connection())

    module.drop_do_reveals(db.connection())

    assert _rows(db, contact) == {"purchase_orders.cost": True}
