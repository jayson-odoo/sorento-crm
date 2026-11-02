"""PS-PROPOSAL-QUOTATION at the HTTP boundary.

The service rules are pinned in ``test_project_proposal_quotation.py``. What is pinned here is what
only the routes decide: the make-quotation route answers 201 with the new quotation's payload and
the refusals with their codes, and the soft stop on a PO save and a PO confirm is a 409 the screen
can read (code + products), after which the SAME save with ``qty_over_reason`` goes through and
the reason is on the PO payload.
"""
from __future__ import annotations

import pytest

from ._pg_fixture import blank_session
from .test_project_po_document_save import _client, _restore
from .test_project_proposal_quotation import (
    MARKER,
    _issue,
    _price,
    _setup,
    _win,
)

BASE = "/api/v1/project-sales"


@pytest.fixture()
def env():
    from app.models.base import company_scope

    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        _price(db, scope, product, owner, "100.00", 10)
        record = _issue(db, document, owner)
        db.commit()
        client, originals = _client(db, owner)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, owner, product, project, document, scope, record
        finally:
            _restore(originals)


def _make(client, project, document, record):
    return client.post(
        f"{BASE}/projects/{project.id}/quotation-documents/{document.id}/make-quotation",
        json={"issue_id": record.id},
    )


def test_make_quotation_route_refuses_a_project_that_is_not_won(env):
    client, _, _, _, project, document, _, record = env
    response = _make(client, project, document, record)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "project_not_won"


def test_make_quotation_route_returns_the_quotation_and_links_both_ways(env):
    client, db, _, _, project, document, scope, record = env
    _win(db, scope)
    db.commit()

    response = _make(client, project, document, record)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "quotation"
    assert body["source_label"] == f"{document.document_no}-A"
    assert body["source_document_id"] == document.id
    assert body["document_no"].startswith(f"{MARKER}/QT/")

    proposal = client.get(f"{BASE}/projects/{project.id}/quotation-documents/{document.id}")
    assert proposal.status_code == 200
    assert proposal.json()["kind"] == "proposal"
    assert proposal.json()["quotation_document_id"] == body["id"]

    again = _make(client, project, document, record)
    assert again.status_code == 409
    assert again.json()["code"] == "project_has_quotation"


def test_po_save_over_the_quoted_qty_asks_for_a_reason_then_saves_with_it(env, monkeypatch):
    from app.services import project_notify_service
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    alerts = []
    monkeypatch.setattr(
        project_notify_service, "notify_po_qty_over", lambda *a, **k: alerts.append(k)
    )
    client, db, _, product, project, document, scope, record = env
    _win(db, scope)
    db.commit()
    quotation = _make(client, project, document, record).json()
    q_scope = qdocs.list_scopes(db, qdocs.get_document(db, quotation["id"]))[0]
    version_id = quotes.current_version(db, q_scope.id).id

    created = client.post(
        f"{BASE}/projects/{project.id}/purchase-orders",
        json={
            "po_number": f"{MARKER}-PO-1",
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
        },
    )
    assert created.status_code == 201, created.text
    po_id = created.json()["id"]
    lines = [{"product_id": product.id, "unit_price": "100.00", "quantity": "12"}]

    refused = client.put(f"{BASE}/purchase-orders/{po_id}", json={"lines": lines})
    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["code"] == "po_qty_over_quoted"
    products = body["details"]["products"]
    assert len(products) == 1
    assert products[0]["product_code"] == product.product_code
    assert float(products[0]["ordered"]) == 12
    assert float(products[0]["quoted"]) == 10
    # Rolled back: nothing of the refused save stuck.
    assert client.get(f"{BASE}/purchase-orders/{po_id}/lines").json()["data"] == []

    saved = client.put(
        f"{BASE}/purchase-orders/{po_id}",
        json={"lines": lines, "qty_over_reason": "Variation order VO-3"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["qty_over_reason"] == "Variation order VO-3"
    assert saved.json()["checked_against_kind"] == "quotation"
    assert len(alerts) == 1

    # The PO carries its reason, so the next save is not asked again.
    again = client.put(f"{BASE}/purchase-orders/{po_id}", json={"lines": lines})
    assert again.status_code == 200, again.text


# --------------------------------------------- review round 1 (B1, B2, S1, S2)


def _manager(db, company_id: str, name: str) -> str:
    import uuid

    from app.models.company import UserCompany
    from app.models.user import User, UserStatus

    from .test_project_quotation_approval_routes import _grant

    user_id = str(uuid.uuid4())
    db.add(
        User(id=user_id, email=f"{user_id}@zzt.test", name=name, status=UserStatus.ACTIVE.value)
    )
    db.flush()
    _grant(db, user_id, "projects.projects.manage")
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=user_id, company_id=company_id))
    db.flush()
    return user_id


