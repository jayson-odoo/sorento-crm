"""S1 of the quotation DOCUMENT layer (UAC-project-quotation-document, Groups A, B, C, D, G).

Written BEFORE the implementation. Every test here is red until the document layer exists.

Three things in this file are worth more than the rest, because each one is a silent money
bug rather than a visible failure:

- **Rate-only lines** (AC-C2). The real artifact has five of them. A system that quietly
  added them to the total would overstate a sent quotation, and nobody would notice until
  the customer paid the smaller number.
- **An issued version must be frozen** (plan grill finding 1). Today a line edit mutates
  the CURRENT version in place, and the current version is the one an issue points at - so
  editing after issuing would rewrite the very rows the PDF on file claims to contain.
  Frozen stays DERIVED, extended rather than replaced:
  ``frozen = version_no < MAX(version_no) OR an issue points at it``.
- **Per-scope outcome still derives the project outcome** (AC-A5 / AC-E10). The document
  layer sits ABOVE the scope, so nothing about the derivation may move.

Postgres only, via ``blank_session``. Every row created here carries the ``zzt-qdoc``
marker so nothing in this file can touch the real data the dev database holds.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.numbering import DocumentNumberingRule
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import ProjectParty
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-qdoc"

# Off the real workbook (Cabana Elmina - nadi cergas R2): one priced line and one rate-only
# line at the SAME quantity, so a system that wrongly counted the rate-only one lands on a
# number that is obviously wrong rather than plausibly wrong.
SAMPLE_QTY = 1046
PRICED_RATE = "250.00"
RATE_ONLY_RATE = "180.00"
CORRECT_TOTAL = Decimal("261500.00")  # 1046 x 250
WRONG_TOTAL_IF_RATE_ONLY_COUNTED = Decimal("449780.00")  # + 1046 x 180


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    """Sorento's company id as a STRING, which is the shape the app passes around.

    psycopg2 hands back a ``uuid.UUID`` for a uuid column, and every ``company_id`` the
    request path carries is a ``str`` (the mixin's column is ``UUID(as_uuid=False)``).
    Handing a UUID object down would test a shape production never produces.
    """
    return str(db.execute(text("select id from companies where code = 'SRT'")).scalar())


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _uom(db) -> str:
    row = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    db.add(row)
    db.flush()
    return row.id


def _category(db, name: str) -> ProductCategory:
    row = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} {name}",
    )
    db.add(row)
    db.flush()
    return row


def _product(db, category_id: str, uom_id: str, list_price: str, code=None) -> Product:
    row = Product(
        id=_uid(),
        product_code=code or f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} WC Suite",
        description="Close-coupled WC suite, white",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal(list_price),
    )
    db.add(row)
    db.flush()
    return row


def _party(db, company_id: str, *, address: str, phone: str, name=None) -> ProjectParty:
    row = ProjectParty(
        id=_uid(),
        company_id=company_id,
        party_type="developer",
        name=name or f"{MARKER} Nadi Cergas {_uid()[:6]}",
        address=address,
        phone=phone,
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id: str, owner: str, *, title=None, developer_party_id=None):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=developer_party_id,
        title=title or f"{MARKER} Cabana Elmina {_uid()[:6]}",
    )


def _quotation_numbering_rule(
    db, company_id: str, *, prefix: str, next_value: int
) -> DocumentNumberingRule:
    """The `project_quotation` rule AC-A0 requires, seeded rather than borrowed: CI's
    database is empty, so a test that assumed an existing rule would pass only locally.

    Upsert rather than insert because the module seed may already have created the rule,
    and `company_id` is set only when the column exists - the plan still marks the
    per-company numbering key as [DECISION NEEDED], so this asserts AC-A0 either way
    instead of hard-coding an unresolved decision.
    """
    scoped = hasattr(DocumentNumberingRule, "company_id")

    query = db.query(DocumentNumberingRule).filter(
        DocumentNumberingRule.doc_type == "project_quotation"
    )
    if scoped:
        query = query.filter(DocumentNumberingRule.company_id == company_id)
    rule = query.first()

    if rule is None:
        rule = DocumentNumberingRule(id=_uid(), doc_type="project_quotation")
        if scoped:
            rule.company_id = company_id
        db.add(rule)

    rule.enabled = True
    rule.prefix_template = prefix
    rule.number_digits = 4
    rule.next_value = next_value
    rule.start_value = next_value
    rule.reset_policy = "none"
    rule.last_reset_key = None
    db.flush()
    return rule


def _issue_scopes(db, issue_id: str):
    from app.models.projects import ProjectQuotationIssueScope

    return (
        db.query(ProjectQuotationIssueScope)
        .filter(ProjectQuotationIssueScope.issue_id == issue_id)
        .all()
    )


def _version_by_scope(db, issue_id: str) -> dict:
    return {row.quotation_id: row.version_id for row in _issue_scopes(db, issue_id)}


# ------------------------------------------------------------------ AC-C2 / AC-D3


def test_a_rate_only_line_is_quoted_but_adds_nothing_to_any_total():
    """The sample workbook carries five `rate only` lines. If any total silently counted
    them, Sorento would send a quotation stating a figure it never priced, and the error
    is invisible: every line looks correct on its own. One rule, three places it must
    hold - the scope, the document, and the frozen number on the issue the customer
    holds."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        uom = _uom(db)
        category = _category(db, "Sanitary Ware")
        product = _product(db, category.id, uom, "300.00")
        project = _project(db, company_id, owner)

        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        version = quotes.current_version(db, scope.id)

        quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={
                "product_id": product.id,
                "unit_price": PRICED_RATE,
                "quantity": SAMPLE_QTY,
            },
        )
        rate_only = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={
                "product_id": product.id,
                "unit_price": RATE_ONLY_RATE,
                "quantity": SAMPLE_QTY,
                "is_rate_only": True,
            },
        )

        # The rate is still quoted - it prints in the UNIT RATE column. Excluded from the
        # money column, not excluded from the document.
        assert rate_only.is_rate_only is True
        assert rate_only.unit_price == Decimal(RATE_ONLY_RATE)

        assert qdocs.scope_total(db, scope) == CORRECT_TOTAL
        assert qdocs.scope_total(db, scope) != WRONG_TOTAL_IF_RATE_ONLY_COUNTED
        assert qdocs.document_total(db, document) == CORRECT_TOTAL
        assert qdocs.document_total(db, document) != WRONG_TOTAL_IF_RATE_ONLY_COUNTED

        # The stored per-version total is what the grid footer reads (AC-D1), so it has to
        # agree with the service rather than being a fourth arithmetic.
        db.refresh(version)
        assert version.total_amount == CORRECT_TOTAL

        issued = qdocs.issue(db, document=document, actor_user_id=owner)
        assert issued.grand_total == CORRECT_TOTAL
        assert issued.grand_total != WRONG_TOTAL_IF_RATE_ONLY_COUNTED

        scopes = _issue_scopes(db, issued.id)
        assert len(scopes) == 1
        assert scopes[0].scope_total == CORRECT_TOTAL


