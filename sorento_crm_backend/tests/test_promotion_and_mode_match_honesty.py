"""AND-mode promotion matching: what it really does, and what must not regress.

`match_mode=and` is not a boolean AND. `_and_token_match_counts` scores each row
by how many WORDS of a token appear in the description, and
`_and_max_tier_filter` keeps every row reaching the GLOBAL MAX of that score
across the table. A token whose words are split across disjoint rows therefore
returns the UNION of those rows, all labelled `match_tier: "and"` - a label that
names the probe, not what any row satisfied.

Nothing asserted that a returned row contains the queried words, so the
behaviour was untested rather than defended. These tests pin both halves:

  * The loose (substring, non-word-boundary) matching that real enquiries
    depend on. Descriptions glue dates to nouns with underscores, so
    `KITCHEN SINK_22052026` has no word boundary after "SINK" and a
    word-boundary matcher silently loses it. "Kitchen sink catalogue" is a
    real customer message; that row is a real answer to it.
  * The max-coverage semantics themselves, so a change in either direction is
    visible instead of silent.

Fixture descriptions mirror the shapes in the live promotions table
(underscore-glued dates, parenthesised access levels, `.pdf` suffixes,
hyphenated compounds) and the queries are taken verbatim from customer
messages in the WhatsApp history.
"""
from __future__ import annotations

import re
import uuid

import pytest

from app.models.base import set_company_scope
from app.models.marketing import Promotion
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.entity_resolver import resolve_references_intersection

from ._pg_fixture import blank_session

# Every seeded description carries this so assertions can never pick up a real
# promotion row if the suite is ever pointed at a populated database.
MARK = "ZZT"


@pytest.fixture(autouse=True)
def _scope_listeners():
    register_company_scope_listeners()


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, None)
        yield session


