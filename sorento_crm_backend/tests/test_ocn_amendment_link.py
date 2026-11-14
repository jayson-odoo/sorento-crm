"""OCN-ORDER-CHANGE-NOTICE red tests: one change, one notice (UAC E1-E4, owner d2).

`ProjectSODeltaService.create(..., ocn_id=None)` drafts an OCN exactly as today unless an
existing OCN of the same project (not linked to another amendment) is picked; publishing an
amendment needs that OCN approved (`approval_status == "approved"`, not voided).

The R1 -> R2 build is the delta suite's own (tests/test_project_so_delta.py), reused rather
than copied. Postgres only, every row seeded.
"""
from __future__ import annotations

import re

import pytest

from app.models.project_so import OrderChangeNotice, SOAmendment
from app.services.error_handler import AppException
from app.services.project_so_delta_service import ProjectSODeltaService

from ._ocn_support import ALL_SLUGS, KIND, change_types, number_pattern, numbering_rule, svc
from ._pg_fixture import blank_session
from .test_project_so_delta import _revision, _tuju
from .test_project_so_draft import _sorento, _user, project_seed_service


@pytest.fixture()
def build():
    from types import SimpleNamespace

    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, "zzt-ocn Sales Admin A")
        # Lead ruling m17 (round 4): the amendment's author must be able to see the notice
        # they pick, so the author holds the OCN view grant.
        from ._forms_chain_support import grant

        grant(db, owner, "procurement.order_change_notices.view")
        numbering_rule(db)
        types = change_types(db)
        with company_scope(db, frozenset({company_id})):
            project, po, po_version, _r1, phases, orders, products = _tuju(db, company_id, owner)
            r2 = _revision(db, project, po, po_version, phases, products)
            yield SimpleNamespace(
                db=db, company_id=company_id, owner=owner, types=types, project=project, po=po,
                orders=orders, r2=r2, products=products,
            )


def _actor(b):
    return svc().actor_from_slugs(b.owner, ALL_SLUGS)


def _crm_ocn(b, project_id):
    p1 = b.products[0]
    row = svc().create_draft(b.db, actor=_actor(b), data={
        "change_type_id": b.types.delay.id,
        "customer_name": "Customer A",
        "customer_po_no": "XT04/3871 (R1)",
        "project_id": project_id,
        "description": "Programme pushed six months.",
        "lines": [{"product_id": p1.id, "qty_before": 10, "qty_after": 10, "date_before": None,
                   "date_after": None, "delivered_qty": 0, "remark": None}],
    })
    b.db.flush()
    return row


def _create(b, **kw):
    return ProjectSODeltaService(b.db).create(
        b.orders["TOWER"].id, schedule_version_id=b.r2.id,
        reason="Main contractor pushed the programme.", actor_user_id=b.owner, **kw,
    )


def _ocns_of_project(b):
    return b.db.query(OrderChangeNotice).filter(OrderChangeNotice.project_id == b.project.id).all()


# ------------------------------------------------------------------ E1


def test_e1_an_amendment_without_a_pick_drafts_a_new_ocn_as_today(build):
    b = build
    created = _create(b)
    ocn = b.db.query(OrderChangeNotice).filter(OrderChangeNotice.id == created["ocn_id"]).one()
    amendment = b.db.query(SOAmendment).filter(SOAmendment.id == created["amendment_id"]).one()
    assert amendment.ocn_id == ocn.id
    assert ocn.source == "amendment"
    assert ocn.status == "draft"
    assert ocn.project_id == b.project.id
    assert ocn.project_sales_order_id == b.orders["TOWER"].id
    assert ocn.purchase_order_id == b.po.id
    assert ocn.change_table_json["verb_summary"] == amendment.verb_summary
    assert re.match(number_pattern(), created["ocn_number"]), created["ocn_number"]


def test_e1_the_amendment_request_schema_takes_an_optional_ocn_id():
    from app.schemas.project_sales_order import AmendmentCreateRequest

    assert AmendmentCreateRequest(reason="Programme pushed.").ocn_id is None
    picked = "00000000-0000-0000-0000-0000000000e2"
    assert AmendmentCreateRequest(reason="Programme pushed.", ocn_id=picked).ocn_id == picked


# ------------------------------------------------------------------ E2


def test_e2_picking_an_existing_ocn_links_it_and_drafts_no_second_one(build):
    b = build
    mine = _crm_ocn(b, b.project.id)
    before = len(_ocns_of_project(b))
    created = _create(b, ocn_id=mine.id)
    amendment = b.db.query(SOAmendment).filter(SOAmendment.id == created["amendment_id"]).one()
    assert amendment.ocn_id == mine.id
    assert created["ocn_id"] == mine.id
    assert len(_ocns_of_project(b)) == before


