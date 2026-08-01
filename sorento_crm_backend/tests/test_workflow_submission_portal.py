"""F2b gate - a CONTACT files a workflow submission from the portal.

F1/F1a/F2a built the submission for a logged-in user: a ``users.id`` created it, a
``users.id`` moved it, and an SLA clock started when it was created. F2b opens the
same document to somebody with no CRM login at all, arriving through the existing
portal token. That changes three things at once, and each has a trap that nothing
shouts about:

1. **Portal-submittable must be DEFAULT CLOSED.** Every other gate in this codebase
   fails OPEN - role gating allows when no roles are declared, lookup validation
   passes an unbound field, an empty market-segment set matches every CS member. The
   local habit is therefore exactly wrong here: a form is internal until somebody
   says otherwise, because this is the one place where fail-open hands a customer a
   form nobody meant them to see (AC-F2b-2).
2. **``respondent_contact_id`` must be ``String``, never ``UUID``.**
   ``respond_contacts.id`` is a **TEXT** column, and a ``uuid`` column cannot hold a
   foreign key to a text one. ``workflow_submissions`` is otherwise full of uuid
   FKs, so matching its neighbours is the natural instinct and it is what breaks
   (AC-F2b-1). Same trap as ``users.id`` in AC-F1-16.
3. **``PortalToken.contact_id`` is the INTERNAL ``respond_contacts.id``, not the
   Respond.io id.** Both are strings, so swapping them type-checks, persists, and
   produces an inbox URL that opens nothing. And the URL has to be written AT ROW
   CREATION or the admin chat panel renders empty - a documented recurring bug in
   this repo, not a hypothetical (AC-F2b-3, AC-F2b-4).

Plus the quiet one: a portal-created submission must go through the SAME creation
path as an internal one, or the F0 answer validation, the F2a ``submission_created``
SLA event and the publish gate are all skipped for exactly the submissions a
customer filed. This file asserts all three as behaviour rather than as call counts.

Every test traces to an AC in
``documentation/plans/forms-platform/forms-platform-acceptance-criteria.md``,
Group F2b (AC-F2b-1..5).

Run: venv/bin/pytest tests/test_workflow_submission_portal.py -q -p no:randomly
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.database import Base
from app.form_engine.schemas import FORM_SCHEMA_VERSION
from app.models.access import (
    AccessAgent,
    AgentTeam,
    ContactAccessType,
    RespondContact,
    Team,
    TeamMember,
    respond_contact_access_types,
)
from app.models.portal import PortalToken
from app.models.sla import (
    ConversationSLATracking,
    FormSLAConfig,
    SLAPolicy,
    SLAPolicyTier,
)
from app.models.user import User
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmission,
)
from app.services.error_handler import AppException
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

# The one module F2b is expected to add. It owns the portal-submittability gate and
# the contact-scoped read/write path, so the rule that decides "may this contact
# file this form" lives beside the code that acts on the answer.
PORTAL_MODULE = "app.services.workflow_submission_portal"

# The repeater every submission in this file files its lines under.
LINE_GROUP = "items"

# The space the portal token is scoped to. Arbitrary - ``portal_tokens.space_id`` is
# free text with no FK - but it must reappear verbatim in the inbox URL.
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
def notifications(monkeypatch):
    """Record every notification instead of sending one.

    A spawned SLA stage notifies its assignee, and that path reaches email and
    WhatsApp. Nothing in F2b is about the message, so it is recorded and dropped.
    """
    from app.services.notification_service import NotificationService

    sent: list[dict] = []
    monkeypatch.setattr(
        NotificationService,
        "create_with_channel_preferences",
        lambda self, **kwargs: sent.append(kwargs),
    )
    monkeypatch.setattr(
        NotificationService, "create", lambda self, **kwargs: sent.append(kwargs)
    )
    return sent


@pytest.fixture(autouse=True)
def _no_queue(monkeypatch):
    """SLA side effects enqueue Respond.io work. A live Redis is not a dependency
    of a test about who is allowed to file a form."""
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    yield


# ---------------------------------------------------------------------- helpers


def _portal_module():
    """Import the module F2b adds, or fail naming the contract it is missing."""
    if importlib.util.find_spec(PORTAL_MODULE) is None:
        raise AssertionError(
            f"{PORTAL_MODULE} does not exist. F2b needs one module owning the "
            "portal-submittability gate and the contact-scoped submission path, so "
            "the rule that decides whether a contact may file a form cannot drift "
            "away from the code that writes their answer."
        )
    return importlib.import_module(PORTAL_MODULE)


def _portal(db):
    """The service under test."""
    module = _portal_module()
    service = getattr(module, "WorkflowSubmissionPortalService", None)
    assert callable(service), (
        f"{PORTAL_MODULE}.WorkflowSubmissionPortalService(db) must exist: the portal "
        "path needs its own service so a contact-scoped create can never be reached "
        "by the user-scoped one, which takes a users.id it does not have."
    )
    return service(db)


def _seed_graphs(db):
    """Both default graphs seeded, both entities registered."""
    seed_workflow_submission_status_graph(db)
    seed_workflow_submission_line_status_graph(db)
    db.flush()
    register_workflow_submission_status_entity()
    register_workflow_submission_line_status_entity()


def _user(db, label: str = "staff") -> str:
    """A real ``users`` row. The attribution columns are foreign keys to
    ``users.id`` and Postgres enforces them, so an invented id aborts the
    transaction."""
    user_id = unique_code(label).lower()
    db.add(
        User(
            id=user_id,
            email=f"{user_id}@{TEST_PREFIX.lower()}.invalid",
            name=f"{TEST_PREFIX} {label}",
            status="ACTIVE",
        )
    )
    db.flush()
    return user_id


def _access_type(db, code: str) -> str:
    """A ``contact_access_types`` row, which the association table foreign-keys to."""
    code = code.lower()
    if db.query(ContactAccessType).filter(ContactAccessType.code == code).first() is None:
        db.add(ContactAccessType(code=code, name=code.replace("_", " ").title()))
        db.flush()
    return code


def _contact(db, *, respond_io_id: str | None = "437264483", kinds=()) -> RespondContact:
    """A ``respond_contacts`` row whose id is deliberately NOT a uuid.

    ``respond_contacts.id`` is a TEXT column with a uuid-shaped default, and every
    test that seeds a uuid there would keep passing against a ``uuid`` FK column.
    A non-uuid id is what makes AC-F2b-1's type requirement observable rather than
    decorative, and it is legal data: the column has no format constraint.
    """
    contact_id = unique_code("contact").lower()
    contact = RespondContact(
        id=contact_id,
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name=f"{TEST_PREFIX} contact",
        respond_io_id=respond_io_id,
    )
    db.add(contact)
    db.flush()
    for kind in kinds:
        db.execute(
            respond_contact_access_types.insert().values(
                contact_id=contact_id, access_type_code=_access_type(db, kind)
            )
        )
    db.flush()
    db.refresh(contact)
    return contact


def _token(db, contact: RespondContact) -> PortalToken:
    """An OTP-verified, live portal token - the credential the portal already uses.

    ``contact_id`` holds the INTERNAL ``respond_contacts.id``, which is the whole
    point of AC-F2b-4: nothing downstream may treat it as the Respond.io id.
    """
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


def _definition(db, *, publish: bool = True, portal=None, kinds=()) -> WorkflowFormDefinition:
    """A definition, built by hand so a broken service reads as one failure not ten.

    ``portal`` is tri-state on purpose. ``None`` touches neither portal column, which
    is the arrangement AC-F2b-2's default-closed test needs: a definition somebody
    created without thinking about the portal at all.
    """
    definition = WorkflowFormDefinition(
        id=str(uuid.uuid4()),
        code=unique_code("wfdef").lower(),
        name=f"{unique_code('Form')} definition",
        draft_schema=FORM_DOC,
    )
    db.add(definition)
    db.flush()
    if publish:
        version = WorkflowFormVersion(
            id=str(uuid.uuid4()),
            definition_id=definition.id,
            version_number=1,
            schema=FORM_DOC,
        )
        db.add(version)
        db.flush()
        definition.published_version_id = version.id
    if portal is not None:
        _declare_portal(definition, submittable=portal, kinds=kinds)
    db.flush()
    return definition


def _declare_portal(definition, *, submittable: bool, kinds=()) -> None:
    """Declare the definition's portal stance.

    ``setattr`` rather than constructor kwargs so a missing column fails the ONE
    structural test that names it, instead of raising the same TypeError out of
    every fixture in the file.
    """
    setattr(definition, "portal_submittable", submittable)
    setattr(definition, "portal_party_kinds", list(kinds))


def _answers(suffix: str = "") -> dict:
    return {"title": f"{TEST_PREFIX} answer{suffix}"}


def _rows(count: int = 1) -> list[dict]:
    return [
        {"line_group_id": LINE_GROUP, "row_data": {"model": f"{TEST_PREFIX}-{i}"}}
        for i in range(count)
    ]


def _create(db, token, definition, *, header=None, lines=None, **extra):
    return _portal(db).create_submission(
        token,
        str(definition.id),
        _answers() if header is None else header,
        _rows() if lines is None else lines,
        **extra,
    )


def _column(model, name):
    return model.__table__.columns.get(name)


# ---- SLA scaffolding, for the "does a portal submit start a clock" question ----


def _policy(db) -> str:
    policy_id = str(uuid.uuid4())
    code = unique_code("pol").upper()
    db.add(SLAPolicy(id=policy_id, code=code, name=code))
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
    return policy_id


def _stage(db, definition, *, start_event: str) -> FormSLAConfig:
    """One ``workflow_submission`` SLA stage, scoped to this definition.

    Scoped because ``emit_event`` selects every active config for the TYPE and
    ``workflow_submission`` is one type for every definition (AC-F2a-10): an
    unscoped stage here would also clock the submissions of every other test in
    the file.
    """
    agent_id = str(uuid.uuid4())
    agent_code = unique_code("agent").lower()
    db.add(AccessAgent(id=agent_id, code=agent_code, name=f"{TEST_PREFIX} agent"))
    db.flush()

    member = _user(db, "member")
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

    config = FormSLAConfig(
        id=str(uuid.uuid4()),
        source_entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
        stage_code="main",
        policy_id=_policy(db),
        agent_code=agent_code,
        team_set_code="main",
        definition_id=str(definition.id),
        start_event=start_event,
        resolve_event=None,
        advance_on_event=None,
        is_active=True,
        notify_assignee=True,
    )
    db.add(config)
    db.commit()
    return config


def _trackers(db, submission_id: str) -> list[ConversationSLATracking]:
    return (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type
            == WORKFLOW_SUBMISSION_ENTITY_TYPE,
            ConversationSLATracking.source_entity_id == str(submission_id),
        )
        .all()
    )


# =================================================================== AC-F2b-2
# Default closed. The highest-value block in the file: this is the one gate in the
# forms platform where the wrong default exposes data rather than merely annoying
# somebody, and it is the opposite of every other default in this codebase.


def test_a_definition_declares_whether_it_is_portal_submittable():
    """Without a column there is nowhere to record the decision, so the gate would
    have to be inferred from something else - and every candidate (is_active, has a
    published version, has a status graph) is true of an internal form too."""
    column = _column(WorkflowFormDefinition, "portal_submittable")
    assert column is not None, (
        "workflow_form_definitions.portal_submittable is missing: a definition has "
        "nowhere to declare that it is open to the portal."
    )
    assert column.nullable is False, (
        "portal_submittable must be NOT NULL. NULL is a third state nobody defines, "
        "and whichever way a reader coerces it is a guess about whether a customer "
        "may see the form."
    )


def test_the_portal_stance_of_an_existing_definition_defaults_to_closed():
    """A server_default, not just a Python default.

    The migration adds this column to definitions that already exist, and those rows
    are backfilled by the DATABASE. A Python-side ``default=False`` never runs for
    them, so without a server default the migration either fails on NOT NULL or
    leaves every existing form in whatever state the DDL picked.
    """
    column = _column(WorkflowFormDefinition, "portal_submittable")
    assert column is not None and column.server_default is not None, (
        "portal_submittable needs a server_default of false, or the ALTER that adds "
        "it cannot backfill the definitions that already exist."
    )
    assert "false" in str(column.server_default.arg).lower(), (
        "the server default must be false. Defaulting to true would open every form "
        "that exists today to the portal the moment the migration runs."
    )


def test_a_definition_created_without_a_portal_stance_reads_as_closed(db):
    """The round trip, not just the DDL: what a reader actually gets back.

    Read after a commit and an expire, so the value comes from Postgres rather than
    from the instance the test just built.
    """
    _seed_graphs(db)
    definition = _definition(db)
    db.commit()
    db.expire(definition)
    assert getattr(definition, "portal_submittable") is False


def test_a_definition_that_never_opened_the_portal_cannot_be_submitted_from_it(db):
    """The behaviour the default protects. A form nobody opened is internal, and a
    contact holding a perfectly valid portal token still cannot file it."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db)
    db.commit()

    with pytest.raises(AppException) as err:
        _create(db, token, definition)
    assert err.value.status_code == 403
    assert err.value.detail["code"] == "portal_not_submittable"
    assert (
        db.query(WorkflowSubmission)
        .filter(WorkflowSubmission.definition_id == definition.id)
        .count()
        == 0
    ), "the refusal must happen before the row is written, not after"


