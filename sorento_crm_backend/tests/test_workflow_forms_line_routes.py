"""F1a over HTTP - the line decision, the disposition, and the derived header.

``tests/test_workflow_submission_line_status.py`` proves the SERVICE layer. This file
proves the routes that expose it, and nothing here re-tests a rule that file already
pins. What a route adds on top of a service call is: an authenticated principal, a
permission slug, a request body that has to parse, a status code, and a serialized
response. Those are what is asserted.

Three of these tests exist because they are the ones that pass a wrong implementation:

1. **The asymmetry** (AC-F1a-22). A deriving definition's header refuses a manual move
   into or out of the derived pair, and PERMITS a move that touches neither. A file that
   only asserted the refusal would pass an implementation that refuses everything, which
   is the bug the correction was written for: a deriving submission that can never be
   closed.
2. **The derived header actually moving over HTTP.** Deciding the lines through the route
   and then READING THE SUBMISSION BACK is the only assertion that proves the recompute
   survives the request boundary (its own commit, its own session).
3. **``published-for-submission`` still answering 200, including with an empty list.**
   The sidebar calls it on every page load in the whole app, so a 404 or a 500 there is
   an error toast on every screen, not a workflow-forms bug.

Runs against a blank Postgres schema (``blank_session``), so nothing here can touch the
real rows this database holds, and every code it creates is ``ZZT``-prefixed anyway.

Run: venv/bin/pytest tests/test_workflow_forms_line_routes.py -q -p no:randomly
"""
from __future__ import annotations

import uuid
from typing import Dict, Iterator, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.form_engine.schemas import FORM_SCHEMA_VERSION
from app.models.lookup import LookupOption
from app.models.status import TRIGGER_MANUAL, Status, StatusTransition
from app.models.user import User
from app.models.workflow_forms import (
    WorkflowFormDefinition,
    WorkflowFormVersion,
    WorkflowSubmissionLine,
)
from app.services.lookup_validator import _cache_clear as _lookup_cache_clear
from app.services.status_service import resolve_graph
from app.services.workflow_forms_service import WorkflowFormsService
from app.services.workflow_submission_line_disposition import (
    LINE_DISPOSITION_SET_KEY,
    seed_workflow_submission_line_disposition_lookup,
)
from app.services.workflow_submission_line_status_graph import (
    WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE,
    register_workflow_submission_line_status_entity,
    seed_workflow_submission_line_status_graph,
)
from app.services.workflow_submission_status_graph import (
    WORKFLOW_SUBMISSION_ENTITY_TYPE,
    register_workflow_submission_status_entity,
    seed_workflow_submission_status_graph,
)
from app.status_engine import registry as status_registry

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

BASE = "/api/v1/workflow-forms"

# The repeater every submission in this file files its lines under.
LINE_GROUP = "items"

# The pair a deriving definition declares here, both rungs of the DEFAULT header graph:
# ``draft`` is its starting state (AC-F1a-23) and ``submitted`` is not final
# (AC-F1a-24), so this is the pair the save route must accept.
OPEN_KEY = "draft"
RESOLVED_KEY = "submitted"

# Two extra header rungs, neither of them in the derived pair, with one edge between
# them. They exist for exactly one assertion: that a move touching neither derived rung
# is PERMITTED. The default graph cannot express it - every one of its edges touches
# ``draft`` or ``submitted`` - so without these the asymmetry is untestable and only the
# refusal half gets covered.
SIDE_FROM_KEY = "zzt_on_hold"
SIDE_TO_KEY = "zzt_filed"

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

ACTOR_ID = "zzt-line-routes-user"


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def db() -> Iterator:
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
def _isolate_lookup_cache():
    """``validate_lookup_value`` memoises a binding's allowed values for 60 seconds.

    Without a clear, this file would validate dispositions against whatever a previous
    test file warmed the cache with - including the REAL database's binding, since the
    cache key is only (tenant, table, column) and knows nothing about which schema the
    session is bound to.
    """
    _lookup_cache_clear()
    yield
    _lookup_cache_clear()