def test_e2_an_ocn_of_another_project_is_refused(build):
    from ._sample_request_seed import make_project

    b = build
    elsewhere = make_project(b.db, b.company_id, b.owner, title="Kestrel Point Lofts")
    theirs = _crm_ocn(b, elsewhere.id)
    with pytest.raises(AppException) as exc:
        _create(b, ocn_id=theirs.id)
    assert exc.value.status_code in (409, 422)
    assert b.db.query(SOAmendment).filter(SOAmendment.ocn_id == theirs.id).count() == 0


def test_e2_an_ocn_already_linked_to_another_amendment_is_refused(build):
    b = build
    first = _create(b)
    with pytest.raises(AppException) as exc:
        _create(b, ocn_id=first["ocn_id"])
    assert exc.value.status_code in (409, 422)
    assert b.db.query(SOAmendment).filter(SOAmendment.ocn_id == first["ocn_id"]).count() == 1


# ------------------------------------------------------------------ E3


def _set(b, ocn_id, **cols):
    row = b.db.query(OrderChangeNotice).filter(OrderChangeNotice.id == ocn_id).one()
    for key, value in cols.items():
        setattr(row, key, value)
    b.db.flush()
    return row


def _publish(b, amendment_id):
    return ProjectSODeltaService(b.db).publish_amendment(amendment_id, actor_user_id=b.owner)


@pytest.mark.parametrize(
    "cols",
    [
        dict(status="draft", approval_status=None),
        dict(status="submitted", approval_status="pending"),
        dict(status="rejected", approval_status="rejected"),
        dict(status="voided", approval_status="voided"),
        dict(status="voided", approval_status="approved"),
    ],
    ids=["draft", "pending", "rejected", "voided", "voided_after_approval"],
)
def test_e3_publishing_is_refused_until_the_ocn_is_approved(build, cols):
    b = build
    created = _create(b)
    # The old gate read approver_id; naming an approver alone no longer publishes.
    _set(b, created["ocn_id"], approver_id=b.owner, **cols)
    with pytest.raises(AppException) as exc:
        _publish(b, created["amendment_id"])
    assert exc.value.status_code == 409
    assert getattr(exc.value, "code", None) in (None, "amendment_ocn_unapproved") or \
        "amendment_ocn_unapproved" in str(exc.value.detail)
    amendment = b.db.query(SOAmendment).filter(SOAmendment.id == created["amendment_id"]).one()
    assert amendment.status == "proposed"


def test_e3_an_approved_ocn_lets_the_amendment_publish(build):
    b = build
    created = _create(b)
    _set(b, created["ocn_id"], status="approved", approval_status="approved", approver_id=b.owner)
    body = _publish(b, created["amendment_id"])
    assert body["status"] == "published"


def test_e3_approved_through_the_ocn_chain_publishes(build):
    """The real path: the amendment-born OCN goes submit -> send -> approve, then publishes."""
    b = build
    s = svc()
    created = _create(b)
    row = b.db.query(OrderChangeNotice).filter(OrderChangeNotice.id == created["ocn_id"]).one()
    _set(b, row.id, change_type_id=b.types.delay.id)
    a = _actor(b)
    s.submit(b.db, row, actor=a)
    s.send_for_approval(b.db, row, actor=a)
    s.decide(b.db, row, actor=a, action="approved", comments=None)
    b.db.flush()
    assert _publish(b, created["amendment_id"])["status"] == "published"


# ------------------------------------------------------------------ E4


def test_e4_an_amendment_born_ocn_keeps_its_links_through_edit(build):
    from ._sample_request_seed import make_project

    b = build
    created = _create(b)
    row = b.db.query(OrderChangeNotice).filter(OrderChangeNotice.id == created["ocn_id"]).one()
    links = (row.project_id, row.project_sales_order_id, row.purchase_order_id)
    elsewhere = make_project(b.db, b.company_id, b.owner, title="Kestrel Point Lofts")
    try:
        svc().update(b.db, row, actor=_actor(b), data={
            "project_id": elsewhere.id, "project_sales_order_id": None, "purchase_order_id": None,
            "description": "Edited text is fine",
        })
    except AppException as exc:  # refusing the link change outright is also acceptable
        assert exc.status_code in (409, 422)
    b.db.flush()
    b.db.refresh(row)
    assert (row.project_id, row.project_sales_order_id, row.purchase_order_id) == links


def test_e4_the_amendment_born_ocn_is_the_same_kind_as_a_crm_one(build):
    """It is one record type: the amendment's OCN reads through the OCN service like any other."""
    b = build
    created = _create(b)
    row = b.db.query(OrderChangeNotice).filter(OrderChangeNotice.id == created["ocn_id"]).one()
    assert row.source == "amendment"
    assert svc().ENTITY == KIND
