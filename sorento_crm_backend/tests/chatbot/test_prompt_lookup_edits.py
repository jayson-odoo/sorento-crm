"""CHAT-SLIM-INDEX S5 red tests: `app/services/chatbot/prompt_lookup_edits.py` (pure).

Contract: PLAN-chat-lookup-lists-25oct.md "S5 contract". `EDITS: tuple[Edit, ...]`, `Edit(op, anchor, payload)`
with op "replace" | "delete"; `apply(text) -> str | None` (None when any anchor is missing or found more than once);
the marker line `== LOOKUP LISTS ==` is appended at the end. The tests are generic over EDITS: the fixture holds
every Edit's own anchor once, so they hold whichever anchors the coder picks.
Pinned: `apply(apply(fixture))` is None (the anchors are gone, so a second pass finds none; the migration's
idempotence is a separate test). No database.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services import chatbot_lookup_edits as ple

ALL_EDITS = tuple(ple.EDITS)
#: `replace_line` edits carry the sha256 of a line that must not be quoted in the repo, so no fixture can hold their
#: anchor; the generic tests below run over the text-anchored edits only.
TEXT_EDITS = tuple(e for e in ALL_EDITS if e.op != "replace_line")


@pytest.fixture(autouse=True)
def _text_edits_only(monkeypatch):
    monkeypatch.setattr(ple, "EDITS", TEXT_EDITS)


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
        assert e.op in ("replace", "delete"), e  # text edits; replace_line is checked in its own test
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


# ------------------------------------------------------------------ replace_line (hashed lines)


def _sha(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def test_every_replace_line_edit_is_a_sha256_anchor_and_a_one_line_payload():
    for e in ALL_EDITS:
        if e.op == "replace_line":
            assert len(e.anchor) == 64 and set(e.anchor) <= set("0123456789abcdef"), e.anchor
            assert "\n" not in e.payload


def test_replace_line_replaces_the_one_line_with_that_hash(monkeypatch):
    secret = "ZZ fake sentence that is only quoted by its hash"
    monkeypatch.setattr(ple, "EDITS", (ple.Edit("replace_line", _sha(secret), "renamed line"),))
    out = ple.apply(f"line a\n{secret}\nline c\n")
    assert out is not None and "renamed line" in out and secret not in out
    assert "line a" in out and "line c" in out
    assert out.rstrip("\n").splitlines()[-1] == MARKER


def test_replace_line_with_an_empty_payload_removes_the_line(monkeypatch):
    secret = "ZZ fake sentence to drop"
    monkeypatch.setattr(ple, "EDITS", (ple.Edit("replace_line", _sha(secret), ""),))
    out = ple.apply(f"line a\n{secret}\nline c\n")
    assert out is not None and secret not in out and "line a" in out and "line c" in out


def test_replace_line_needs_the_hash_exactly_once_and_the_whole_line(monkeypatch):
    secret = "ZZ fake sentence twice"
    monkeypatch.setattr(ple, "EDITS", (ple.Edit("replace_line", _sha(secret), "x"),))
    assert ple.apply(f"a\n{secret}\n{secret}\nb\n") is None, "doubled line"
    assert ple.apply("a\nnothing like it\nb\n") is None, "missing line"
    assert ple.apply(f"a\nprefix {secret}\nb\n") is None, "a longer line is not the line"


# ------------------------------------------------------------------ crew audit: no real names, no company or location lists


def test_the_edits_module_source_holds_no_real_customer_name_words():
    source = (Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot_lookup_edits.py").read_text(encoding="utf-8").casefold()
    for word in ("sdn bhd", "enterprise", "trading", "hardware"):
        assert word not in source, word


def _anchored(prefix: str):
    return [e for e in ALL_EDITS if e.op != "replace_line" and prefix in e.anchor]


def test_the_company_codes_line_is_removed():
    assert [e for e in ALL_EDITS if e.anchor.startswith("Company codes:")], "no edit removes the Company codes line"
    assert not [ln for ln in ple.apply(fixture()).splitlines() if ln.startswith("Company codes:")]


def test_the_sales_company_section_keeps_no_company_list():
    edits = _anchored("== SALES_COMPANY")
    assert edits, "no edit covers the SALES_COMPANY list"
    out_lines = set(ple.apply(fixture()).splitlines())
    for e in edits:
        for ln in e.anchor.splitlines():
            if ln.strip() and not ln.startswith("=="):
                assert ln not in out_lines, ln[:60]


def test_no_empty_known_brands_banner_is_left():
    assert [e for e in ALL_EDITS if any(ln.strip() == "KNOWN BRANDS" for ln in e.anchor.splitlines())], "no edit covers the banner"
    assert not [ln for ln in ple.apply(fixture()).splitlines() if ln.strip() == "KNOWN BRANDS"]


def test_the_warehouse_code_list_under_the_short_token_rule_is_removed():
    edits = _anchored("A SHORT TOKEN IS A LOCATION")
    assert edits, "no edit removes the warehouse code list under the short-token rule"
    out = ple.apply(fixture())
    for e in edits:
        assert e.anchor not in out or e.payload.startswith(e.anchor)