# -------------------------------------------------- grill finding 1: issue freezes


def test_issuing_freezes_the_version_the_customer_now_holds():
    """A line edit mutates the CURRENT version in place, and an issue points at that same
    version - so without this rule, editing after issuing R1 rewrites the rows R1 claims to
    contain and the PDF on file stops matching the record behind it. Nothing is stamped:
    frozen stays derived, extended to `OR an issue points at it`, so the highest-numbered
    version can be frozen without a second fact that could disagree."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        uom = _uom(db)
        category = _category(db, "Sanitary Ware")
        product = _product(db, category.id, uom, "300.00")
        project = _project(db, company_id, owner)

        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        version = quotes.current_version(db, scope.id)
        quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "250.00", "quantity": 4},
        )

        assert quotes.is_frozen(db, version) is False
        issued = qdocs.issue(db, document=document, actor_user_id=owner)

        before = [
            (line.id, line.quantity, line.unit_price, line.line_total)
            for line in quotes.list_lines(db, version.id)
        ]
        assert before, "the issue points at a version with no lines"

        # Still the highest-numbered version for its scope, and frozen anyway.
        assert quotes.current_version(db, scope.id).id == version.id
        assert quotes.is_frozen(db, version) is True

        with pytest.raises(AppException) as adding:
            quotes.upsert_line(
                db,
                version=version,
                actor_user_id=owner,
                payload={"product_id": product.id, "unit_price": "180.00", "quantity": 1},
            )
        assert adding.value.status_code == 422

        # Re-read from the database rather than from the identity map, so a write that
        # half-landed before the refusal would show up here.
        db.expire_all()
        after = [
            (line.id, line.quantity, line.unit_price, line.line_total)
            for line in quotes.list_lines(db, version.id)
        ]
        assert after == before

        # The issue itself still names the same version and the same money.
        assert _version_by_scope(db, issued.id) == {scope.id: version.id}


# ------------------------------------------------------------ AC-B3 / AC-B2 / AC-E3


def test_reissuing_records_the_version_each_scope_actually_contributed():
    """A revision almost never moves every scope. If an issue only stored "the document as
    of now", answering "what exactly did we send them in February" would mean reconstructing
    it from timestamps - and the untouched scope's own history gives no signal at all. The
    issue stores the (scope, version) pairs, so an untouched scope points at the SAME version
    R1 did while the re-priced one points at the new one."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        uom = _uom(db)
        category = _category(db, "Sanitary Ware")
        product = _product(db, category.id, uom, "300.00")
        project = _project(db, company_id, owner)

        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        townhouse = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        guard_house = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Guard House", actor_user_id=owner
        )
        # Ordered, because the PDF renders the bands in this order (AC-A4).
        assert (townhouse.sort_order, guard_house.sort_order) == (0, 1)

        for scope, price in ((townhouse, "250.00"), (guard_house, "400.00")):
            quotes.upsert_line(
                db,
                version=quotes.current_version(db, scope.id),
                actor_user_id=owner,
                payload={"product_id": product.id, "unit_price": price, "quantity": 2},
            )

        document.cover_letter_html = f"<p>{MARKER} first letter</p>"
        document.terms_html = f"<p>{MARKER} first terms</p>"
        db.flush()

        r1 = qdocs.issue(db, document=document, actor_user_id=owner)
        r1_pairs = _version_by_scope(db, r1.id)
        townhouse_v1 = r1_pairs[townhouse.id]
        guard_house_v1 = r1_pairs[guard_house.id]

        # Only the townhouse is re-priced.
        townhouse_v2 = quotes.revise(db, quotation=townhouse, actor_user_id=owner)
        quotes.upsert_line(
            db,
            version=townhouse_v2,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "230.00", "quantity": 2},
        )

        document.cover_letter_html = f"<p>{MARKER} revised letter</p>"
        db.flush()
        r2 = qdocs.issue(db, document=document, actor_user_id=owner)

        assert (r1.issue_no, r2.issue_no) == (1, 2)
        r2_pairs = _version_by_scope(db, r2.id)
        assert r2_pairs[townhouse.id] == townhouse_v2.id
        assert r2_pairs[townhouse.id] != townhouse_v1
        assert r2_pairs[guard_house.id] == guard_house_v1

        # AC-E3: the letter is snapshotted onto the issue, so R1 still reads as it was sent
        # even though the document's own copy has moved on.
        assert r1.cover_letter_rendered == f"<p>{MARKER} first letter</p>"
        assert r2.cover_letter_rendered == f"<p>{MARKER} revised letter</p>"
        assert r1.terms_rendered == f"<p>{MARKER} first terms</p>"