def test_a_definition_explicitly_opened_to_the_portal_can_be_submitted(db):
    """The other half of the gate. A default-closed rule that also refuses the
    forms somebody deliberately opened is not a gate, it is an outage."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    assert submission.id is not None
    assert str(submission.definition_id) == str(definition.id)
    assert submission.respondent_contact_id == contact.id


def test_the_party_kind_a_definition_declares_is_honoured(db):
    """A dealer-only warranty claim must refuse an end user holding a valid token.

    The asker's kind comes from the contact's ``contact_access_types`` - the same
    codes that already gate promotion and attachment visibility - because that is
    the only classification a PortalToken can reach: the token carries a contact id
    and nothing else.
    """
    _seed_graphs(db)
    definition = _definition(db, portal=True, kinds=("dealer",))
    dealer = _contact(db, kinds=("dealer",))
    end_user = _contact(db, kinds=("end_user",))
    db.commit()

    with pytest.raises(AppException) as err:
        _create(db, _token(db, end_user), definition)
    assert err.value.status_code == 403
    assert err.value.detail["code"] == "portal_not_submittable"

    allowed = _create(db, _token(db, dealer), definition)
    assert allowed.respondent_contact_id == dealer.id


def test_a_definition_declaring_no_party_kind_is_open_to_every_contact(db):
    """Empty means "no narrowing", which is safe only because the boolean is the door.

    Two columns, one meaning each: ``portal_submittable`` decides whether the form is
    on the portal at all, ``portal_party_kinds`` narrows who sees it. An empty list
    therefore reads the way every other filter list in this codebase reads. It is not
    a fail-open, because reaching it took a deliberate flip of the boolean - and
    without this reading, a contact with no access types assigned (the common case)
    could never file anything.
    """
    _seed_graphs(db)
    definition = _definition(db, portal=True, kinds=())
    unclassified = _contact(db, kinds=())
    db.commit()

    submission = _create(db, _token(db, unclassified), definition)
    assert submission.respondent_contact_id == unclassified.id


def test_the_portal_party_kinds_column_defaults_to_no_narrowing(db):
    """A definition that never declared kinds must read as an empty list, not NULL.

    NULL and ``[]`` would then both have to mean "everyone", and the first reader to
    write ``if definition.portal_party_kinds:`` gets it right for one of them only.
    """
    column = _column(WorkflowFormDefinition, "portal_party_kinds")
    assert column is not None, (
        "workflow_form_definitions.portal_party_kinds is missing: AC-F2b-2 requires "
        "the definition to declare BY WHICH PARTY KIND it is submittable."
    )
    assert column.nullable is False and column.server_default is not None

    _seed_graphs(db)
    definition = _definition(db)
    db.commit()
    db.expire(definition)
    assert list(getattr(definition, "portal_party_kinds")) == []


def test_a_closed_definition_never_appears_in_the_portal_form_list(db):
    """The listing is its own exposure. A refusal on submit still leaks the names of
    every internal form to a customer if the picker lists them."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    open_definition = _definition(db, portal=True)
    closed_definition = _definition(db)
    db.commit()

    listed = {str(item["id"]) for item in _portal(db).list_definitions(token)}
    assert str(open_definition.id) in listed
    assert str(closed_definition.id) not in listed


