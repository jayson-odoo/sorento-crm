"""ITEM-CLASS AC-8 / TAG-BRAND-CLASS AC-1: allowed item classes over every REST path brand scope covers.

The CONTACT-BRAND-SCOPE path list (`tests/test_brand_scope_paths.py::NAMING_PATHS`: stock,
product search, incoming stock, orders, outstanding, top selling, stock list) driven over
X-API-Key + contact_id/space_id, the MCP shape, with the real `apply_company_scope`.

The world's SORENTO product is given class SERENE. A contact allowed SORENTO with allowed classes
SERENE sees it; one allowed DIY (a class it does not carry) does not. Neither sees the MOCHA or the
unbranded product (brand not allowed / NULL brand, unchanged). The owner's case: All brands with
allowed classes "No class, DIY" sees MOCHA and the unbranded product (no class) but not the
SERENE one (TAG-BRAND-CLASS, `respond_contacts.allowed_item_class_codes`).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product import ItemClass
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._brand_scope_seed import api, contact, db, leaks, world  # noqa: F401
from tests._pg_fixture import unique_code
from tests.test_brand_scope_paths import IDS, NAMING_PATHS


def _item_class(db, name: str) -> ItemClass:
    row = ItemClass(id=str(uuid.uuid4()), item_class_code=unique_code(name, alpha=True).upper()[:50],
                    item_class_name=f"ZZT {name}", company_id=DEFAULT_COMPANY_ID)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def narrowed(db, world):
    from app.models.access import RespondContact

    serene, diy = _item_class(db, "SERENE"), _item_class(db, "DIY")
    world.p_sorento.item_class_id = serene.id
    db.flush()

    def _contact(codes, brands=True):
        c = contact(db, brand_ids=[world.sorento.id] if brands else None, access_code=world.access_code)
        db.query(RespondContact).filter(RespondContact.id == c.id).update(
            {"allowed_item_class_codes": list(codes)}, synchronize_session=False
        )
        return c

    out = {
        "serene": _contact([serene.item_class_code]),
        "diy": _contact([diy.item_class_code]),
        "no_serene": _contact(["__NONE__", diy.item_class_code], brands=False),
        "brand_only": contact(db, brand_ids=[world.sorento.id], access_code=world.access_code),
    }
    db.commit()
    return out


@pytest.mark.parametrize(("name", "path", "params"), NAMING_PATHS, ids=IDS)
def test_deploy_state_brand_only_contact_still_sees_a_classed_product(api, world, narrowed, name, path, params) -> None:
    """AC-10 inert: a contact with brands and no class list (every contact right after the
    migration) sees the SORENTO product after sync gave it a class, exactly as before."""
    resp = api.get(path, narrowed["brand_only"], **params)
    assert resp.status_code == 200, resp.text
    assert leaks(resp, world) == {"mocha": False, "sorento": True, "null": False}, name


@pytest.mark.parametrize(("name", "path", "params"), NAMING_PATHS, ids=IDS)
def test_contact_limited_to_the_products_class_sees_it(api, world, narrowed, name, path, params) -> None:
    resp = api.get(path, narrowed["serene"], **params)
    assert resp.status_code == 200, resp.text
    assert leaks(resp, world) == {"mocha": False, "sorento": True, "null": False}, name


@pytest.mark.parametrize(("name", "path", "params"), NAMING_PATHS, ids=IDS)
def test_contact_limited_to_another_class_sees_nothing_of_the_brand(api, world, narrowed, name, path, params) -> None:
    resp = api.get(path, narrowed["diy"], **params)
    assert resp.status_code == 200, resp.text
    assert leaks(resp, world) == {"mocha": False, "sorento": False, "null": False}, name


@pytest.mark.parametrize(("name", "path", "params"), NAMING_PATHS, ids=IDS)
def test_all_brands_without_serene_hides_only_the_serene_product(api, world, narrowed, name, path, params) -> None:
    resp = api.get(path, narrowed["no_serene"], **params)
    assert resp.status_code == 200, resp.text
    assert leaks(resp, world) == {"mocha": True, "sorento": False, "null": True}, name
