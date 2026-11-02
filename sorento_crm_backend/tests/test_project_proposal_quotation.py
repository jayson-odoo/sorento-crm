"""PS-PROPOSAL-QUOTATION: proposal vs quotation flow, PO tallies with the quotation.

Written BEFORE the implementation (Phase 2, test-first). Every test is red until the lane
lands. Contract: documentation/plans/project-sales/PLAN-proposal-quotation-2nov.md, "Backend
contracts". Acceptance: proposal-quotation-2nov-acceptance-criteria.md (AC ids in each docstring).

Postgres only, via ``blank_session``. Every test seeds its own chain; every row carries the
``zzt-ppq`` marker. No price floor is configured anywhere here, so the only approval trigger a
test can hit is the new "below the proposal" rule.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.numbering import DocumentNumberingRule
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import ProjectParty, ProjectQuotationLine
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-ppq"
QUOTE_PREFIX = f"{MARKER}/QT/"


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
        .filter(DocumentNumberingRule.doc_type == doc_type)
        .first()
    )
    if rule is None:
        rule = DocumentNumberingRule(id=_uid(), doc_type=doc_type)
        if hasattr(DocumentNumberingRule, "company_id"):
            rule.company_id = company_id
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
    db.add(uom)
    category = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} Sanitary Ware",
    )
    db.add(category)
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} WC Suite",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("300.00"),
    )
    db.add(row)
    db.flush()
    return row


def _setup(db):
    """Project + one proposal document + one scope. Returns the parts a test needs."""
    from app.services import project_quotation_document_service as qdocs
    from app.services.project_service import register_project

    company_id = _sorento(db)
    project_seed_service.run(db, company_id=company_id)
    _rule(db, company_id, "project_quotation", f"{MARKER}/Q/")
    _rule(db, company_id, "project_sales_quotation", QUOTE_PREFIX)
    owner = _user(db, f"{MARKER} Baser")
    product = _product(db)
    project = register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Cabana Elmina {_uid()[:12]}",
    )
    document = qdocs.create_document(db, project=project, actor_user_id=owner)
    scope = qdocs.add_scope(
        db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
    )
    return company_id, owner, product, project, document, scope


def _price(db, scope, product, owner, unit_price: str, quantity: int = 2):
    from app.services import project_quotation_service as quotes

    return quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=owner,
        payload={"product_id": product.id, "unit_price": unit_price, "quantity": quantity},
    )


def _reprice(db, scope, product, owner, *, unit_price=None, quantity=None):
    """Open the next version of a scope and edit its single carried line."""
    from app.services import project_quotation_service as quotes

    version = quotes.revise(db, quotation=scope, actor_user_id=owner)
    line = (
        db.query(ProjectQuotationLine)
        .filter(ProjectQuotationLine.version_id == version.id)
        .one()
    )
    return quotes.upsert_line(
        db,
        version=version,
        actor_user_id=owner,
        line=line,
        payload={
            "product_id": product.id,
            "unit_price": unit_price if unit_price is not None else line.unit_price,
            "quantity": quantity if quantity is not None else line.quantity,
        },
    )


def _sign(db, document, owner) -> None:
    from app.services import project_quotation_document_service as qdocs

    qdocs.sign_as_sorento(
        db,
        document=document,
        actor_user_id=owner,
        payload={
            "signer_name": f"{MARKER} Baser",
            "mode": "draw",
            "image_data_uri": "data:image/png;base64,zzt",
        },
    )


def _issue(db, document, owner):
    from app.services import project_quotation_document_service as qdocs

    _sign(db, document, owner)
    return qdocs.issue(db, document=document, actor_user_id=owner)


def _win(db, scope) -> None:
    from app.services import project_quotation_service as quotes

    quotes.set_outcome(db, quotation=scope, outcome="won")


def _won_issued_proposal(db):
    """A priced, signed, issued proposal on a Won project. Returns (parts..., record)."""
    company_id, owner, product, project, document, scope = _setup(db)
    _price(db, scope, product, owner, "100.00", 2)
    record = _issue(db, document, owner)
    _win(db, scope)
    return company_id, owner, product, project, document, scope, record


def _make(db, proposal, record, owner):
    from app.services import project_quotation_document_service as qdocs

    return qdocs.make_quotation(
        db, proposal=proposal, issue_id=record.id, actor_user_id=owner
    )


# ------------------------------------------------------------------ 1. kind + labels (AC-1, AC-2)


def test_1_a_new_document_is_a_proposal_and_issues_label_a_then_b():
    from app.services import project_quotation_document_service as qdocs

    # Letters: A..Z then AA.
    assert qdocs.revision_letter(1) == "A"
    assert qdocs.revision_letter(2) == "B"
    assert qdocs.revision_letter(26) == "Z"
    assert qdocs.revision_letter(27) == "AA"

    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        assert document.kind == "proposal"
        assert document.source_issue_id is None

        _price(db, scope, product, owner, "100.00")
        first = _issue(db, document, owner)
        assert first.issue_no == 1
        assert first.revision_label == "A"
        assert first.our_ref_text == f"{document.document_no}-A"
        # The Send button reads what the server will stamp next.
        assert qdocs.serialize_document(db, document)["next_revision_label"] == "B"

        _reprice(db, scope, product, owner, unit_price="100.00", quantity=3)
        second = _issue(db, document, owner)
        assert second.issue_no == 2
        assert second.revision_label == "B"
        assert second.our_ref_text == f"{document.document_no}-B"
        assert qdocs.quotation_no(document.document_no, 2, second.revision_label) == (
            f"{document.document_no}-B"
        )
        # No label given keeps the legacy spelling.
        assert qdocs.quotation_no(document.document_no, 2) == f"{document.document_no}-R2"


# ------------------------------------------------------------------ 2. legacy R chain continues (AC-2)


def test_2_a_document_whose_first_issue_is_r1_keeps_r_labels():
    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        _price(db, scope, product, owner, "100.00")
        first = _issue(db, document, owner)
        # What the migration backfill does to every pre-lane issue.
        first.revision_label = "R1"
        db.flush()

        _reprice(db, scope, product, owner, unit_price="100.00", quantity=3)
        second = _issue(db, document, owner)
        assert second.revision_label == "R2"
        assert second.our_ref_text == f"{document.document_no}-R2"


# ------------------------------------------------------------------ 3. price alert (AC-3)


def test_3_a_changed_unit_price_alerts_management_and_a_qty_only_change_does_not(monkeypatch):
    from app.services import project_notify_service
    from app.services import project_quotation_document_service as qdocs

    calls = []

    def _fake(db, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        project_notify_service, "notify_proposal_price_changed", _fake, raising=False
    )

    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        _price(db, scope, product, owner, "100.00", 2)
        first = _issue(db, document, owner)
        qdocs.alert_price_changes(db, document, first)
        assert calls == []  # nothing to compare against on the first issue

        _reprice(db, scope, product, owner, unit_price="90.00")
        record_b = _issue(db, document, owner)
        # Worked out inside issue(), sent by the route after its commit.
        assert calls == []
        qdocs.alert_price_changes(db, document, record_b)
        assert len(calls) == 1
        assert record_b.issue_no == 2  # the issue always goes out
        call = calls[0]
        assert call["project"].id == project.id
        assert call["document"].id == document.id
        assert call["record"].id == record_b.id
        assert len(call["changes"]) == 1
        change = call["changes"][0]
        assert change["product_code"] == product.product_code
        assert Decimal(str(change["old_price"])) == Decimal("100.00")
        assert Decimal(str(change["new_price"])) == Decimal("90.00")

        # Quantity only: no new alert.
        _reprice(db, scope, product, owner, quantity=9)
        record_c = _issue(db, document, owner)
        assert record_c.price_changes == []
        qdocs.alert_price_changes(db, document, record_c)
        assert len(calls) == 1


# ------------------------------------------------------------------ 4. make_quotation refusals (AC-5)


def test_4a_make_quotation_is_refused_when_the_project_is_not_won():
    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        _price(db, scope, product, owner, "100.00")
        record = _issue(db, document, owner)  # scope stays open

        with pytest.raises(AppException) as refused:
            _make(db, document, record, owner)
        assert refused.value.status_code == 409
        assert refused.value.code == "project_not_won"


def test_4b_make_quotation_is_refused_when_the_source_is_itself_a_quotation():
    with blank_session() as db:
        _, owner, _, _, proposal, _, record = _won_issued_proposal(db)
        quotation = _make(db, proposal, record, owner)
        assert quotation.kind == "quotation"

        with pytest.raises(AppException) as refused:
            _make(db, quotation, record, owner)
        assert refused.value.status_code == 422
        assert refused.value.code == "quotation_source_not_proposal"


def test_4c_make_quotation_is_refused_when_the_project_already_has_one():
    with blank_session() as db:
        _, owner, _, _, proposal, _, record = _won_issued_proposal(db)
        _make(db, proposal, record, owner)

        with pytest.raises(AppException) as refused:
            _make(db, proposal, record, owner)
        assert refused.value.status_code == 409
        assert refused.value.code == "project_has_quotation"


def test_4d_make_quotation_is_refused_for_an_issue_that_is_not_on_the_document():
    with blank_session() as db:
        _, owner, _, _, proposal, _, _ = _won_issued_proposal(db)

        with pytest.raises(AppException) as refused:
            from app.services import project_quotation_document_service as qdocs

            qdocs.make_quotation(
                db, proposal=proposal, issue_id=_uid(), actor_user_id=owner
            )
        assert refused.value.status_code == 404
        assert refused.value.code == "quotation_issue_not_found"


# ------------------------------------------------------------------ 5. make_quotation copy (AC-5)


def test_5_make_quotation_copies_the_picked_revision_and_skips_lost_scopes():
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id, owner, product, project, proposal, won_scope = _setup(db)
        lost_scope = qdocs.add_scope(
            db, document=proposal, scope_label=f"{MARKER} Lost block", actor_user_id=owner
        )
        _price(db, won_scope, product, owner, "100.00", 4)
        _price(db, lost_scope, product, owner, "55.00", 1)

        party = ProjectParty(
            id=_uid(),
            company_id=company_id,
            party_type="main_contractor",
            name=f"{MARKER} Contractor Sdn Bhd",
            address=f"{MARKER} 1 Jalan Test",
            phone="0123456789",
        )
        db.add(party)
        db.flush()
        proposal.recipient_party_id = party.id
        proposal.recipient_name_snapshot = party.name
        proposal.recipient_address_snapshot = party.address
        proposal.recipient_phone_snapshot = party.phone
        proposal.attn_name = f"{MARKER} Attn"
        proposal.your_ref = f"{MARKER}-YR"
        proposal.subject_title = f"{MARKER} Subject"
        proposal.quotation_purpose = f"{MARKER} Purpose"
        proposal.cover_letter_html = f"<p>{MARKER} letter as issued</p>"
        proposal.terms_html = f"<p>{MARKER} terms as issued</p>"
        proposal.payment_terms = f"{MARKER} 30 days"
        proposal.validity = f"{MARKER} 60 days"
        proposal.signatory_name = f"{MARKER} Signer"
        proposal.signatory_phone = "0111111111"
        proposal.spec_sheet = {"templates": ["zzt-ppq"], "items": {}}
        db.flush()

        record = _issue(db, proposal, owner)

        # The draft moves on after the issue; the quotation must take the ISSUE's frozen copies.
        proposal.cover_letter_html = "<p>edited after issue</p>"
        proposal.terms_html = "<p>terms edited after issue</p>"
        db.flush()

        _win(db, won_scope)
        quotes.set_outcome(db, quotation=lost_scope, outcome="lost", loss_reason="price")
        assert project.outcome == "won"

        quotation = _make(db, proposal, record, owner)

        assert quotation.kind == "quotation"
        assert quotation.id != proposal.id
        assert quotation.project_id == project.id
        assert quotation.source_issue_id == record.id
        assert quotation.document_no.startswith(QUOTE_PREFIX)
        assert quotation.recipient_party_id == party.id
        assert quotation.recipient_name_snapshot == party.name
        assert quotation.attn_name == f"{MARKER} Attn"
        assert quotation.your_ref == f"{MARKER}-YR"
        assert quotation.subject_title == f"{MARKER} Subject"
        assert quotation.quotation_purpose == f"{MARKER} Purpose"
        assert quotation.cover_letter_html == record.cover_letter_rendered
        assert quotation.terms_html == record.terms_rendered
        assert quotation.payment_terms == f"{MARKER} 30 days"
        assert quotation.validity == f"{MARKER} 60 days"
        assert quotation.signatory_name == f"{MARKER} Signer"
        assert quotation.signatory_phone == "0111111111"
        # PS-SPEC-SHEET (#2103): the spec sheet settings travel too.
        assert quotation.spec_sheet == {"templates": ["zzt-ppq"], "items": {}}
        # The name and phone travel; the signature itself does not.
        assert quotation.signatory_signature_id is None

        scopes = qdocs.list_scopes(db, quotation)
        assert [s.scope_label for s in scopes] == [f"{MARKER} Townhouse"]
        assert scopes[0].id != won_scope.id
        assert scopes[0].outcome == "won"
        assert scopes[0].decided_at is not None

        version = quotes.current_version(db, scopes[0].id)
        assert version.version_no == 1
        lines = (
            db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.version_id == version.id)
            .all()
        )
        assert len(lines) == 1
        assert lines[0].product_id == product.id
        assert lines[0].unit_price == Decimal("100.00")
        assert lines[0].quantity == Decimal("4.00")
        assert lines[0].product_code_snapshot == product.product_code
        assert qdocs.version_total(db, version) == Decimal("400.00")

        # The first issue of a quotation counts R1, R2.
        issued = _issue(db, quotation, owner)
        assert issued.revision_label == "R1"
        assert issued.our_ref_text == f"{quotation.document_no}-R1"

        # Serializer carries the new fields to the screen.
        payload = qdocs.serialize_document(db, quotation)
        assert payload["kind"] == "quotation"
        assert payload["source_issue_id"] == record.id
        assert payload["source_document_id"] == proposal.id
        assert payload["source_label"] == f"{proposal.document_no}-A"
        proposal_payload = qdocs.serialize_document(db, proposal)
        assert proposal_payload["kind"] == "proposal"
        assert proposal_payload["quotation_document_id"] == quotation.id


# ------------------------------------------------------------------ 6. below-proposal approval (AC-6)


def test_6_a_quotation_line_below_the_source_price_needs_approval_equal_or_higher_does_not():
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        _, owner, product, _, proposal, _, record = _won_issued_proposal(db)
        quotation = _make(db, proposal, record, owner)
        scope = qdocs.list_scopes(db, quotation)[0]
        line = (
            db.query(ProjectQuotationLine)
            .filter(
                ProjectQuotationLine.version_id == quotes.current_version(db, scope.id).id
            )
            .one()
        )

        def _set(price: str, qty: int = 2) -> None:
            quotes.upsert_line(
                db,
                version=quotes.current_version(db, scope.id),
                actor_user_id=owner,
                line=line,
                payload={"product_id": product.id, "unit_price": price, "quantity": qty},
            )

        # As copied (equal): nothing to approve.
        assert approval.below_proposal_line_count(db, quotation) == 0
        assert approval.requires_approval(db, quotation) is False

        _set("90.00")  # below the proposal's 100.00
        assert approval.below_proposal_line_count(db, quotation) == 1
        assert approval.requires_approval(db, quotation) is True
        assert approval.serialize_approval(db, quotation)["below_proposal_count"] == 1

        _set("100.00")  # equal
        assert approval.below_proposal_line_count(db, quotation) == 0
        assert approval.requires_approval(db, quotation) is False

        _set("120.00", qty=50)  # higher, and a different quantity
        assert approval.below_proposal_line_count(db, quotation) == 0
        assert approval.requires_approval(db, quotation) is False

        # The rule is for quotations only: a proposal is never compared with itself.
        assert approval.below_proposal_line_count(db, proposal) == 0


# ------------------------------------------------------------------ 7. PO binding (AC-7)


def test_7_a_new_po_cannot_bind_to_a_proposal_once_a_quotation_exists():
    from app.services import project_po_service as pos
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        _, owner, _, project, proposal, scope, record = _won_issued_proposal(db)
        proposal_version = quotes.current_version(db, scope.id)

        assert pos.project_quotation_document(db, project.id) is None
        # Before any quotation exists a proposal binding is fine (AC-7 only bites afterwards).
        early = pos.create_po(
            db,
            project=project,
            actor_user_id=owner,
            payload={
                "po_number": f"{MARKER}-PO-EARLY",
                "po_source": "contractor_direct",
                "quotation_version_id": proposal_version.id,
            },
        )
        assert early.quotation_version_id == proposal_version.id

        quotation = _make(db, proposal, record, owner)
        found = pos.project_quotation_document(db, project.id)
        assert found is not None and found.id == quotation.id

        with pytest.raises(AppException) as refused:
            pos.create_po(
                db,
                project=project,
                actor_user_id=owner,
                payload={
                    "po_number": f"{MARKER}-PO-1",
                    "po_source": "contractor_direct",
                    "quotation_version_id": proposal_version.id,
                },
            )
        assert refused.value.status_code == 422
        assert refused.value.code == "po_bind_proposal_refused"

        quotation_scope = qdocs.list_scopes(db, quotation)[0]
        quotation_version = quotes.current_version(db, quotation_scope.id)
        po = pos.create_po(
            db,
            project=project,
            actor_user_id=owner,
            payload={
                "po_number": f"{MARKER}-PO-2",
                "po_source": "contractor_direct",
                "quotation_version_id": quotation_version.id,
            },
        )
        assert po.quotation_version_id == quotation_version.id
        # The existing binding was never touched.
        db.refresh(early)
        assert early.quotation_version_id == proposal_version.id


# ------------------------------------------------------------------ 8. qty over quoted (AC-8)


def _quoted(db, quoted_qty: int):
    """A project holding a quotation whose single line is quoted at ``quoted_qty``."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    company_id, owner, product, project, document, scope = _setup(db)
    _price(db, scope, product, owner, "100.00", quoted_qty)
    record = _issue(db, document, owner)
    _win(db, scope)
    quotation = _make(db, document, record, owner)
    q_scope = qdocs.list_scopes(db, quotation)[0]
    return owner, product, project, quotes.current_version(db, q_scope.id)


