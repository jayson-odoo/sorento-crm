"""Group A2 - the salesperson master on the ingest surface.

  AC-A2-1  a push creates the row upper/trim-normalised, with NO company
  AC-A2-2  a re-push restates the four synced columns and leaves the annotations
  AC-A2-3  first sync adopts the row already spelled there, however it was spelled
  AC-A2-4  dry_run previews and writes nothing
  AC-A2-5  read-back answers in the canonical shape
  AC-A2-6  the edit slug is required, and a missing key is 401 not 403
  AC-A2-8  the same unqualified ref under two companies is ONE shared row

`sales_agents` is the first entity on this surface that is NOT company-scoped,
and both halves of that follow from one ruling in the model's own docstring: the
captain's files show the same agents selling for both companies, so the row is
shared (`company_id NULL`) and partitioning it would split one person's demand
class in two. Everything below exists because that makes this entity behave
differently from the six that came before it:

* the INSERT must not stamp the anchor (a stamped row is invisible to the other
  company, which is the split the shared row exists to avoid),
* adoption must match on `upper(btrim())` on BOTH sides, because the AutoCount
  mirror wrote whatever AutoCount said and a `sean i` that fails to adopt
  `SEAN I` creates the duplicate the whole master was designed against,
* and the four annotation columns - `internal_note`, `follow_up`,
  `demand_class`, `location_group` - are the captain's, filled in by hand on the
  master screen. A weekly re-sync that restated them would undo his
  classification every Monday, so they are simply not in the written column set.

Substrate: Postgres, on the shared copy of production. Every code is minted under
a `ZZTAGT` marker and every assertion is scoped to it; nothing here reads or
touches a production row.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.main  # noqa: F401  isort:skip  (registers models/handlers; see test_integration_auth_dependencies)

from app.api.v1.external import ingest as ingest_module
from app.api.v1.external.permissions import require_external_permission_for_path
from app.database import engine, get_db
from app.dependencies import get_external_api_user
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._external_auth import external_permissions_granted

MARKER = "ZZTAGT"


def _code() -> str:
    """A collision-free agent code under this suite's marker.

    Not `_pg_fixture.unique_code`: that mints `ZZT-<stem>-<hex>`, and an agent
    code is compared upper-cased, so a marker that reads the same before and
    after normalisation keeps the assertions about the normalisation honest.
    """
    return f"{MARKER}-{uuid.uuid4().hex[:6].upper()}"


def _ref(code: str) -> str:
    """The unqualified ref shape the ESB mints: `agent:{CODE}`, never per company."""
    return f"agent:{code}"


def _record(code: str, **extra) -> dict:
    return {
        "source_ref": extra.pop("ref", None) or _ref(code),
        "code": code,
        **extra,
    }


@pytest.fixture()
def db():
    """A Postgres session whose work is discarded at teardown.

    ``create_savepoint`` for the reason ``test_master_ingest_routes`` spells out:
    the code under test calls ``session.rollback()`` to make a dry run write
    nothing, and under the default join mode that would roll back the test's own
    setup too - so "the dry run wrote nothing" could not be told apart from "the
    fixture discarded everything".
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db):
    """The two routers mounted the way ``external/__init__.py`` mounts them.

    The real path guard stays in place so the entity -> slug lookup is exercised;
    ``external_permissions_granted`` says plainly that *authorization* is out of
    scope for these cases. It has its own class at the bottom of this file.
    """
    api = FastAPI()
    api.include_router(
        ingest_module.ingest_router,
        prefix="/ingest",
        dependencies=[
            Depends(require_external_permission_for_path(ingest_module.INGEST_PERMISSIONS))
        ],
    )
    api.include_router(
        ingest_module.read_router,
        prefix="/read",
        dependencies=[
            Depends(require_external_permission_for_path(ingest_module.READ_PERMISSIONS))
        ],
    )

    def _override_db():
        yield db

    api.dependency_overrides[get_db] = _override_db
    api.dependency_overrides[get_external_api_user] = lambda: {
        "id": str(uuid.uuid4()),
        "integration_id": None,
        "integration_name": "test-esb",
    }

    with external_permissions_granted():
        yield TestClient(api, raise_server_exceptions=False)


@pytest.fixture()
def company_code(db):
    """The anchor every ingest/read body carries since group A1.

    Read rather than spelled out: the incumbent's code is data on this copy of
    production, not contract.
    """
    return db.execute(
        text("SELECT code FROM companies WHERE id = :id"), {"id": DEFAULT_COMPANY_ID}
    ).scalar()


