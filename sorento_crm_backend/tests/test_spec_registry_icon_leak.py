"""SPEC-REGISTRY-ICON-LEAK: the spec registry is shared by every company, its icons are not.

1. A key's History tab (`/audit/logs/?entity_type=product_spec_registry`) shows only the
   caller's own company's icon ids in `value_icons` (and `value_icon_conditions`, the
   SPEC-ICON-COMBINED column keyed by icon id), never another company's.
2. A `value_icons` save naming another company's icon that is not already stored there is
   refused (422), so an id read elsewhere cannot be hung on a value. Postgres only.
"""
from __future__ import annotations

import uuid

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from tests.test_feature_icons_spec_value import _icon, _patch, _spec_key, reg  # noqa: F401
from tests.test_feature_icons_spec_value_fixround import _stored, two_companies  # noqa: F401
from tests.test_spec_registry_pr2_routes import _key

_HISTORY = "/api/v1/audit/logs/?entity_type=product_spec_registry&entity_id={}"


def _history_row(db, row_id: str, old: dict, new: dict) -> None:
    from app.models.audit import AuditLog

    db.add(AuditLog(
        id=str(uuid.uuid4()), entity_type="product_spec_registry", entity_id=row_id,
        action="UPDATE", old_values=old, new_values=new,
    ))
    db.commit()


def _setup(two_companies):  # noqa: F811
    db, _as, client, other, as_company = two_companies
    a_icon, a_icon2 = _icon(db, "ZZT A"), _icon(db, "ZZT A2")
    b_icon = _icon(db, "ZZT B")
    b_icon.company_id = other
    row = _key(db, _spec_key(), data_type="enum", allowed_values=["a", "b"])
    db.commit()
    return db, client, other, as_company, row, a_icon, a_icon2, b_icon


# ---------------------------------------------------------------------------
# 1. History
# ---------------------------------------------------------------------------


def test_history_hides_another_companys_icon_ids(two_companies):  # noqa: F811
    db, client, other, as_company, row, a_icon, a_icon2, b_icon = _setup(two_companies)
    _history_row(
        db, row.id,
        old={"value_icons": {"a": [a_icon.id, b_icon.id]}, "label": "Old"},
        new={"value_icons": {"a": [a_icon.id, b_icon.id], "b": [b_icon.id, a_icon2.id]},
             "label": "New"},
    )

    res = client.get(_HISTORY.format(row.id))
    assert res.status_code == 200, res.text
    [entry] = res.json()["data"]
    assert b_icon.id not in res.text
    # The caller's own icons, and the rest of the diff, are untouched.
    assert entry["old_values"] == {"value_icons": {"a": [a_icon.id]}, "label": "Old"}
    assert entry["new_values"] == {
        "value_icons": {"a": [a_icon.id], "b": [a_icon2.id]}, "label": "New",
    }

    # The other company sees its own and none of A's.
    as_company(other)
    res = client.get(_HISTORY.format(row.id))
    assert res.status_code == 200, res.text
    [entry] = res.json()["data"]
    assert a_icon.id not in res.text and a_icon2.id not in res.text
    assert entry["new_values"]["value_icons"] == {"a": [b_icon.id], "b": [b_icon.id]}
    assert entry["old_values"]["value_icons"] == {"a": [b_icon.id]}


def test_history_hides_another_companys_ids_in_value_icon_conditions(two_companies):  # noqa: F811
    # SPEC-ICON-COMBINED (#2291) column: value -> {icon id: [conditions]}. The audit row is
    # JSON, so this holds whether or not the column has landed on main yet.
    db, client, _other, _as_company, row, a_icon, _a2, b_icon = _setup(two_companies)
    cond = [{"spec_key": "zz_len", "value": "150"}]
    _history_row(
        db, row.id, old={},
        new={"value_icon_conditions": {"a": {a_icon.id: cond, b_icon.id: cond}}},
    )

    res = client.get(_HISTORY.format(row.id))
    assert res.status_code == 200, res.text
    assert b_icon.id not in res.text
    [entry] = res.json()["data"]
    assert entry["new_values"] == {"value_icon_conditions": {"a": {a_icon.id: cond}}}