def test_b1_a_price_change_reaches_every_manager_in_app_and_by_email(env, monkeypatch):
    """The real notification service, not a stub: it commits per recipient, so sending inside
    the issue's transaction reached one manager and queued no email at all."""
    from app.models.notification import Notification, NotificationDelivery

    from .test_project_proposal_quotation import _reprice, _sign

    # Nothing leaves the sandbox: the email job is enqueued, never run.
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: None)
    client, db, owner, product, project, document, scope, _ = env
    managers = {_manager(db, project.company_id, f"{MARKER} Boss {n}") for n in (1, 2)}
    _reprice(db, scope, product, owner, unit_price="90.00")
    _sign(db, document, owner)
    db.commit()

    response = client.post(
        f"{BASE}/projects/{project.id}/quotation-documents/{document.id}/issue"
    )
    assert response.status_code == 201, response.text
    assert response.json()["revision_label"] == "B"

    rows = (
        db.query(Notification)
        .filter(Notification.type == "project_proposal_price_changed")
        .all()
    )
    assert {row.user_id for row in rows} >= managers
    emails = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id.in_([row.id for row in rows]),
            NotificationDelivery.channel == "email",
        )
        .all()
    )
    assert {d.notification_id for d in emails} == {row.id for row in rows}


def test_b2_a_scanned_po_auto_binds_to_the_quotation_not_the_won_proposal(env):
    from app.services import project_po_service as pos
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes
    from app.services.project_po_extraction_service import ProjectPOExtractionService

    client, db, owner, _, project, document, scope, record = env
    _win(db, scope)  # the proposal scope is won too: without the filter, two equal candidates
    db.commit()
    quotation = _make(client, project, document, record).json()
    q_scope = qdocs.list_scopes(db, qdocs.get_document(db, quotation["id"]))[0]

    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={"po_number": f"{MARKER}-SCAN", "po_source": "contractor_direct"},
    )
    assert po.quotation_version_id is None
    ProjectPOExtractionService(db)._bind_quotation_version(po)
    assert po.quotation_version_id == quotes.current_version(db, q_scope.id).id


def test_s1_only_the_po_checked_against_the_quotation_with_the_product_is_asked(env):
    from app.services import project_po_service as pos
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    client, db, owner, product, project, document, scope, record = env
    early = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "po_number": f"{MARKER}-EARLY",
            "po_source": "contractor_direct",
            "quotation_version_id": quotes.current_version(db, scope.id).id,
        },
    )
    _win(db, scope)
    db.commit()
    quotation = _make(client, project, document, record).json()
    q_scope = qdocs.list_scopes(db, qdocs.get_document(db, quotation["id"]))[0]
    version_id = quotes.current_version(db, q_scope.id).id
    over = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "po_number": f"{MARKER}-OVER",
            "po_source": "contractor_direct",
            "quotation_version_id": version_id,
        },
    )
    pos.replace_lines(
        db, po=over, lines=[{"product_id": product.id, "unit_price": "100.00", "quantity": 12}]
    )
    pos.enforce_qty_over(db, over, reason="VO-1", actor_user_id=owner)
    db.commit()

    # A legacy PO bound to the proposal, and a header-only save of it, is never asked.
    saved = client.put(f"{BASE}/purchase-orders/{early.id}", json={"notes": "called them"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["qty_over_reason"] is None


def test_s2_confirming_a_scan_over_the_quotation_asks_then_confirms_with_the_reason(env):
    from app.models.project_so import ProjectPOVersion
    from app.services import project_po_service as pos
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes
    from app.services.document_extraction import PageResult
    from app.services.project_po_extraction_service import (
        STATE_QUEUED,
        ProjectPOExtractionService,
    )

    client, db, owner, product, project, document, scope, record = env
    _win(db, scope)
    db.commit()
    quotation = _make(client, project, document, record).json()
    q_scope = qdocs.list_scopes(db, qdocs.get_document(db, quotation["id"]))[0]
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "po_number": f"{MARKER}-SCAN2",
            "po_source": "contractor_direct",
            "quotation_version_id": quotes.current_version(db, q_scope.id).id,
        },
    )
    version = ProjectPOVersion(
        company_id=po.company_id,
        purchase_order_id=po.id,
        version_no=1,
        source_filename=f"{MARKER}.pdf",
        page_count=1,
        extraction_state=STATE_QUEUED,
    )
    db.add(version)
    db.flush()
    ProjectPOExtractionService(db).persist_pages(
        version,
        [
            PageResult(
                page_no=1,
                data={
                    "header": {"po_number": f"{MARKER}-SCAN2"},
                    "lines": [
                        {
                            "no": 1,
                            "stock_code": product.product_code,
                            "qty": 12,
                            "unit_price": 100.00,
                            "amount": 1200.00,
                        }
                    ],
                },
            )
        ],
    )
    db.commit()
    url = f"{BASE}/purchase-order-versions/{version.id}/confirm"

    refused = client.post(url)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "po_qty_over_quoted"
    db.expire_all()
    assert db.query(ProjectPOVersion).get(version.id).confirmed_at is None  # rolled back

    confirmed = client.post(url, json={"qty_over_reason": "Extra block"})
    assert confirmed.status_code == 200, confirmed.text
    db.expire_all()
    assert pos.get_po(db, po.id).qty_over_reason == "Extra block"
