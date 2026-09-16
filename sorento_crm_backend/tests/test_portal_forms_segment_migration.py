"""Migration ptag_0012 - portal_form_types moves from contact access types to
market segments, schema only (D1, D4 r2: no seed / backfill data statements).

``blank_session()``'s ``create_all`` builds from CURRENT models, which already
IS the pre-ptag_0012 shape: ``market_segments`` carries no
``portal_form_types`` column yet and ``contact_access_types`` still does - so,
unlike ``test_migration_ptag_0011_line_promotion.py`` (whose migration trails
the models), no ``_rewind_to_pre_migration`` step is needed here. The model
catches up to the migration in this slice, not the other way round.

AC-D3 is a resolver assertion, not a migration-file one, but it is grouped
here per the tester brief's file split (migration file carries AC-D1..D4).
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from app.models.access import MarketSegment
from app.models.price_tag import ContactPortalFormOverride
from app.services.portal_form_visibility_service import resolve_visible_form_types
from app.services.portal_service import SUPPORTED_TYPES
from tests._pg_fixture import blank_session, unique_code

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "ptag_0012_segment_portal_forms.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("ptag0012", MIGRATION)
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


def _contact(db) -> str:
    contact_id = _uid()
    db.execute(
        text("INSERT INTO respond_contacts (id, phone_number, name) VALUES (:i, :p, :n)"),
        {"i": contact_id, "p": f"+60{uuid.uuid4().hex[:9]}", "n": unique_code("contact")},
    )
    db.flush()
    return contact_id


# --------------------------------------------------------------------------- AC-D1


def test_migration_adds_segment_column_and_drops_access_type_column(db):
    segment = MarketSegment(
        code=unique_code("seg").lower()[:50], name="ZZT segment", is_active=True
    )
    db.add(segment)
    db.flush()

    _run_upgrade(db)

    segment_columns = {
        c["name"]: c for c in inspect(db.get_bind()).get_columns("market_segments")
    }
    assert "portal_form_types" in segment_columns
    assert segment_columns["portal_form_types"]["nullable"] is False

    access_type_columns = {
        c["name"] for c in inspect(db.get_bind()).get_columns("contact_access_types")
    }
    assert "portal_form_types" not in access_type_columns

    default_value = db.execute(
        text("SELECT portal_form_types FROM market_segments WHERE code = :c"),
        {"c": segment.code},
    ).scalar()
    assert default_value == []

    _run_upgrade(db)  # second run converges, no error (idempotent column checks)


# --------------------------------------------------------------------------- AC-D2


def test_migration_writes_no_data_rows(db):
    active_segment = MarketSegment(
        code=unique_code("seg").lower()[:50], name="ZZT active", is_active=True
    )
    inactive_segment = MarketSegment(
        code=unique_code("seg").lower()[:50], name="ZZT inactive", is_active=False
    )
    db.add_all([active_segment, inactive_segment])
    contact_id = _contact(db)
    existing_override = ContactPortalFormOverride(
        id=_uid(), contact_id=contact_id, form_type="price_tag_request", is_enabled=True
    )
    db.add(existing_override)
    db.flush()

    _run_upgrade(db)

    rows = dict(
        db.execute(text("SELECT code, portal_form_types FROM market_segments")).all()
    )
    assert rows[active_segment.code] == [], "no seed/backfill - stays empty even though active"
    assert rows[inactive_segment.code] == []

    overrides = db.query(ContactPortalFormOverride).all()
    assert len(overrides) == 1, "no override rows written by the migration"
    kept = overrides[0]
    assert kept.id == existing_override.id
    assert kept.contact_id == contact_id
    assert kept.form_type == "price_tag_request"
    assert kept.is_enabled is True


# --------------------------------------------------------------------------- AC-D3


def test_contact_with_no_segment_and_no_override_sees_exactly_the_four_legacy_kinds(db):
    contact_id = _contact(db)

    visible = resolve_visible_form_types(db, contact_id)

    assert visible == set(SUPPORTED_TYPES)
    assert "price_tag_request" not in visible


# --------------------------------------------------------------------------- AC-D4


def test_migration_downgrade_restores_access_type_column(db):
    _run_upgrade(db)

    _run_downgrade(db)

    segment_columns = {
        c["name"] for c in inspect(db.get_bind()).get_columns("market_segments")
    }
    assert "portal_form_types" not in segment_columns

    access_type_columns = {
        c["name"]: c for c in inspect(db.get_bind()).get_columns("contact_access_types")
    }
    assert "portal_form_types" in access_type_columns
    assert access_type_columns["portal_form_types"]["nullable"] is False
