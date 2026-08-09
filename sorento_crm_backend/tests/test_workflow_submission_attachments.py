"""F2c gate - files and messages hang off a workflow submission.

F1 gave a submission a status, F1a gave its LINES a status, F2a gave it a clock and
F2b let a contact file it. F2c is the last dependency after-sales S1 needs: the
customer photographs the cracked unit, somebody at Sorento is told, and the customer
is told back. Four constraints shape the whole slice, and every one of them is a
place where the obvious implementation is wrong:

1. **The proof belongs to the LINE, not to the case.** An RMA lists five items and
   two of them are damaged. A design that can only link a file to the submission
   cannot express "photo of the cracked unit on line 2", which is the literal
   requirement (AC-F2c-1). It is also the difference between a 10-file cap meaning
   ten photos per claim and ten photos per item.
2. **The storage key must carry a row id.** ``{type}/{name}`` collides the moment two
   customers both photograph ``IMG_0001.jpg``, and this is not hypothetical: 120 keys
   in this repo were already shared between records before the uuid-segregation
   migration (AC-F2c-2).
3. **``notifications.user_id`` is NOT NULL and has no foreign key**, so writing a
   ``respond_contacts.id`` into it type-checks, persists, and produces a notification
   addressed to nobody that no query will ever surface. A contact must be reached by
   a path that is explicit about being a contact path (AC-F2c-4).
4. **Every one of these is a POST-COMMIT side effect.** The file is stored, the
   status has moved. A notification that raises hands the caller a 500 for an
   operation that succeeded, and the retry then takes an idempotent path that never
   backfills the missed message (AC-F2c-6).

Two decisions this suite takes, because F2c does not state them and both are
load-bearing. They are asserted here so the next reader inherits an answer rather
than a coin flip:

- **A submission attachment is company-SHARED (``company_id IS NULL``).**
  ``workflow_submissions`` has no ``company_id`` at all while ``attachments`` does,
  and ``Attachment`` is already ``__company_shared__``. Stamping a company on the
  child of an unscoped parent means the submission stays visible under a scope where
  its own evidence has vanished, which reads as data loss rather than as a
  permission.
- **The per-type cap counts per LINKED ROW, so a line-linked file counts against the
  LINE.** ``attachment_types.max_count_per_entity`` is named per ENTITY and
  ``check_quota`` already counts by ``(entity_type, entity_id, attachment_type)``.
  The alternative - one budget for the whole case - means item 1 of a 20-item RMA can
  exhaust the evidence allowance for item 20.

Every test traces to an AC in
``documentation/plans/forms-platform/forms-platform-acceptance-criteria.md``,
Group F2c (AC-F2c-1..7).

Run: venv/bin/pytest tests/test_workflow_submission_attachments.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid
from datetime import timedelta

import pytest

from app.database import Base
from app.form_engine.schemas import FORM_SCHEMA_VERSION
from app.models.access import AccessAgent, AgentTeam, RespondContact, Team, TeamMember
from app.models.entity_attachment import EntityAttachmentLink
from app.models.integration import IntegrationLog
from app.models.notification import Notification, NotificationDelivery
from app.models.portal import PortalToken
from app.models.resources import Attachment, AttachmentType
from app.models.sla import ConversationSLATracking, FormSLAConfig, SLAPolicy, SLAPolicyTier
from app.models.user import User
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
    WorkflowSubmissionLine,
)
from app.services.error_handler import AppException
from app.services.status_service import resolve_graph
from app.services.storage_router import sanitize_storage_filename
from app.services.workflow_forms_service import WorkflowFormsService
from app.services.workflow_submission_line_status_graph import (
    register_workflow_submission_line_status_entity,
    seed_workflow_submission_line_status_graph,
)
from app.services.workflow_submission_sla import SUBMISSION_CREATED_EVENT
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
    register_workflow_submission_status_entity,
    seed_workflow_submission_status_graph,
)
from app.status_engine import registry as status_registry

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# The two modules F2c is expected to add. Split on purpose: one owns bytes and links,
# the other owns who gets told. Folding them together is how "the upload failed
# because the customer's WhatsApp window is shut" becomes possible.
ATTACHMENTS_MODULE = "app.services.workflow_submission_attachments"
NOTIFY_MODULE = "app.services.workflow_submission_notify"
PORTAL_MODULE = "app.services.workflow_submission_portal"

# The repeater every submission in this file files its lines under.
LINE_GROUP = "items"

SPACE_ID = "9911"

FORM_DOC = {
    "schemaVersion": FORM_SCHEMA_VERSION,
    "pages": [
        {
            "id": "p1",
            "title": "Details",
            "sections": [
                {
                    "id": "s1",
                    "title": "Main",
                    "fields": [
                        {
                            "id": "f1",
                            "type": "text",
                            "key": "title",
                            "label": "Title",
                            "required": True,
                        },
                        {
                            "id": "f2",
                            "type": "repeater",
                            "key": LINE_GROUP,
                            "label": "Items",
                            "repeater": {
                                "fields": [
                                    {
                                        "id": "sf1",
                                        "type": "text",
                                        "key": "model",
                                        "label": "Model",
                                    }
                                ]
                            },
                        },
                    ],
                }
            ],
        }
    ],
}

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"ZZT" * 8


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _isolate_registry():
    """The status registry is process-global; snapshot and restore it."""
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)


@pytest.fixture(autouse=True)
def _no_queue(monkeypatch):
    """Notification and SLA side effects enqueue RQ work. A live Redis is not a
    dependency of a test about where a file lands."""
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    yield


class FakeBackend:
    """An in-memory bucket. A test that writes to a live bucket is a defect.

    Records the key every upload was addressed to, which is the whole of AC-F2c-2:
    the assertion is about the key, and the key is only observable here.
    """

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.fail_with: Exception | None = None

    def upload_file(self, contents, key, content_type=None, **kwargs):
        if self.fail_with is not None:
            raise self.fail_with
        self.objects[str(key).lstrip("/")] = contents
        return True

    def file_exists(self, key):
        return str(key).lstrip("/") in self.objects

    def download_file(self, key):
        return self.objects[str(key).lstrip("/")]

    def delete_file(self, key):
        return self.objects.pop(str(key).lstrip("/"), None) is not None

    def copy_file(self, old_key, new_key):
        self.objects[str(new_key).lstrip("/")] = self.objects[str(old_key).lstrip("/")]

    def get_signed_url(self, key, expires_in=3600):
        return f"https://zzt.invalid/{str(key).lstrip('/')}?sig=zzt"

    def get_cdn_base_url(self, key):
        return f"https://zzt.invalid/{str(key).lstrip('/')}"


@pytest.fixture(autouse=True)
def storage(monkeypatch):
    """Every storage path in the process points at the fake bucket."""
    from app.services import image_thumbnailer, storage_router

    backend = FakeBackend()
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: backend)
    monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
    monkeypatch.setattr(
        storage_router, "resolve_signed_url", lambda path, provider=None: str(path)
    )
    # Thumbnailing is a real image pipeline over PIL. Nothing in F2c is about it, and
    # a non-image fixture would make it the reason a test fails.
    monkeypatch.setattr(
        image_thumbnailer, "store_thumbnail", lambda *a, **k: None
    )
    return backend


class RespondRecorder:
    """Stands in for ``send_text_or_template``.

    Records what was attempted; ``fail_with`` makes the next send raise, which is how
    AC-F2c-5's "a 401'd send still has to appear in the outbox" is reachable without
    real (deliberately wrong) credentials.
    """

    def __init__(self):
        self.calls: list[dict] = []
        self.fail_with: Exception | None = None

    def __call__(self, db, **kwargs):
        self.calls.append(kwargs)
        if self.fail_with is not None:
            raise self.fail_with
        payload = {"message": {"type": "text", "text": kwargs.get("text")}}
        return {
            "sent_as": "text",
            "response": {"messageId": 1234567890},
            "window_state": {"open": True},
            "request_payload": payload,
        }

    @property
    def identifiers(self) -> list[str]:
        return [str(call.get("identifier") or "") for call in self.calls]


@pytest.fixture(autouse=True)
def respond(monkeypatch):
    """No CRM message leaves the process.

    Patched on the DEFINING module and on any module that has already bound the name,
    because this repo's call sites import it locally inside the function body.
    """
    from app.services import respond_messaging_service

    recorder = RespondRecorder()
    monkeypatch.setattr(respond_messaging_service, "send_text_or_template", recorder)
    for name in (NOTIFY_MODULE, ATTACHMENTS_MODULE):
        module = _optional_module(name)
        if module is not None and hasattr(module, "send_text_or_template"):
            monkeypatch.setattr(module, "send_text_or_template", recorder)
    return recorder


# ---------------------------------------------------------------------- helpers


def _optional_module(name: str):
    if importlib.util.find_spec(name) is None:
        return None
    return importlib.import_module(name)


def _attachments_module():
    """Import the module F2c adds for files, or fail naming the contract it misses."""
    module = _optional_module(ATTACHMENTS_MODULE)
    if module is None:
        raise AssertionError(
            f"{ATTACHMENTS_MODULE} does not exist. F2c needs one module owning the "
            "submission and line linkage, the storage key and the per-type cap, so "
            "the rule that decides where bytes land cannot drift away from the rule "
            "that decides how many of them a record may hold."
        )
    return module


def _notify_module():
    module = _optional_module(NOTIFY_MODULE)
    if module is None:
        raise AssertionError(
            f"{NOTIFY_MODULE} does not exist. F2c needs one module owning who gets "
            "told about a submission, because a CONTACT and a USER are reached by "
            "completely different machinery and notifications.user_id (NOT NULL, no "
            "foreign key) will silently accept a contact id from either caller."
        )
    return module


def _attach(db):
    module = _attachments_module()
    service = getattr(module, "WorkflowSubmissionAttachmentService", None)
    assert callable(service), (
        f"{ATTACHMENTS_MODULE}.WorkflowSubmissionAttachmentService(db) must exist."
    )
    return service(db)


def _portal(db):
    module = importlib.import_module(PORTAL_MODULE)
    return module.WorkflowSubmissionPortalService(db)


def _seed_graphs(db):
    seed_workflow_submission_status_graph(db)
    seed_workflow_submission_line_status_graph(db)
    db.flush()
    register_workflow_submission_status_entity()
    register_workflow_submission_line_status_entity()


def _seed_attachment_type(db, *, cap: int | None = None) -> AttachmentType:
    """The ``attachment_types`` row whose ``max_count_per_entity`` IS the cap.

    Seeded through the module's own seeder so the code under test and the migration
    cannot disagree about the code string; the cap is then set per test, because the
    point of AC-F2c-3 is that it is configuration rather than a constant.
    """
    module = _attachments_module()
    seeder = getattr(module, "seed_workflow_submission_attachment_type", None)
    assert callable(seeder), (
        f"{ATTACHMENTS_MODULE}.seed_workflow_submission_attachment_type(db) must "
        "exist: the attachment type carries the configurable cap, so a migration has "
        "to create it and a re-run has to correct it rather than duplicate it."
    )
    seeder(db)
    db.flush()
    code = getattr(module, "ATTACHMENT_TYPE_CODE")
    row = db.query(AttachmentType).filter(AttachmentType.code == code).one()
    row.max_count_per_entity = cap
    db.flush()
    return row


def _user(db, label: str = "staff", *, user_id: str | None = None) -> str:
    """A real ``users`` row.

    The id defaults to a UUID string on purpose: ``attachments.uploaded_by`` is a
    ``uuid`` column while ``users.id`` is ``String(64)``, so only a uuid-shaped id can
    actually be recorded there. The non-uuid case is exercised deliberately, once.
    """
    uid = user_id or str(uuid.uuid4())
    db.add(
        User(
            id=uid,
            email=f"{TEST_PREFIX.lower()}-{uuid.uuid4().hex[:8]}@{TEST_PREFIX.lower()}.invalid",
            name=f"{TEST_PREFIX} {label}",
            status="ACTIVE",
        )
    )
    db.flush()
    return uid


def _contact(db, *, respond_io_id: str | None = "437264483") -> RespondContact:
    """A ``respond_contacts`` row whose id is deliberately NOT a uuid.

    ``respond_contacts.id`` is TEXT. A uuid-shaped test id would let a contact id
    slip into ``notifications.user_id`` or ``integration_log.business_id`` unnoticed,
    which is exactly what AC-F2c-4 and AC-F2c-5 forbid.
    """
    contact = RespondContact(
        id=unique_code("contact").lower(),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name=f"{TEST_PREFIX} contact",
        respond_io_id=respond_io_id,
    )
    db.add(contact)
    db.flush()
    return contact


def _token(db, contact: RespondContact) -> PortalToken:
    from app.services.portal_service import _utcnow

    token = PortalToken(
        id=str(uuid.uuid4()),
        token=unique_code("tok").upper(),
        contact_id=contact.id,
        space_id=SPACE_ID,
        expires_at=_utcnow() + timedelta(days=7),
        verified_at=_utcnow(),
    )
    db.add(token)
    db.flush()
    return token


def _definition(db, *, portal: bool = False) -> WorkflowFormDefinition:
    definition = WorkflowFormDefinition(
        id=str(uuid.uuid4()),
        code=unique_code("wfdef").lower(),
        name=f"{unique_code('Form')} definition",
        draft_schema=FORM_DOC,
    )
    db.add(definition)
    db.flush()
    version = WorkflowFormVersion(
        id=str(uuid.uuid4()),
        definition_id=definition.id,
        version_number=1,
        schema=FORM_DOC,
    )
    db.add(version)
    db.flush()
    definition.published_version_id = version.id
    if portal:
        definition.portal_submittable = True
        definition.portal_party_kinds = []
    db.flush()
    return definition


def _submission(db, definition, *, rows: int = 2, user_id: str | None = None):
    lines = [
        {"line_group_id": LINE_GROUP, "row_data": {"model": f"{TEST_PREFIX}-{i}"}}
        for i in range(rows)
    ]
    return WorkflowFormsService(db).create_submission(
        str(definition.id), {"title": f"{TEST_PREFIX} answer"}, lines, user_id
    )


def _lines(db, submission) -> list[WorkflowSubmissionLine]:
    return (
        db.query(WorkflowSubmissionLine)
        .filter(WorkflowSubmissionLine.submission_id == str(submission.id))
        .order_by(WorkflowSubmissionLine.sort_order.asc())
        .all()
    )


def _upload(db, submission, *, line=None, filename="proof.png", **extra):
    """One upload through the service under test. Returns the created Attachment."""
    result = _attach(db).upload(
        submission_id=str(submission.id),
        line_id=str(line.id) if line is not None else None,
        contents=PNG_BYTES,
        filename=filename,
        content_type="image/png",
        **extra,
    )
    assert isinstance(result, dict) and result.get("attachment_id"), (
        "upload() must return the fixed upload-and-link shape used by every other "
        f"upload path in this repo: got {result!r}"
    )
    return db.query(Attachment).filter(Attachment.id == result["attachment_id"]).one()


def _links(db, entity_type: str, entity_id: str) -> list[EntityAttachmentLink]:
    return (
        db.query(EntityAttachmentLink)
        .filter(
            EntityAttachmentLink.entity_type == entity_type,
            EntityAttachmentLink.entity_id == str(entity_id),
        )
        .all()
    )


def _key_of(attachment: Attachment) -> str:
    """The storage key behind an attachment row, however the row spells it."""
    from app.services.storage_router import extract_key

    return str(extract_key(attachment.file_path) or attachment.file_path or "").lstrip("/")


def _outbox(db, business_id: str) -> list[IntegrationLog]:
    return (
        db.query(IntegrationLog)
        .filter(IntegrationLog.business_id == str(business_id))
        .order_by(IntegrationLog.created_at.asc())
        .all()
    )


def _header_graph(db, scope=None):
    return resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, scope)


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# --------------------------------------------------- SLA scaffolding (AC-F2c-7)


def _stage(
    db,
    definition,
    *,
    notify_assignee: bool = True,
    member_id: str | None = None,
) -> FormSLAConfig:
    """One ``workflow_submission`` stage that starts on creation, scoped to this
    definition so it cannot clock another test's submission."""
    agent_id = str(uuid.uuid4())
    agent_code = unique_code("agent").lower()
    db.add(AccessAgent(id=agent_id, code=agent_code, name=f"{TEST_PREFIX} agent"))
    db.flush()

    member = member_id or _user(db, "member")
    team_id = str(uuid.uuid4())
    db.add(Team(id=team_id, name=f"{TEST_PREFIX} team"))
    db.flush()
    db.add(
        AgentTeam(
            id=str(uuid.uuid4()), agent_id=agent_id, code="main", team_id=team_id, tier=1
        )
    )
    db.add(
        TeamMember(
            id=str(uuid.uuid4()),
            team_id=team_id,
            user_id=member,
            include_in_round_robin=True,
        )
    )
    db.flush()

    policy_id = str(uuid.uuid4())
    policy_code = unique_code("pol").upper()
    db.add(SLAPolicy(id=policy_id, code=policy_code, name=policy_code))
    db.add(
        SLAPolicyTier(
            id=str(uuid.uuid4()),
            policy_id=policy_id,
            tier_level=1,
            tier_name="Tier 1",
            response_hours=4,
            resolution_hours=24,
        )
    )
    db.flush()

    config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        stage_code="main",
        policy_id=policy_id,
        agent_code=agent_code,
        team_set_code="main",
        definition_id=str(definition.id),
        start_event=SUBMISSION_CREATED_EVENT,
        resolve_event=None,
        advance_on_event=None,
        is_active=True,
        notify_assignee=notify_assignee,
        notify_on_escalation=notify_assignee,
    )
    db.add(config)
    db.commit()
    return config


