"""Brand CRUD route + `is_chatbot_default` (owner brief W5 on PR #833, hand test round 2).

The owner's knob for "recommend Sorento with a heavier preference": one brand per company
is the chatbot's default. When a customer names no brand, a counted set answers the
default brand's products first and names the other brands' counts; naming a brand answers
that brand only. Edited on Master Data > Brands (the brand's own edit form).

Contract:
* POST without the field creates a brand with `is_chatbot_default: false`.
* PUT `{"is_chatbot_default": true}` persists it; GET by id and the list read it back.
* Setting a second brand as the default clears the first (one default per company).
* PUT without the field leaves it alone.
"""
from __future__ import annotations

from tests._pg_fixture import unique_code
from tests.test_brand_flows_to_purchasing_route import BRANDS_ENDPOINT, api, db  # noqa: F401 - fixtures


def _create(api, name: str, **extra):
    resp = api.post(BRANDS_ENDPOINT, json={"brand_code": unique_code("BCD"), "brand_name": name, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_post_without_the_field_is_not_the_default(api, db):
    assert _create(api, "ZZT Plain Brand")["is_chatbot_default"] is False


def test_put_true_persists_and_get_reads_it_back(api, db):
    brand_id = _create(api, "ZZT Default Brand")["id"]

    put = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"is_chatbot_default": True})
    assert put.status_code == 200, put.text
    assert put.json()["is_chatbot_default"] is True

    assert api.get(f"{BRANDS_ENDPOINT}/{brand_id}").json()["is_chatbot_default"] is True
    listed = api.get(BRANDS_ENDPOINT, params={"query": "ZZT Default Brand"}).json()["data"]
    assert [r["is_chatbot_default"] for r in listed if r["id"] == brand_id] == [True]


def test_a_second_default_clears_the_first(api, db):
    first = _create(api, "ZZT First Default", is_chatbot_default=True)["id"]
    second = _create(api, "ZZT Second Brand")["id"]

    api.put(f"{BRANDS_ENDPOINT}/{second}", json={"is_chatbot_default": True})

    assert api.get(f"{BRANDS_ENDPOINT}/{first}").json()["is_chatbot_default"] is False
    assert api.get(f"{BRANDS_ENDPOINT}/{second}").json()["is_chatbot_default"] is True


def test_put_without_the_field_leaves_it_alone(api, db):
    brand_id = _create(api, "ZZT Kept Default", is_chatbot_default=True)["id"]

    put = api.put(f"{BRANDS_ENDPOINT}/{brand_id}", json={"brand_name": "ZZT Kept Default Renamed"})
    assert put.status_code == 200
    assert put.json()["is_chatbot_default"] is True
