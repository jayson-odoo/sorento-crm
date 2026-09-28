"""Fix round 6 on PR #1304: episode summaries a person reads in one pass.

Owner hand test, 28 Sep 2026: "the summary and the answer is too messy for me [...]
the structure of our summary is quite messy". The recall reply and the contact's
Conversations card showed `Tue 8 Sep, 639 turns: (declined); (escalated); inventory
MWT5727SS-CR, ... (answered); ...` and bare `(escalated); (not found).` rows.

Pinned here:
* the stored summary is prose, asked then got then still open: no bracket tags, no
  semicolon chains, no date header, no turn count, never over 240 chars;
* the three conversations the owner saw, before and after, word for word;
* the recall reply is one numbered line per conversation, `date, Topic: sentence`,
  with a subject in every line, no turn counts and the "reply with a number" close;
* a summary stored before this round is never shown as tags: every reader goes
  through `readable_summary`, and the backfill script rewrites it from its turns;
* the Conversations card rows carry the same sentence;
* three worst-case lines still fit the L4 memory layer cap.
"""
from __future__ import annotations

import importlib.util
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.models.chatbot_turn import ChatbotTurn
from app.models.conversation_frame import ConversationFrame
from app.services.chatbot.turn import context as context_mod
from app.services.chatbot.turn import episode_digest
from app.services.chatbot.turn.episode_digest import digest
from tests.chatbot.test_engine import CONTACT_ID, stub_access  # noqa: F401
from tests.chatbot.test_memory_s4_fallback_replay import (  # noqa: F401
    _run_turn,
    _seed_contact,
    _seed_frames,
    lane,
    sent_text,
)

_TAG = re.compile(r"\((answered|not found|asked back|escalated|declined|denied)\)")
_TURN_COUNT = re.compile(r"\b\d+ turns?\b")
_LINE = re.compile(r"^\d+\. (Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Z][a-z]{2}, [A-Z][^:]*: (Asked|Small talk) ")

BASE = datetime(2026, 9, 28, 2, 0, tzinfo=timezone.utc)


def _turn(
    n: int,
    *,
    domain: str | None = None,
    codes: tuple[str, ...] = (),
    branch_kind: str = "business_query",
    missed: bool = False,
    offer_team: str | None = None,
    ask: str | None = None,
) -> dict[str, Any]:
    """One turn dict in the shape `chatbot.turns` rows project to."""
    trace: list[dict[str, Any]] = [
        {
            "kind": "apply",
            "verdict": {
                "domain_hint": domain,
                "entities": [{"canonical_code": c} for c in codes],
            },
            "plan": {"domains": [domain] if domain else [], "ask": ask},
        }
    ]
    if domain and branch_kind == "business_query":
        trace.append(
            {"stage": "looked_up", "status": "ok", "facts": {"sections": 1, "missed": [domain] if missed else []}}
        )
    if offer_team:
        trace.append({"kind": "memory", "open_question": {"after": {"kind": "team_pick", "team": offer_team}}})
    return {
        "id": f"t{n}",
        "created_at": BASE + timedelta(minutes=n),
        "branch_kind": branch_kind,
        "status": "done",
        "message": "",
        "trace": trace,
        "result_refs": [],
    }


def _owner_conversation_1() -> list[dict[str, Any]]:
    """`Mon 28 Sep, 7 turns: incoming (answered); offered purchasing team, no answer`."""
    turns = [_turn(i, branch_kind="low_signal") for i in range(5)]
    turns.append(_turn(5, domain="incoming"))
    turns.append(_turn(6, domain="incoming", offer_team="purchasing"))
    return turns


def _owner_conversation_2() -> list[dict[str, Any]]:
    """`Mon 28 Sep, 1 turns: inventory srtwc286 (answered); offered warehouse team, no answer`."""
    t = _turn(0, domain="inventory", offer_team="warehouse")
    t["trace"][0]["verdict"]["entities"] = [{"raw": "srtwc286"}]
    return [t]


