"""DEALER-ACCESS-PORTAL D1: migration `dap_0001_dealer_access` grants `user_management.contacts.edit_own` to the
`salesperson` role (idempotent) and seeds the two owner tags when no tag of that name (case-insensitive) exists; an
existing tag of that name is left untouched.

Red test, written before the migration exists. Driven through `upgrade()` under an alembic `Operations` context on
the blank Postgres schema (the `agp3_0002` test's convention in tests/chatbot/agent/test_agent_writes_contacts.py):
`blank_session` pins `search_path` to the scratch schema, so the migration's raw SQL lands there and nowhere else.
Every row is seeded here; names are invented.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

import app.main  # noqa: F401  register every model
from app.models.access import ContactTag
from app.models.user import UserPermission, UserRole
from tests._pg_fixture import blank_session

REVISION = "dap_0001_dealer_access"
PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / f"{REVISION}.py"
EDIT_OWN = "user_management.contacts.edit_own"
SRT_TAG = "Sorento Business Owner"
MCH_TAG = "Mocha Business Owner"
CUSTOM = {"access_types": ["end_user"], "zzt_marker": "kept"}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _migration():
    if not PATH.exists():
        pytest.fail(f"expected migration module at {PATH} (revision id {REVISION!r})")
    spec = importlib.util.spec_from_file_location(REVISION, PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_role_and_permission(db) -> tuple[str, str]:
    role = UserRole(id=str(uuid.uuid4()), slug="salesperson", name="ZZT Salesperson")
    perm = db.query(UserPermission).filter(UserPermission.slug == EDIT_OWN).first()
    if perm is None:
        perm = UserPermission(id=str(uuid.uuid4()), slug=EDIT_OWN, name="ZZT Edit Own")
        db.add(perm)
    db.add(role)
    db.flush()
    return role.id, perm.id


def _upgrade(db, module) -> None:
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()


def _grants(db, role_id: str, perm_id: str) -> int:
    return db.execute(
        text("SELECT count(*) FROM user_role_permissions WHERE role_id = :r AND permission_id = :p"),
        {"r": role_id, "p": perm_id},
    ).scalar()


def _tags(db, name: str) -> list[tuple[str, dict, bool]]:
    rows = db.execute(
        text("SELECT name, settings, is_active FROM contact_tags WHERE lower(name) = lower(:n)"), {"n": name}
    ).all()
    return [(r[0], r[1] if isinstance(r[1], dict) else json.loads(r[1]), r[2]) for r in rows]


def _snapshot(db) -> tuple:
    return (
        sorted(tuple(r) for r in db.execute(text("SELECT role_id, permission_id FROM user_role_permissions")).all()),
        sorted((r[0], json.dumps(r[1], sort_keys=True)) for r in db.execute(text("SELECT name, settings FROM contact_tags")).all()),
    )


def test_D1_the_revision_id_is_named_and_fits_alembic():
    module = _migration()
    assert module.revision == REVISION
    assert len(module.revision) <= 32
    assert module.down_revision


def test_D1_upgrade_grants_edit_own_to_salesperson_seeds_mocha_keeps_an_existing_sorento_tag_and_reruns_as_a_no_op(db):
    module = _migration()
    role_id, perm_id = _seed_role_and_permission(db)
    db.add(ContactTag(id=str(uuid.uuid4()), name="sorento business owner", settings=CUSTOM, is_active=True))
    db.flush()

    _upgrade(db, module)

    assert _grants(db, role_id, perm_id) == 1
    mocha = _tags(db, MCH_TAG)
    assert len(mocha) == 1
    assert mocha[0][1] == {"access_types": ["mocha_dealer"]} and mocha[0][2] is True
    sorento = _tags(db, SRT_TAG)
    assert sorento == [("sorento business owner", CUSTOM, True)]

    before = _snapshot(db)
    _upgrade(db, module)
    assert _snapshot(db) == before
    assert _grants(db, role_id, perm_id) == 1


def test_D1_upgrade_on_a_schema_with_no_owner_tags_seeds_both_with_their_access_types(db):
    module = _migration()
    _seed_role_and_permission(db)

    _upgrade(db, module)

    sorento, mocha = _tags(db, SRT_TAG), _tags(db, MCH_TAG)
    assert len(sorento) == 1 and len(mocha) == 1
    assert sorento[0][0] == SRT_TAG and mocha[0][0] == MCH_TAG
    assert sorted(sorento[0][1]["access_types"]) == ["cabana_dealer", "dealer"]
    assert mocha[0][1]["access_types"] == ["mocha_dealer"]
