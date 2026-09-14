"""r9 S4/D12-D15: the salesperson hears about it (AC-S4-1 .. AC-S4-6).

Nobody told the salesperson anything. Marketing marked a design ready and the
request sat there until the salesperson happened to open the portal. B1's
ruling is deliberately blunt: EVERY status change goes to them, including
confirmations of their own actions, plus "PDF ready" when a self print export
finishes.

The contract these tests hold the coder to:

* ``app.services.price_tag_notify.notify_salesperson(db, request, event, **ctx)``
  is the single door. ``transition_status`` calls it THROUGH THE MODULE, not
  through a bound name - the same reason the auto-export call is written that
  way today, so a test can replace the attribute.
* it is called ONCE per transition, and a failure inside it is logged and
  swallowed. A WhatsApp outage must never turn a successful approve into a
  failed one.
* the assignee's in-app bell is a different thing with a different rule: only
  ``changes_requested`` and ``approved``, deduplicated per request + status +
  round.

Red before the coder starts: the module, the SLA entry and the note
persistence do not exist.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests import _ptag_r9_seed as seed
from tests._pg_fixture import blank_session

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1", reason="SKIP_LIVE_DB_TESTS=1"
)

_CRM = "/api/v1/dealer-kit/price-tag-requests/{id}"


@pytest.fixture
def db_only():
    with blank_session() as db:
        seed.seed_marketer(db)
        yield db


@pytest.fixture
def notifier(monkeypatch):
    """Capture every ``notify_salesperson`` call instead of sending anything."""
    from app.services import price_tag_notify

    calls: list[dict] = []

    def _record(db, request, event, **ctx):
        calls.append({"request_id": request.id, "event": event, "ctx": ctx})

    monkeypatch.setattr(price_tag_notify, "notify_salesperson", _record)
    return calls


@pytest.fixture
def no_export(monkeypatch):
    """The approve auto-export is a different slice's concern."""
    monkeypatch.setattr(
        "app.services.dealer_kit.tag_sheet_export_service.request_tag_sheet_export",
        lambda *a, **k: None,
    )


def _request_at(db, status, *, print_by="office", contact_id=None):
    contact_id = contact_id or seed.seed_portal_contact(db)
    product = seed.seed_product(db)
    return seed.seed_request(
        db,
        contact_id,
        status=status,
        products=[product],
        print_by=print_by,
        assigned_to_id=seed.MARKETER_ID,
    )


# ---------------------------------------------------------------------------
# AC-S4-1 - every edge, exactly once
# ---------------------------------------------------------------------------


EDGES = [
    ("new", "designing", "self"),
    ("designing", "proof_ready", "self"),
    ("proof_ready", "changes_requested", "self"),
    ("proof_ready", "approved", "self"),
    ("approved", "ready_for_collection", "office"),
    ("ready_for_collection", "collected", "office"),
    ("designing", "rejected", "office"),
    ("proof_ready", "void", "office"),
]


class TestEveryTransitionReachesTheSalesperson:
    @pytest.mark.parametrize("current,nxt,print_by", EDGES)
    def test_one_call_per_transition_naming_the_event_and_a_portal_link(
        self, db_only, notifier, no_export, current, nxt, print_by
    ):
        from app.services.price_tag_request_service import PriceTagRequestService

        request = _request_at(db_only, current, print_by=print_by)

        PriceTagRequestService.transition_status(
            db_only, request.id, nxt, user_id=seed.MARKETER_ID
        )

        assert len(notifier) == 1, notifier
        call = notifier[0]
        assert call["request_id"] == request.id
        assert call["event"] == nxt, (
            "the event name is the status the request landed on, so the copy "
            "table in the plan can be keyed off it"
        )

    def test_a_notifier_failure_is_logged_and_the_transition_still_commits(
        self, db_only, monkeypatch, no_export
    ):
        from app.models.price_tag import PriceTagRequest
        from app.services import price_tag_notify
        from app.services.price_tag_request_service import PriceTagRequestService

        def _boom(*_args, **_kwargs):
            raise RuntimeError("Respond.io is down")

        monkeypatch.setattr(price_tag_notify, "notify_salesperson", _boom)
        request = _request_at(db_only, "designing")

        PriceTagRequestService.transition_status(
            db_only, request.id, "proof_ready", user_id=seed.MARKETER_ID
        )
        db_only.commit()
        db_only.expire_all()

        assert (
            db_only.query(PriceTagRequest)
            .filter(PriceTagRequest.id == request.id)
            .first()
            .status
            == "proof_ready"
        )

    def test_a_refused_transition_notifies_nobody(self, db_only, notifier, no_export):
        from app.services.error_handler import AppException
        from app.services.price_tag_request_service import PriceTagRequestService

        request = _request_at(db_only, "new")

        with pytest.raises(AppException):
            PriceTagRequestService.transition_status(
                db_only, request.id, "approved", user_id=seed.MARKETER_ID
            )

        assert notifier == []


