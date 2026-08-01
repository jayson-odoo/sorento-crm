"""Tests for the workflow forms service, rewritten for the F1 shape (AC-F1-10).

What changed under this file. The old version pinned a state machine embedded in
``workflow_form_versions.schema``: ``default_draft_schema`` shipped four states and four
transitions, and ``validate_schema`` / ``validate_submission_payload`` were a second
validator over the same JSONB column that F0's ``app.form_engine`` already owned. F1
deletes that surface, so the tests that named those functions cannot survive as written.

Every behaviour they proved is still asserted here, against whichever authority now owns
it:

- "the default draft is coherent" -> it is a readable ``FormDocument`` with one page and
  one section, and carries no state machine.
- "exactly one initial state" -> a graph property, owned by the status engine and pinned
  in ``test_workflow_submission_status.py`` and ``test_status_engine.py``.
- "a required header field is enforced" / "a valid payload passes" -> the answer boundary
  is ``form_engine.validate_submission``, reached through ``create_submission``.

Run: pytest tests/test_workflow_forms.py -v
"""
from __future__ import annotations

import uuid

import pytest

from app.form_engine.schemas import FORM_SCHEMA_VERSION, FormDocument
from app.models.user import User
from app.models.workflow_forms import WorkflowFormDefinition, WorkflowFormVersion
from app.services.error_handler import AppException
from app.services.workflow_forms_service import (
    WorkflowFormsService,
    default_form_document,
)
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
    register_workflow_submission_status_entity,
    seed_workflow_submission_status_graph,
)
from app.services.status_service import fork_graph, resolve_graph
from app.status_engine import registry as status_registry

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

USER_ID = "zzt-forms-user"

# One page, one section, one required text answer plus a repeater. The repeater is what
# makes a line group exist, so "unknown line group" can be told from "no line groups".
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
                            "key": "items",
                            "label": "Items",
                            "repeater": {
                                "fields": [
                                    {"id": "sf1", "type": "text", "key": "sku", "label": "SKU"}
                                ]
                            },
                        },
                    ],
                }
            ],
        }
    ],
}


@pytest.fixture(autouse=True)
def _isolate_registry():
    """The status registry is process-global; snapshot and restore it."""
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)


def _user(db):
    """``created_by_user_id`` is a real FK to ``users.id`` (AC-F1-16)."""
    if db.query(User).filter(User.id == USER_ID).first() is None:
        db.add(User(id=USER_ID, email=f"{USER_ID}@zzt.invalid", name=f"{TEST_PREFIX} tester"))
        db.flush()


def _ready(db):
    """A seeded graph, a registered entity and an attributable user."""
    seed_workflow_submission_status_graph(db)
    db.flush()
    register_workflow_submission_status_entity()
    _user(db)


