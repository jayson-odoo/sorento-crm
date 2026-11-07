"""Spec-value feature icons, review + security fix round (5 Nov).

B1 a value taken away (built-in suppressed, or staff-added dropped) takes its icons with it, and a
draft that still names it does not lock the key's icon saves. S1/S3 the registry is shared by
every company, the icon assets are not: a save carries another company's icons forward in their
places, a read never shows them, and an icon that no longer exists is dropped instead of refused.
S2 saving value_icons needs the Dealer Kit library permission on the server too. Postgres only.
"""
from __future__ import annotations

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests.test_feature_icons_spec_value import (  # noqa: F401  (fixture)
    _icon,
    _patch,
    _spec_key,
    reg,
)
from tests.test_spec_registry_pr2_routes import (
    _BASE,
    _MERCHANDISER,
    _grant,
    _key,
)


def _stored(db, key):
    from app.models.product_spec import ProductSpecRegistry

    db.expire_all()
    return db.query(ProductSpecRegistry).filter_by(spec_key=key).one().value_icons


# ---------------------------------------------------------------------------
# B1
# ---------------------------------------------------------------------------


def test_removing_a_built_in_value_drops_its_icons_and_the_next_save_still_works(reg):
    from app.services.product_spec_registry import remove_value

    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["cold_only", "mixer"], source="seed")
    hot, cold = _icon(db, "ZZT hot"), _icon(db, "ZZT cold")
    db.commit()
    assert _patch(client, key, {"mixer": [hot.id, cold.id], "cold_only": [cold.id]}).status_code == 200

    remove_value(db, key, "cold_only")
    assert "cold_only" not in _stored(db, key)

    # The open draft still names cold_only: a mixer change must save, cold_only stays gone.
    res = _patch(client, key, {"mixer": [cold.id, hot.id], "cold_only": [cold.id]})
    assert res.status_code == 200, res.text
    assert res.json()["value_icons"] == {"mixer": [cold.id, hot.id]}


def test_a_patch_that_suppresses_a_value_drops_its_icons(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["cold_only", "mixer"], source="seed",
         synonyms={"cold_only": ["cold only"], "mixer": ["mixer"]})
    cold = _icon(db, "ZZT cold")
    db.commit()
    assert _patch(client, key, {"cold_only": [cold.id], "mixer": [cold.id]}).status_code == 200

    res = client.patch(f"{_BASE}/{key}", json={"suppressed_values": ["cold_only"]})
    assert res.status_code == 200, res.text
    assert _stored(db, key) == {"mixer": [cold.id]}


def test_a_value_never_stored_is_still_refused(reg):
    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    icon = _icon(db, "ZZT i")
    db.commit()
    res = _patch(client, key, {"lava": [icon.id]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "spec_registry_icon_unknown_value"


def test_a_deleted_icon_is_dropped_on_the_next_save_not_refused(reg):
    from app.models.resources import Attachment

    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    gone, kept = _icon(db, "ZZT gone"), _icon(db, "ZZT kept")
    db.commit()
    assert _patch(client, key, {"a": [gone.id, kept.id]}).status_code == 200
    db.get(Attachment, gone.attachment_id).is_deleted = True
    db.commit()

    res = _patch(client, key, {"a": [gone.id, kept.id]})
    assert res.status_code == 200, res.text
    assert res.json()["value_icons"] == {"a": [kept.id]}


# ---------------------------------------------------------------------------
# S1 / S3: two companies on one shared registry row
# ---------------------------------------------------------------------------


@pytest.fixture
def two_companies(reg):
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from tests._knowledge_seed import seed_company

    db, _as, client = reg
    other = seed_company(db)
    db.commit()

    def as_company(company_id: str) -> None:
        async def _scope():
            scope = frozenset({company_id})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _scope

    return db, _as, client, other, as_company


def test_another_companys_icons_survive_a_save_in_their_places(two_companies):
    db, _as, client, other, as_company = two_companies
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["mixer", "cold_only"])
    a_hot, a_cold = _icon(db, "ZZT A hot"), _icon(db, "ZZT A cold")
    b_icon = _icon(db, "ZZT B icon")
    b_icon.company_id = other
    db.commit()
    # Company A (Sorento) sets its icons.
    assert _patch(client, key, {"mixer": [a_hot.id, a_cold.id], "cold_only": [a_cold.id]}).status_code == 200

    # Company B saves, seeing none of A's icons: A's stay, in their places.
    as_company(other)
    res = _patch(client, key, {"mixer": [b_icon.id]})
    assert res.status_code == 200, res.text
    assert _stored(db, key) == {
        "mixer": [a_hot.id, a_cold.id, b_icon.id],
        "cold_only": [a_cold.id],
    }
    # ...and B's own answer and read show only B's.
    assert res.json()["value_icons"] == {"mixer": [b_icon.id]}
    _as(_MERCHANDISER)
    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[key]["value_icons"] == {"mixer": [b_icon.id]}
    assert set(listed[key]["value_icon_names"]) == {b_icon.id}


def test_a_company_reads_only_its_own_icons(two_companies):
    db, _as, client, other, as_company = two_companies
    key = _spec_key()
    a_icon, b_icon = _icon(db, "ZZT A"), _icon(db, "ZZT B")
    b_icon.company_id = other
    _key(db, key, data_type="enum", allowed_values=["a"], value_icons={"a": [a_icon.id, b_icon.id]})
    db.commit()
    _as(_MERCHANDISER)

    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[key]["value_icons"] == {"a": [a_icon.id]}
    as_company(other)
    listed = {k["spec_key"]: k for k in client.get(_BASE).json()["keys"]}
    assert listed[key]["value_icons"] == {"a": [b_icon.id]}


# ---------------------------------------------------------------------------
# S2: value_icons needs the Dealer Kit library on the server
# ---------------------------------------------------------------------------


def test_value_icons_need_the_dealer_kit_library_permission(reg):
    from app.models.user import UserRole, UserRoleAssignment

    db, _as, client = reg
    key = _spec_key()
    _key(db, key, data_type="enum", allowed_values=["a"])
    icon = _icon(db, "ZZT i")
    # A registry editor WITHOUT dealer_kit.library.manage.
    role = UserRole(id="2c7f5b94-9ea3-5068-d4f2-0b3c8e6a1d99", slug="zzt_reg_only",
                    name="zzt_reg_only", description="", is_protected=False, is_default=False)
    db.add(role)
    db.flush()
    _grant(db, role.id, ["master_data.spec_registry.edit", "master_data.products.edit"])
    db.add(UserRoleAssignment(user_id=_MERCHANDISER, role_id=role.id))
    db.commit()
    _as(_MERCHANDISER)

    res = _patch(client, key, {"a": [icon.id]})
    assert res.status_code == 403, res.text
    # Icon order is registry-only: no Dealer Kit permission needed.
    assert client.patch(f"{_BASE}/{key}", json={"icon_order": 3}).status_code == 200
