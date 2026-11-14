"""B6/B7 fix round: every designer layer type saves, apply-all reaches Every page copies, an add
that adds nothing is no edit, a foreign asset is refused. Written test-FIRST. Postgres only."""
from __future__ import annotations

import pytest

from ._pg_fixture import blank_session
from .test_project_spec_sheet import _chain  # noqa: F401  (helper, not a test)
from .test_project_spec_sheets_v2 import (  # noqa: F401  (helpers, not tests)
    EDIT_SLUGS,
    _asset,
    _asset_layer,
    _base,
    _client,
    _layer,
    _make,
    _restore,
    _uid,
)

MARK = "FIX-B6"
DESIGNER_TYPES = [
    "image", "text", "shape", "product_slot", "price_badge", "badge", "barcode", "group",
    "feature_icons", "accessories", "table",
]


def _url(c, sheet, layer_id="client-layer"):
    return _base(c, f"/{sheet.id}/layers/{layer_id}/apply-all")


def _typed(kind, n):
    props = {"kind": kind}
    if kind == "table":
        props = {"kind": "table", "columns": [{"width_mm": 10}], "rows": [{"height_mm": 5}], "cells": [[{"text": "x"}]]}
    return {
        "id": f"t{n}", "type": kind, "x_mm": 1, "y_mm": 1, "width_mm": 10, "height_mm": 5,
        "rotation_deg": 0, "z_index": n, "props": props,
    }


def test_a_page_edit_holding_one_of_each_designer_layer_type_saves_and_an_unknown_type_does_not():
    from app.services import project_spec_sheet_service as spec
    from app.services.error_handler import AppException

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        spec.save_page_edit(db, sheet, c["basin"].id, [_typed(k, i) for i, k in enumerate(DESIGNER_TYPES)])
        assert len(sheet.page_edits[c["basin"].id]["layers"]) == len(DESIGNER_TYPES)
        with pytest.raises(AppException) as raised:
            spec.save_page_edit(db, sheet, c["basin"].id, [{**_typed("text", 1), "type": "hologram"}])
        assert raised.value.status_code == 422


def test_the_layer_types_match_the_frontend_union():
    import re
    from pathlib import Path

    from app.services import project_spec_sheet_service as spec

    source = (Path(__file__).resolve().parents[2] / "sorento_crm_frontend/lib/dealer-kit/tag-template-types.ts").read_text()
    block = source[source.index("export type TagLayerType"):]
    block = block[: block.index(";")]
    assert set(re.findall(r"'([a-z_]+)'", block)) == set(spec.LAYER_TYPES)


def test_an_add_to_every_page_accepts_an_accessories_layer():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        layer = _typed("accessories", 1)
        layer["id"] = "client-acc"
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            ok = client.post(
                _url(c, sheet, "client-acc"),
                json={"op": "add", "layer": layer, "origin_page_key": c["basin"].id},
            )
            assert ok.status_code == 200, ok.text
        finally:
            _restore(originals)


def test_apply_all_moves_the_copies_an_every_page_add_made():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        layer = _layer(MARK)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            add = client.post(
                _url(c, sheet, layer["id"]),
                json={"op": "add", "layer": layer, "origin_page_key": c["basin"].id},
            )
            assert add.status_code == 200, add.text
            move = client.post(_url(c, sheet, layer["id"]), json={"changes": {"x_mm": 33}})
            assert move.status_code == 200, move.text
            for edit in sheet.page_edits.values():
                added = [l for l in edit["layers"] if l.get("source_id") == layer["id"]]
                assert [l["x_mm"] for l in added] == [33]
        finally:
            _restore(originals)


def test_an_origin_page_already_holding_the_client_layer_gets_no_second_copy():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        layer = _layer(MARK)
        spec.save_page_edit(db, sheet, c["basin"].id, [layer])  # the reader saved it first
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            ok = client.post(
                _url(c, sheet, layer["id"]),
                json={"op": "add", "layer": layer, "origin_page_key": c["basin"].id},
            )
            assert ok.status_code == 200, ok.text
            origin = sheet.page_edits[c["basin"].id]["layers"]
            assert [l["id"] for l in origin] == [layer["id"]]
        finally:
            _restore(originals)


def test_a_foreign_company_asset_in_an_add_is_422_and_changes_nothing():
    from app.models.company import Company
    from ._pg_fixture import unique_code

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        other = Company(id=_uid(), name="ZZT Other", code=unique_code("OTH")[:20])
        db.add(other)
        db.flush()
        foreign = _asset(db, other.id)
        layer = _asset_layer(foreign.id)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            refused = client.post(
                _url(c, sheet, layer["id"]),
                json={"op": "add", "layer": layer, "origin_page_key": c["basin"].id},
            )
            assert refused.status_code == 422, refused.text
            assert sheet.page_edits == {}
        finally:
            _restore(originals)


def test_an_add_that_added_nothing_is_not_an_edit():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        layer = _layer(MARK)
        spec.add_layer_to_all_pages(db, sheet, layer["id"], layer, user_id=c["owner"], origin_page_key=c["basin"].id)
        stamped = (sheet.updated_at, sheet.updated_by)
        spec.add_layer_to_all_pages(db, sheet, layer["id"], layer, user_id=_uid(), origin_page_key=c["basin"].id)
        assert (sheet.updated_at, sheet.updated_by) == stamped
