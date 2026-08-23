"""S4 cover letter and terms templates (UAC-project-quotation-document, Group E).

Written BEFORE the implementation. Every test here is red until
``app/services/project_quotation_template_service.py`` and the ``quotation_templates`` table
exist.

Three of these are worth more than the rest, because each one is a customer-facing text bug
rather than a visible failure:

- **One active template per (company, kind)** (AC-E1). "The active template" has to identify
  exactly one row. The `system_settings` singleton is the cautionary tale in this repo: a
  singleton nothing enforced became two rows, and reads went non-deterministic while every
  screen still returned 200. So the rule is asserted through the service AND against a raw
  insert that races the flag past it.
- **Editing the template must not rewrite a document that already exists** (AC-E2). The
  document's letter is its OWN copy, rendered once at create. Reading the template live would
  silently rewrite every draft, and a quotation already ISSUED would stop matching the PDF in
  the customer's inbox.
- **An unknown merge token is refused on SAVE** (AC-E4 / plan scope note). A token nobody
  declared cannot be rendered, and the alternative to refusing is a blank hole in a letter
  going out on Sorento letterhead. Refusing at save time is the only moment a human is still
  looking.

Postgres only, via ``blank_session``. Every row created here carries the ``zzt-qtmpl`` marker,
so nothing in this file can touch the real data the dev database holds.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.company import Company
from app.models.numbering import DocumentNumberingRule
from app.models.projects import ProjectParty
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-qtmpl"

COVER_LETTER = "cover_letter"
TERMS = "terms"

# Every token the letter in this file uses, so a registry that quietly dropped one would fail
# here rather than in front of a customer.
SAMPLE_BODY = (
    "<p>Attn: {{attn_name}}</p>"
    "<p>Dear Sir/Madam, we refer to {{project_title}} for {{developer_name}}.</p>"
    "<p>Our Ref: {{our_ref}} &middot; {{doc_date}} &middot; {{subject_title}}</p>"
    "<p>To: {{recipient_name}}</p>"
    "<p>Total: RM {{grand_total}}</p>"
    "<p>Yours faithfully, {{salesperson_name}} &middot; {{company_name}}</p>"
)


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    """Sorento's company id as a STRING, which is the shape the app passes around."""
    return str(db.execute(text("select id from companies where code = 'SRT'")).scalar())


def _second_company(db) -> str:
    """A second company, because AC-E1 is a per-company rule and one company cannot prove it."""
    row = Company(
        id=_uid(), name=f"{MARKER} Zenith {_uid()[:6]}", code=f"ZQT{_uid()[:5]}", is_active=True
    )
    db.add(row)
    db.flush()
    return row.id


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _party(db, company_id: str, name: str) -> ProjectParty:
    row = ProjectParty(
        id=_uid(),
        company_id=company_id,
        party_type="developer",
        name=f"{MARKER} {name} {_uid()[:6]}",
        address=f"{MARKER} Level 8, Menara Lama, Kuala Lumpur",
        phone="03-1111 1111",
    )
    db.add(row)
    db.flush()
    return row


def _numbering_rule(db, company_id: str) -> DocumentNumberingRule:
    """Seeded rather than borrowed: CI's database has no seed data, so a test that assumed an
    existing `project_quotation` rule would pass only on a developer's machine."""
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
    rule.prefix_template = f"{MARKER}/Q/"
    rule.number_digits = 4
    rule.next_value = 1
    rule.start_value = 1
    rule.reset_policy = "none"
    rule.last_reset_key = None
    db.flush()
    return rule


def _project(db, company_id: str, owner: str, *, developer_party_id=None):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=developer_party_id,
        title=f"{MARKER} Cabana Elmina {_uid()[:12]}",
    )


def _sign(db, document, owner):
    """AC-H1: an unsigned quotation cannot be issued, so issuing here means signing first."""
    from app.services import project_quotation_document_service as qdocs

    return qdocs.sign_as_sorento(
        db,
        document=document,
        actor_user_id=owner,
        payload={
            "signer_name": f"{MARKER} Baser",
            "mode": "draw",
            "image_data_uri": "data:image/png;base64,zzt",
        },
    )


# ----------------------------------------------------------------------- AC-E1