def _agent_row(db, code: str):
    """The stored row for a code, matched however it was spelled.

    Raw SQL and a normalised comparison on both sides, because which spelling
    landed is exactly what these tests are asking.
    """
    return (
        db.execute(
            text(
                "SELECT id, sales_agent, description, is_active, person_label, company_id, "
                "internal_note, follow_up, demand_class, location_group, source "
                "FROM sales_agents WHERE upper(btrim(sales_agent)) = upper(btrim(:c))"
            ),
            {"c": code},
        )
        .mappings()
        .all()
    )


def _reference_count(db, source_ref: str) -> int:
    return db.execute(
        text("SELECT count(*) FROM integration_references WHERE source_ref = :r"),
        {"r": source_ref},
    ).scalar()


class TestCreate:
    def test_a_push_creates_a_shared_row_with_the_four_synced_columns(
        self, client, db, company_code
    ):
        """AC-A2-1. The row carries no company, deliberately.

        Every other entity on this surface is stamped with the anchor. Stamping
        this one would make the agent invisible to the other company's planner
        and give the same person two demand classes - the exact split the shared
        master exists to prevent.
        """
        code = _code()
        res = client.post(
            "/ingest/sales_agents",
            json={
                "companyCode": company_code,
                "records": [
                    _record(
                        code.lower(),
                        description="Northern region",
                        person_label="Sean",
                        is_active=True,
                    )
                ],
            },
        )

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["summary"]["created"] == 1
        assert body["records"][0]["outcome"] == "created"

        rows = _agent_row(db, code)
        assert len(rows) == 1
        row = rows[0]
        # Stored upper/trim-normalised, so the next file spelling it any other
        # way resolves here instead of minting a second agent.
        assert row["sales_agent"] == code.upper()
        assert row["description"] == "Northern region"
        assert row["person_label"] == "Sean"
        assert row["is_active"] is True
        assert row["company_id"] is None
        assert _reference_count(db, _ref(code.lower())) == 1

    def test_the_created_row_is_linked_to_the_entity_the_response_names(
        self, client, db, company_code
    ):
        code = _code()
        res = client.post(
            "/ingest/sales_agents",
            json={"companyCode": company_code, "records": [_record(code)]},
        )

        entity_id = res.json()["records"][0]["entity_id"]
        assert str(_agent_row(db, code)[0]["id"]) == entity_id
        linked = db.execute(
            text(
                "SELECT entity_id FROM integration_references "
                "WHERE entity_type = 'sales_agents' AND source_ref = :r"
            ),
            {"r": _ref(code)},
        ).scalar()
        assert str(linked) == entity_id


class TestRepush:
    def test_a_repush_restates_the_synced_columns_and_leaves_the_annotations(
        self, client, db, company_code
    ):
        """AC-A2-2. The captain's four columns survive the sync.

        `demand_class`, `location_group`, `internal_note` and `follow_up` are
        decisions a human made on the master screen; AutoCount holds no opinion
        about any of them. Restating them from a payload that does not carry
        them would blank the classification every Monday, so they are not in the
        written column set at all - which is what this asserts, byte for byte.
        """
        code = _code()
        client.post(
            "/ingest/sales_agents",
            json={
                "companyCode": company_code,
                "records": [_record(code, description="First", person_label="Sean")],
            },
        )
        agent_id = _agent_row(db, code)[0]["id"]
        db.execute(
            text(
                "UPDATE sales_agents SET internal_note = :n, follow_up = true, "
                "demand_class = 'project', location_group = 'BB' WHERE id = :id"
            ),
            {"n": f"{MARKER} hand written", "id": agent_id},
        )

        res = client.post(
            "/ingest/sales_agents",
            json={
                "companyCode": company_code,
                "records": [
                    _record(
                        code,
                        description="Second",
                        person_label="Sean Lim",
                        is_active=False,
                    )
                ],
            },
        )

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "updated"

        rows = _agent_row(db, code)
        assert len(rows) == 1
        row = rows[0]
        assert str(row["id"]) == str(agent_id)
        # The four AutoCount owns:
        assert row["description"] == "Second"
        assert row["person_label"] == "Sean Lim"
        assert row["is_active"] is False
        assert row["sales_agent"] == code.upper()
        # ...and the four it does not:
        assert row["internal_note"] == f"{MARKER} hand written"
        assert row["follow_up"] is True
        assert row["demand_class"] == "project"
        assert row["location_group"] == "BB"


