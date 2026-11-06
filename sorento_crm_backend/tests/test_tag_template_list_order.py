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
    from datetime import datetime, timedelta

    db, _as, _scope = api
    stem = unique_code("Srt")
    with TestClient(app) as client:
        big = _make(client, f"{stem} b", family="toilet", price_type="selling", w=100, h=70)
        small = _make(client, f"{stem} a", family="basin", price_type="list", w=50, h=30)
        mid = _make(client, f"{stem} c", family="kitchen", price_type=None, w=70, h=40)
        # One test transaction gives every row the same now(); spread them out by hand.
        base = datetime(2026, 1, 1)
        for offset, template_id in enumerate([big, small, mid]):
            db.query(TagTemplate).filter(TagTemplate.id == template_id).update(
                {"created_at": base + timedelta(days=offset)}, synchronize_session=False
            )
        db.commit()
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


def test_the_manual_order_is_numbered_per_company(api):
    """A duplicate's shift and a new template's number stay inside the caller's company: the
    other company's rows never move, and its numbers never push this company's next one."""
    import uuid

    from app.models.company import Company

    from app.models.base import get_company_scope, set_company_scope

    db, _as, scope = api

    def order_and_company(template_id: str) -> tuple[int, str]:
        # Read with the system scope (every company), then put the caller's scope back.
        saved = get_company_scope(db)
        set_company_scope(db, None)
        try:
            row = db.query(TagTemplate).filter(TagTemplate.id == template_id).one()
            return row.sort_order, str(row.company_id)
        finally:
            set_company_scope(db, saved)

    stem = unique_code("Co")
    with TestClient(app) as client:
        mine_a = _make(client, f"{stem} mine A")
        mine_b = _make(client, f"{stem} mine B")

    other = str(uuid.uuid4())
    db.add(Company(id=other, name="ZZT other co", code=unique_code("ZZTC")))
    db.commit()
    scope(other)
    with TestClient(app) as client:
        theirs_1 = _make(client, f"{stem} theirs 1")
        theirs_2 = _make(client, f"{stem} theirs 2")
        # Numbered from 1 in their own company, whatever this company's numbers are.
        assert order_and_company(theirs_1) == (1, other)
        assert client.post(f"{BASE}/{theirs_1}/duplicate").status_code == 201

    db.expire_all()
    mine_orders = (order_and_company(mine_a)[0], order_and_company(mine_b)[0])
    assert order_and_company(theirs_2)[0] == 3  # shifted below their duplicate

    scope("00000000-0000-0000-0000-000000000001")
    with TestClient(app) as client:
        mine_c = _make(client, f"{stem} mine C")
    db.expire_all()
    # This company's rows did not move, and its next number follows its OWN maximum.
    assert (order_and_company(mine_a)[0], order_and_company(mine_b)[0]) == mine_orders
    assert order_and_company(mine_c)[0] == mine_orders[1] + 1


def test_a_duplicate_outside_a_request_shifts_only_its_own_company(api):
    """The service filters by company itself, not only through the request's scope listener: a
    caller with the system scope (a script, the worker) must not shift another company's rows."""
    import uuid

    from app.models.base import get_company_scope, set_company_scope
    from app.models.company import Company
    from app.services.dealer_kit import tag_template_service

    db, _as, scope = api
    stem = unique_code("Sys")
    with TestClient(app) as client:
        mine = [_make(client, f"{stem} mine {n}") for n in range(3)]

    other = str(uuid.uuid4())
    db.add(Company(id=other, name="ZZT other co", code=unique_code("ZZTC")))
    db.commit()
    scope(other)
    with TestClient(app) as client:
        theirs = _make(client, f"{stem} theirs")

    saved = get_company_scope(db)
    set_company_scope(db, None)  # the system principal: sees every company
    try:
        before = {i: db.get(TagTemplate, i).sort_order for i in mine}
        source = db.get(TagTemplate, theirs)
        clone = tag_template_service.duplicate(db, source)
        db.expire_all()
        assert {i: db.get(TagTemplate, i).sort_order for i in mine} == before
        assert db.get(TagTemplate, clone.id).sort_order == source.sort_order + 1
        assert str(db.get(TagTemplate, clone.id).company_id) == other
        assert tag_template_service.next_sort_order(db, other) == source.sort_order + 2
    finally:
        set_company_scope(db, saved)
