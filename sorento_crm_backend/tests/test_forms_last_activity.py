"""FORMS-LAST-ACTIVITY Phase 2 red tests: stamping of ``last_activity_at`` (U2-U6, U5b).

UAC: documentation/plans/forms/forms-last-activity-acceptance-criteria.md. Stamping happens in the
audit capture (person actors: user, contact, public_link) and in the form comment path. Every
assertion reads ``last_activity_at``, which does not exist yet, so each test fails on the missing
column / attribute.

Run: SORENTO_ENV_FILE=.env.ci-tests venv/bin/pytest tests/test_forms_last_activity.py -q
"""
from __future__ import annotations

import pytest
from sqlalchemy import update

from tests._last_activity_support import (
    BY_KEY, FORMS, IDS, OLD, SORENTO, at, newest_audit, non_person, person, seed_contact, seed_user,
    set_stamp, stamp, uid,
)
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    from app.models.base import set_company_scope

    with blank_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.queue_service.enqueue_job", lambda *a, **k: calls.append((a, k)))
    return calls


# --------------------------------------------------------------------------- U2 create
@pytest.mark.parametrize("form", FORMS, ids=IDS)
def test_u2_create_by_a_person_stamps_the_create_time(db, form):
    user = seed_user(db)
    with person(db, user):
        row = form.seed(db)
    value = stamp(db, row)
    assert value is not None, "U2: a new record must carry last_activity_at"
    db.refresh(row)
    assert abs((value - row.created_at).total_seconds()) < 60


@pytest.mark.parametrize("form", FORMS, ids=IDS)
def test_u2_create_by_a_system_path_is_never_null(db, form):
    with non_person(db, "worker"):
        row = form.seed(db)
    assert stamp(db, row) is not None, "U2: a system-path create is also stamped"


# --------------------------------------------------------------------------- U3 person edits
@pytest.mark.parametrize("form", FORMS, ids=IDS)
def test_u3_person_header_edit_moves_the_stamp_to_the_audit_row_time(db, form):
    user = seed_user(db)
    row = form.seed(db)
    set_stamp(db, row, OLD)
    field, value = form.edit
    with person(db, user):
        setattr(row, field, value)
        db.commit()
    audit = newest_audit(db, row)
    assert audit is not None, "precondition: the edit wrote a person audit row"
    assert stamp(db, row) == audit.changed_at


def test_u3_person_status_change_moves_the_stamp(db):
    user = seed_user(db)
    row = BY_KEY["stock_inquiry"].seed(db)
    set_stamp(db, row, OLD)
    with person(db, user):
        row.status = "responded"
        db.commit()
    audit = newest_audit(db, row)
    assert audit is not None
    assert stamp(db, row) == audit.changed_at


def test_u3_line_edit_and_line_add_roll_up_to_the_header(db):
    from app.models.procurement import PurchaseRequestLine

    user = seed_user(db)
    header = BY_KEY["purchase_request"].seed(db)
    line = PurchaseRequestLine(id=uid(), purchase_request_id=header.id, item_code="ZZT-FLA-I1", quantity=1)
    db.add(line)
    db.commit()
    set_stamp(db, header, OLD)
    with person(db, user):
        line.remark = "edited line"
        db.commit()
    first = stamp(db, header)
    assert first is not None and first > OLD, "a line edit is rolled up by __audit_parent__"
    set_stamp(db, header, OLD)
    with person(db, user):
        db.add(PurchaseRequestLine(id=uid(), purchase_request_id=header.id, item_code="ZZT-FLA-I2", quantity=2))
        db.commit()
    assert stamp(db, header) > OLD, "a line add moves the header stamp"


# --------------------------------------------------------------------------- U4 non-person
@pytest.mark.parametrize("actor_type", ["worker", "scheduler", "system", "integration", "none"])
@pytest.mark.parametrize("form", FORMS, ids=IDS)
def test_u4_non_person_change_does_not_move_the_stamp(db, form, actor_type):
    row = form.seed(db)
    set_stamp(db, row, at(days=3))
    field, value = form.edit
    if actor_type == "none":
        setattr(row, field, value)
        db.commit()
    else:
        with non_person(db, actor_type):
            setattr(row, field, value)
            db.commit()
    assert stamp(db, row) == at(days=3)


# --------------------------------------------------------------------------- U5 comments
@pytest.mark.parametrize("kind", ["complaint", "purchase_request", "stock_inquiry", "sample_request"])
def test_u5_staff_comment_moves_the_stamp(db, enqueued, kind):
    from app.services.form_comment_service import FormCommentService

    form = next(f for f in FORMS if f.comment_kind == kind)
    user = seed_user(db)
    row = form.seed(db, status="responded") if kind != "sample_request" else form.seed(db)
    set_stamp(db, row, OLD)
    with person(db, user):
        FormCommentService(db).add_staff_comment(kind, str(row.id), user, "ZZT-FLA staff comment")
    assert stamp(db, row) > OLD