def _definition(db, *, publish: bool = True) -> WorkflowFormDefinition:
    definition = WorkflowFormDefinition(
        id=str(uuid.uuid4()),
        code=unique_code("wfsvc").lower(),
        name=f"{unique_code('Form')} definition",
        draft_schema=FORM_DOC,
        created_by_user_id=USER_ID,
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
        db.flush()
    return definition


# ============================================================ the default draft


def test_the_default_draft_is_a_readable_form_document():
    """It replaces the retired builder default, which shipped an embedded state
    machine. The builder loads this straight after "create form", so an unreadable
    default would be a blank screen on the very first action."""
    document = default_form_document()
    parsed = FormDocument.model_validate(document)
    assert len(parsed.pages) == 1
    assert len(parsed.pages[0].sections) == 1
    assert parsed.pages[0].sections[0].fields == []


def test_the_default_draft_carries_no_state_machine():
    """The states, transitions and per-state role arrays moved to the status engine.
    A document still carrying them would be config nothing reads, which gets taken for
    intent later."""
    document = default_form_document()
    for retired in ("states", "transitions", "notification_rules", "header_fields", "line_groups"):
        assert retired not in document


def test_the_default_draft_is_not_publishable_until_a_field_is_added():
    """A form that asks nothing is a dead end in the renderer, so the publish gate must
    refuse it -- and refusing at publish, not at save, is what lets an author leave a
    draft half-finished."""
    with blank_session() as db:
        _ready(db)
        service = WorkflowFormsService(db)
        definition = WorkflowFormDefinition(
            id=str(uuid.uuid4()),
            code=unique_code("wfempty").lower(),
            name=f"{unique_code('Empty')} form",
            draft_schema=default_form_document(),
            created_by_user_id=USER_ID,
        )
        db.add(definition)
        db.flush()

        with pytest.raises(AppException) as err:
            service.publish_definition(str(definition.id), USER_ID)
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "form_document_invalid"


# ============================================================ definitions


def test_a_definition_is_created_with_the_default_document():
    with blank_session() as db:
        _ready(db)
        code = unique_code("wfnew").lower()
        created = WorkflowFormsService(db).create_definition(
            code, f"{TEST_PREFIX} new form", None, USER_ID
        )
        assert created.code == code
        assert FormDocument.model_validate(created.draft_schema).pages


def test_a_malformed_code_is_rejected_before_anything_is_written():
    with blank_session() as db:
        _ready(db)
        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).create_definition("-nope", "ZZT bad code", None, USER_ID)
        assert err.value.detail["code"] == "code_invalid"


def test_a_duplicate_code_is_a_conflict():
    with blank_session() as db:
        _ready(db)
        service = WorkflowFormsService(db)
        code = unique_code("wfdup").lower()
        service.create_definition(code, f"{TEST_PREFIX} first", None, USER_ID)
        with pytest.raises(AppException) as err:
            service.create_definition(code, f"{TEST_PREFIX} second", None, USER_ID)
        assert err.value.status_code == 409


def test_an_unreadable_draft_is_refused_rather_than_stored():
    """Saving it would be silent: every downstream reader (builder, dynamic list-query
    columns, publish gate) degrades to empty on a document it cannot parse, with no
    error anywhere."""
    with blank_session() as db:
        _ready(db)
        definition = _definition(db, publish=False)
        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).update_definition(
                str(definition.id),
                name=None,
                description=None,
                is_active=None,
                draft_schema={"pages": "not a list"},
            )
        assert err.value.detail["code"] == "form_document_malformed"


def test_publishing_snapshots_the_draft_and_points_the_definition_at_it():
    with blank_session() as db:
        _ready(db)
        definition = _definition(db, publish=False)
        version = WorkflowFormsService(db).publish_definition(str(definition.id), USER_ID)
        assert version.version_number == 1
        db.refresh(definition)
        assert definition.published_version_id == version.id
        assert version.schema == FORM_DOC


def test_published_for_submission_lists_only_active_published_forms():
    """The sidebar calls this on every page load in the whole app, so it is the one
    endpoint F1 may not break (AC-F1-20). An unpublished or deactivated form must not
    appear as something a user can submit."""
    with blank_session() as db:
        _ready(db)
        service = WorkflowFormsService(db)
        published = _definition(db)
        draft_only = _definition(db, publish=False)
        deactivated = _definition(db)
        deactivated.is_active = False
        db.flush()

        codes = {row["code"] for row in service.list_published_definitions_for_submission()}
        assert published.code in codes
        assert draft_only.code not in codes
        assert deactivated.code not in codes


def test_a_definition_with_submissions_cannot_be_deleted():
    with blank_session() as db:
        _ready(db)
        service = WorkflowFormsService(db)
        definition = _definition(db)
        service.create_submission(str(definition.id), {"title": "ZZT answer"}, [], USER_ID)

        with pytest.raises(AppException) as err:
            service.delete_definition(str(definition.id))
        assert err.value.status_code == 409


def test_the_definitions_flow_graph_comes_from_the_status_engine():
    """It used to be read out of the schema document's states. A definition that has
    not forked reports the default graph, and says so."""
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        graph = WorkflowFormsService(db).status_graph(str(definition.id))
        assert graph["is_fork"] is False
        assert {node["key"] for node in graph["nodes"]} == {
            "draft",
            "submitted",
            "approved",
            "rejected",
        }
        assert graph["edges"]


