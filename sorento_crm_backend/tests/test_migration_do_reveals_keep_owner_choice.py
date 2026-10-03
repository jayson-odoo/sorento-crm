"""An owner-OFF DO field switch stays OFF through the deploy's upgrade (crew review, 4 Oct 2026).

`do_ask_0001_reveals` seeded `granted = true` for every DO key on every contact with
`ON CONFLICT ... DO UPDATE SET granted = true`, so on production the upgrade turned back ON every
DO switch the owner had turned OFF. The DO fields default ON in `granted_keys` (a missing row
reads as ON), so no seed is needed at all and an owner choice must survive the upgrade.

The test replays the revisions the deploy runs after `dev_login_0001` (the revision before the
lane), in order, through alembic's own script directory and an `Operations` context bound to the
scratch schema. It stays meaningful once `do_ask_0001_reveals` is deleted: whatever revisions
follow `dev_login_0001` then are the ones that must leave the owner's row alone.

A `test_migration_*` file: CI runs it serially (LESSONS 97).
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.services import contact_field_reveal_service

from tests._pg_fixture import blank_session

BASE_REVISION = "dev_login_0001"
WAREHOUSE = "delivery_orders.warehouse"
DO_KEYS = sorted(k for k, _label in contact_field_reveal_service.FIELD_REVEAL_KEYS if k.startswith("delivery_orders."))
BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _upgrade_steps():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    return script._upgrade_revs("head", BASE_REVISION)


def test_an_owner_off_do_switch_stays_off_after_the_upgrade(db):
    contact_id, admin_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number) VALUES (:id, :phone)"),
        {"id": contact_id, "phone": f"+60{uuid.uuid4().int % 10**10:010d}"},
    )
    db.execute(
        text(
            "INSERT INTO contact_field_reveals (id, respond_contact_id, field_key, granted, created_by) "
            "VALUES (:id, :c, :key, false, :admin)"
        ),
        {"id": str(uuid.uuid4()), "c": contact_id, "key": WAREHOUSE, "admin": admin_id},
    )

    with Operations.context(MigrationContext.configure(db.connection())):
        for step in _upgrade_steps():
            step.migration_fn()

    granted = db.execute(
        text("SELECT granted FROM contact_field_reveals WHERE respond_contact_id = :c AND field_key = :key"),
        {"c": contact_id, "key": WAREHOUSE},
    ).scalar()
    assert granted is False, "the upgrade turned an owner-OFF DO switch back ON"
    db.expire_all()
    effective = contact_field_reveal_service.granted_keys(db, contact_id)
    assert WAREHOUSE not in effective
    assert effective == [k for k in DO_KEYS if k != WAREHOUSE]
