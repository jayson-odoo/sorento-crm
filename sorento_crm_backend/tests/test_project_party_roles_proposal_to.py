"""PROJECT-PARTY-ROLES PR 2 (red-first): the proposal / quotation "To" is chosen from the parties,
autoloaded, and a party or contact not yet on the project is backfilled onto it.

Card: documentation/plans/project-sales/CARD-project-party-roles-10nov.md (owner addition 2,
10 Nov ~14:00, rules 15-21; answers Q5 a: the party locks once revision A is issued, Q7 a: the
address is the party's, else the project's site address). UAC AC-12..AC-16.

Postgres only, via ``blank_session``. Every name is invented.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.numbering import DocumentNumberingRule
from app.models.projects import (
    ProjectParty,
    ProjectPartyContact,
    ProjectPartyLink,
    ProjectQuotationIssue,
    ProjectSalesProfile,
    ProjectStakeholder,
)
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-pprto"
SITE_ADDRESS = "Lot 1, Mukim Kuala Kuantan\n25000 Kuantan, Pahang"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return str(db.execute(text("select id from companies where code = 'SRT'")).scalar())


def _user(db) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} Owner"))
    db.flush()
    return user_id


def _party(db, company_id, party_type, name, *, address=None, phone=None, email=None):
    row = ProjectParty(
        id=_uid(), company_id=company_id, party_type=party_type, name=f"{MARKER} {name}",
        address=address, phone=phone, email=email,
    )
    db.add(row)
    db.flush()
    return row


def _contact(db, party, name, *, phone=None, email=None):
    row = ProjectPartyContact(
        id=_uid(), company_id=party.company_id, party_id=party.id, name=name, phone=phone, email=email,
    )
    db.add(row)
    db.flush()
    return row


def _rule(db, company_id):
    rule = (
        db.query(DocumentNumberingRule)
        .filter(DocumentNumberingRule.doc_type == "project_quotation", DocumentNumberingRule.company_id == company_id)
        .first()
    )
    if rule is None:
        rule = DocumentNumberingRule(id=_uid(), doc_type="project_quotation", company_id=company_id)
        db.add(rule)
    rule.enabled = True
    rule.prefix_template = f"{MARKER}/Q/"
    rule.number_digits = 4
    rule.next_value = 1
    rule.start_value = 1
    rule.reset_policy = "none"
    rule.last_reset_key = None
    db.flush()


class World:
    pass


def _world(db, *, developer_address="Level 8, Menara Contoh\n50450 Kuala Lumpur", site_address=SITE_ADDRESS):
    from app.services.project_service import register_project

    w = World()
    w.db = db
    w.company_id = _sorento(db)
    project_seed_service.run(db, company_id=w.company_id)
    _rule(db, w.company_id)
    w.owner = _user(db)
    w.developer = _party(db, w.company_id, "developer", "PARAGON CONTOH SDN BHD", address=developer_address, phone="03-0000 0001")
    w.project = register_project(
        db, company_id=w.company_id, actor_user_id=w.owner, developer_party_id=w.developer.id,
        title=f"{MARKER} Taman Contoh {_uid()}",
    )
    profile = db.get(ProjectSalesProfile, w.project.id)
    if profile is None:
        profile = ProjectSalesProfile(project_id=w.project.id)
        db.add(profile)
    profile.address = site_address
    db.flush()
    return w


def _create(w, **payload):
    from app.services import project_quotation_document_service as qdocs

    document, _lines = qdocs.create_document_with_scopes(
        w.db, project=w.project, actor_user_id=w.owner, payload=payload
    )
    w.db.flush()
    return document


def _update(w, document, **fields):
    from app.schemas.projects import ProjectQuotationDocumentUpdate
    from app.services import project_quotation_document_service as qdocs

    body = ProjectQuotationDocumentUpdate(**fields).model_dump(exclude_unset=True)
    qdocs.update_document(w.db, document=document, payload=body)
    w.db.flush()
    w.db.refresh(document)
    return document


def _links(w):
    return {
        (l.role, l.party_id)
        for l in w.db.query(ProjectPartyLink).filter(ProjectPartyLink.project_id == w.project.id)
    }


# ------------------------------------------------------------------ AC-12: default stays the developer


def test_ac12_a_new_proposal_is_addressed_to_the_developer_by_default():
    with blank_session() as db:
        w = _world(db)
        doc = _create(w)
        assert doc.recipient_party_id == w.developer.id
        assert doc.recipient_name_snapshot == w.developer.name
        assert doc.recipient_address_snapshot == w.developer.address
        assert doc.recipient_phone_snapshot == "03-0000 0001"


def test_ac12_a_developer_without_an_address_takes_the_project_site_address():
    """Owner Q7 (a): the party's address, else the project's site address."""
    with blank_session() as db:
        w = _world(db, developer_address=None)
        doc = _create(w)
        assert doc.recipient_address_snapshot == SITE_ADDRESS


# ------------------------------------------------------------------ AC-13: choose a party on the project, autoload


def test_ac13_picking_a_party_on_the_project_autoloads_its_block():
    from app.services import project_party_contact_service as party_contacts

    with blank_session() as db:
        w = _world(db)
        mc = _party(db, w.company_id, "main_contractor", "PGB CONTOH SDN BHD", address="Level 8, Menara PGB", phone="03-1111")
        party_contacts.set_party_links(db, w.project, [{"role": "main_contractor", "party_id": mc.id}])
        doc = _create(w, recipient_party_id=mc.id)
        assert doc.recipient_party_id == mc.id
        assert doc.recipient_name_snapshot == mc.name
        assert doc.recipient_address_snapshot == "Level 8, Menara PGB"
        assert doc.recipient_phone_snapshot == "03-1111"
        assert _links(w) == {("main_contractor", mc.id)}  # nothing extra backfilled


def test_ac13_a_party_without_an_address_falls_back_to_the_site_address():
    from app.services import project_party_contact_service as party_contacts

    with blank_session() as db:
        w = _world(db)
        th = _party(db, w.company_id, "trading_house", "TRADING CONTOH")
        party_contacts.set_party_links(db, w.project, [{"role": "trading_house", "party_id": th.id}])
        doc = _create(w, recipient_party_id=th.id)
        assert doc.recipient_address_snapshot == SITE_ADDRESS


def test_ac13_typed_fields_win_over_the_autoload():
    with blank_session() as db:
        w = _world(db)
        doc = _create(w, recipient_party_id=w.developer.id, recipient_name_snapshot="PARAGON (Finance)")
        assert doc.recipient_name_snapshot == "PARAGON (Finance)"


def test_ac13_a_party_of_another_company_is_refused():
    with blank_session() as db:
        w = _world(db)
        from ._sample_request_seed import second_company

        other = second_company(db)
        foreign = _party(db, other, "main_contractor", "FOREIGN CONTOH")
        with pytest.raises(AppException) as exc:
            _create(w, recipient_party_id=foreign.id, recipient_role="main_contractor")
        assert exc.value.code == "project_ref_invalid"


# ------------------------------------------------------------------ AC-14: not on the project yet: backfilled


def test_ac14_a_party_not_on_the_project_is_backfilled_in_the_role_picked():
    with blank_session() as db:
        w = _world(db)
        pgb = _party(db, w.company_id, "main_contractor", "PGB CONTOH SDN BHD")
        doc = _create(w, recipient_party_id=pgb.id, recipient_role="main_contractor")
        assert doc.recipient_party_id == pgb.id
        assert _links(w) == {("main_contractor", pgb.id)}


def test_ac14_without_a_role_a_party_not_on_the_project_is_refused():
    with blank_session() as db:
        w = _world(db)
        pgb = _party(db, w.company_id, "main_contractor", "PGB CONTOH SDN BHD")
        with pytest.raises(AppException) as exc:
            _create(w, recipient_party_id=pgb.id)
        assert exc.value.code == "quotation_recipient_role_required"


def test_ac14_a_full_one_party_role_is_refused():
    from app.services import project_party_contact_service as party_contacts

    with blank_session() as db:
        w = _world(db)
        first = _party(db, w.company_id, "main_contractor", "FIRST CONTOH")
        party_contacts.set_party_links(db, w.project, [{"role": "main_contractor", "party_id": first.id}])
        second = _party(db, w.company_id, "main_contractor", "SECOND CONTOH")
        with pytest.raises(AppException) as exc:
            _create(w, recipient_party_id=second.id, recipient_role="main_contractor")
        assert exc.value.code == "project_party_role_single"


def test_ac14_backfill_keeps_the_links_already_there():
    from app.services import project_party_contact_service as party_contacts

    with blank_session() as db:
        w = _world(db)
        arch = _party(db, w.company_id, "architect", "ARCH CONTOH")
        party_contacts.set_party_links(db, w.project, [{"role": "architect", "party_id": arch.id}])
        th = _party(db, w.company_id, "trading_house", "TRADING CONTOH")
        _create(w, recipient_party_id=th.id, recipient_role="trading_house")
        assert _links(w) == {("architect", arch.id), ("trading_house", th.id)}


# ------------------------------------------------------------------ AC-15: Attn contacts


def test_ac15_two_attn_contacts_fill_attn_phone_email_and_become_stakeholders():
    with blank_session() as db:
        w = _world(db)
        pgb = _party(db, w.company_id, "main_contractor", "PGB CONTOH SDN BHD", phone="03-1111", email="info@pgb.example")
        anne = _contact(db, pgb, "MS. ANNE CONTOH", phone="012-0000001", email="anne@pgb.example")
        iiyana = _contact(db, pgb, "MS IIYANA CONTOH")
        doc = _create(w, recipient_party_id=pgb.id, recipient_role="main_contractor", attn_contact_ids=[anne.id, iiyana.id])
        assert doc.attn_name == "MS. ANNE CONTOH & MS IIYANA CONTOH"
        assert doc.recipient_phone_snapshot == "012-0000001"
        assert doc.recipient_email_snapshot == "anne@pgb.example"
        people = {s.party_contact_id for s in db.query(ProjectStakeholder).filter(ProjectStakeholder.project_id == w.project.id)}
        assert people == {anne.id, iiyana.id}


def test_ac15_an_attn_contact_without_a_number_leaves_the_party_number():
    with blank_session() as db:
        w = _world(db)
        pgb = _party(db, w.company_id, "main_contractor", "PGB CONTOH", phone="03-1111", email="info@pgb.example")
        iiyana = _contact(db, pgb, "MS IIYANA CONTOH")
        doc = _create(w, recipient_party_id=pgb.id, recipient_role="main_contractor", attn_contact_ids=[iiyana.id])
        assert doc.recipient_phone_snapshot == "03-1111"
        assert doc.recipient_email_snapshot == "info@pgb.example"


def test_ac15_an_attn_contact_of_another_party_is_refused():
    with blank_session() as db:
        w = _world(db)
        pgb = _party(db, w.company_id, "main_contractor", "PGB CONTOH")
        stranger = _party(db, w.company_id, "architect", "STRANGER CONTOH")
        person = _contact(db, stranger, "EN. STRANGER")
        with pytest.raises(AppException) as exc:
            _create(w, recipient_party_id=pgb.id, recipient_role="main_contractor", attn_contact_ids=[person.id])
        assert exc.value.code == "quotation_attn_not_of_party"


def test_ac15_a_typed_attn_wins_over_the_picked_names():
    with blank_session() as db:
        w = _world(db)
        anne = _contact(db, w.developer, "MS. ANNE CONTOH")
        doc = _create(w, recipient_party_id=w.developer.id, attn_contact_ids=[anne.id], attn_name="Ms Anne (Finance)")
        assert doc.attn_name == "Ms Anne (Finance)"


# ------------------------------------------------------------------ AC-16: editable, and locked on issue


def test_ac16_the_party_can_change_on_a_draft():
    with blank_session() as db:
        w = _world(db)
        doc = _create(w)
        pgb = _party(db, w.company_id, "main_contractor", "PGB CONTOH", address="Menara PGB")
        doc = _update(w, doc, recipient_party_id=pgb.id, recipient_role="main_contractor")
        assert doc.recipient_party_id == pgb.id
        assert doc.recipient_name_snapshot == pgb.name
        assert doc.recipient_address_snapshot == "Menara PGB"


def test_ac16_a_save_without_the_party_key_leaves_the_recipient_alone():
    with blank_session() as db:
        w = _world(db)
        doc = _create(w)
        doc = _update(w, doc, your_ref="REF-1")
        assert doc.recipient_party_id == w.developer.id
        assert doc.recipient_name_snapshot == w.developer.name


def test_ac16_the_party_is_fixed_once_revision_a_is_issued():
    with blank_session() as db:
        w = _world(db)
        doc = _create(w)
        db.add(ProjectQuotationIssue(id=_uid(), company_id=w.company_id, document_id=doc.id, issue_no=1))
        db.flush()
        pgb = _party(db, w.company_id, "main_contractor", "PGB CONTOH")
        with pytest.raises(AppException) as exc:
            _update(w, doc, recipient_party_id=pgb.id, recipient_role="main_contractor")
        assert exc.value.code == "quotation_recipient_locked"


def test_ac16_resending_the_same_party_after_issue_is_not_a_change():
    with blank_session() as db:
        w = _world(db)
        doc = _create(w)
        db.add(ProjectQuotationIssue(id=_uid(), company_id=w.company_id, document_id=doc.id, issue_no=1))
        db.flush()
        doc = _update(w, doc, recipient_party_id=w.developer.id, your_ref="REF-2")
        assert doc.your_ref == "REF-2"


def test_ac16_the_response_names_the_role_on_the_project():
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        w = _world(db)
        pgb = _party(db, w.company_id, "consultant", "PGB CONTOH")
        doc = _create(w, recipient_party_id=pgb.id, recipient_role="main_contractor")
        body = qdocs.serialize_document(db, doc, viewer_id=w.owner)
        assert body["recipient_role"] == "main_contractor"
        assert body["recipient_party_type"] == "consultant"


def test_n3_a_malformed_attn_contact_id_is_refused_not_a_500():
    with blank_session() as db:
        w = _world(db)
        with pytest.raises(AppException) as exc:
            _create(w, recipient_party_id=w.developer.id, attn_contact_ids=["not-a-uuid"])
        assert exc.value.status_code == 422


def test_rv_a_new_proposal_carries_the_developer_email():
    with blank_session() as db:
        w = _world(db)
        w.developer.email = "info@paragon.example"
        db.flush()
        doc = _create(w)
        assert doc.recipient_email_snapshot == "info@paragon.example"


def test_rv_a_typed_email_wins_over_the_developer_email():
    with blank_session() as db:
        w = _world(db)
        w.developer.email = "info@paragon.example"
        db.flush()
        doc = _create(w, recipient_email_snapshot="finance@paragon.example")
        assert doc.recipient_email_snapshot == "finance@paragon.example"


def test_rv_an_inactive_attn_contact_is_refused():
    with blank_session() as db:
        w = _world(db)
        gone = _contact(db, w.developer, "EN. RETIRED")
        gone.is_active = False
        db.flush()
        with pytest.raises(AppException) as exc:
            _create(w, recipient_party_id=w.developer.id, attn_contact_ids=[gone.id])
        assert exc.value.code == "quotation_attn_not_of_party"


def test_rv_clearing_the_party_on_a_draft_saves_no_party():
    with blank_session() as db:
        w = _world(db)
        doc = _create(w)
        doc = _update(w, doc, recipient_party_id=None)
        assert doc.recipient_party_id is None
        # The typed block stays: clearing the party is not blanking the letter.
        assert doc.recipient_name_snapshot == w.developer.name
