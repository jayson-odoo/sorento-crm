"""TAG-TEMPLATE-DUPLICATE (owner 6 Nov): duplicate a tag template.

PLAN: documentation/plans/dealer-kit/PLAN-tag-template-duplicate-06nov.md

`POST /tag-templates/{id}/duplicate` makes a new DRAFT template named "<name> (copy)" (then
"(copy 2)", "(copy 3)" ...) with the source's family, price type, print size and its latest doc
(the draft, which is never older than the live version). Product/combo links, versions and
request lines are not copied. Gated by `dealer_kit.tag_templates.manage`, the same as create.
"""
from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  (first app import)
from app.models.dealer_kit import (
    ComboTagTemplate,
    ProductTagTemplate,
    TagTemplate,
    TagTemplateVersion,
)
from tests._pg_fixture import unique_code
from tests.test_product_combos import _combo, _product
from tests.test_tag_template_bulk_delete import _VIEWER_ID, api  # noqa: F401

BASE = "/api/v1/dealer-kit/tag-templates"

_LAYERS = [
    {
        "id": "bg",
        "type": "image",
        "x": 0,
        "y": 0,
        "w": 85,
        "h": 58,
        "props": {"asset_id": "asset-123", "fit": "cover"},
    },
    {
        "id": "name",
        "type": "text",
        "x": 4,
        "y": 4,
        "w": 60,
        "h": 8,
        "props": {"text": "{{product.name}}", "font_size": 12},
    },
]


def _source(client: TestClient, *, name: str | None = None, price_type: str | None = "selling") -> dict:
    doc = {"layers": copy.deepcopy(_LAYERS), "width_mm": 85, "height_mm": 58}
    res = client.post(
        BASE,
        json={
            "name": name or unique_code("Dup"),
            "family": "toilet",
            "doc": doc,
            "print_size": {"width_mm": 85, "height_mm": 58, "sheet": {"cols": 2, "rows": 4, "turn": False}},
            "price_type": price_type,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _duplicate(client: TestClient, template_id: str):
    return client.post(f"{BASE}/{template_id}/duplicate")


def test_copy_carries_the_doc_and_settings_as_a_new_draft(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        src = _source(client)
        assert client.post(f"{BASE}/{src['id']}/publish", json={}).status_code == 200

        res = _duplicate(client, src["id"])
        assert res.status_code == 201, res.text
        dup = res.json()

    assert dup["id"] != src["id"]
    assert dup["name"] == f"{src['name']} (copy)"
    assert dup["family"] == src["family"]
    assert dup["price_type"] == "selling"
    assert dup["doc"] == src["doc"]
    assert dup["print_size"] == src["print_size"]
    # Draft: no live pointer and no version rows.
    assert dup["published_version_id"] is None
    assert db.query(TagTemplateVersion).filter(TagTemplateVersion.template_id == dup["id"]).count() == 0


def test_copy_takes_the_latest_draft_not_the_live_version(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        src = _source(client)
        assert client.post(f"{BASE}/{src['id']}/publish", json={}).status_code == 200
        edited = copy.deepcopy(src["doc"])
        edited["layers"][1]["props"]["text"] = "edited after publish"
        res = client.put(f"{BASE}/{src['id']}", json={"doc": edited})
        assert res.status_code == 200, res.text

        dup = _duplicate(client, src["id"]).json()

    assert dup["doc"]["layers"][1]["props"]["text"] == "edited after publish"


def test_links_are_not_copied_and_the_source_is_untouched(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        src = _source(client)
        assert client.post(f"{BASE}/{src['id']}/publish", json={}).status_code == 200
        product = _product(db, "TTDUP")
        combo = _combo(db, product, "Set")
        db.add_all(
            [
                ProductTagTemplate(product_id=product.id, template_id=src["id"]),
                ComboTagTemplate(combo_id=combo.id, template_id=src["id"]),
            ]
        )
        db.commit()
        before = client.get(f"{BASE}/{src['id']}").json()

        dup = _duplicate(client, src["id"]).json()
        after = client.get(f"{BASE}/{src['id']}").json()

    assert db.query(ProductTagTemplate).filter(ProductTagTemplate.template_id == dup["id"]).count() == 0
    assert db.query(ComboTagTemplate).filter(ComboTagTemplate.template_id == dup["id"]).count() == 0
    assert db.query(ProductTagTemplate).filter(ProductTagTemplate.template_id == src["id"]).count() == 1
    assert db.query(ComboTagTemplate).filter(ComboTagTemplate.template_id == src["id"]).count() == 1
    assert after == before


def test_a_taken_copy_name_gets_the_next_number(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        src = _source(client)
        first = _duplicate(client, src["id"]).json()
        second = _duplicate(client, src["id"]).json()
        third = _duplicate(client, src["id"]).json()

    assert first["name"] == f"{src['name']} (copy)"
    assert second["name"] == f"{src['name']} (copy 2)"
    assert third["name"] == f"{src['name']} (copy 3)"


def test_an_archived_template_cannot_be_duplicated(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        src = _source(client)
        assert client.delete(f"{BASE}/{src['id']}").status_code == 204
        res = _duplicate(client, src["id"])

    assert res.status_code == 404, res.text
    assert db.query(TagTemplate).filter(TagTemplate.name.like(f"{src['name']} (copy%")).count() == 0


def test_a_viewer_without_manage_is_refused(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        src = _source(client)
    _as(_VIEWER_ID)
    with TestClient(app) as client:
        res = _duplicate(client, src["id"])

    assert res.status_code == 403, res.text
    assert db.query(TagTemplate).filter(TagTemplate.name.like(f"{src['name']} (copy%")).count() == 0
