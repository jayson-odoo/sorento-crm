"""QUOTE-DUPLICATE-PARTY (red-first): "Duplicate for another party" on a proposal / quotation.

Plan: documentation/plans/project-sales/PLAN-quote-duplicate-party-11nov.md. UAC D1-D11 in
quote-duplicate-party-11nov-acceptance-criteria.md (ids in each docstring).

Postgres only, via ``blank_session``. Every name is invented (public repo).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.certificate import Certificate
from app.models.numbering import DocumentNumberingRule
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import (
    ProjectParty,
    ProjectPartyContact,
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationDocumentCertificate,
    ProjectQuotationLine,
    QuotationDocumentSnapshot,
)
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-qdp"
LIST_PRICE = "100.00"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return str(db.execute(text("select id from companies where code = 'SRT'")).scalar())


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _rule(db, company_id: str, doc_type: str, prefix: str) -> None:
    rule = (
        db.query(DocumentNumberingRule)
        .filter(DocumentNumberingRule.doc_type == doc_type, DocumentNumberingRule.company_id == company_id)
        .first()
    )
    if rule is None:
        rule = DocumentNumberingRule(id=_uid(), doc_type=doc_type, company_id=company_id)
        db.add(rule)
    rule.enabled = True
    rule.prefix_template = prefix
    rule.number_digits = 4
    rule.next_value = 1
    rule.start_value = 1
    rule.reset_policy = "none"
    rule.last_reset_key = None
    db.flush()


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{uuid.uuid4().hex}", uom_name="Piece")
    category = ProductCategory(id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} Basins")
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Basin",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal(LIST_PRICE),
    )
    db.add(row)
    db.flush()
    return row


def _party(db, company_id, party_type, name):
    row = ProjectParty(
        id=_uid(), company_id=company_id, party_type=party_type, name=f"{MARKER} {name}",
        address="1 Jalan Contoh\n50000 Kuala Lumpur", phone="03-0000 0002", email="party@zzt.test",
    )
    db.add(row)
    db.flush()
    return row


def _contact(db, party, name):
    row = ProjectPartyContact(
        id=_uid(), company_id=party.company_id, party_id=party.id, name=name,
        phone="012-000 0003", email="contact@zzt.test",
    )
    db.add(row)
    db.flush()
    return row


class World:
    pass


def _world(db) -> World:
    """A project with a developer and an architect on it, one priced, signed proposal."""
    from app.services import project_party_contact_service as party_contacts
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes
    from app.services.project_service import register_project

    w = World()
    w.db = db
    w.company_id = _sorento(db)
    project_seed_service.run(db, company_id=w.company_id)
    _rule(db, w.company_id, "project_quotation", f"{MARKER}/Q/")
    _rule(db, w.company_id, "project_sales_quotation", f"{MARKER}/QT/")
    w.owner = _user(db, f"{MARKER} Salesperson Lim")
    w.copier = _user(db, f"{MARKER} Salesperson Wong")
    w.product = _product(db)
    w.developer = _party(db, w.company_id, "developer", "CONTOH DEVELOPMENT SDN BHD")
    w.architect = _party(db, w.company_id, "architect", "CONTOH ARKITEK")
    w.attn = _contact(db, w.architect, "Ar. Test Person")
    w.project = register_project(
        db, company_id=w.company_id, actor_user_id=w.owner, developer_party_id=w.developer.id,
        title=f"{MARKER} Taman Contoh {_uid()[:8]}",
    )
    party_contacts.add_party_link(db, w.project, "architect", w.architect.id)
    w.source = qdocs.create_document(
        db, project=w.project, actor_user_id=w.owner,
        payload={"your_ref": "THEIR-REF-1", "terms_html": "<p>zzt terms</p>"},
    )
    w.source.cover_letter_html = "<p>zzt letter</p>"
    w.source.cover_closing_html = "<p>zzt closing</p>"
    w.source.validity = "30 days"
    w.source.spec_sheet = {"items": {"zzt": {"area": "Lobby"}}}
    w.scope_a = qdocs.add_scope(db, document=w.source, scope_label=f"{MARKER} Tower A", actor_user_id=w.owner)
    w.scope_b = qdocs.add_scope(db, document=w.source, scope_label=f"{MARKER} Tower B", actor_user_id=w.owner)
    for scope, qty in ((w.scope_a, 3), (w.scope_b, 5)):
        quotes.upsert_line(
            db, version=quotes.current_version(db, scope.id), actor_user_id=w.owner,
            payload={"product_id": w.product.id, "unit_price": LIST_PRICE, "quantity": qty},
        )
    _sign(db, w.source, w.owner)
    db.flush()
    return w


def _sign(db, document, actor) -> None:
    from app.services import project_quotation_document_service as qdocs

    qdocs.sign_as_sorento(
        db, document=document, actor_user_id=actor,
        payload={"signer_name": f"{MARKER} Signer", "mode": "draw", "image_data_uri": "data:image/png;base64,zzt"},
    )


def _discount(w, price="80.00"):
    """Re-price every line below list: the document now needs a manager."""
    from app.services import project_quotation_service as quotes

    for scope in (w.scope_a, w.scope_b):
        version = quotes.current_version(w.db, scope.id)
        if quotes.is_issued(w.db, version):
            version = quotes.revise(w.db, quotation=scope, actor_user_id=w.owner)
        for line in quotes.list_lines(w.db, version.id):
            quotes.upsert_line(
                w.db, version=version, actor_user_id=w.owner, line=line,
                payload={"product_id": w.product.id, "unit_price": price, "quantity": line.quantity},
            )
    w.db.flush()


def _approve(w) -> None:
    from app.services import project_quotation_approval_service as approvals

    approvals._set_status(w.db, w.source, approvals._status_by_key(w.db, approvals.STATUS_APPROVED))
    w.db.flush()


def _key(db, document):
    from app.services import project_quotation_approval_service as approvals

    return approvals.current_key(db, document)


def _duplicate(w, *, party=None, attn=None, actor=None, source=None):
    from app.services import project_quotation_document_service as qdocs

    payload = {"recipient_party_id": (party or w.architect).id}
    if attn is not None:
        payload["attn_contact_ids"] = [c.id for c in attn]
    copy = qdocs.duplicate_document(
        w.db, source=source or w.source, actor_user_id=actor or w.copier, payload=payload
    )
    w.db.flush()
    return copy


def _lines(db, document):
    from app.services import project_quotation_service as quotes

    out = []
    scopes = (
        db.query(ProjectQuotation)
        .filter(ProjectQuotation.document_id == document.id)
        .order_by(ProjectQuotation.sort_order)
        .all()
    )
    for scope in scopes:
        version = quotes.current_version(db, scope.id)
        for line in quotes.list_lines(db, version.id):
            out.append((scope.scope_label, str(line.product_id), Decimal(line.quantity), Decimal(line.unit_price)))
    return out


def _history_notes(db, document):
    return [
        row.note
        for row in db.query(QuotationDocumentSnapshot)
        .filter(QuotationDocumentSnapshot.document_id == document.id)
        .all()
    ]


# --------------------------------------------------------------------------- the copy


def test_copy_is_a_new_document_for_the_picked_party():
    """D3: new number, picked To + Attn, today's date, no Your Ref, Prepared By = whoever duplicated."""
    with blank_session() as db:
        w = _world(db)
        copy = _duplicate(w, attn=[w.attn])

        assert copy.id != w.source.id
        assert copy.document_no != w.source.document_no
        assert copy.project_id == w.project.id
        assert copy.kind == "proposal"
        assert copy.recipient_party_id == w.architect.id
        assert copy.recipient_name_snapshot == w.architect.name
        assert copy.attn_name == "Ar. Test Person"
        assert copy.your_ref is None
        assert copy.created_by == w.copier
        assert copy.copied_from_document_id == w.source.id


