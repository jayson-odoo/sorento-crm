"""Spec visibility policy - resolution, hidden-key derivation and the admin CRUD.

UAC `documentation/plans/chatbot/spec-visibility-policy-acceptance-criteria.md`
Phase 2, AC-8..AC-13. PLAN `documentation/plans/chatbot/PLAN-spec-visibility-policy.md`.

Precedent copied mechanically from `tests/test_stock_visibility_policy.py` (three-tier
policy, migration CHECK test, response_model field-drop test, audit rows) - see that
file's own docstring for the reasoning behind each technique reused here.

Postgres only, blank schema, every row seeded here (CI's database has none). Written
BEFORE any of `app/models/access.py::SpecVisibilityPolicy`,
`app/services/spec_visibility.py` or `app/api/v1/user_management/spec_visibility.py`
exist - every test below is expected to fail on collection or on the first call into
one of those symbols, not on an assertion.
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.dependencies import (
    get_current_user,
    get_current_user_or_api_key,
    get_db,
)
from app.models.access import MarketSegment, RespondContact, respond_contact_market_segments
from app.models.base import set_company_scope
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from app.services.user_service import UserPermissionService

from tests._pg_fixture import blank_session, unique_code

READ_PERM = "user_management.contacts.view"
WRITE_PERM = "user_management.contacts.edit"
BASE = "/api/v1/user-management/spec-visibility"


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


@pytest.fixture
def client(db, monkeypatch):
    """A staff caller holding both contacts permissions, on the SAME session the
    assertions read.

    A real `users` row, not a bare uuid dict: `FormActionService.dispatch` (the
    pending-actions engine, AC-13b) inserts `sla_form_actions.requested_by_id`
    with an FK to `users.id`, the same reason `tests/test_record_actions_s6b.py`'s
    own `client` fixture seeds one.
    """
    from app.models.user import User

    def _override_db():
        yield db

    actor_row = User(
        id=str(uuid.uuid4()), email="zzt-spec-visibility@test.com", name="ZZT Spec Visibility"
    )
    db.add(actor_row)
    db.flush()
    principal = {"id": actor_row.id, "email": actor_row.email}
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

    async def _override_scope():
        scope = frozenset({DEFAULT_COMPANY_ID})
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in {READ_PERM, WRITE_PERM},
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------- seeding


def _contact(db) -> RespondContact:
    row = RespondContact(
        id=unique_code("CONTACT"),
        phone_number=f"+60{uuid.uuid4().int % 10**9:09d}",
        name="ZZT Contact",
    )
    db.add(row)
    db.flush()
    return row


def _segment(db, code: str, name: str) -> MarketSegment:
    row = MarketSegment(id=str(uuid.uuid4()), code=code, name=name, is_active=True)
    db.add(row)
    db.flush()
    return row


def _tag_segment(db, contact: RespondContact, segment: MarketSegment) -> None:
    db.execute(
        respond_contact_market_segments.insert().values(
            contact_id=contact.id, segment_code=segment.code
        )
    )
    db.flush()


def _spec_key(db, key: str, label: str, *, is_active: bool = True):
    from app.models.product_spec import ProductSpecRegistry

    row = ProductSpecRegistry(
        id=str(uuid.uuid4()),
        spec_key=key,
        label=label,
        data_type="enum",
        is_active=is_active,
    )
    db.add(row)
    db.flush()
    return row


def _policy_row(
    db,
    *,
    contact: RespondContact | None = None,
    segment: MarketSegment | None = None,
    spec_keys: list[str] | None = None,
    excluded_spec_keys: list[str] | None = None,
):
    from app.models.access import SpecVisibilityPolicy

    row = SpecVisibilityPolicy(
        id=str(uuid.uuid4()),
        contact_id=contact.id if contact else None,
        segment_code=segment.code if segment else None,
        spec_keys=spec_keys,
        excluded_spec_keys=excluded_spec_keys,
    )
    db.add(row)
    db.flush()
    return row


# ============================================================ AC-8 migration


_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "510_spec_visibility_policies.py"
)


def _load_migration(path: pathlib.Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_510_creates_table_checks_and_seeds(db):
    """AC-8: the table, both CHECKs (one tier, one rule), and the two seeded rows -
    the default (`excluded_spec_keys = ['thickness', 'board_thickness']`) and the
    `project` segment (`excluded_spec_keys = []`), the latter only because a
    `project` segment row exists. Downgrade drops the table.

    `create_all` and the migration are two independent descriptions of the same
    table (see `test_stock_visibility_policy.py::test_migration_builds_the_table_the_model_expects`),
    and only one of them runs in production - `blank_session` already built
    `spec_visibility_policies` from the ORM model, so it is dropped first and the
    real `upgrade()` run in its place; a CHECK that only exists on the model would
    otherwise never be exercised here.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text as sa_text
    from sqlalchemy.exc import IntegrityError

    project = _segment(db, "project", "Project")
    contact = _contact(db)
    db.flush()

    db.execute(sa_text("DROP TABLE spec_visibility_policies"))
    module = _load_migration(_MIGRATION, "migration_510_spec_visibility_policies")
    context = MigrationContext.configure(db.connection())
    with Operations.context(context):
        module.upgrade()

    rows = db.execute(
        sa_text(
            "SELECT contact_id, segment_code, spec_keys, excluded_spec_keys "
            "FROM spec_visibility_policies"
        )
    ).all()
    by_tier = {
        (row.contact_id, row.segment_code): (row.spec_keys, row.excluded_spec_keys)
        for row in rows
    }
    assert by_tier[(None, None)] == (None, ["thickness", "board_thickness"])
    assert by_tier[(None, project.code)] == (None, [])

    sp = db.begin_nested()
    with pytest.raises(IntegrityError):
        db.execute(
            sa_text(
                "INSERT INTO spec_visibility_policies (id, spec_keys, excluded_spec_keys) "
                "VALUES (gen_random_uuid(), ARRAY['a'], ARRAY['b'])"
            )
        )
        db.flush()
    sp.rollback()

    sp = db.begin_nested()
    with pytest.raises(IntegrityError):
        db.execute(
            sa_text(
                "INSERT INTO spec_visibility_policies "
                "(id, contact_id, segment_code, spec_keys, excluded_spec_keys) "
                "VALUES (gen_random_uuid(), :cid, :seg, NULL, ARRAY['x'])"
            ),
            {"cid": contact.id, "seg": project.code},
        )
        db.flush()
    sp.rollback()

    with Operations.context(context):
        module.downgrade()
    with pytest.raises(Exception):
        db.execute(sa_text("SELECT 1 FROM spec_visibility_policies")).all()
    db.rollback()