def _notifications_for(db, user_id: str) -> list[Notification]:
    return (
        db.query(Notification).filter(Notification.user_id == str(user_id)).all()
    )


def _channels(db, notification_id: str) -> set[str]:
    return {
        row.channel
        for row in db.query(NotificationDelivery).filter(
            NotificationDelivery.notification_id == str(notification_id)
        )
    }


# =================================================================== AC-F2c-1
# Submission-level AND line-level linkage, on the generic polymorphic table.


def test_no_third_linkage_pattern_appears_for_submissions():
    """This repo already carries two ways to link an attachment: per-entity tables
    (``complaint_attachments``, ``product_attachments``, ``promotion_attachments``) and
    the generic ``entity_attachment_links``. A ``workflow_submission_attachments``
    table would be a third - on the one feature whose entire premise is that a new
    form is CONFIGURATION, not code. Every future form type would then need its own
    migration to hold a photo."""
    offenders = sorted(
        name
        for name in Base.metadata.tables
        if "attachment" in name
        and ("submission" in name or "workflow" in name)
    )
    assert offenders == [], (
        f"a bespoke linkage table appeared for submissions: {offenders}. AC-F2c-1 "
        "requires reusing the generic entity_attachment_links table."
    )


def test_the_two_link_scopes_are_named_and_distinct():
    """One name each for the header and the line, declared in one place.

    Two hand-written copies of the string ``workflow_submission_line`` is the same
    defect as the duplicated FORM_SLA_TYPES tuple: the writer and the reader drift,
    and the symptom is a photo that was stored and can never be listed.
    """
    module = _attachments_module()
    submission_type = getattr(module, "SUBMISSION_ENTITY_TYPE", None)
    line_type = getattr(module, "SUBMISSION_LINE_ENTITY_TYPE", None)
    assert submission_type and line_type, (
        f"{ATTACHMENTS_MODULE} must declare SUBMISSION_ENTITY_TYPE and "
        "SUBMISSION_LINE_ENTITY_TYPE."
    )
    assert submission_type != line_type, (
        "the header and the line must be different entity types, or a line's proof "
        "is indistinguishable from the case's."
    )
    width = EntityAttachmentLink.__table__.columns["entity_type"].type.length
    assert len(line_type) <= width, (
        f"{line_type!r} does not fit entity_attachment_links.entity_type "
        f"(VARCHAR({width})); the INSERT would be truncated or refused."
    )


