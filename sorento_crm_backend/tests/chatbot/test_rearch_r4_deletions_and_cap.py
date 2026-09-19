"""R4 RED tests - deletions (AC-1680 subset) and the did-you-mean cap (rest of AC-1710).

PLAN-chatbot-answer-half-reattach.md's deletion table + Deleted table; UAC AC-1680, AC-1692,
AC-1710.

**The split this tester pinned for AC-1680** (captain's brief item 5: "measure which
strings the multi-domain path needs, and scope the scan so it does not contradict the
[owner] ruling"):

- ALWAYS forbidden, no exceptions, scanned across every `.py` file in `turn/` plus
  `turn_runtime.py`: "Which product do you mean?", "Which customer do you mean?", "Which
  price tier applies to you?", "Did you mean", "search needs to be more specific". MEASURED:
  all five are live string literals in `turn/compose.py` TODAY - `_ASK_HEADERS`'s
  product_pick/customer_pick/tier_pick entries, `_REQUIRE_SPECIFIC_HEADER_DOMAINS`'s own
  clarification header built in `compose_question`, and the "Did you mean:" header in the
  same function. These are ALL single-domain roster/picker text; even the multi-domain
  fan-out never raises a product/customer/tier picker (its own `_lane_question` /
  `_team_pick_question` are generic), so no exception is needed for them anywhere.
- SCOPED to `turn/compose.py`'s own `compose()` function (owner ruling, Hazards section: a
  multi-domain miss keeps today's copy because production has no composer for a fan-out):
  "Would you like me to escalate to", "No matching results found". MEASURED: "No matching
  results found" is not a live string literal anywhere in `turn/` or `turn_runtime.py`
  today (only in comments/docstrings quoting it) - that half of the scan is a genuine GREEN
  CONTROL, not a contradiction. "Would you like me to escalate to" IS a live literal, but
  only inside `compose()` (`compose.py:355`, the multi-domain missed-team offer) - never
  inside `compose_question` (the single-domain picker composer, which moves to the bridge).
  `TestAC1680MultiDomainScopedException.test_escalate_to_team_phrase_is_scoped_to_compose_
  not_compose_question` pins that boundary and is ALSO a green control today (documented,
  not invented for this file).

**AC-1710's did-you-mean cap, the cut point this tester measured**: `miss_suggest._dym_plan`'s
own closure `cap_for_block` (`miss_suggest.py:429-430`) is what trims the PRINTED
did-you-mean candidate list per unresolved token, via the module-level `_cap3` helper (a
hard `value[:3]`) - bypassed only for `product_attachment` on the uuid-keyed d1/picker
lanes (F2 owner ruling, kept as is). This is a DIFFERENT cap from
`DOMAIN_PROBE[domain]["probe_cap"]` (which limits how many candidates get PROBED for the
has/no annotation, not how many are PRINTED) - the two must not be conflated. Not
captain-pinned (unlike gate.py's `roster_caps` in R3's own `test_rearch_r3_roster_cap.py`)
- this tester's own guessed name is `dym_transform(..., roster_caps: Mapping[str, int] |
None = None)`, keyed by entity kind ("product"), signature-guarded so a coder naming it
differently only updates this file's call sites.
"""
from __future__ import annotations

import ast
import inspect
import pathlib
from typing import Any

import pytest

from app.services.chatbot import turn_runtime
from app.services.chatbot.lanes.business import miss_suggest as miss_mod

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]
TURN_DIR = BACKEND_ROOT / "app" / "services" / "chatbot" / "turn"
TURN_RUNTIME_PY = BACKEND_ROOT / "app" / "services" / "chatbot" / "turn_runtime.py"

ALWAYS_FORBIDDEN: tuple[str, ...] = (
    "Which product do you mean?",
    "Which customer do you mean?",
    "Which price tier applies to you?",
    "Did you mean",
    "search needs to be more specific",
)

MULTI_DOMAIN_SCOPED: tuple[str, ...] = (
    "Would you like me to escalate to",
    "No matching results found",
)


