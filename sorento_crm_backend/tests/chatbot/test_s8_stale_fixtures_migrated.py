"""S8a: S2's `tier_menu` STALE_FIXTURES entries migrate to CAPTURE_BODY_ADDITIONS with
the live body cited, and `STALE_FIXTURES` ends up empty (AC-808).

`tests/chatbot/_corpus.py` currently carries ten `STALE_FIXTURES` entries: four
`build-ctx` captures (RS-2, predate the RS-4 `media` key - unrelated to tier_menu) and
six `compile-current-state` captures (RS-9 Fix 6, predate the tier_menu block - see the
module's own comment at `_corpus.py` around line 285). AC-808 is explicit that
`STALE_FIXTURES` must end up EMPTY, so both groups have to clear, and the plan's own
words for HOW are scoped to the tier_menu group only ("migrated to
CAPTURE_BODY_ADDITIONS with the live body cited") - the four `build-ctx` entries need
their own resolution (a fresh capture, most likely), which this file does not prescribe.

RED-first: every test here fails today because `STALE_FIXTURES` still has ten entries
and `CAPTURE_BODY_ADDITIONS["compile-current-state"]` does not exist at all
(`compile-current-state` is not currently a key in that dict - see `_corpus.py` lines
204-217, which lists `disallowed-entity-gate`, `tier-gate`, `build-ctx-resolved`,
`annotate-incoming-picker`, `annotate-customer-picker`, `resolve-exit-*` and
`sub-resolve-and-gate` only). None of these are import errors - `_corpus` imports fine
today; the failures are assertion mismatches against dicts that still hold the pre-S8a
values.
"""
from __future__ import annotations

import pytest

from tests.chatbot import _corpus

# The six `compile-current-state` captures the module comment names as predating the
# RS-9 Fix 6 tier_menu block - the exact set AC-808 says "migrated ... every former
# tier_menu entry now exists in CAPTURE_BODY_ADDITIONS".
FORMER_TIER_MENU_STALE_FIXTURES = (
    "exec-14087671",
    "exec-14113654",
    "exec-14120751",
    "hand-tier-ask-roster-and-null-quick-reply",
    "rs34-04-accesschoice",
    "rs6-02-accesschoice",
)


def test_stale_fixtures_is_empty() -> None:
    assert _corpus.STALE_FIXTURES == {}, (
        f"STALE_FIXTURES still holds {len(_corpus.STALE_FIXTURES)} entr"
        f"{'y' if len(_corpus.STALE_FIXTURES) == 1 else 'ies'} - AC-808 requires it "
        f"empty: {sorted(_corpus.STALE_FIXTURES)}"
    )


def test_every_former_tier_menu_entry_is_in_capture_body_additions() -> None:
    """Migrated, not just deleted: `compile-current-state` must appear in
    `CAPTURE_BODY_ADDITIONS` carrying `tier_menu`, the same mechanism S1's
    `disallowed-entity-gate` / `tier-gate` already use for their own body additions
    (`_corpus.py` lines 204-217) - so `keys_to_strip` can tell an OLD capture (missing
    the block, gradeable after stripping the key) from a capture that already has it."""
    additions = _corpus.CAPTURE_BODY_ADDITIONS.get("compile-current-state", ())
    assert "tier_menu" in additions, (
        "CAPTURE_BODY_ADDITIONS['compile-current-state'] does not carry 'tier_menu' - "
        f"got {additions!r}"
    )


def test_the_migrated_fixtures_are_no_longer_registered_stale() -> None:
    stale_names = {name for (_node, name) in _corpus.STALE_FIXTURES}
    still_stale = [name for name in FORMER_TIER_MENU_STALE_FIXTURES if name in stale_names]
    assert not still_stale, f"still registered as stale: {still_stale}"


def test_the_replay_suite_actually_grades_the_migrated_captures() -> None:
    """Not just "not excluded" - present in the loaded, gradeable fixture list for
    `compile-current-state` once the full corpus is available (AC-004 skip semantics:
    this test skips, rather than failing, when the sibling n8n checkout is absent)."""
    root = _corpus.corpus_root()
    if root is None:
        pytest.skip(_corpus.corpus_skip_reason())

    fixtures = _corpus.graded(_corpus.full_corpus("compile-current-state"))
    loaded_names = {f.name for f in fixtures}
    missing = [
        name for name in FORMER_TIER_MENU_STALE_FIXTURES if name not in loaded_names
    ]
    assert not missing, (
        f"these former STALE_FIXTURES entries are still not loaded for replay: {missing} "
        "(on disk under one of _corpus.NODE_SLUGS['compile-current-state'], or still "
        "filtered by _load_dir because STALE_FIXTURES was not actually cleared)"
    )
