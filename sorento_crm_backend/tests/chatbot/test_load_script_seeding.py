"""AC-711's load gate seeds access, or it measures the error path (see
`scripts/chatbot_load.py`'s module docstring for the incident this fixes).

Before this fix, `_seed_contacts` inserted `respond_contacts` rows with no
`workspace_id` and no `contact_agent_access` grant. `app/services/chatbot/head/access.py`'s
`check_access` -> `app/services/mcp_access_service.evaluate_agent` therefore denied every
mocked `business_query` turn (`deny_unknown_contact` / `deny_no_access`), `head/route.py`'s
FIRST predicate (`not access_allowed()`) forced `branch_kind = "access_denied"` on every
turn, and the resolve / tier-gate / fetch / answer stages the load gate exists to measure
never ran.

Runs against the shared database via `tests._pg_fixture.pg_session` (one transaction,
rolled back at teardown - nothing here survives the test). Per the "CI's database has no
data" lesson, every catalog row this test depends on is get-or-created inside that same
transaction rather than assumed present: the default `respond_workspaces` row and the
`access_agents` row for `scripts.chatbot_load.ACCESS_AGENT_CODE` both already exist in the
shared local (prod-copy) database but not in CI's blank one.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.access import AccessAgent
from app.models.chatbot_turn import ChatbotTurn
from app.models.respond_workspace import RespondWorkspace
from app.services.mcp_access_service import evaluate_agent
from scripts import chatbot_load
from scripts.chatbot_load import (
    ACCESS_AGENT_CODE,
    BUSINESS_BRANCH_KINDS,
    TARGET_BRANCH_KIND,
    _resolve_agent_id,
    _resolve_default_workspace_id,
    _seed_access_grants,
)
from tests._pg_fixture import pg_session, unique_code
from tests.chatbot.conftest import set_chatbot_switches


def _get_or_create_default_workspace(db) -> tuple[str, str]:
    """`(workspace_id, space_id)` of the one `is_default` row.

    Creates one only when the database has none (CI): `uq_respond_workspaces_one_default`
    allows exactly one, so a test must never insert a second beside the local dev DB's
    real one.
    """
    row = db.execute(
        text("SELECT id, space_id FROM respond_workspaces WHERE is_default IS TRUE LIMIT 1")
    ).first()
    if row is not None:
        return str(row[0]), row[1]
    workspace = RespondWorkspace(
        space_id=unique_code("space"), api_key_ciphertext="zzt-test-key", is_default=True
    )
    db.add(workspace)
    db.flush()
    return workspace.id, workspace.space_id


def _get_or_create_agent(db, code: str) -> str:
    agent_id = db.execute(
        text("SELECT id FROM access_agents WHERE code = :code"), {"code": code}
    ).scalar()
    if agent_id is not None:
        return str(agent_id)
    agent = AccessAgent(code=code, name="ZZT test agent", is_active=True)
    db.add(agent)
    db.flush()
    return agent.id


def _insert_contact(db, *, workspace_id: str) -> str:
    contact = unique_code("load")
    phone = f"+609{uuid.uuid4().int % 10**9:09d}"
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, "
            "workspace_id, session_vars) VALUES (gen_random_uuid()::text, :cid, :phone, "
            ":ws, '{}'::jsonb)"
        ),
        {"cid": contact, "phone": phone, "ws": workspace_id},
    )
    return contact


def test_seed_access_grants_passes_the_access_gate():
    """The exact bug: before `_seed_access_grants`, `evaluate_agent` denies the seeded
    contact (`deny_no_access` - the contact and its workspace both resolve, only the
    grant is missing). After it, the SAME call the S6a head's `check_access` makes
    returns `allowed=True`, which is what keeps `decide()`'s first predicate off
    `branch_kind = "access_denied"`.
    """
    with pg_session() as db:
        workspace_id, space_id = _get_or_create_default_workspace(db)
        agent_id = _get_or_create_agent(db, ACCESS_AGENT_CODE)
        contact = _insert_contact(db, workspace_id=workspace_id)

        before = evaluate_agent(
            db, agent_code=ACCESS_AGENT_CODE, contact_id=contact, space_id=space_id
        )
        assert before.allowed is False
        assert before.decision == "deny_no_access"

        _seed_access_grants(db, [contact], agent_id=agent_id)

        after = evaluate_agent(
            db, agent_code=ACCESS_AGENT_CODE, contact_id=contact, space_id=space_id
        )
        assert after.allowed is True
        assert after.decision == "allow"


def test_seed_access_grants_covers_every_seeded_contact():
    """One call, N contacts - the shape `_seed_contacts` uses for a whole burst."""
    with pg_session() as db:
        workspace_id, space_id = _get_or_create_default_workspace(db)
        agent_id = _get_or_create_agent(db, ACCESS_AGENT_CODE)
        contacts = [_insert_contact(db, workspace_id=workspace_id) for _ in range(3)]

        _seed_access_grants(db, contacts, agent_id=agent_id)

        for contact in contacts:
            decision = evaluate_agent(
                db, agent_code=ACCESS_AGENT_CODE, contact_id=contact, space_id=space_id
            )
            assert decision.allowed is True, contact


def test_resolve_helpers_find_the_seeded_catalog_rows():
    """The script's own lookups, used by `_seed_contacts` to fail loudly (SystemExit)
    rather than seed a contact that cannot pass the gate when the catalog is missing.
    """
    with pg_session() as db:
        workspace_id, _ = _get_or_create_default_workspace(db)
        agent_id = _get_or_create_agent(db, ACCESS_AGENT_CODE)

        assert _resolve_default_workspace_id(db) == workspace_id
        assert _resolve_agent_id(db, ACCESS_AGENT_CODE) == agent_id


def test_resolve_helpers_return_none_on_a_blank_schema(session_factory):
    """A brand-new install (or CI) has neither row yet - the helpers must say so with
    `None` rather than raising, so `_seed_contacts` can turn that into one clear
    `SystemExit` instead of a stack trace.
    """
    db = session_factory()
    assert _resolve_default_workspace_id(db) is None
    assert _resolve_agent_id(db, ACCESS_AGENT_CODE) is None


@pytest.fixture()
def redirect_script_session(monkeypatch, session_factory):
    """Point every `_script_session()` call inside `scripts.chatbot_load` at the
    blank-schema `session_factory` the chatbot suite already wires up (`tests/chatbot/
    conftest.py`), so `_seed_contacts` / `_delete_contacts` / `_grade_business_path` /
    the switches helpers run against an isolated schema instead of opening a real
    connection to the shared local (prod-copy) database via `app.database.SessionLocal`.
    """
    monkeypatch.setattr(chatbot_load, "_script_session", session_factory)
    return session_factory


def _insert_turn(
    session_factory,
    *,
    contact_respond_id: str,
    message_id: str,
    branch_kind: str | None,
    stage: str | None,
    status: str,
) -> None:
    db = session_factory()
    db.add(
        ChatbotTurn(
            id=str(uuid.uuid4()),
            contact_respond_id=contact_respond_id,
            message_id=message_id,
            envelope={},
            branch_kind=branch_kind,
            stage=stage,
            status=status,
        )
    )
    db.commit()


class TestDeleteContactsRemovesTheGrantToo:
    """Item 1's FK-order requirement: the grant row goes before the contact row."""

    def test_seed_then_delete_leaves_no_grant_or_contact_behind(
        self, redirect_script_session
    ):
        session_factory = redirect_script_session
        db = session_factory()
        _get_or_create_default_workspace(db)
        _get_or_create_agent(db, ACCESS_AGENT_CODE)
        db.commit()

        run_id = uuid.uuid4().hex[:8]
        contacts = [f"ZZT-load-{run_id}-{i:03d}" for i in range(2)]

        chatbot_load._seed_contacts(contacts, run_id)

        db = session_factory()
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM contact_agent_access "
                    "WHERE respond_contact_id IN (SELECT id FROM respond_contacts "
                    "WHERE respond_io_id = ANY(:ids))"
                ),
                {"ids": contacts},
            ).scalar()
            == len(contacts)
        )

        chatbot_load._delete_contacts(contacts)

        db = session_factory()
        assert (
            db.execute(
                text("SELECT count(*) FROM respond_contacts WHERE respond_io_id = ANY(:ids)"),
                {"ids": contacts},
            ).scalar()
            == 0
        )
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM contact_agent_access ca "
                    "JOIN respond_contacts rc ON rc.id = ca.respond_contact_id "
                    "WHERE rc.respond_io_id = ANY(:ids)"
                ),
                {"ids": contacts},
            ).scalar()
            == 0
        )


