"""Tile designs: the whitelist, the ordering, and the document shape.

The field list is a whitelist because a design that binds a field the renderer
cannot draw produces a blank space in a printed catalogue, and nobody notices
that until it is at the printer. Better a 422 while authoring.
"""
from __future__ import annotations

import os

import pytest

from app.services.dealer_kit import tile_template_service as svc
from app.services.error_handler import AppException
from tests._pg_fixture import pg_session, unique_code

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)


def _name() -> str:
    return f"ZZT {unique_code('tile')}"


def test_a_design_stores_its_fields_in_the_document():
    with pg_session() as db:
        row = svc.create_template(db, name=_name(), fields=["image", "name", "price"])
        # JSONB doc rather than columns, so adding a background later is a
        # document change instead of a migration.
        assert row.doc == {"fields": ["image", "name", "price"]}
        assert svc.fields_of(row) == ["image", "name", "price"]


def test_field_order_is_preserved_because_the_order_is_the_design():
    with pg_session() as db:
        row = svc.create_template(db, name=_name(), fields=["price", "image", "name"])
        assert svc.fields_of(row) == ["price", "image", "name"]


def test_a_repeated_field_is_collapsed_not_drawn_twice():
    with pg_session() as db:
        row = svc.create_template(db, name=_name(), fields=["name", "name", "price"])
        assert svc.fields_of(row) == ["name", "price"]


@pytest.mark.parametrize("bad", ["margin", "cost_price", "productName", "Image"])
def test_a_field_the_renderer_cannot_draw_is_refused(bad):
    with pg_session() as db:
        with pytest.raises(AppException) as caught:
            svc.create_template(db, name=_name(), fields=["name", bad])
        # AppException is an HTTPException; the message lives in `detail`.
        assert bad in str(caught.value.detail)


def test_a_design_must_show_something():
    with pg_session() as db:
        with pytest.raises(AppException):
            svc.create_template(db, name=_name(), fields=[])
        with pytest.raises(AppException):
            svc.create_template(db, name=_name(), fields=["  "])


def test_a_design_needs_a_name():
    with pg_session() as db:
        with pytest.raises(AppException):
            svc.create_template(db, name="   ", fields=["name"])


def test_updating_fields_replaces_them_rather_than_merging():
    # Merging would leave a removed field silently still rendering.
    with pg_session() as db:
        row = svc.create_template(db, name=_name(), fields=["image", "name", "price"])
        updated = svc.update_template(db, row.id, fields=["name"])
        assert svc.fields_of(updated) == ["name"]


def test_updating_the_name_leaves_the_fields_alone():
    with pg_session() as db:
        row = svc.create_template(db, name=_name(), fields=["image", "price"])
        updated = svc.update_template(db, row.id, name="ZZT renamed")
        assert updated.name == "ZZT renamed"
        assert svc.fields_of(updated) == ["image", "price"]


def test_an_unknown_design_is_404():
    import uuid

    with pg_session() as db:
        with pytest.raises(AppException) as caught:
            svc.get_template(db, str(uuid.uuid4()))
        assert caught.value.status_code == 404


def test_a_document_written_before_this_shape_reads_as_no_fields():
    # Defensive: `doc` is free-form JSONB, so a row from an older shape must not
    # explode the renderer.
    with pg_session() as db:
        row = svc.create_template(db, name=_name(), fields=["name"])
        row.doc = {"blocks": []}
        db.flush()
        assert svc.fields_of(row) == []


def test_deleting_a_design_removes_it():
    with pg_session() as db:
        row = svc.create_template(db, name=_name(), fields=["name"])
        svc.delete_template(db, row.id)
        with pytest.raises(AppException):
            svc.get_template(db, row.id)
