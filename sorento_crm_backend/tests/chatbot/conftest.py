"""Shared fixtures for the engine tests: a blank Postgres schema and a stubbed parser.

Postgres only, via `tests/_pg_fixture.py`. The engine's own tests run against the BLANK
schema rather than the shared database because they count rows to prove the dry run wrote
nothing (D14, AC-702's shape), and a shared prod-copy database makes "nothing was written"
unprovable.

The parser is stubbed at the same seam `tests/test_ideation_turn.py` uses for the ideation
extractor: the function that makes the provider call. No test in this suite reaches an LLM,
n8n or respond.io.
"""
from __future__ import annotations

import contextlib
from typing import Any, Iterator

import pytest

from app.models.user import SystemSetting
from tests._pg_fixture import blank_schema_engine


@pytest.fixture()
def session_factory() -> Iterator[Any]:
    """A factory of independent sessions over ONE blank schema, all discarded at teardown.

    The engine opens and closes several sessions per turn on purpose (it must not hold one
    across the LLM call), so a single fixture session would not exercise the real shape.
    Every session shares one connection inside one outer transaction, which is rolled back
    here, so nothing survives the test.
    """
    from sqlalchemy.orm import Session

    connection = blank_schema_engine().connect()
    transaction = connection.begin()
    from tests import _pg_fixture

    name = _pg_fixture._BLANK["name"]
    connection.exec_driver_sql(
        f'SET LOCAL search_path TO "{name}", "{name}_scm", "{name}_dealer_kit", '
        f'"{name}_chatbot", "{name}_projects"'
    )
    opened: list[Session] = []

    def factory() -> Session:
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        opened.append(session)
        return session

    factory.opened = opened  # type: ignore[attr-defined]
    try:
        yield factory
    finally:
        for session in opened:
            with contextlib.suppress(Exception):
                session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def counting_session_factory(session_factory):
    """The same factory, but it tracks how many sessions are OPEN right now.

    This is what makes "never hold a DB session across the LLM call" testable through the
    real seam rather than through a production hook: the stubbed parser asserts the count
    is zero while it runs.
    """
    from sqlalchemy.orm import Session

    state = {"open": 0}

    def factory() -> Session:
        session = session_factory()
        state["open"] += 1
        original_close = session.close

        def close() -> None:
            if not getattr(session, "_counted_closed", False):
                session._counted_closed = True
                state["open"] -= 1
            original_close()

        session.close = close  # type: ignore[method-assign]
        return session

    factory.state = state  # type: ignore[attr-defined]
    return factory


@pytest.fixture()
def system_settings_row(session_factory):
    """The singleton `system_settings` row, so the R1 flag can be flipped in a test."""
    db = session_factory()
    row = SystemSetting()
    db.add(row)
    db.commit()
    return row


def set_chatbot_switches(
    session_factory: Any,
    *,
    business_lane: bool | None = None,
    ordering: bool | None = None,
) -> None:
    """Set the two chatbot switches on the `system_settings` singleton (AC-810).

    They were `app.config.settings` flags until S8, and every test that wanted one on did
    `monkeypatch.setattr(settings, "chatbot_ordering_enabled", True)`. They are columns
    now, read per turn, so the ROW is the only lever and this is the one place that pulls
    it. Creates the singleton when the test has not seeded one, so a caller does not have
    to also depend on `system_settings_row`; `None` leaves a switch alone.
    """
    db = session_factory()
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting()
        db.add(row)
    if business_lane is not None:
        row.chatbot_business_lane_enabled = business_lane
    if ordering is not None:
        row.chatbot_ordering_enabled = ordering
    db.commit()