def test_a_definition_open_to_another_party_kind_is_not_listed(db):
    """Same exposure, narrower: the picker must apply the party-kind narrowing too,
    or a dealer-only form is advertised to every end user who opens the portal."""
    _seed_graphs(db)
    dealer_only = _definition(db, portal=True, kinds=("dealer",))
    everyone = _definition(db, portal=True, kinds=())
    end_user = _contact(db, kinds=("end_user",))
    db.commit()

    listed = {str(item["id"]) for item in _portal(db).list_definitions(_token(db, end_user))}
    assert str(everyone.id) in listed
    assert str(dealer_only.id) not in listed


def test_the_definition_serializer_exposes_the_portal_stance(db):
    """``_def_out`` is a MANUAL dict builder, and a field it does not name never
    reaches the frontend however correctly it is stored.

    This is the ``get_user`` / ``system_settings`` bug family: the builder toggle
    saves, the page reloads, and the switch is back off - which reads as a broken
    save rather than a missing key.
    """
    _seed_graphs(db)
    definition = _definition(db, portal=True, kinds=("dealer",))
    db.commit()

    out = WorkflowFormsService(db)._def_out(definition)
    assert out.get("portal_submittable") is True, (
        "_def_out does not emit portal_submittable, so the builder toggle reads as "
        f"{out.get('portal_submittable')!r} however it was saved"
    )
    assert list(out.get("portal_party_kinds") or []) == ["dealer"], (
        "_def_out does not emit portal_party_kinds, so the declared party kinds "
        "never reach the builder"
    )