def test_only_one_template_of_a_kind_can_be_active_for_a_company():
    """"The active template" has to identify exactly one row.

    With two active rows, `active_template()` returns whichever the planner happens to hand
    back first, so the same document created twice can carry different letters and nothing
    reports an error. This is the `system_settings` failure exactly: a singleton nothing
    enforced became two rows and reads went non-deterministic.

    Activating the second one has to DEACTIVATE the first, rather than refusing: an admin
    rewriting the company letter should not have to remember to switch the old one off.
    """
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)

        first = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Standard letter",
                "body_html": "<p>First</p>",
            },
        )
        # The FIRST template of a kind is active on arrival: a company with a template but
        # nothing active would render an empty letter and look like a missing feature.
        assert first.is_active is True

        second = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} 2026 letter",
                "body_html": "<p>Second</p>",
                "is_active": True,
            },
        )
        db.expire_all()

        assert second.is_active is True
        assert first.is_active is False
        assert templates.active_template(db, company_id=company_id, kind=COVER_LETTER).id == (
            second.id
        )

        # A kind is its own slot: a terms template does not compete with a cover letter.
        terms = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": TERMS,
                "name": f"{MARKER} Standard terms",
                "body_html": "<p>1. Prices are valid for 30 days.</p>",
            },
        )
        db.expire_all()
        assert terms.is_active is True
        assert templates.active_template(db, company_id=company_id, kind=COVER_LETTER).id == (
            second.id
        )


def test_a_second_active_row_is_refused_by_the_database_not_only_by_the_service():
    """The service deactivates the incumbent before activating the new one. That is one
    ordered pair of writes, so two concurrent activations can interleave and both land - and
    a Python-only rule cannot see it happen. The partial unique index is the backstop, which
    is the whole lesson of the `system_settings` duplicate rows."""
    from app.models.projects import QuotationTemplate
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)
        templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Standard letter",
                "body_html": "<p>First</p>",
            },
        )

        # Straight onto the table, bypassing the service exactly as a racing request would.
        db.add(
            QuotationTemplate(
                id=_uid(),
                company_id=company_id,
                kind=COVER_LETTER,
                name=f"{MARKER} Racing letter",
                body_html="<p>Second</p>",
                is_active=True,
            )
        )
        with pytest.raises(IntegrityError) as clash:
            db.flush()
        # 23505 = unique_violation. Pinned so a missing NOT NULL column cannot make this test
        # pass for the wrong reason: that is also an IntegrityError.
        assert getattr(clash.value.orig, "pgcode", None) == "23505"
        db.rollback()


def test_two_companies_keep_their_own_active_template_and_never_see_each_others():
    """SRT and Zenith send different letters on different letterheads.

    The scope is deliberately opened to ALL companies for this test, so what isolates the two
    is the service's own `company_id` filter rather than the ambient request scope. A service
    that leaned on the scope listener would pass under a single-company session and leak the
    moment anything ran with a wider scope (the MCP principal, a worker, an admin listing).
    """
    from app.models.base import company_scope
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        srt = _sorento(db)
        zenith = _second_company(db)

        with company_scope(db, None):
            srt_letter = templates.create_template(
                db,
                company_id=srt,
                payload={
                    "kind": COVER_LETTER,
                    "name": f"{MARKER} SRT letter",
                    "body_html": "<p>{{company_name}} of Sorento</p>",
                },
            )
            zenith_letter = templates.create_template(
                db,
                company_id=zenith,
                payload={
                    "kind": COVER_LETTER,
                    "name": f"{MARKER} Zenith letter",
                    "body_html": "<p>{{company_name}} of Zenith</p>",
                },
            )
            db.expire_all()

            # Both active at once, because they are different companies.
            assert srt_letter.is_active is True
            assert zenith_letter.is_active is True

            assert templates.active_template(db, company_id=srt, kind=COVER_LETTER).id == (
                srt_letter.id
            )
            assert templates.active_template(db, company_id=zenith, kind=COVER_LETTER).id == (
                zenith_letter.id
            )

            srt_ids = {row.id for row in templates.list_templates(db, company_id=srt)}
            zenith_ids = {row.id for row in templates.list_templates(db, company_id=zenith)}
            assert srt_letter.id in srt_ids and zenith_letter.id not in srt_ids
            assert zenith_letter.id in zenith_ids and srt_letter.id not in zenith_ids


