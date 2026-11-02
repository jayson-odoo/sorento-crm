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