def test_a_file_links_to_the_submission_when_no_line_is_named(db):
    """The case-level attachment: a receipt belongs to the claim, not to an item."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), user_id=_user(db))
    db.commit()

    module = _attachments_module()
    attachment = _upload(db, submission)

    links = _links(db, module.SUBMISSION_ENTITY_TYPE, submission.id)
    assert [str(link.attachment_id) for link in links] == [str(attachment.id)]


def test_a_file_links_to_one_line_of_a_submission(db):
    """The requirement F2c exists for. After-sales attaches proof PER RETURNED ITEM,
    so the link has to name the line - a submission-only design cannot express
    "photo of the cracked unit on line 2" at all."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=2, user_id=_user(db))
    db.commit()
    second = _lines(db, submission)[1]

    module = _attachments_module()
    attachment = _upload(db, submission, line=second)

    line_links = _links(db, module.SUBMISSION_LINE_ENTITY_TYPE, second.id)
    assert [str(link.attachment_id) for link in line_links] == [str(attachment.id)]
    assert _links(db, module.SUBMISSION_ENTITY_TYPE, submission.id) == [], (
        "a line-linked file must not also be linked to the header: the header list "
        "would then show every item's evidence with no way to tell them apart."
    )


def test_each_line_holds_only_its_own_proof(db):
    """Two damaged items, two photos, and the adjudicator must be able to tell which
    photo is which. This is the assertion a submission-level-only implementation
    cannot make pass, however many files it stores."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=2, user_id=_user(db))
    db.commit()
    first, second = _lines(db, submission)

    one = _upload(db, submission, line=first, filename="item-one.png")
    two = _upload(db, submission, line=second, filename="item-two.png")

    service = _attach(db)
    listed_first = service.list_attachments(str(submission.id), line_id=str(first.id))
    listed_second = service.list_attachments(str(submission.id), line_id=str(second.id))
    assert {str(row["attachment_id"]) for row in listed_first} == {str(one.id)}
    assert {str(row["attachment_id"]) for row in listed_second} == {str(two.id)}


def test_the_submission_listing_does_not_absorb_the_lines_files(db):
    """The other direction of the same separation. If the header listing silently
    included every line's file, the cap, the UI and the customer's own view would all
    disagree about how many files the case holds."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=1, user_id=_user(db))
    db.commit()
    line = _lines(db, submission)[0]

    header_file = _upload(db, submission, filename="receipt.png")
    _upload(db, submission, line=line, filename="item.png")

    listed = _attach(db).list_attachments(str(submission.id))
    assert {str(row["attachment_id"]) for row in listed} == {str(header_file.id)}