def _po_with_qty(db, project, owner, version, number: str, qty: int, product):
    from app.services import project_po_service as pos

    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "po_number": f"{MARKER}-{number}",
            "po_source": "contractor_direct",
            "quotation_version_id": version.id,
        },
    )
    pos.replace_lines(
        db,
        po=po,
        lines=[{"product_id": product.id, "unit_price": "100.00", "quantity": qty}],
    )
    return po


def test_8a_qty_over_the_quotation_without_a_reason_is_a_409_naming_the_products():
    from app.services import project_po_service as pos

    with blank_session() as db:
        owner, product, project, version = _quoted(db, 10)
        first = _po_with_qty(db, project, owner, version, "A", 6, product)
        pos.enforce_qty_over(db, first, reason=None, actor_user_id=owner)  # 6 of 10: fine
        second = _po_with_qty(db, project, owner, version, "B", 6, product)

        over = pos.qty_over_quotation(db, project.id)
        assert len(over) == 1
        assert over[0]["product_code"] == product.product_code
        assert Decimal(str(over[0]["ordered"])) == Decimal("12")
        assert Decimal(str(over[0]["quoted"])) == Decimal("10")

        for blank in (None, "", "   "):
            with pytest.raises(AppException) as refused:
                pos.enforce_qty_over(db, second, reason=blank, actor_user_id=owner)
            assert refused.value.status_code == 409
            assert refused.value.code == "po_qty_over_quoted"
            products = refused.value.detail["details"]["products"]
            assert len(products) == 1
            assert products[0]["product_code"] == product.product_code
        assert second.qty_over_reason is None


