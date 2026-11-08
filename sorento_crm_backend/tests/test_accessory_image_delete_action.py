"""Picture removal is a server-deferred action `accessory_image.delete` (no confirm dialog).

Parking refuses another company's picture id; the commit removes the picture and its attachment.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services import record_actions  # noqa: F401  (registers the record actions)
from tests._pg_fixture import unique_code
from tests.test_pending_action_company_scope import (  # noqa: F401
    _ACTOR_ID,
    _SORENTO,
    _lapse,
    _park,
    _sweep,
    api,
)


def _picture(db, company):
    from app.models.accessory import Accessory, AccessoryImage
    from app.models.resources import Attachment

    accessory = Accessory(id=str(uuid.uuid4()), company_id=company, name=unique_code("ZZT ACC").upper())
    db.add(accessory)
    db.flush()
    stem = unique_code("zztimg")
    attachment = Attachment(
        id=str(uuid.uuid4()), original_filename=f"{stem}.jpg", stored_filename=f"{stem}.jpg",
        file_path=f"https://cdn.test/accessory_image/{stem}.jpg", mime_type="image/jpeg",
        storage_provider="s3", company_id=company, is_deleted=False,
    )
    db.add(attachment)
    db.flush()
    image = AccessoryImage(accessory_id=accessory.id, attachment_id=attachment.id, sort_order=0)
    db.add(image)
    db.commit()
    return image


def _grant_products_edit(db):
    from app.models.user import UserPermission, UserRolePermission, UserRoleAssignment

    role_id = db.query(UserRoleAssignment.role_id).filter(UserRoleAssignment.user_id == _ACTOR_ID).scalar()
    permission = db.query(UserPermission).filter(UserPermission.slug == "master_data.products.edit").first()
    if permission is None:
        permission = UserPermission(
            id=str(uuid.uuid4()), slug="master_data.products.edit", name="edit", description=""
        )
        db.add(permission)
        db.flush()
    db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=permission.id))
    db.commit()


def test_the_action_is_registered_with_the_products_edit_permission():
    from app.services.form_action_registry import get_action

    action = get_action("accessory_image.delete")
    assert action is not None
    assert action.entity_types == ("accessory_image",)
    assert action.permission == "master_data.products.edit"


def test_parking_another_companys_picture_is_refused(api):
    db, in_company, other = api
    _grant_products_edit(db)
    in_company(other)
    foreign = _picture(db, other)
    in_company(_SORENTO)
    with TestClient(app) as client:
        res = _park(client, "accessory_image.delete", "accessory_image", foreign.id)
    assert res.status_code == 404, res.text


def test_a_lapsed_action_removes_the_picture_and_its_attachment(api, monkeypatch):
    from app.models.accessory import AccessoryImage
    from app.models.resources import Attachment
    from app.services import accessory_service

    monkeypatch.setattr(accessory_service, "delete_object_best_effort", lambda *a, **k: None)
    db, in_company, _other = api
    _grant_products_edit(db)
    mine = _picture(db, _SORENTO)
    image_id, attachment_id = mine.id, mine.attachment_id
    with TestClient(app) as client:
        res = _park(client, "accessory_image.delete", "accessory_image", image_id)
        assert res.status_code == 202, res.text
        _lapse(db, res.json()["id"])
    _sweep(db)
    db.expire_all()
    assert db.query(AccessoryImage).filter(AccessoryImage.id == image_id).first() is None
    assert db.query(Attachment).filter(Attachment.id == attachment_id).first() is None