# ============================================================ AC-9 resolution


def test_resolve_policy_contact_override_beats_segments_beats_default(db):
    from app.services.spec_visibility import resolve_policy

    retail = _segment(db, unique_code("retail")[:20].lower(), "Retail")
    contact = _contact(db)
    _tag_segment(db, contact, retail)
    _policy_row(db, spec_keys=None, excluded_spec_keys=["thickness"])
    _policy_row(db, segment=retail, spec_keys=None, excluded_spec_keys=["finish"])
    _policy_row(db, contact=contact, spec_keys=["material"], excluded_spec_keys=None)
    db.flush()

    policy = resolve_policy(db, contact.id, None)

    assert policy.source == "contact"
    assert set(policy.spec_keys or []) == {"material"}
    assert policy.excluded_spec_keys is None


def test_resolve_policy_merges_segments_intersection_and_union(db):
    """Segment A Show-only {material, finish}, segment B Hide {finish} ->
    spec_keys {material, finish}, excluded {finish} - both carried on the merged
    (in-memory) policy, never on one row."""
    from app.services.spec_visibility import resolve_policy

    seg_a = _segment(db, unique_code("a")[:20].lower(), "Segment A")
    seg_b = _segment(db, unique_code("b")[:20].lower(), "Segment B")
    contact = _contact(db)
    _tag_segment(db, contact, seg_a)
    _tag_segment(db, contact, seg_b)
    _policy_row(db, segment=seg_a, spec_keys=["material", "finish"], excluded_spec_keys=None)
    _policy_row(db, segment=seg_b, spec_keys=None, excluded_spec_keys=["finish"])
    db.flush()

    policy = resolve_policy(db, contact.id, None)

    assert policy.source == "segment"
    assert set(policy.spec_keys or []) == {"material", "finish"}
    assert set(policy.excluded_spec_keys or []) == {"finish"}


