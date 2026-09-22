"""The verdict, one pure function (S0).

UAC `documentation/plans/chatbot/chatbot-dealer-stock-verdict-acceptance-criteria.md`
AC-1720 to AC-1723. PLAN `documentation/plans/chatbot/PLAN-chatbot-dealer-stock-verdict.md`
("The verdict, one pure function (S0)"). Ruling D6 (the rule) and D7 (the configurable
threshold) in the UAC's D-table.

`verdict()` has no I/O and no dates - it is the one decision seam every arm of the reply
passes through, so it is tested as a pure table: `(available, ask, incoming, purchase,
threshold_pct)` in, `(answer, running_low, sources, limited)` out.

D6 in full: deficit D = ask - available, T = threshold_pct / 100.
* ask <= available -> "available"; running_low when ask >= T * available.
* Else ("not_available"), incoming is consulted FIRST:
  - incoming >= D -> sources ("incoming",), PO ignored; limited when D >= T * incoming.
  - 0 < incoming < D and incoming + purchase >= D -> sources ("incoming", "purchase");
    limited when D >= T * (incoming + purchase).
  - no incoming (== 0) and purchase >= D -> sources ("purchase",); limited when
    D >= T * purchase.
  - otherwise -> sources (), limited False (no disclaimer).

`ROWS` below is the owner's OWN 18-row matrix, verbatim (the coordinator's correction, 22 Sep
2026) - not a tester-derived table. `available=100`, `threshold_pct=50` for every row; only
ask/incoming/purchase vary. Two rows beyond the 18 are kept as separate, explicitly-labelled
tests (`test_verdict_both_sources_...`) below because they exercise a branch combination the
owner's 18 rows do not hit on their own (a "both" disclaimer that is NOT limited, and the
"otherwise" no-disclaimer outcome with both incoming and purchase present but jointly short) -
per the coordinator's instruction, kept OUT of the AC-1720 parametrization.

This module does not exist yet: `from app.services.stock_verdict import verdict, Verdict`
is expected to raise `ModuleNotFoundError` until S0 lands - that IS the red state.
"""
from __future__ import annotations

import pytest

from app.services.stock_verdict import Verdict, verdict

AVAILABLE = 100
THRESHOLD = 50

# Owner's 18 rows verbatim: (row, ask, incoming, purchase, expected
# (answer, running_low, sources, limited)).
ROWS = [
    (1, 10, 0, 0, ("available", False, (), False)),
    (2, 50, 0, 0, ("available", True, (), False)),
    (3, 60, 0, 0, ("available", True, (), False)),
    (4, 100, 0, 0, ("available", True, (), False)),
    (5, 110, 0, 0, ("not_available", False, (), False)),
    (6, 110, 5, 0, ("not_available", False, (), False)),
    (7, 110, 10, 0, ("not_available", False, ("incoming",), True)),
    (8, 110, 20, 0, ("not_available", False, ("incoming",), True)),
    (9, 110, 25, 0, ("not_available", False, ("incoming",), False)),
    (10, 110, 0, 5, ("not_available", False, (), False)),
    (11, 110, 0, 10, ("not_available", False, ("purchase",), True)),
    (12, 110, 0, 20, ("not_available", False, ("purchase",), True)),
    (13, 110, 0, 25, ("not_available", False, ("purchase",), False)),
    (14, 110, 5, 5, ("not_available", False, ("incoming", "purchase"), True)),
    (15, 110, 5, 10, ("not_available", False, ("incoming", "purchase"), True)),
    (16, 110, 10, 10, ("not_available", False, ("incoming",), True)),
    (17, 110, 20, 20, ("not_available", False, ("incoming",), True)),
    (18, 110, 25, 25, ("not_available", False, ("incoming",), False)),
]

assert len(ROWS) == 18, "the owner's matrix is 18 rows"


@pytest.mark.parametrize(
    "row, ask, incoming, purchase, expected", ROWS, ids=[str(r[0]) for r in ROWS]
)
def test_verdict_matches_owner_matrix(row, ask, incoming, purchase, expected):
    """AC-1720."""
    result = verdict(
        available=AVAILABLE,
        ask=ask,
        incoming=incoming,
        purchase=purchase,
        threshold_pct=THRESHOLD,
    )

    assert isinstance(result, Verdict)
    assert (result.answer, result.running_low, result.sources, result.limited) == expected, row


def test_verdict_both_sources_present_below_threshold_not_limited():
    """Extra edge row, kept OUT of the owner's 18: ask 110, incoming 5, purchase 100 - the
    owner's 18 rows only exercise the "both" disclaimer as `limited=True` (rows 14, 15); this
    fills the "both, but NOT limited" combination (D=10 against incoming+purchase=105, well
    over T * 105 = 52.5)."""
    result = verdict(available=AVAILABLE, ask=110, incoming=5, purchase=100, threshold_pct=THRESHOLD)

    assert result.answer == "not_available"
    assert result.sources == ("incoming", "purchase")
    assert result.limited is False


def test_verdict_both_sources_present_but_jointly_short_no_disclaimer():
    """Extra edge row, kept OUT of the owner's 18: ask 110, incoming 5, purchase 3 - incoming
    alone is short (5 < D=10) and incoming + purchase (8) still falls short of D, so NEITHER
    the incoming-only nor the both-sources branch fires and there is no disclaimer at all, even
    though both incoming and purchase are nonzero (distinct from row 6's incoming-only-short
    case, where purchase is zero)."""
    result = verdict(available=AVAILABLE, ask=110, incoming=5, purchase=3, threshold_pct=THRESHOLD)

    assert result.answer == "not_available"
    assert result.sources == ()
    assert result.limited is False


def test_verdict_zero_available_incoming_only():
    """AC-1721, first half: available 0, ask 10, incoming 30 - incoming alone covers the
    whole ask (D=10, incoming=30 >= D), PO is not consulted, and the surplus keeps it
    unlimited (D=10 < T * incoming = 15)."""
    result = verdict(available=0, ask=10, incoming=30, purchase=0, threshold_pct=THRESHOLD)

    assert result.answer == "not_available"
    assert result.sources == ("incoming",)
    assert result.limited is False


def test_verdict_zero_available_both_limited():
    """AC-1721, second half: available 0, ask 10, incoming 5 (< D=10) and purchase 5, so
    incoming + purchase == 10 >= D names both, and the tight cover (D == T * (incoming +
    purchase) == 10) makes it limited."""
    result = verdict(available=0, ask=10, incoming=5, purchase=5, threshold_pct=THRESHOLD)

    assert result.answer == "not_available"
    assert result.sources == ("incoming", "purchase")
    assert result.limited is True


def test_verdict_rejects_non_positive_ask():
    """AC-1722: the service never calls `verdict()` without a positive ask, so 0 and a
    negative value both raise rather than silently answering."""
    with pytest.raises(ValueError):
        verdict(available=100, ask=0, incoming=0, purchase=0, threshold_pct=THRESHOLD)

    with pytest.raises(ValueError):
        verdict(available=100, ask=-5, incoming=0, purchase=0, threshold_pct=THRESHOLD)


def test_verdict_threshold_is_inclusive():
    """AC-1723: threshold 30, available 100 - ask 30 is running_low (30 >= 30 * 1.00 == 30,
    inclusive), ask 29 is not (29 >= 30 is false)."""
    at_threshold = verdict(available=100, ask=30, incoming=0, purchase=0, threshold_pct=30)
    below_threshold = verdict(available=100, ask=29, incoming=0, purchase=0, threshold_pct=30)

    assert at_threshold.running_low is True
    assert below_threshold.running_low is False
