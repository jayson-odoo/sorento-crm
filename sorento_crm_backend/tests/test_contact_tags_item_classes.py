"""TAG-BRAND-CLASS: the tag `item_classes` setting (AC-7, AC-8, AC-9). RED first.

PLAN: documentation/plans/contacts/PLAN-tag-brand-class-30oct.md D5. A tag's settings may hold
`item_classes: "all" | [code]` beside `brands`; codes are item class codes ("__NONE__" = No
class). Across a contact's tags the lists intersect ("all" neutral, nothing in common = a
conflict that is never written); Apply writes the result onto
`respond_contacts.allowed_item_class_codes`.
"""
from __future__ import annotations

import uuid

from app.models.product import ItemClass
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests.test_contact_tags_s1 import (  # noqa: F401
    CONTACTS, EDIT, TAGS, VIEW, _contact, _set_tags, _tag, client, db, perms,
)
from tests.test_contact_tags_s2 import _holder, _item, _read, _stag, all_perms  # noqa: F401
from tests.test_contact_tags_s3 import _apply, _change, _fresh, _rows
from tests._pg_fixture import unique_code

NONE = "__NONE__"


def _class(db, stem: str, company_id: str = DEFAULT_COMPANY_ID) -> ItemClass:
    row = ItemClass(id=str(uuid.uuid4()), item_class_code=unique_code(stem, alpha=True).upper()[:50],
                    item_class_name=f"ZZT {stem}", company_id=company_id)
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------- validation + catalog


def test_a_tag_saves_and_reads_back_its_item_classes(client, db, all_perms):
    diy = _class(db, "DIY")
    tag = _tag(client)
    settings = {"brands": "all", "item_classes": [NONE, diy.item_class_code]}
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": settings})
    assert resp.status_code == 200, resp.text
    assert client.get(f"{TAGS}/{tag['id']}").json()["settings"] == settings


def test_all_is_a_valid_item_classes_value(client, db, all_perms):
    tag = _tag(client)
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": {"item_classes": "all"}})
    assert resp.status_code == 200, resp.text


def test_an_unknown_code_is_422_naming_it(client, db, all_perms):
    tag = _tag(client)
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": {"item_classes": ["ZZT-NO-SUCH"]}})
    assert resp.status_code == 422, resp.text
    assert "ZZT-NO-SUCH" in resp.text


def test_an_empty_list_is_422(client, db, all_perms):
    """An empty allow list would hide everything; "all" says every class."""
    tag = _tag(client)
    resp = client.patch(f"{TAGS}/{tag['id']}", json={"settings": {"item_classes": []}})
    assert resp.status_code == 422, resp.text


def test_the_catalog_offers_no_class_first_and_one_option_per_code(client, db, all_perms):
    from app.models.company import Company

    diy = _class(db, "DIY")
    other = Company(id=str(uuid.uuid4()), name="ZZT tbc other", code=unique_code("TBO")[:20])
    db.add(other)
    db.flush()
    db.add(ItemClass(id=str(uuid.uuid4()), item_class_code=diy.item_class_code,
                     item_class_name="ZZT DIY other", company_id=other.id))
    db.flush()
    resp = client.get(f"{TAGS}/settings-catalog")
    assert resp.status_code == 200, resp.text
    options = resp.json()["item_classes"]
    assert options[0] == {"value": NONE, "label": "No class"}
    assert [o["value"] for o in options].count(diy.item_class_code) == 1


# ---------------------------------------------------------------- merge + evaluate


def test_two_tags_intersect_and_all_is_neutral(client, db, all_perms):
    diy, serene = _class(db, "DIY"), _class(db, "SERENE")
    a = _stag(client, db, {"item_classes": [NONE, diy.item_class_code, serene.item_class_code]})
    b = _stag(client, db, {"item_classes": [NONE, diy.item_class_code]})
    c = _stag(client, db, {"item_classes": "all"})
    item = _item(_read(client, _holder(client, db, [a, b, c])), "item_classes")
    assert item["conflict"] is False
    assert sorted(item["expected"]) == sorted(["No class", diy.item_class_name])


def test_nothing_in_common_is_a_conflict(client, db, all_perms):
    diy, serene = _class(db, "DIY"), _class(db, "SERENE")
    a = _stag(client, db, {"item_classes": [diy.item_class_code]})
    b = _stag(client, db, {"item_classes": [serene.item_class_code]})
    assert _item(_read(client, _holder(client, db, [a, b])), "item_classes")["conflict"] is True


def test_current_reads_the_contact_column(client, db, all_perms):
    diy = _class(db, "DIY")
    tag = _stag(client, db, {"item_classes": [NONE, diy.item_class_code]})
    matching = _holder(client, db, [tag], allowed_item_class_codes=[NONE, diy.item_class_code])
    item = _item(_read(client, matching), "item_classes")
    assert item["differs"] is False
    other = _holder(client, db, [tag])
    item = _item(_read(client, other), "item_classes")
    assert item["differs"] is True
    assert item["current"] == "All"


# ---------------------------------------------------------------- apply


def test_apply_writes_the_allowed_classes_and_a_second_apply_changes_nothing(client, db, all_perms):
    """AC-9, the owner's case on a tag: All brands + "No class, DIY"."""
    diy = _class(db, "DIY")
    tag = _stag(client, db, {"brands": "all", "item_classes": [NONE, diy.item_class_code]})
    contact = _holder(client, db, [tag])
    preview = _rows(_apply(client, [contact.id], dry_run=True))["results"][0]
    change = _change(preview, "item_classes")
    assert change["before"] == "All"
    assert sorted(change["after"]) == sorted(["No class", diy.item_class_name])
    applied = _rows(_apply(client, [contact.id], dry_run=False))["results"][0]
    assert applied["status"] == "changed", applied
    row = _fresh(db, contact.id)
    assert sorted(row.allowed_item_class_codes) == sorted([NONE, diy.item_class_code])
    assert row.brand_class_ids is None
    again = _rows(_apply(client, [contact.id], dry_run=False))["results"][0]
    assert again["status"] == "unchanged", again


def test_apply_all_clears_the_contact_list(client, db, all_perms):
    diy = _class(db, "DIY")
    tag = _stag(client, db, {"item_classes": "all"})
    contact = _holder(client, db, [tag], allowed_item_class_codes=[diy.item_class_code])
    _rows(_apply(client, [contact.id], dry_run=False))
    assert not _fresh(db, contact.id).allowed_item_class_codes


def test_a_conflict_is_never_written(client, db, all_perms):
    diy, serene = _class(db, "DIY"), _class(db, "SERENE")
    a = _stag(client, db, {"item_classes": [diy.item_class_code]})
    b = _stag(client, db, {"item_classes": [serene.item_class_code]})
    contact = _holder(client, db, [a, b])
    _rows(_apply(client, [contact.id], dry_run=False))
    assert _fresh(db, contact.id).allowed_item_class_codes is None


def test_apply_needs_contacts_edit_like_brands(client, db, perms):
    diy = _class(db, "DIY")
    perms["granted"] = {VIEW, EDIT}
    tag = _stag(client, db, {"item_classes": [diy.item_class_code]})
    contact = _holder(client, db, [tag])
    _rows(_apply(client, [contact.id], dry_run=False))
    assert _fresh(db, contact.id).allowed_item_class_codes == [diy.item_class_code]