# =================================================================== AC-F2b-3
# respond_inbox_url, written at row creation and never writable from a payload.


def test_a_portal_created_submission_carries_its_inbox_url_at_row_creation(db):
    """Set at creation, not backfilled.

    The admin chat panel reads this column when it opens the submission. A row that
    starts NULL renders an empty conversation with no error anywhere, which is why
    the portal's four bespoke forms were shipped with the same bug.
    """
    _seed_graphs(db)
    contact = _contact(db, respond_io_id="437264483")
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    assert submission.respond_inbox_url, (
        "workflow_submissions.respond_inbox_url is empty on a freshly created portal "
        "row: the admin chat panel will render nothing for this submission."
    )
    assert submission.respond_inbox_url.endswith(f"/space/{SPACE_ID}/inbox/437264483")


def test_a_portal_payload_cannot_write_the_inbox_url(db):
    """A contact must not be able to blank or redirect the admin's chat link.

    Sent as an answer AND as a top-level field, because the two plausible
    implementations differ: header answers land in JSONB, and a ``_editable_fields``
    style setattr loop lands on the column. Neither may move it.
    """
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    original = submission.respond_inbox_url
    assert original

    _portal(db).update_submission(
        token,
        str(submission.id),
        {**_answers(" edited"), "respond_inbox_url": None},
        None,
    )
    db.expire(submission)
    assert submission.respond_inbox_url == original

    _portal(db).update_submission(
        token,
        str(submission.id),
        {**_answers(" again"), "respond_inbox_url": "https://evil.invalid/inbox/1"},
        None,
    )
    db.expire(submission)
    assert submission.respond_inbox_url == original


