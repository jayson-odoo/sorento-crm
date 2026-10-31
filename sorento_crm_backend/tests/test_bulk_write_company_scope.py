"""The remaining bulk writes stay inside the caller's company.

Follows #2027 (bulk deletes). The company scope filter (`app/services/company_scope.py`)
applies to ORM SELECTs only, so a bulk `query(...).update()` / `.delete()` or a Core
`update()` reached every company's rows by id. Promotion access levels, SPO allocation bulk
delete, attachment type and attachment access levels (with their propagation) now read
their rows through the scoped query and write each one.

Postgres only, on the blank scratch schema, seeding its own chain.
"""
from __future__ import annotations

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.access import ContactAccessType
from app.models.base import company_scope
from app.models.entity_attachment import EntityAttachmentLink
from app.models.marketing import Promotion
from app.models.procurement import InboundShipment, SPOAllocation
from app.models.product import Product, ProductAttachment, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from tests._pg_fixture import blank_session, unique_code

_SORENTO = "00000000-0000-0000-0000-000000000001"
_ACTOR_ID = "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d"
_ROLE_ID = "8b9c0d1e-2f3a-4b4c-9d5e-6f7a8b9c0d1e"

PROMOTIONS_BULK = "/api/v1/marketing/promotions/bulk"
ALLOCATIONS_BULK = "/api/v1/procurement/spo-allocations/bulk"
ATTACHMENT_TYPE_BULK = "/api/v1/resource-management/attachments/bulk-attachment-type"
ACCESS_LEVELS_APPLY = "/api/v1/resource-management/attachments/bulk-access-levels/apply"

_SLUGS = (
    "marketing.promotions.edit",
    "procurement.spo_allocations.delete",
)

_OLD = ["zzt_old"]
_NEW = ["zzt_new"]


def _seed_actor(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ROLE_ID,
            slug="zzt_bulk_write_scope",
            name="zzt_bulk_write_scope",
            description="",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=_ACTOR_ID, email="zzt-bulk-write@test.com", name="Bo Write", status="ACTIVE"))
    db.flush()
    db.add(UserRoleAssignment(user_id=_ACTOR_ID, role_id=_ROLE_ID))
    for slug in _SLUGS:
        permission = db.query(UserPermission).filter(UserPermission.slug == slug).first()
        if permission is None:
            permission = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
            db.add(permission)
            db.flush()
        db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=_ROLE_ID, permission_id=permission.id))
    for code in (*_OLD, *_NEW):
        if db.query(ContactAccessType).filter(ContactAccessType.code == code).first() is None:
            db.add(ContactAccessType(code=code, name=code, is_active=True))
    db.commit()


@pytest.fixture
def api():
    """One session, one signed-in user, and a switchable company scope (the request's
    and the session's together, so rows created after `_in_company` are stamped to it)."""
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_actor(db)
        other_company = str(uuid.uuid4())
        db.add(Company(id=other_company, name="ZZT other co", code=unique_code("ZZTC")))
        db.commit()

        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        principal = {"id": _ACTOR_ID, "email": "zzt-bulk-write@test.com"}
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        yield db, _in_company, other_company

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Seeds                                                                       #
# --------------------------------------------------------------------------- #


def _promotion(db) -> str:
    row = Promotion(id=str(uuid.uuid4()), description=unique_code("ZZTPR"), access_levels=list(_OLD))
    db.add(row)
    db.commit()
    return row.id


def _product(db) -> str:
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="Category"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:50], uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    code = unique_code("ZZTP")
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=0,
        is_active=True,
    )
    db.add(row)
    db.commit()
    return row.id


def _allocation(db) -> str:
    row = SPOAllocation(
        id=str(uuid.uuid4()),
        spo_number=unique_code("SPO")[:50],
        spo_line_number=1,
        product_id=_product(db),
        allocated_quantity=1,
    )
    db.add(row)
    db.commit()
    return row.id


def _attachment(db, company_id) -> str:
    """An attachment owned by `company_id`, or shared (visible to every company) for None."""
    name = unique_code("ZZTF") + ".pdf"
    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=name,
        stored_filename=name,
        file_path=f"zzt/{name}",
        access_levels=list(_OLD),
        company_id=company_id,
    )
    db.add(row)
    db.commit()
    return row.id


