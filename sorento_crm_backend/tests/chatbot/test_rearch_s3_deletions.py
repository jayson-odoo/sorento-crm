"""S3 half of AC-1594 (PLAN-chatbot-turn-rearch.md "Slices": S3's deletions -
`head/output_exchange.py`, `tail/compile_state.py`, `dialogue/`). The FULL AC-1594 list
(`DOMAIN_SPEC`, `SUGGESTED_TEAMS`, `_BASE_PROPERTY_WORDS`, the three `TIER_ORDER`
copies, `ENTITY_FILTER_REQUIRED_TOOLS`, `PRODUCT_ID_REQUIRED_TOOLS`,
`BARE_ENTITY_TYPE_BY_DOMAIN`) is S6's own ticket per the plan's own "Slices" table
(`S6 | ... deletions guard ... | AC-1590 to 1594`) and per the PLAN's own guardrail
note under "The policy": "until the constants are deleted (S6), a test asserts table
== constant" - `test_rearch_s0_domains_seed.py` (already committed) DEPENDS on
`DOMAIN_SPEC` still existing, so asserting its deletion here would contradict a
red/green test already landed on this branch. This file is scoped to the S3-only
subset the captain's brief names.

`tail/pending.py` "remnants" (also named in AC-1532's own evidence line) are checked
too, since `turn/pending.py` (S2, already committed) is its replacement.

RIGHT NOW every test is RED: `head/output_exchange.py` and `tail/compile_state.py`
both exist and are imported from several places (measured below); `engine.py` does
not import `app.services.chatbot.turn.apply` yet (measured: `grep -n "turn.apply"
app/services/chatbot/engine.py` finds nothing).
"""
from __future__ import annotations

import pathlib

import pytest

CHATBOT_PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "chatbot"

RETIRED_PATHS = [
    CHATBOT_PACKAGE / "head" / "output_exchange.py",
    CHATBOT_PACKAGE / "tail" / "compile_state.py",
    CHATBOT_PACKAGE / "dialogue",
]

RETIRED_IMPORT_NAMES = [
    "head.output_exchange",
    "tail.compile_state",
    "chatbot.dialogue",
    "chatbot import dialogue",
]


@pytest.mark.parametrize("path", RETIRED_PATHS, ids=lambda p: p.name)
def test_retired_path_does_not_exist(path: pathlib.Path) -> None:
    assert not path.exists(), f"must be deleted by S3: {path}"


def test_tail_pending_remnants_gone() -> None:
    path = CHATBOT_PACKAGE / "tail" / "pending.py"
    assert not path.exists(), (
        f"tail/pending.py remnants must be gone - turn/pending.py (S2) is its "
        f"replacement: {path}"
    )


def test_engine_imports_turn_apply() -> None:
    engine_source = (CHATBOT_PACKAGE / "engine.py").read_text(encoding="utf-8")
    assert "turn.apply" in engine_source or "turn import apply" in engine_source, (
        "engine.py must import app.services.chatbot.turn.apply (PLAN 'Slices': "
        "'Engine rewired A to G') - not found in its source today"
    )


@pytest.mark.parametrize("name", RETIRED_IMPORT_NAMES)
def test_no_module_imports_a_retired_path(name: str) -> None:
    hits = [
        f
        for f in CHATBOT_PACKAGE.rglob("*.py")
        if name in f.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not hits, f"{name!r} still imported/referenced in: {hits}"