# ----------------------------------------------------------------------- AC-E2


def test_creating_a_document_renders_the_active_template_into_its_own_copy():
    """Journey step 5: the letter is already written when the salesperson gets there.

    Rendered ONCE, into a column on the document, with every merge field substituted. A
    document that stored a template id and rendered at print time would look identical on
    screen and then change under the salesperson the next time an admin edited the template.
    """
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _numbering_rule(db, company_id)
        owner = _user(db, f"{MARKER} Baser Ramli")
        party = _party(db, company_id, "Nadi Cergas")
        project = _project(db, company_id, owner, developer_party_id=party.id)

        templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Standard letter",
                "body_html": SAMPLE_BODY,
            },
        )
        templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": TERMS,
                "name": f"{MARKER} Standard terms",
                "body_html": "<p>1. Prices valid 30 days for {{project_title}}.</p>",
            },
        )

        document = qdocs.create_document(
            db,
            project=project,
            actor_user_id=owner,
            payload={"attn_name": "Kelly"},
        )
        letter = document.cover_letter_html or ""

        # Nothing unsubstituted reaches the salesperson: a raw {{token}} in a letter on
        # Sorento letterhead is the failure this whole registry exists to prevent.
        assert "{{" not in letter
        assert "Kelly" in letter
        assert project.title in letter
        assert party.name in letter
        assert document.document_no in letter
        assert f"{MARKER} Baser Ramli" in letter
        assert "Sorento" in letter

        assert document.terms_html is not None
        assert "{{" not in document.terms_html
        assert project.title in document.terms_html


def test_a_template_with_no_merge_fields_at_all_still_renders():
    """The commonest real template is prose with no tokens in it. A renderer that required a
    token, or that mangled untokenised HTML, would fail on the simplest possible input."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_template_service as templates

    plain = "<p>Thank you for the opportunity to quote. We look forward to your reply.</p>"

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _numbering_rule(db, company_id)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        templates.create_template(
            db,
            company_id=company_id,
            payload={"kind": COVER_LETTER, "name": f"{MARKER} Plain", "body_html": plain},
        )
        document = qdocs.create_document(db, project=project, actor_user_id=owner)

        assert document.cover_letter_html == plain
        # And no terms template configured is not an error: the section is simply empty.
        assert document.terms_html in (None, "")


def test_editing_the_template_afterwards_leaves_an_existing_document_untouched():
    """THE promise of AC-E2, and the one most likely to break.

    An admin rewrites the company letter in March. Every quotation drafted in February must
    still read as it did, and one already ISSUED must still match the PDF the customer is
    holding - so the issue's snapshot has to carry the text rendered at CREATE, not a
    re-render taken at issue time.
    """
    from app.models.projects import ProjectQuotationDocument
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _numbering_rule(db, company_id)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        template = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Standard letter",
                "body_html": f"<p>{MARKER} FIRST wording for {{{{project_title}}}}</p>",
            },
        )
        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        rendered_at_create = document.cover_letter_html
        assert f"{MARKER} FIRST wording" in (rendered_at_create or "")

        templates.update_template(
            db,
            template=template,
            payload={"body_html": f"<p>{MARKER} SECOND wording for {{{{project_title}}}}</p>"},
        )
        db.flush()
        db.expire_all()

        # Read straight off the table rather than through a getter: the assertion is about what
        # is STORED, so a getter that helpfully re-rendered would hide the bug.
        stored = (
            db.query(ProjectQuotationDocument)
            .filter(ProjectQuotationDocument.id == document.id)
            .first()
        )
        assert stored is not None
        assert stored.cover_letter_html == rendered_at_create
        assert f"{MARKER} SECOND wording" not in (stored.cover_letter_html or "")

        # AC-E3: the issue snapshots the RENDERED letter, and it is the create-time text.
        qdocs.add_scope(
            db, document=stored, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        _sign(db, stored, owner)
        issued = qdocs.issue(db, document=stored, actor_user_id=owner)
        assert issued.cover_letter_rendered == rendered_at_create

        # And a NEW document, created after the edit, gets the new wording. Otherwise this
        # test would pass against a create path that ignored templates entirely.
        later = qdocs.create_document(db, project=project, actor_user_id=owner)
        assert f"{MARKER} SECOND wording" in (later.cover_letter_html or "")


def test_a_document_created_with_its_own_letter_is_not_overwritten_by_the_template():
    """A caller that supplies the letter has already decided. Rendering over it would discard
    what a person typed, which is worse than not rendering at all."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _numbering_rule(db, company_id)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Standard letter",
                "body_html": "<p>From the template</p>",
            },
        )
        document = qdocs.create_document(
            db,
            project=project,
            actor_user_id=owner,
            payload={"cover_letter_html": f"<p>{MARKER} typed by hand</p>"},
        )
        assert document.cover_letter_html == f"<p>{MARKER} typed by hand</p>"