class TestAdoption:
    def test_first_sync_adopts_the_row_however_it_was_spelled(
        self, client, db, company_code
    ):
        """AC-A2-3. The mirror wrote AutoCount's spelling; the ESB pushes ours.

        `sales_agent_service` normalises the COLUMN as well as the value for
        exactly this reason, and adoption here has to do the same. Matching the
        raw string instead would leave `SEAN I` sitting next to `sean i`, both
        classified separately, which reads on screen as the demand class not
        working rather than as a duplicate master row.
        """
        code = _code()
        db.execute(
            text(
                "INSERT INTO sales_agents (id, sales_agent, description, is_active, source) "
                "VALUES (:i, :c, :d, true, 'manual')"
            ),
            {"i": str(uuid.uuid4()), "c": code.lower(), "d": "Hand entered"},
        )
        existing_id = _agent_row(db, code)[0]["id"]

        res = client.post(
            "/ingest/sales_agents",
            json={
                "companyCode": company_code,
                "records": [_record(code.upper(), description="From AutoCount")],
            },
        )

        assert res.status_code == 200, res.text
        entry = res.json()["records"][0]
        assert entry["outcome"] == "updated"
        assert entry["entity_id"] == str(existing_id)

        rows = _agent_row(db, code)
        assert len(rows) == 1
        assert rows[0]["description"] == "From AutoCount"
        assert rows[0]["sales_agent"] == code.upper()
        assert _reference_count(db, _ref(code.upper())) == 1


class TestDryRun:
    def test_dry_run_reports_the_verdict_and_writes_nothing(
        self, client, db, company_code
    ):
        """AC-A2-4. Every assertion here is about the absence of writes."""
        code = _code()
        db.execute(
            text(
                "INSERT INTO sales_agents (id, sales_agent, description, is_active, source) "
                "VALUES (:i, :c, 'Hand entered', true, 'manual')"
            ),
            {"i": str(uuid.uuid4()), "c": code},
        )
        # Committed so the service's rollback cannot take the setup with it.
        db.commit()

        res = client.post(
            "/ingest/sales_agents?dry_run=true",
            json={
                "companyCode": company_code,
                "records": [_record(code, description="From AutoCount")],
            },
        )

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["dry_run"] is True
        entry = body["records"][0]
        # Adoption matched, so this is an overwrite the operator gets to see first.
        assert entry["outcome"] == "updated"
        assert entry["diff"]["description"] == {
            "current": "Hand entered",
            "incoming": "From AutoCount",
        }
        assert "sales_agent" not in entry["diff"]

        rows = _agent_row(db, code)
        assert len(rows) == 1
        assert rows[0]["description"] == "Hand entered"
        assert _reference_count(db, _ref(code)) == 0

        # The control: without it, "nothing was written" could equally mean the
        # request never reached the database.
        client.post(
            "/ingest/sales_agents",
            json={
                "companyCode": company_code,
                "records": [_record(code, description="From AutoCount")],
            },
        )
        assert _agent_row(db, code)[0]["description"] == "From AutoCount"
        assert _reference_count(db, _ref(code)) == 1

    def test_dry_run_does_not_create(self, client, db, company_code):
        code = _code()
        res = client.post(
            "/ingest/sales_agents?dry_run=true",
            json={"companyCode": company_code, "records": [_record(code)]},
        )

        assert res.json()["summary"]["created"] == 1
        assert _agent_row(db, code) == []
        assert _reference_count(db, _ref(code)) == 0


class TestReadBack:
    def test_read_returns_the_canonical_shape(self, client, db, company_code):
        """AC-A2-5. The ESB diffs against this, so it answers in the vocabulary
        it pushed - a diff between two vocabularies is not a diff anyone can
        review."""
        code = _code()
        client.post(
            "/ingest/sales_agents",
            json={
                "companyCode": company_code,
                "records": [
                    _record(
                        code,
                        description="Northern region",
                        person_label="Sean",
                        is_active=False,
                    )
                ],
            },
        )

        res = client.post(
            "/read/sales_agents",
            json={
                "companyCode": company_code,
                "source_refs": [_ref(code), f"agent:{MARKER}-NOSUCH"],
            },
        )

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["not_found"] == [f"agent:{MARKER}-NOSUCH"]
        record = body["records"][0]
        assert record["code"] == code.upper()
        assert record["description"] == "Northern region"
        assert record["person_label"] == "Sean"
        assert record["is_active"] is False
        assert record["entity_id"] == str(_agent_row(db, code)[0]["id"])