def _promo(db, description: str) -> str:
    pid = str(uuid.uuid4())
    db.add(
        Promotion(
            id=pid,
            description=description,
            is_active=True,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return pid


# Shapes copied from the live corpus, prefixed so they are identifiable as test
# rows. The underscore before the date in the SINK_ rows is the load-bearing
# detail - it is what a word-boundary matcher trips on.
CABANA_SINK = f"{MARK} CABANA KITCHEN SINK PROMO 27042026 (END USER)"
CABANA_SHELF = f"{MARK} CABANA SHELF PROMO 31032026 (DEALER USE)"
CABANA_TAP = f"{MARK} CABANA NEW ARRIVAL FILTER TAP PROMO_08052026 (OFFICE USE)"
SORENTO_SINK_GLUED = f"{MARK} SORENTO NEW ARRIVAL KITCHEN SINK_22052026 DEALER.pdf"
SORENTO_SINK_PROMO = f"{MARK} SORENTO KITCHEN SINK PROMO_22052026 END USER.pdf"
ALA_CARTE = f"{MARK} SORENTO UPDATED CERAMIC SINK PROMO (ALA-CARTE & COMBO)_30072026"


@pytest.fixture
def corpus(db):
    """Six rows: three Cabana, three Sorento. No row contains both "cabana" and
    "car"; that disjointness is what several assertions below turn on."""
    ids = {
        "cabana_sink": _promo(db, CABANA_SINK),
        "cabana_shelf": _promo(db, CABANA_SHELF),
        "cabana_tap": _promo(db, CABANA_TAP),
        "sorento_sink_glued": _promo(db, SORENTO_SINK_GLUED),
        "sorento_sink_promo": _promo(db, SORENTO_SINK_PROMO),
        "ala_carte": _promo(db, ALA_CARTE),
    }
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
    return ids


def _resolve(db, tokens):
    return resolve_references_intersection(
        db, tokens, allowed_entity_types=["promotion"]
    ).as_dict()


def _descriptions(payload) -> set[str]:
    return {
        (m.get("display") or {}).get("description")
        for m in payload["intersection"]
        if m["entity_type"] == "promotion"
    }


def _uuids(payload) -> set[str]:
    return {m["uuid"] for m in payload["intersection"] if m["entity_type"] == "promotion"}


# ---------------------------------------------------------------------------
# Why the loose matcher exists. These are the rows a stricter matcher loses.
# ---------------------------------------------------------------------------


def test_kitchen_sink_finds_the_row_whose_date_is_glued_to_the_noun(db, corpus):
    """Real customer message: "Kitchen sink catalogue".

    `SINK_22052026` is one regex word - `_` is a word character - so there is no
    boundary after "SINK". Substring matching finds the row; word-boundary
    matching does not. On the live table this is 3 of the 13 kitchen-sink
    promotions, i.e. a fifth of the answers to a routine question.
    """
    payload = _resolve(db, ["kitchen sink"])

    assert SORENTO_SINK_GLUED in _descriptions(payload), (
        "the underscore-glued row must resolve; losing it is the concrete "
        "regression that word-boundary matching would cause"
    )

    # Spelled out so the reason survives even if this test later fails.
    # `_` is a word character in every regex flavour involved (Python `\b`,
    # Postgres `\m`/`\M`), so "SINK_22052026" offers no boundary after SINK.
    assert not re.search(r"\bsink\b", SORENTO_SINK_GLUED, re.I), (
        "if this row ever gains a word boundary after SINK, the test above "
        "stops defending anything and should be re-pointed at a glued row"
    )
    assert re.search(r"sink", SORENTO_SINK_GLUED, re.I)


def test_a_hyphenated_compound_is_reachable_by_either_half(db, corpus):
    """"ALA-CARTE" is one hyphenated token. Enquiries arrive with the parts
    spelled apart or partially, and the substring matcher keeps them reachable.
    """
    payload = _resolve(db, ["carte"])
    assert ALA_CARTE in _descriptions(payload)


# ---------------------------------------------------------------------------
# What AND-mode actually does. Pinned so a change is loud, not silent.
# ---------------------------------------------------------------------------


def test_a_word_that_matches_nothing_does_not_narrow_the_result(db, corpus):
    """Real customer message: "can share with me bath tub promotion".

    No promotion mentions a bathtub. Max coverage is 1 (the brand word alone),
    so every Cabana row still comes back and the second word contributes
    nothing. The result is not wrong - it is the brand's promotions - but it is
    presented as though both words were honoured.
    """
    both = _resolve(db, ["cabana bathtub"])
    brand_only = _resolve(db, ["cabana"])

    assert _uuids(both) == _uuids(brand_only) != set(), (
        "the unmatched word must be shown to have changed nothing"
    )
    assert all(
        "bathtub" not in (d or "").lower() for d in _descriptions(both)
    ), "no returned row mentions the word the customer asked for"


def test_disjoint_words_return_the_union_of_two_coverage_one_sets(db, corpus):
    """The sharpest case: no row matches both words, yet rows matching EITHER
    come back together under one `match_tier: "and"`.

    "car" hits ALA-CARTE by substring, so a Cabana enquiry is answered partly
    with another brand's promotion. This assertion fails in both directions -
    tightening the matcher drops the ALA-CARTE row, loosening it adds rows, and
    breaking the max-tier rule empties the result.
    """
    payload = _resolve(db, ["cabana car"])
    found = _descriptions(payload)

    assert CABANA_SINK in found, "rows matching only the first word are returned"
    assert ALA_CARTE in found, "rows matching only the second word are returned too"

    for description in found:
        low = (description or "").lower()
        assert not ("cabana" in low and "car" in low), (
            "no row satisfies both words - the result is a union, not an "
            "intersection, which is precisely what `match_tier: and` conceals"
        )

    assert all(m["match_tier"] == "and" for m in payload["intersection"]), (
        "every row carries the same tier label regardless of what it matched"
    )


def test_a_token_whose_words_are_all_absent_returns_nothing(db, corpus):
    """Max coverage does not mean "always return something". When no row hits
    any word the global max is 0 and the probe short-circuits, so the loose
    matcher cannot invent an answer out of nothing.
    """
    payload = _resolve(db, ["helicopter"])
    assert _uuids(payload) == set()


# ---------------------------------------------------------------------------
# The additive honesty fields. Red until the resolver emits them.
# ---------------------------------------------------------------------------


def _coverage(payload, token: str) -> dict:
    entries = payload.get("token_coverage") or []
    match = [e for e in entries if e.get("token") == token]
    assert match, f"no token_coverage entry for {token!r}; got {entries!r}"
    return match[0]


def test_the_response_names_which_words_went_unmatched(db, corpus):
    """The whole point: the caller can say "none of them mention bathtub"
    instead of presenting a broader list as though it answered."""
    payload = _resolve(db, ["cabana bathtub"])

    entry = _coverage(payload, "cabana bathtub")
    assert entry["matched_words"] == ["cabana"]
    assert entry["unmatched_words"] == ["bathtub"]


def test_coverage_is_reported_per_token_not_per_query(db, corpus):
    """Two tokens, each carrying a different unmatched word. A query-level list
    would collapse them and lose which token went unmet.

    The tokens have to genuinely co-occur on a row, or the intersection is empty
    and the test proves nothing: "cabana" and "shelf" both land on the shelf
    promotion, while "bathtub" and "helicopter" land nowhere.
    """
    payload = _resolve(db, ["cabana bathtub", "shelf helicopter"])

    assert _descriptions(payload) == {CABANA_SHELF}
    assert _coverage(payload, "cabana bathtub")["unmatched_words"] == ["bathtub"]
    assert _coverage(payload, "shelf helicopter")["unmatched_words"] == ["helicopter"]


def test_the_response_declares_its_matching_semantics(db, corpus):
    """`match_tier` stays as it is - n8n branches on it - so the honest label
    arrives alongside rather than replacing it."""
    payload = _resolve(db, ["cabana bathtub"])

    assert payload["match_semantics"] == "max_coverage"
    assert all(m["match_tier"] == "and" for m in payload["intersection"]), (
        "the existing field must not change shape"
    )


def test_unmatched_words_are_scoped_to_the_returned_rows(db, corpus):
    """The weak claim, deliberately: "absent from these results", never "absent
    from the catalogue". "sink" appears in the table but in no Cabana-shelf row,
    and no extra query is issued to find that out."""
    payload = _resolve(db, ["cabana shelf"])

    entry = _coverage(payload, "cabana shelf")
    assert set(entry["matched_words"]) == {"cabana", "shelf"}
    assert entry["unmatched_words"] == []


def test_a_word_matched_only_via_its_singular_form_counts_as_matched(db, corpus):
    """`_word_variants` lets "shelves"-style plurals hit the singular in the
    description. Reporting such a word as UNMATCHED would produce a new false
    statement - "no promotion matches taps" while showing a TAP promotion - so
    the variant counts as a match and the word is echoed as the customer typed
    it.
    """
    payload = _resolve(db, ["cabana taps"])

    assert CABANA_TAP in _descriptions(payload)
    entry = _coverage(payload, "cabana taps")
    assert entry["unmatched_words"] == []
    assert "taps" in entry["matched_words"], "echo the customer's spelling, not the variant"


def test_rows_and_tiers_are_untouched_by_the_new_fields(db, corpus):
    """Additive means additive: the same rows come back, with the same tier.
    This is the assertion that lets the change ship without a behaviour diff.
    """
    payload = _resolve(db, ["cabana car"])

    assert _descriptions(payload) == {CABANA_SINK, CABANA_SHELF, CABANA_TAP, ALA_CARTE}
    assert {m["match_tier"] for m in payload["intersection"]} == {"and"}
    assert payload["match_mode"] == "and"
