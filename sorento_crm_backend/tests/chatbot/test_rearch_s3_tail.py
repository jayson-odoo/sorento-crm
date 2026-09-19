"""S3 - tail persist (AC-1532, PLAN-chatbot-turn-rearch.md "Tail").

`turn/tail.py::persist(state, answer, ctx)` does not exist yet, so every test in
`TestPersist*` below is RED at collection with `ModuleNotFoundError: No module named
'app.services.chatbot.turn.tail'`.

The FOR UPDATE write seam is the ALREADY-COMMITTED
`app.services.conversation_variables_service.overwrite_for_contact` (measured: its own
SQL is `SELECT id FROM respond_contacts WHERE respond_io_id = :cid FOR UPDATE`). AC-1532
says "persists the five keys under FOR UPDATE" - the five keys (`focus`,
`open_question`, `ideation`, `access_levels`, `contains_flyer`) are pinned by S0's
`SessionVars` (`test_rearch_s0_session_slots.py`), so this file asserts on the
`open_question` key of the dict `persist` hands that seam, spied via monkeypatch.

**Ambiguity flagged to the captain**: "the offer team recorded equals the team the
composer returned" - `turn/pending.py::Pending.team` (already committed, S2) is a single
`str | None`, while `Answer.offer.teams` (AC-1531) is a LIST (a team_pick over 2+ missed
domains has more than one). This file tests only the single-team case
(`Pending.team == answer.offer.teams[0]` when `len(teams) == 1`) against
`open_question["team"]`; how a MULTI-team offer's team set is recorded (a second field,
or held only in `open_question["options"]`) is not specified anywhere in the PLAN/UAC
and is left to the coder, not resolved here.
"""
from __future__ import annotations

import pathlib
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.chatbot.turn.pending import ask as pending_ask
from app.services.chatbot.turn.state import Focus, Profile, State

CHATBOT_PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"

RETIRED_NAMES = [
    "record_offer",
    "team_from_reply",
    "_spend_the_answer",
    "with_offer",
    "_re_armed",
    "_partial_dym_block",
    "_picker_carry",
    "_offer_carry",
]


def _state(pending=None) -> State:
    return State(focus=Focus(), pending=pending, profile=Profile(), turn_no=3)


class _StubAnswer:
    def __init__(self, *, question=None, offer=None) -> None:
        self.question = question
        self.offer = offer
        self.sections = []
        self.canned = []
        self.text = "ok"
        self.actions = []


class _StubOffer:
    def __init__(self, teams: list[str]) -> None:
        self.teams = teams


def _ctx(**overrides: Any) -> SimpleNamespace:
    base = dict(contact_respond_id="ZZT-tail-1")
    base.update(overrides)
    return SimpleNamespace(**base)


def _persist(state, answer, ctx):
    from app.services.chatbot.turn import tail as tail_mod

    return tail_mod, tail_mod.persist(state, answer, ctx)


class TestPersistWritesPendingFromAnswerQuestion:
    def test_pending_question_becomes_open_question(self, monkeypatch) -> None:
        recorded: dict[str, Any] = {}

        def fake_overwrite(db, *, respond_io_id, state):
            recorded["respond_io_id"] = respond_io_id
            recorded["state"] = state
            return state

        tail_mod, _ = self._patched_persist(monkeypatch, fake_overwrite)

        question = pending_ask("product_pick", [{"position": 1, "label": "A"}], asked_at_turn=3)
        answer = _StubAnswer(question=question)

        tail_mod.persist(_state(), answer, _ctx())

        assert recorded["state"].get("open_question") is not None, recorded
        assert recorded["state"]["open_question"].get("kind") == "product_pick"

    def test_no_question_leaves_open_question_none(self, monkeypatch) -> None:
        recorded: dict[str, Any] = {}

        def fake_overwrite(db, *, respond_io_id, state):
            recorded["state"] = state
            return state

        tail_mod, _ = self._patched_persist(monkeypatch, fake_overwrite)

        answer = _StubAnswer(question=None)
        tail_mod.persist(_state(), answer, _ctx())

        assert recorded["state"].get("open_question") is None, recorded

    def _patched_persist(self, monkeypatch, fake_overwrite):
        from app.services.chatbot.turn import tail as tail_mod

        monkeypatch.setattr(tail_mod, "overwrite_for_contact", fake_overwrite)
        return tail_mod, None


class TestOfferTeamRecorded:
    def test_single_team_offer_recorded_on_open_question(self, monkeypatch) -> None:
        from app.services.chatbot.turn import tail as tail_mod

        recorded: dict[str, Any] = {}

        def fake_overwrite(db, *, respond_io_id, state):
            recorded["state"] = state
            return state

        monkeypatch.setattr(tail_mod, "overwrite_for_contact", fake_overwrite)

        question = pending_ask("team_pick", [{"position": 1, "label": "Purchasing"}], team="purchasing", asked_at_turn=3)
        answer = _StubAnswer(question=question, offer=_StubOffer(["purchasing"]))

        tail_mod.persist(_state(), answer, _ctx())

        assert recorded["state"]["open_question"]["team"] == answer.offer.teams[0]


class TestPersistUsesForUpdate:
    def test_persist_calls_the_for_update_seam(self, monkeypatch) -> None:
        from app.services.chatbot.turn import tail as tail_mod
        from app.services import conversation_variables_service as cvs_mod

        calls: list[dict[str, Any]] = []

        def spy(db, *, respond_io_id, state):
            calls.append({"respond_io_id": respond_io_id, "state": state})
            return state

        # Patch the ACTUAL seam, imported into tail.py, not a bare local mock - so this
        # proves `persist` calls INTO the FOR UPDATE seam (`overwrite_for_contact`'s own
        # SQL is `... FOR UPDATE`), not merely that some function ran.
        monkeypatch.setattr(cvs_mod, "overwrite_for_contact", spy)
        monkeypatch.setattr(tail_mod, "overwrite_for_contact", spy, raising=False)

        answer = _StubAnswer(question=None)
        tail_mod.persist(_state(), answer, _ctx(contact_respond_id="ZZT-tail-for-update"))

        assert calls, "persist() must call the FOR UPDATE seam (overwrite_for_contact)"
        assert calls[0]["respond_io_id"] == "ZZT-tail-for-update"


class TestRetiredNamesGrepGuard:
    """AC-1532's own retired-name list. Duplicated (narrower) by AC-1594's dedicated
    deletions file - this copy exists because AC-1532 names it as its own evidence."""

    @pytest.mark.parametrize("name", RETIRED_NAMES)
    def test_retired_name_gone_from_chatbot_package(self, name: str) -> None:
        hits = [
            f
            for f in CHATBOT_PACKAGE.rglob("*.py")
            if name in f.read_text(encoding="utf-8", errors="ignore")
        ]
        assert not hits, f"{name} still referenced in: {hits}"