def _attachment_type(db) -> str:
    row = AttachmentType(
        id=str(uuid.uuid4()),
        type_name=unique_code("ZZTT"),
        allowed_extensions="pdf",
        max_file_size_mb=10,
    )
    db.add(row)
    db.commit()
    return row.id


def _shipment(db) -> str:
    row = InboundShipment(
        id=str(uuid.uuid4()),
        shipment_number=unique_code("SHP")[:50],
        shipment_date=datetime.date(2026, 10, 1),
        access_levels=list(_OLD),
    )
    db.add(row)
    db.commit()
    return row.id


def _unscoped(db, model, row_id: str):
    db.expire_all()
    with company_scope(db, None):
        return db.query(model).filter(model.id == row_id).first()


# --------------------------------------------------------------------------- #
# Promotion access levels                                                     #
# --------------------------------------------------------------------------- #


def _patch_promotions(client, ids):
    return client.patch(PROMOTIONS_BULK, json={"ids": ids, "access_levels": _NEW})


def test_promotion_access_levels_leave_another_companys_promotion_alone(api):
    db, _in_company, other = api
    _in_company(other)
    theirs = _promotion(db)
    _in_company(_SORENTO)
    mine = _promotion(db)

    with TestClient(app) as client:
        res = _patch_promotions(client, [theirs, mine])
    assert res.status_code == 200, res.text
    assert res.json()["updated_count"] == 1
    assert _unscoped(db, Promotion, theirs).access_levels == _OLD
    assert _unscoped(db, Promotion, mine).access_levels == _NEW


def test_promotion_access_levels_only_theirs_counts_zero(api):
    db, _in_company, other = api
    _in_company(other)
    theirs = _promotion(db)
    _in_company(_SORENTO)

    with TestClient(app) as client:
        res = _patch_promotions(client, [theirs])
    assert res.status_code == 200, res.text
    assert res.json()["updated_count"] == 0
    assert _unscoped(db, Promotion, theirs).access_levels == _OLD


def test_promotion_access_levels_need_the_edit_permission(api):
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.models.user import User

    db, _in_company, _other = api
    stranger = str(uuid.uuid4())
    db.add(User(id=stranger, email=f"{stranger}@zzt.test", name="No Grants", status="ACTIVE"))
    db.commit()
    mine = _promotion(db)
    principal = {"id": stranger, "email": f"{stranger}@zzt.test"}
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    with TestClient(app) as client:
        res = _patch_promotions(client, [mine])
    assert res.status_code == 403, res.text
    assert _unscoped(db, Promotion, mine).access_levels == _OLD


# --------------------------------------------------------------------------- #
# SPO allocation bulk delete                                                  #
# --------------------------------------------------------------------------- #


def test_allocation_bulk_delete_leaves_another_companys_row_alone(api):
    db, _in_company, other = api
    _in_company(other)
    theirs = _allocation(db)
    _in_company(_SORENTO)
    mine = _allocation(db)

    with TestClient(app) as client:
        res = client.request("DELETE", ALLOCATIONS_BULK, json={"ids": [theirs, mine]})
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 1
    assert _unscoped(db, SPOAllocation, theirs) is not None
    assert _unscoped(db, SPOAllocation, mine) is None


def test_allocation_bulk_delete_only_theirs_counts_zero(api):
    db, _in_company, other = api
    _in_company(other)
    theirs = _allocation(db)
    _in_company(_SORENTO)

    with TestClient(app) as client:
        res = client.request("DELETE", ALLOCATIONS_BULK, json={"ids": [theirs]})
    assert res.status_code == 200, res.text
    assert res.json()["deleted_count"] == 0
    assert _unscoped(db, SPOAllocation, theirs) is not None


# --------------------------------------------------------------------------- #
# Attachment type and access levels                                           #
# --------------------------------------------------------------------------- #


def test_attachment_type_leaves_another_companys_file_alone(api):
    db, _in_company, other = api
    type_id = _attachment_type(db)
    theirs = _attachment(db, other)
    mine = _attachment(db, _SORENTO)
    shared = _attachment(db, None)

    with TestClient(app) as client:
        res = client.post(
            ATTACHMENT_TYPE_BULK,
            json={"attachment_ids": [theirs, mine, shared], "attachment_type_id": type_id},
        )
    assert res.status_code == 200, res.text
    assert res.json()["updated_attachments"] == 2
    assert _unscoped(db, Attachment, theirs).attachment_type_id is None
    assert _unscoped(db, Attachment, mine).attachment_type_id == type_id
    assert _unscoped(db, Attachment, shared).attachment_type_id == type_id


