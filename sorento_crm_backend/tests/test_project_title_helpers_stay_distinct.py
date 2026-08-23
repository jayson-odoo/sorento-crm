"""Two projects registered by the same test must not read as one development.

CI failure 32610489429: `test_a_manual_regroup_is_remembered_for_that_customer`
registered a second project, and `register_project` refused it with

    409 project_already_registered: This development is already registered as
    "zzt-so Tuju Residences cdcedb" (PRJ-000001)

Nothing about the feature was wrong. The test helpers built both titles as a
fixed phrase plus a 6-hex tail, and trigram similarity does not care that the
tail differs: the shared phrase is most of the string. Measured against the live
`similarity()` with the shipped 0.7 block threshold, `zzt-so Tuju Residences` +
6 hex crossed it on about 1 run in 120, and the longer
`zzt-so Cadangan Membina Pangsapuri` + 6 hex crossed it EVERY time - that one
only ever passed because those tests happen to register one project each.

So the guard is on the helpers, not on any single test: a suffix has to be long
enough that two draws are different developments no matter what they draw.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._pg_fixture import blank_session
from app.services.project_clash_service import (
    normalise_project_title,
    resolve_thresholds,
)

# Every distinct fixed phrase the test suite registers projects under, longest
# first: the longer the shared phrase, the higher two titles score against each
# other, so the longest is the one that decides whether the suffix is enough.
_TITLE_CALL = re.compile(r'title=f"(\{MARKER\}[^"]*?)\s*\{_uid\(\)\[:(\d+)\]\}"')

# The suffix every project-title helper draws. Kept here as the number the guard
# below actually proves, so raising it is a deliberate edit rather than a drift.
REQUIRED_SUFFIX_HEX = 12


def _title_calls() -> list[tuple[Path, str, int]]:
    out: list[tuple[Path, str, int]] = []
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        for phrase, width in _TITLE_CALL.findall(path.read_text()):
            out.append((path, phrase.replace("{MARKER}", "zzt-so").strip(), int(width)))
    return out


def test_every_project_title_helper_draws_a_long_enough_suffix():
    """The mechanical half: no helper is left on the short tail."""
    short = [
        f"{path.name}: {phrase!r} + {width} hex"
        for path, phrase, width in _title_calls()
        if width < REQUIRED_SUFFIX_HEX
    ]
    assert not short, (
        "These helpers build two registrable titles that differ only by a short "
        "random tail, which trigram similarity reads as the same development:\n  "
        + "\n  ".join(short)
    )


def test_the_longest_shared_phrase_still_scores_below_the_block_threshold():
    """The measured half, against the live scorer rather than an assumed number.

    A pure unit assertion on the suffix width would keep passing if the threshold
    were lowered or the normaliser changed what it strips. This asks Postgres.
    """
    phrases = {phrase for _, phrase, _ in _title_calls()}
    assert phrases, "the title helpers moved; this guard needs its pattern updated"
    longest = max(phrases, key=len)

    with blank_session() as db:
        _surface, block = resolve_thresholds(db)
        # `pg_trgm` is installed in `public`, which a scratch schema's search_path
        # does not include - the scorer only resolves in production because the
        # app runs on the public schema.
        db.execute(text("SET search_path TO public"))
        worst = 0.0
        for _ in range(200):
            left = normalise_project_title(
                f"{longest} {uuid.uuid4().hex[:REQUIRED_SUFFIX_HEX]}"
            )
            right = normalise_project_title(
                f"{longest} {uuid.uuid4().hex[:REQUIRED_SUFFIX_HEX]}"
            )
            score = db.execute(
                text("select similarity(:a, :b)"), {"a": left, "b": right}
            ).scalar()
            worst = max(worst, float(score))

    assert worst < block, (
        f"{longest!r} plus {REQUIRED_SUFFIX_HEX} hex scored {worst:.3f} against "
        f"itself, at or above the {block} block threshold: a test registering two "
        "projects under that helper will 409 at random."
    )