@pytest.fixture
def seeded(db):
    """Both default graphs, both entity registrations, and the disposition lookup."""
    seed_workflow_submission_status_graph(db)
    seed_workflow_submission_line_status_graph(db)
    seed_workflow_submission_line_disposition_lookup(db)
    db.add(
        User(
            id=ACTOR_ID,
            email=f"{ACTOR_ID}@{TEST_PREFIX.lower()}.invalid",
            name=f"{TEST_PREFIX} route tester",
        )
    )
    db.commit()
    _lookup_cache_clear()  # the binding was created after any earlier warm read
    register_workflow_submission_status_entity()
    register_workflow_submission_line_status_entity()
    return {
        "header": resolve_graph(db, WORKFLOW_SUBMISSION_ENTITY_TYPE, None),
        "line": resolve_graph(db, WORKFLOW_SUBMISSION_LINE_ENTITY_TYPE, None),
    }


_GRANTED: Dict[str, Optional[set]] = {"slugs": None}  # None = every slug granted


@pytest.fixture(autouse=True)
def _permissions(monkeypatch):
    """Grant everything by default; a denial test narrows ``_GRANTED``.

    Patched rather than seeded: the blank schema has no roles, and this file is about
    which slug a route asks for, not about how a role resolves to one.
    """
    from app.services.user_service import UserPermissionService

    _GRANTED["slugs"] = None

    def _has(_self, _uid, slug):
        allowed = _GRANTED["slugs"]
        return True if allowed is None else slug in allowed

    def _slugs(_self, _uid):
        allowed = _GRANTED["slugs"]
        return set(allowed) if allowed is not None else {
            "workflow_forms.definitions.view",
            "workflow_forms.submissions.view",
            "workflow_forms.submissions.add",
            "workflow_forms.submissions.edit",
            "workflow_forms.submissions.transition",
        }

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", _has)
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", _slugs)
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield
    _GRANTED["slugs"] = None


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    actor = {"id": ACTOR_ID}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def anon_client(db) -> Iterator[TestClient]:
    """No auth override, so the real dependency runs and rejects the request."""
    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------------- helpers


def _definition(db, *, derives: bool = False, published: bool = True):
    """A definition with a published version, built directly.

    ``derives=False`` passes none of the derivation columns, so it exercises the server
    defaults - which is the "no existing form changes shape" case.
    """
    declared = (
        {
            "derives_status_from_lines": True,
            "derived_open_status_key": OPEN_KEY,
            "derived_resolved_status_key": RESOLVED_KEY,
        }
        if derives
        else {}
    )
    definition = WorkflowFormDefinition(
        id=str(uuid.uuid4()),
        code=unique_code("wfl").lower(),
        name=f"{unique_code('Form')} definition",
        draft_schema=FORM_DOC,
        **declared,
    )
    db.add(definition)
    db.flush()
    if published:
        version = WorkflowFormVersion(
            id=str(uuid.uuid4()),
            definition_id=definition.id,
            version_number=1,
            schema=FORM_DOC,
        )
        db.add(version)
        db.flush()
        definition.published_version_id = version.id
    db.commit()
    return definition


def _submission(db, definition, *, rows: int = 2):
    """A submission through the service, which is what stamps the initial statuses."""
    lines = [
        {"line_group_id": LINE_GROUP, "row_data": {"model": f"{TEST_PREFIX}-{i}"}}
        for i in range(rows)
    ]
    return WorkflowFormsService(db).create_submission(
        definition.id, {"title": f"{TEST_PREFIX} answer"}, lines, ACTOR_ID
    )


def _lines(db, submission) -> List[WorkflowSubmissionLine]:
    return (
        db.query(WorkflowSubmissionLine)
        .filter(WorkflowSubmissionLine.submission_id == submission.id)
        .order_by(WorkflowSubmissionLine.sort_order)
        .all()
    )