def test_resolve_policy_source_label_is_segment_name_not_code(db):
    from app.services.spec_visibility import resolve_policy

    retail = _segment(db, "retail", "Retail")
    contact = _contact(db)
    _tag_segment(db, contact, retail)
    _policy_row(db, segment=retail, spec_keys=None, excluded_spec_keys=[])
    db.flush()

    policy = resolve_policy(db, contact.id, None)

    assert policy.source == "segment"
    assert policy.source_label == "Retail"
    assert policy.source_label != "retail"


def test_resolve_policy_unresolvable_contact_returns_default(db):
    """Fail closed to the DEFAULT policy, not to `None` - unlike stock visibility,
    an unresolvable contact must still get an answer (the plan's Decisions table)."""
    from app.services.spec_visibility import resolve_policy

    policy = resolve_policy(db, "ZZT-NO-SUCH-CONTACT", None)

    assert policy is not None
    assert policy.source == "default"


# ============================================================ AC-10 hidden_keys


def test_hidden_keys_show_only_null_hides_only_hide_list(db):
    from app.services.spec_visibility import hidden_keys, resolve_policy

    _spec_key(db, "material", "Material")
    _spec_key(db, "thickness", "Thickness")
    contact = _contact(db)
    _policy_row(db, contact=contact, spec_keys=None, excluded_spec_keys=["thickness"])
    db.flush()

    policy = resolve_policy(db, contact.id, None)

    assert hidden_keys(policy, {"material", "thickness"}) == frozenset({"thickness"})


def test_hidden_keys_show_only_list_hides_every_other_key(db):
    from app.services.spec_visibility import hidden_keys, resolve_policy

    _spec_key(db, "material", "Material")
    _spec_key(db, "finish", "Finish")
    _spec_key(db, "thickness", "Thickness")
    contact = _contact(db)
    _policy_row(db, contact=contact, spec_keys=["material"], excluded_spec_keys=None)
    db.flush()

    policy = resolve_policy(db, contact.id, None)

    assert hidden_keys(policy, {"material", "finish", "thickness"}) == frozenset(
        {"finish", "thickness"}
    )


def test_hidden_keys_show_only_empty_hides_all(db):
    from app.services.spec_visibility import hidden_keys, resolve_policy

    _spec_key(db, "material", "Material")
    _spec_key(db, "finish", "Finish")
    contact = _contact(db)
    _policy_row(db, contact=contact, spec_keys=[], excluded_spec_keys=None)
    db.flush()

    policy = resolve_policy(db, contact.id, None)

    assert hidden_keys(policy, {"material", "finish"}) == frozenset({"material", "finish"})


def test_hidden_keys_ignores_key_missing_from_registry(db):
    """A key later removed from the registry is ignored on read (AC-10)."""
    from app.services.spec_visibility import hidden_keys, resolve_policy

    _spec_key(db, "thickness", "Thickness")
    contact = _contact(db)
    _policy_row(
        db, contact=contact, spec_keys=None, excluded_spec_keys=["thickness", "ghost_key"]
    )
    db.flush()

    policy = resolve_policy(db, contact.id, None)

    assert hidden_keys(policy, {"thickness"}) == frozenset({"thickness"})


# ============================================================ AC-11/12/13 routes


