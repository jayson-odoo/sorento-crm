"""Port of `sub-miss-suggest` (S6c, AC-607): the lane a MISSED turn takes.

The live graph (`f42de9c6`) has FOUR Code nodes - `dym-transform`, `dym-annotate`,
`sibling-transform` and the exit `miss-suggest-result`. It has NO `build-suggest-offer` of
its own: that composer stays on the SPINE and reads this exit's `outcome_fragment` one hop
later (the RS-7 errata), which is why `build_suggest_offer` lives in `answer.py` and takes
the fragment's three members as parameters.

Bodies are the LIVE ones, and all four are byte-equal to the export (verified against the
live-body index for `sub-miss-suggest-live@f42de9c6`).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def miss_suggest_result(
    item: dict[str, Any] | None,
    *,
    dym_annotate: Any = None,
    sibling_transform: Any = None,
    sibling_probe: Any = None,
) -> dict[str, Any]:
    """The sub's ONE exit, three mutually exclusive arms.

    A NAMED `isExecuted` check on the convergence, never a positional `$input` guess: n8n's
    fan-out order is not stable, so which arm fired has to be asked, not inferred.

    `outcome_fragment` carries THREE keys, not one. `dym-annotate` is the out-of-lane
    reader a literal sweep cannot see (a dynamic `$(n)` in `build-outcome`'s own map);
    `sibling-transform` / `sibling-probe` are three literal by-name reads inside
    `build-suggest-offer` that the original sweep's "zero out-of-lane readers" claim missed
    outright.
    """
    fragment = {
        "dym-annotate": dym_annotate if dym_annotate is not None else None,
        "sibling-transform": sibling_transform if sibling_transform is not None else None,
        "sibling-probe": sibling_probe if sibling_probe is not None else None,
    }
    if dym_annotate is not None:
        return {**dym_annotate, "outcome_fragment": fragment}
    return {**(item if isinstance(item, dict) else {}), "outcome_fragment": fragment}