def _side_track(db):
    """Two header rungs outside the derived pair, joined by one manual edge.

    Added to the DEFAULT graph rather than to a fork: a fork would strand the submission
    that already exists, which is a different failure with its own test elsewhere.
    """
    made = {}
    for index, (key, label, terminal) in enumerate(
        ((SIDE_FROM_KEY, "On hold", False), (SIDE_TO_KEY, "Filed", True))
    ):
        row = Status(
            id=str(uuid.uuid4()),
            entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
            key=key,
            label=label,
            scope_id=None,
            tenant_id=None,
            sort_order=100 + index * 10,
            is_terminal=terminal,
        )
        db.add(row)
        made[key] = row
    db.flush()
    db.add(
        StatusTransition(
            id=str(uuid.uuid4()),
            entity_type=WORKFLOW_SUBMISSION_ENTITY_TYPE,
            scope_id=None,
            tenant_id=None,
            from_status_id=made[SIDE_FROM_KEY].id,
            to_status_id=made[SIDE_TO_KEY].id,
            label="File it",
            trigger_mode=TRIGGER_MANUAL,
        )
    )
    db.commit()
    return made[SIDE_FROM_KEY], made[SIDE_TO_KEY]


def _park(db, submission, status):
    """Put the header on a status WITHOUT a transition.

    Deliberately not through the route: the moves this file then attempts start from a
    rung no edge of the default graph leads to, and getting there legitimately is a
    different slice's problem. The point under test is what happens NEXT.
    """
    submission.status_id = status.id
    db.commit()


def _status(seeded, graph: str, key: str) -> Status:
    found = seeded[graph].by_key(key)
    assert found is not None, f"{graph} graph has no rung '{key}'"
    return found


# ------------------------------------------------------- reading a line