def test_two_issues_of_one_document_can_never_share_a_revision_number():
    """`Our Ref ... (R2)` is what the customer quotes back at us on the phone. If two rows
    could both claim R2 the reference stops identifying anything, so the rule is enforced by
    the database and not only by the service that increments it."""
    from app.models.projects import ProjectQuotationIssue
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )

        first = qdocs.issue(db, document=document, actor_user_id=owner)
        second = qdocs.issue(db, document=document, actor_user_id=owner)
        assert (first.issue_no, second.issue_no) == (1, 2)

        db.add(
            ProjectQuotationIssue(
                id=_uid(),
                company_id=company_id,
                document_id=document.id,
                issue_no=1,
                our_ref_text=f"{document.document_no} (R1)",
                issued_by=owner,
                cover_letter_rendered=None,
                terms_rendered=None,
                grand_total=Decimal("0.00"),
            )
        )
        with pytest.raises(IntegrityError) as clash:
            db.flush()
        # 23505 = unique_violation. Pinned so a missing NOT NULL column cannot make this
        # test pass for the wrong reason: that is also an IntegrityError.
        assert getattr(clash.value.orig, "pgcode", None) == "23505"
        db.rollback()


# ------------------------------------------------------------------------- AC-A0


def test_the_document_reference_is_drawn_from_the_numbering_rule():
    """`Our Ref` is a customer-facing running number. Deriving it from the project code
    would give two documents for one project the same reference, and free text would let two
    salespeople type the same one; both are only discovered after the number is on paper. The
    same `document_numbering_rules` machinery purchase requests already use, so an admin
    changes the prefix in Setup without a deploy."""
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/{{year}}/", next_value=141)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        first = qdocs.create_document(db, project=project, actor_user_id=owner)
        second = qdocs.create_document(db, project=project, actor_user_id=owner)

        year = date.today().year
        assert first.document_no == f"{MARKER}/Q/{year}/0141"
        assert second.document_no == f"{MARKER}/Q/{year}/0142"
        assert first.document_no != second.document_no


