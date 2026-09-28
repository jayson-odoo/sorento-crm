"""Every hand-built mail this coder converted to `render_code` (#1349, PLAN-email-layout-28sep.md).

Drives the REAL sender (or the smallest real call path) and asserts on what was written:
the `data-sorento-layout` marker, the TEMPLATE's own heading + `em-btn-link` button (not the
safety-net's plain wrapper), the business facts, and that the text part carries the link.

AC ids: documentation/plans/email/email-layout-28sep-acceptance-criteria.md
(AC-EM068, 069, 070, 071, 072, 073, 074, 075, 076, 077, 085).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.email_outbox import EmailOutbox
from app.models.notification import Notification, NotificationDelivery
from app.models.user import User
from app.services.email_layout import has_layout
from tests._pg_fixture import pg_session, unique_code

MARKER_EMAIL = "zzt-email-senders"


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


@pytest.fixture
def no_real_queue(monkeypatch):
    """Complaint notifies enqueue onto the real `notifications` RQ queue, which drains
    immediately on a daemon thread in-process. That thread opens its OWN db session and
    would find nothing (our rows live only in this test's rolled-back transaction) - a
    harmless no-op - but capturing instead of running keeps the test deterministic and
    off real infra, matching tests/test_complaint_do_notify.py's own pattern."""
    from app.services import queue_service

    captured: list = []

    def fake_enqueue(fn, *args, **kw):  # noqa: ANN001
        captured.append({"fn": getattr(fn, "__name__", str(fn)), "args": args})

        class _Job:
            id = "job-1"

        return _Job()

    monkeypatch.setattr(queue_service, "enqueue_job", fake_enqueue)
    return captured


def _user(db, *, name: str = "Test User") -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=f"{MARKER_EMAIL}-{uuid.uuid4().hex[:8]}@example.com",
        name=name,
        status="ACTIVE",
    )
    db.add(u)
    db.flush()
    return u


# --------------------------------------------------------------------------- #
# 1. Complaint created / resubmitted (complaint_created)                      #
# --------------------------------------------------------------------------- #


def test_complaint_created_is_templated(db, monkeypatch, no_real_queue):
    from app.models.complaints import Complaint
    from app.services.complaints_service import ComplaintService
    from app.tasks import notification_tasks

    svc = ComplaintService(db)
    user = _user(db, name="Complaint Handler")
    monkeypatch.setattr(
        svc, "_get_complaint_handler_user_ids", lambda *, company_id=None: [str(user.id)]
    )
    c = Complaint(id=str(uuid.uuid4()), complaint_number=unique_code("CN"), status="processed_by_cs")
    db.add(c)
    db.flush()

    svc.notify_team_complaint_external_created(c.id)

    notif = (
        db.query(Notification)
        .filter(Notification.source_entity_type == "complaint", Notification.source_entity_id == c.id)
        .one()
    )
    html = notif.data["body_html"]
    assert has_layout(html)
    assert "New Complaint created" in html  # the template's own heading, not a safety-net wrapper
    assert "em-btn-link" in html

    delivery = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == notif.id, NotificationDelivery.channel == "email")
        .one()
    )
    notification_tasks._enqueue_email_for_delivery(db, notif, user, delivery, "complaint_created_external")
    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == user.email).one()
    assert has_layout(row.body_html)
    assert "em-btn-link" in row.body_html
    view_url = svc._build_complaint_view_url(c.id)
    assert view_url in row.body_html
    assert view_url in row.body_text  # text part carries the link


# --------------------------------------------------------------------------- #
# 2. Replacement DO delivered (complaint_do_delivered)                        #
# --------------------------------------------------------------------------- #


def test_complaint_do_delivered_is_templated(db, monkeypatch, no_real_queue):
    from app.models.complaints import Complaint
    from app.services.complaints_service import ComplaintService
    from app.tasks import notification_tasks

    svc = ComplaintService(db)
    user = _user(db, name="Tier Member")
    monkeypatch.setattr(
        svc, "_get_complaint_team_user_ids_tiers", lambda tiers=(1, 2), *, company_id=None: [str(user.id)]
    )
    c = Complaint(id=str(uuid.uuid4()), complaint_number=unique_code("CN"), status="processed_by_cs")
    db.add(c)
    db.flush()

    items = [{"product_code": "SKU-1", "qty": 2}, {"product_code": "SKU-2", "qty": 1}]
    svc.notify_team_do_delivered(c.id, complaint_number=c.complaint_number, order_number="REPPS-9001", items=items)

    notif = (
        db.query(Notification)
        .filter(Notification.source_entity_type == "complaint", Notification.source_entity_id == c.id)
        .one()
    )
    html = notif.data["body_html"]
    assert has_layout(html)
    assert "Replacement delivery order delivered" in html
    assert "em-btn-link" in html
    assert "SKU-1 x 2</li>" in html
    # still the old pins: plain body byte-identical, internal link, never the token link
    assert "\n- SKU-1 x 2\n- SKU-2 x 1" in (notif.body or "")
    assert "/complaint-management/complaints/" in (notif.body or "")
    assert "/view/complaint?token=" not in (notif.body or "")
    assert "/view/complaint?token=" not in html

    delivery = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.notification_id == notif.id, NotificationDelivery.channel == "email")
        .one()
    )
    notification_tasks._enqueue_email_for_delivery(db, notif, user, delivery, "notification_delivery")
    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == user.email).one()
    assert has_layout(row.body_html)
    assert "SKU-1 x 2</li>" in row.body_html