def test_get_line_reports_its_status_and_disposition(client, db, seeded):
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=1)
    line = _lines(db, submission)[0]

    r = client.get(f"{BASE}/lines/{line.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(line.id)
    assert body["line_group_id"] == LINE_GROUP
    # Key and label beside the id, because the frontend may not render a UUID.
    assert body["status_key"] == "pending"
    assert body["status_label"] == "Pending"
    assert body["disposition"] is None
    assert body["disposition_reason"] is None


def test_get_unknown_line_is_404(client, db, seeded):
    r = client.get(f"{BASE}/lines/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_allowed_line_transitions_offers_the_three_decisions(client, db, seeded):
    definition = _definition(db, derives=True)
    line = _lines(db, _submission(db, definition, rows=1))[0]

    r = client.get(f"{BASE}/lines/{line.id}/allowed-transitions")
    assert r.status_code == 200, r.text
    offered = r.json()["transitions"]
    # Not pinned to a hardcoded list of labels: the graph is admin-editable. What matters
    # is that every offer names a rung the caller can render and then post back.
    assert {t["to_status_key"] for t in offered} == {"approved", "rejected", "cancelled"}
    assert all(t["to_status_id"] and t["to_status_label"] for t in offered)


def test_allowed_line_transitions_is_empty_for_a_form_without_line_statuses(
    client, db, seeded
):
    """A non-deriving form's lines carry no status, so there is no decision to offer.

    Empty rather than an error: this is every form that exists today, and a 422 here
    would break a submission detail page that merely asked.
    """
    line = _lines(db, _submission(db, _definition(db), rows=1))[0]
    r = client.get(f"{BASE}/lines/{line.id}/allowed-transitions")
    assert r.status_code == 200, r.text
    assert r.json()["transitions"] == []


# --------------------------------------------------- deciding a line


def test_line_transition_decides_the_line_and_answers_with_the_submission(
    client, db, seeded
):
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=2)
    first, second = _lines(db, submission)
    approved = _status(seeded, "line", "approved")

    r = client.post(
        f"{BASE}/lines/{first.id}/transition", json={"to_status_id": approved.id}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(submission.id)
    decided = {ln["id"]: ln for ln in body["lines"]}
    assert decided[str(first.id)]["status_key"] == "approved"
    # The other line is untouched: a decision is per item (AC-F1a-14).
    assert decided[str(second.id)]["status_key"] == "pending"
    # One line still undecided, so the header has not moved.
    assert body["status_key"] == OPEN_KEY


def test_partial_approval_is_a_first_class_outcome(client, db, seeded):
    """Approve one, reject the other: both lines terminal, header resolved."""
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=2)
    first, second = _lines(db, submission)

    r = client.post(
        f"{BASE}/lines/{first.id}/transition",
        json={"to_status_id": _status(seeded, "line", "approved").id},
    )
    assert r.status_code == 200, r.text
    r = client.post(
        f"{BASE}/lines/{second.id}/transition",
        json={"to_status_id": _status(seeded, "line", "rejected").id},
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert {ln["status_key"] for ln in body["lines"]} == {"approved", "rejected"}
    assert body["status_key"] == RESOLVED_KEY


def test_the_derived_header_is_on_the_resolved_rung_when_read_back(client, db, seeded):
    """The recompute has to survive the request boundary, not just the service call.

    Decide every line through the route, then READ THE SUBMISSION with a second request.
    Asserting only the mutation's own response body would pass an implementation that
    computed the header in memory and never committed it.
    """
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=2)
    approved = _status(seeded, "line", "approved")
    for line in _lines(db, submission):
        assert (
            client.post(
                f"{BASE}/lines/{line.id}/transition", json={"to_status_id": approved.id}
            ).status_code
            == 200
        )

    r = client.get(f"{BASE}/submissions/{submission.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status_key"] == RESOLVED_KEY
    # ...and the move is in the trail, marked as nobody's: no user, no edge (AC-F1a-29).
    derived = [lg for lg in body["transition_logs"] if lg["user_id"] is None]
    assert len(derived) == 1
    assert derived[0]["status_transition_id"] is None
    assert derived[0]["to_status_key"] == RESOLVED_KEY


def test_line_transition_to_an_out_of_graph_status_is_422(client, db, seeded):
    """A HEADER status id is a real status, and still not a rung of the LINE graph.

    The two graphs share keys, so this is the mistake a client actually makes.
    """
    definition = _definition(db, derives=True)
    line = _lines(db, _submission(db, definition, rows=1))[0]
    header_approved = _status(seeded, "header", "approved")

    r = client.post(
        f"{BASE}/lines/{line.id}/transition", json={"to_status_id": header_approved.id}
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "status_not_in_graph"


def test_line_transition_on_a_line_with_no_status_is_422(client, db, seeded):
    """A non-deriving form's line is data, not a decision, so it cannot be moved."""
    line = _lines(db, _submission(db, _definition(db), rows=1))[0]
    r = client.post(
        f"{BASE}/lines/{line.id}/transition",
        json={"to_status_id": _status(seeded, "line", "approved").id},
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "status_not_in_graph"


def test_line_transition_on_an_unknown_line_is_404(client, db, seeded):
    r = client.post(
        f"{BASE}/lines/{uuid.uuid4()}/transition",
        json={"to_status_id": _status(seeded, "line", "approved").id},
    )
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_line_transition_without_a_target_is_422(client, db, seeded):
    """The body is required: FastAPI rejects it before the service sees a blank id."""
    line = _lines(db, _submission(db, _definition(db, derives=True), rows=1))[0]
    assert client.post(f"{BASE}/lines/{line.id}/transition", json={}).status_code == 422


# ------------------------------------------------------ the disposition


def test_disposition_options_come_from_the_bound_lookup_set(client, db, seeded):
    r = client.get(f"{BASE}/line-dispositions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["set_key"] == LINE_DISPOSITION_SET_KEY
    values = [o["value"] for o in body["options"]]
    # Not pinned to the full list (AC-F1a-26: admin-editable master data). What is pinned
    # is that the two the after-sales flow names are offered, with labels to render.
    assert "write_off" in values and "nothing_to_collect" in values
    assert all(o["label"] for o in body["options"])


def test_a_retired_disposition_is_not_offered(client, db, seeded):
    """Deactivating means "closed to new ones", so the picker must drop it too.

    Offering it would hand the user a choice the write path refuses one call later.
    """
    row = db.query(LookupOption).filter(LookupOption.value == "repair").first()
    row.is_active = False
    db.commit()

    values = [o["value"] for o in client.get(f"{BASE}/line-dispositions").json()["options"]]
    assert "repair" not in values


def test_setting_a_valid_disposition_records_it_with_its_reason(client, db, seeded):
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=1)
    line = _lines(db, submission)[0]

    r = client.patch(
        f"{BASE}/lines/{line.id}/disposition",
        json={
            "disposition": "nothing_to_collect",
            "disposition_reason": f"{TEST_PREFIX} customer kept the unit",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    stored = body["lines"][0]
    assert stored["disposition"] == "nothing_to_collect"
    assert stored["disposition_reason"] == f"{TEST_PREFIX} customer kept the unit"
    # Recording HOW a line settles is not a decision, so nothing moved (AC-F1a-8).
    assert stored["status_key"] == "pending"
    assert body["status_key"] == OPEN_KEY


def test_an_unknown_disposition_is_422(client, db, seeded):
    line = _lines(db, _submission(db, _definition(db, derives=True), rows=1))[0]
    r = client.patch(
        f"{BASE}/lines/{line.id}/disposition", json={"disposition": "zzt_not_a_thing"}
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "invalid_lookup_value"


def test_a_retired_disposition_cannot_be_set(client, db, seeded):
    line = _lines(db, _submission(db, _definition(db, derives=True), rows=1))[0]
    row = db.query(LookupOption).filter(LookupOption.value == "maintenance").first()
    row.is_active = False
    db.commit()
    _lookup_cache_clear()  # the validator memoises the allowed set for 60 seconds

    r = client.patch(
        f"{BASE}/lines/{line.id}/disposition", json={"disposition": "maintenance"}
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "invalid_lookup_value"


def test_clearing_a_disposition_also_clears_its_reason(client, db, seeded):
    line = _lines(db, _submission(db, _definition(db, derives=True), rows=1))[0]
    assert (
        client.patch(
            f"{BASE}/lines/{line.id}/disposition",
            json={"disposition": "write_off", "disposition_reason": "scrapped"},
        ).status_code
        == 200
    )

    r = client.patch(f"{BASE}/lines/{line.id}/disposition", json={"disposition": None})
    assert r.status_code == 200, r.text
    cleared = r.json()["lines"][0]
    assert cleared["disposition"] is None
    # A cleared disposition has no reason left to explain.
    assert cleared["disposition_reason"] is None


# ------------------------------------------- turning derivation on, over HTTP


def test_enabling_derivation_saves_the_declared_pair(client, db, seeded):
    definition = _definition(db)

    r = client.patch(
        f"{BASE}/definitions/{definition.id}",
        json={
            "derives_status_from_lines": True,
            "derived_open_status_key": OPEN_KEY,
            "derived_resolved_status_key": RESOLVED_KEY,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["derives_status_from_lines"] is True
    assert body["derived_open_status_key"] == OPEN_KEY
    assert body["derived_resolved_status_key"] == RESOLVED_KEY

    # ...and it is readable back, which is what the builder renders the toggle from.
    read = client.get(f"{BASE}/definitions/{definition.id}").json()
    assert read["derives_status_from_lines"] is True
    assert read["derived_resolved_status_key"] == RESOLVED_KEY


def test_an_open_key_that_is_not_the_starting_state_is_refused(client, db, seeded):
    """``submitted`` is a real rung and still wrong: a submission is created on
    ``draft``, so it would sit outside the declared pair forever (AC-F1a-23)."""
    definition = _definition(db)
    r = client.patch(
        f"{BASE}/definitions/{definition.id}",
        json={
            "derives_status_from_lines": True,
            "derived_open_status_key": "submitted",
            "derived_resolved_status_key": "approved",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "status_derivation_misconfigured"

    # The refused values are not left on the row: a save that failed must change nothing.
    read = client.get(f"{BASE}/definitions/{definition.id}").json()
    assert read["derives_status_from_lines"] is False
    assert read["derived_open_status_key"] is None


def test_a_terminal_resolved_key_is_refused(client, db, seeded):
    """A final rung cannot be edited or reopened, so adding a line could never reopen
    the submission (AC-F1a-24)."""
    definition = _definition(db)
    r = client.patch(
        f"{BASE}/definitions/{definition.id}",
        json={
            "derives_status_from_lines": True,
            "derived_open_status_key": OPEN_KEY,
            "derived_resolved_status_key": "approved",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "status_derivation_misconfigured"


def test_a_key_the_graph_does_not_have_is_refused(client, db, seeded):
    definition = _definition(db)
    r = client.patch(
        f"{BASE}/definitions/{definition.id}",
        json={
            "derives_status_from_lines": True,
            "derived_open_status_key": OPEN_KEY,
            "derived_resolved_status_key": "zzt_nowhere",
        },
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "status_derivation_misconfigured"


# ------------------------------- the derived header is single-writer (asymmetry)


def test_a_manual_move_INTO_the_derived_pair_is_refused(client, db, seeded):
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=1)  # created on the open rung

    r = client.post(
        f"{BASE}/submissions/{submission.id}/transition",
        json={"to_status_id": _status(seeded, "header", RESOLVED_KEY).id},
    )
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "status_derived_not_writable"


def test_a_manual_move_OUT_OF_the_derived_pair_is_permitted(client, db, seeded):
    """The realistic path, and the one that used to be broken.

    A deriving submission is ALWAYS created on a pair rung, because
    `assert_derivation_config` forces the open key to be the graph's initial rung. So
    every move a real user is offered starts from inside the pair. An earlier guard
    refused whenever EITHER endpoint was in the pair, which therefore refused everything:
    `allowed-transitions` returned an empty list forever and the detail page had no
    action buttons at all.

    Gating on the TARGET fixes it. Leaving the pair is fine because once the header is
    parked outside both declared rungs, derivation declines to touch it, so there is no
    second writer. Same shape as `complaint_fulfilment_service`, where `closed` and
    `rejected` are sticky.
    """
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=1)
    _park(db, submission, _status(seeded, "header", RESOLVED_KEY))
    outside = _status(seeded, "header", "approved")

    r = client.post(
        f"{BASE}/submissions/{submission.id}/transition",
        json={"to_status_id": outside.id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status_id"] == outside.id


def test_a_manual_move_touching_NEITHER_derived_rung_is_permitted(client, db, seeded):
    """The half that a "refuse everything" implementation gets wrong.

    Derivation owns the open/resolved pair and nothing else, so the rest of the
    lifecycle stays human-driven (AC-F1a-22). Without this assertion a deriving
    submission could never reach any terminal state at all.
    """
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=1)
    on_hold, filed = _side_track(db)
    _park(db, submission, on_hold)

    r = client.post(
        f"{BASE}/submissions/{submission.id}/transition",
        json={"to_status_id": filed.id, "remark": f"{TEST_PREFIX} closing by hand"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status_key"] == SIDE_TO_KEY
    # A human move, so it IS attributed, unlike the derived one.
    moved = [lg for lg in body["transition_logs"] if lg["to_status_key"] == SIDE_TO_KEY]
    assert len(moved) == 1
    assert moved[0]["user_id"] == ACTOR_ID
    assert moved[0]["remark"] == f"{TEST_PREFIX} closing by hand"


def test_allowed_header_transitions_hides_the_derived_pair(client, db, seeded):
    """The buttons must agree with the guard, or the user learns the product is broken
    by pressing one."""
    definition = _definition(db, derives=True)
    submission = _submission(db, definition, rows=1)

    r = client.get(f"{BASE}/submissions/{submission.id}/allowed-transitions")
    assert r.status_code == 200, r.text
    # The only edge out of the open rung leads into the resolved one, which derivation
    # owns, so nothing is offered.
    assert r.json()["transitions"] == []


# ----------------------------------------------------------- auth denial


def test_every_line_route_requires_a_principal(anon_client, db, seeded):
    definition = _definition(db, derives=True)
    line = _lines(db, _submission(db, definition, rows=1))[0]
    target = _status(seeded, "line", "approved").id

    assert anon_client.get(f"{BASE}/lines/{line.id}").status_code == 401
    assert anon_client.get(f"{BASE}/lines/{line.id}/allowed-transitions").status_code == 401
    assert anon_client.get(f"{BASE}/line-dispositions").status_code == 401
    assert (
        anon_client.post(
            f"{BASE}/lines/{line.id}/transition", json={"to_status_id": target}
        ).status_code
        == 401
    )
    assert (
        anon_client.patch(
            f"{BASE}/lines/{line.id}/disposition", json={"disposition": "write_off"}
        ).status_code
        == 401
    )


def test_deciding_a_line_needs_the_transition_permission(client, db, seeded):
    """View must not imply decide: deciding lines is how a deriving header moves, so a
    reader who could do it would move submissions indirectly."""
    definition = _definition(db, derives=True)
    line = _lines(db, _submission(db, definition, rows=1))[0]
    target = _status(seeded, "line", "approved").id

    _GRANTED["slugs"] = {"workflow_forms.submissions.view"}
    r = client.post(f"{BASE}/lines/{line.id}/transition", json={"to_status_id": target})
    assert r.status_code == 403, r.text
    # ...while the read of the same line still works.
    assert client.get(f"{BASE}/lines/{line.id}").status_code == 200


def test_setting_a_disposition_needs_the_edit_permission(client, db, seeded):
    definition = _definition(db, derives=True)
    line = _lines(db, _submission(db, definition, rows=1))[0]

    _GRANTED["slugs"] = {"workflow_forms.submissions.view"}
    r = client.patch(
        f"{BASE}/lines/{line.id}/disposition", json={"disposition": "write_off"}
    )
    assert r.status_code == 403, r.text


def test_enabling_derivation_needs_the_definitions_edit_permission(client, db, seeded):
    definition = _definition(db)
    _GRANTED["slugs"] = {"workflow_forms.definitions.view"}
    r = client.patch(
        f"{BASE}/definitions/{definition.id}",
        json={"derives_status_from_lines": True, "derived_open_status_key": OPEN_KEY},
    )
    assert r.status_code == 403, r.text


# ------------------------------ the sidebar's app-wide call (AC-F1a-20)


def test_published_for_submission_is_200_with_an_empty_list(client, db, seeded):
    """Every page in the app calls this on load, so a 404 or 500 here is an error toast
    on every screen. The empty case is the one a fresh install hits."""
    r = client.get(f"{BASE}/definitions/published-for-submission")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"] == []
    assert body["empty"] is True


def test_published_for_submission_lists_a_deriving_definition(client, db, seeded):
    definition = _definition(db, derives=True)
    r = client.get(f"{BASE}/definitions/published-for-submission")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [row["id"] for row in body["data"]] == [str(definition.id)]
    assert body["empty"] is False


def test_published_for_submission_skips_an_unpublished_definition(client, db, seeded):
    _definition(db, published=False)
    r = client.get(f"{BASE}/definitions/published-for-submission")
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []


def test_a_submission_read_still_carries_its_lines_for_a_plain_form(client, db, seeded):
    """The no-op case: a form that never opted in answers exactly as it did before,
    with NULL line statuses and no disposition."""
    submission = _submission(db, _definition(db), rows=2)
    body = client.get(f"{BASE}/submissions/{submission.id}").json()
    assert len(body["lines"]) == 2
    assert all(ln["status_id"] is None for ln in body["lines"])
    assert all(ln["disposition"] is None for ln in body["lines"])
