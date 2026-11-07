"""PRICETAG-ACCESSORY-DESIGNER S1: saved accessories templates (live-linked box designs).

Plan: PLAN-pricetag-accessory-designer-07nov.md "Accessory templates (presets)". Written test-FIRST:
`/api/v1/dealer-kit/accessory-templates` does not exist yet (404).

Fixture mirrors `tests/test_tag_size_presets.py` (real company scope). Docs are seeded like
`tests/test_dealer_kit_font_manage.py`. The preset ORM class is deliberately not imported: everything
is asserted through the API.
"""
from __future__ import annotations

import copy
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"

_MANAGER_ID = "1a2b3c4d-5e6f-461a-8b2c-3d4e5f6a7b81"
_MANAGER_ROLE = "2b3c4d5e-6f7a-472b-9c3d-4e5f6a7b8c92"
_VIEWER_ID = "3c4d5e6f-7a8b-483c-0d4e-5f6a7b8c9da3"
_VIEWER_ROLE = "4d5e6f7a-8b9c-494d-1e5f-6a7b8c9daeb4"

BASE = "/api/v1/dealer-kit/accessory-templates"

DESIGN = {
    "direction": "vertical",
    "headerText": "FREE",
    "fill": "#f3f7f4",
    "card": {"width_mm": 30, "height_mm": 20, "elements": []},
    "footer": {"show": False, "height_mm": 6, "elements": []},
}