def test_u5_contact_comment_moves_the_stamp(db, enqueued):
    from app.services.form_comment_service import FormCommentService

    contact = seed_contact(db)
    row = BY_KEY["complaint"].seed(db, status="responded", contact_id=contact, space_id="zzt-fla-space")
    set_stamp(db, row, OLD)
    FormCommentService(db).add_contact_comment("complaint", str(row.id), contact, "zzt-fla-space", "ZZT-FLA hello")
    assert stamp(db, row) > OLD


def test_u5_system_comment_edit_and_delete_do_not_move_the_stamp(db, enqueued):
    from datetime import datetime

    from app.models.entity_conversation import EntityConversationMessage
    from app.services.form_comment_service import FormCommentService

    user = seed_user(db)
    row = BY_KEY["complaint"].seed(db, status="responded")
    system_msg = EntityConversationMessage(
        id=uid(), entity_type="complaint", entity_id=str(row.id), scope="form_comment", is_system=True,
        body_html="ZZT-FLA system note",
    )
    db.add(system_msg)
    db.commit()
    set_stamp(db, row, at(days=2))
    assert stamp(db, row) == at(days=2), "a system comment must not move the stamp"

    with person(db, user):
        result = FormCommentService(db).add_staff_comment("complaint", str(row.id), user, "ZZT-FLA real comment")
    set_stamp(db, row, at(days=2))
    comment_id = result["comment"]["id"]
    with person(db, user):
        msg = db.query(EntityConversationMessage).filter_by(id=comment_id).one()
        msg.body_html = "ZZT-FLA edited"
        msg.edited_at = datetime.utcnow()
        db.commit()
    assert stamp(db, row) == at(days=2), "a comment edit must not move the stamp"
    with person(db, user):
        msg = db.query(EntityConversationMessage).filter_by(id=comment_id).one()
        msg.deleted_at = datetime.utcnow()
        db.commit()
    assert stamp(db, row) == at(days=2), "a comment delete must not move the stamp"


# --------------------------------------------------------------------------- U5b attachment links
@pytest.mark.parametrize("key", ["complaint", "purchase_request", "price_tag_request", "stock_inquiry"])
def test_u5b_person_linking_a_file_moves_the_stamp(db, key):
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    form = BY_KEY[key]
    user = seed_user(db)
    row = form.seed(db)
    att = Attachment(id=uid(), original_filename="zzt-fla.pdf", stored_filename=f"zzt-fla-{uid()}.pdf",
                     file_path="zzt/fla.pdf")
    db.add(att)
    db.commit()
    set_stamp(db, row, OLD)
    with person(db, user):
        db.add(EntityAttachmentLink(id=uid(), entity_type=form.link_entity_type, entity_id=str(row.id),
                                    attachment_id=att.id))
        db.commit()
    assert stamp(db, row) > OLD, f"link entity_type {form.link_entity_type!r} must stamp {key}"


def test_u5b_person_unlinking_a_file_moves_the_stamp_and_a_worker_link_does_not(db):
    from app.models.entity_attachment import EntityAttachmentLink
    from app.models.resources import Attachment

    user = seed_user(db)
    row = BY_KEY["complaint"].seed(db)
    atts = []
    for _ in range(2):
        a = Attachment(id=uid(), original_filename="zzt-fla.pdf", stored_filename=f"zzt-fla-{uid()}.pdf",
                       file_path="zzt/fla.pdf")
        db.add(a)
        atts.append(a)
    db.commit()
    set_stamp(db, row, at(days=1))
    with non_person(db, "worker"):
        link = EntityAttachmentLink(id=uid(), entity_type="complaint", entity_id=str(row.id), attachment_id=atts[0].id)
        db.add(link)
        db.commit()
    assert stamp(db, row) == at(days=1), "a worker link does not move the stamp"
    with person(db, user):
        db.delete(db.query(EntityAttachmentLink).filter_by(id=link.id).one())
        db.commit()
    assert stamp(db, row) > at(days=1), "a person deleting the link moves the stamp"


# --------------------------------------------------------------------------- U6 bulk DML
@pytest.mark.parametrize("key", ["complaint", "stock_inquiry", "purchase_request"])
def test_u6_bulk_update_stamps_each_row(db, key):
    form = BY_KEY[key]
    user = seed_user(db)
    rows = [form.seed(db) for _ in range(3)]
    untouched = form.seed(db)
    for r in rows + [untouched]:
        set_stamp(db, r, OLD)
    field, value = form.edit
    with person(db, user):
        db.execute(
            update(form.model).where(form.model.id.in_([r.id for r in rows])).values({field: value})
            .execution_options(synchronize_session=False)
        )
        db.commit()
    for r in rows:
        audit = newest_audit(db, r)
        assert audit is not None, "precondition: the bulk path wrote a row per record"
        assert stamp(db, r) == audit.changed_at
    assert stamp(db, untouched) == OLD
