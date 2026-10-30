"""Copying a contact's access carries its allowed item classes (TAG-BRAND-CLASS AC-10; ITEM-CLASS
security review H1 for the retired per-brand narrowing).

Without it a copy from a source allowed "No class, DIY" gave every target every class (SERENE
included), and a target with no list read as "identical" (no change shown).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.access import RespondContact
from app.models.company import Company
from app.models.product import ItemClass
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._brand_scope_seed import brand
from tests._pg_fixture import unique_code
from tests.test_contact_bulk_copy_access import (  # noqa: F401 - fixtures + helpers
    AGENTS_EDIT,
    EDIT,
    VIEW,
    _by_id,
    _contact,
    _post,
    client,
    db,
    perms,
)
from tests.test_contact_copy_fields import STOCK_EDIT, roles  # noqa: F401


@pytest.fixture
def full(perms, roles):  # noqa: F811
    perms["granted"] = {VIEW, EDIT, AGENTS_EDIT, STOCK_EDIT}
    return perms


def _class(db, name: str, company_id: str = DEFAULT_COMPANY_ID) -> ItemClass:
    row = ItemClass(id=str(uuid.uuid4()), item_class_code=unique_code(name, alpha=True).upper()[:50],
                    item_class_name=f"ZZT {name}", company_id=company_id)
    db.add(row)
    db.flush()
    return row


def _brands_change(resp, target):
    return next((c for c in _by_id(resp.json())[target.id]["changes"] if c["facet"] == "brands"), None)


def test_copy_carries_the_allowed_classes_to_a_target_with_none(client, db, full):  # noqa: F811
    diy = _class(db, "DIY")
    source, target = _contact(db, "ic-src"), _contact(db, "ic-tgt")
    source.allowed_item_class_codes = ["__NONE__", diy.item_class_code]
    db.flush()

    preview = _post(client, source, [target], dry_run=True)
    assert preview.status_code == 200, preview.text
    change = _brands_change(preview, target)
    assert change is not None, "the allowed classes must show as a change"
    assert change["before"] == "All brands"
    assert change["after"] == f"All brands; classes: No class, {diy.item_class_name}"

    applied = _post(client, source, [target])
    assert applied.status_code == 200, applied.text
    db.expire_all()
    row = db.get(RespondContact, target.id)
    assert row.allowed_item_class_codes == ["__NONE__", diy.item_class_code]
    assert row.brand_class_ids is None  # the retired column is never written


def test_copy_from_a_source_with_no_list_clears_the_target_list(client, db, full):  # noqa: F811
    sorento, diy = brand(db, "zicsrt2"), _class(db, "DIY2")
    source, target = _contact(db, "ic-src2"), _contact(db, "ic-tgt2")
    source.brand_ids = [sorento.id]
    target.brand_ids = [sorento.id]
    target.allowed_item_class_codes = [diy.item_class_code]
    db.flush()

    applied = _post(client, source, [target])
    assert applied.status_code == 200, applied.text
    assert _brands_change(applied, target) is not None
    db.expire_all()
    assert not db.get(RespondContact, target.id).allowed_item_class_codes


def test_identical_allowed_classes_are_no_change(client, db, full):  # noqa: F811
    sorento, diy = brand(db, "zicsrt3"), _class(db, "DIY3")
    source, target = _contact(db, "ic-src3"), _contact(db, "ic-tgt3")
    for c in (source, target):
        c.brand_ids = [sorento.id]
        c.allowed_item_class_codes = ["__NONE__", diy.item_class_code]
    db.flush()
    resp = _post(client, source, [target], dry_run=True)
    assert resp.status_code == 200, resp.text
    assert _brands_change(resp, target) is None


def test_a_class_outside_the_actor_company_scope_skips_the_brands_facet(client, db, full):  # noqa: F811
    """As for a hidden brand: the direct editor would refuse the code, so the copy leaves the
    whole facet out rather than writing the brands without the class limit (a widening)."""
    other = Company(id=str(uuid.uuid4()), name="ZZT ic other", code=f"ZIO{uuid.uuid4().hex[:6]}")
    db.add(other)
    db.flush()
    sorento, hidden = brand(db, "zicsrt4"), _class(db, "HIDDEN", company_id=other.id)
    source, target = _contact(db, "ic-src4"), _contact(db, "ic-tgt4")
    source.brand_ids = [sorento.id]
    source.allowed_item_class_codes = [hidden.item_class_code]
    db.flush()

    resp = _post(client, source, [target])
    assert resp.status_code == 200, resp.text
    assert _brands_change(resp, target) is None
    db.expire_all()
    row = db.get(RespondContact, target.id)
    assert not row.brand_ids and not row.allowed_item_class_codes
