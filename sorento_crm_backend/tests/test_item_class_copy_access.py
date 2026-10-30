"""ITEM-CLASS security review H1: copying a contact's access carries its class narrowing.

Without it a copy from a source limited to SORENTO / SERENE gave every target the whole SORENTO
brand, and a target that already held SORENTO whole read as "identical" (no change shown).
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
    row = ItemClass(id=str(uuid.uuid4()), item_class_code=unique_code(name)[:50],
                    item_class_name=f"ZZT {name}", company_id=company_id)
    db.add(row)
    db.flush()
    return row


def _brands_change(resp, target):
    return next((c for c in _by_id(resp.json())[target.id]["changes"] if c["facet"] == "brands"), None)


def test_copy_from_a_narrowed_source_narrows_a_target_holding_the_whole_brand(client, db, full):  # noqa: F811
    sorento, serene = brand(db, "zicsrt"), _class(db, "SERENE")
    source, target = _contact(db, "ic-src"), _contact(db, "ic-tgt")
    source.brand_ids = [sorento.id]
    source.brand_class_ids = {sorento.id: [serene.id]}
    target.brand_ids = [sorento.id]
    db.flush()

    preview = _post(client, source, [target], dry_run=True)
    assert preview.status_code == 200, preview.text
    change = _brands_change(preview, target)
    assert change is not None, "the class narrowing must show as a change"
    assert change["before"] == sorento.brand_name
    assert change["after"] == f"{sorento.brand_name} ({serene.item_class_name})"

    applied = _post(client, source, [target])
    assert applied.status_code == 200, applied.text
    db.expire_all()
    row = db.get(RespondContact, target.id)
    assert row.brand_ids == [sorento.id]
    assert row.brand_class_ids == {sorento.id: [serene.id]}


def test_copy_from_a_whole_brand_source_clears_a_target_narrowing(client, db, full):  # noqa: F811
    sorento, serene = brand(db, "zicsrt2"), _class(db, "SERENE2")
    source, target = _contact(db, "ic-src2"), _contact(db, "ic-tgt2")
    source.brand_ids = [sorento.id]
    target.brand_ids = [sorento.id]
    target.brand_class_ids = {sorento.id: [serene.id]}
    db.flush()

    applied = _post(client, source, [target])
    assert applied.status_code == 200, applied.text
    assert _brands_change(applied, target) is not None
    db.expire_all()
    assert not db.get(RespondContact, target.id).brand_class_ids


def test_identical_narrowing_is_no_change(client, db, full):  # noqa: F811
    sorento, serene = brand(db, "zicsrt3"), _class(db, "SERENE3")
    source, target = _contact(db, "ic-src3"), _contact(db, "ic-tgt3")
    for c in (source, target):
        c.brand_ids = [sorento.id]
        c.brand_class_ids = {sorento.id: [serene.id]}
    db.flush()
    resp = _post(client, source, [target], dry_run=True)
    assert resp.status_code == 200, resp.text
    assert _brands_change(resp, target) is None


def test_a_class_outside_the_actor_company_scope_skips_the_brands_facet(client, db, full):  # noqa: F811
    """As for a hidden brand: the direct editor would refuse the class, so the copy leaves the
    whole facet out rather than writing the brand without its narrowing (a widening)."""
    other = Company(id=str(uuid.uuid4()), name="ZZT ic other", code=f"ZIO{uuid.uuid4().hex[:6]}")
    db.add(other)
    db.flush()
    sorento, hidden = brand(db, "zicsrt4"), _class(db, "HIDDEN", company_id=other.id)
    source, target = _contact(db, "ic-src4"), _contact(db, "ic-tgt4")
    source.brand_ids = [sorento.id]
    source.brand_class_ids = {sorento.id: [hidden.id]}
    db.flush()

    resp = _post(client, source, [target])
    assert resp.status_code == 200, resp.text
    assert _brands_change(resp, target) is None
    db.expire_all()
    row = db.get(RespondContact, target.id)
    assert not row.brand_ids and not row.brand_class_ids