class TestGradeBusinessPath:
    """Item 2: the `branch_kind` histogram, and whether the business turns finished."""

    def test_counts_branch_kinds_and_a_completed_business_turn_is_not_flagged(
        self, redirect_script_session
    ):
        session_factory = redirect_script_session
        run_id = uuid.uuid4().hex[:8]
        answered = f"ZZT-load-{run_id}-000"
        refused = f"ZZT-load-{run_id}-001"
        _insert_turn(
            session_factory,
            contact_respond_id=answered,
            message_id=f"ZZT-load-{run_id}-{answered}-0",
            branch_kind="business_query",
            stage="remembered",
            status="done",
        )
        _insert_turn(
            session_factory,
            contact_respond_id=refused,
            message_id=f"ZZT-load-{run_id}-{refused}-0",
            branch_kind="access_denied",
            stage="access",
            status="done",
        )

        report = chatbot_load._grade_business_path(run_id)

        assert report.branch_kind_counts == {"business_query": 1, "access_denied": 1}
        assert report.access_denied == 1
        assert report.business_count == 1
        assert report.business_incomplete == []

    def test_flags_a_business_query_turn_that_did_not_finish(self, redirect_script_session):
        session_factory = redirect_script_session
        run_id = uuid.uuid4().hex[:8]
        contact = f"ZZT-load-{run_id}-000"
        _insert_turn(
            session_factory,
            contact_respond_id=contact,
            message_id=f"ZZT-load-{run_id}-{contact}-0",
            branch_kind="business_query",
            stage="delegated",
            status="processing",
        )

        report = chatbot_load._grade_business_path(run_id)

        assert report.business_count == 1
        assert len(report.business_incomplete) == 1
        assert "stage=delegated" in report.business_incomplete[0]

    def test_zero_business_turns_shows_up_as_zero(self, redirect_script_session):
        """The exact regression this whole fix is about: every turn `access_denied`,
        none of them `business_query` (or `check_promotion` / `stock_denied`).
        """
        session_factory = redirect_script_session
        run_id = uuid.uuid4().hex[:8]
        contact = f"ZZT-load-{run_id}-000"
        _insert_turn(
            session_factory,
            contact_respond_id=contact,
            message_id=f"ZZT-load-{run_id}-{contact}-0",
            branch_kind="access_denied",
            stage="access",
            status="done",
        )

        report = chatbot_load._grade_business_path(run_id)

        assert report.business_count == 0
        assert set(report.branch_kind_counts) & BUSINESS_BRANCH_KINDS == set()