def _owner_conversation_3() -> list[dict[str, Any]]:
    """`Tue 8 Sep, 639 turns: (declined); (escalated); inventory MWT5727SS-CR, MHS1028,
    MSK11A-QT (answered); incoming TGHU6295708 (not found); incoming srtwb1542 (not
    found); incoming IBKS7245-NG-BL (answered); ideate (answered); order hanlim, rp`."""
    return [
        _turn(0, branch_kind="escalation_declined"),
        _turn(1, branch_kind="out_of_scope"),
        _turn(2, domain="inventory", codes=("MWT5727SS-CR", "MHS1028", "MSK11A-QT")),
        _turn(3, domain="incoming", codes=("TGHU6295708",), missed=True),
        _turn(4, domain="incoming", codes=("SRTWB1542",), missed=True),
        _turn(5, domain="incoming", codes=("IBKS7245-NG-BL",)),
        _turn(6, domain="ideate"),
        _turn(7, domain="order", codes=("hanlim", "rp")),
    ]


OWNER_AFTER = {
    "conversation_1": (
        _owner_conversation_1,
        "Asked about incoming stock and got an answer. "
        "Still open: the offer to pass this to the purchasing team got no reply.",
    ),
    "conversation_2": (
        _owner_conversation_2,
        "Asked about stock for SRTWC286 and got an answer. "
        "Still open: the offer to pass this to the warehouse team got no reply.",
    ),
    "conversation_3": (
        _owner_conversation_3,
        "Asked about stock, incoming stock, product ideas and orders. "
        "TGHU6295708 and SRTWB1542 were not found, the rest got an answer. "
        "Was offered our staff, said no once and was passed on once.",
    ),
}


def _assert_readable(summary: str) -> None:
    assert summary, "a summary is never empty"
    assert "(" not in summary and ")" not in summary, f"bracket in {summary!r}"
    assert ";" not in summary, f"semicolon chain in {summary!r}"
    assert not _TURN_COUNT.search(summary), f"turn count in {summary!r}"
    assert not re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ", summary), f"date header in {summary!r}"
    assert summary.startswith(("Asked ", "Small talk")), f"no subject first in {summary!r}"
    assert summary.endswith("."), summary
    assert len(summary) <= 200, (len(summary), summary)


class TestTheOwnersThreeConversations:
    @pytest.mark.parametrize("name", sorted(OWNER_AFTER))
    def test_after(self, name: str) -> None:
        build, expected = OWNER_AFTER[name]
        summary = digest(build())["summary"]
        assert summary == expected
        _assert_readable(summary)

    def test_a_tag_only_episode_still_names_what_happened(self) -> None:
        """`Tue 8 Sep, 41 turns: (escalated); (not found).` on the owner's card."""
        turns = [_turn(0, branch_kind="out_of_scope"), _turn(1, domain=None)]
        turns[1]["trace"].append({"stage": "looked_up", "status": "failed", "facts": {}})
        summary = digest(turns)["summary"]
        assert summary == "Asked for something the bot does not cover, but nothing was found. Was passed to our staff."
        _assert_readable(summary)


class TestShapeHoldsForEveryMix:
    @pytest.mark.parametrize(
        "turns",
        [
            [_turn(0, branch_kind="low_signal")],
            [_turn(0, domain="inventory", codes=("A1",))],
            [_turn(0, domain="inventory", codes=("A1",), missed=True)],
            [_turn(0, domain="inventory", codes=("A1",)), _turn(1, domain="inventory", codes=("B2",), missed=True)],
            [_turn(0, domain="order", ask="which_order")],
            [_turn(0, branch_kind="access_denied", domain="sales_report")],
            [_turn(0, branch_kind="escalation_declined")],
            [_turn(i, domain=d, codes=(f"CODE{i}X", f"CODE{i}Y", f"CODE{i}Z", f"CODE{i}W"))
             for i, d in enumerate(("inventory", "incoming", "order", "promotion", "purchase_order", "ideate"))],
        ],
        ids=["small-talk", "answered", "missed", "mixed", "asked-back", "denied", "declined", "six-topics"],
    )
    def test_no_tags_no_counts_no_date_subject_first(self, turns: list[dict[str, Any]]) -> None:
        _assert_readable(digest(turns)["summary"])

    def test_a_long_episode_drops_codes_before_topics(self) -> None:
        summary = digest(
            [_turn(i, domain=d, codes=(f"LONGCODE{i}AAAA", f"LONGCODE{i}BBBB", f"LONGCODE{i}CCCC"))
             for i, d in enumerate(("inventory", "incoming", "order", "promotion"))]
        )["summary"]
        for noun in ("stock", "incoming stock", "orders", "promotions"):
            assert noun in summary, summary

    def test_no_figure_leaks_in(self) -> None:
        t = _turn(0, domain="inventory", codes=("SRTWB1455",))
        t["trace"].append({"stage": "replied", "status": "done", "facts": {"text": "137 units at RM45.90"}})
        summary = digest([t])["summary"]
        assert "137" not in summary and "45.90" not in summary