def test_routes_get_put_delete_on_three_tiers_round_trip(client, db):
    """AC-11: GET/PUT/DELETE on all three tiers, `/effective` accepting the
    api-key principal, and `/keys` sorted by label from the active registry."""
    _spec_key(db, "material", "Material")
    _spec_key(db, "thickness", "Thickness")
    contact = _contact(db)
    project = _segment(db, "project", "Project")
    db.flush()

    put_contact = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"spec_keys": ["material"], "excluded_spec_keys": None},
    )
    assert put_contact.status_code == 200, put_contact.text
    body = put_contact.json()
    assert body["override"]["specs"] == [{"key": "material", "label": "Material"}]
    assert body["override"]["source"] == "contact"

    get_contact = client.get(f"{BASE}/contacts/{contact.id}")
    assert get_contact.status_code == 200
    assert get_contact.json()["override"]["specs"] == [{"key": "material", "label": "Material"}]

    delete_contact = client.delete(f"{BASE}/contacts/{contact.id}")
    assert delete_contact.status_code == 200
    assert delete_contact.json()["override"] is None

    put_segment = client.put(
        f"{BASE}/segments/{project.code}",
        json={"spec_keys": None, "excluded_spec_keys": []},
    )
    assert put_segment.status_code == 200, put_segment.text
    seg_body = put_segment.json()
    assert seg_body["override"]["excluded_specs"] == []
    assert seg_body["override"]["source"] == "segment"
    assert seg_body["override"]["source_label"] == "Project"

    get_segment = client.get(f"{BASE}/segments/{project.code}")
    assert get_segment.json()["override"]["excluded_specs"] == []

    delete_segment = client.delete(f"{BASE}/segments/{project.code}")
    assert delete_segment.status_code == 200
    assert delete_segment.json()["override"] is None

    put_default = client.put(
        f"{BASE}/default",
        json={"spec_keys": None, "excluded_spec_keys": ["thickness"]},
    )
    assert put_default.status_code == 200, put_default.text
    default_body = put_default.json()
    assert default_body["override"] == default_body["effective"]
    assert default_body["effective"]["source"] == "default"
    assert client.delete(f"{BASE}/default").status_code == 405

    get_default = client.get(f"{BASE}/default")
    assert get_default.json()["effective"]["excluded_specs"] == [
        {"key": "thickness", "label": "Thickness"}
    ]

    keys = client.get(f"{BASE}/keys")
    assert keys.status_code == 200
    assert keys.json() == [
        {"key": "material", "label": "Material"},
        {"key": "thickness", "label": "Thickness"},
    ]

    # AC-11: `/effective` accepts the api-key principal, not just a staff JWT -
    # n8n's own preflight convenience.
    app.dependency_overrides[get_current_user_or_api_key] = lambda: {
        "id": str(uuid.uuid4()),
        "email": "zzt-integration@test.com",
    }
    del app.dependency_overrides[get_current_user]
    api_effective = TestClient(app).get(
        f"{BASE}/effective", params={"contact_id": contact.id}
    )
    assert api_effective.status_code == 200, api_effective.text


def test_routes_write_requires_contacts_edit(db, monkeypatch):
    """AC-11: reads need `user_management.contacts.view`, writes need `.edit` - no
    new permission slug."""
    contact = _contact(db)
    db.flush()

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        principal = {"id": str(uuid.uuid4()), "email": "zzt-spec-reader@test.com"}
        app.dependency_overrides[get_current_user] = lambda: principal
        app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
        monkeypatch.setattr(
            UserPermissionService,
            "check_user_has_permission",
            lambda self, uid, slug: slug == READ_PERM,
        )
        reader = TestClient(app)
        assert reader.get(f"{BASE}/contacts/{contact.id}").status_code == 200
        assert (
            reader.put(
                f"{BASE}/contacts/{contact.id}",
                json={"spec_keys": None, "excluded_spec_keys": []},
            ).status_code
            == 403
        )
        assert reader.delete(f"{BASE}/contacts/{contact.id}").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_put_both_lists_non_null_422_with_exact_message(client, db):
    """AC-12."""
    _spec_key(db, "material", "Material")
    _spec_key(db, "thickness", "Thickness")
    contact = _contact(db)
    db.flush()

    response = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"spec_keys": ["material"], "excluded_spec_keys": ["thickness"]},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Pick specs to show or to hide, not both."


def test_put_unknown_key_422_names_it(client, db):
    contact = _contact(db)
    db.flush()

    response = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"spec_keys": ["ZZT-NOT-A-REAL-KEY"], "excluded_spec_keys": None},
    )
    assert response.status_code == 422
    assert "ZZT-NOT-A-REAL-KEY" in response.text