def test_copy_holds_every_scope_line_and_letter():
    """D4: every area, line, quantity and price; letter, closing, terms, validity, spec sheet."""
    with blank_session() as db:
        w = _world(db)
        copy = _duplicate(w)

        assert _lines(db, copy) == _lines(db, w.source)
        assert len(_lines(db, copy)) == 2
        assert copy.cover_letter_html == "<p>zzt letter</p>"
        assert copy.cover_closing_html == "<p>zzt closing</p>"
        assert copy.terms_html == "<p>zzt terms</p>"
        assert copy.validity == "30 days"
        assert copy.spec_sheet == {"items": {"zzt": {"area": "Lobby"}}}


def test_copy_is_not_signed_and_carries_no_quotation_link():
    """Plan: the signature is not copied (Q2 a); source_issue_id is never copied."""
    with blank_session() as db:
        w = _world(db)
        copy = _duplicate(w)
        assert copy.signatory_signature_id is None
        assert copy.source_issue_id is None


def test_certificate_choices_are_copied():
    """D4: the Certification tab choices travel with the copy."""
    with blank_session() as db:
        w = _world(db)
        cert = Certificate(id=_uid(), scheme="PPS", certificate_number=f"ZZT{uuid.uuid4().hex[:10]}", status="active", title="ZZT cert")
        db.add(cert)
        db.flush()
        db.add(
            ProjectQuotationDocumentCertificate(
                company_id=w.company_id, document_id=w.source.id, certificate_id=cert.id,
                included=True, source="manual", send_to_customer=True, boxes=["zzt"],
            )
        )
        db.flush()
        copy = _duplicate(w)
        rows = (
            db.query(ProjectQuotationDocumentCertificate)
            .filter(ProjectQuotationDocumentCertificate.document_id == copy.id)
            .all()
        )
        assert [(r.certificate_id, r.source, r.send_to_customer, r.boxes) for r in rows] == [
            (cert.id, "manual", True, ["zzt"])
        ]


