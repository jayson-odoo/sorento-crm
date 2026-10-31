"""CONSOLE-SWITCH-OVERRIDE: a console turn runs with every lane on FOR ITSELF ONLY.

It used to write `system_settings.chatbot_business_lane_enabled = true` and
`chatbot_completed_lanes = every lane` around its turn and restore them in a `finally`.
Live WhatsApp turns read that row fresh per turn, so while a console turn ran, every live
turn for every contact ran all lanes in the CRM, and two overlapping console turns could
restore "all on" for good. Now the console passes `run_turn(switch_overrides=...)` and
the stored row is never written.

The three claims, each kill-checked by restoring the old write:
1. the `system_settings` row is identical before and after, and nothing writes it
   during the turn (a flush/statement spy);
2. a live turn's switch read DURING a console turn sees the stored switches;
3. the console turn itself still runs with every lane on.
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.user import SystemSetting
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import BRANCH_KINDS
from app.services.chatbot.head import parser as parser_mod

from tests.chatbot.test_console_turn_endpoint import (  # noqa: F401 - pytest fixtures
    CONSOLE_TURN_URL,
    CONTACT_ID,
    NOT_SUPPORTED_OUTPUT,
    _permissions,
    _run_id,
    client,
    seeded_contact_with_a_prior_turn,
    stub_console_seams,
)
from tests.chatbot.test_engine import _envelope

# The owner's stored switches: business lane OFF, one lane completed. Anything but
# "all on", so a leak of the console's override into the row shows.
STORED_LANES = ["low_signal"]


@pytest.fixture()
def stored_switches(session_factory, system_settings_row):
    db = session_factory()
    row = db.query(SystemSetting).first()
    row.chatbot_business_lane_enabled = False
    row.chatbot_completed_lanes = list(STORED_LANES)
    db.commit()
    db.close()


def _stored(session_factory) -> tuple[bool, Any]:
    db = session_factory()
    try:
        row = db.query(SystemSetting).first()
        return bool(row.chatbot_business_lane_enabled), row.chatbot_completed_lanes
    finally:
        db.close()


@pytest.fixture()
def settings_write_spy():
    """Every ORM flush or SQL statement that would write `system_settings`."""
    writes: list[str] = []

    def before_flush(session, flush_context, instances):
        for obj in list(session.dirty) + list(session.new) + list(session.deleted):
            if isinstance(obj, SystemSetting) and session.is_modified(obj):
                writes.append(f"orm flush of {type(obj).__name__}")

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        head = statement.lstrip().upper()
        if head.startswith(("UPDATE", "INSERT", "DELETE")) and "SYSTEM_SETTINGS" in head:
            writes.append(statement.split("\n", 1)[0])

    event.listen(Session, "before_flush", before_flush)
    event.listen(Engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield writes
    finally:
        event.remove(Session, "before_flush", before_flush)
        event.remove(Engine, "before_cursor_execute", before_cursor_execute)


@pytest.fixture()
def mid_turn(monkeypatch, session_factory):
    """Runs inside the console turn (at the parse): what is STORED at that moment, and
    what a live turn's own switch read (`engine._read_switches`, the call `_run_turn`
    makes at its first session) returns."""
    seen: dict[str, Any] = {}

    def fake_parse(config, user_block):
        seen["stored"] = _stored(session_factory)
        db = session_factory()
        try:
            seen["live_read"] = engine_mod._read_switches(db)
        finally:
            db.close()
        return NOT_SUPPORTED_OUTPUT

    monkeypatch.setattr(parser_mod, "parse", fake_parse)
    return seen


@pytest.fixture()
def lanes_the_turn_used(monkeypatch):
    """The switch snapshot the console turn routed on (`_enabled_lanes(db, switches)`)."""
    seen: list[Any] = []
    real = engine_mod._enabled_lanes

    def spy(db, row=engine_mod._UNSET):
        seen.append(row)
        return real(db, row)

    monkeypatch.setattr(engine_mod, "_enabled_lanes", spy)
    return seen


def _console_turn(client):
    resp = client.post(
        CONSOLE_TURN_URL,
        json={
            "contact_respond_id": str(CONTACT_ID),
            "text": "can I submit a goods receive here",
            "run_id": _run_id(),
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestConsoleTurnNeverWritesSystemSettings:
    def test_row_identical_and_no_write_during_the_turn(
        self, client, session_factory, seeded_contact_with_a_prior_turn, stored_switches,
        stub_console_seams, mid_turn, settings_write_spy,
    ):
        before = _stored(session_factory)
        _console_turn(client)
        after = _stored(session_factory)

        assert after == before == (False, STORED_LANES)
        assert mid_turn["stored"] == before, "the stored row changed while the console turn ran"
        assert settings_write_spy == [], f"a console turn wrote system_settings: {settings_write_spy}"

    def test_a_live_turn_during_a_console_turn_reads_the_stored_switches(
        self, client, session_factory, seeded_contact_with_a_prior_turn, stored_switches,
        stub_console_seams, mid_turn,
    ):
        _console_turn(client)
        live = mid_turn["live_read"]
        assert live.chatbot_business_lane_enabled is False
        assert live.chatbot_completed_lanes == STORED_LANES


class TestConsoleTurnStillRunsEveryLane:
    def test_the_console_turn_routes_with_every_lane_on(
        self, client, session_factory, seeded_contact_with_a_prior_turn, stored_switches,
        stub_console_seams, mid_turn, lanes_the_turn_used,
    ):
        body = _console_turn(client)
        # `goods_receive` is a canned `not_supported` answer only when that lane completes;
        # with the stored `["low_signal"]` it would delegate to n8n with an empty reply.
        assert body["branch_kind"] == "not_supported"
        assert body["reply_text"] or body["send_messages"]
        assert lanes_the_turn_used, "the turn never read its lane switches"
        used = lanes_the_turn_used[0]
        assert used.chatbot_business_lane_enabled is True
        assert set(used.chatbot_completed_lanes) == set(BRANCH_KINDS)

    def test_an_overridden_turn_never_offloads_to_the_worker(
        self, client, session_factory, seeded_contact_with_a_prior_turn, stored_switches,
        stub_console_seams, mid_turn, monkeypatch,
    ):
        # The override does not travel through the RQ queue, so a worker would run the
        # turn on the STORED switches. With the offload on, the console must stay in-process.
        monkeypatch.setattr(engine_mod.settings, "chatbot_turn_on_worker", True)

        def no_worker(*args, **kwargs):
            raise AssertionError("an overridden turn was offloaded to the worker")

        monkeypatch.setattr(engine_mod, "_run_on_worker", no_worker)
        body = _console_turn(client)
        assert body["branch_kind"] == "not_supported"


def test_unknown_override_key_is_refused(session_factory):
    with pytest.raises(ValueError, match="chatbot_no_such_switch"):
        engine_mod.run_turn(
            _envelope(),
            session_factory=session_factory,
            switch_overrides={"chatbot_no_such_switch": True},
        )