def test_history_hides_a_deleted_icon_of_another_company_keeps_my_deleted_one(two_companies):  # noqa: F811
    from app.models.resources import Attachment

    db, client, _other, _as_company, row, a_icon, _a2, b_icon = _setup(two_companies)
    db.get(Attachment, a_icon.attachment_id).is_deleted = True
    db.get(Attachment, b_icon.attachment_id).is_deleted = True
    db.commit()
    _history_row(db, row.id, old={}, new={"value_icons": {"a": [a_icon.id, b_icon.id]}})

    res = client.get(_HISTORY.format(row.id))
    assert res.status_code == 200, res.text
    [entry] = res.json()["data"]
    assert entry["new_values"] == {"value_icons": {"a": [a_icon.id]}}


def test_history_of_other_entities_is_untouched(two_companies):  # noqa: F811
    from app.models.audit import AuditLog

    db, _client, _other, _as_company, _row, _a, _a2, b_icon = _setup(two_companies)
    from app.api.v1.audit.audit_logs import _redact_foreign_icon_ids

    it = AuditLog(entity_type="product", entity_id="x", action="UPDATE",
                  old_values=None, new_values={"value_icons": {"a": [b_icon.id]}})
    _redact_foreign_icon_ids(db, [it])
    assert it.new_values == {"value_icons": {"a": [b_icon.id]}}


# ---------------------------------------------------------------------------
# 2. Save
# ---------------------------------------------------------------------------


def test_a_save_naming_another_companys_icon_is_refused(two_companies):  # noqa: F811
    db, client, _other, _as_company, row, a_icon, _a2, b_icon = _setup(two_companies)

    res = _patch(client, row.spec_key, {"a": [a_icon.id, b_icon.id]})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "spec_registry_icon_not_an_icon"
    assert _stored(db, row.spec_key) == {}


def test_a_foreign_icon_stored_on_one_value_cannot_be_copied_to_another(two_companies):  # noqa: F811
    db, client, other, as_company, row, a_icon, _a2, b_icon = _setup(two_companies)
    as_company(other)
    assert _patch(client, row.spec_key, {"a": [b_icon.id]}).status_code == 200

    # Company A learned b_icon's id (e.g. from History before this fix) and names it on "b".
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from tests.test_feature_icons_spec_value import SORENTO

    async def _a_scope():
        scope = frozenset({SORENTO})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _a_scope
    res = _patch(client, row.spec_key, {"a": [a_icon.id], "b": [b_icon.id]})
    # Dropped, never stored on "b": it stays only where its own company put it.
    assert res.status_code == 200, res.text
    assert res.json()["value_icons"] == {"a": [a_icon.id]}
    assert _stored(db, row.spec_key) == {"a": [b_icon.id, a_icon.id]}


def test_own_icons_still_save_and_another_companys_stored_ones_are_kept(two_companies):  # noqa: F811
    db, client, other, as_company, row, a_icon, a_icon2, b_icon = _setup(two_companies)
    as_company(other)
    assert _patch(client, row.spec_key, {"a": [b_icon.id]}).status_code == 200

    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from tests.test_feature_icons_spec_value import SORENTO

    async def _a_scope():
        scope = frozenset({SORENTO})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _a_scope
    res = _patch(client, row.spec_key, {"a": [a_icon.id], "b": [a_icon2.id, a_icon.id]})
    assert res.status_code == 200, res.text
    assert res.json()["value_icons"] == {"a": [a_icon.id], "b": [a_icon2.id, a_icon.id]}
    assert _stored(db, row.spec_key) == {"a": [b_icon.id, a_icon.id], "b": [a_icon2.id, a_icon.id]}
