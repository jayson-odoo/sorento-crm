"""PRICETAG-ACCESSORY-DESIGNER fix round (security review): colour validation, explicit company filter on
the propagation walk, uuid path checks, creator/updater names, one-pass used_in."""
from __future__ import annotations

import copy
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import unique_code
from tests.test_accessory_templates_api import (  # noqa: F401
    BASE,
    DESIGN,
    _MANAGER_ID,
    _SORENTO,
    _box,
    _create,
    _fresh,
    _make_template,
    _second_company,
    _template_doc,
    api,
)


def _post(client, design):
    return client.post(BASE, json={"name": unique_code("Col"), "design": design})


@pytest.mark.parametrize(
    "design",
    [
        {**DESIGN, "fill": "url(https://evil.test/x)"},
        {**DESIGN, "cardFill": "red; background: url(x)"},
        {**DESIGN, "headerStyle": {"color": "url(x)"}},
        {**DESIGN, "card": {"width_mm": 30, "height_mm": 20, "elements": [{"id": "e", "kind": "shape", "fill": "url(x)"}]}},
        {**DESIGN, "footer": {"show": True, "height_mm": 6, "elements": [{"id": "e", "kind": "colour_dots", "colours": ["#fff", "expression(1)"]}]}},
        {**DESIGN, "card": {"width_mm": 30, "height_mm": 20, "elements": [{"id": "e", "kind": "text", "dotOutline": "javascript:1"}]}},
    ],
)
def test_a_non_colour_in_a_colour_slot_is_422_with_its_path(api, design):
    with TestClient(app) as client:
        res = _post(client, design)
        assert res.status_code == 422, res.text
        mine = _create(client)
        assert client.put(f"{BASE}/{mine['id']}", json={"design": design}).status_code == 422


def test_real_colours_are_accepted(api):
    design = {
        **DESIGN,
        "fill": "#f3f7f4",
        "stroke": "#abc",
        "cardFill": "transparent",
        "headerBackground": "",
        "headerStyle": {"color": "#112233"},
        "card": {"width_mm": 30, "height_mm": 20, "elements": [
            {"id": "e", "kind": "colour_dots", "colours": ["#1f2937", "#9ca3af"], "dotOutline": "#000"}
        ]},
    }
    with TestClient(app) as client:
        assert _post(client, design).status_code == 201


def test_a_superadmin_scope_never_rewrites_another_companys_doc(api):
    from app.dependencies import get_current_user  # noqa: F401
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    db, _as, _scope = api
    with TestClient(app) as client:
        preset = _create(client)
        pid = preset["id"]
        other = _second_company(db)
        foreign = _box(pid)
        before = copy.deepcopy(foreign)
        theirs = _make_template(db, unique_code("ZZT theirs"), _template_doc(foreign), company=other)
        mine = _make_template(db, unique_code("ZZT mine"), _template_doc(_box(pid)))

        async def _all_companies():
            set_company_scope(db, None)
            return None

        app.dependency_overrides[apply_company_scope] = _all_companies
        res = client.put(f"{BASE}/{pid}", json={"design": {**DESIGN, "headerText": "NEW"}})
        assert res.status_code == 200, res.text
        assert res.json()["rewritten"] == 1
        assert client.delete(f"{BASE}/{pid}").status_code == 204
    _fresh(db, theirs), _fresh(db, mine)
    assert theirs.doc["layers"][0] == before
    assert "presetId" not in mine.doc["layers"][0]["props"]


def test_a_malformed_id_is_404_on_every_preset_route(api):
    with TestClient(app) as client:
        for method, path in (
            ("get", "/not-a-uuid"),
            ("get", "/not-a-uuid/usage"),
            ("put", "/not-a-uuid"),
            ("delete", "/not-a-uuid"),
        ):
            kwargs = {"json": {"name": "x"}} if method == "put" else {}
            res = getattr(client, method)(BASE + path, **kwargs)
            assert res.status_code == 404, (method, path, res.status_code)


def test_the_list_names_who_last_changed_it(api):
    with TestClient(app) as client:
        created = _create(client)
        assert created["updated_by_name"] == "zzt_apt_manager"
        row = next(r for r in client.get(BASE).json() if r["id"] == created["id"])
        assert row["updated_by_name"] == "zzt_apt_manager"


def test_used_in_is_counted_in_one_pass_for_the_list(api, monkeypatch):
    from app.services.dealer_kit import accessory_template_service as service

    db, _as, _scope = api
    with TestClient(app) as client:
        a, b = _create(client), _create(client)
        _make_template(db, unique_code("ZZT t"), _template_doc(_box(a["id"]), _box(b["id"])))
        _make_template(db, unique_code("ZZT t"), _template_doc(_box(a["id"])))
        calls = []
        real = service.usage
        monkeypatch.setattr(service, "usage", lambda *args, **kw: calls.append(1) or real(*args, **kw))
        rows = {r["id"]: r for r in client.get(BASE).json()}
        assert rows[a["id"]]["used_in"] == 2 and rows[b["id"]]["used_in"] == 1
        assert calls == [], "the list must not call usage() once per preset"
