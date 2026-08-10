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
# The honesty fields. Computed at the API layer (`_resolve_input`) over the
# FINAL row set, after the access-level filter, the promotion expansion and the
# limit have all run - because coverage describing rows a later stage removed
# is itself a false statement (review finding on the first version, which
# baked it into `as_dict()` and asserted "every word matched" on zero-row
# entitlement-filtered results). Partitioned per entity type for the same
# reason: a word matched by a product code must not be credited to a
# promotion enquiry.
# ---------------------------------------------------------------------------


def _resolve_api(db, tokens, **kw):
    """The production entry: the same function the /references/resolve route
    calls, with every row-mutating stage active."""
    from app.api.v1.system.references import _resolve_input

    kw.setdefault("match_mode", "and")
    kw.setdefault("allowed_entity_types", ["promotion"])
    return _resolve_input(db, "", tokens, **kw)


def _coverage(payload, token: str, entity_type: str = "promotion") -> dict:
    entries = payload.get("token_coverage") or []
    tok_entry = [e for e in entries if e.get("token") == token]
    assert tok_entry, f"no token_coverage entry for {token!r}; got {entries!r}"
    per_type = [c for c in tok_entry[0].get("coverage") or [] if c.get("entity_type") == entity_type]
    assert per_type, (
        f"no {entity_type!r} coverage for {token!r}; got {tok_entry[0].get('coverage')!r}"
    )
    return per_type[0]


def test_the_response_names_which_words_went_unmatched(db, corpus):
    """The whole point: the caller can say "none of them mention bathtub"
    instead of presenting a broader list as though it answered."""
    payload = _resolve_api(db, ["cabana bathtub"])

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
    payload = _resolve_api(db, ["cabana bathtub", "shelf helicopter"])

    assert _descriptions(payload) == {CABANA_SHELF}
    assert _coverage(payload, "cabana bathtub")["unmatched_words"] == ["bathtub"]
    assert _coverage(payload, "shelf helicopter")["unmatched_words"] == ["helicopter"]


def test_semantics_is_nested_per_token_never_top_level(db, corpus):
    """`match_tier` stays as it is - n8n branches on it - so the honest label
    arrives alongside rather than replacing it. And it lives INSIDE the
    `token_coverage` entry, not at the top level: top-level keys ride n8n's
    item-mutation chain toward the persisted session, and `by_entity_type`'s
    keys are rendered to the customer as entity types - both consumer
    constraints reported against the first version."""
    payload = _resolve_api(db, ["cabana bathtub"])

    assert "match_semantics" not in payload, "top-level key rides too far downstream"
    entry = [e for e in payload["token_coverage"] if e["token"] == "cabana bathtub"][0]
    assert entry["match_semantics"] == "max_coverage"
    assert set(payload["by_entity_type"].keys()) <= {"promotion"}, (
        "by_entity_type keys are read as resolved entity types downstream; "
        "no metadata key may ever appear there"
    )
    assert all(m["match_tier"] == "and" for m in payload["intersection"]), (
        "the existing field must not change shape"
    )


def test_unmatched_words_are_scoped_to_the_returned_rows(db, corpus):
    """The weak claim, deliberately: "absent from these results", never "absent
    from the catalogue". "sink" appears in the table but in no Cabana-shelf row,
    and no extra query is issued to find that out."""
    payload = _resolve_api(db, ["cabana shelf"])

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
    payload = _resolve_api(db, ["cabana taps"])

    assert CABANA_TAP in _descriptions(payload)
    entry = _coverage(payload, "cabana taps")
    assert entry["unmatched_words"] == []
    assert "taps" in entry["matched_words"], "echo the customer's spelling, not the variant"


def test_rows_and_tiers_are_untouched_by_the_new_fields(db, corpus):
    """Additive means additive: the same rows come back, with the same tier.
    This is the assertion that lets the change ship without a behaviour diff.
    """
    payload = _resolve_api(db, ["cabana car"])

    assert _descriptions(payload) == {CABANA_SINK, CABANA_SHELF, CABANA_TAP, ALA_CARTE}
    assert {m["match_tier"] for m in payload["intersection"]} == {"and"}
    assert payload["match_mode"] == "and"


def test_no_transport_key_leaks_into_the_response(db, corpus):
    """`_match_blob` is how the probes hand the scored text to the API layer;
    it must never reach a consumer. Checked recursively because the filters
    rebuild `by_entity_type` from the same row dicts."""
    payload = _resolve_api(db, ["cabana car"])

    def walk(node):
        if isinstance(node, dict):
            assert "_match_blob" not in node, f"transport key leaked: {node.keys()}"
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    assert "_truncated_entity_types" not in payload


# ---------------------------------------------------------------------------
# The two review blockers, pinned so they cannot come back.
# ---------------------------------------------------------------------------


def _access_type(db, *, name: str, code: str) -> None:
    from app.models.access import ContactAccessType

    db.add(ContactAccessType(code=code, name=name))