# ---------------------------------------------------------------------------
# AC-S4-2 - the PDF
# ---------------------------------------------------------------------------


class TestPdfReady:
    def test_a_self_print_export_completing_says_the_pdf_is_ready(
        self, db_only, notifier
    ):
        from app.tasks import dealer_kit_export_tasks

        request = _request_at(db_only, "approved", print_by="self")
        seed.attach_design(db_only, request)

        dealer_kit_export_tasks.notify_price_tag_pdf_ready(db_only, request.id)

        assert [call["event"] for call in notifier] == ["pdf_ready"]

    def test_an_office_print_export_says_nothing(self, db_only, notifier):
        """The office collects the tags; the salesperson never downloads them."""
        from app.tasks import dealer_kit_export_tasks

        request = _request_at(db_only, "approved", print_by="office")
        seed.attach_design(db_only, request)

        dealer_kit_export_tasks.notify_price_tag_pdf_ready(db_only, request.id)

        assert notifier == []


# ---------------------------------------------------------------------------
# AC-S4-3 - the send is observable without Respond
# ---------------------------------------------------------------------------


class TestTheSendLeavesATrail:
    def test_it_writes_an_integration_log_row_against_price_tag_requests(
        self, db_only, monkeypatch
    ):
        """Respond sends are disabled on a lane stack, so the outbox / log row
        is how a transition's message is verified at all (AC-S4-3)."""
        from app.models.integration import IntegrationLog
        from app.services import price_tag_notify

        sent: list[dict] = []

        def _fake_send(db, *, identifier, text, use_case, context_vars=None, **_kw):
            sent.append({"identifier": identifier, "text": text, "use_case": use_case})
            return {
                "sent_as": "text",
                "response": {"id": "zzt-msg-1"},
                "window_state": "open",
                "request_payload": {"message": {"type": "text", "text": text}},
            }

        monkeypatch.setattr(
            "app.services.respond_messaging_service.send_text_or_template", _fake_send
        )
        request = _request_at(db_only, "proof_ready")

        price_tag_notify.notify_salesperson(db_only, request, "proof_ready")
        db_only.commit()

        assert len(sent) == 1, "the notifier did not reach the messaging service"
        assert request.doc_number in sent[0]["text"]

        rows = (
            db_only.query(IntegrationLog)
            .filter(IntegrationLog.business_table == "price_tag_requests")
            .filter(IntegrationLog.business_id == str(request.id))
            .all()
        )
        assert len(rows) == 1, "no IntegrationLog row for the price tag send"
        assert rows[0].direction == "outbound"

    def test_the_message_carries_the_portal_link_for_that_submission(
        self, db_only, monkeypatch
    ):
        from app.services import price_tag_notify

        sent: list[str] = []
        monkeypatch.setattr(
            "app.services.respond_messaging_service.send_text_or_template",
            lambda db, *, identifier, text, use_case, context_vars=None, **_kw: (
                sent.append(text)
                or {
                    "sent_as": "text",
                    "response": {},
                    "window_state": "open",
                    "request_payload": {},
                }
            ),
        )
        request = _request_at(db_only, "proof_ready")

        price_tag_notify.notify_salesperson(db_only, request, "proof_ready")

        assert sent, "nothing was sent"
        assert "price_tag_request" in sent[0], (
            "the salesperson needs a link that opens THIS request in the portal"
        )


# ---------------------------------------------------------------------------
# AC-S4-4 - the assignee's bell
# ---------------------------------------------------------------------------


class TestAssigneeBell:
    def _bells(self, db, user_id: str):
        from app.models.notification import Notification

        return (
            db.query(Notification)
            .filter(Notification.user_id == user_id)
            .filter(Notification.source_entity_type == "price_tag_request")
            .all()
        )

    @pytest.mark.parametrize(
        "current,nxt,event_type",
        [
            ("proof_ready", "changes_requested", "price_tag_changes_requested"),
            ("proof_ready", "approved", "price_tag_approved"),
        ],
    )
    def test_the_assignee_gets_one_in_app_notification(
        self, db_only, notifier, no_export, current, nxt, event_type
    ):
        from app.services.price_tag_request_service import PriceTagRequestService

        request = _request_at(db_only, current)

        PriceTagRequestService.transition_status(
            db_only, request.id, nxt, user_id=seed.MARKETER_ID
        )
        db_only.commit()

        bells = self._bells(db_only, seed.MARKETER_ID)
        assert len(bells) == 1, [bell.title for bell in bells]
        assert request.doc_number in (bells[0].title or "")
        # There is no `link` column: a deep link travels in `data` (the same
        # place every other in-app notification puts one).
        haystack = f"{bells[0].body or ''} {bells[0].data or {}}"
        assert f"/dealer-kit/price-tag-requests/{request.id}" in haystack, haystack
        assert bells[0].event_type == event_type

    def test_a_transition_that_is_neither_rings_no_bell(
        self, db_only, notifier, no_export
    ):
        from app.services.price_tag_request_service import PriceTagRequestService

        request = _request_at(db_only, "new")

        PriceTagRequestService.transition_status(
            db_only, request.id, "designing", user_id=seed.MARKETER_ID
        )
        db_only.commit()

        assert self._bells(db_only, seed.MARKETER_ID) == []

    def test_the_same_request_status_and_round_does_not_duplicate(
        self, db_only, notifier, no_export
    ):
        """Marketing sends the same proof back twice in one round: one bell."""
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        request = _request_at(db_only, "proof_ready")

        PriceTagRequestService.transition_status(
            db_only, request.id, "changes_requested", user_id=seed.MARKETER_ID
        )
        db_only.commit()
        db_only.query(PriceTagRequest).filter(
            PriceTagRequest.id == request.id
        ).update({"status": "proof_ready"})
        db_only.commit()
        PriceTagRequestService.transition_status(
            db_only, request.id, "changes_requested", user_id=seed.MARKETER_ID
        )
        db_only.commit()

        assert len(self._bells(db_only, seed.MARKETER_ID)) == 1