# --------------------------------------------------------------------------- #
# 3. External attachment linked, coalesced (attachment_linked)                #
# --------------------------------------------------------------------------- #


def test_attachment_linked_merges_two_notices_into_one_outbox_row(db):
    from app.models.resources import Attachment
    from app.services import attachment_notification_helper as helper
    from app.tasks import notification_tasks

    user = _user(db, name="Uploader")
    batch = uuid.uuid4().hex[:16]
    att1 = Attachment(
        id=str(uuid.uuid4()), original_filename="photo-a.jpg", stored_filename="a.jpg",
        file_path="https://cdn.example.test/a.jpg", uploaded_by=user.id, upload_batch_id=batch,
    )
    att2 = Attachment(
        id=str(uuid.uuid4()), original_filename="photo-b.jpg", stored_filename="b.jpg",
        file_path="https://cdn.example.test/b.jpg", uploaded_by=user.id, upload_batch_id=batch,
    )
    db.add_all([att1, att2])
    db.flush()

    n_ids1, _ = helper.notify_uploaders_after_external_attachment_event(
        db, [att1.id],
        notification_batch_id="batch-1",
        notif_type="external_product_attachment_linked",
        title="Product attachment linked: PRD-1",
        summary_plain='Your file was linked to product "PRD-1" in Sorento CRM',
        summary_html='<p>Your file was linked to product <strong>PRD-1</strong> in Sorento CRM.</p>',
        entity_url="https://crm.example.com/master-data-management/products/p1",
        entity_link_text="Open product in Sorento CRM",
    )
    n_ids2, _ = helper.notify_uploaders_after_external_attachment_event(
        db, [att2.id],
        notification_batch_id="batch-2",
        notif_type="external_product_attachment_linked",
        title="Product attachment linked: PRD-2",
        summary_plain='Your file was linked to product "PRD-2" in Sorento CRM',
        summary_html='<p>Your file was linked to product <strong>PRD-2</strong> in Sorento CRM.</p>',
        entity_url="https://crm.example.com/master-data-management/products/p2",
        entity_link_text="Open product in Sorento CRM",
    )
    assert len(n_ids1) == 1 and len(n_ids2) == 1

    # Each notice's OWN Notification.data.body_html is already the branded template.
    first_notif = db.query(Notification).filter(Notification.id == n_ids1[0]).one()
    assert has_layout(first_notif.data["body_html"])
    assert "em-btn-link" in first_notif.data["body_html"]
    assert "photo-a.jpg" in first_notif.data["body_html"]

    for nid in (n_ids1[0], n_ids2[0]):
        notif = db.query(Notification).filter(Notification.id == nid).one()
        delivery = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.notification_id == notif.id, NotificationDelivery.channel == "email")
            .one()
        )
        notification_tasks._enqueue_email_for_delivery(db, notif, user, delivery, "external_product_attachment")

    rows = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == user.email).all()
    assert len(rows) == 1, "two notices in one coalesce window must produce ONE outbox row"
    row = rows[0]
    assert has_layout(row.body_html)
    assert "photo-a.jpg" in row.body_html and "photo-b.jpg" in row.body_html
    assert "em-btn-link" in row.body_html


def test_attachment_linked_explicit_user_no_uploader(db):
    """notify_after_external_attachment_entity's notify_user_id fallback path."""
    from app.services import attachment_notification_helper as helper

    user = _user(db, name="Explicit Notify User")
    helper.notify_after_external_attachment_entity(
        db,
        [],
        str(user.id),
        notif_type="external_form_created",
        title="Form created",
        summary_plain="A form was created in Sorento CRM using your uploaded file(s).",
        summary_html="<p>A form was created in Sorento CRM using your uploaded file(s).</p>",
        entity_url="https://crm.example.com/forms-management/forms/f1",
        entity_link_text="Open form in Sorento CRM",
    )
    notif = (
        db.query(Notification)
        .filter(Notification.source_entity_type == "external_api", Notification.user_id == str(user.id))
        .one()
    )
    html = notif.data["body_html"]
    assert has_layout(html)
    assert "Form created" in html
    assert "em-btn-link" in html


