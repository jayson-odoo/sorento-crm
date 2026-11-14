"""OCN-ORDER-CHANGE-NOTICE round 8: the order change notice on the project's Related tab
(PROJECT-RELATED-RECORDS contract section 6, the plug-in registry).

A notice linked to the project is one more row type: number, status, approval, its date, the
raiser's name (never an id), its description, no value. Who sees it follows the notice's own
rule: `.view` or an acting grant (edit, approve, process) sees every notice, `.view_own` the
ones they raised or are named on, no grant none (the type is absent altogether).

Reuses the related-records suite's own scene (tests/test_project_related_records.py). Postgres
only, every row seeded.
"""
from __future__ import annotations

import uuid
from datetime import date

from ._own_scope_support import acting, user
from .test_project_related_records import FULL, _get, _viewer, scene  # noqa: F401  (fixture)

KIND = "order_change_notice"
OCN_VIEW = "procurement.order_change_notices.view"
OCN_OWN = "procurement.order_change_notices.view_own"
OCN_EDIT = "procurement.order_change_notices.edit"


def _ocn(db, company_id, project_id, created_by, **kw):
    from app.models.project_so import OrderChangeNotice

    values = dict(
        id=str(uuid.uuid4()),
        company_id=company_id,
        ocn_number=f"OCN26-{uuid.uuid4().int % 10**4:04d}",
        status="submitted",
        approval_status="pending",
        source="crm",
        customer_name="zzt-prr Customer A",
        ocn_date=date(2026, 6, 10),
        created_by=created_by,
        description="zzt-prr delivery pushed to January",
        project_id=project_id,
    )
    values.update(kw)
    row = OrderChangeNotice(**values)
    db.add(row)
    db.flush()
    return row


def _named_user(db, name):
    from app.models.user import User

    user_id = user(db, "x")
    db.get(User, user_id).name = name
    db.flush()
    return user_id


def test_r8_a_notice_on_the_project_is_listed_with_its_columns(scene):
    db, p = scene["db"], scene["p"]
    raiser = _named_user(db, "Rina Raiser")
    row = _ocn(db, scene["company_id"], p.id, raiser)
    _ocn(db, scene["company_id"], scene["p2"].id, raiser, ocn_number="OCN26-9902")  # another project
    _ocn(db, scene["company_id"], None, raiser, ocn_number="OCN26-9903")  # no project
    with acting(db, _viewer(db), FULL | {OCN_VIEW}) as client:
        body = _get(client, p.id)
    mine = [r for r in body["data"] if r["kind"] == KIND]
    assert len(mine) == 1
    got = mine[0]
    assert got["id"] == row.id
    assert got["number"] == row.ocn_number
    assert got["status"] == "submitted"
    assert got["approval_status"] == "pending"
    assert got["date"] == "2026-06-10"
    assert got["raised_by"] == "Rina Raiser"
    assert got["subject"] == "zzt-prr delivery pushed to January"
    assert got["value"] is None
    assert body["type_counts"][KIND] == 1
    assert body["types"][-1] == {"kind": KIND, "label": "Order change notice"}


def test_r8_a_view_own_reader_sees_only_the_notices_they_raised_or_are_named_on(scene):
    db, p, company_id = scene["db"], scene["p"], scene["company_id"]
    me = _named_user(db, "Owen Own")
    other = _named_user(db, "Olga Other")
    raised = _ocn(db, company_id, p.id, me, ocn_number="OCN26-8801")
    named = _ocn(db, company_id, p.id, other, ocn_number="OCN26-8802", cs_in_charge_user_id=me)
    _ocn(db, company_id, p.id, other, ocn_number="OCN26-8803")
    with acting(db, me, FULL | {OCN_OWN}) as client:
        body = _get(client, p.id)
    numbers = sorted(r["number"] for r in body["data"] if r["kind"] == KIND)
    assert numbers == sorted([raised.ocn_number, named.ocn_number])
    assert body["type_counts"][KIND] == 2


def test_r8_an_acting_grant_sees_every_notice(scene):
    db, p, company_id = scene["db"], scene["p"], scene["company_id"]
    raiser = _named_user(db, "Rex Raiser")
    _ocn(db, company_id, p.id, raiser, ocn_number="OCN26-7701")
    with acting(db, _viewer(db), FULL | {OCN_EDIT}) as client:
        body = _get(client, p.id)
    assert [r["number"] for r in body["data"] if r["kind"] == KIND] == ["OCN26-7701"]


def test_r8_no_notice_grant_means_no_notice_rows_type_or_count(scene):
    db, p = scene["db"], scene["p"]
    _ocn(db, scene["company_id"], p.id, _named_user(db, "Rae Raiser"))
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id)
        filtered = _get(client, p.id, type=[KIND])
    assert KIND not in {r["kind"] for r in body["data"]}
    assert KIND not in body["type_counts"]
    assert KIND not in [t["kind"] for t in body["types"]]
    assert filtered["data"] == []


def test_r8_the_registry_and_the_notice_agree_on_who_sees_every_notice():
    """own_scope's access table names the notice's view-all grants; they are the notice's own."""
    from app.services import order_change_notice_service as ocn
    from app.services import own_scope
    from app.services import project_related_records as registry

    assert own_scope.MODULE_REQUEST_KINDS[KIND] == (ocn.VIEW, ocn.VIEW_OWN)
    assert {own_scope.OCN_VIEW, *own_scope.VIEW_ALL_ALSO[KIND]} == set(ocn.VIEW_ALL_SLUGS)
    assert registry.RELATED_TYPES[KIND].label == "Order change notice"
    assert registry.RELATED_TYPES[KIND].screen_path == "/procurement-management/order-change-notices/{id}"