# ============================================================== authorization
# The real guard, no `external_permissions_granted` anywhere in this class: the
# question is whether the surface is gated at all, so bypassing the gate would
# answer it by assumption.
class TestPermission:
    @pytest.fixture()
    def guard_db(self):
        from app.models.integration import Integration, IntegrationApiKey
        from app.models.user import (
            User,
            UserPermission,
            UserRole,
            UserRoleAssignment,
            UserRolePermission,
        )
        from tests._pg_fixture import pg_empty_schema

        with pg_empty_schema(
            [
                User.__table__,
                UserRole.__table__,
                UserRoleAssignment.__table__,
                UserPermission.__table__,
                UserRolePermission.__table__,
                Integration.__table__,
                IntegrationApiKey.__table__,
            ]
        ) as session:
            yield session

    @pytest.fixture()
    def guard_client(self, guard_db):
        """A stand-in route behind the REAL ingest guard.

        The handler is a stub rather than the ingest route because what is under
        test is the gate, and running the ingest itself here would need the whole
        master schema in this empty one for no gain.
        """
        api = FastAPI()

        @api.post("/ingest/{entity}")
        def _stub(
            entity: str,
            _: dict = Depends(
                require_external_permission_for_path(ingest_module.INGEST_PERMISSIONS)
            ),
        ):
            return {"ok": entity}

        def _override_db():
            yield guard_db

        api.dependency_overrides[get_db] = _override_db
        return TestClient(api, raise_server_exceptions=False)

    @pytest.fixture()
    def keys(self, guard_db):
        """Two integrations: one holding the edit slug, one holding only view."""
        from app.models.integration import Integration
        from app.models.user import (
            User,
            UserPermission,
            UserRole,
            UserRoleAssignment,
            UserRolePermission,
        )
        from app.services.integration_key_service import IntegrationKeyService

        perms = {}
        for slug in (
            ingest_module.INGEST_PERMISSIONS["sales_agents"],
            ingest_module.READ_PERMISSIONS["sales_agents"],
        ):
            perm = UserPermission(slug=slug, name=slug)
            guard_db.add(perm)
            guard_db.flush()
            perms[slug] = perm

        issued = {}
        for label, held in (
            ("editor", [ingest_module.INGEST_PERMISSIONS["sales_agents"]]),
            ("viewer", [ingest_module.READ_PERMISSIONS["sales_agents"]]),
        ):
            user = User(
                email=f"{MARKER.lower()}-{label}@integrations.local",
                name=f"Integration: {label}",
                status="ACTIVE",
                is_integration=True,
            )
            guard_db.add(user)
            guard_db.flush()
            role = UserRole(slug=f"{MARKER.lower()}_{label}", name=f"{MARKER} {label}")
            guard_db.add(role)
            guard_db.flush()
            guard_db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
            for slug in held:
                guard_db.add(
                    UserRolePermission(role_id=role.id, permission_id=perms[slug].id)
                )
            guard_db.flush()
            integration = Integration(
                name=f"{MARKER}-{label}", type="autocount_esb", act_as_user_id=user.id,
                is_active=True,
            )
            guard_db.add(integration)
            guard_db.flush()
            issued[label] = IntegrationKeyService(guard_db).issue_key(integration)
        return issued

    def test_no_key_is_401(self, guard_client, keys):
        assert guard_client.post("/ingest/sales_agents").status_code == 401

    def test_a_key_without_the_edit_slug_is_403_naming_it(self, guard_client, keys):
        # AC-A2-6. View is not enough: writing an agent through the ESB is the
        # same act as writing one through the master screen.
        res = guard_client.post(
            "/ingest/sales_agents", headers={"X-API-Key": keys["viewer"]}
        )
        assert res.status_code == 403
        assert "master_data.sales_agents.edit" in res.text

    def test_the_edit_slug_passes(self, guard_client, keys):
        # The control. Without it a 403 for everybody would pass the test above.
        res = guard_client.post(
            "/ingest/sales_agents", headers={"X-API-Key": keys["editor"]}
        )
        assert res.status_code == 200, res.text


