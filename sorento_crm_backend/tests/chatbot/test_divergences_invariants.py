"""Invariants over `divergences.DIVERGENCES`, guarding the post-pass splice.

`_FIXROUND_NEW` is spliced into the built list AHEAD of each node's blanket
(`fixture=None`) entry, and an existing per-fixture entry is patched in place rather than
duplicated (`divergences.py`'s own comment: "`find` returns the first match and uses it
whole, so a second entry for the same fixture would never be reached"). These are the
invariants that comment depends on, checked directly over the BUILT list rather than
trusted by inspection.
"""
from __future__ import annotations

from collections import Counter

from tests.chatbot import divergences


def test_exactly_one_blanket_entry_per_node_that_has_one() -> None:
    blanket_nodes = [d.node for d in divergences.DIVERGENCES if d.fixture is None]
    counts = Counter(blanket_nodes)
    duplicated = {node: n for node, n in counts.items() if n > 1}
    assert not duplicated, (
        f"a node with more than one blanket (fixture=None) entry: {duplicated!r} - "
        "`find` returns the FIRST match, so every entry after the first blanket is dead"
    )


def test_no_per_fixture_entry_sits_after_its_nodes_blanket_entry() -> None:
    blanket_index: dict[str, int] = {}
    for index, d in enumerate(divergences.DIVERGENCES):
        if d.fixture is None:
            blanket_index.setdefault(d.node, index)

    stranded = [
        (index, d.node, d.fixture)
        for index, d in enumerate(divergences.DIVERGENCES)
        if d.fixture is not None
        and d.node in blanket_index
        and index > blanket_index[d.node]
    ]
    assert not stranded, (
        f"per-fixture entries after their node's blanket entry (never reached by `find`, "
        f"which returns the first match): {stranded!r}"
    )


def test_no_node_fixture_pair_is_registered_twice() -> None:
    pairs = [(d.node, d.fixture) for d in divergences.DIVERGENCES]
    counts = Counter(pairs)
    duplicated = {pair: n for pair, n in counts.items() if n > 1}
    assert not duplicated, (
        f"the same (node, fixture) pair registered more than once - the second entry is "
        f"dead, `find` never reaches it: {duplicated!r}"
    )


def test_every_fixround_output_exchange_name_resolves_through_find() -> None:
    unresolved = [
        name
        for name in divergences._FIXROUND_OUTPUT_EXCHANGE
        if divergences.find("output_exchange", name) is None
    ]
    assert not unresolved, (
        f"names in _FIXROUND_OUTPUT_EXCHANGE that `find` cannot resolve to any "
        f"divergence at all: {unresolved!r}"
    )

    # "Exactly one" is find's own contract (Divergence | None, first match wins) - what
    # the splice must not violate is THIS name resolving to a DIFFERENT fixture's own
    # entry standing in for it, which only the per-fixture (or blanket) match on the
    # SAME node proves.
    for name in divergences._FIXROUND_OUTPUT_EXCHANGE:
        resolved = divergences.find("output_exchange", name)
        assert resolved is not None
        assert resolved.node == "output_exchange"
        assert resolved.fixture in (None, name), (
            f"{name!r} resolved to a divergence registered for a different fixture "
            f"({resolved.fixture!r})"
        )
