"""SPEC-SHEET-DESIGNER-PARITY B6: `POST .../spec-sheets/{id}/apply-all` with
`{"op": "add", "layer": {...}, "origin_page_key": ...}` adds the layer to every page of the sheet.
Written test-FIRST. Postgres only.

Contract: the page's effective layers (its edit, else the pinned template) plus the new layer
under a new id derived per page; the same client `layer.id` sent again adds nothing; the layer is
validated like a page edit (422); the existing move / restyle route is unchanged.
An origin of the cover reaches the cover only, any other origin the item pages only (the rule
`apply_to_all_pages` already follows).
"""
from __future__ import annotations

from ._pg_fixture import blank_session
from .test_project_spec_sheet import _chain  # noqa: F401  (helper, not a test)
from .test_project_spec_sheets_v2 import (  # noqa: F401  (helpers, not tests)
    EDIT_SLUGS,
    VIEW_ONLY,
    _base,
    _client,
    _layer,
    _make,
    _restore,
    _uid,
)

MARK = "ADDED-B6"


def _url(c, sheet):
    return _base(c, f"/{sheet.id}/apply-all")


def _added(layers):
    return [layer for layer in layers if (layer.get("props") or {}).get("text") == MARK]


def test_add_puts_the_layer_once_on_every_item_page_with_a_fresh_id_each():
    from app.services import project_spec_sheet_service as spec

    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        set_key = f"set:{c['set'].id}"
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            new = _layer(MARK)
            ok = client.post(
                _url(c, sheet),
                json={"op": "add", "layer": new, "origin_page_key": c["basin"].id},
            )
            assert ok.status_code == 200, ok.text
            assert ok.json()["id"] == sheet.id

            edits = sheet.page_edits
            assert set(edits) == {c["basin"].id, set_key}  # item pages only, no cover
            ids = []
            for key in (c["basin"].id, set_key):
                layers = edits[key]["layers"]
                added = _added(layers)
                assert len(added) == 1, key
                assert added[0]["x_mm"] == new["x_mm"] and added[0]["width_mm"] == new["width_mm"]
                # The template's own layers are kept, the new one is on top of them.
                assert len(layers) >= 2
                assert len({layer["id"] for layer in layers}) == len(layers)
                ids.append(added[0]["id"])
            assert len(set(ids)) == 2
        finally:
            _restore(originals)


def test_adding_the_same_client_layer_again_adds_no_duplicate():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            body = {"op": "add", "layer": _layer(MARK), "origin_page_key": c["basin"].id}
            assert client.post(_url(c, sheet), json=body).status_code == 200
            before = {k: [layer["id"] for layer in v["layers"]] for k, v in sheet.page_edits.items()}
            again = client.post(_url(c, sheet), json=body)
            assert again.status_code == 200, again.text
            after = {k: [layer["id"] for layer in v["layers"]] for k, v in sheet.page_edits.items()}
            assert after == before
            for v in sheet.page_edits.values():
                assert len(_added(v["layers"])) == 1
        finally:
            _restore(originals)


def test_an_add_from_the_cover_reaches_the_cover_only():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            ok = client.post(
                _url(c, sheet), json={"op": "add", "layer": _layer(MARK), "origin_page_key": "cover"}
            )
            assert ok.status_code == 200, ok.text
            assert set(sheet.page_edits) == {"cover"}
            assert len(_added(sheet.page_edits["cover"]["layers"])) == 1
        finally:
            _restore(originals)


def test_an_invalid_layer_or_operation_is_a_422_and_changes_nothing():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        client, originals = _client(db, c["owner"], slugs=EDIT_SLUGS)
        try:
            bad_layer = {**_layer(MARK), "type": "hologram"}
            for body in (
                {"op": "add", "layer": bad_layer, "origin_page_key": c["basin"].id},
                {"op": "add", "origin_page_key": c["basin"].id},
                {"op": "add", "layer": "not-a-layer"},
                {"op": "explode", "layer": _layer(MARK)},
            ):
                refused = client.post(_url(c, sheet), json=body)
                assert refused.status_code == 422, (body, refused.text)
            assert sheet.page_edits == {}
        finally:
            _restore(originals)


def test_adding_to_every_page_needs_the_edit_right():
    with blank_session() as db:
        c = _chain(db)
        sheet = _make(db, c)
        for who, slugs in ((c["owner"], VIEW_ONLY), (_uid(), EDIT_SLUGS[:2])):
            client, originals = _client(db, who, slugs=slugs)
            try:
                refused = client.post(
                    _url(c, sheet),
                    json={"op": "add", "layer": _layer(MARK), "origin_page_key": c["basin"].id},
                )
                assert refused.status_code == 403, refused.text
            finally:
                _restore(originals)
        assert sheet.page_edits == {}