def test_put_inactive_key_422(client, db):
    _spec_key(db, "retired_key", "Retired", is_active=False)
    contact = _contact(db)
    db.flush()

    response = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"spec_keys": ["retired_key"], "excluded_spec_keys": None},
    )
    assert response.status_code == 422
    assert "retired_key" in response.text


def test_put_unknown_segment_404(client, db):
    response = client.put(
        f"{BASE}/segments/ZZT-NO-SUCH-SEGMENT",
        json={"spec_keys": None, "excluded_spec_keys": []},
    )
    assert response.status_code == 404


def test_put_body_missing_excluded_spec_keys_422(client, db):
    """Both fields are REQUIRED-nullable (never defaulted) - an omitted key must
    422 rather than silently widen the policy."""
    contact = _contact(db)
    db.flush()

    response = client.put(f"{BASE}/contacts/{contact.id}", json={"spec_keys": None})
    assert response.status_code == 422


def test_response_model_declares_every_field(client, db):
    """`response_model` silently drops undeclared fields (LESSONS) - asserted on
    the SCHEMA and on a real response body."""
    from app.schemas.spec_visibility import SpecVisibilityPolicyOut, SpecVisibilityPolicyResponse

    assert {"effective", "override"} <= set(SpecVisibilityPolicyResponse.model_fields)
    assert {"specs", "excluded_specs", "hidden", "source", "source_label"} <= set(
        SpecVisibilityPolicyOut.model_fields
    )

    _spec_key(db, "material", "Material")
    contact = _contact(db)
    db.flush()
    body = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"spec_keys": ["material"], "excluded_spec_keys": None},
    ).json()
    assert set(body["effective"]) >= {"specs", "excluded_specs", "hidden", "source", "source_label"}


def test_excluded_empty_list_round_trips_as_empty(client, db):
    """AC-13: `excluded_spec_keys: []` round-trips as `[]`, not None - nothing
    hidden at that tier."""
    contact = _contact(db)
    db.flush()

    response = client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"spec_keys": None, "excluded_spec_keys": []},
    )
    assert response.status_code == 200, response.text
    assert response.json()["override"]["excluded_specs"] == []
    assert response.json()["override"]["hidden"] == []


def test_delete_on_inheriting_tier_404(client, db):
    contact = _contact(db)
    db.flush()

    response = client.delete(f"{BASE}/contacts/{contact.id}")
    assert response.status_code == 404


def test_put_and_delete_write_audit_rows(client, db):
    """AC-13: a policy row decides what a future turn tells a contact, so the
    delete half (a bulk delete never fires an ORM event) has to be audited too."""
    from app.models.access import SpecVisibilityPolicy
    from app.models.audit import AuditLog
    from app.services.audit_service import _audit_entity_type, register_audit_listeners

    register_audit_listeners()
    _spec_key(db, "thickness", "Thickness")
    contact = _contact(db)
    db.flush()

    client.put(
        f"{BASE}/contacts/{contact.id}",
        json={"spec_keys": None, "excluded_spec_keys": ["thickness"]},
    )
    row_id = str(
        db.query(SpecVisibilityPolicy.id)
        .filter(SpecVisibilityPolicy.contact_id == contact.id)
        .scalar()
    )
    client.delete(f"{BASE}/contacts/{contact.id}")

    entries = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == row_id)
        .order_by(AuditLog.changed_at)
        .all()
    )
    assert _audit_entity_type(SpecVisibilityPolicy) == "spec_visibility_policies"
    actions = [entry.action for entry in entries]
    assert "CREATE" in actions
    assert "DELETE" in actions


# ============================================================ AC-13b pending action


def _park_action(client_http, *, action_key: str, entity_type: str, entity_id: str, payload=None):
    return client_http.post(
        "/api/v1/pending-actions",
        json={
            "action_key": action_key,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "payload": payload or {},
        },
    )


def _lapse_action(db, action_id: str) -> None:
    """Move the window into the past without waiting out its real length."""
    from datetime import datetime, timedelta

    from app.models.sla import SlaFormAction

    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
        synchronize_session=False,
    )
    db.commit()