class TestBusinessLaneSwitchesPreflight:
    """Item 3: refuse before firing a single turn when the business lane cannot both
    RUN and ANSWER `TARGET_BRANCH_KIND`."""

    def _set_completed_lanes(self, session_factory, lanes: list[str]) -> None:
        from app.models.user import SystemSetting

        db = session_factory()
        row = db.query(SystemSetting).first()
        if row is None:
            row = SystemSetting()
            db.add(row)
        row.chatbot_completed_lanes = lanes
        db.commit()

    def test_no_settings_row_refuses(self, redirect_script_session):
        assert chatbot_load._business_lane_switches() == (False, [])
        message = chatbot_load._check_business_lane_switches()
        assert message is not None
        assert "chatbot_business_lane_enabled" in message
        assert "UPDATE system_settings" in message

    def test_lane_off_refuses_even_with_the_kind_completed(self, redirect_script_session):
        session_factory = redirect_script_session
        set_chatbot_switches(session_factory, business_lane=False)
        self._set_completed_lanes(session_factory, [TARGET_BRANCH_KIND])

        message = chatbot_load._check_business_lane_switches()

        assert message is not None
        assert "chatbot_business_lane_enabled=False" in message

    def test_lane_on_but_kind_not_completed_refuses(self, redirect_script_session):
        session_factory = redirect_script_session
        set_chatbot_switches(session_factory, business_lane=True)
        self._set_completed_lanes(session_factory, ["low_signal"])

        message = chatbot_load._check_business_lane_switches()

        assert message is not None
        assert TARGET_BRANCH_KIND in message

    def test_both_configured_passes(self, redirect_script_session):
        session_factory = redirect_script_session
        set_chatbot_switches(session_factory, business_lane=True)
        self._set_completed_lanes(session_factory, [TARGET_BRANCH_KIND])

        assert chatbot_load._check_business_lane_switches() is None
