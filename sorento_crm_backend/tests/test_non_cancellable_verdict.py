"""NON-CANCELLABLE-ITEMS F1 (owner hand test, 12 Nov): the Non-cancellable badge is live on the open
quote form, like Non-standard and Below minimum price. The line verdict the form already asks
(`_judge_line`, both routes) answers `is_non_cancellable` with the function the save runs.
"""
from __future__ import annotations

from .test_project_series_product_routes import BASE
from .test_series_brand_scope import _series, world  # noqa: F401

VERDICT = f"{BASE}/quotation-line-verdict"


def _mark(w, series_id, category_ids):
    r = w.client.put(
        f"{BASE}/config/series/{series_id}", json={"non_cancellable_category_ids": category_ids}
    )
    assert r.status_code == 200, r.text


def _verdict(w, **params):
    r = w.client.get(VERDICT, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_product_under_a_marked_category_is_non_cancellable_live(world):
    s = _series(world, category_ids=[world.parent.id])
    _mark(world, s["id"], [world.parent.id])
    # a1 sits in the child category: the marked parent covers it, as on save.
    assert _verdict(world, series_id=s["id"], product_id=world.a1.id)["is_non_cancellable"] is True


def test_no_series_or_an_unmarked_series_is_not_non_cancellable(world):
    s = _series(world, category_ids=[world.parent.id])
    assert _verdict(world, series_id=s["id"], product_id=world.a1.id)["is_non_cancellable"] is False
    assert _verdict(world, product_id=world.a1.id)["is_non_cancellable"] is False


def test_a_company_default_counts_with_no_series(world):
    r = world.client.post(
        f"{BASE}/config/non-cancellable-rules",
        json={"product_id": world.a2.id, "non_cancellable": True},
    )
    assert r.status_code in (200, 201), r.text
    assert _verdict(world, product_id=world.a2.id)["is_non_cancellable"] is True


def test_the_saved_quotation_route_answers_it_too(world):
    from .test_project_series_product_routes import _quotation

    s = _series(world, category_ids=[world.parent.id])
    _mark(world, s["id"], [world.parent.id])
    q = _quotation(world.client, world.project.id)
    world.client.put(f"{BASE}/quotations/{q['id']}", json={"series_id": s["id"]})
    body = world.client.get(
        f"{BASE}/quotations/{q['id']}/line-verdict", params={"product_id": world.a1.id}
    ).json()
    assert body["is_non_cancellable"] is True