def _seed_roles(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    slugs = ("dealer_kit.tag_templates.view", "dealer_kit.tag_templates.manage")
    perm_ids: dict[str, str] = {}
    for slug in slugs:
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        perm_ids[slug] = perm_id
    db.flush()
    roles = (
        (_MANAGER_ROLE, "zzt_apt_manager", _MANAGER_ID, slugs),
        (_VIEWER_ROLE, "zzt_apt_viewer", _VIEWER_ID, (slugs[0],)),
    )
    for role_id, slug, user_id, granted in roles:
        db.add(UserRole(id=role_id, slug=slug, name=slug, description="", is_protected=False, is_default=False))
        db.add(User(id=user_id, email=f"{slug}@test.com", name=slug, status="ACTIVE"))
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        for granted_slug in granted:
            db.add(
                UserRolePermission(
                    id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_ids[granted_slug]
                )
            )
    db.commit()


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        _as(_MANAGER_ID)
        yield db, _as, _in_company
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- doc helpers


def _box(preset_id=None, *, slot="main", part=None, **props) -> dict:
    out = {
        "kind": "accessories",
        "direction": "horizontal",
        "oldOnly": "gone-after-propagation",
        "subjectSlot": slot,
        **props,
    }
    if part is not None:
        out["subjectPart"] = part
    if preset_id:
        out["presetId"] = preset_id
    return {"id": f"box-{uuid.uuid4().hex[:6]}", "type": "accessories", "x_mm": 3, "props": out}


def _text_layer() -> dict:
    return {"id": "t1", "type": "text", "props": {"kind": "text", "text": "Hi"}}


def _template_doc(*layers) -> dict:
    return {"width_mm": 70, "height_mm": 38, "layers": list(layers)}


def _sheet_doc(*layers) -> dict:
    return {"sheets": [{"id": "s1", "tags": [{"id": "tag-1", "layers": list(layers)}]}]}


def _make_template(db, name, doc, *, company=None):
    from app.models.base import company_scope
    from app.models.dealer_kit import TagTemplate

    def build():
        row = TagTemplate(
            name=name, family=unique_code("family").lower(), doc=doc,
            print_size={"width_mm": 70, "height_mm": 38},
        )
        db.add(row)
        db.flush()
        return row

    if company:
        with company_scope(db, frozenset({company})):
            row = build()
    else:
        row = build()
    db.commit()
    db.refresh(row)
    return row


def _make_version(db, template, doc):
    from app.models.dealer_kit import TagTemplateVersion

    row = TagTemplateVersion(template_id=template.id, version_no=1, doc=doc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_page(db, doc, *, draft: bool):
    from app.models.dealer_kit import Page, PageVersion

    page = Page(name=unique_code("ZZT sheet"), slug=unique_code("tag-sheet").lower(), kind="tag_sheet")
    if draft:
        page.draft_doc = doc
    db.add(page)
    db.flush()
    version = None
    if not draft:
        version = PageVersion(page_id=page.id, version=1, doc=doc)
        db.add(version)
    db.commit()
    db.refresh(page)
    if version is not None:
        db.refresh(version)
    return page, version


def _second_company(db) -> str:
    from app.models.company import Company

    company = Company(id=str(uuid.uuid4()), name=unique_code("ZZT Company B"), code=f"ZB{uuid.uuid4().hex[:6]}")
    db.add(company)
    db.commit()
    return company.id


def _create(client, name=None, design=None):
    response = client.post(BASE, json={"name": name or unique_code("FREE"), "design": design or DESIGN})
    assert response.status_code == 201, response.text
    return response.json()


def _fresh(db, row):
    db.expire_all()
    db.refresh(row)
    return row


# --------------------------------------------------------------------------- CRUD


def test_manager_creates_lists_reads_updates_and_deletes(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        name = unique_code("Free vertical")
        created = client.post(BASE, json={"name": name, "design": DESIGN})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["name"] == name and body["design"] == DESIGN
        assert body["used_in"] == 0
        assert body["created_by_name"] == "zzt_apt_manager"
        assert body["updated_at"] and body["created_at"]
        preset_id = body["id"]

        listed = client.get(BASE)
        assert listed.status_code == 200, listed.text
        assert any(row["id"] == preset_id for row in listed.json())

        one = client.get(f"{BASE}/{preset_id}")
        assert one.status_code == 200 and one.json()["id"] == preset_id

        renamed = client.put(f"{BASE}/{preset_id}", json={"name": f"{name} 2"})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == f"{name} 2" and renamed.json()["design"] == DESIGN

        deleted = client.delete(f"{BASE}/{preset_id}")
        assert deleted.status_code == 204, deleted.text
        assert client.get(f"{BASE}/{preset_id}").status_code == 404


def test_the_list_is_ordered_by_name(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        stem = unique_code("ord")
        for suffix in ("b", "c", "a"):
            _create(client, f"{stem}-{suffix}")
        names = [row["name"] for row in client.get(BASE).json() if row["name"].startswith(stem)]
    assert names == [f"{stem}-a", f"{stem}-b", f"{stem}-c"]


def test_a_duplicate_name_ignoring_case_is_409(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        name = unique_code("Dup")
        _create(client, name)
        again = client.post(BASE, json={"name": name.upper(), "design": DESIGN})
        assert again.status_code == 409, again.text
        assert again.json()["code"] == "DUPLICATE_NAME"

        mine = _create(client, unique_code("Mine"))
        renamed = client.put(f"{BASE}/{mine['id']}", json={"name": name.lower()})
        assert renamed.status_code == 409, renamed.text
        assert renamed.json()["code"] == "DUPLICATE_NAME"


def test_renaming_to_its_own_name_with_other_case_is_allowed(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        mine = _create(client, unique_code("Casey"))
        response = client.put(f"{BASE}/{mine['id']}", json={"name": mine["name"].upper()})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("name", ["", "   "])
def test_a_blank_name_is_422(api, name):
    with TestClient(app) as client:
        assert client.post(BASE, json={"name": name, "design": DESIGN}).status_code == 422
        mine = _create(client)
        assert client.put(f"{BASE}/{mine['id']}", json={"name": name}).status_code == 422


def test_a_design_must_be_an_object_and_name_is_required(api):
    with TestClient(app) as client:
        assert client.post(BASE, json={"name": unique_code("x"), "design": [1, 2]}).status_code == 422
        assert client.post(BASE, json={"name": unique_code("x"), "design": "str"}).status_code == 422
        assert client.post(BASE, json={"name": unique_code("x")}).status_code == 422


def test_a_design_over_64kb_is_422(api):
    with TestClient(app) as client:
        big = {**DESIGN, "blob": "x" * (64 * 1024 + 10)}
        response = client.post(BASE, json={"name": unique_code("Big"), "design": big})
        assert response.status_code == 422, response.text
        mine = _create(client)
        assert client.put(f"{BASE}/{mine['id']}", json={"design": big}).status_code == 422
        small = {**DESIGN, "blob": "x" * 1000}
        assert client.post(BASE, json={"name": unique_code("Ok"), "design": small}).status_code == 201


def test_per_box_keys_are_stripped_before_storing(api):
    with TestClient(app) as client:
        dirty = {
            **DESIGN,
            "kind": "accessories",
            "subjectSlot": "main",
            "subjectPart": 2,
            "presetId": "someone-else",
        }
        created = client.post(BASE, json={"name": unique_code("Strip"), "design": dirty})
        assert created.status_code == 201, created.text
        assert created.json()["design"] == DESIGN
        assert client.get(f"{BASE}/{created.json()['id']}").json()["design"] == DESIGN

        put = client.put(f"{BASE}/{created.json()['id']}", json={"design": dirty})
        assert put.status_code == 200 and put.json()["design"] == DESIGN


# --------------------------------------------------------------------------- permissions


def test_unauthenticated_is_401(api):
    from fastapi import HTTPException

    from app.dependencies import get_current_user, get_current_user_or_api_key

    db, _as, _scope = api

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _deny
    app.dependency_overrides[get_current_user_or_api_key] = _deny
    try:
        with TestClient(app) as client:
            response = client.get(BASE)
    finally:
        _as(_MANAGER_ID)
    assert response.status_code == 401, response.text


def test_view_only_lists_and_reads_but_cannot_write(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        mine = _create(client)
        _as(_VIEWER_ID)
        assert client.get(BASE).status_code == 200
        assert client.get(f"{BASE}/{mine['id']}").status_code == 200
        assert client.get(f"{BASE}/{mine['id']}/usage").status_code == 200
        refused = client.post(BASE, json={"name": unique_code("Refused"), "design": DESIGN})
        assert refused.status_code == 403, refused.text
        assert client.put(f"{BASE}/{mine['id']}", json={"name": "x"}).status_code == 403
        assert client.delete(f"{BASE}/{mine['id']}").status_code == 403
        _as(_MANAGER_ID)
        assert client.get(f"{BASE}/{mine['id']}").status_code == 200


def test_the_deferred_delete_action_is_registered():
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.services.form_action_registry import get_action

    action = get_action("accessory_box_preset.delete")
    assert action is not None
    assert action.entity_types == ("accessory_box_preset",)
    assert action.permission == "dealer_kit.tag_templates.manage"


# --------------------------------------------------------------------------- company scope


def test_a_foreign_companys_template_is_invisible_and_untouchable(api):
    db, _as, in_company = api
    with TestClient(app) as client:
        mine = _create(client)
    other = _second_company(db)
    in_company(other)
    with TestClient(app) as client:
        assert all(row["id"] != mine["id"] for row in client.get(BASE).json())
        assert client.get(f"{BASE}/{mine['id']}").status_code == 404
        assert client.get(f"{BASE}/{mine['id']}/usage").status_code == 404
        assert client.put(f"{BASE}/{mine['id']}", json={"name": "Stolen"}).status_code == 404
        assert client.delete(f"{BASE}/{mine['id']}").status_code == 404
        same_name = client.post(BASE, json={"name": mine["name"], "design": DESIGN})
        assert same_name.status_code == 201, "names are unique per company"
    in_company(_SORENTO)
    with TestClient(app) as client:
        assert client.get(f"{BASE}/{mine['id']}").status_code == 200


# --------------------------------------------------------------------------- usage


def test_used_in_counts_tag_templates_with_a_linked_box_and_usage_names_them(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        preset = _create(client)
        pid = preset["id"]
        a = _make_template(db, unique_code("ZZT tpl A"), _template_doc(_box(pid), _box(pid, slot="fixed")))
        b = _make_template(db, unique_code("ZZT tpl B"), _template_doc(_box(pid)))
        _make_template(db, unique_code("ZZT tpl C"), _template_doc(_box(None), _text_layer()))
        _make_template(db, unique_code("ZZT tpl D"), _template_doc(_box(str(uuid.uuid4()))))

        row = next(r for r in client.get(BASE).json() if r["id"] == pid)
        assert row["used_in"] == 2, "templates, not boxes"
        assert client.get(f"{BASE}/{pid}").json()["used_in"] == 2

        usage = client.get(f"{BASE}/{pid}/usage")
        assert usage.status_code == 200, usage.text
        got = usage.json()["templates"]
        assert sorted(t["id"] for t in got) == sorted([a.id, b.id])
        assert {t["name"] for t in got} == {a.name, b.name}


def test_usage_of_an_unused_template_is_empty(api):
    with TestClient(app) as client:
        preset = _create(client)
        assert client.get(f"{BASE}/{preset['id']}/usage").json() == {"templates": []}


# --------------------------------------------------------------------------- propagation


NEW_DESIGN = {
    "direction": "vertical",
    "headerText": "FREE",
    "card": {"width_mm": 31, "height_mm": 21, "elements": [{"id": "e1", "kind": "picture"}]},
}


def test_put_design_rewrites_every_linked_box_in_all_four_doc_kinds(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        preset = _create(client)
        pid = preset["id"]

        template = _make_template(db, unique_code("ZZT tpl"), _template_doc(_box(pid, slot="fixed", part=2), _text_layer()))
        version = _make_version(db, template, _template_doc(_box(pid, slot="main")))
        draft_page, _ = _make_page(db, _sheet_doc(_box(pid, slot="upgrades"), _text_layer()), draft=True)
        _, page_version = _make_page(db, _sheet_doc(_box(pid, part=-1)), draft=False)

        response = client.put(f"{BASE}/{pid}", json={"design": NEW_DESIGN})
        assert response.status_code == 200, response.text
        assert response.json()["rewritten"] == 4
        assert response.json()["design"] == NEW_DESIGN

    def props_of(layers, index=0):
        return layers[index]["props"]

    _fresh(db, template), _fresh(db, version), _fresh(db, draft_page), _fresh(db, page_version)

    tpl = props_of(template.doc["layers"])
    assert tpl == {**NEW_DESIGN, "kind": "accessories", "presetId": pid, "subjectSlot": "fixed", "subjectPart": 2}
    assert "oldOnly" not in tpl
    assert template.doc["layers"][0]["x_mm"] == 3, "the layer itself (position) is untouched"
    assert template.doc["layers"][1]["props"]["text"] == "Hi", "other layers untouched"

    ver = props_of(version.doc["layers"])
    assert ver["presetId"] == pid and ver["subjectSlot"] == "main" and ver["card"]["width_mm"] == 31

    draft = props_of(draft_page.draft_doc["sheets"][0]["tags"][0]["layers"])
    assert draft["presetId"] == pid and draft["subjectSlot"] == "upgrades" and draft["headerText"] == "FREE"
    assert "oldOnly" not in draft

    pv = props_of(page_version.doc["sheets"][0]["tags"][0]["layers"])
    assert pv["presetId"] == pid and pv["subjectPart"] == -1 and pv["direction"] == "vertical"


def test_put_leaves_unlinked_and_differently_linked_boxes_alone(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        preset = _create(client)
        other_preset = _create(client)
        unlinked = _box(None)
        elsewhere = _box(other_preset["id"])
        snapshot = copy.deepcopy([unlinked, elsewhere])
        template = _make_template(db, unique_code("ZZT tpl"), _template_doc(unlinked, elsewhere, _box(preset["id"])))

        response = client.put(f"{BASE}/{preset['id']}", json={"design": NEW_DESIGN})
        assert response.status_code == 200, response.text
        assert response.json()["rewritten"] == 1

    _fresh(db, template)
    assert template.doc["layers"][0] == snapshot[0]
    assert template.doc["layers"][1] == snapshot[1]
    assert template.doc["layers"][2]["props"]["card"]["width_mm"] == 31


def test_put_only_a_name_rewrites_nothing(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        preset = _create(client)
        box = _box(preset["id"])
        before = copy.deepcopy(box)
        template = _make_template(db, unique_code("ZZT tpl"), _template_doc(box))
        response = client.put(f"{BASE}/{preset['id']}", json={"name": unique_code("Renamed")})
        assert response.status_code == 200, response.text
        assert response.json().get("rewritten", 0) == 0
    _fresh(db, template)
    assert template.doc["layers"][0] == before


def test_put_never_touches_another_companys_docs_naming_the_same_preset_id(api):
    db, _as, in_company = api
    with TestClient(app) as client:
        preset = _create(client)
        pid = preset["id"]
        mine = _make_template(db, unique_code("ZZT mine"), _template_doc(_box(pid)))
        other_company = _second_company(db)
        foreign_box = _box(pid)
        before = copy.deepcopy(foreign_box)
        theirs = _make_template(db, unique_code("ZZT theirs"), _template_doc(foreign_box), company=other_company)

        response = client.put(f"{BASE}/{pid}", json={"design": NEW_DESIGN})
        assert response.status_code == 200, response.text
        assert response.json()["rewritten"] == 1
        assert [t["id"] for t in client.get(f"{BASE}/{pid}/usage").json()["templates"]] == [mine.id]

    _fresh(db, mine), _fresh(db, theirs)
    assert mine.doc["layers"][0]["props"]["card"]["width_mm"] == 31
    assert theirs.doc["layers"][0] == before

    # And deleting my preset must not strip the link from their doc either.
    with TestClient(app) as client:
        assert client.delete(f"{BASE}/{pid}").status_code == 204
    _fresh(db, theirs)
    assert theirs.doc["layers"][0] == before


# --------------------------------------------------------------------------- delete detaches


def test_delete_removes_presetid_from_linked_boxes_and_keeps_their_design(api):
    db, _as, _scope = api
    with TestClient(app) as client:
        preset = _create(client)
        pid = preset["id"]
        template = _make_template(db, unique_code("ZZT tpl"), _template_doc(_box(pid, headerText="KEEP")))
        version = _make_version(db, template, _template_doc(_box(pid)))
        draft_page, _ = _make_page(db, _sheet_doc(_box(pid)), draft=True)
        _, page_version = _make_page(db, _sheet_doc(_box(pid)), draft=False)

        assert client.delete(f"{BASE}/{pid}").status_code == 204
        assert client.get(f"{BASE}/{pid}").status_code == 404

    _fresh(db, template), _fresh(db, version), _fresh(db, draft_page), _fresh(db, page_version)
    kept = template.doc["layers"][0]["props"]
    assert "presetId" not in kept
    assert kept["headerText"] == "KEEP" and kept["kind"] == "accessories" and kept["subjectSlot"] == "main"
    assert kept["oldOnly"] == "gone-after-propagation", "the box keeps its CURRENT design"
    assert "presetId" not in version.doc["layers"][0]["props"]
    assert "presetId" not in draft_page.draft_doc["sheets"][0]["tags"][0]["layers"][0]["props"]
    assert "presetId" not in page_version.doc["sheets"][0]["tags"][0]["layers"][0]["props"]


def test_the_deferred_action_runs_the_same_detach(api):
    import app.services.record_actions  # noqa: F401
    from app.services.form_action_registry import get_action

    db, _as, _scope = api
    with TestClient(app) as client:
        preset = _create(client)
    template = _make_template(db, unique_code("ZZT tpl"), _template_doc(_box(preset["id"])))
    action = get_action("accessory_box_preset.delete")
    action.execute(db, {"entity_id": preset["id"]})
    db.commit()
    _fresh(db, template)
    assert "presetId" not in template.doc["layers"][0]["props"]
    with TestClient(app) as client:
        assert client.get(f"{BASE}/{preset['id']}").status_code == 404
