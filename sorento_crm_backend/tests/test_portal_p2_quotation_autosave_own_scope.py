"""RELEASE-FIX-PORTAL: the "only theirs" guard on the quotation form's draft, History and Payment
Terms routes (QUOTE-AUTOSAVE #2303, QUOTE-TERMS-SELECT #2305, STANDARD-HISTORY #2299).

UAC: documentation/plans/project-sales/release-fix-portal-11nov-acceptance-criteria.md.

A user limited to their own projects works these routes on their own project with the right
data, gets the standard 404 on anyone else's (never the guard's 403, which would say the route
exists), cannot reach another proposal's History entry through their own proposal, and is still
refused without a session.
"""
from __future__ import annotations

import pytest

from app.models.base import company_scope
from app.models.payment_term import PaymentTerm
from app.models.projects import (
    ProjectQuotationDocument,
    QuotationDocumentDraft,
    QuotationDocumentSnapshot,
)

from ._own_scope_support import MARKER, acting, uid
from .test_portal_p2_own_scope_projects import (  # noqa: F401  (`scene` is a fixture)
    BASE,
    LIMITED,
    VIEW,
    scene,
)

GUARD_REFUSAL = "Not available with access to your own records only."


def _state(subject: str) -> dict:
    """A form state in the shape ``QuotationFormClient`` holds it."""
    return {
        "v": 1,
        "header": {"subject_title": subject},
        "letter": {},
        "scopes": [],
        "staged": {},
        "removedIds": [],
        "total": "0",
    }


def _document(db, company_id: str, project_id: str) -> ProjectQuotationDocument:
    row = ProjectQuotationDocument(
        id=uid(), company_id=company_id, project_id=project_id, document_no=f"{MARKER}-{uid()[:6]}"
    )
    db.add(row)
    db.flush()
    return row


