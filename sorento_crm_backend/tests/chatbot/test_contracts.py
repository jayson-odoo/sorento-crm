"""AC-109 (H28): every enum the turn engine speaks is declared ONCE, in contracts.py.

H28 is enum drift: n8n declared `branch_kind` in the router, again in the Switch, again
in `escalate-catalog`, and the three lists stopped agreeing. The port's answer is a single
`Literal` per vocabulary plus this test, which greps the package for a second copy of any
of those string sets. A duplicated set fails and names the file.

The scan is deliberately dumb - it looks for the literal strings, not for a `Literal[...]`
construct - because a copy hand-written as a `set`, a `frozenset`, a tuple or a match
statement is exactly as much drift as a second `Literal`.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.services.chatbot import contracts

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND_ROOT / "app" / "services" / "chatbot"
CONTRACTS_FILE = PACKAGE / "contracts.py"

# The vocabularies AC-109 names, plus the ones the engine itself owns.
VOCABULARIES = {
    "MESSAGE_TYPES": contracts.MESSAGE_TYPES,
    "INTENT_HINTS": contracts.INTENT_HINTS,
    "DOMAIN_HINTS": contracts.DOMAIN_HINTS,
    "SUGGESTED_TEAMS": contracts.SUGGESTED_TEAMS,
    "SUGGESTED_AGENTS": contracts.SUGGESTED_AGENTS,
    "ENTITY_HINTS": contracts.ENTITY_HINTS,
    "SELECTION_CONTEXTS": contracts.SELECTION_CONTEXTS,
    "BRANCH_KINDS": contracts.BRANCH_KINDS,
    "TURN_STAGES": contracts.TURN_STAGES,
    "TURN_STATUSES": contracts.TURN_STATUSES,
    "ACTION_KINDS": contracts.ACTION_KINDS,
    "INGRESS_KINDS": contracts.INGRESS_KINDS,
}


def test_every_vocabulary_is_non_empty_and_unique() -> None:
    for name, values in VOCABULARIES.items():
        assert values, f"{name} is empty"
        assert len(set(values)) == len(values), f"{name} has a duplicate member"


def test_branch_kinds_are_the_thirteen_the_router_decides() -> None:
    assert set(contracts.BRANCH_KINDS) == {
        "access_denied",
        "escalate_offer",
        "out_of_scope",
        "ideate",
        "offer_hold",
        "escalation_declined",
        "check_promotion",
        "low_signal",
        "clarify_menu",
        "not_supported",
        "stock_denied",
        "demand_qty",
        "business_query",
    }


def test_tag_only_branch_kinds_are_a_subset_of_branch_kinds() -> None:
    assert contracts.TAG_ONLY_BRANCH_KINDS <= set(contracts.BRANCH_KINDS)


def _package_sources() -> list[Path]:
    return [p for p in PACKAGE.rglob("*.py") if p != CONTRACTS_FILE]


def test_no_second_copy_of_any_vocabulary_lives_in_the_package() -> None:
    """A module that re-lists a whole vocabulary is a second source of truth (H28)."""
    offenders: list[str] = []
    for path in _package_sources():
        source = path.read_text(encoding="utf-8")
        # Comments quote member names freely and that is fine; only code counts.
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        quoted = set(re.findall(r"['\"]([a-z_]+)['\"]", code))
        for name, values in VOCABULARIES.items():
            if len(values) >= 3 and set(values) <= quoted:
                offenders.append(f"{path.relative_to(BACKEND_ROOT).as_posix()} re-lists {name}")
    assert not offenders, (
        "duplicated enum vocabularies (H28) - import the Literal from contracts.py: "
        + "; ".join(sorted(offenders))
    )


def test_contracts_is_the_only_module_declaring_a_literal_of_these_names() -> None:
    declared = {
        path.relative_to(BACKEND_ROOT).as_posix()
        for path in _package_sources()
        if re.search(r"^\s*[A-Z_]+\s*=\s*Literal\[", path.read_text(encoding="utf-8"), re.M)
    }
    assert not declared, (
        "a Literal vocabulary is declared outside contracts.py: " + ", ".join(sorted(declared))
    )