def test_a_line_belonging_to_another_submission_cannot_be_attached_to(db):
    """``entity_attachment_links`` is polymorphic and has NO foreign key on
    ``entity_id``, so a line id from a different claim inserts perfectly happily and
    the file appears under somebody else's item. The parent/child check has to be
    made in code, because the database will not make it."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    definition = _definition(db)
    mine = _submission(db, definition, rows=1, user_id=_user(db))
    theirs = _submission(db, definition, rows=1, user_id=_user(db))
    db.commit()
    their_line = _lines(db, theirs)[0]

    with pytest.raises(AppException) as err:
        _upload(db, mine, line=their_line)
    assert err.value.status_code in (400, 404, 422)


# =================================================================== AC-F2c-2
# The key is {type}/{id}/{original_filename}. A flat {type}/{name} collides, and
# already did: 120 keys in this repo were shared between records.


def test_the_key_is_type_then_id_then_filename(db):
    """Three segments, in that order. The id segment is what makes the key unique;
    the type segment is what makes a bucket listing readable."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    attachment = _upload(db, submission, filename="warranty.png")
    key = _key_of(attachment)
    segments = key.split("/")
    assert len(segments) == 3, (
        f"key {key!r} is not {{type}}/{{id}}/{{original_filename}}. A flat "
        "{type}/{name} key collides across records - this already happened here."
    )
    assert segments[1] == str(attachment.id), (
        f"the middle segment must be the attachment id; got {segments[1]!r}. Any "
        "other value re-introduces the collision the id is there to prevent."
    )
    assert segments[2] == sanitize_storage_filename(attachment.original_filename)


def test_two_records_uploading_the_same_filename_do_not_collide(db):
    """The defect in one test. Two customers both send ``IMG_0001.jpg``; under a flat
    key the second silently overwrites the first, and the first claim's evidence is
    replaced by the second claim's without an error anywhere."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    definition = _definition(db)
    first = _submission(db, definition, rows=0, user_id=_user(db))
    second = _submission(db, definition, rows=0, user_id=_user(db))
    db.commit()

    one = _upload(db, first, filename="IMG_0001.jpg")
    two = _upload(db, second, filename="IMG_0001.jpg")

    assert _key_of(one) != _key_of(two)
    assert len(storage_objects()) == 2, (
        "the second upload overwrote the first in the bucket: both records now point "
        "at the same bytes."
    )


def test_two_lines_of_one_submission_uploading_the_same_filename_do_not_collide(db):
    """Same collision, one level down and far more likely: a phone names every photo
    ``IMG_0001.jpg``, and a customer photographing two damaged items in one claim
    sends exactly that twice."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=2, user_id=_user(db))
    db.commit()
    first, second = _lines(db, submission)

    one = _upload(db, submission, line=first, filename="IMG_0001.jpg")
    two = _upload(db, submission, line=second, filename="IMG_0001.jpg")

    assert _key_of(one) != _key_of(two)
    assert len(storage_objects()) == 2


def test_the_key_basename_cannot_escape_its_id_segment(db):
    """``original_filename`` is raw client input and the key is built from it.

    AC-F2c-2 says the original filename IS the key basename, but a name containing a
    path separator would then add a segment and land the object outside its own id
    folder - which is the collision the id segment exists to prevent, re-opened by
    the customer's file picker. ``sanitize_storage_filename`` is the repo's existing
    answer and this pins it.
    """
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    attachment = _upload(db, submission, filename="../../etc/passwd.png")
    key = _key_of(attachment)
    assert len(key.split("/")) == 3, f"key {key!r} escaped its id segment"