def _entry(db, document: ProjectQuotationDocument, subject: str) -> QuotationDocumentSnapshot:
    row = QuotationDocumentSnapshot(
        id=uid(), document_id=document.id, kind="saved", doc=_state(subject), grand_total=0
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def quotes(scene):
    """A proposal with one saved History entry on A's own P1 and on B's P4, plus a payment term."""
    db, w, p = scene
    with company_scope(db, frozenset({w.company_id})):
        own = _document(db, w.company_id, p["p1"])
        foreign = _document(db, w.company_id, p["p4"])
        own_entry = _entry(db, own, f"{MARKER} own Monday")
        foreign_entry = _entry(db, foreign, f"{MARKER} foreign Monday")
        term = PaymentTerm(
            company_id=w.company_id, term_code=f"{MARKER} Net 30", term_rule="Net 30", is_active=True
        )
        db.add(term)
        db.flush()
        yield db, w, p, {
            "own": own.id,
            "foreign": foreign.id,
            "own_entry": own_entry.id,
            "foreign_entry": foreign_entry.id,
            "term": str(term.id),
        }


def _root(project_id: str) -> str:
    return f"{BASE}/projects/{project_id}/quotation-documents"


# Every project route these PRs added, addressed on (project, document, entry).
_ROUTES = (
    ("POST", "/new-draft/open", None),
    ("GET", "/new-draft/holder", None),
    ("PUT", "/new-draft", {"doc": _state("x"), "token": ""}),
    ("GET", "/payment-terms", None),
    ("POST", "/{document}/form-draft/open", None),
    ("GET", "/{document}/form-draft/holder", None),
    ("PUT", "/{document}/form-draft", {"doc": _state("x"), "token": ""}),
    ("GET", "/{document}/history", None),
    ("GET", "/{document}/history/{entry}", None),
    ("POST", "/{document}/history/{entry}/restore", {"token": ""}),
)


def _path(project_id: str, template: str, document: str, entry: str) -> str:
    return _root(project_id) + template.format(document=document, entry=entry)


# ------------------------------------------------------------------ AC-1: their own project


def test_their_own_proposal_draft_history_and_restore_work(quotes):
    db, w, p, q = quotes
    root = f"{_root(p['p1'])}/{q['own']}"
    with acting(db, w.a, LIMITED) as client:
        opened = client.post(f"{root}/form-draft/open")
        assert opened.status_code == 200, opened.text
        token = opened.json()["token"]

        holder = client.get(f"{root}/form-draft/holder", headers={"X-Form-Draft-Token": token})
        assert holder.status_code == 200, holder.text
        assert holder.json()["is_holder"] is True

        saved = client.put(f"{root}/form-draft", json={"doc": _state(f"{MARKER} Tuesday"), "token": token})
        assert saved.status_code == 200, saved.text

        history = client.get(f"{root}/history")
        assert history.status_code == 200, history.text
        assert [row["id"] for row in history.json()["data"]] == [q["own_entry"]]

        entry = client.get(f"{root}/history/{q['own_entry']}")
        assert entry.status_code == 200, entry.text
        assert entry.json()["doc"]["header"]["subject_title"] == f"{MARKER} own Monday"

        restored = client.post(f"{root}/history/{q['own_entry']}/restore", json={"token": token})
        assert restored.status_code == 200, restored.text
        assert restored.json()["doc"]["header"]["subject_title"] == f"{MARKER} own Monday"


def test_their_own_new_proposal_draft_and_payment_terms_work(quotes):
    db, w, p, q = quotes
    root = _root(p["p1"])
    with acting(db, w.a, LIMITED) as client:
        opened = client.post(f"{root}/new-draft/open")
        assert opened.status_code == 200, opened.text
        token = opened.json()["token"]

        holder = client.get(f"{root}/new-draft/holder", headers={"X-Form-Draft-Token": token})
        assert holder.status_code == 200, holder.text
        assert holder.json()["is_holder"] is True

        saved = client.put(f"{root}/new-draft", json={"doc": _state(f"{MARKER} new"), "token": token})
        assert saved.status_code == 200, saved.text

        terms = client.get(f"{root}/payment-terms")
        assert terms.status_code == 200, terms.text
        assert q["term"] in {row["id"] for row in terms.json()["data"]}


# ------------------------------------------------------------------ AC-2: someone else's project


@pytest.mark.parametrize("method,template,body", _ROUTES)
def test_every_route_is_404_on_another_salespersons_project(quotes, method, template, body):
    db, w, p, q = quotes
    path = _path(p["p4"], template, q["foreign"], q["foreign_entry"])
    with acting(db, w.a, LIMITED) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == 404, (method, template, response.status_code, response.text)
    assert response.json().get("detail") == "Not found", response.text
    drafts = db.query(QuotationDocumentDraft).filter(QuotationDocumentDraft.project_id == p["p4"]).count()
    assert drafts == 0


# ------------------------------------------------------------------ AC-3: ids under their own parent


@pytest.mark.parametrize("method,template,body", [r for r in _ROUTES if "{document}" in r[1]])
def test_another_projects_proposal_is_404_under_their_own_project(quotes, method, template, body):
    db, w, p, q = quotes
    path = _path(p["p1"], template, q["foreign"], q["foreign_entry"])
    with acting(db, w.a, LIMITED) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == 404, (method, template, response.status_code, response.text)
    assert GUARD_REFUSAL not in response.text


def test_another_proposals_history_entry_is_404_through_their_own_proposal(quotes):
    db, w, p, q = quotes
    root = f"{_root(p['p1'])}/{q['own']}"
    with acting(db, w.a, LIMITED) as client:
        token = client.post(f"{root}/form-draft/open").json()["token"]
        read = client.get(f"{root}/history/{q['foreign_entry']}")
        restore = client.post(f"{root}/history/{q['foreign_entry']}/restore", json={"token": token})
    for response in (read, restore):
        assert response.status_code == 404, response.text
        assert response.json().get("code") == "quotation_history_not_found", response.text


# ------------------------------------------------------------------ AC-4: no session


@pytest.mark.parametrize("method,template,body", _ROUTES)
def test_every_route_still_refuses_without_a_session(quotes, method, template, body):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    db, _w, p, q = quotes
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).request(
            method, _path(p["p1"], template, q["own"], q["own_entry"]), json=body
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code in (401, 403), (method, template, response.status_code, response.text)


# ------------------------------------------------------------------ AC-5: not records of a project


@pytest.mark.parametrize(
    "path,own_slug",
    [
        # quotation_templates.py:68, gated like the other /config/quotation-templates reads.
        ("/config/quotation-templates/payment-terms", "projects.types.view"),
        # order_inquiries.py:2069, gated like GET /order-inquiry-headers/{inquiry_id}.
        ("/order-inquiry-headers/{x}/history", VIEW),
    ],
)
def test_the_company_terms_list_and_oi_history_follow_their_own_slug(quotes, path, own_slug):
    """No project behind them: `view_own` neither opens nor closes them; their own slug (the
    one their sibling routes take) decides."""
    db, w, _p, _q = quotes
    url = BASE + path.replace("{x}", uid())
    with acting(db, w.a, LIMITED) as client:
        response = client.get(url)
        assert response.status_code == 403, response.text
        assert GUARD_REFUSAL not in response.text
    with acting(db, w.a, LIMITED | {own_slug}) as client:
        response = client.get(url)
        assert response.status_code != 403, response.text