# --------------------------------------------------------------------------- #
# 4. Promotion created, coalesced (promotion_created)                         #
# --------------------------------------------------------------------------- #


def test_promotion_created_is_templated(db):
    from app.models.resources import Attachment
    from app.services import attachment_notification_helper as helper

    user = _user(db, name="Promo Uploader")
    att = Attachment(
        id=str(uuid.uuid4()), original_filename="promo-banner.png", stored_filename="banner.png",
        file_path="https://cdn.example.test/banner.png", uploaded_by=user.id,
    )
    db.add(att)
    db.flush()
    promotion = SimpleNamespace(id=str(uuid.uuid4()), description="Year-End Sale")

    n_ids, _ = helper.notify_uploaders_after_external_promotion_created(
        db, [att.id], promotion, notification_batch_id="batch-1",
    )
    assert len(n_ids) == 1
    notif = db.query(Notification).filter(Notification.id == n_ids[0]).one()
    html = notif.data["body_html"]
    assert has_layout(html)
    assert "Promotion created: Year-End Sale" in html
    assert "em-btn-link" in html
    assert "promo-banner.png" in html


def test_promotion_created_explicit_user(db):
    from app.services import attachment_notification_helper as helper

    user = _user(db, name="Promo Explicit User")
    promotion = SimpleNamespace(id=str(uuid.uuid4()), description="Clearance Bonanza")

    ids = helper.notify_external_promotion_explicit_user(
        db, promotion, str(user.id), notification_batch_id="batch-2",
    )
    assert len(ids) == 1
    notif = db.query(Notification).filter(Notification.id == ids[0]).one()
    html = notif.data["body_html"]
    assert has_layout(html)
    assert "Promotion created: Clearance Bonanza" in html
    assert "em-btn-link" in html


# --------------------------------------------------------------------------- #
# 5. Daily SLA summary (sla_daily_summary) - HTML moves to the template,      #
#    the plain text stays (shared with WhatsApp / in-app)                     #
# --------------------------------------------------------------------------- #


def test_sla_daily_summary_html_is_templated(db):
    from app.services.user_sla_daily_summary_service import _build_bodies

    user = _user(db, name="Agent Smith")
    text_body, html_body = _build_bodies(db, user, "28/09/2026", 12, 9, 48, 41, [])

    assert has_layout(html_body)
    assert "Your daily SLA summary" in html_body
    assert "em-btn-link" in html_body
    assert "12" in html_body and "48" in html_body  # responded_7 / responded_30 facts
    # the plain text is unchanged - it is also the WhatsApp fallback default and the
    # in-app body, so it cannot drift from what those channels read.
    assert "Below is your daily summary." in text_body
    assert "Thanks for your help in making Sorento a better place to work." in text_body


# --------------------------------------------------------------------------- #
# 6. Onboarding (onboarding_intake_link, onboarding_submitted, completed)      #
# --------------------------------------------------------------------------- #


def test_onboarding_intake_link_is_templated(db, monkeypatch):
    import app.config as app_config
    from app.api.v1.user_management.onboarding import _email_intake_link

    monkeypatch.setattr(app_config.settings, "frontend_base_url", "https://crm.example.com")

    request = SimpleNamespace(
        id=str(uuid.uuid4()),
        token="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567ABCDEFGH",
        expires_at=datetime.utcnow() + timedelta(days=7),
        requester_name="Aina",
        requester_email=f"{MARKER_EMAIL}-{uuid.uuid4().hex[:8]}@example.com",
        title="ACME Sdn Bhd - Sales Team",
    )
    _email_intake_link(db, request)

    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == request.requester_email).one()
    assert row.subject == f"Submit your team for onboarding: {request.title}"
    assert has_layout(row.body_html)
    assert "Submit your team for onboarding" in row.body_html
    assert "em-btn-link" in row.body_html
    assert request.token in row.body_text  # the link is in the text part


def test_onboarding_submitted_is_templated(db):
    from app.api.v1.public.onboarding import _notify_submission

    request = SimpleNamespace(
        id=str(uuid.uuid4()),
        requester_name="Aina",
        requester_email=f"{MARKER_EMAIL}-{uuid.uuid4().hex[:8]}@example.com",
        title="ACME Sdn Bhd - Sales Team",
        people=[object(), object()],
        created_by_user_id=None,
        reviewed_by_user_id=None,
    )
    _notify_submission(db, request)

    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == request.requester_email).one()
    assert row.subject == f"Received: {request.title}"
    assert has_layout(row.body_html)
    assert "We received your submission" in row.body_html
    assert "2 people" in row.body_html


