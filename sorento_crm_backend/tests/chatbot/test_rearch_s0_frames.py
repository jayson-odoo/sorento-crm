"""S0 - `conversation_frames` is the episode store; `source_type = "conversation_frame"`
is an accepted embedding source (AC-1505, PLAN-chatbot-turn-rearch.md).

Column check runs on the blank scratch schema (`ConversationFrame` is an ordinary ORM
model today, no migration-only seed involved) - `create_all` reflects whatever the
model currently declares.

`source_type = "conversation_frame"` is ALREADY an accepted embedding source today
(`app.services.embedding_worker._canonical_for_source`, written for the Phase 1 (2026)
table that was "never wired" per the plan) - that half of this AC is a GUARD, not a red,
same as AC-1507. Said explicitly here rather than left to look like an oversight.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session

EXPECTED_COLUMNS = {
    "contact_respond_id",
    "domain",
    "intent",
    "entities",
    "tools_used",
    "summary",
    "opened_at",
    "closed_at",
    "turn_ids",
}


def _columns(db) -> set[str]:
    rows = db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'conversation_frames' AND table_schema = current_schema()"
        )
    ).scalars().all()
    return set(rows)


def test_conversation_frames_table_exists():
    with blank_session() as db:
        exists = db.execute(text("SELECT to_regclass('conversation_frames')")).scalar()
        assert exists is not None


@pytest.mark.parametrize("column", sorted(EXPECTED_COLUMNS))
def test_conversation_frames_has_column(column):
    with blank_session() as db:
        present = _columns(db)
        assert column in present, sorted(present)


def test_source_type_conversation_frame_is_an_accepted_embedding_source():
    """Distinguishes "known type, no row yet" from "unsupported source type" - the
    latter is `_canonical_for_source`'s own catch-all `ValueError` at the bottom of the
    function; a registered type raises the type-specific "not found" message instead.
    """
    from app.services.embedding_worker import _canonical_for_source

    with blank_session() as db:
        with pytest.raises(ValueError) as excinfo:
            _canonical_for_source(db, "conversation_frame", "00000000-0000-0000-0000-000000000000")
        assert "Unsupported source type" not in str(excinfo.value), excinfo.value
        assert "not found" in str(excinfo.value).lower(), excinfo.value