def test_the_inbox_url_is_not_stored_among_the_answers(db):
    """``header_data`` is the contact's answers. Parking an admin-only URL in there
    would put it inside the document the contact can read back and re-post."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    assert "respond_inbox_url" not in (submission.header_data or {})


# =================================================================== AC-F2b-4
# The internal contact id and the Respond.io id are both strings. Swapping them
# type-checks, persists, and produces a link that opens nothing.


def test_the_inbox_url_names_the_respond_io_id_not_the_internal_contact_id(db):
    """``PortalToken.contact_id`` is the INTERNAL ``respond_contacts.id``.

    The Respond.io inbox path needs ``respond_io_id``. Because both columns are
    text, an implementation that pipes the token's contact id straight into the URL
    produces a well-formed, persistent, permanently dead link, and the only symptom
    is a chat panel that never loads.
    """
    _seed_graphs(db)
    contact = _contact(db, respond_io_id="1234567890")
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    url = submission.respond_inbox_url or ""
    assert url.endswith("/inbox/1234567890")
    assert contact.id not in url, (
        "the internal respond_contacts.id reached the inbox URL: the URL must be "
        "built from the resolved respond_io_id"
    )


def test_a_contact_with_no_respond_io_id_gets_no_inbox_url_rather_than_a_dead_one(db):
    """The failure mode the mix-up hides behind.

    A contact created by an import or by the portal itself may have no Respond.io id
    at all. An implementation that falls back to the internal id writes a link that
    looks right in the database and 404s in the browser. No link is honest; a wrong
    link is not.
    """
    _seed_graphs(db)
    contact = _contact(db, respond_io_id=None)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    assert submission.respond_inbox_url is None
    assert submission.respondent_contact_id == contact.id, (
        "the submission must still record WHO filed it - only the chat link is absent"
    )


# =================================================================== AC-F2b-1
# The columns, their types, and what a user-created submission still looks like.


def test_the_respondent_contact_column_is_a_string_not_a_uuid():
    """``respond_contacts.id`` is TEXT, so a ``uuid`` column cannot foreign-key to it.

    Every other FK on ``workflow_submissions`` is a uuid, which makes matching them
    the natural instinct and the exact thing that breaks - same trap as ``users.id``
    in AC-F1-16. The migration fails outright if it is wrong, but the model can drift
    from the migration, and then the error is an unreadable operator-does-not-exist.
    """
    column = _column(WorkflowSubmission, "respondent_contact_id")
    assert column is not None, "workflow_submissions.respondent_contact_id is missing"
    assert not isinstance(column.type, PG_UUID), (
        "respondent_contact_id is a uuid column. respond_contacts.id is TEXT; a uuid "
        "column cannot hold a foreign key to it."
    )
    assert isinstance(column.type, String)
    assert column.nullable is True, (
        "it must stay nullable: every submission filed by a logged-in user has no "
        "respondent contact at all"
    )
    targets = {str(fk.target_fullname) for fk in column.foreign_keys}
    assert targets == {"respond_contacts.id"}, (
        f"respondent_contact_id must foreign-key to respond_contacts.id, got {targets}"
    )


def test_a_non_uuid_contact_id_round_trips_through_the_column(db):
    """The behavioural proof, which a type assertion alone cannot give.

    ``respond_contacts.id`` has a uuid-shaped default but no format constraint, so
    real rows can hold anything. A ``uuid`` column would reject this insert; a
    ``varchar`` one stores it. Nothing else in the file would notice the difference,
    because every other contact id it creates happens to be uuid-shaped.
    """
    _seed_graphs(db)
    contact = _contact(db)
    assert "-" in contact.id and len(contact.id) != 36, (
        "this test is only meaningful with a non-uuid contact id"
    )
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    db.commit()
    db.expire(submission)
    assert submission.respondent_contact_id == contact.id


def test_the_source_entity_columns_exist_and_are_nullable_strings():
    """A submission points back at whatever spawned it, and the pointer is
    polymorphic: ``source_entity_type`` names the table.

    ``String``, not ``uuid``. The pair mirrors ``conversation_sla_tracking``'s in
    name, where ``source_entity_id`` is a uuid column, but that pair only ever holds
    the five form types and all five have uuid primary keys. This one is meant to
    point at whatever spawned an after-sales form, and the candidates include tables
    keyed by text (``respond_contacts``, ``users``). A varchar accepts a uuid string;
    the reverse is not true, so String is the strictly wider choice.
    """
    for name in ("source_entity_type", "source_entity_id"):
        column = _column(WorkflowSubmission, name)
        assert column is not None, f"workflow_submissions.{name} is missing"
        assert column.nullable is True, (
            f"{name} must be nullable: most submissions are spawned by nobody"
        )
        assert not isinstance(column.type, PG_UUID), (
            f"{name} is a uuid column; a polymorphic pointer cannot assume every "
            "target table has a uuid primary key"
        )
        assert isinstance(column.type, String)


def test_a_portal_submission_can_point_back_at_whatever_spawned_it(db):
    """The pair is only useful if the portal path can actually set it - an
    after-sales claim is filed FROM an order, and losing that link means the claim
    arrives with no idea what it is about."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    origin_id = str(uuid.uuid4())
    submission = _create(
        db, token, definition, source_entity_type="order", source_entity_id=origin_id
    )
    db.commit()
    db.expire(submission)
    assert submission.source_entity_type == "order"
    assert submission.source_entity_id == origin_id