def _all_turn_files() -> list[pathlib.Path]:
    assert TURN_DIR.is_dir(), f"app/services/chatbot/turn/ does not exist: {TURN_DIR}"
    files = sorted(TURN_DIR.glob("*.py"))
    assert files, f"no .py files found under {TURN_DIR}"
    files.append(TURN_RUNTIME_PY)
    return files


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """`id()` of every module/function/class DOCSTRING constant node - the first
    statement of that body, when it is a bare string expression. Excluded from the scan
    below, or a docstring narrating one of these phrases (as this file's own module
    docstring does, and as `turn_runtime._tier_gate`'s docstring already does today) is
    mistaken for a live rendering-time duplicate."""
    ids: set[int] = set()
    candidates: list[ast.AST] = [tree] + [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    for node in candidates:
        body = getattr(node, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            ids.add(id(body[0].value))
    return ids


def _string_literal_lines(path: pathlib.Path, needle: str) -> list[int]:
    """Line numbers where `needle` sits inside a Python STRING LITERAL that is NOT a
    docstring - a live rendering-time string, never prose about one."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    doc_ids = _docstring_constant_ids(tree)
    hits: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str) and needle in node.value):
            continue
        if id(node) in doc_ids:
            continue
        hits.append(node.lineno)
    return hits


# --------------------------------------------------------------------------- #
# AC-1680 - no production copy string exists twice
# --------------------------------------------------------------------------- #


class TestAC1680AlwaysForbidden:
    @pytest.mark.parametrize("needle", ALWAYS_FORBIDDEN, ids=[n[:28] for n in ALWAYS_FORBIDDEN])
    def test_string_absent_from_every_turn_file(self, needle: str) -> None:
        hits: dict[str, list[int]] = {}
        for path in _all_turn_files():
            lines = _string_literal_lines(path, needle)
            if lines:
                hits[path.name] = lines
        assert hits == {}, (
            f"{needle!r} still exists as a live string literal under turn/ or "
            f"turn_runtime.py (must move to the bridge / production composers): {hits}"
        )


class TestAC1680MultiDomainScopedException:
    """The two strings a multi-domain miss legitimately keeps (owner ruling) - scoped to
    `turn/compose.py`, never anywhere else."""

    @pytest.mark.parametrize("needle", MULTI_DOMAIN_SCOPED)
    def test_absent_outside_compose_py(self, needle: str) -> None:
        hits: dict[str, list[int]] = {}
        for path in _all_turn_files():
            if path.name == "compose.py":
                continue
            lines = _string_literal_lines(path, needle)
            if lines:
                hits[path.name] = lines
        assert hits == {}, f"{needle!r} leaked outside turn/compose.py: {hits}"

    def test_escalate_to_team_phrase_is_scoped_to_compose_not_compose_question(self) -> None:
        """GREEN CONTROL today: the phrase already lives only in `compose()` (the
        multi-domain fan-out), never in `compose_question` (the single-domain picker
        composer R4 empties out). Kept as a standing guard against regression."""
        path = TURN_DIR / "compose.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert "compose_question" in functions, "compose.py has no compose_question function"
        segment = ast.get_source_segment(source, functions["compose_question"]) or ""
        assert "Would you like me to escalate to" not in segment, (
            "compose_question (the single-domain picker composer) must not carry the "
            "multi-domain-only escalate phrase"
        )


# --------------------------------------------------------------------------- #
# Deleted table - turn_runtime's did-you-mean stand-ins retire once miss_suggest is live
# --------------------------------------------------------------------------- #


class TestAlternativesAskFunctionsRetired:
    @pytest.mark.parametrize(
        "name", ["_alternatives_ask", "_alternatives_ask_text", "_resolve_dominant_neighbours"]
    )
    def test_function_no_longer_exists(self, name: str) -> None:
        assert not hasattr(turn_runtime, name), (
            f"turn_runtime.{name} must be deleted once the did-you-mean roster is "
            "produced by miss_suggest.dym_transform / dym_annotate (R4's own Deleted table)"
        )


# --------------------------------------------------------------------------- #
# AC-1710 - the did-you-mean list cap
# --------------------------------------------------------------------------- #


def _dym_parser(domain: str = "incoming") -> dict[str, Any]:
    return {
        "domain_hint": domain,
        "message_type": "business_query",
        "entities": [{"raw": "zzt", "hint": "product", "current_message": True}],
    }


def _dym_resolved_many(n: int) -> dict[str, Any]:
    return {
        "resolutions": [
            {
                "token": "zzt",
                "matches": [],
                "alternatives": [
                    {
                        "canonical_code": f"ZZTPROD{i:03d}",
                        "entity_type": "product",
                        "uuid": f"prod-{i:03d}",
                        "match_tier": "fuzzy",
                    }
                    for i in range(n)
                ],
            }
        ],
        "unresolved_tokens": ["zzt"],
        "tokens": ["zzt"],
    }


class TestDidYouMeanCapIsConfigurable:
    @pytest.mark.parametrize("cap", [3, 10])
    def test_printed_candidate_count_honours_roster_caps(self, cap: int) -> None:
        sig = inspect.signature(miss_mod.dym_transform)
        if "roster_caps" not in sig.parameters:
            pytest.fail(
                "miss_suggest.dym_transform has no roster_caps parameter yet (this "
                "tester's own guessed name, Mapping[str, int] | None) - the did-you-mean "
                "print cut point is _dym_plan's own cap_for_block/_cap3, today a "
                "hard-coded value[:3]"
            )
        resolved = _dym_resolved_many(12)
        parser = _dym_parser()
        gate = {"gate_debug": {"domain": "incoming"}}
        plan = miss_mod.dym_transform(
            {}, parser=parser, resolved=resolved, gate=gate, roster_caps={"product": cap}
        )
        candidates = plan.get("dym_candidate_codes") or []
        assert len(candidates) <= cap, (
            f"did-you-mean printed candidates: {len(candidates)}, cap was {cap}: {candidates}"
        )

    def test_a_missing_or_none_roster_caps_keeps_a_default(self) -> None:
        """Fail-open, same convention as R3's gate.py roster_caps: an absent kind or a
        None roster_caps must not crash and must still cut the list somewhere sane (not
        unboundedly print every trigram neighbour)."""
        sig = inspect.signature(miss_mod.dym_transform)
        if "roster_caps" not in sig.parameters:
            pytest.fail("miss_suggest.dym_transform has no roster_caps parameter yet")
        resolved = _dym_resolved_many(12)
        parser = _dym_parser()
        gate = {"gate_debug": {"domain": "incoming"}}
        plan = miss_mod.dym_transform(
            {}, parser=parser, resolved=resolved, gate=gate, roster_caps=None
        )
        candidates = plan.get("dym_candidate_codes") or []
        assert len(candidates) <= 10, (
            f"a None roster_caps must still cap the printed list (default 10): {candidates}"
        )

    def test_cap_for_block_no_longer_returns_a_bare_cap3(self) -> None:
        path = pathlib.Path(inspect.getfile(miss_mod))
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        node = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "cap_for_block"),
            None,
        )
        assert node is not None, (
            "cap_for_block (the did-you-mean print-cap closure inside _dym_plan) was not "
            "found by name - re-check it has not been renamed without updating this test"
        )
        segment = ast.get_source_segment(source, node) or ""
        assert "_cap3(cands)" not in segment, (
            f"cap_for_block must honour roster_caps rather than the hard-coded "
            f"_cap3(cands): {segment}"
        )