def test_a_forked_definitions_flow_graph_reports_its_own_rows():
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        fork = fork_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, str(definition.id))

        graph = WorkflowFormsService(db).status_graph(str(definition.id))
        assert graph["is_fork"] is True
        assert {node["id"] for node in graph["nodes"]} == {s.id for s in fork.statuses}


# ============================================================ submissions


def test_a_required_answer_is_enforced_on_create():
    """The old file proved this through ``validate_submission_payload``. The rule
    survives; the authority is now ``form_engine.validate_submission``."""
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).create_submission(str(definition.id), {}, [], USER_ID)
        assert err.value.status_code == 422
        assert err.value.detail["code"] == "form_answers_invalid"
        assert "title" in err.value.detail["message"]


def test_a_valid_payload_is_accepted_and_stored_cleaned():
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        submission = WorkflowFormsService(db).create_submission(
            str(definition.id),
            {"title": "ZZT answer", "not_a_field": "dropped"},
            [],
            USER_ID,
        )
        # Unknown keys are dropped rather than stored: header_data is what every grid,
        # export and filter reads, so a key no field owns can never appear in one.
        assert submission.header_data == {"title": "ZZT answer"}
        assert submission.status_key == "draft"


def test_a_submission_against_an_unpublished_form_is_refused():
    with blank_session() as db:
        _ready(db)
        definition = _definition(db, publish=False)
        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).create_submission(
                str(definition.id), {"title": "ZZT answer"}, [], USER_ID
            )
        assert err.value.detail["code"] == "not_published"


def test_a_line_row_filed_under_an_unknown_group_is_refused():
    """Preserved from the retired payload validator. A row under a group the document
    does not declare is invisible to every grid and export, so storing it loses data
    silently."""
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        with pytest.raises(AppException) as err:
            WorkflowFormsService(db).create_submission(
                str(definition.id),
                {"title": "ZZT answer"},
                [{"line_group_id": "nope", "row_data": {"sku": "ZZT-1"}}],
                USER_ID,
            )
        assert err.value.detail["code"] == "line_group_unknown"


def test_a_line_row_under_a_declared_repeater_is_stored():
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        submission = WorkflowFormsService(db).create_submission(
            str(definition.id),
            {"title": "ZZT answer"},
            [{"line_group_id": "items", "sort_order": 0, "row_data": {"sku": "ZZT-1"}}],
            USER_ID,
        )
        assert [ln.line_group_id for ln in submission.lines] == ["items"]


def test_a_submission_can_be_edited_while_its_status_is_not_final():
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        service = WorkflowFormsService(db)
        submission = service.create_submission(
            str(definition.id), {"title": "ZZT answer"}, [], USER_ID
        )

        updated = service.update_submission(
            str(submission.id), {"title": "ZZT edited"}, None, USER_ID
        )
        assert updated.header_data == {"title": "ZZT edited"}
        assert updated.updated_by_user_id == USER_ID


def test_a_submission_in_a_final_status_cannot_be_edited():
    """Terminality is read from the status graph. Deriving it from a document that no
    longer carries states would make it unconditionally false and quietly re-enable
    editing on closed submissions -- an authorization regression that throws nothing."""
    with blank_session() as db:
        _ready(db)
        graph = resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None)
        definition = _definition(db)
        service = WorkflowFormsService(db)
        submission = service.create_submission(
            str(definition.id), {"title": "ZZT answer"}, [], USER_ID
        )
        service.apply_transition(
            str(submission.id), graph.by_key("submitted").id, None, USER_ID
        )
        service.apply_transition(
            str(submission.id), graph.by_key("approved").id, None, USER_ID
        )

        with pytest.raises(AppException) as err:
            service.update_submission(str(submission.id), {"title": "ZZT late"}, None, USER_ID)
        assert err.value.detail["code"] == "status_terminal"