class TestOldStoredSummariesNeverShow:
    OWNER_BEFORE = (
        "Tue 8 Sep, 639 turns: (declined); (escalated); inventory MWT5727SS-CR, MHS1028, MSK11A-QT (answered).",
        "Tue 8 Sep, 41 turns: (escalated); (not found).",
        "Mon 28 Sep, 1 turns: inventory srtwc286 (answered); offered warehouse team, no answer.",
        "Thu 25 Sep: stock SRTWB1455 (answered).",
    )

    @pytest.mark.parametrize("before", OWNER_BEFORE)
    def test_is_legacy(self, before: str) -> None:
        assert episode_digest.is_legacy_summary(before)

    @pytest.mark.parametrize("after", [v[1] for v in OWNER_AFTER.values()])
    def test_a_new_summary_is_not_legacy(self, after: str) -> None:
        assert not episode_digest.is_legacy_summary(after)

    def test_read_time_fallback_uses_the_frame_columns(self) -> None:
        text_value = episode_digest.readable_summary(
            self.OWNER_BEFORE[2], "inventory", {"product": ["srtwc286"]}
        )
        # The old text's own tags still say it was answered and the offer is open.
        assert text_value == OWNER_AFTER["conversation_2"][1]
        _assert_readable(text_value)

    def test_read_time_fallback_with_nothing_named(self) -> None:
        text_value = episode_digest.readable_summary(self.OWNER_BEFORE[1], None, {})
        assert text_value == (
            "Asked for something the bot does not cover, but nothing was found. Was passed to our staff."
        )
        _assert_readable(text_value)

    def test_the_line_is_date_topic_sentence(self) -> None:
        line = episode_digest.episode_line(datetime(2026, 9, 8, 2, 0), "inventory", "Asked about stock for A1.")
        assert line == "Tue 8 Sep, Stock: Asked about stock for A1."


# --------------------------------------------------------------------------- #
# The recall reply, end to end through the engine
# --------------------------------------------------------------------------- #


class TestRecallReply:
    def test_numbered_lines_read_date_topic_sentence(self, session_factory, stub_access, lane) -> None:
        _seed_contact(session_factory, {}, level="episodes")
        _seed_frames(
            session_factory,
            [
                # Stored before this round, as the owner's database holds them.
                {"days_ago": 1, "domain": "incoming", "summary": "Mon 28 Sep, 7 turns: incoming (answered); "
                 "offered purchasing team, no answer.", "entities": {}},
                {"days_ago": 2, "domain": "inventory", "summary": "Mon 28 Sep, 1 turns: inventory srtwc286 "
                 "(answered); offered warehouse team, no answer.", "entities": {"product": ["srtwc286"]}},
                {"days_ago": 3, "domain": None, "summary": "Tue 8 Sep, 41 turns: (escalated); (not found).",
                 "entities": {}},
                # Stored after it.
                {"days_ago": 4, "domain": "order", "summary": "Asked about orders for hanlim and got an answer."},
            ],
            is_test=False,
        )
        result, _prompt = _run_turn(
            session_factory,
            stub_access,
            message="what did i ask",
            verdict_overrides={"message_type": "history_question"},
            n=5,
            console=False,
        )
        text_value = sent_text(result)
        lines = [ln for ln in text_value.splitlines() if re.match(r"^\d+\. ", ln)]
        assert len(lines) == 4, text_value
        for ln in lines:
            assert _LINE.match(ln), f"not `N. date, Topic: sentence`: {ln!r}"
            assert not _TURN_COUNT.search(ln), ln
            assert not _TAG.search(ln) and ";" not in ln, ln
        assert ", Stock: Asked about stock for SRTWC286" in text_value, text_value
        assert ", Orders: Asked about orders for hanlim and got an answer" in text_value, text_value
        assert "Reply with a number and I'll run it again with today's figures." in text_value