def test_source_is_untouched():
    """D5: lines, To and History of the source do not move (apart from the History note)."""
    with blank_session() as db:
        w = _world(db)
        before = _lines(db, w.source)
        _duplicate(w)
        db.refresh(w.source)
        assert _lines(db, w.source) == before
        assert w.source.recipient_party_id == w.developer.id


def test_copy_lines_are_their_own_rows():
    """Later revisions of each copy are independent: no line row is shared."""
    with blank_session() as db:
        w = _world(db)
        copy = _duplicate(w)
        source_scope_ids = {s.id for s in db.query(ProjectQuotation).filter(ProjectQuotation.document_id == w.source.id)}
        copy_scopes = db.query(ProjectQuotation).filter(ProjectQuotation.document_id == copy.id).all()
        assert copy_scopes and not ({s.id for s in copy_scopes} & source_scope_ids)


# --------------------------------------------------------------------------- refusals


def test_party_is_required():
    """D2: no party, no copy."""
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        w = _world(db)
        with pytest.raises(AppException) as err:
            qdocs.duplicate_document(db, source=w.source, actor_user_id=w.copier, payload={})
        assert err.value.status_code == 422
        assert db.query(ProjectQuotationDocument).filter(ProjectQuotationDocument.project_id == w.project.id).count() == 1


def test_party_not_on_project_needs_a_role():
    """The header picker's rule: a party not on the project is linked in a role, else refused."""
    with blank_session() as db:
        w = _world(db)
        stranger = _party(db, w.company_id, "consultant", "CONTOH PERUNDING")
        with pytest.raises(AppException) as err:
            _duplicate(w, party=stranger)
        assert err.value.code == "quotation_recipient_role_required"


def test_pending_draft_refuses():
    """D10: unsaved autosave edits on the source refuse the copy."""
    from app.services import quotation_form_draft_service as drafts

    with blank_session() as db:
        w = _world(db)
        row = drafts.document_draft(db, w.source, create=True)
        row.doc = {"header": {"your_ref": "typed"}}
        db.flush()
        with pytest.raises(AppException):
            _duplicate(w)


def test_quotation_source_copies_as_a_proposal():
    """D11: the project keeps one quotation; its copy is a proposal (card Q1 a)."""
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        w = _world(db)
        record = qdocs.issue(db, document=w.source, actor_user_id=w.owner)
        quotation = qdocs.make_quotation(db, proposal=w.source, issue_id=record.id, actor_user_id=w.owner)
        db.flush()
        copy = _duplicate(w, source=quotation)
        assert copy.kind == "proposal"
        assert copy.copied_from_document_id == quotation.id


# --------------------------------------------------------------------------- approval


def test_no_approval_needed_leaves_copy_off_the_graph():
    """D7 (nothing to carry): a list-priced source gives a copy with no approval state."""
    with blank_session() as db:
        w = _world(db)
        copy = _duplicate(w)
        assert copy.approval_status_id is None


def test_approval_carried_from_an_approved_source():
    """D6: source approved -> copy approved, no request, History says where it came from."""
    with blank_session() as db:
        w = _world(db)
        _discount(w)
        _approve(w)
        copy = _duplicate(w)
        assert _key(db, copy) == "approved"
        notes = _history_notes(db, copy)
        assert any(n and n.startswith("Approval carried from") and w.source.document_no in n for n in notes)


def test_approval_carried_from_a_source_sent_while_approved_and_unchanged():
    """D6: approved, then sent (approval spent), nothing changed since -> carried."""
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        w = _world(db)
        _discount(w)
        _approve(w)
        qdocs.issue(db, document=w.source, actor_user_id=w.owner)
        db.flush()
        assert _key(db, w.source) == "issued"
        copy = _duplicate(w)
        assert _key(db, copy) == "approved"