def test_the_immutable_upload_name_and_the_editable_display_name_are_both_kept(db):
    """Two columns, two jobs. ``original_filename`` is the key basename and never
    changes; ``stored_filename`` is what a user may rename in the Files page. Storing
    only one of them means either the key drifts when somebody renames a file, or the
    rename is not possible at all."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    attachment = _upload(db, submission, filename="Cracked Unit.png")
    assert attachment.original_filename == "Cracked Unit.png"
    assert attachment.stored_filename, "stored_filename is NOT NULL"
    assert _key_of(attachment).endswith(
        sanitize_storage_filename(attachment.original_filename)
    )


# =================================================================== AC-F2c-3
# The cap is attachment_types.max_count_per_entity. Blank means unlimited.


def test_the_cap_is_read_from_the_attachment_type_row(db):
    """Not a constant in the code. The same test data with a different cap has to
    behave differently, which is the only way to tell a configured limit from a
    hardcoded one that happens to agree with it today."""
    _seed_graphs(db)
    attachment_type = _seed_attachment_type(db, cap=2)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    _upload(db, submission, filename="one.png")
    _upload(db, submission, filename="two.png")
    with pytest.raises(AppException) as err:
        _upload(db, submission, filename="three.png")
    assert err.value.status_code in (400, 422)

    attachment_type.max_count_per_entity = 5
    db.commit()
    _upload(db, submission, filename="three.png")


def test_a_blank_cap_means_unlimited(db):
    """NULL is "no limit configured", and the only safe reading is no limit. Treating
    a blank as zero would make an unconfigured type refuse every upload, which looks
    exactly like a broken bucket."""
    _seed_graphs(db)
    _seed_attachment_type(db, cap=None)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    for i in range(12):
        _upload(db, submission, filename=f"file-{i}.png")
    module = _attachments_module()
    assert len(_links(db, module.SUBMISSION_ENTITY_TYPE, submission.id)) == 12


def test_the_cap_counts_per_line_not_across_the_whole_case(db):
    """THE decision this suite takes, and it is not in the AC.

    ``max_count_per_entity`` is named per ENTITY, and a line-linked file's entity IS
    the line. The alternative - one budget for the whole submission - means item 1 of
    a 20-item RMA can exhaust the evidence allowance for item 20, and the customer
    discovers it only when the last photo is refused.
    """
    _seed_graphs(db)
    _seed_attachment_type(db, cap=1)
    submission = _submission(db, _definition(db), rows=2, user_id=_user(db))
    db.commit()
    first, second = _lines(db, submission)

    _upload(db, submission, line=first, filename="one.png")
    with pytest.raises(AppException):
        _upload(db, submission, line=first, filename="two.png")

    # The other line still has its own full budget.
    _upload(db, submission, line=second, filename="three.png")


def test_a_case_level_file_does_not_consume_a_lines_budget(db):
    """The corollary. A receipt attached to the claim must not be the reason an item
    photo is refused - they are counted against different rows."""
    _seed_graphs(db)
    _seed_attachment_type(db, cap=1)
    submission = _submission(db, _definition(db), rows=1, user_id=_user(db))
    db.commit()
    line = _lines(db, submission)[0]

    _upload(db, submission, filename="receipt.png")
    _upload(db, submission, line=line, filename="item.png")


def test_nothing_reaches_the_bucket_when_the_cap_refuses(db, storage):
    """Order of operations, not just the outcome. Uploading first and checking after
    leaves an orphan object per refused attempt - billed, undeletable through the UI
    and invisible to the storage audit, since no row points at it."""
    _seed_graphs(db)
    _seed_attachment_type(db, cap=1)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    _upload(db, submission, filename="one.png")
    stored = set(storage.objects)
    with pytest.raises(AppException):
        _upload(db, submission, filename="two.png")
    assert set(storage.objects) == stored, (
        "the refused upload still wrote bytes: the quota check must run BEFORE the "
        "object is stored."
    )


def test_a_storage_failure_leaves_no_attachment_row_behind(db, storage):
    """The mirror image. A row whose bytes were never written renders as a broken
    link the storage audit reports as ``missing`` forever, and the customer believes
    the photo was received."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    storage.fail_with = RuntimeError("ZZT: bucket unreachable")
    with pytest.raises(AppException) as err:
        _upload(db, submission, filename="lost.png")
    assert err.value.status_code in (500, 502)
    assert (
        db.query(Attachment)
        .filter(Attachment.original_filename == "lost.png")
        .count()
        == 0
    )


# ======================================================= uploader attribution
# A portal upload is by a CONTACT, and a contact has no users.id.


def test_a_portal_upload_is_attributed_to_the_contact_and_to_no_user(db):
    """``uploaded_by`` used to be the only attribution column, so a portal upload's
    NULL meant both "a contact sent it" and "we do not know". The two contact columns
    exist to make that derivable, and a portal path that leaves them unset recreates
    the ambiguity for the one flow that needs it most."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _portal(db).create_submission(
        token, str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()

    result = _portal(db).upload_attachment(
        token,
        str(submission.id),
        contents=PNG_BYTES,
        filename="cracked.png",
        content_type="image/png",
    )
    attachment = (
        db.query(Attachment).filter(Attachment.id == result["attachment_id"]).one()
    )
    assert attachment.uploader_kind == "contact"
    assert attachment.uploaded_by_contact_id == contact.id
    assert attachment.uploaded_by is None, (
        "a contact upload has no users.id; stamping one would put a staff member's "
        "name on a customer's photo in the Files page."
    )


def test_a_staff_upload_is_attributed_to_the_user(db):
    """The other origin, so the panel can say who added a file."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    staff = _user(db)
    submission = _submission(db, _definition(db), rows=0, user_id=staff)
    db.commit()

    attachment = _upload(db, submission, uploaded_by=staff)
    assert attachment.uploader_kind == "user"
    assert str(attachment.uploaded_by) == staff
    assert attachment.uploaded_by_contact_id is None


def test_a_non_uuid_user_id_does_not_break_a_staff_upload(db):
    """``users.id`` is ``String(64)`` and ``attachments.uploaded_by`` is ``uuid``.

    Real ids in this database are not all uuids (the API-key principal is literally
    ``system``), so passing one through unchecked raises "invalid input syntax for
    type uuid" and the upload 500s. The neighbouring paths drop the id and keep the
    file; the KIND must still be recorded, or the row degrades to "unknown origin"
    rather than "a staff member we cannot name".
    """
    _seed_graphs(db)
    _seed_attachment_type(db)
    staff = _user(db, user_id=unique_code("staff").lower())
    submission = _submission(db, _definition(db), rows=0, user_id=staff)
    db.commit()

    attachment = _upload(db, submission, uploaded_by=staff)
    assert attachment.uploader_kind == "user"


def test_a_submission_attachment_is_company_shared(db):
    """The second decision this suite takes.

    ``workflow_submissions`` has no ``company_id``; ``attachments`` does, and its
    scope filter is fail-closed. Stamping a company on the child of an unscoped
    parent means a submission stays visible under a scope where its own evidence has
    disappeared - which reads as data loss, not as a permission. ``Attachment`` is
    already ``__company_shared__``, so NULL is the value the existing machinery
    produces; this pins it so nobody "fixes" it later.
    """
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    attachment = _upload(db, submission)
    assert attachment.company_id is None