# --------------------------------------------------------------------------- #
# The Conversations card and the backfill rewrite
# --------------------------------------------------------------------------- #


def _backfill_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "backfill_chatbot_episodes.py"
    spec = importlib.util.spec_from_file_location("backfill_chatbot_episodes_r6", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestCardAndBackfill:
    def test_card_rows_never_show_tags(self, session_factory) -> None:
        from app.services.contact_service import ContactService

        contact_pk = _seed_contact(session_factory, {}, level="full")
        _seed_frames(
            session_factory,
            [{"days_ago": 1, "domain": None, "summary": "Tue 8 Sep, 41 turns: (escalated); (not found)."}],
            is_test=False,
        )
        episodes = ContactService(session_factory()).get_chatbot_memory(contact_pk, include_episodes=True)["episodes"]
        (row,) = episodes["rows"]
        _assert_readable(row["summary"])
        assert row["turn_count"] == 1  # Turns stays its own column
        assert row["topic"] == "General chat"  # the recall reply's own Topic word

    def test_backfill_rewrites_an_old_summary_from_its_turns_once(self, session_factory) -> None:
        db = session_factory()
        turn_id = str(uuid.uuid4())
        db.add(
            ChatbotTurn(
                id=turn_id,
                contact_respond_id=str(CONTACT_ID),
                is_test=True,
                ingress="console",
                branch_kind="business_query",
                status="done",
                trace=_owner_conversation_2()[0]["trace"],
                envelope={},
                created_at=datetime(2026, 9, 28, 2, 0),
            )
        )
        frame_id = str(uuid.uuid4())
        db.add(
            ConversationFrame(
                id=frame_id,
                contact_id=str(CONTACT_ID),
                contact_respond_id=str(CONTACT_ID),
                space_id="0",
                channel="whatsapp",
                domain="inventory",
                status="closed",
                is_test=True,
                close_reason="topic_switch",
                summary="Mon 28 Sep, 1 turns: inventory srtwc286 (answered); offered warehouse team, no answer.",
                turn_ids=[turn_id],
                last_activity_at=datetime(2026, 9, 28, 2, 0),
            )
        )
        db.commit()

        module = _backfill_module()
        assert module.rerender_summaries(db) >= 1
        db.commit()
        rewritten = session_factory().query(ConversationFrame).filter(ConversationFrame.id == frame_id).one()
        assert rewritten.summary == OWNER_AFTER["conversation_2"][1]
        assert module.rerender_summaries(db) == 0


# --------------------------------------------------------------------------- #
# Memory budget: three worst-case lines still fit L4
# --------------------------------------------------------------------------- #


class TestBudget:
    def test_the_longest_line_is_within_240_chars(self) -> None:
        heads = [episode_digest.episode_line(datetime(2026, 9, 30), d, "") for d in episode_digest._DOMAIN_NOUNS]
        assert max(len(h) for h in heads) + 200 <= 240, max(heads, key=len)

    def test_three_worst_case_lines_fit_the_l4_cap_undropped(self) -> None:
        worst = episode_digest.episode_line(
            datetime(2026, 9, 30), "product_attachment", "Asked " + "x" * 193 + "."
        )
        layers = context_mod.ContextLayers(
            level="episodes",
            profile_facts=None,
            summaries=[worst, worst, worst],
            earlier_messages=[],
            previous_response=None,
            current_subject=None,
            pending_kind=None,
            pending_options=None,
            settings_profile_line=None,
            current_message="hi",
            reply_to=None,
            media_line=None,
        )
        _block, report = context_mod.assemble(layers)
        (l4,) = [entry for entry in report["layers"] if entry["layer"] == "L4"]
        assert l4["est_tokens"] <= context_mod.CAPS["L4"] and not l4["dropped"], l4
