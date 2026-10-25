"""CHAT-SLIM-INDEX S5 red tests: `app/services/chatbot/prompt_lookup_edits.py` (pure).

Contract: PLAN-chat-lookup-lists-25oct.md "S5 contract". `EDITS: tuple[Edit, ...]`, `Edit(op, anchor, payload)`
with op "replace" | "delete"; `apply(text) -> str | None` (None when any anchor is missing or found more than once);
the marker line `== LOOKUP LISTS ==` is appended at the end. The tests are generic over EDITS: the fixture holds
every Edit's own anchor once, so they hold whichever anchors the coder picks.
Pinned: `apply(apply(fixture))` is None (the anchors are gone, so a second pass finds none; the migration's
idempotence is a separate test). No database.
"""
from __future__ import annotations

from app.services.chatbot import prompt_lookup_edits as ple

MARKER = "== LOOKUP LISTS =="
SALES_REPORT_ANCHOR = '== SALES REPORT: order_status "sales_report", domain_hint "order" =='
#: The SALES-TARGET-CHAT insert (fc2943a9b7 prompt_inserts.py), shortened to the same shape: a header line,
#: prose with quoted words, a bullet list, a closing line, a blank line, then the SALES REPORT header follows.
SALES_TARGET_SECTION = """== SALES TARGET: order_status "sales_target", domain_hint "order" ==
A question about a SALES TARGET is order_status "sales_target", domain_hint "order", intent_hint "check_order".
The target words decide it, in any language: "target", "achievement", "sasaran", "目标", "达标".
  - "how is my target this quarter" -> order_status "sales_target", self_reference
    true, entities []
  - "did we hit the Q3 target?" -> order_status "sales_target", self_reference true
A SALES TARGET ask leaves sales_channel and group_by null and requested_attributes [].

"""


def fixture(edits=None, *, skip: int | None = None, double: int | None = None) -> str:
    edits = list(ple.EDITS if edits is None else edits)
    parts = ["Rules for {{current_date}}."]
    for i, e in enumerate(edits):
        if i != skip:
            parts.append(e.anchor)
        if i == double:
            parts.append(e.anchor)
    head = "\n\n".join(parts) + "\n\n"
    return head + SALES_TARGET_SECTION + SALES_REPORT_ANCHOR + '\nThe sales report rules follow here.\n'


def test_edits_are_well_formed():
    assert len(ple.EDITS) >= 1
    for e in ple.EDITS:
        assert e.op in ("replace", "delete"), e
        assert e.anchor.strip() and isinstance(e.payload, str)
        assert fixture().count(e.anchor) == 1, f"anchor appears more than once in the fixture: {e.anchor[:60]!r}"
        if e.op == "delete":
            assert e.payload == "", e
        else:
            # No instruction section (placement rule 2): a replacement is one line or empty.
            assert "\n" not in e.payload, e.payload[:80]


def test_apply_removes_every_anchor_and_appends_the_marker_once_at_the_end():
    out = ple.apply(fixture())
    assert out is not None
    for e in ple.EDITS:
        assert e.anchor not in out or e.payload.startswith(e.anchor), e.anchor[:60]
    lines = out.rstrip("\n").splitlines()
    assert lines[-1] == MARKER, lines[-3:]
    assert sum(1 for ln in out.splitlines() if ln.strip() == MARKER) == 1
    assert out.count(MARKER) == 1


def test_the_sales_target_section_and_the_sales_report_header_survive_byte_for_byte():
    out = ple.apply(fixture())
    assert SALES_TARGET_SECTION + SALES_REPORT_ANCHOR in out
    assert out.count(SALES_REPORT_ANCHOR) == 1


def test_replace_payloads_land_in_the_text():
    out = ple.apply(fixture())
    for e in ple.EDITS:
        if e.op == "replace" and e.payload:
            assert e.payload in out, e.payload[:60]


def test_a_missing_anchor_gives_none():
    for i in range(len(ple.EDITS)):
        assert ple.apply(fixture(skip=i)) is None, ple.EDITS[i].anchor[:60]


def test_a_doubled_anchor_gives_none():
    for i in range(len(ple.EDITS)):
        assert ple.apply(fixture(double=i)) is None, ple.EDITS[i].anchor[:60]


def test_a_second_pass_finds_nothing():
    once = ple.apply(fixture())
    assert once is not None and ple.apply(once) is None


# ------------------------------------------------------------------ coverage (content, list free)


def _removing(substr: str):
    return [e for e in ple.EDITS if substr in e.anchor and substr not in e.payload]


def test_every_specification_line_is_removed():
    assert any(ln.startswith("Specification ") for e in ple.EDITS for ln in e.anchor.splitlines()), "no edit removes a Specification line"
    out = ple.apply(fixture())
    assert not [ln for ln in out.splitlines() if ln.startswith("Specification ")]


def test_the_product_types_line_is_removed():
    needle = "Product types (the category entity keeps these"
    assert _removing(needle), "no edit removes the Product types line"
    assert needle not in ple.apply(fixture())


def test_the_translation_and_file_word_lists_are_removed():
    out = ple.apply(fixture())
    for word in ("tandas", "马桶", "kepala paip", "sinki dapur", "gambar", "foto"):
        assert _removing(word), f"no edit removes {word!r}"
        assert word not in out, word


def test_rule_text_naming_a_removed_per_turn_line_is_renamed_to_its_block():
    renamed = [e for e in ple.EDITS if "Known brands:" in e.anchor]
    assert renamed, "no edit renames the Known brands: reference"
    assert any("Brand candidates" in e.payload for e in renamed)
    out = ple.apply(fixture())
    assert "Known brands:" not in out and "Brand candidates" in out


def test_the_text_says_spec_key_and_value_come_from_the_spec_candidates_bracket():
    """The removed Specification lines were the vocabulary of spec_key / spec_value (head/parser.py:222-227)."""
    assert any("Spec candidates" in e.payload and "spec_key" in e.payload for e in ple.EDITS), \
        "no replacement tells the parser where spec_key / spec_value come from"
    out = ple.apply(fixture())
    assert "Spec candidates" in out and "spec_key" in out