def test_a_contact_cannot_upload_to_another_contacts_submission(db):
    """The token IS the authorization. Without an ownership check the only thing
    protecting one customer's claim from another's is the unguessability of its id."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    definition = _definition(db, portal=True)
    owner = _contact(db)
    stranger = _contact(db)
    db.commit()

    submission = _portal(db).create_submission(
        _token(db, owner), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()

    with pytest.raises(AppException) as err:
        _portal(db).upload_attachment(
            _token(db, stranger),
            str(submission.id),
            contents=PNG_BYTES,
            filename="not-mine.png",
            content_type="image/png",
        )
    assert err.value.status_code in (403, 404)


def test_a_contact_cannot_read_another_contacts_evidence(db):
    """Reading is the leak that matters: a warranty claim's photos are the customer's
    own property damage. Scoped in the QUERY, so another contact's row is never
    loaded and never distinguishable from one that does not exist."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    definition = _definition(db, portal=True)
    owner = _contact(db)
    stranger = _contact(db)
    db.commit()

    submission = _portal(db).create_submission(
        _token(db, owner), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()
    _portal(db).upload_attachment(
        _token(db, owner),
        str(submission.id),
        contents=PNG_BYTES,
        filename="mine.png",
        content_type="image/png",
    )

    with pytest.raises(AppException) as err:
        _portal(db).list_attachments(_token(db, stranger), str(submission.id))
    assert err.value.status_code in (403, 404)

    mine = _portal(db).list_attachments(_token(db, owner), str(submission.id))
    assert len(mine) == 1


# =================================================================== AC-F2c-4
# A contact cannot be addressed through notifications.user_id. Since S4 that is
# enforced by respond_contact_id + the XOR recipient check, not by user_id being
# NOT NULL.


def test_the_notification_table_cannot_hold_a_contact():
    """The constraint that shapes the whole notification half of F2c - **restated for S4**.

    As written for F2c this said ``user_id`` is NOT NULL and carries no foreign key,
    so writing a ``respond_contacts.id`` there succeeds, persists, and produces a row
    addressed to a principal that will never log in. That is why the contact path had
    to be a different path.

    **S4 (AC-H1/AC-H2, migration 320) made the recipient two-valued** and the first
    half expired: ``user_id`` is now NULLABLE, because a contact-addressed
    notification has no user. The original *intent* did not expire, and this is now
    how it is enforced - positively, rather than by the absence of a key:

    * ``respond_contact_id`` exists, TEXT, with a real FK onto ``respond_contacts.id``
      (uuid was refused onto a text primary key - AC-H1a). A contact now has its own
      column, so nothing has to smuggle one into ``user_id``.
    * ``notifications_recipient_present`` is an XOR, so a row is addressable by
      EXACTLY ONE of the two. Both set would fan out to two different people
      depending on which query read it first; neither set is undeliverable.

    ``user_id`` still carries no foreign key, and that is asserted below unchanged -
    if it ever gains one pointing at ``users.id``, update this test, but nothing here
    may start relying on the absence of that key to address a contact.
    """
    columns = Notification.__table__.columns
    user_id = columns["user_id"]
    # Nullable since S4: the contact-addressed row has no user. Asserted rather than
    # dropped so a silent revert to NOT NULL (which would make every contact
    # notification unwritable) is caught here.
    assert user_id.nullable is True
    assert list(user_id.foreign_keys) == [], (
        "notifications.user_id gained a foreign key. If it now points at users.id "
        "this test should be updated - but nothing here should be relying on the "
        "absence of that key to smuggle a contact id in."
    )

    # The positive half: a contact has its own column, with a real key onto the
    # contact table, so the smuggling this test was written about has a legitimate
    # destination and no reason to happen.
    contact_id = columns["respond_contact_id"]
    assert contact_id.nullable is True
    assert [fk.column.table.name for fk in contact_id.foreign_keys] == [
        "respond_contacts"
    ], "notifications.respond_contact_id must key onto respond_contacts (AC-H1a)."

    # ...and exactly one of the two is set, so a row can never address both.
    checks = {
        c.name
        for c in Notification.__table__.constraints
        if getattr(c, "sqltext", None) is not None
    }
    assert "notifications_recipient_present" in checks, (
        "The XOR recipient check is gone. Without it a notification can name a user "
        "AND a contact, and the delivery fan-out and the outbox renderer each pick a "
        "different recipient."
    )


def test_a_contact_is_reached_without_writing_a_notification_row(db, respond):
    """The contact-only recipient, end to end.

    ``respond_contacts.id`` is TEXT with no format constraint, so it slots into
    ``notifications.user_id`` without complaint - the write succeeds and the customer
    is never told anything. The contact path must therefore be a different path, and
    it must leave no notification row naming the contact.
    """
    _seed_graphs(db)
    contact = _contact(db, respond_io_id="437264483")
    definition = _definition(db, portal=True)
    db.commit()
    submission = _portal(db).create_submission(
        _token(db, contact), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()

    notify = _notify_module()
    notify.notify_submission_contact(
        db,
        submission,
        title=f"{TEST_PREFIX} update",
        body=f"{TEST_PREFIX} your claim moved",
        event_type="status_changed",
    )

    assert respond.identifiers == ["437264483"], (
        "the send must address the contact's respond_io_id. PortalToken.contact_id "
        "and respond_contacts.respond_io_id are both strings, so swapping them "
        "type-checks and produces a message delivered to nobody."
    )
    assert _notifications_for(db, contact.id) == [], (
        "a notifications row was written naming the contact id in user_id."
    )


def test_a_portal_filed_submission_tells_its_customer_when_it_moves(db, respond):
    """The hole F2c has to close.

    ``_notify_submitter`` reads ``created_by_user_id``, which is NULL for every
    portal filing, and returns early. So today a customer's claim can be approved or
    rejected and the only person told is nobody: the one origin with a real person
    waiting for the answer is the one origin that gets no message.
    """
    _seed_graphs(db)
    contact = _contact(db)
    definition = _definition(db, portal=True)
    staff = _user(db, "decider")
    db.commit()

    submission = _portal(db).create_submission(
        _token(db, contact), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()
    assert submission.created_by_user_id is None

    graph = _header_graph(db)
    WorkflowFormsService(db).apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, staff
    )

    assert respond.calls, (
        "a portal-filed submission moved and its respondent contact was told nothing."
    )
    assert _notifications_for(db, contact.id) == []


def test_a_contact_with_no_respond_io_id_is_not_addressed_by_its_internal_id(db, respond):
    """Most Respond.io-synced contacts have an id; some do not.

    ``PortalToken.contact_id`` holds the INTERNAL ``respond_contacts.id``, and using
    it as the send identifier is a documented recurring bug here. It would not raise:
    Respond.io would simply be handed an id it does not know.
    """
    _seed_graphs(db)
    contact = _contact(db, respond_io_id=None)
    definition = _definition(db, portal=True)
    db.commit()
    submission = _portal(db).create_submission(
        _token(db, contact), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()

    result = _notify_module().notify_submission_contact(
        db, submission, title=f"{TEST_PREFIX} update", body=f"{TEST_PREFIX} body"
    )

    assert contact.id not in respond.identifiers, (
        "the internal contact id was used as the Respond.io identifier."
    )
    assert respond.calls == [], "no send is possible; none should have been attempted"
    assert result is None


def test_an_internal_submission_with_no_contact_notifies_nobody_and_does_not_raise(db, respond):
    """A staff-filed submission legitimately has no respondent. The contact path must
    treat that as "nothing to do", not as an error - it runs on every transition."""
    _seed_graphs(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    assert (
        _notify_module().notify_submission_contact(
            db, submission, title=f"{TEST_PREFIX} t", body=f"{TEST_PREFIX} b"
        )
        is None
    )
    assert respond.calls == []


# =================================================================== AC-F2c-5
# Every Respond.io send writes an integration_log, on success AND on failure.


def test_a_successful_contact_send_writes_an_outbox_row(db):
    """The Respond outbox is the only place a send is auditable. A message that went
    out and left no trace cannot be distinguished from one that was never attempted
    when a customer says they were not told."""
    _seed_graphs(db)
    contact = _contact(db)
    definition = _definition(db, portal=True)
    db.commit()
    submission = _portal(db).create_submission(
        _token(db, contact), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()

    _notify_module().notify_submission_contact(
        db, submission, title=f"{TEST_PREFIX} t", body=f"{TEST_PREFIX} b"
    )

    rows = _outbox(db, submission.id)
    assert len(rows) == 1, f"expected one outbox row, got {len(rows)}"
    assert rows[0].status == "success"
    assert rows[0].direction == "outbound"
    assert rows[0].integration_channel == "respond_io"
    assert rows[0].external_reference == contact.respond_io_id


def test_a_failed_contact_send_still_writes_an_outbox_row(db, respond):
    """Local development runs with deliberately wrong credentials, so the FAILURE
    path is the one a developer actually exercises. A 401 that logs nothing makes the
    outbox look healthy precisely when nothing is being delivered."""
    _seed_graphs(db)
    contact = _contact(db)
    definition = _definition(db, portal=True)
    db.commit()
    submission = _portal(db).create_submission(
        _token(db, contact), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()

    respond.fail_with = RuntimeError("ZZT: 401 Unauthorized")
    _notify_module().notify_submission_contact(
        db, submission, title=f"{TEST_PREFIX} t", body=f"{TEST_PREFIX} b"
    )

    rows = _outbox(db, submission.id)
    assert len(rows) == 1, "a 401'd send left no trace in the Respond outbox"
    assert rows[0].status == "failed"
    assert rows[0].error_message, "the failure must say what went wrong"


def test_the_outbox_row_identifies_its_record_by_a_bare_uuid(db):
    """``integration_log.business_id`` is a ``uuid`` COLUMN.

    A composite identifier (``<user>:<date>:manual:<ts>``) has been written into a
    business_id here before; on a uuid column it aborts the INSERT, so the outbox row
    is lost inside the exception handler that was supposed to record the failure.
    Whatever F2c chooses to point at, it has to be one row's uuid.
    """
    _seed_graphs(db)
    contact = _contact(db)
    definition = _definition(db, portal=True)
    db.commit()
    submission = _portal(db).create_submission(
        _token(db, contact), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()

    _notify_module().notify_submission_contact(
        db, submission, title=f"{TEST_PREFIX} t", body=f"{TEST_PREFIX} b"
    )

    row = _outbox(db, submission.id)[0]
    assert _is_uuid(row.business_id), f"business_id {row.business_id!r} is not a uuid"
    assert row.business_table == WorkflowSubmission.__tablename__, (
        "business_table must name the table business_id is a primary key of, or the "
        "outbox row cannot be joined back to anything. There is no notification row "
        "for a contact-facing send (notifications.user_id is NOT NULL), so the "
        "submission is the only real row this send is about."
    )
    assert (
        db.query(WorkflowSubmission)
        .filter(WorkflowSubmission.id == str(row.business_id))
        .count()
        == 1
    )


# =================================================================== AC-F2c-6
# Notification is a post-commit side effect: catch and warn, never raise.


def _sabotage(monkeypatch):
    """Break every notification channel at once.

    Patched at the sinks rather than at a named hook, so the assertion holds whatever
    shape the notification path takes: whichever of these F2c reaches, the operation
    underneath must still have succeeded.
    """
    from app.services import respond_messaging_service
    from app.services.notification_service import NotificationService

    def _boom(*args, **kwargs):
        raise RuntimeError("ZZT: the notification stack is down")

    monkeypatch.setattr(NotificationService, "create", _boom)
    monkeypatch.setattr(NotificationService, "create_in_app_only", _boom)
    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", _boom)
    monkeypatch.setattr(respond_messaging_service, "send_text_or_template", _boom)
    for name in (NOTIFY_MODULE, ATTACHMENTS_MODULE):
        module = _optional_module(name)
        if module is None:
            continue
        for attr in (
            "send_text_or_template",
            "notify_submission_contact",
            "notify_attachment_added",
        ):
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, _boom)


def test_a_failing_notification_does_not_fail_an_upload(db, monkeypatch):
    """The bytes are in the bucket and the row is committed by the time anyone is
    told. Raising here hands the caller a 502 for an upload that worked, and the
    customer's retry uploads the file a second time."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    _sabotage(monkeypatch)
    attachment = _upload(db, submission, filename="survives.png")

    module = _attachments_module()
    assert len(_links(db, module.SUBMISSION_ENTITY_TYPE, submission.id)) == 1
    assert attachment.id is not None


def test_a_failing_notification_does_not_fail_a_transition(db, monkeypatch):
    """Same rule on the status move, which is worse: a submission that cannot be
    approved because a customer's WhatsApp window is shut is the least acceptable
    failure mode this slice can produce."""
    _seed_graphs(db)
    contact = _contact(db)
    definition = _definition(db, portal=True)
    staff = _user(db, "decider")
    db.commit()
    submission = _portal(db).create_submission(
        _token(db, contact), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()

    _sabotage(monkeypatch)
    graph = _header_graph(db)
    moved = WorkflowFormsService(db).apply_transition(
        str(submission.id), graph.by_key("submitted").id, None, staff
    )
    db.refresh(moved)
    assert moved.status_key == "submitted"


def test_a_failing_notification_leaves_the_session_usable(db, monkeypatch):
    """The subtle half of best-effort. Swallowing the exception is not enough if the
    failure happened mid-flush: the session is then poisoned, and the caller's very
    next read raises PendingRollbackError - a 500 for the same operation, one line
    later, with a stack trace pointing somewhere innocent."""
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    _sabotage(monkeypatch)
    _upload(db, submission, filename="after.png")

    assert (
        db.query(WorkflowSubmission)
        .filter(WorkflowSubmission.id == str(submission.id))
        .count()
        == 1
    )


# =================================================================== AC-F2c-7
# The SLA notify matrix: stage boolean AND per-user per-event toggle.


def test_a_stage_that_does_not_notify_sends_nothing(db):
    """``notify_assignee`` is the master switch, not a per-channel hint. A silent
    stage exists so a high-volume form can be assigned without a message per row."""
    _seed_graphs(db)
    definition = _definition(db)
    member = _user(db, "member")
    _stage(db, definition, notify_assignee=False, member_id=member)
    _submission(db, definition, rows=0, user_id=_user(db))
    db.commit()

    assert _notifications_for(db, member) == []


def test_in_app_always_sends_when_the_stage_allows(db):
    """In-app has no per-user toggle by design: the stage already decided this person
    should be told, and an in-app row is the record of the assignment itself. If it
    were opt-out, a user could silently make their own queue disappear."""
    _seed_graphs(db)
    definition = _definition(db)
    member = _user(db, "member")
    user = db.query(User).filter(User.id == member).one()
    user.notify_email_on_assignment = False
    user.notify_whatsapp_on_assignment = False
    db.flush()
    _stage(db, definition, notify_assignee=True, member_id=member)
    _submission(db, definition, rows=0, user_id=_user(db))
    db.commit()

    notifications = _notifications_for(db, member)
    assert len(notifications) == 1, "the stage allowed the notification and none was sent"
    assert "in_app" in _channels(db, notifications[0].id)


def test_the_users_per_event_email_toggle_gates_email_alone(db):
    """The second half of the matrix. Turning email off must not turn the assignment
    off - the task still has to appear in the assignee's queue."""
    _seed_graphs(db)
    definition = _definition(db)
    member = _user(db, "member")
    user = db.query(User).filter(User.id == member).one()
    user.notify_email_on_assignment = False
    db.flush()
    _stage(db, definition, notify_assignee=True, member_id=member)
    _submission(db, definition, rows=0, user_id=_user(db))
    db.commit()

    notifications = _notifications_for(db, member)
    assert len(notifications) == 1
    channels = _channels(db, notifications[0].id)
    assert "in_app" in channels
    assert "email" not in channels


def test_email_is_sent_when_the_users_toggle_allows_it(db):
    """The control. A matrix test that only ever proves the OFF case would pass
    against an implementation that never sends email at all."""
    _seed_graphs(db)
    definition = _definition(db)
    member = _user(db, "member")
    user = db.query(User).filter(User.id == member).one()
    user.notify_email_on_assignment = True
    db.flush()
    _stage(db, definition, notify_assignee=True, member_id=member)
    _submission(db, definition, rows=0, user_id=_user(db))
    db.commit()

    notifications = _notifications_for(db, member)
    assert len(notifications) == 1
    assert "email" in _channels(db, notifications[0].id)


def test_whatsapp_needs_the_toggle_and_a_linked_respond_contact(db):
    """WhatsApp has a third gate the other channels do not: reachability. A user who
    opted in but is not linked to a RespondContact has no number to send to, and the
    channel is skipped SILENTLY so the other channels still fire."""
    _seed_graphs(db)
    definition = _definition(db)
    member = _user(db, "member")
    user = db.query(User).filter(User.id == member).one()
    user.notify_whatsapp_on_assignment = True
    user.respond_contact_id = None
    db.flush()
    _stage(db, definition, notify_assignee=True, member_id=member)
    _submission(db, definition, rows=0, user_id=_user(db))
    db.commit()

    notifications = _notifications_for(db, member)
    assert len(notifications) == 1
    channels = _channels(db, notifications[0].id)
    assert "whatsapp" not in channels
    assert "in_app" in channels, "an unreachable channel must not suppress the rest"


def test_whatsapp_is_sent_when_the_user_is_both_opted_in_and_reachable(db):
    """The one arrangement that produces a WhatsApp delivery, so the gate above is a
    gate rather than a channel nobody wired up."""
    _seed_graphs(db)
    definition = _definition(db)
    member = _user(db, "member")
    contact = _contact(db)
    user = db.query(User).filter(User.id == member).one()
    user.notify_whatsapp_on_assignment = True
    user.respond_contact_id = contact.id
    db.flush()
    _stage(db, definition, notify_assignee=True, member_id=member)
    _submission(db, definition, rows=0, user_id=_user(db))
    db.commit()

    notifications = _notifications_for(db, member)
    assert len(notifications) == 1
    assert "whatsapp" in _channels(db, notifications[0].id)


def test_the_assignee_of_a_submission_is_told_when_evidence_arrives(db):
    """The reason F2c needs the SLA at all.

    A customer uploading the photo the adjudicator asked for is the event that
    unblocks the case, and nothing else surfaces it: the file appears on a detail
    page nobody has a reason to reopen. The recipient is the active tracker's
    assignee, because that is the only definition of "who is handling this" the
    platform has.
    """
    _seed_graphs(db)
    _seed_attachment_type(db)
    definition = _definition(db, portal=True)
    member = _user(db, "member")
    _stage(db, definition, notify_assignee=True, member_id=member)
    contact = _contact(db)
    db.commit()

    submission = _portal(db).create_submission(
        _token(db, contact), str(definition.id), {"title": f"{TEST_PREFIX} answer"}, []
    )
    db.commit()
    assigned = (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type == WORKFLOW_SUBMISSION_ENTITY_TYPE,
            ConversationSLATracking.source_entity_id == str(submission.id),
        )
        .all()
    )
    assert assigned, "arrangement failed: the stage started no clock"
    before = len(_notifications_for(db, member))

    _portal(db).upload_attachment(
        _token(db, contact),
        str(submission.id),
        contents=PNG_BYTES,
        filename="cracked.png",
        content_type="image/png",
    )

    after = _notifications_for(db, member)
    assert len(after) > before, (
        "the customer sent the evidence the case was waiting on and the person "
        "handling it was told nothing."
    )


def test_an_upload_on_a_submission_nobody_is_handling_notifies_nobody(db):
    """The day-one case, and it must be silent rather than broken.

    F2a's stage seed deliberately creates no teams (a migration cannot invent
    members), so on a fresh install ``_start_for_config`` raises, ``emit_event``
    swallows it, and there is no tracker and therefore no assignee. An upload then
    has no recipient at all, which has to be a no-op and not an exception.
    """
    _seed_graphs(db)
    _seed_attachment_type(db)
    submission = _submission(db, _definition(db), rows=0, user_id=_user(db))
    db.commit()

    _upload(db, submission, filename="unwatched.png")
    assert (
        db.query(Notification)
        .filter(Notification.source_entity_id == str(submission.id))
        .count()
        == 0
    )


# --------------------------------------------------------------------- support


def storage_objects() -> dict:
    """The fake bucket's contents, reachable from a test that did not request the
    fixture by name (the autouse fixture is the same instance)."""
    from app.services import storage_router

    return storage_router.get_backend(None).objects