# ----------------------------------------------------------------------- AC-E4


def test_an_unknown_merge_token_is_refused_when_the_template_is_saved():
    """Rendering an undeclared token can only produce a hole in the letter or the raw
    `{{token}}` itself, and both go out on letterhead. Save time is the last moment a human
    is looking at it, so the refusal happens there and NAMES the tokens - an admin who mistyped
    `{{grand_totals}}` cannot find it in a page of HTML otherwise."""
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)

        with pytest.raises(AppException) as refused:
            templates.create_template(
                db,
                company_id=company_id,
                payload={
                    "kind": COVER_LETTER,
                    "name": f"{MARKER} Typo letter",
                    "body_html": "<p>{{grand_totals}} for {{projekt_title}} {{project_title}}</p>",
                },
            )
        assert refused.value.status_code == 422
        message = refused.value.detail["message"]
        assert "grand_totals" in message
        assert "projekt_title" in message
        # The valid token is not reported as a problem.
        assert "{{project_title}}" not in message

        # The same refusal on UPDATE: a template saved clean once must not become dirty later.
        good = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Good letter",
                "body_html": "<p>{{project_title}}</p>",
            },
        )
        with pytest.raises(AppException) as on_update:
            templates.update_template(
                db, template=good, payload={"body_html": "<p>{{no_such_field}}</p>"}
            )
        assert on_update.value.status_code == 422
        assert "no_such_field" in on_update.value.detail["message"]

        db.expire_all()
        assert good.body_html == "<p>{{project_title}}</p>", "the refused body was saved anyway"