def test_submissions_are_filtered_by_status_key_not_by_a_state_string():
    """The listing filter travels as a KEY, because keys are stable across a
    per-definition fork where ids are not."""
    with blank_session() as db:
        _ready(db)
        graph = resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None)
        definition = _definition(db)
        service = WorkflowFormsService(db)
        staying = service.create_submission(
            str(definition.id), {"title": "ZZT stays"}, [], USER_ID
        )
        moving = service.create_submission(
            str(definition.id), {"title": "ZZT moves"}, [], USER_ID
        )
        service.apply_transition(str(moving.id), graph.by_key("submitted").id, None, USER_ID)

        drafts = service.list_submissions(definition_id=str(definition.id), status_key="draft")
        assert [row["id"] for row in drafts["data"]] == [str(staying.id)]
        assert drafts["total"] == 1

        submitted = service.list_submissions(
            definition_id=str(definition.id), status_key="submitted"
        )
        assert [row["id"] for row in submitted["data"]] == [str(moving.id)]


def test_a_listed_submission_carries_its_status_key_and_label():
    """No UUIDs in the UI: a grid renders the label, so the row has to arrive holding
    it rather than an id the frontend would have to resolve."""
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        service = WorkflowFormsService(db)
        service.create_submission(str(definition.id), {"title": "ZZT answer"}, [], USER_ID)

        row = service.list_submissions(definition_id=str(definition.id))["data"][0]
        assert row["status_key"] == "draft"
        assert row["status_label"] == "Draft"
        assert "current_state_code" not in row


def test_the_offered_transitions_are_the_graphs_outgoing_edges():
    """What the frontend draws as buttons. It comes from the same resolution the guard
    uses, or a user is shown an action the server will refuse."""
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        service = WorkflowFormsService(db)
        submission = service.create_submission(
            str(definition.id), {"title": "ZZT answer"}, [], USER_ID
        )

        offered = service.allowed_transitions_for_user(str(submission.id), USER_ID)
        assert [t["to_status_key"] for t in offered] == ["submitted"]
        assert offered[0]["label"] == "Submit"


def test_a_final_status_offers_no_transitions():
    with blank_session() as db:
        _ready(db)
        graph = resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None)
        definition = _definition(db)
        service = WorkflowFormsService(db)
        submission = service.create_submission(
            str(definition.id), {"title": "ZZT answer"}, [], USER_ID
        )
        service.apply_transition(
            str(submission.id), graph.by_key("submitted").id, None, USER_ID
        )
        service.apply_transition(
            str(submission.id), graph.by_key("rejected").id, None, USER_ID
        )

        assert service.allowed_transitions_for_user(str(submission.id), USER_ID) == []


def test_a_transition_records_who_moved_it_and_on_which_edge():
    with blank_session() as db:
        _ready(db)
        graph = resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None)
        definition = _definition(db)
        service = WorkflowFormsService(db)
        submission = service.create_submission(
            str(definition.id), {"title": "ZZT answer"}, [], USER_ID
        )
        service.apply_transition(
            str(submission.id), graph.by_key("submitted").id, "ZZT remark", USER_ID
        )

        payload = service._submission_out(submission, include_logs=True)
        assert payload["status_key"] == "submitted"
        assert len(payload["transition_logs"]) == 1
        entry = payload["transition_logs"][0]
        assert (entry["from_status_key"], entry["to_status_key"]) == ("draft", "submitted")
        assert entry["remark"] == "ZZT remark"
        assert entry["user_id"] == USER_ID


def test_deleting_a_submission_takes_its_lines_with_it():
    with blank_session() as db:
        _ready(db)
        definition = _definition(db)
        service = WorkflowFormsService(db)
        submission = service.create_submission(
            str(definition.id),
            {"title": "ZZT answer"},
            [{"line_group_id": "items", "row_data": {"sku": "ZZT-1"}}],
            USER_ID,
        )
        submission_id = str(submission.id)
        service.delete_submission(submission_id)

        with pytest.raises(AppException) as err:
            service.get_submission(submission_id)
        assert err.value.status_code == 404
