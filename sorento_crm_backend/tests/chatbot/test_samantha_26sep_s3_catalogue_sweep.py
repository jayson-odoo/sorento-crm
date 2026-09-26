"""Phase 2 RED tests - issue #1262 (Samantha case), group B, slice 3, finding F5.

Turn T10 of the diagnosed conversation. Source:
`documentation/plans/chatbot/PLAN-chatbot-samantha-slices-26sep.md` slice 3 and
`chatbot-samantha-slices-26sep-acceptance-criteria.md` AC-S3-1 to AC-S3-4.

The bug, in order: `gate._CODE_SHAPED` (`lanes/business/gate.py`) requires TWO leading
letters, so a bare Mocha code like "M210-GM" (one letter, then digits) fails it and
`gate._is_a_described_word` reads it as a DESCRIPTION word rather than a typed code.
`resolve_gate._names_a_typed_code` reads off the same rule, so a stock ask naming only
"M210-GM" withholds nothing, `require={"stock": True}` goes out unscoped, and the
resolver sweeps the whole in-stock catalogue (5,857 measured). `answer.build_set_header`
then prints "Showing 0" (0 rows drawn against 5,857 qualifying) - a paging fragment the
owner has banned outright, not merely a wrong number - and `fetch._axis_labelled_subject`
joins every miss-line code with no cap, so the hundreds of codes that "matched" spill
across three WhatsApp messages.

Owner ruling 1 is NOT in scope here (that is F4/S5): this slice is about CODE SHAPE, one
leading letter versus two, never about stripping a quantity prefix - flagged in the plan
itself ("Not a quantity regex").
"""
from __future__ import annotations

import pathlib

from app.services.chatbot.lanes.business.answer import build_set_header
from app.services.chatbot.lanes.business.gate import _is_a_described_word
from app.services.chatbot.lanes.business.resolve_gate import _names_a_typed_code
from app.services.chatbot.lanes.business.fetch import _axis_labelled_subject


# --------------------------------------------------------------------------- #
# AC-S3-1 / F5 step 4: a one-letter Mocha code counts as a typed code.
# --------------------------------------------------------------------------- #


def test_f5_bare_mocha_code_is_not_a_described_word() -> None:
    """`M210-GM` is one leading letter then digits - today `_CODE_SHAPED` demands
    two, so this reads as a DESCRIPTION word (`_is_a_described_word` -> True) exactly
    like "bidet" does, and the stock filter goes out unscoped over the whole catalogue."""
    assert _is_a_described_word("M210-GM") is False, (
        "a one-letter-then-digits code must be read as a typed code, not a "
        "description - _CODE_SHAPED must accept one leading letter"
    )


def test_f5_two_letter_code_is_still_not_a_described_word() -> None:
    """Guard: today's own two-letter case must not regress."""
    assert _is_a_described_word("srtwc286") is False


def test_f5_genuine_descriptive_words_stay_described() -> None:
    """Guard: "tap" and "basin" carry no digit at all, so they must stay described
    words whatever `_CODE_SHAPED`'s leading-letter count becomes."""
    assert _is_a_described_word("tap") is True
    assert _is_a_described_word("basin") is True


def test_t10_single_letter_code_withholds_require() -> None:
    """A stock ask naming only "M210-GM" must withhold the catalogue `require`
    filter - today it does not, and `resolve_entity_body` sends `require={"stock":
    True}` unscoped, which is what sweeps all 5,857 in-stock products."""
    parse_output = {
        "intent_hint": "check_stock",
        "domain_hint": "inventory",
        "entities": [
            {
                "hint": "product",
                "raw": "M210-GM",
                "canonical_code": "M210-GM",
                "current_message": True,
            }
        ],
    }
    assert _names_a_typed_code(parse_output) is True, (
        "M210-GM must be read as a typed code so the caller withholds the "
        "unscoped 'has stock' filter"
    )


# --------------------------------------------------------------------------- #
# AC-S3-2: build_set_header never appends "Showing N" (owner's paging ban).
# --------------------------------------------------------------------------- #


def test_set_header_has_no_paging_text() -> None:
    big = build_set_header(5857, 0, "products", {"stock": True})
    small = build_set_header(10, 5, "products", {"stock": True})

    assert "Showing" not in big, f"build_set_header must never append paging text: {big!r}"
    assert "Showing" not in small, f"build_set_header must never append paging text: {small!r}"


def test_set_header_still_names_the_count_and_predicate() -> None:
    """Guard: the ban is on the PAGING half only - the header itself still says
    what the set is and how many qualify."""
    header = build_set_header(3, 3, "products", {"stock": True})
    assert "3" in header
    assert "products" in header


# --------------------------------------------------------------------------- #
# AC-S3-3: the silent-company miss line caps its subject at 5 codes.
# --------------------------------------------------------------------------- #


def _product_entities(n: int) -> list[dict]:
    return [
        {"uuid": f"u{i}", "entity_type": "product", "code": f"CODE{i}"} for i in range(n)
    ]


def test_silent_company_line_caps_subject_above_five() -> None:
    subject = _axis_labelled_subject(_product_entities(300))

    assert "CODE250" not in subject, (
        f"above 5 codes the subject must not list every one of them: {subject[:200]}..."
    )
    assert "300" in subject and "searched" in subject, (
        f"above 5 codes the subject must say 'the N products searched' (N=300): {subject!r}"
    )


def test_silent_company_line_lists_every_code_at_or_under_five() -> None:
    subject = _axis_labelled_subject(_product_entities(3))

    for i in range(3):
        assert f"CODE{i}" in subject, f"CODE{i} missing from a 3-code subject: {subject!r}"
    assert "searched" not in subject, (
        f"a subject at or under the cap must print the codes, not the 'searched' summary: "
        f"{subject!r}"
    )


# --------------------------------------------------------------------------- #
# AC-S3-4: the owner's paging ban is written down.
# --------------------------------------------------------------------------- #


def test_paging_ban_is_written_down() -> None:
    """The ban ("no 'Showing N' text in a chatbot reply, ever") must be written in a
    `documentation/reference/*.md` file, not only enforced in code where the next
    editor cannot see the rule. No such file exists yet (grepped: zero "Showing"
    hits anywhere under documentation/reference today)."""
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    ref_dir = repo_root / "documentation" / "reference"
    combined = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in ref_dir.glob("*.md")
    )

    assert "Showing" in combined, (
        "documentation/reference must carry the owner's paging ban (a sentence "
        "naming 'Showing N' as banned chatbot reply text); none of its .md files "
        "mention 'Showing' at all"
    )
