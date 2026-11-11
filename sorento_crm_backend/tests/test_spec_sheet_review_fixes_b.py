"""SPEC-SHEET-DESIGNER-PARITY B review fixes: row overrides over HTTP, table colour and shape
checks on page edits and template saves, image fetch caps. Written test-FIRST. Postgres only."""
from __future__ import annotations

import pytest

from ._pg_fixture import blank_session
from .test_project_spec_sheet import _chain  # noqa: F401  (helper, not a test)
from .test_project_spec_sheets_v2 import EDIT_SLUGS, _base, _client, _make, _restore


def _detail_page(client, c, sheet, key):
    got = client.get(_base(c, f"/{sheet.id}"))
    assert got.status_code == 200, got.text
    return next(p for p in got.json()["pages"] if p["key"] == key)


# ------------------------------------------------------------------ 1. overrides over HTTP


def test_overrides_round_trip_over_the_patch_route_and_survive_a_partial_patch():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            url = _base(c, f"/{sheet.id}")
            key, valve = f"set:{c['set'].id}", c["valve"].id
            ok = client.patch(
                url,
                json={
                    "rows": [
                        {"key": c["basin"].id, "description": "Typed text"},
                        {"key": key, "accessory_descriptions": {valve: "Valve typed"}},
                    ]
                },
            )
            assert ok.status_code == 200, ok.text
            assert _detail_page(client, c, sheet, c["basin"].id)["description"] == "Typed text"
            assert _detail_page(client, c, sheet, key)["accessory_descriptions"] == {valve: "Valve typed"}

            # A reader PATCH that names only the area keeps what it did not send.
            ok = client.patch(url, json={"rows": [{"key": c["basin"].id, "area": "Pantry"}]})
            assert ok.status_code == 200, ok.text
            page = _detail_page(client, c, sheet, c["basin"].id)
            assert page["area"] == "Pantry" and page["description"] == "Typed text"

            # An empty string resets it.
            ok = client.patch(url, json={"rows": [{"key": c["basin"].id, "description": ""}]})
            assert ok.status_code == 200, ok.text
            assert _detail_page(client, c, sheet, c["basin"].id)["description"] == ""
        finally:
            _restore(originals)


def test_the_row_schema_caps_the_overrides():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            url = _base(c, f"/{sheet.id}")
            key = c["basin"].id
            assert client.patch(url, json={"rows": [{"key": key, "description": "x" * 20_001}]}).status_code == 422
            many = {f"p{i}": "v" for i in range(201)}
            assert client.patch(url, json={"rows": [{"key": key, "accessory_descriptions": many}]}).status_code == 422
            assert client.patch(url, json={"rows": [{"key": key, "accessory_descriptions": {"k" * 121: "v"}}]}).status_code == 422
        finally:
            _restore(originals)


def test_the_service_caps_accessory_override_keys():
    from app.services import project_spec_sheet_service as spec

    kept = spec._accessory_descriptions({"k" * 500: "v", "ok": "v"})
    assert list(kept) == ["ok"]


# ------------------------------------------------------------------ 2/3. table checks


def _table(**over):
    side = {"color": "#000000", "width_mm": 0.2}
    cell = lambda: {"text": "x", "padding_mm": 1, "border": {"top": side}}  # noqa: E731
    layer = {
        "id": "tbl",
        "type": "table",
        "x_mm": 0,
        "y_mm": 0,
        "width_mm": 40,
        "height_mm": 10,
        "rotation_deg": 0,
        "z_index": 0,
        "locked": False,
        "visible": True,
        "slot_binding": None,
        "text_override": None,
        "props": {
            "kind": "table",
            "columns": [{"width_mm": 20}, {"width_mm": 20}],
            "rows": [{"height_mm": 5}],
            "cells": [[cell(), cell()]],
        },
    }
    for key, value in over.items():
        layer["props"][key] = value
    return layer


BAD_COLOURS = ["url(http://169.254.169.254/x)", "red; background:url(x)", "expression(1)"]


@pytest.mark.parametrize("bad", BAD_COLOURS)
def test_a_page_edit_refuses_a_table_colour_that_is_not_a_plain_colour(bad):
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        layer = _table()
        layer["props"]["cells"][0][0]["fill"] = bad
        with pytest.raises(AppException) as raised:
            spec.save_page_edit(db, sheet, c["basin"].id, [layer])
        assert raised.value.status_code == 422
        edge = _table()
        edge["props"]["cells"][0][0]["border"]["top"]["color"] = bad
        with pytest.raises(AppException):
            spec.save_page_edit(db, sheet, c["basin"].id, [edge])
        text = _table(color=bad)
        with pytest.raises(AppException):
            spec.save_page_edit(db, sheet, c["basin"].id, [text])


def test_a_page_edit_keeps_a_plain_table_colour():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        layer = _table(color="rgb(1, 2, 3)")
        layer["props"]["cells"][0][0]["fill"] = "#eee"
        layer["props"]["cells"][0][1]["fill"] = "transparent"
        spec.save_page_edit(db, sheet, c["basin"].id, [layer])


def test_a_page_edit_refuses_a_table_whose_grid_does_not_match():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        short = _table()
        short["props"]["cells"][0].pop()
        wide = _table(rows=[{"height_mm": 5}, {"height_mm": 5}])
        huge = _table(columns=[{"width_mm": 1}] * 51)
        for layer in (short, wide, huge):
            with pytest.raises(AppException) as raised:
                spec.save_page_edit(db, sheet, c["basin"].id, [layer])
            assert raised.value.status_code == 422


@pytest.mark.parametrize("field", ["doc"])
def test_template_saves_run_the_same_table_checks(field):
    from pydantic import ValidationError

    from app.schemas.price_tag import TagTemplateCreate, TagTemplateFromTagCreate, TagTemplateUpdate

    bad = _table()
    bad["props"]["cells"][0][0]["fill"] = "url(http://x/y)"
    doc = {"width_mm": 80, "height_mm": 60, "layers": [bad]}
    for model, extra in (
        (TagTemplateCreate, {"name": "n", "family": "f"}),
        (TagTemplateFromTagCreate, {"name": "n", "family": "f"}),
        (TagTemplateUpdate, {}),
    ):
        with pytest.raises(ValidationError):
            model(doc=doc, **extra)
    good = {"width_mm": 80, "height_mm": 60, "layers": [_table()]}
    assert TagTemplateCreate(name="n", family="f", doc=good).doc == good
    # A document with no table, or none of the layer keys, is untouched.
    assert TagTemplateCreate(name="n", family="f", doc={"anything": 1}).doc == {"anything": 1}


# ------------------------------------------------------------------ 8. image fetch caps


def test_inline_images_total_cap_is_100_mb():
    from app.tasks.catalogue_render_cli import IMAGES_TOTAL_MAX_BYTES, inline_images

    assert IMAGES_TOTAL_MAX_BYTES == 100 * 1024 * 1024
    assert inline_images([], lambda _u: None) == {}


def test_a_declared_oversize_body_is_not_read():
    from app.tasks.catalogue_render_cli import fetch_image_with_cap

    class Response:
        ok = True
        headers = {"content-type": "image/png", "content-length": str(30 * 1024 * 1024)}

        def body(self):  # pragma: no cover - must not be reached
            raise AssertionError("body read despite an oversize content-length")

    class Request:
        def get(self, _url, timeout=None):
            return Response()

    assert fetch_image_with_cap(Request(), "https://x/big.png") is None