def test_8b_qty_over_the_quotation_with_a_reason_saves_and_stores_the_reason(monkeypatch):
    from app.services import project_notify_service
    from app.services import project_po_service as pos

    alerts = []
    monkeypatch.setattr(
        project_notify_service,
        "notify_po_qty_over",
        lambda *a, **k: alerts.append((a, k)),
        raising=False,
    )

    with blank_session() as db:
        owner, product, project, version = _quoted(db, 10)
        _po_with_qty(db, project, owner, version, "A", 6, product)
        second = _po_with_qty(db, project, owner, version, "B", 6, product)

        over = pos.enforce_qty_over(
            db, second, reason="  Client added two floors.  ", actor_user_id=owner
        )
        assert second.qty_over_reason == "Client added two floors."
        assert second.qty_over_reason_by == owner
        assert second.qty_over_reason_at is not None
        assert alerts == []  # sent by the route after its commit, never inside the save
        pos.alert_qty_over(db, second, over, owner)
        assert len(alerts) == 1  # management + owner alerted once

        # A PO that already carries a reason is not asked again.
        assert pos.enforce_qty_over(db, second, reason=None, actor_user_id=owner) == []
        assert second.qty_over_reason == "Client added two floors."
        assert len(alerts) == 1


def test_8c_superseded_po_lines_are_not_counted_towards_the_quoted_quantity():
    from app.services import project_po_service as pos

    with blank_session() as db:
        owner, product, project, version = _quoted(db, 10)
        first = _po_with_qty(db, project, owner, version, "A", 6, product)
        second = _po_with_qty(db, project, owner, version, "B", 6, product)

        first.status = "superseded"
        db.flush()

        assert pos.qty_over_quotation(db, project.id) == []
        # No reason needed and nothing raised: only the live 6 of 10 remain.
        pos.enforce_qty_over(db, second, reason=None, actor_user_id=owner)
        assert second.qty_over_reason is None


def test_2b_a_proposal_whose_earlier_revision_is_the_letter_r_keeps_lettering():
    """Revision 18 is the LETTER "R"; only "R<number>" is the legacy chain."""
    from app.services import project_quotation_document_service as qdocs

    assert qdocs.revision_letter(18) == "R"
    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        _price(db, scope, product, owner, "100.00")
        first = _issue(db, document, owner)
        first.revision_label = "R"
        db.flush()

        _reprice(db, scope, product, owner, unit_price="100.00", quantity=3)
        second = _issue(db, document, owner)
        assert second.revision_label == "B"