# ---------------------------------------------------------------------------
# AC-S4-5 - the form SLA notification says PT-...
# ---------------------------------------------------------------------------


class TestFormSlaNamesTheDocument:
    def test_the_number_source_resolves_the_pt_number(self, db_only):
        from app.services import form_sla_service

        contact_id = seed.seed_portal_contact(db_only)
        product = seed.seed_product(db_only)
        request = seed.seed_request(
            db_only, contact_id, status="new", products=[product]
        )

        resolved = form_sla_service._resolve_entity_number(
            db_only, "price_tag_request", str(request.id)
        )

        assert resolved == request.doc_number
        assert resolved.startswith("PT-")

    def test_the_detail_link_points_at_the_crm_page(self):
        from app.services import form_sla_service

        entity_id = "11111111-2222-3333-4444-555555555555"

        assert form_sla_service._form_detail_link("price_tag_request", entity_id) == (
            f"/dealer-kit/price-tag-requests/{entity_id}"
        )


# ---------------------------------------------------------------------------
# AC-S4-6 - a rejection's reason survives
# ---------------------------------------------------------------------------


class TestTheTransitionNoteIsKept:
    @pytest.fixture
    def crm(self, monkeypatch):
        from app.dependencies import (
            get_current_user,
            get_current_user_or_api_key,
            get_db,
        )
        from app.models.base import set_company_scope
        from app.services import price_tag_notify
        from app.services.company_scope_resolver import apply_company_scope

        monkeypatch.setattr(
            price_tag_notify, "notify_salesperson", lambda *a, **k: None
        )
        with blank_session() as db:
            seed.seed_marketer(db)

            def _override_get_db():
                yield db

            async def _override_scope():
                scope = frozenset({seed.SORENTO})
                set_company_scope(db, scope)
                return scope

            principal = {
                "id": seed.MARKETER_ID,
                "email": "zzt-ptag-r9-marketer@test.com",
            }
            app.dependency_overrides[get_db] = _override_get_db
            app.dependency_overrides[apply_company_scope] = _override_scope
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
            try:
                with TestClient(app) as client:
                    yield client, db
            finally:
                app.dependency_overrides.clear()

    def test_a_rejection_note_lands_as_a_general_review_comment_by_the_user(
        self, crm
    ):
        """``TransitionPayload.note`` has existed since r7 and the route threw
        it away, so a rejection reason was typed into a box that discarded it."""
        client, db = crm
        from app.models.price_tag import PriceTagReviewComment

        contact_id = seed.seed_portal_contact(db)
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="proof_ready", products=[product]
        )

        response = client.post(
            f"{_CRM.format(id=request.id)}/transition",
            json={"status": "rejected", "note": "The dealer cancelled the order"},
        )

        assert response.status_code == 200, response.text
        rows = (
            db.query(PriceTagReviewComment)
            .filter(PriceTagReviewComment.request_id == request.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].line_id is None
        assert rows[0].body == "The dealer cancelled the order"
        assert rows[0].author_user_id == seed.MARKETER_ID
        assert rows[0].author_contact_id is None

    def test_a_transition_with_no_note_creates_nothing(self, crm):
        client, db = crm
        from app.models.price_tag import PriceTagReviewComment

        contact_id = seed.seed_portal_contact(db)
        product = seed.seed_product(db)
        request = seed.seed_request(
            db, contact_id, status="proof_ready", products=[product]
        )

        client.post(
            f"{_CRM.format(id=request.id)}/transition", json={"status": "rejected"}
        )

        assert (
            db.query(PriceTagReviewComment)
            .filter(PriceTagReviewComment.request_id == request.id)
            .count()
            == 0
        )