# ====================================================== one agent, two companies
# AC-A2-8, and the reason section 7.6 of the plan exists. The ESB mints the ref
# UNQUALIFIED (`agent:{CODE}`), so both companies' pushes carry the same ref and
# must land on the same shared row. Anything else and the second company's push
# is `failed` with a ReferenceConflict, which is what the shared-service session
# was told would not happen.
def test_the_same_ref_under_two_companies_is_one_shared_row():
    from app.main import app
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db as app_get_db,
        get_external_api_user,
    )
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.integration import Integration
    from app.models.user import User, UserRole, UserRoleAssignment
    from app.services.company_scope_resolver import apply_company_scope
    from tests._pg_fixture import blank_session

    user_id = "5b8b9c10-1111-4222-8333-4444555566a1"
    role_id = "5b8b9c10-2222-4222-8333-4444555566a2"

    with blank_session() as db:
        db.add(
            UserRole(
                id=role_id,
                slug="superadmin",
                name=f"{MARKER} Superadmin",
                description="",
                is_protected=True,
                is_default=False,
            )
        )
        db.flush()
        db.add(
            User(
                id=user_id,
                name=f"{MARKER} admin",
                email=f"{MARKER.lower()}-admin@test.com",
                password="x",
                status="active",
            )
        )
        db.flush()
        db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
        db.flush()

        suffix = uuid.uuid4().hex[:8]
        other = Company(id=str(uuid.uuid4()), name=f"{MARKER} B {suffix}", code=f"ZG{suffix}")
        db.add(other)
        db.flush()
        company_a_code = db.execute(
            text("SELECT code FROM companies WHERE id = :id"), {"id": DEFAULT_COMPANY_ID}
        ).scalar()

        def _override_get_db():
            yield db

        def _override_user():
            return {"id": user_id, "email": f"{MARKER.lower()}-admin@test.com"}

        def _override_company_scope():
            set_company_scope(db, None)
            return None

        app.dependency_overrides[app_get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_current_user_or_api_key] = _override_user
        app.dependency_overrides[get_external_api_user] = _override_user
        app.dependency_overrides[apply_company_scope] = _override_company_scope
        try:
            with TestClient(app) as client:
                code = _code()
                first = client.post(
                    "/api/v1/external/ingest/sales_agents",
                    json={
                        "companyCode": company_a_code,
                        "records": [_record(code, description="Pushed by A")],
                    },
                )
                assert first.status_code == 200, first.text
                assert first.json()["records"][0]["outcome"] == "created"

                # Company B's extract, same agent, same unqualified ref, carried
                # by a DIFFERENT integration - the ESB runs one per AutoCount
                # database, so this is the ordinary case and not an edge one.
                # A real row, because the half of section 7.6(b) under test is
                # that `link()` re-points the existing mapping at whoever pushed
                # last instead of refusing it, and `integration_id=None` on both
                # pushes would never have exercised that.
                second_integration = Integration(
                    id=str(uuid.uuid4()),
                    name=f"{MARKER} esb B {uuid.uuid4().hex[:6]}",
                    type="esb",
                )
                db.add(second_integration)
                db.flush()
                app.dependency_overrides[get_external_api_user] = lambda: {
                    "id": user_id,
                    "email": f"{MARKER.lower()}-admin@test.com",
                    "integration_id": str(second_integration.id),
                }
                second = client.post(
                    "/api/v1/external/ingest/sales_agents",
                    json={
                        "companyCode": other.code,
                        "records": [_record(code, description="Pushed by B")],
                    },
                )
                assert second.status_code == 200, second.text
                entry = second.json()["records"][0]
                assert entry["outcome"] == "updated", entry

                rows = (
                    db.execute(
                        text(
                            "SELECT id, company_id, description FROM sales_agents "
                            "WHERE upper(btrim(sales_agent)) = :c"
                        ),
                        {"c": code.upper()},
                    )
                    .mappings()
                    .all()
                )
                assert len(rows) == 1
                assert rows[0]["company_id"] is None
                assert rows[0]["description"] == "Pushed by B"
                # One mapping, re-pointed in place at the integration that
                # pushed last. A second row here would be the shared agent
                # linked twice, which is the duplicate this whole path exists
                # to prevent.
                mapping = (
                    db.execute(
                        text(
                            "SELECT integration_id FROM integration_references "
                            "WHERE entity_type = 'sales_agents' AND entity_id = :e"
                        ),
                        {"e": str(rows[0]["id"])},
                    )
                    .mappings()
                    .all()
                )
                assert len(mapping) == 1
                assert str(mapping[0]["integration_id"]) == str(second_integration.id)
        finally:
            app.dependency_overrides.clear()