def test_a_user_created_submission_still_has_no_respondent_contact(db):
    """Today's behaviour, pinned. The internal create path gains three nullable
    columns and must keep writing nothing to any of them - a default that stamped
    something here would attribute every staff-filed form to a contact."""
    _seed_graphs(db)
    user_id = _user(db)
    definition = _definition(db)
    db.commit()

    submission = WorkflowFormsService(db).create_submission(
        str(definition.id), _answers(), _rows(), user_id
    )
    assert submission.created_by_user_id == user_id
    assert submission.respondent_contact_id is None
    assert submission.source_entity_type is None
    assert submission.source_entity_id is None


def test_a_portal_submission_is_attributed_to_the_contact_and_to_no_user(db):
    """The mirror image. Nobody logged in, so ``created_by_user_id`` must stay NULL.

    Stamping a service account there would put a real person's name on every
    customer's filing, in the audit trail and on the detail page, and
    ``resolved_by``-style auto-attribution has already been rejected once for
    exactly this reason (AC-F1a-29).
    """
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    assert submission.respondent_contact_id == contact.id
    assert submission.created_by_user_id is None


# =================================================================== AC-F2b-5
# One token scheme. The portal already has PortalToken + OTP; a submission must not
# grow a second one.


def test_no_second_token_table_appears_for_workflow_submissions():
    """A per-submission token would be a second credential with its own expiry,
    revocation and delivery path, none of which the OTP flow knows about - so
    revoking a contact's portal access would leave the other one live."""
    offenders = sorted(
        name
        for name in Base.metadata.tables
        if ("token" in name or "otp" in name)
        and name not in ("portal_tokens", "portal_otp_codes")
        and ("submission" in name or "workflow" in name or "form" in name)
    )
    assert offenders == [], (
        f"a second token scheme appeared for submissions: {offenders}. AC-F2b-5 "
        "requires the portal surface to reuse PortalToken + OTP."
    )


