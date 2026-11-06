"""TAG-TEMPLATE-DUPLICATE items 5 + 6: the Tag Templates list's server-side filters and sort,
and its shared manual (drag) order.

PLAN: documentation/plans/dealer-kit/PLAN-tag-template-duplicate-06nov.md

- Filters are multi-select (comma-joined): price_type (with `unset`), family, status (live/draft),
  plus a name search (`query`).
- Every column sorts on the server: name, family, price_type, print_size, created_at, published.
- No sort = the manual order (`sort_order`), where a new template goes to the END and a duplicate
  right BELOW its source. `POST /reorder` swaps the dragged rows among their own slots; only a
  user who can edit templates may call it.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app  # noqa: E402  (first app import)
from app.models.dealer_kit import TagTemplate
from tests._pg_fixture import unique_code
from tests.test_tag_template_bulk_delete import _VIEWER_ID, api  # noqa: F401

BASE = "/api/v1/dealer-kit/tag-templates"


def _make(client, name, *, family="toilet", price_type=None, w=85, h=58) -> str:
    res = client.post(
        BASE,
        json={
            "name": name,
            "family": family,
            "doc": {"layers": [], "width_mm": w, "height_mm": h},
            "print_size": {"width_mm": w, "height_mm": h},
            "price_type": price_type,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _names(client, stem: str, params: str = "") -> list[str]:
    sep = "&" if params else ""
    res = client.get(f"{BASE}?query={stem}{sep}{params}")
    assert res.status_code == 200, res.text
    return [row["name"] for row in res.json()]


def test_default_order_is_creation_order_and_a_new_template_goes_last(api):
    stem = unique_code("Ord")
    with TestClient(app) as client:
        for n in ("C", "A", "B"):
            _make(client, f"{stem} {n}")
        assert _names(client, stem) == [f"{stem} C", f"{stem} A", f"{stem} B"]


def test_a_duplicate_lands_right_below_its_source(api):
    stem = unique_code("Ord")
    with TestClient(app) as client:
        a = _make(client, f"{stem} A")
        _make(client, f"{stem} B")
        res = client.post(f"{BASE}/{a}/duplicate")
        assert res.status_code == 201, res.text
        assert _names(client, stem) == [f"{stem} A", f"{stem} A (copy)", f"{stem} B"]


def test_reorder_saves_the_dragged_order_for_everyone(api):
    db, _as, _scope = api
    stem = unique_code("Ord")
    with TestClient(app) as client:
        a = _make(client, f"{stem} A")
        b = _make(client, f"{stem} B")
        c = _make(client, f"{stem} C")
        res = client.post(f"{BASE}/reorder", json={"template_ids": [c, a, b]})
        assert res.status_code == 200, res.text
        assert _names(client, stem) == [f"{stem} C", f"{stem} A", f"{stem} B"]

    _as(_VIEWER_ID)
    with TestClient(app) as client:
        assert _names(client, stem) == [f"{stem} C", f"{stem} A", f"{stem} B"]


def test_reorder_of_a_subset_keeps_every_other_row_in_place(api):
    stem = unique_code("Ord")
    with TestClient(app) as client:
        a = _make(client, f"{stem} A")
        _make(client, f"{stem} B")
        c = _make(client, f"{stem} C")
        # A filtered view showed only A and C; dragging C above A swaps those two slots only.
        assert client.post(f"{BASE}/reorder", json={"template_ids": [c, a]}).status_code == 200
        assert _names(client, stem) == [f"{stem} C", f"{stem} B", f"{stem} A"]


def test_reorder_is_refused_for_a_viewer_and_for_a_missing_id(api):
    db, _as, _scope = api
    stem = unique_code("Ord")
    with TestClient(app) as client:
        a = _make(client, f"{stem} A")
        b = _make(client, f"{stem} B")
        missing = client.post(
            f"{BASE}/reorder", json={"template_ids": [b, "00000000-0000-0000-0000-00000000dead"]}
        )
        assert missing.status_code == 404, missing.text
    _as(_VIEWER_ID)
    with TestClient(app) as client:
        refused = client.post(f"{BASE}/reorder", json={"template_ids": [b, a]})
        assert refused.status_code == 403, refused.text
        assert _names(client, stem) == [f"{stem} A", f"{stem} B"]


def test_every_column_sorts_on_the_server(api):
    stem = unique_code("Srt")
    with TestClient(app) as client:
        big = _make(client, f"{stem} b", family="toilet", price_type="selling", w=100, h=70)
        _make(client, f"{stem} a", family="basin", price_type="list", w=50, h=30)
        _make(client, f"{stem} c", family="kitchen", price_type=None, w=70, h=40)
        assert client.post(f"{BASE}/{big}/publish", json={}).status_code == 200

        assert _names(client, stem, "sort=name&dir=asc") == [f"{stem} a", f"{stem} b", f"{stem} c"]
        assert _names(client, stem, "sort=name&dir=desc") == [f"{stem} c", f"{stem} b", f"{stem} a"]
        assert _names(client, stem, "sort=family") == [f"{stem} a", f"{stem} c", f"{stem} b"]
        # Unset price type sorts last either way.
        assert _names(client, stem, "sort=price_type") == [f"{stem} a", f"{stem} b", f"{stem} c"]
        assert _names(client, stem, "sort=print_size&dir=desc") == [f"{stem} b", f"{stem} c", f"{stem} a"]
        assert _names(client, stem, "sort=created_at&dir=desc") == [f"{stem} c", f"{stem} a", f"{stem} b"]
        assert _names(client, stem, "sort=published&dir=desc")[0] == f"{stem} b"


def test_filters_are_multi_select(api):
    stem = unique_code("Flt")
    with TestClient(app) as client:
        live = _make(client, f"{stem} 1", family="toilet", price_type="list")
        _make(client, f"{stem} 2", family="basin", price_type="selling")
        _make(client, f"{stem} 3", family="kitchen", price_type=None)
        assert client.post(f"{BASE}/{live}/publish", json={}).status_code == 200

        assert _names(client, stem, "price_type=list,unset") == [f"{stem} 1", f"{stem} 3"]
        assert _names(client, stem, "family=basin,kitchen") == [f"{stem} 2", f"{stem} 3"]
        assert _names(client, stem, "status=live") == [f"{stem} 1"]
        assert _names(client, stem, "status=draft") == [f"{stem} 2", f"{stem} 3"]
        assert _names(client, stem, "status=live,draft") == [f"{stem} 1", f"{stem} 2", f"{stem} 3"]
        assert _names(client, stem, "price_type=selling&family=toilet") == []
