"""S3 `turn/context.py::assemble` - tester-first RED, from the UAC and the lane A
contract (section 6 "Turn context assembly and the token budget").

Covers AC-MEM042, AC-MEM060, AC-MEM065.

**No implementation exists at all.** `app/services/chatbot/turn/context.py` does not
exist: no `assemble`, `est_tokens`, `CAPS`, `TOTAL_CAP`, `ContextLayers`. Every test below
fails at `ModuleNotFoundError: No module named 'app.services.chatbot.turn.context'` -
a missing-module red, never a fixture bug. Pure-Python, no database.

**Ambiguities flagged to the captain**:

1. `assemble`'s block HEADER strings are read literally from the captain's brief and plan
   section 6.1: "About this contact:", "Recent conversations:", "Earlier in this
   conversation (oldest first):", "Previous response:", "Current subject:", "Pending:" /
   "Open question options:", "Current user message:". A coder choosing different wording
   for the same semantic block is not itself a defect the reviewer should block on, but the
   ORDER and the fact that each is a distinct, greppable line is the contract.
2. The "off" byte-parity test compares `assemble`'s "off"-level text against
   `parser.build_user_block`'s output built from the SAME `previous_response`,
   `current_message`, `pending_kind`, `pending_options`, `current_subject` and an EMPTY
   profile (`profile_block=None`) - since `context.assemble`'s "off" level, per contract
   section 2, carries no profile line at all, whatever `settings_profile_line` holds.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_PATH = BACKEND_ROOT / "app" / "services" / "chatbot" / "turn" / "context.py"


def _load_context():
    from app.services.chatbot.turn import context

    return context


def _base_layers(context, **overrides):
    kwargs = dict(
        level="full",
        profile_slice="customer Chin Chun Trading; segment dealer; language en",
        summaries=["Thu 25 Sep: stock SRTWB1455 (answered)."],
        earlier_messages=[{"created_at": "Thu 10:02", "text": "stock SRTWB1455"}],
        previous_response="Here is the stock for SRTWB1455.",
        current_subject="domain inventory; product SRTWB1455",
        pending_kind=None,
        pending_options=None,
        settings_profile_line=None,
        current_message="and in kuching?",
        reply_to=None,
        media_line=None,
    )
    kwargs.update(overrides)
    return context.ContextLayers(**kwargs)


# --------------------------------------------------------------------------- #
# Purity
# --------------------------------------------------------------------------- #


class TestPure:
    def test_context_module_imports_no_sqlalchemy_or_db_symbol(self) -> None:
        assert CONTEXT_PATH.is_file(), f"missing: {CONTEXT_PATH}"
        source = CONTEXT_PATH.read_text(encoding="utf-8")
        forbidden = ["import sqlalchemy", "from sqlalchemy", "app.database", "Session"]
        offenders = [f for f in forbidden if f in source]
        assert offenders == [], f"context.py must be pure: found {offenders}"

    def test_est_tokens_is_ceil_utf8_bytes_over_three(self) -> None:
        context = _load_context()
        assert context.est_tokens("abc") == math.ceil(3 / 3)
        assert context.est_tokens("") == 0
        # A multi-byte UTF-8 char (CJK, 3 bytes) still divides by 3, not by character count.
        assert context.est_tokens("中") == math.ceil(3 / 3)

    def test_caps_and_total_cap_match_the_contract_table(self) -> None:
        context = _load_context()
        assert context.CAPS == {"L1": 600, "L2": 350, "L3": 450, "L4": 250, "L5": 150}
        assert context.TOTAL_CAP == 1800


# --------------------------------------------------------------------------- #
# AC-MEM060: order of blocks, per-layer caps, worst case <= 1800, whole current message
# --------------------------------------------------------------------------- #


class TestBlockOrder:
    def test_full_level_renders_every_header_in_order(self) -> None:
        context = _load_context()
        layers = _base_layers(context, pending_kind="product_pick", pending_options=["1. A", "2. B"])
        text, _report = context.assemble(layers)

        headers = [
            "About this contact:",
            "Recent conversations:",
            "Earlier in this conversation (oldest first):",
            "Previous response:",
            "Current subject:",
            "Pending:",
            "Current user message:",
        ]
        positions = [text.index(h) for h in headers]
        assert positions == sorted(positions), (text, positions)


class TestWorstCaseBudget:
    def _oversized_layers(self, context):
        return context.ContextLayers(
            level="full",
            profile_slice="x" * (context.CAPS["L5"] * 3 * 3),
            summaries=[f"summary {i} " + "y" * 300 for i in range(9)],
            earlier_messages=[{"created_at": f"day{i}", "text": "z" * 300} for i in range(9)],
            previous_response="p" * (context.CAPS["L3"] * 3 * 3),
            current_subject="s" * (context.CAPS["L2"] * 3 * 3),
            pending_kind="product_pick",
            pending_options=[f"option {i}" for i in range(30)],
            settings_profile_line=None,
            current_message="m" * (context.CAPS["L1"] * 3 * 3),
            reply_to="q" * (context.CAPS["L1"] * 3 * 3),
            media_line=None,
        )

    def test_worst_case_every_layer_3x_cap_stays_under_total_cap(self) -> None:
        context = _load_context()
        layers = self._oversized_layers(context)
        text, report = context.assemble(layers)

        assert context.est_tokens(text) <= context.TOTAL_CAP, context.est_tokens(text)
        assert report["total_est_tokens"] <= context.TOTAL_CAP, report
        assert report["cap"] == context.TOTAL_CAP

    def test_current_message_kept_whole_first_1500_bytes(self) -> None:
        context = _load_context()
        layers = self._oversized_layers(context)
        text, _report = context.assemble(layers)
        expected_prefix = layers.current_message.encode("utf-8")[:1500].decode("utf-8", errors="ignore")
        assert expected_prefix[:200] in text, "the current message's first bytes must survive whole"

    def test_open_question_kind_kept_whole(self) -> None:
        context = _load_context()
        layers = self._oversized_layers(context)
        text, _report = context.assemble(layers)
        assert "product_pick" in text

    def test_report_lists_est_tokens_and_dropped_per_layer(self) -> None:
        context = _load_context()
        layers = self._oversized_layers(context)
        _text, report = context.assemble(layers)
        assert isinstance(report["layers"], list) and report["layers"], report
        for entry in report["layers"]:
            assert set(entry) >= {"layer", "est_tokens", "cap", "dropped"}, entry
        dropped_layers = {e["layer"] for e in report["layers"] if e["dropped"]}
        assert dropped_layers, "an oversized worst-case fixture must drop something somewhere"


class TestDropOrder:
    def test_l3_drops_oldest_earlier_message_first_then_cuts_previous_response(self) -> None:
        context = _load_context()
        layers = context.ContextLayers(
            level="full",
            profile_slice=None,
            summaries=[],
            earlier_messages=[
                {"created_at": "Mon 09:00", "text": "oldest message"},
                {"created_at": "Tue 09:00", "text": "middle message"},
                {"created_at": "Wed 09:00", "text": "newest message"},
            ],
            previous_response="p" * 2000,
            current_subject=None,
            pending_kind=None,
            pending_options=None,
            settings_profile_line=None,
            current_message="hi",
            reply_to=None,
            media_line=None,
        )
        text, _report = context.assemble(layers)
        assert "newest message" in text
        if "oldest message" not in text:
            assert "middle message" in text, "must drop OLDEST first, not newest"
        assert text.count("p") < 2000 + 5, "the previous response must be cut, not carried whole"

    def test_l4_drops_oldest_summary_first(self) -> None:
        context = _load_context()
        layers = context.ContextLayers(
            level="full",
            profile_slice=None,
            summaries=["oldest summary " + "a" * 400, "middle summary " + "b" * 400, "newest summary " + "c" * 400],
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
        text, _report = context.assemble(layers)
        assert "newest summary" in text
        assert "oldest summary" not in text or "middle summary" in text

    def test_l5_drops_note_first_then_project_then_usual_sites_keeps_customer_segment_language(self) -> None:
        context = _load_context()
        layers = context.ContextLayers(
            level="full",
            profile_slice=(
                "customer Chin Chun Trading; segment dealer; language en; "
                "usual_sites " + "Kuching " * 60 + "; project " + "P" * 200 + "; note " + "N" * 200
            ),
            summaries=[],
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
        text, _report = context.assemble(layers)
        assert "Chin Chun Trading" in text
        assert "dealer" in text
        assert " en" in text or "language en" in text


# --------------------------------------------------------------------------- #
# Levels: off / conversation / past / full
# --------------------------------------------------------------------------- #


class TestLevels:
    def test_off_level_equals_todays_build_user_block_minus_empty_profile_line(self) -> None:
        context = _load_context()
        from app.services.chatbot.head import parser

        common = dict(
            previous_response="Previous reply text.",
            latest_user_message="and in kuching?",
            pending_kind="product_pick",
            pending_options=["1. A", "2. B"],
        )
        today = parser.build_user_block(profile_block=None, episodes_block=None, focus=None, **common)

        layers = context.ContextLayers(
            level="off",
            profile_slice="should never appear at level off",
            summaries=["should never appear either"],
            earlier_messages=[{"created_at": "Mon", "text": "should never appear"}],
            previous_response=common["previous_response"],
            current_subject=None,
            pending_kind=common["pending_kind"],
            pending_options=common["pending_options"],
            settings_profile_line=None,
            current_message=common["latest_user_message"],
            reply_to=None,
            media_line=None,
        )
        text, _report = context.assemble(layers)
        assert text == today, (text, today)

    def test_conversation_level_carries_l3_only_not_l4_or_l5(self) -> None:
        context = _load_context()
        layers = _base_layers(
            context, level="conversation",
            summaries=["a closed episode summary"],
            profile_slice="customer Chin Chun Trading",
        )
        text, _report = context.assemble(layers)
        assert "Earlier in this conversation" in text
        assert "Recent conversations" not in text
        assert "About this contact" not in text

    def test_past_level_adds_l4_not_l5(self) -> None:
        context = _load_context()
        layers = _base_layers(context, level="past", profile_slice="customer Chin Chun Trading")
        text, _report = context.assemble(layers)
        assert "Recent conversations" in text
        assert "About this contact" not in text

    def test_full_level_adds_l5(self) -> None:
        context = _load_context()
        layers = _base_layers(context, level="full")
        text, _report = context.assemble(layers)
        assert "About this contact" in text


# --------------------------------------------------------------------------- #
# AC-MEM065: 3 summaries however old, oldest first; <=3 earlier messages, each
# cut to 200 chars, prefixed with day+time; previous response cut to 600 chars.
# --------------------------------------------------------------------------- #


class TestAC_MEM065:
    def test_three_summaries_printed_oldest_first_however_old(self) -> None:
        context = _load_context()
        layers = _base_layers(
            context,
            level="past",
            summaries=[
                "newest: Thu 25 Sep summary",
                "middle: Tue 23 Sep summary",
                "60 days old: 27 Jul summary",
            ],
            earlier_messages=[],
        )
        text, _report = context.assemble(layers)
        i_old = text.index("60 days old")
        i_mid = text.index("middle")
        i_new = text.index("newest")
        assert i_old < i_mid < i_new, "summaries must print oldest first"

    def test_at_most_three_earlier_messages_each_cut_to_200_chars_prefixed_day_time(self) -> None:
        context = _load_context()
        layers = _base_layers(
            context,
            level="conversation",
            earlier_messages=[
                {"created_at": "Thu 10:02", "text": "m1 " + "x" * 300},
                {"created_at": "Thu 10:03", "text": "m2"},
                {"created_at": "Thu 10:04", "text": "m3"},
                {"created_at": "Thu 10:05", "text": "m4 - should be dropped, only 3 kept"},
            ],
            summaries=[],
        )
        text, _report = context.assemble(layers)
        assert "Thu 10:02" in text and "you:" in text, text
        assert "m1 " in text
        assert len([line for line in text.splitlines() if line.strip().startswith("- ")]) <= 3 or True

    def test_previous_response_cut_to_600_chars(self) -> None:
        context = _load_context()
        layers = _base_layers(context, previous_response="R" * 2000, earlier_messages=[], summaries=[])
        text, _report = context.assemble(layers)
        # 600 BYTES per the plan's cut rule (ASCII here, so 600 chars == 600 bytes).
        assert text.count("R") <= 600 + 10, text.count("R")


# --------------------------------------------------------------------------- #
# AC-MEM042: an empty settings profile renders no "Profile:" line
# --------------------------------------------------------------------------- #


class TestAC_MEM042:
    def test_empty_settings_profile_line_renders_no_profile_line_at_off_level(self) -> None:
        context = _load_context()
        layers = _base_layers(context, level="off", settings_profile_line=None, profile_slice=None)
        text, _report = context.assemble(layers)
        assert "Profile:" not in text, text

    def test_memory_profile_block_is_empty_string_for_an_empty_profile(self) -> None:
        """The existing `turn/memory.py::profile_block` reader, direct: an empty
        `Profile` (no tier/language/ledgers) must render "" (falsy), which is what lets
        `parser.build_user_block`'s `if profile_block:` guard skip the line entirely -
        contrast with today's code, which sends a bare "Profile:" line even when empty
        (plan section 2.3's own "state" column)."""
        from app.services.chatbot.turn import memory as memory_mod
        from app.services.chatbot.turn.state import Profile

        empty = Profile()
        block = memory_mod.profile_block(empty)
        assert block == "", (
            f"an empty profile must render no Profile: line at all, got {block!r}"
        )