def test_a_submission_carries_no_bespoke_token_column():
    """The cheaper version of the same mistake: a token column on the row itself.

    It would be a shareable credential embedded in the record, invisible to
    ``revoke_token`` and to the OTP gate.
    """
    offenders = sorted(
        column.name
        for column in WorkflowSubmission.__table__.columns
        if "token" in column.name or "otp" in column.name or "secret" in column.name
    )
    assert offenders == [], (
        f"workflow_submissions grew its own credential column(s): {offenders}"
    )


def test_a_token_for_another_contact_cannot_read_a_submission(db):
    """The token IS the authorization, which is what makes one scheme sufficient.

    If ownership were not scoped by ``token.contact_id``, the only thing protecting
    one customer's warranty claim from another's would be the unguessability of its
    id - which is precisely the bespoke-token design AC-F2b-5 refuses.
    """
    _seed_graphs(db)
    owner = _contact(db)
    stranger = _contact(db)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, _token(db, owner), definition)
    db.commit()

    with pytest.raises(AppException) as err:
        _portal(db).get_submission(_token(db, stranger), str(submission.id))
    assert err.value.status_code in (403, 404)


def test_the_portal_lists_only_the_tokens_own_submissions(db):
    """Same rule on the collection. A listing scoped by definition rather than by
    contact would show every customer the whole queue."""
    _seed_graphs(db)
    owner = _contact(db)
    stranger = _contact(db)
    definition = _definition(db, portal=True)
    db.commit()

    mine = _create(db, _token(db, owner), definition)
    theirs = _create(db, _token(db, stranger), definition)
    db.commit()

    listed = {str(getattr(row, "id", None) or row["id"]) for row in _portal(db).list_submissions(_token(db, owner))}
    assert str(mine.id) in listed
    assert str(theirs.id) not in listed


# ============================================== the same contract as an internal
# submission: F0 answer validation and the publish gate.