def test_attachment_access_levels_leave_another_companys_file_alone(api):
    db, _in_company, other = api
    theirs = _attachment(db, other)
    mine = _attachment(db, _SORENTO)

    with TestClient(app) as client:
        res = client.post(
            ACCESS_LEVELS_APPLY,
            json={"attachment_ids": [theirs, mine], "access_levels": _NEW},
        )
    assert res.status_code == 200, res.text
    assert res.json()["updated_attachments"] == 1
    assert _unscoped(db, Attachment, theirs).access_levels == _OLD
    assert _unscoped(db, Attachment, mine).access_levels == _NEW


def test_access_level_propagation_stays_in_the_company(api):
    """A shared file is visible from every company and can be linked from each. Setting
    its access levels with propagation reaches the caller's own product link, promotion
    and packing list, and nobody else's."""
    db, _in_company, other = api
    shared = _attachment(db, None)

    _in_company(other)
    their_product_link = ProductAttachment(
        id=str(uuid.uuid4()), product_id=_product(db), attachment_id=shared, access_levels=list(_OLD)
    )
    db.add(their_product_link)
    their_promotion = _promotion(db)
    from app.models.marketing import PromotionAttachment

    db.add(PromotionAttachment(id=str(uuid.uuid4()), promotion_id=their_promotion, attachment_id=shared))
    their_shipment = _shipment(db)
    db.add(
        EntityAttachmentLink(
            id=str(uuid.uuid4()), entity_type="inbound_shipment", entity_id=their_shipment, attachment_id=shared
        )
    )
    db.commit()

    _in_company(_SORENTO)
    my_product_link = ProductAttachment(
        id=str(uuid.uuid4()), product_id=_product(db), attachment_id=shared, access_levels=list(_OLD)
    )
    db.add(my_product_link)
    my_promotion = _promotion(db)
    db.add(PromotionAttachment(id=str(uuid.uuid4()), promotion_id=my_promotion, attachment_id=shared))
    my_shipment = _shipment(db)
    db.add(
        EntityAttachmentLink(
            id=str(uuid.uuid4()), entity_type="inbound_shipment", entity_id=my_shipment, attachment_id=shared
        )
    )
    db.commit()
    their_link_id, my_link_id = their_product_link.id, my_product_link.id

    with TestClient(app) as client:
        res = client.post(
            ACCESS_LEVELS_APPLY,
            json={"attachment_ids": [shared], "access_levels": _NEW, "propagate_to_linked": True},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["updated_attachments"] == 1
    assert body["propagated"]["product_links"] == 1
    assert body["propagated"]["promotions"] == 1
    assert body["propagated"]["packing_lists"] == 1

    assert _unscoped(db, ProductAttachment, their_link_id).access_levels == _OLD
    assert _unscoped(db, Promotion, their_promotion).access_levels == _OLD
    assert _unscoped(db, InboundShipment, their_shipment).access_levels == _OLD
    assert _unscoped(db, ProductAttachment, my_link_id).access_levels == _NEW
    assert _unscoped(db, Promotion, my_promotion).access_levels == _NEW
    assert _unscoped(db, InboundShipment, my_shipment).access_levels == _NEW


def test_access_level_propagation_to_a_packing_lists_own_file_stays_in_the_company(api):
    """A packing list can also hold the file directly (`InboundShipment.attachment_id`)."""
    db, _in_company, other = api
    shared = _attachment(db, None)
    _in_company(other)
    theirs = _shipment(db)
    _unscoped(db, InboundShipment, theirs).attachment_id = shared
    db.commit()
    _in_company(_SORENTO)
    mine = _shipment(db)
    _unscoped(db, InboundShipment, mine).attachment_id = shared
    db.commit()

    with TestClient(app) as client:
        res = client.post(
            ACCESS_LEVELS_APPLY,
            json={"attachment_ids": [shared], "access_levels": _NEW, "propagate_to_linked": True},
        )
    assert res.status_code == 200, res.text
    assert res.json()["propagated"]["packing_lists"] == 1
    assert _unscoped(db, InboundShipment, theirs).access_levels == _OLD
    assert _unscoped(db, InboundShipment, mine).access_levels == _NEW
