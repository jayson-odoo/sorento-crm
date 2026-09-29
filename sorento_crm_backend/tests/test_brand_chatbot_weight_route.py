"""Brand CRUD route + `chatbot_weight` (owner console test of round 3 on PR #833, R1).

The owner (27 Sep 2026): "i want weights as brand preference instead of switch". Every
brand carries a chatbot weight; when a customer names no brand, a counted set answers the
highest weighted brand the set reaches and names the other brands in weight order. It
replaces round 2's one-per-company `is_chatbot_default` switch. Edited on Master Data >
Brands (the list shows it, the brand's own edit form and the create/edit dialog set it).

Contract:
* POST without the field creates a brand with `chatbot_weight: 0`.
* PUT `{"chatbot_weight": 0.5}` persists it; GET by id and the list read it back.
* Two brands keep their own weights: setting one never touches another.
* PUT without the field leaves it alone; a negative weight is a 422.
* The retired `is_chatbot_default` is no longer in the response.
"""
from __future__ import annotations

from tests._pg_fixture import unique_code
from tests.test_brand_flows_to_purchasing_route import BRANDS_ENDPOINT, api, db  # noqa: F401 - fixtures


def _create(api, name: str, **extra):
    resp = api.post(BRANDS_ENDPOINT, json={"brand_code": unique_code("BCW"), "brand_name": name, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_post_without_the_field_is_unweighted(api, db):
    body = _create(api, "ZZT Plain Brand")
    assert body["chatbot_weight"] == 0
    assert "is_chatbot_default" not in body


def test_put_a_weight_persists_and_get_reads_it_back(api, db):
    brand_id = _create(api, "ZZT Weighted Brand")["id"]

    put = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"chatbot_weight": 0.5})
    assert put.status_code == 200, put.text
    assert put.json()["chatbot_weight"] == 0.5

    assert api.get(f"{BRANDS_ENDPOINT}/{brand_id}").json()["chatbot_weight"] == 0.5
    listed = api.get(BRANDS_ENDPOINT, params={"query": "ZZT Weighted Brand"}).json()["data"]
    assert [r["chatbot_weight"] for r in listed if r["id"] == brand_id] == [0.5]


def test_two_brands_keep_their_own_weights(api, db):
    first = _create(api, "ZZT First Weight", chatbot_weight=1.5)["id"]
    second = _create(api, "ZZT Second Weight")["id"]

    api.put(f"{BRANDS_ENDPOINT}/{second}", json={"chatbot_weight": 0.1})

    assert api.get(f"{BRANDS_ENDPOINT}/{first}").json()["chatbot_weight"] == 1.5
    assert api.get(f"{BRANDS_ENDPOINT}/{second}").json()["chatbot_weight"] == 0.1


def test_put_without_the_field_leaves_it_alone(api, db):
    brand_id = _create(api, "ZZT Kept Weight", chatbot_weight=1.5)["id"]

    put = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"brand_name": "ZZT Kept Weight Renamed"})
    assert put.status_code == 200
    assert put.json()["chatbot_weight"] == 1.5


def test_a_negative_weight_is_refused(api, db):
    brand_id = _create(api, "ZZT Negative Weight")["id"]
    assert api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"chatbot_weight": -1}).status_code == 422