# ------------------------------------------------------------------------- AC-A3


def test_the_recipient_block_is_snapshotted_so_a_later_address_edit_cannot_rewrite_it():
    """A party moves office and someone updates the address. Every quotation ever sent to
    them must still show the address it was actually posted to, exactly as a line snapshots
    the product it was priced from. Reading the party live would silently rewrite last
    year's documents, and the reader has no way to tell."""
    from app.models.projects import ProjectQuotationDocument
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        party = _party(
            db,
            company_id,
            address=f"{MARKER} Level 8, Menara Lama, Kuala Lumpur",
            phone="03-1111 1111",
        )
        project = _project(db, company_id, owner, developer_party_id=party.id)

        document = qdocs.create_document(db, project=project, actor_user_id=owner)

        assert document.recipient_party_id == party.id
        assert document.recipient_name_snapshot == party.name
        assert document.recipient_address_snapshot == f"{MARKER} Level 8, Menara Lama, Kuala Lumpur"
        assert document.recipient_phone_snapshot == "03-1111 1111"
        # AC-A2: the subject comes off the project rather than being asked for.
        assert document.subject_title == project.title
        assert document.doc_date == date.today()

        party.address = f"{MARKER} Level 22, Menara Baru, Petaling Jaya"
        party.phone = "03-9999 9999"
        db.flush()
        db.expire_all()

        # Straight off the table rather than through a service getter: the assertion is
        # about what is STORED, so a getter that helpfully re-derived the block would hide
        # exactly the bug this test exists to catch.
        reloaded = (
            db.query(ProjectQuotationDocument)
            .filter(ProjectQuotationDocument.id == document.id)
            .first()
        )
        assert reloaded is not None
        assert reloaded.recipient_address_snapshot == (
            f"{MARKER} Level 8, Menara Lama, Kuala Lumpur"
        )
        assert reloaded.recipient_phone_snapshot == "03-1111 1111"


# ------------------------------------------------------------------------- AC-C1 / AC-C3


def test_a_line_carries_the_columns_the_real_quotation_actually_prints():
    """The sample's column set is not the CRM's. Without `item_label` the A / B / C grouping
    that ties a WC to its angle valve and hose is lost; without `band_label` the customer's
    own BQ headings (`BILL NO 3 PAGE 15/4`, `OPTIONAL ITEMS FOR OKU TOILET`) cannot be
    reproduced, and a QS reading the PDF cannot line it up against their bill. The band is a
    marker ON the line so it can never orphan itself from the lines it heads."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        uom = _uom(db)
        category = _category(db, "Sanitary Ware")
        product = _product(db, category.id, uom, "300.00")
        project = _project(db, company_id, owner)

        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        line = quotes.upsert_line(
            db,
            version=quotes.current_version(db, scope.id),
            actor_user_id=owner,
            payload={
                "product_id": product.id,
                "unit_price": "250.00",
                "quantity": 2,
                "item_label": "A",
                "brand_snapshot": "SORENTO",
                "technical_spec": "S-trap 225mm, 3/6L dual flush",
                "complete_set": "c/w seat cover and angle valve",
                "band_label": "BILL NO 3 PAGE 15/4",
            },
        )

        db.expire_all()
        stored = quotes.list_lines(db, line.version_id)[0]
        assert stored.item_label == "A"
        assert stored.brand_snapshot == "SORENTO"
        assert stored.technical_spec == "S-trap 225mm, 3/6L dual flush"
        assert stored.complete_set == "c/w seat cover and angle valve"
        assert stored.band_label == "BILL NO 3 PAGE 15/4"
        assert stored.is_rate_only is False


# ------------------------------------------------------------------------- AC-A5


def test_the_document_layer_does_not_disturb_the_derived_project_outcome():
    """This is the regression that matters most: the document was added ABOVE the scope
    precisely so that winning the townhouse stays a fact about the townhouse and not about a
    revision. A project with one decided scope and one still open is not decided, and one win
    beside one loss is still a win - the pipeline's rule (AC-E10), unchanged, now reached
    through a document."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        townhouse = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        guard_house = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Guard House", actor_user_id=owner
        )

        assert quotes.derive_project_outcome(db, project) == "open"

        # One scope lost, the other still open: the project is still live.
        quotes.set_outcome(db, quotation=townhouse, outcome="lost", loss_reason="price")
        assert quotes.derive_project_outcome(db, project) == "open"
        db.refresh(project)
        assert project.outcome == "open"

        # A won scope beside a lost one is a won project (AC-E10, any-won wins).
        quotes.set_outcome(db, quotation=guard_house, outcome="won", loss_reason=None)
        assert quotes.derive_project_outcome(db, project) == "won"
        db.refresh(project)
        assert project.outcome == "won"