def test_every_declared_merge_field_actually_renders():
    """The registry is the single source of truth the FE picker and the renderer share. A token
    the picker offers but the renderer does not know would insert a hole into a letter, and it
    would look like an FE bug. So the two are proven to agree here: every declared token is
    substituted, none is left behind."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _numbering_rule(db, company_id)
        owner = _user(db, f"{MARKER} Baser")
        party = _party(db, company_id, "Nadi Cergas")
        project = _project(db, company_id, owner, developer_party_id=party.id)

        declared = templates.serialize_merge_fields()
        assert declared, "the registry is empty, so the picker would have nothing to offer"
        for field in declared:
            assert field["token"]
            assert field["label"], f"{field['token']} has no human label"
            assert field["example"], f"{field['token']} has no example value"
            assert field["placeholder"] == "{{" + field["token"] + "}}"

        body = " ".join(f"[{field['token']}={field['placeholder']}]" for field in declared)
        templates.create_template(
            db,
            company_id=company_id,
            payload={"kind": COVER_LETTER, "name": f"{MARKER} All fields", "body_html": body},
        )
        document = qdocs.create_document(
            db, project=project, actor_user_id=owner, payload={"attn_name": "Kelly"}
        )

        letter = document.cover_letter_html or ""
        assert "{{" not in letter and "}}" not in letter

        # Every declared token resolves to something on a document that HAS every fact: a token
        # declared with nothing behind it renders as an invisible gap, which is exactly the drift
        # this registry exists to prevent and exactly the kind of hole a reader never spots.
        context = templates.build_document_context(db, document=document)
        for field in declared:
            token = field["token"]
            assert token in context, f"{token} is offered by the picker but never filled"
            assert str(context[token] or "").strip(), f"{token} rendered as nothing"
            assert f"[{token}={context[token]}]" in letter


def test_the_grand_total_renders_as_money_not_as_a_decimal_repr():
    """A letter reading "RM 261500.00" is not what Sorento sends, and `Decimal('261500.00')`
    reaching the page is the failure mode when a total is interpolated without formatting."""
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes
    from app.services import project_quotation_template_service as templates
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        _numbering_rule(db, company_id)
        owner = _user(db, f"{MARKER} Baser")
        project = _project(db, company_id, owner)

        uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
        category = ProductCategory(
            id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} Sanitary"
        )
        db.add_all([uom, category])
        db.flush()
        product = Product(
            id=_uid(),
            product_code=f"ZZT-{_uid()[:8]}",
            product_name=f"{MARKER} WC Suite",
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal("300.00"),
        )
        db.add(product)
        db.flush()

        templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Money letter",
                "body_html": "<p>RM {{grand_total}}</p>",
            },
        )

        document = qdocs.create_document(db, project=project, actor_user_id=owner)
        scope = qdocs.add_scope(
            db, document=document, scope_label=f"{MARKER} Townhouse", actor_user_id=owner
        )
        quotes.upsert_line(
            db,
            version=quotes.current_version(db, scope.id),
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "250.00", "quantity": 1046},
        )

        # Rendered from a document whose scopes are already priced, which is what the FE's
        # re-render will do once the salesperson has finished pricing.
        rendered = templates.render_for_document(db, document=document, kind=COVER_LETTER)
        assert rendered == "<p>RM 261,500.00</p>"
        assert "Decimal" not in rendered


# ------------------------------------------------------------------ delete rules


def test_the_active_template_cannot_be_deleted_out_from_under_a_company():
    """Deleting the active template leaves the company with no letter, and the next document
    created is silently blank - nothing errors, the section is just empty. So the refusal names
    the fix (activate another one first). An inactive template is history and deletes cleanly."""
    from app.models.projects import QuotationTemplate
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)

        first = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Old letter",
                "body_html": "<p>Old</p>",
            },
        )
        second = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} New letter",
                "body_html": "<p>New</p>",
                "is_active": True,
            },
        )
        db.expire_all()

        with pytest.raises(AppException) as refused:
            templates.delete_template(db, template=second)
        assert refused.value.status_code == 422

        db.expire_all()
        assert (
            db.query(QuotationTemplate).filter(QuotationTemplate.id == second.id).count() == 1
        ), "the refusal deleted it anyway"

        # The superseded one carries nothing the company depends on.
        templates.delete_template(db, template=first)
        db.expire_all()
        assert db.query(QuotationTemplate).filter(QuotationTemplate.id == first.id).count() == 0

        # Activating the old one back is how the active one becomes deletable.
        restored = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Restored letter",
                "body_html": "<p>Restored</p>",
                "is_active": True,
            },
        )
        db.expire_all()
        assert restored.is_active is True
        templates.delete_template(db, template=second)
        db.expire_all()
        assert db.query(QuotationTemplate).filter(QuotationTemplate.id == second.id).count() == 0


def test_the_template_table_is_company_scoped_and_stamped_on_insert():
    """AC-G3. A new table without `company_id` is a leak no screen shows until one company
    reads the other's letterhead, so the column is asserted on the table AND the stamp is
    asserted on a real inserted row: a declared column nothing populates is the same leak with
    extra steps."""
    from app.models.base import CompanyScopedMixin
    from app.models.projects import QuotationTemplate
    from app.services import project_quotation_template_service as templates

    assert issubclass(QuotationTemplate, CompanyScopedMixin)
    assert "company_id" in {c.name for c in QuotationTemplate.__table__.columns}

    with blank_session() as db:
        company_id = _sorento(db)
        row = templates.create_template(
            db,
            company_id=company_id,
            payload={
                "kind": COVER_LETTER,
                "name": f"{MARKER} Scoped letter",
                "body_html": "<p>Scoped</p>",
            },
        )
        assert row.company_id == company_id


def test_an_unknown_kind_is_refused():
    """`kind` is a two-value slot, not free text: a third value would create a template nothing
    ever renders, and it would look configured."""
    from app.services import project_quotation_template_service as templates

    with blank_session() as db:
        company_id = _sorento(db)
        with pytest.raises(AppException) as refused:
            templates.create_template(
                db,
                company_id=company_id,
                payload={
                    "kind": "invoice_footer",
                    "name": f"{MARKER} Wrong kind",
                    "body_html": "<p>x</p>",
                },
            )
        assert refused.value.status_code == 422
        assert "invoice_footer" in refused.value.detail["message"]
