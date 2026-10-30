"""PORTAL-P4-REQUESTS owner hand test 2 (A): a salesperson reads the fulfilment DOs of their
OWN complaint (view_own), read-only. Another salesperson's complaint answers 404 (as the detail
GET does), staff `.view` is unchanged, a user with neither is refused (403).
"""
from __future__ import annotations

import uuid

from app.models.complaints import Complaint, ComplaintFulfilmentOrder
from app.models.order import Order
from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

BASE = "/api/v1/complaints-management/complaints"


def _complaint_with_do(sc, contact_id, number):
    c = Complaint(id=str(uuid.uuid4()), complaint_number=f"ZZT-{number}", status="processed_by_cs",
                  contact_id=contact_id)
    o = Order(id=str(uuid.uuid4()), order_number=f"ZZTDO-{number}")
    sc.db.add_all([c, o])
    sc.db.flush()
    sc.db.add(ComplaintFulfilmentOrder(id=str(uuid.uuid4()), complaint_id=c.id, order_id=o.id))
    sc.db.commit()
    return c, o


def _get(sc, actor, cid):
    return sc.client.get(f"{BASE}/{cid}/fulfilment-orders", headers=actor.headers)


def test_view_own_reads_fulfilment_orders_of_own_complaint(scene):
    c, o = _complaint_with_do(scene, scene.contact.id, uuid.uuid4().hex[:8])
    r = _get(scene, scene.sp, c.id)
    assert r.status_code == 200, (r.status_code, r.text)
    assert [row["order_number"] for row in r.json()] == [o.order_number]


def test_view_own_refused_for_another_contacts_complaint(scene):
    c, _ = _complaint_with_do(scene, scene.other_contact.id, uuid.uuid4().hex[:8])
    r = _get(scene, scene.sp, c.id)
    assert r.status_code == 404, (r.status_code, r.text)


def test_staff_view_unchanged(scene):
    staff = s.make_user(scene.db, perms=["complaint_management.complaints.view"], name="ZZT Viewer")
    c, o = _complaint_with_do(scene, scene.other_contact.id, uuid.uuid4().hex[:8])
    r = _get(scene, staff, c.id)
    assert r.status_code == 200, (r.status_code, r.text)
    assert [row["order_number"] for row in r.json()] == [o.order_number]


def test_user_with_neither_permission_is_refused(scene):
    nobody = s.make_user(scene.db, perms=["inventory.products.view"], name="ZZT Nobody")
    c, _ = _complaint_with_do(scene, scene.contact.id, uuid.uuid4().hex[:8])
    r = _get(scene, nobody, c.id)
    assert r.status_code == 403, (r.status_code, r.text)