def test_onboarding_completed_is_templated(db):
    from app.tasks.onboarding_tasks import _notify_requester_complete

    request = SimpleNamespace(
        id=str(uuid.uuid4()),
        requester_name="Aina",
        requester_email=f"{MARKER_EMAIL}-{uuid.uuid4().hex[:8]}@example.com",
        title="ACME Sdn Bhd - Sales Team",
    )
    summary = {"created": 4, "skipped": 1, "failed": 0}
    _notify_requester_complete(db, request, summary)

    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == request.requester_email).one()
    assert row.subject == f"Onboarding complete: {request.title}"
    assert has_layout(row.body_html)
    assert "Onboarding complete" in row.body_html
    assert "Could not be created" not in row.body_html  # hidden when failed == 0


def test_onboarding_completed_shows_failed_when_nonzero(db):
    from app.tasks.onboarding_tasks import _notify_requester_complete

    request = SimpleNamespace(
        id=str(uuid.uuid4()),
        requester_name="Aina",
        requester_email=f"{MARKER_EMAIL}-{uuid.uuid4().hex[:8]}@example.com",
        title="ACME Sdn Bhd - Sales Team",
    )
    summary = {"created": 3, "skipped": 0, "failed": 2}
    _notify_requester_complete(db, request, summary)

    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == request.requester_email).one()
    assert "Could not be created" in row.body_html
    assert "Somebody from the team will be in touch" in row.body_html


# --------------------------------------------------------------------------- #
# 7. Bare notifications (title + body only) -> notification_generic          #
# --------------------------------------------------------------------------- #


def test_bare_notification_renders_notification_generic(db):
    from app.tasks import notification_tasks

    user = _user(db, name="Bare Notify User")
    notif = Notification(
        id=str(uuid.uuid4()),
        user_id=str(user.id),
        type="import_job_finished",
        title="Import finished",
        body="Your import of 120 rows finished with no errors.",
        data={"link": "https://crm.example.com/imports/sample"},
    )
    db.add(notif)
    db.flush()
    delivery = NotificationDelivery(
        id=str(uuid.uuid4()), notification_id=notif.id, channel="email", status="pending"
    )
    db.add(delivery)
    db.flush()

    notification_tasks._enqueue_email_for_delivery(db, notif, user, delivery, "import_job_completed")

    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == user.email).one()
    assert has_layout(row.body_html)
    assert "Import finished" in row.body_html  # the title, as the heading
    assert "Your import of 120 rows finished" in row.body_html
    assert "em-btn-link" in row.body_html
    assert row.subject == "Import finished"  # subject stays the notification title


def test_bare_notification_without_link_drops_the_button(db):
    from app.services.email_template_service import EmailTemplateService

    rendered = EmailTemplateService(db).render_code(
        "notification_generic", {"title": "T", "body": "B", "link": "", "link_label": ""}
    )
    assert has_layout(rendered["body_html"])
    # the phone-breakpoint CSS selector is always present; only the anchor itself
    # (the actual button) must be absent when there is nothing to link to.
    assert '<a class="em-btn-link"' not in rendered["body_html"]


# --------------------------------------------------------------------------- #
# 8. Supplier loading notice stays text-only (layout=False)                   #
# --------------------------------------------------------------------------- #


def test_supplier_loading_notice_stays_text_only(db, monkeypatch):
    from app.services.scm import loading_plan_service
    from app.services.scm import supplier_notice_service as scm_svc
    from tests.scm.test_loading_plan import World

    monkeypatch.setattr(scm_svc, "render_document", lambda html: b"%PDF-1.4 stub")
    monkeypatch.setattr(scm_svc, "_store", lambda data, filename: ("s3", f"exports/test/{filename}"))

    w = World(db)
    w.po("1", [("A", 10, 0)], issue_date=date(2026, 1, 1))
    w.stock("A", packed=10, unfinished=0, cbm=1.0)
    plan = loading_plan_service.build(
        db, supplier_id=str(w.supplier.id), container_count=1, container_cbm=10
    )
    supplier_email = f"{MARKER_EMAIL}-{uuid.uuid4().hex[:8]}@example.test"
    w.supplier.email = supplier_email
    db.flush()

    scm_svc.approve_and_notify(db, str(plan.id), actor="Ms Tee")

    row = db.query(EmailOutbox).filter(EmailOutbox.recipient_email == supplier_email).one()
    assert row.body_html is None
    assert row.body_text  # the bilingual EN/中文 cover note, unchanged