def _promo_with_levels(db, description: str, levels: list[str]) -> str:
    pid = str(uuid.uuid4())
    db.add(
        Promotion(
            id=pid,
            description=description,
            is_active=True,
            access_levels=levels,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    return pid


def test_zero_rows_after_the_access_filter_claims_nothing(db):
    """Review blocker 1. `access_levels` is what the n8n promo flow sends on
    every turn. The first version computed coverage before the entitlement
    filter ran, so a zero-row filtered response still asserted "every word
    matched" - a self-contradictory payload on the production path.

    Coverage must describe the FINAL rows: zero rows means no coverage claims
    at all, not "all matched".
    """
    _access_type(db, name="ZZT Dealer", code="zzt_dealer")
    _access_type(db, name="ZZT End User", code="zzt_end_user")
    _promo_with_levels(db, f"{MARK} CABANA FILTER TAP PROMO (END USER)", ["zzt_end_user"])
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    payload = _resolve_api(db, ["cabana tap"], access_levels=["ZZT Dealer"])

    assert payload["intersection"] == [], "the dealer must not see the end-user promo"
    for entry in payload.get("token_coverage") or []:
        assert entry["coverage"] == [], (
            "zero returned rows cannot support any matched/unmatched claim; "
            f"got {entry['coverage']!r}"
        )

    # And the positive side: the entitled caller gets rows AND coverage.
    payload = _resolve_api(db, ["cabana tap"], access_levels=["ZZT End User"])
    assert len(payload["intersection"]) == 1
    entry = _coverage(payload, "cabana tap")
    assert set(entry["matched_words"]) == {"cabana", "tap"}
    assert entry["unmatched_words"] == []


def test_coverage_is_partitioned_by_entity_type(db, corpus):
    """Review blocker 2. The first version pooled every match's text across
    entity types, so "bathtub" was credited to a PRODUCT code while all the
    promotions lacked the word - the flagship example silently failing on any
    unscoped call.

    A word matched only by a product must appear unmatched under promotion,
    and vice versa.
    """
    import uuid as _uuid

    from app.models.product import Product, ProductCategory, UnitOfMeasure

    cat, uom = str(_uuid.uuid4()), str(_uuid.uuid4())
    db.add(ProductCategory(id=cat, category_code=f"ZZTC-{cat[:8]}", category_name="C"))
    db.add(UnitOfMeasure(id=uom, uom_code=f"ZZTU-{uom[:8]}"[:20], uom_name="Each"))
    db.flush()
    db.add(
        Product(
            id=str(_uuid.uuid4()),
            product_code="ZZT-BATHTUB-01",
            product_name="ZZT Bathtub",
            category_id=cat,
            base_uom_id=uom,
            list_price=10,
            is_active=True,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    payload = _resolve_api(
        db, ["cabana bathtub"], allowed_entity_types=["promotion", "product"]
    )

    promo = _coverage(payload, "cabana bathtub", "promotion")
    assert promo["matched_words"] == ["cabana"]
    assert promo["unmatched_words"] == ["bathtub"], (
        "a word matched only by a product code must not be credited to promotions"
    )
    product = _coverage(payload, "cabana bathtub", "product")
    assert "bathtub" in product["matched_words"]
    assert "cabana" in product["unmatched_words"]


def test_coverage_describes_the_rows_after_the_limit(db, corpus):
    """Coverage runs AFTER `_apply_limit`, so it describes exactly the rows in
    the response - and the trimmed type is flagged `truncated` so a consumer
    knows not to phrase an unmatched word as a catalogue-wide absence."""
    payload = _resolve_api(
        db,
        ["cabana"],
        fallback_to_all_types=True,   # the limit is only applied on this path
        limit=2,
    )

    assert len(payload["intersection"]) == 2
    entry = _coverage(payload, "cabana")
    assert entry["matched_words"] == ["cabana"]
    assert entry["truncated"] is True, (
        "rows were cut by the limit; the claim must be marked incomplete"
    )


def _link_product_to_promo(db, product_id: str, promotion_id: str) -> None:
    from app.models.marketing import PromotionGroup, PromotionProduct

    gid = str(uuid.uuid4())
    db.add(
        PromotionGroup(
            id=gid,
            promotion_id=promotion_id,
            group_name="ZZT G",
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    db.flush()
    db.add(
        PromotionProduct(
            id=str(uuid.uuid4()),
            promotion_id=promotion_id,
            promotion_group_id=gid,
            product_id=product_id,
            company_id=DEFAULT_COMPANY_ID,
        )
    )


def _seed_sku_in_promo(db, *, sku: str, promo_desc: str) -> None:
    """A product plus a promotion that CONTAINS it but whose description does
    not mention it - the "check the promo for <SKU>" shape."""
    import uuid as _uuid

    from app.models.product import Product, ProductCategory, UnitOfMeasure

    cat, uom = str(_uuid.uuid4()), str(_uuid.uuid4())
    db.add(ProductCategory(id=cat, category_code=f"ZZTC-{cat[:8]}", category_name="C"))
    db.add(UnitOfMeasure(id=uom, uom_code=f"ZZTU-{uom[:8]}"[:20], uom_name="Each"))
    db.flush()
    pid = str(_uuid.uuid4())
    db.add(
        Product(
            id=pid,
            product_code=sku,
            product_name="ZZT Sink",
            category_id=cat,
            base_uom_id=uom,
            list_price=10,
            is_active=True,
            company_id=DEFAULT_COMPANY_ID,
        )
    )
    promo_id = _promo(db, promo_desc)
    db.flush()
    _link_product_to_promo(db, pid, promo_id)


def test_a_promotion_found_via_membership_is_never_scored_on_its_description(db):
    """Reviewer blocker on the fix itself. "check the promo for <SKU>" walks
    `promotion_products` BACKWARD from the resolved product - the promotion's
    description was never scored against the token
    (`match_field="promotion_membership"`). Blanket-falling-back to
    `display.description` for every promotion row invented
    `unmatched_words=[<SKU>]` on exactly the rows that ARE that SKU's
    promotions - "none of these mention <SKU>" about the SKU's own promos.

    A membership-derived promotion row must contribute no blob: when every
    promotion row is membership-derived the type is OMITTED from coverage
    (no claim), never reported all-unmatched.
    """
    _seed_sku_in_promo(db, sku="ZZT-SINK-9001", promo_desc=f"{MARK} KITCHEN SINK PROMO 2026")
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    payload = _resolve_api(
        db,
        ["ZZT-SINK-9001"],
        allowed_entity_types=["product"],
        domain_hint="promotion",
    )

    types_in_rows = {m["entity_type"] for m in payload["intersection"]}
    assert "promotion" in types_in_rows, "the membership walk must surface the promo"
    membership_rows = [
        m for m in payload["intersection"]
        if m["entity_type"] == "promotion" and m["match_field"] == "promotion_membership"
    ]
    assert membership_rows, "fixture must exercise the via_product path"

    entry = [e for e in payload["token_coverage"] if e["token"] == "ZZT-SINK-9001"][0]
    by_type = {c["entity_type"]: c for c in entry["coverage"]}
    promo_cov = by_type.get("promotion")
    if promo_cov is not None:
        assert "ZZT-SINK-9001" not in promo_cov["unmatched_words"], (
            "the SKU's own promotions reported as not mentioning the SKU - the "
            "false statement this feature exists to prevent"
        )
    # The product row WAS scored (on its code) and must still claim honestly.
    assert by_type["product"]["matched_words"] == ["ZZT-SINK-9001"]


def test_a_type_with_unscored_rows_alongside_scored_ones_is_marked_incomplete(db, corpus):
    """Second half of the omission rule: when SOME rows of a type carry scored
    text and others don't (AND-probe promos next to membership-derived ones),
    the claims cover only the scored subset - so the type must carry
    `truncated: true`, the existing "do not phrase this as an absence" signal.
    """
    # One token, two promotions: promo A NAMES the SKU in its description
    # (scored by the AND probe), promo B merely CONTAINS the product
    # (membership walk, unscored). The response mixes scored and unscored
    # promotion rows.
    _seed_sku_in_promo(db, sku="ZZT-SINK-9002", promo_desc=f"{MARK} BUNDLE PROMO_22052026")
    _promo(db, f"{MARK} ZZT-SINK-9002 LAUNCH PROMO (END USER)")
    db.commit()
    set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))

    payload = _resolve_api(
        db,
        ["ZZT-SINK-9002"],
        allowed_entity_types=["product", "promotion"],
        domain_hint="promotion",
    )

    promo_rows = [m for m in payload["intersection"] if m["entity_type"] == "promotion"]
    fields = {m["match_field"] for m in promo_rows}
    assert fields >= {"promotion_membership", "description"}, (
        f"fixture must produce BOTH row kinds; got {fields!r}"
    )
    cov = _coverage(payload, "ZZT-SINK-9002", "promotion")
    assert "ZZT-SINK-9002" in cov["matched_words"], "the scored promo names the SKU"
    assert cov["truncated"] is True, (
        "unscored promotion rows sit in the response; the claim does not "
        "cover them and must be flagged incomplete"
    )


def test_route_level_coverage_matches_the_response_rows(db, corpus):
    """Reviewer finding F3: `_resolve_input` is not the response boundary -
    the POST route's spec-fallback replaces `intersection` AFTER it returns.
    Coverage must be recomputed over whatever the route actually sends, so a
    future stage that adds rows after `_resolve_input` cannot resurrect the
    original blocker. Exercised through the real route function, not a shim.
    """
    from app.api.v1.system.references import resolve_reference_post, ResolveReferenceRequest

    body = ResolveReferenceRequest(
        query="",
        tokens=["cabana car"],
        match_mode="and",
        allowed_entity_types=["promotion"],
    )
    payload = resolve_reference_post(body, current_user={}, db=db)

    # Same invariants the _resolve_input tests pin, now at the boundary.
    assert "match_semantics" not in payload
    tokens_with_rows = {m["entity_type"] for m in payload["intersection"]}
    for entry in payload.get("token_coverage") or []:
        for cov in entry["coverage"]:
            assert cov["entity_type"] in tokens_with_rows, (
                "coverage mentions a type absent from the rows the route returns"
            )

    def walk(node):
        if isinstance(node, dict):
            assert "_match_blob" not in node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