def test_approval_not_carried_when_lines_changed_after_the_send():
    """D7: sent while approved, then re-priced -> the copy asks through the normal flow."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        w = _world(db)
        _discount(w)
        _approve(w)
        qdocs.issue(db, document=w.source, actor_user_id=w.owner)
        db.flush()
        version = quotes.revise(db, quotation=w.scope_a, actor_user_id=w.owner)
        line = quotes.list_lines(db, version.id)[0]
        quotes.upsert_line(
            db, version=version, actor_user_id=w.owner, line=line,
            payload={"product_id": w.product.id, "unit_price": "70.00", "quantity": line.quantity},
        )
        db.flush()
        copy = _duplicate(w)
        assert _key(db, copy) != "approved"


def test_approval_not_carried_from_a_pending_source():
    """D7: a request still with the manager is not an approval."""
    from app.services import project_quotation_approval_service as approvals

    with blank_session() as db:
        w = _world(db)
        _discount(w)
        approvals._set_status(db, w.source, approvals._status_by_key(db, approvals.STATUS_PENDING))
        db.flush()
        copy = _duplicate(w)
        assert _key(db, copy) != "approved"


def test_carried_approval_is_spent_by_the_copys_own_send():
    """The copy then behaves like any approved document: Send spends it."""
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        w = _world(db)
        _discount(w)
        _approve(w)
        copy = _duplicate(w)
        _sign(db, copy, w.copier)
        qdocs.issue(db, document=copy, actor_user_id=w.copier)
        db.flush()
        assert _key(db, copy) == "issued"


# --------------------------------------------------------------------------- traceability


def test_history_on_both_documents():
    """D8: the copy says where it came from, the source says who it was copied for."""
    with blank_session() as db:
        w = _world(db)
        copy = _duplicate(w)
        copy_notes = _history_notes(db, copy)
        source_notes = _history_notes(db, w.source)
        assert any(n and n.startswith("Copied from") and w.source.document_no in n for n in copy_notes)
        assert any(
            n and w.architect.name in n and copy.document_no in n and n.startswith("Duplicated for")
            for n in source_notes
        )


def test_history_event_entries_list_but_do_not_restore():
    """The History sheet lists event entries; they carry no state to restore."""
    from app.services import quotation_form_draft_service as drafts

    with blank_session() as db:
        w = _world(db)
        copy = _duplicate(w)
        rows = drafts.list_history(db, copy)
        events = [r for r in rows if r["kind"] == "event"]
        assert events
        with pytest.raises(AppException):
            drafts.restore_entry(db, document=copy, entry_id=events[0]["id"], token="zzt", user_id=w.copier)


def test_serializer_carries_copied_from_label():
    """D8: the header's "Copied from" link reads the source's number."""
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        w = _world(db)
        copy = _duplicate(w)
        payload = qdocs.serialize_document(db, copy)
        assert payload["copied_from_document_id"] == str(w.source.id)
        assert w.source.document_no in payload["copied_from_label"]


def test_approval_read_fresh_not_from_a_stale_source_object():
    """Security review S1: a Revise committed after the source was loaded must win. The status is
    re-read (row locked) before the carry, so a source moved back to draft carries nothing."""
    from app.services import project_quotation_approval_service as approvals

    with blank_session() as db:
        w = _world(db)
        _discount(w)
        _approve(w)
        draft = approvals._status_by_key(db, approvals.STATUS_DRAFT)
        # Another transaction's Revise, written past this session's loaded object.
        db.query(ProjectQuotationDocument).filter(ProjectQuotationDocument.id == w.source.id).update(
            {"approval_status_id": draft.id}, synchronize_session=False
        )
        assert _key(db, w.source) == "approved"  # the loaded object is stale
        copy = _duplicate(w)
        assert _key(db, copy) != "approved"


def test_carried_approval_is_on_the_project_feed():
    """Security review N1: the carry is recorded as its own event, naming source and actor."""
    from app.models.activities import ActivityEvent

    with blank_session() as db:
        w = _world(db)
        _discount(w)
        _approve(w)
        copy = _duplicate(w)
        rows = (
            db.query(ActivityEvent)
            .filter(ActivityEvent.system_template == "quotation_approval_carried")
            .all()
        )
        mine = [r for r in rows if (r.system_payload or {}).get("document_id") == str(copy.id)]
        assert mine and w.source.document_no in (mine[0].body_text or "")
