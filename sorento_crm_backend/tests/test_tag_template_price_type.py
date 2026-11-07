"""PRICETAG-COMBO-FORMAT S5: a tag template carries a hand-picked price type.

UAC: documentation/plans/dealer-kit/pricetag-combo-format-acceptance-criteria.md, AC-27, AC-29
(the list-filter half).

Written test-FIRST (PRINCIPLES.md Phase 2). `tag_template.price_type` and the schema field do
not exist yet, so the response key is absent (`response_model` drops what it was not told
about) and the filter is ignored.

Harness reused from `tests/test_product_tag_templates.py` (staff manager, Postgres scratch schema).
"""
from __future__ import annotations

import pytest

from tests._pg_fixture import unique_code
from tests.test_product_tag_templates import DK, _template, env  # noqa: F401  (env is a fixture)

URL = f"{DK}/tag-templates"


def _create(c, price_type="__omit__", **extra):
    body = {"name": unique_code("PT"), "family": "ala_carte", **extra}
    if price_type != "__omit__":
        body["price_type"] = price_type
    return c.post(URL, json=body)


# --------------------------------------------------------------------------- AC-27
@pytest.mark.parametrize("value", ["list", "selling", "both", None])
def test_create_persists_the_price_type(env, value):
    _db, c, _ = env
    res = _create(c, value)
    assert res.status_code == 201, res.text
    assert res.json()["price_type"] == value
    assert c.get(f"{URL}/{res.json()['id']}").json()["price_type"] == value


def test_create_without_a_price_type_leaves_it_unset(env):
    _db, c, _ = env
    res = _create(c)
    assert res.status_code == 201, res.text
    assert res.json()["price_type"] is None


@pytest.mark.parametrize("value", ["lp", "LIST", "", "sp", 3])
def test_an_unknown_price_type_is_422_on_create_and_put(env, value):
    db, c, _ = env
    assert _create(c, value).status_code == 422
    template = _template(db, "Bad", published=False)
    res = c.put(f"{URL}/{template}", json={"price_type": value})
    assert res.status_code == 422, res.text


@pytest.mark.parametrize("value", ["list", "selling", "both", None])
def test_put_persists_the_price_type(env, value):
    db, c, _ = env
    template = _template(db, "Put", published=False)
    first = c.put(f"{URL}/{template}", json={"price_type": "both"})
    assert first.status_code == 200, first.text
    assert first.json()["price_type"] == "both"

    res = c.put(f"{URL}/{template}", json={"price_type": value})
    assert res.status_code == 200, res.text
    assert res.json()["price_type"] == value
    assert c.get(f"{URL}/{template}").json()["price_type"] == value


def test_a_put_without_the_field_leaves_it_alone(env):
    db, c, _ = env
    template = _template(db, "Keep", published=False)
    c.put(f"{URL}/{template}", json={"price_type": "selling"})
    res = c.put(f"{URL}/{template}", json={"name": unique_code("Renamed")})
    assert res.status_code == 200, res.text
    assert res.json()["price_type"] == "selling"


def test_publish_does_not_change_the_price_type_and_a_published_get_returns_it(env):
    """AC-27: the price type is a template fact, not a version fact."""
    db, c, _ = env
    template = _template(db, "Pub", published=False)
    assert c.put(f"{URL}/{template}", json={"price_type": "selling"}).status_code == 200

    published = c.post(f"{URL}/{template}/publish", json={})
    assert published.status_code == 200, published.text
    assert published.json()["price_type"] == "selling"
    assert c.get(f"{URL}/{template}").json()["price_type"] == "selling"

    # changing it later does not need (or cause) a republish
    version_before = c.get(f"{URL}/{template}").json()["published_version_no"]
    assert c.put(f"{URL}/{template}", json={"price_type": "list"}).json()["price_type"] == "list"
    after = c.get(f"{URL}/{template}").json()
    assert after["published_version_no"] == version_before

    listed = {row["id"]: row for row in c.get(URL, params={"published": "true"}).json()}
    assert listed[template]["price_type"] == "list"


# --------------------------------------------------------------------------- AC-29
def test_list_filter_by_price_type_including_unset(env):
    db, c, _ = env
    by_type = {}
    for value in ("list", "selling", "both", None):
        template = _template(db, f"F{value}", published=False)
        if value is not None:
            assert c.put(f"{URL}/{template}", json={"price_type": value}).status_code == 200
        by_type[value] = template
    ours = set(by_type.values())

    def ids(filter_value=None):
        params = {} if filter_value is None else {"price_type": filter_value}
        res = c.get(URL, params=params)
        assert res.status_code == 200, res.text
        return {row["id"] for row in res.json()} & ours

    assert ids() == ours, "no filter = every template"
    assert ids("unset") == {by_type[None]}
    assert ids("selling") == {by_type["selling"]}
    assert ids("list") == {by_type["list"]}
    assert ids("both") == {by_type["both"]}
