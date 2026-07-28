"""Migration 308 ships the intended requestor-picker state for the seeded market
segments, so a deploy does not depend on someone remembering to toggle it:

    project -> included   (the salesmen a PR / SF / stock inquiry is raised FOR)
    retail  -> excluded   (end buyers, never a requestor)

Also pins the revision id length: CI bootstraps a blank database and STAMPS the
head into ``alembic_version.version_num``, which alembic creates as VARCHAR(32).
A longer head id passes locally (legacy column widened to 255) and then fails the
job with "value too long for type character varying(32)".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.access import MarketSegment
from tests._pg_fixture import blank_session

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "308_requestor_uploader_attr.py"
)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _revision_id() -> str:
    match = re.search(r'^revision\s*=\s*"([^"]+)"', _MIGRATION.read_text(), re.M)
    assert match, "revision id not found in migration 308"
    return match.group(1)


def test_head_revision_id_fits_the_stamped_column():
    assert len(_revision_id()) <= 32, (
        f"{_revision_id()!r} is {len(_revision_id())} chars; the head id must fit "
        "alembic_version.version_num (VARCHAR(32) on a fresh database)"
    )


def test_migration_marks_project_included_and_retail_excluded(db):
    """The UPDATE statements the migration runs, replayed against the same rows."""
    db.add(MarketSegment(code="project", name="Project", is_active=True))
    db.add(MarketSegment(code="retail", name="Retail", is_active=True))
    db.commit()

    for code, flag in (("project", True), ("retail", False)):
        db.execute(
            text(
                "UPDATE market_segments SET is_requestor_selectable = :flag "
                "WHERE lower(code) = :code"
            ),
            {"flag": flag, "code": code},
        )
    db.commit()

    rows = dict(
        db.query(MarketSegment.code, MarketSegment.is_requestor_selectable).all()
    )
    assert rows["project"] is True
    assert rows["retail"] is False


def test_migration_body_actually_contains_those_statements():
    """Guard the test above from drifting away from the migration it describes."""
    body = _MIGRATION.read_text()
    assert '("project", True)' in body
    assert '("retail", False)' in body
    assert "is_requestor_selectable = :flag" in body