def _commit_action(client_http, db, *, entity_type: str, entity_id: str, action_id: str):
    """Lapse the window and let the lazy commit on GET apply it, as a poll would -
    same technique as `tests/test_record_actions_s6b.py::_commit_now`."""
    _lapse_action(db, action_id)
    return client_http.get(
        "/api/v1/pending-actions/current",
        params={"entity_type": entity_type, "entity_id": str(entity_id)},
    )


def test_pending_action_spec_visibility_policy_remove_deletes_override_row(client, db):
    """AC-13b: the record action key `spec_visibility_policy.remove` (registered in
    `app/services/record_actions.py` like `stock_visibility_policy.remove`) deletes
    the contact-tier row and the segment-tier row when run for each, refuses the
    default tier, and writes the same audit row the DELETE route writes.

    Must fail TODAY with the "Unknown action" refusal - the key is not registered
    yet. The park call is made BEFORE any `SpecVisibilityPolicy` row is seeded (and
    before that model is even imported) on purpose: `_record_action` checks the key
    before anything else, so this is the first thing to break, ahead of the model/
    table that also do not exist yet - the red reason stays pinned to the actual
    gap named in this AC rather than to whichever gap happens to be seeded first.
    """
    # -- contact tier ------------------------------------------------------
    contact = _contact(db)

    parked = _park_action(
        client,
        action_key="spec_visibility_policy.remove",
        entity_type="spec_visibility_policy",
        entity_id=contact.id,
        payload={"scope_kind": "contact"},
    )
    assert parked.status_code == 202, parked.text

    # Everything below only runs once the action key above is registered - by then
    # the model it needs exists too.
    from app.models.access import SpecVisibilityPolicy
    from app.models.audit import AuditLog
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    contact_row = _policy_row(
        db, contact=contact, spec_keys=None, excluded_spec_keys=["thickness"]
    )
    db.commit()

    committed = _commit_action(
        client,
        db,
        entity_type="spec_visibility_policy",
        entity_id=contact.id,
        action_id=parked.json()["id"],
    )
    assert committed.json()["last_outcome"]["status"] == "committed", committed.json()
    db.expire_all()
    assert (
        db.query(SpecVisibilityPolicy)
        .filter(SpecVisibilityPolicy.id == contact_row.id)
        .first()
        is None
    )

    # -- segment tier --------------------------------------------------------
    segment = _segment(db, unique_code("seg")[:20].lower(), "ZZT Segment")
    segment_row = _policy_row(
        db, segment=segment, spec_keys=None, excluded_spec_keys=["material"]
    )
    db.commit()

    parked_segment = _park_action(
        client,
        action_key="spec_visibility_policy.remove",
        entity_type="spec_visibility_policy",
        entity_id=segment.code,
        payload={"scope_kind": "segment"},
    )
    assert parked_segment.status_code == 202, parked_segment.text

    committed_segment = _commit_action(
        client,
        db,
        entity_type="spec_visibility_policy",
        entity_id=segment.code,
        action_id=parked_segment.json()["id"],
    )
    assert committed_segment.json()["last_outcome"]["status"] == "committed", committed_segment.json()
    db.expire_all()
    assert (
        db.query(SpecVisibilityPolicy)
        .filter(SpecVisibilityPolicy.id == segment_row.id)
        .first()
        is None
    )

    # -- the default tier is the floor of the chain and has no DELETE route -- the
    # refusal is raised inside `execute`, at COMMIT time, same as every other
    # record action (D7: the button parks unconditionally, the server applies -
    # or fails - the action when the window lapses), so parking itself still
    # accepts and the refusal shows up as a FAILED `last_outcome`.
    parked_default = _park_action(
        client,
        action_key="spec_visibility_policy.remove",
        entity_type="spec_visibility_policy",
        entity_id="default",
        payload={"scope_kind": "default"},
    )
    assert parked_default.status_code == 202, parked_default.text

    committed_default = _commit_action(
        client,
        db,
        entity_type="spec_visibility_policy",
        entity_id="default",
        action_id=parked_default.json()["id"],
    )
    assert committed_default.json()["last_outcome"]["status"] == "failed", committed_default.json()

    entries = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id.in_([str(contact_row.id), str(segment_row.id)]))
        .all()
    )
    assert "DELETE" in [entry.action for entry in entries]