# ------------------------------------------------------------------------- AC-A6


def test_a_document_the_customer_has_been_sent_cannot_be_deleted():
    """Deleting an issued document would delete the record of what a customer is holding in
    their inbox, and the refusal has to be visible rather than a silent hide - a salesperson
    who thinks it is gone will re-quote the same scope. A draft nobody has seen is different:
    it deletes, and takes its scopes with it, because a scope has no meaning without the
    document that carries it."""
    from app.models.projects import (
        ProjectQuotation,
        ProjectQuotationDocument,
        ProjectQuotationVersion,
    )
    from app.services import project_quotation_document_service as qdocs

    def _document_rows(db, document_id):
        return (
            db.query(ProjectQuotationDocument)
            .filter(ProjectQuotationDocument.id == document_id)
            .count()
        )

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        issued_doc = qdocs.create_document(db, project=project, actor_user_id=owner)
        qdocs.add_scope(
            db, document=issued_doc, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        qdocs.issue(db, document=issued_doc, actor_user_id=owner)

        with pytest.raises(AppException) as refused:
            qdocs.delete_document(db, issued_doc)
        assert refused.value.status_code == 422

        db.expire_all()
        assert _document_rows(db, issued_doc.id) == 1, "the refusal deleted it anyway"

        draft = qdocs.create_document(db, project=project, actor_user_id=owner)
        scope = qdocs.add_scope(
            db, document=draft, scope_label=f"{MARKER} Reception", actor_user_id=owner
        )
        scope_id = scope.id
        draft_id = draft.id

        qdocs.delete_document(db, draft)
        db.expire_all()

        assert (
            db.query(ProjectQuotation).filter(ProjectQuotation.id == scope_id).first() is None
        )
        assert (
            db.query(ProjectQuotationVersion)
            .filter(ProjectQuotationVersion.quotation_id == scope_id)
            .count()
            == 0
        )
        assert _document_rows(db, draft_id) == 0


# ------------------------------------------------------------------------- AC-G3


def test_every_new_table_is_company_scoped_and_stamped_on_insert():
    """SRT and MOCHA quote the same developers. A new table without `company_id` is a leak
    that no screen shows until one company reads the other's prices, so the column is asserted
    on the table AND the stamp is asserted on a real inserted row - a declared column that
    nothing populates is the same leak with extra steps."""
    from app.models.projects import (
        ProjectQuotationDocument,
        ProjectQuotationIssue,
        ProjectQuotationIssueScope,
    )
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _quotation_numbering_rule(db, company_id, prefix=f"{MARKER}/Q/", next_value=1)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        for model in (
            ProjectQuotationDocument,
            ProjectQuotationIssue,
            ProjectQuotationIssueScope,
        ):
            columns = {c.name for c in model.__table__.columns}
            assert "company_id" in columns, f"{model.__tablename__} is not company scoped"

        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        issued = qdocs.issue(db, document=document, actor_user_id=owner)

        assert document.company_id == company_id
        assert scope.company_id == company_id
        assert issued.company_id == company_id
        rows = _issue_scopes(db, issued.id)
        assert rows and all(row.company_id == company_id for row in rows)