def test_a_portal_submission_runs_the_same_answer_validation(db):
    """A contact must not be able to file an answer set a user could not.

    The document contract lives in ``validate_submission`` and is reached through
    ``WorkflowFormsService.create_submission``. A portal path that builds the row by
    hand - which is exactly what ``_instantiate`` does for the four bespoke forms -
    skips it, and the only submissions that skip it are the ones nobody at Sorento
    typed.
    """
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    with pytest.raises(AppException) as err:
        _create(db, token, definition, header={})
    assert err.value.status_code == 422
    assert err.value.detail["code"] == "form_answers_invalid"


def test_a_portal_submission_cannot_name_a_line_group_the_form_does_not_have(db):
    """The other half of the F0 contract. A row filed under an unknown group is
    invisible to every grid and export, so it is refused rather than stored."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    with pytest.raises(AppException) as err:
        _create(
            db,
            token,
            definition,
            lines=[{"line_group_id": "not_a_group", "row_data": {}}],
        )
    assert err.value.status_code == 422
    assert err.value.detail["code"] == "line_group_unknown"


def test_an_unpublished_definition_cannot_be_submitted_from_the_portal(db):
    """The publish gate is what makes a version immutable, and a submission always
    points at the version it was answered against. A portal create against a draft
    would have no version to reference and no fixed document to have validated."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, publish=False, portal=True)
    db.commit()

    with pytest.raises(AppException) as err:
        _create(db, token, definition)
    assert err.value.status_code in (400, 403)


def test_a_portal_submission_records_the_version_it_answered(db):
    """Cheap, and it is the tell for a hand-rolled create: a row built outside
    ``create_submission`` has to pick a version itself, and the shortcut is to reach
    for the definition's draft."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    db.commit()

    submission = _create(db, token, definition)
    assert str(submission.version_id) == str(definition.published_version_id)


# ================================== does a portal submit start an SLA clock? YES.
# F2a emits `submission_created` from WorkflowFormsService.create_submission. If the
# portal builds its row any other way, the clock never starts for exactly the
# submissions a customer filed - and nothing anywhere reports that, because an SLA
# that was never started looks identical to one nobody configured.


def test_a_portal_created_submission_starts_its_sla_clock(db):
    """A customer's filing is the one that most needs a deadline on it.

    Asserted through the tracker rather than through a call count: what matters is
    that somebody is on the hook, not which function emitted the event.
    """
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    _stage(db, definition, start_event=SUBMISSION_CREATED_EVENT)
    db.commit()

    submission = _create(db, token, definition)
    trackers = _trackers(db, str(submission.id))
    assert len(trackers) == 1, (
        "a portal-created submission started no SLA clock. F2a emits "
        f"'{SUBMISSION_CREATED_EVENT}' from WorkflowFormsService.create_submission; a "
        "portal path that builds the row itself silently skips it."
    )
    assert trackers[0].assigned_to_id is not None
    assert trackers[0].is_resolved is False


def test_the_clock_a_portal_submission_starts_knows_the_contact(db):
    """``conversation_sla_tracking.respond_contact_id`` is how the assignee reaches
    the person who filed it.

    Without it the tracker has a deadline and no way to reply: the WhatsApp channel
    on an SLA notification needs a linked RespondContact, and the CS pin lookup keys
    on the contact too. An internal submission legitimately has none, so this is the
    one field the portal path must add that the user path cannot.
    """
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db, portal=True)
    _stage(db, definition, start_event=SUBMISSION_CREATED_EVENT)
    db.commit()

    submission = _create(db, token, definition)
    trackers = _trackers(db, str(submission.id))
    assert len(trackers) == 1
    assert trackers[0].respond_contact_id == contact.id, (
        "the spawned tracker does not know which contact filed the submission"
    )


def test_a_refused_portal_submission_starts_no_clock(db):
    """The gate runs before anything else. A stage that spawned on a submission the
    portal then refused would leave a live tracker pointing at no row."""
    _seed_graphs(db)
    contact = _contact(db)
    token = _token(db, contact)
    definition = _definition(db)
    _stage(db, definition, start_event=SUBMISSION_CREATED_EVENT)
    db.commit()

    with pytest.raises(AppException):
        _create(db, token, definition)
    assert (
        db.query(ConversationSLATracking)
        .filter(
            ConversationSLATracking.source_entity_type
            == WORKFLOW_SUBMISSION_ENTITY_TYPE
        )
        .count()
        == 0
    )
