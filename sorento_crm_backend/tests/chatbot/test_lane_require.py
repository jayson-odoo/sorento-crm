"""Phase 2 RED tests for the attribute-first-asks lane, slices S1-S3 - work items B1,
B2, C4, E1, F1 (S1), D1-D3/F3 (S2), E2/F2 (S3).

`documentation/plans/chatbot/attribute-first-asks-acceptance-criteria.md` AC-1303,
AC-1304, AC-1315, AC-1316, AC-1318, AC-1319, AC-1320, AC-1323, AC-1326.
`documentation/plans/chatbot/PLAN-attribute-first-asks.md` - Shape, Work items
B1/B2/C4/E1/F1/D1-D3/F3/E2/F2.

Written BEFORE `app/services/chatbot/lanes/business/predicate.py` exists. An `ImportError`
naming that module is the expected red reason for the tests that import it directly;
`resolve_gate.py` / `gate.py` / `fetch.py` / `answer.py` are ported and DO exist today, so
tests against them fail on a wrong VALUE (missing dict key, wrong count, wrong text) rather
than an import - each test's own docstring says which.

Every module is imported LOCALLY inside its own test (not at file scope), so one missing
module can only fail the tests that actually depend on it, never the whole file's collection.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

import pytest

from tests._pg_fixture import blank_session

# S4 fixtures: reused, not rebuilt (same convention `test_complete_turn.py` and
# `test_s6_s7_integration.py` follow) - `stub_parser` / `stub_access` are the exact
# seams every other engine-level chatbot test stubs the LLM and access check at.
from tests.chatbot.test_engine import stub_access, stub_parser  # noqa: F401 - fixtures used by name


# --------------------------------------------------------------------------- #
# B1 - AC-1303: derive_require is a pure map off the parser's own output.       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "parser_output, expected",
    [
        ({"intent_hint": "check_stock"}, {"stock": True}),
        ({"intent_hint": "check_incoming"}, {"incoming": True}),
        ({"intent_hint": "check_promotion"}, {"promotion": True}),
        (
            {
                "intent_hint": "check_product_attachment",
                "entities": [{"hint": "attachment_type", "raw": "cert"}],
            },
            {"certificate": True},
        ),
        (
            {
                "intent_hint": "check_product_attachment",
                "entities": [{"hint": "attachment_type", "raw": "photo"}],
            },
            {"attachment_type": "photo"},
        ),
        ({"intent_hint": "check_order"}, None),
        ({"intent_hint": None}, None),
    ],
)
def test_derive_require_maps_intents_and_entity_hints(parser_output, expected):
    from app.services.chatbot.lanes.business.predicate import derive_require

    assert derive_require(parser_output) == expected


# --------------------------------------------------------------------------- #
# B1/D2 - AC-1303 (S2 half): a scheme word is split off the SAME attachment_type   #
# raw mechanically - no message-text matching beyond `_CERT_RE`, no DB lookup at   #
# parse time (the `certificate_scheme` lookup set is read later, server-side, by   #
# `_leg_certificate`).                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("pps cert", {"certificate": {"scheme": "pps"}}),
        ("watermark certificate", {"certificate": {"scheme": "watermark"}}),
        # Already asserted by S1 (kept here so the whole scheme-splitting contract
        # lives in one parametrize): the raw IS the cert word alone, nothing left
        # over to name a scheme.
        ("cert", {"certificate": True}),
    ],
)
def test_derive_require_extracts_a_scheme_word_from_the_cert_raw(raw, expected):
    from app.services.chatbot.lanes.business.predicate import derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [{"hint": "attachment_type", "raw": raw}],
    }
    assert derive_require(parser_output) == expected


# --------------------------------------------------------------------------- #
# Console pass 6 (R21, AC-1345): the head's entity reuse hands over an          #
# attachment_type raw already canonicalised to the AttachmentType NAME          #
# ("Certification"), not the customer's own word - every inflection of the     #
# cert word must still be read as the bare leg, never survive as a "scheme".   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Certification", {"certificate": True}),
        ("certification", {"certificate": True}),
        ("certificates", {"certificate": True}),
        ("certs", {"certificate": True}),
        ("CERTIFICATIONS", {"certificate": True}),
        ("PPS certification", {"certificate": {"scheme": "PPS"}}),
        # Regression: "sijil" (the Malay word) is already one of the covered
        # inflections (R21's own rule names it explicitly) - a raw made only of
        # it must stay the bare leg too, not fall through to the generic
        # attachment_type branch the way an unrelated document label would.
        ("sijil", {"certificate": True}),
    ],
)
def test_derive_require_treats_every_cert_inflection_as_the_bare_leg(raw, expected):
    """AC-1345/R21: measured live - the head's `entity_op: reuse` re-used the
    previous turn's attachment_type entity, canonicalised to the AttachmentType
    NAME ("Certification"), and `_cert_scheme_from_raw` only strips "cert",
    "certificate" and "sijil" verbatim - every OTHER inflection (certs,
    certificate-s, certification(s), any case) survives as a bogus "scheme",
    so "which tap has cert" -> "which water tap has cert" (clarify) -> "more"
    (which re-asks the previous certificate question) answered "The register
    has no Certification certificates."

    RED for "Certification"/"certification"/"certificates"/"certs"/
    "CERTIFICATIONS": `derive_require` returns `{"certificate": {"scheme":
    <the raw itself>}}`, not the bare `{"certificate": True}` this AC demands.
    "PPS certification" must still split "PPS" out as the scheme once
    "certification" itself is recognised as a bare cert word.
    """
    from app.services.chatbot.lanes.business.predicate import derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [{"hint": "attachment_type", "raw": raw}],
    }
    assert derive_require(parser_output) == expected


def test_derive_predicate_words_still_strips_a_reused_certification_raw():
    """AC-1345/R21: whatever `derive_require` decides the leg is, the reused
    "Certification" raw must still leave `derive_predicate_words`' own list -
    the described-set remainder must never be asked to bind an AttachmentType
    NAME as a class/product_type word.

    Green today - `derive_predicate_words` collects every attachment_type raw
    unconditionally (`_attachment_type_raws`), so this half of the contract was
    never broken; kept alongside the red cases above so the fix's own test
    file proves the whole turn, not only the leg shape.
    """
    from app.services.chatbot.lanes.business.predicate import derive_predicate_words, derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [{"hint": "attachment_type", "raw": "Certification"}],
    }
    require = derive_require(parser_output)
    assert "Certification" in derive_predicate_words(parser_output, require)


# --------------------------------------------------------------------------- #
# Owner regression (PR #833, R28, AC-1353): the head can drop the             #
# attachment_type entity entirely (console run 10 - one entity, raw "PPS",     #
# canonical_code null, normalised away to `entities: []`) - `derive_require`   #
# must still read the bare certificate leg off `user_goal` / the message text  #
# alone when there is NO attachment raw at all, the same fallback R4 already   #
# uses for a scheme-only raw.                                                  #
# --------------------------------------------------------------------------- #


def test_derive_require_reads_a_bare_certificate_leg_with_no_attachment_raw_at_all():
    """AC-1353/R28(1): intent `check_product_attachment`, `entities: []` (the
    head dropped the attachment_type entity entirely), `user_goal: "trying to
    find which item has PPS cert"` - must still yield the bare `{"certificate":
    True}` leg (the resolver then recovers "PPS" from the remainder, AC-1338).

    RED: `derive_require`'s `check_product_attachment` branch returns `None`
    immediately when `_attachment_type_raws` is empty (`if not raws: return
    None`) - it never reads `user_goal` at all when there is no raw, so the
    turn stays forward and the gate asks for an attachment type. Measured
    live: "which item has PPS cert" (console run 10) answered "Please provide
    the attachment type for the requested product".
    """
    from app.services.chatbot.lanes.business.predicate import derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [],
        "user_goal": "trying to find which item has PPS cert",
    }
    assert derive_require(parser_output) == {"certificate": True}


def test_derive_require_reads_a_bare_certificate_leg_off_the_message_text_fallback():
    """AC-1353/R28(2): the same no-attachment-raw shape, but `user_goal` is
    None - the fallback reads `message_text` instead (the same `message_text`
    keyword R4/AC-1328 already added for the scheme-only-raw case).

    RED for the SAME reason as the sibling test: `derive_require` returns
    `None` before it ever reaches the `user_goal or message_text` read, since
    that read sits inside the `if not raws:` early-return's dead code.
    """
    from app.services.chatbot.lanes.business.predicate import derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [],
        "user_goal": None,
    }
    assert derive_require(parser_output, message_text="which item has PPS cert") == {"certificate": True}


def test_derive_require_stays_forward_with_no_attachment_raw_and_no_cert_word():
    """AC-1353/R28(3) control: `entities: []` and neither `user_goal` nor the
    message text carries a cert word ("send me the photo of item") - the turn
    must stay `None` (forward, unchanged) exactly as it does today. Guards
    the R28 fix against reading EVERY no-attachment-raw check_product_
    attachment turn as a certificate question.

    Green today (and must stay green) - `derive_require` already returns
    `None` here, for the (currently) right structural reason; kept so the
    fix's own test file proves the negative case alongside the two positive
    ones above.
    """
    from app.services.chatbot.lanes.business.predicate import derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [],
        "user_goal": "trying to find the photo of item",
    }
    assert derive_require(parser_output, message_text="send me the photo of item") is None


def test_derive_predicate_words_strips_the_cert_word_found_in_the_message():
    """AC-1353/R28(4): with no attachment_type raw at all, `derive_predicate_
    words` has nothing of its own to strip (`_attachment_type_raws` is empty)
    - it must instead find and strip the cert word the MESSAGE TEXT itself
    carried ("cert" in "which item has PPS cert"), or the described-set reader
    sees "item pps cert" and reports it unrecognized.

    RED: `derive_predicate_words` takes no `message_text` keyword today -
    calling it with one raises `TypeError`, the accepted red shape for this
    AC (measured, no such parameter exists in the current signature).
    """
    from app.services.chatbot.lanes.business.predicate import derive_predicate_words, derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [],
        "user_goal": None,
    }
    require = derive_require(parser_output, message_text="which item has PPS cert")
    words = derive_predicate_words(parser_output, require, message_text="which item has PPS cert")
    assert "cert" in words, words


# --------------------------------------------------------------------------- #
# Reviewer round 4, should-fix (R33, AC-1358): with NO attachment_type raw at   #
# all, the R28 fallback tests `_CERTIFICATE_RE` against `user_goal`/            #
# `message_text` VERBATIM - `_CERTIFICATE_RE = re.compile(r"cert|certificate")` #
# is a bare substring match, so "certainly" and "concert" false-positive as a  #
# certificate question. And "sijil" (already a recognised bare-cert word       #
# everywhere a raw exists) is never tried at all in this no-raw branch, only   #
# `_CERTIFICATE_RE` is.                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "message_text, expected",
    [
        # RED: "certainly" contains the substring "cert" - `_CERTIFICATE_RE`
        # has no word boundary, so this false-positives as a certificate ask.
        ("certainly, send me the drawing for the basin", None),
        # RED for the same reason: "concert" contains "cert".
        ("concert hall basin photo", None),
        # Green control: a genuine cert word, no false-positive substring risk.
        ("is this certified?", {"certificate": True}),
        ("which item has PPS cert", {"certificate": True}),
        # RED: "sijil" (Malay for "certificate") is a recognised bare-cert word
        # everywhere an attachment_type raw exists (`_BARE_CERT_WORDS`), but the
        # no-raw fallback branch only tests `_CERTIFICATE_RE` (English "cert"/
        # "certificate" only) against `user_goal`/`message_text` - "ada sijil
        # untuk basin?" matches neither, so `derive_require` returns `None`
        # instead of the bare certificate leg.
        ("ada sijil untuk basin?", {"certificate": True}),
    ],
)
def test_derive_require_does_not_false_positive_on_a_cert_shaped_substring(message_text, expected):
    """AC-1358/R33 (reviewer round 4, should-fix): `derive_require` with
    `entities: []`, `user_goal: None`, and `message_text` as the ONLY source -
    the no-attachment-raw fallback (R28) must recognise a genuine cert
    question ("is this certified?", "which item has PPS cert", the Malay
    "ada sijil untuk basin?") and must NOT fire on a word that merely
    contains the substring "cert" inside an unrelated word ("certainly",
    "concert").
    """
    from app.services.chatbot.lanes.business.predicate import derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [],
        "user_goal": None,
    }
    assert derive_require(parser_output, message_text=message_text) == expected


def test_derive_predicate_words_strips_the_bare_cert_word_without_punctuation():
    """AC-1358/R33: `derive_predicate_words(..., message_text="is this
    certified?")` must strip the bare word "certified" - WITHOUT the question
    mark - so the described-set reader never sees a stray "?" glued onto a
    class/spec word.

    RED: the no-raw branch splits `message_text` on whitespace and keeps
    whatever `_CERTIFICATE_RE` matched verbatim (`cleaned = word.strip()`,
    which strips surrounding WHITESPACE only, never punctuation) - the word
    survives as "certified?", not "certified".
    """
    from app.services.chatbot.lanes.business.predicate import derive_predicate_words, derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [],
        "user_goal": None,
    }
    require = derive_require(parser_output, message_text="is this certified?")
    words = derive_predicate_words(parser_output, require, message_text="is this certified?")
    assert "certified" in words, words


# --------------------------------------------------------------------------- #
# R4 (fix round 2, AC-1328): a scheme-only attachment_type raw ("PPS") carries  #
# no `_CERT_RE` word of its own (that regex names a BODY - cert/ikram/span/     #
# sirim/bomba/ms####/halal - never the bare register spelling), so             #
# `derive_require` must mirror `derive_routing`'s `is_cert`: ALSO certificate   #
# when the intent is check_product_attachment and `_CERTIFICATE_RE` matches    #
# `user_goal` or the message text.                                             #
# --------------------------------------------------------------------------- #


def test_derive_require_reads_a_scheme_only_attachment_raw_as_a_certificate():
    """AC-1328 (fix round 2, R4): "which item has PPS cert" - the parser emitted
    ONE `attachment_type` entity, raw "PPS" (no cert-word entity at all) - must
    still map to `{"certificate": {"scheme": "PPS"}}`, the same way
    `derive_routing`'s `is_cert` already treats a `check_product_attachment`
    intent whose `user_goal` matches `_CERTIFICATE_RE` as a certificate question
    regardless of what the attachment_type raw itself says.

    Two halves: `user_goal` carries the sentence (the parser's own field,
    `derive_routing` reads the exact same one), and - when `user_goal` is absent
    - the message text reaches `derive_require` through a `message_text` keyword,
    the same seam `resolve_entity_body` already has to hand (`_query_text(ctx)`).

    RED: `derive_require` only tests `_CERT_RE` against the raw itself ("PPS"
    matches none of cert/ikram/span/sirim/bomba/ms####/halal), so today it falls
    to the generic `{"attachment_type": "PPS"}` branch - the actual console
    finding ("I don't know 'PPS' as a product type").
    """
    from app.services.chatbot.lanes.business.predicate import derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [{"hint": "attachment_type", "raw": "PPS", "canonical_code": None}],
        "user_goal": "which item has PPS cert",
    }
    assert derive_require(parser_output) == {"certificate": {"scheme": "PPS"}}

    parser_output_no_goal = {
        "intent_hint": "check_product_attachment",
        "entities": [{"hint": "attachment_type", "raw": "PPS", "canonical_code": None}],
        "user_goal": None,
    }
    assert derive_require(
        parser_output_no_goal, message_text="which item has PPS cert"
    ) == {"certificate": {"scheme": "PPS"}}


# --------------------------------------------------------------------------- #
# B2 - AC-1304 / AC-1322: resolve_entity_body gains require + predicate_words ONLY   #
# when derive_require returns something, every other key stays byte-identical. #
# --------------------------------------------------------------------------- #


def _ctx_for_intent(intent_hint: str | None) -> dict[str, Any]:
    """Two ctx dicts identical except `intent_hint` - domain_hint is held CONSTANT so
    the "every other key equal" assertion is meaningful (a varying domain would also
    vary `body["domain"]`, which is not what this test is about)."""
    return {
        "text": {"message": {"message": {"text": "check"}}},
        "contact": {"id": "1"},
        "parse": {
            "output": {
                "message_type": "business_query",
                "intent_hint": intent_hint,
                "domain_hint": "inventory",
                "match_mode": "or",
                "access_levels": [],
                "entities": [{"raw": "basin", "hint": "product"}],
            }
        },
    }


def test_resolve_entity_body_adds_require_and_predicate_words_only_when_derived():
    from app.services.chatbot.lanes.business.resolve_gate import resolve_entity_body

    body_stock = resolve_entity_body(_ctx_for_intent("check_stock"))
    body_order = resolve_entity_body(_ctx_for_intent("check_order"))

    assert body_stock.get("require") == {"stock": True}
    assert body_stock.get("predicate_words") == ["stock"]
    assert "require" not in body_order
    assert "predicate_words" not in body_order

    keys = (set(body_stock) | set(body_order)) - {"require", "predicate_words"}
    for key in keys:
        assert body_stock.get(key) == body_order.get(key), key


# --------------------------------------------------------------------------- #
# Round 3 re-check (R25, AC-1349): `needs_tier_ask` fires only for a contact    #
# entitled to MORE than one tier, so a single-tier contact's resolve body       #
# sends the parser's own bare `access_levels` - never the tier gate's own      #
# RECOMPOSED names - and the promotion leg counts what the parser tokens       #
# translate to, which can be the wrong tier once a brand qualifies the code.    #
# --------------------------------------------------------------------------- #


def _tier_ctx(access_levels: list[str]) -> dict[str, Any]:
    return {
        "text": {"message": {"message": {"text": "which tap has promo"}}},
        "contact": {"id": "1"},
        "parse": {
            "output": {
                "message_type": "business_query",
                "intent_hint": "check_promotion",
                "domain_hint": "promotion",
                "match_mode": "and",
                "access_levels": access_levels,
                "entities": [],
            }
        },
    }


def test_resolve_entity_body_uses_the_tier_gates_recomposed_access_levels():
    """AC-1349/R25(a): when the tier gate ran and produced any recomposed
    names, `resolve_entity_body`'s own `access_levels` must be exactly those
    names - never the parser's bare tokens - so a stated tier translates to
    the CORRECT brand-qualified code (`['Sorento Dealer'] -> {'dealer'}`)
    rather than whatever `_access_level_codes` makes of the raw parser token
    alone.

    RED today: `resolve_entity_body` accepts no `tier_gate` keyword at all -
    the call itself raises `TypeError: resolve_entity_body() got an
    unexpected keyword argument 'tier_gate'`, the accepted red shape for this
    AC (measured, no such parameter exists in the current signature).
    """
    from app.services.chatbot.lanes.business.resolve_gate import resolve_entity_body

    ctx = _tier_ctx(["dealer"])
    body = resolve_entity_body(ctx, tier_gate={"access_levels_recomposed": ["Sorento Dealer"]})
    assert body.get("access_levels") == ["Sorento Dealer"], body


def test_resolve_entity_body_falls_back_to_parser_tokens_with_no_tier_gate():
    """AC-1349/R25(b): `tier_gate=None` (the tier gate never ran on this turn)
    or a tier gate that ran but recomposed NOTHING (an empty list - no
    entitlement, no stated tier) must both keep today's behaviour: the
    parser's own `access_levels`, unchanged.

    RED today for the SAME reason as the sibling test: the keyword itself
    does not exist yet, so both calls raise `TypeError` before either
    fallback path is reached.
    """
    from app.services.chatbot.lanes.business.resolve_gate import resolve_entity_body

    ctx = _tier_ctx(["dealer"])

    body_none = resolve_entity_body(ctx, tier_gate=None)
    assert body_none.get("access_levels") == ["dealer"], body_none

    body_empty = resolve_entity_body(ctx, tier_gate={"access_levels_recomposed": []})
    assert body_empty.get("access_levels") == ["dealer"], body_empty


# --------------------------------------------------------------------------- #
# C4 - AC-1326: a qualifying predicate bypasses the ambiguity picker AND the    #
# product_attachment "subject did not resolve" block.                          #
# --------------------------------------------------------------------------- #


def _predicate_world() -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Three `spec_search`-tier product matches for an unresolved raw ("water tap"),
    plus a qualifying `predicate` block - the exact shape AC-1326 describes."""
    uuids = [str(uuid.uuid4()) for _ in range(3)]
    matches = [
        {
            "uuid": u,
            "entity_type": "product",
            "canonical_code": f"ZZT-BIDET-{i}",
            "match_tier": "spec_search",
        }
        for i, u in enumerate(uuids)
    ]
    resolver = {
        "resolutions": [{"token": "water tap", "resolved": False, "matches": matches}],
        "unresolved_tokens": ["water tap"],
        "predicate": {
            "qualifying_total": 3,
            "truncated": False,
            "unrecognized_terms": [],
            "require": {"certificate": True},
        },
    }
    parser = {
        "domain_hint": "product_attachment",
        "entities": [
            {"hint": "product", "raw": "water tap"},
            {"hint": "attachment_type", "raw": "cert"},
        ],
    }
    return resolver, parser, uuids


def test_gate_bypasses_ambiguity_and_subject_block_when_predicate_present():
    from app.services.chatbot.lanes.business.gate import run_gate

    resolver, parser, uuids = _predicate_world()

    out = run_gate(dict(resolver), parser=parser, resolver=resolver)

    assert out["require_specific"] is False, out.get("gate_reason")
    assert out["gate_passed"] is True, out.get("gate_reason")
    product_entities = [e for e in out["compatible_entities"] if e["entity_type"] == "product"]
    assert {e["uuid"] for e in product_entities} == set(uuids)


# --------------------------------------------------------------------------- #
# E1 - AC-1315: a HAS turn's fetch passes every qualifying id to the SAME domain #
# tool.                                                                         #
#                                                                                #
# AC-1316 REVISED (console findings, 11 Sep 2026, committed 3779b32d6): "the    #
# tool's row limit stays at its default" - a page is five PRODUCTS, never five  #
# ROWS (measured live: `limit=5` on the stock tool cut the answer to 5          #
# warehouse rows spanning 4 products under a header saying "Showing 5"). The    #
# `assert args.get("limit") == 5` this test used to carry is the SUPERSEDED     #
# half of that AC; fixed here in the same round as the new                     #
# `test_has_fetch_pages_five_products_not_five_rows` below, which is the one    #
# that actually proves the id-slicing this world (3 ids, all shown) is too      #
# small to prove.                                                              #
# --------------------------------------------------------------------------- #


def test_has_turn_fetch_passes_all_ids_to_the_domain_tool():
    from app.services.chatbot.lanes.business import fetch
    from app.services.chatbot.lanes.business.gate import run_gate

    resolver, parser, uuids = _predicate_world()
    gate_out = run_gate(dict(resolver), parser=parser, resolver=resolver)

    args = fetch.entity_ids_transformer(
        {
            "entities": gate_out["compatible_entities"],
            "tool": "crm_master_product_attachments_list",
            "semantic_input": {"contact_id": "1", "space_id": "364817"},
            "predicate": resolver["predicate"],
        }
    )

    assert set(args.get("product_ids") or []) == set(uuids)
    assert "limit" not in args, args.get("limit")


def test_has_fetch_pages_five_products_not_five_rows():
    """AC-1315/AC-1316 (console finding, 11 Sep 2026): with SEVEN qualifying
    product ids the fetch step must carry `product_ids` == the FIRST FIVE (a
    page of PRODUCTS) and must NOT carry `limit: 5` at all (the tool's row
    limit stays at its own default) - `_predicate_world`'s own three-id world
    is too small to prove this: three ids all fit on one page either way, so
    the same three would appear whether the code slices to five or not. Same
    for both domains named in the console finding: the stock tool (rows can
    outnumber products) and the cert tool (files per product).

    RED: `fetch.py`'s own `entity_ids_transformer` sets `out["limit"] = 5`
    unconditionally whenever `trig.get("predicate")` is not None (no product
    slicing exists anywhere in the function), so today ALL SEVEN ids land in
    `product_ids` (not sliced to five) AND `limit` is wrongly present at 5.
    """
    from app.services.chatbot.lanes.business import fetch

    ids = [str(uuid.uuid4()) for _ in range(7)]
    entities = [
        {"uuid": pid, "entity_type": "product", "canonical_code": f"ZZT-PAGE-{i}"}
        for i, pid in enumerate(ids)
    ]
    predicate = {"require": {"stock": True}, "qualifying_total": 7, "truncated": False, "unrecognized_terms": []}

    stock_args = fetch.entity_ids_transformer(
        {
            "entities": entities,
            "tool": "crm_inventory_stock_balance_list",
            "semantic_input": {"contact_id": "1", "space_id": "364817"},
            "predicate": predicate,
        }
    )
    assert stock_args.get("product_ids") == ids[:5], stock_args.get("product_ids")
    assert "limit" not in stock_args, stock_args.get("limit")

    cert_args = fetch.entity_ids_transformer(
        {
            "entities": entities,
            "tool": "crm_master_product_attachments_list",
            "semantic_input": {"contact_id": "1", "space_id": "364817"},
            "predicate": {**predicate, "require": {"certificate": True}},
        }
    )
    assert cert_args.get("product_ids") == ids[:5], cert_args.get("product_ids")
    assert "limit" not in cert_args, cert_args.get("limit")


# --------------------------------------------------------------------------- #
# F1 - AC-1319: qualifying_total=0 enters the existing miss flow, naming the    #
# described set and the predicate.                                             #
# --------------------------------------------------------------------------- #


def test_zero_qualifying_enters_the_existing_miss_flow_naming_the_set():
    """Full lane run (the `_run_lane` pattern from `tests/chatbot/test_warehouse_entity.py`,
    reproduced locally rather than imported across files): three products named
    "* BIDET", none certified, real resolver + real gate, then the render function
    `not_found_error_message` (`answer.py`) named at PLAN work item F1.

    Today `derive_require` is not wired into `resolve_entity_body` at all, so no
    `require` ever reaches the resolver for this turn, the certificate leg never runs,
    and the rendered text carries none of the predicate-shaped copy this AC demands -
    the right red reason for a full-pipeline gap, not a single missing function.
    """
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.answer import not_found_error_message
    from app.services.chatbot.lanes.business.services import ResolveGateServices
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings
    from tests._pg_fixture import blank_session, unique_code

    codes = ["ACC-BIDET", "CAB-BIDET", "SRT-BIDET"]

    with blank_session() as db:
        company = Company(id=str(uuid.uuid4()), code=unique_code("ZZTBD")[:50], name=unique_code("ZZTBD"))
        db.add(company)
        db.flush()
        category = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=unique_code("CAT")[:50],
            category_name="ZZT bidet category",
            company_id=company.id,
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company.id
        )
        db.add_all([category, uom])
        db.flush()

        for code in codes:
            db.add(
                Product(
                    id=str(uuid.uuid4()),
                    product_code=code,
                    product_name=code,
                    description="BIDET SPRAY SET",
                    category_id=category.id,
                    base_uom_id=uom.id,
                    list_price=10,
                    is_active=True,
                    company_id=company.id,
                )
            )
        db.commit()

        set_company_scope(db, frozenset({company.id}))

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = {
            "text": {"message": {"message": {"text": "which sorento bidet has cert"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_product_attachment",
                    "domain_hint": "product_attachment",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [
                        {"raw": "bidet", "hint": "product"},
                        {"raw": "cert", "hint": "attachment_type"},
                    ],
                }
            },
        }

        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert text.startswith("Couldn't find"), text
    assert "certificate" in text.lower(), text
    for code in codes:
        assert code in text, text
    assert "did you mean" in text.lower() or "escalate" in text.lower(), text


# --------------------------------------------------------------------------- #
# Fix round 3 - R16/AC-1340: the zero-qualifying miss copy never reads "a a    #
# match" - the subject is brand + product + category/product_type raws, then  #
# the predicate's class labels; when ALL of those are empty the sentence is    #
# "Couldn't find any product with <predicate>.", never "a a match".            #
# --------------------------------------------------------------------------- #


def test_zero_copy_names_the_category_raw_not_a_a_match():
    """AC-1340/R16(1): a category-hint entity ("bathroom accessory") must be the
    zero-copy's subject - the same standing brand/product raws already have.

    RED: the subject builder (`answer.py`'s `subject_words`) reads only
    `brand` + `hint == "product"` raws - a `hint == "category"` entity is
    invisible to it, so `subject_words` stays empty, `subject` falls to the
    literal "a match", and the sentence reads "Couldn't find a a match with
    stock." - never naming "bathroom accessory" at all.
    """
    from app.services.chatbot.lanes.business.answer import not_found_error_message

    parser = {
        "domain_hint": "product_query",
        "entities": [{"raw": "bathroom accessory", "hint": "category"}],
    }
    gate = {
        "gate_passed": True,
        "predicate": {
            "qualifying_total": 0,
            "unrecognized_terms": [],
            "require": {"stock": True},
            "class_labels": ["Bathroom Accessory"],
        },
    }
    msg = not_found_error_message({}, parser=parser, resolved={}, gate=gate)
    text = (msg.get("escalate_message") or "").strip()

    assert "a a match" not in text.lower(), text
    assert "a match" not in text.lower(), text
    assert text.startswith("Couldn't find a bathroom accessory with stock."), text


def test_zero_copy_says_any_product_when_nothing_names_the_subject():
    """AC-1340/R16(2): no brand/product/category raw AND no `class_labels` at
    all - the sentence must read "Couldn't find any product with <predicate>.",
    never "Couldn't find a a match with <predicate>.".

    RED: `subject_words` stays empty (as in the category case above) and
    falls to the literal "a match" regardless - the sentence reads "Couldn't
    find a a match with stock.", never "any product".
    """
    from app.services.chatbot.lanes.business.answer import not_found_error_message

    parser = {"domain_hint": "product_query", "entities": []}
    gate = {
        "gate_passed": True,
        "predicate": {
            "qualifying_total": 0,
            "unrecognized_terms": [],
            "require": {"stock": True},
            "class_labels": [],
        },
    }
    msg = not_found_error_message({}, parser=parser, resolved={}, gate=gate)
    text = (msg.get("escalate_message") or "").strip()

    assert "a a match" not in text.lower(), text
    assert "a match" not in text.lower(), text
    assert text.startswith("Couldn't find any product with"), text


# --------------------------------------------------------------------------- #
# F3 - AC-1321 (S2): a scheme miss names the schemes on file, not a generic "no  #
# certificate matched these".                                                   #
# --------------------------------------------------------------------------- #


def test_scheme_miss_reply_names_the_schemes_on_file():
    """AC-1321: "which item has watermark cert" against a register that holds PPS
    and SPAN (and an EMPTY `certificate_scheme` lookup set, so "watermark" resolves
    to nothing) must answer "no watermark certificates" and name both schemes on
    file, never the generic zero-qualifying miss.

    Full-pipeline red, deliberately: TODAY `derive_require` has not learned to split
    a scheme word off the SAME attachment_type raw (work item B1/D2 above) - "watermark
    cert" maps to a bare `{"certificate": True}`, so the certificate leg runs
    UNSCOPED, both seeded certified products qualify, and the reply this AC describes
    never renders at all (neither "no watermark certificates" nor "PPS"/"SPAN" appear
    anywhere in the text) - the correct red reason for a whole-pipeline gap spanning
    B1, D2 and the scheme-miss copy, not a single missing function.
    """
    from app.models.base import set_company_scope
    from app.models.certificate import Certificate, CertificateProduct
    from app.models.company import Company
    from app.models.lookup import LookupSet
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.answer import not_found_error_message
    from app.services.chatbot.lanes.business.services import ResolveGateServices
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings
    from tests._pg_fixture import blank_session, unique_code

    with blank_session() as db:
        company = Company(id=str(uuid.uuid4()), code=unique_code("ZZTSC")[:50], name=unique_code("ZZTSC"))
        db.add(company)
        db.flush()
        category = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=unique_code("CAT")[:50],
            category_name="ZZT scheme category",
            company_id=company.id,
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company.id
        )
        db.add_all([category, uom])
        db.flush()

        # D3: the migration ships the set EMPTY - the owner enters options later.
        db.add(
            LookupSet(
                id=str(uuid.uuid4()), tenant_id=None, set_key="certificate_scheme",
                name="Certificate Scheme", is_active=True,
            )
        )
        db.flush()

        for code, scheme in (("ZZT-CERT-PPS", "PPS"), ("ZZT-CERT-SPAN", "SPAN")):
            product = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                description="ZZT CERTIFIED ITEM",
                category_id=category.id,
                base_uom_id=uom.id,
                list_price=10,
                is_active=True,
                company_id=company.id,
            )
            db.add(product)
            db.flush()
            cert = Certificate(
                id=str(uuid.uuid4()),
                scheme=scheme,
                certificate_number=unique_code("CERTNO")[:120],
                status="active",
                company_id=company.id,
            )
            db.add(cert)
            db.flush()
            db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product.id))
        db.commit()

        set_company_scope(db, frozenset({company.id}))

        def resolve_entity(body: dict) -> dict:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = {
            "text": {"message": {"message": {"text": "which item has watermark cert"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_product_attachment",
                    "domain_hint": "product_attachment",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [{"raw": "watermark cert", "hint": "attachment_type"}],
                }
            },
        }

        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert "no watermark certificates" in text.lower(), text
    assert "PPS" in text, text
    assert "SPAN" in text, text


# --------------------------------------------------------------------------- #
# S3 - AC-1316, AC-1318, AC-1320, AC-1323 (work items E2, F2).
#
# Written BEFORE `answer.build_set_header` / `answer.set_noun_for` exist. Every full
# lane-run test below is expected to fail for a WHOLE-PIPELINE reason, spelled out in
# its own docstring, the same convention `test_zero_qualifying_enters_the_existing_
# miss_flow_naming_the_set` (S1) and `test_scheme_miss_reply_names_the_schemes_on_file`
# (S2) above use: `answer.build_set_header` does not exist (ImportError on the two
# direct unit tests), AND `lanes/business/__init__.py::run_fetch`'s own trigger dict
# (built at "the read", ~line 327) never reads `gate.get("predicate")` at all - only
# `fetch.entity_ids_transformer`'s OWN `trig.get("predicate")` branch honours it
# (S1's own `test_has_turn_fetch_passes_all_ids_to_the_domain_tool_with_limit_5` proves
# the transformer alone, by calling it directly rather than through `run_fetch`). So
# through the real production seam a HAS turn's fetch never learns `require` /
# `qualifying_total` at all today: no `limit=5` is ever applied, and there is nothing
# for a header to be built FROM even once `build_set_header` exists. Both gaps are S3's
# own E2 work, not a separate slice's: `qualifying_total` and the actually-shown count
# must reconcile in the SAME header line, so threading the predicate through
# `run_fetch`'s trigger is what makes the header possible at all.
#
# CONTRACT CONTRADICTION (see `test_unknown_term_clarifies_with_nearest_names`'s own
# docstring for the full measurement): a bare CLASS word with no product entity
# ("which tap has cert") does not actually bind to class "Tap" anywhere in the current
# pipeline - `resolve_product_set` counts EVERY active product satisfying the `require`
# leg when neither `product_ids` nor a `filter_specs` clause describes the set, which is
# what happens here. The cert/stock counts the tests below assert (7, 3, 1, 2) are
# therefore right for the WRONG reason - every product this suite seeds happens to be a
# class-Tap product, so "no class filter" and "class = Tap" are indistinguishable. This
# is a real gap in AC-1306/C2 (S1), surfaced here because S3's header text is the first
# place a class NOUN is ever read back to the customer; it is not this slice's to fix,
# but the coder should know the qualifying_total these tests exercise is not proof the
# class scoping itself works.
# --------------------------------------------------------------------------- #


def _seed_registry(db) -> None:
    """The class / product_type vocabulary the described-set binding reads
    (`product_spec_search.filter_specs` -> `ProductSpecifications.values`), seeded
    exactly as `tests/test_product_predicate_service.py`'s own fixture does. No custom
    company is created and no `company_id` is ever passed below - every owned row relies
    on the `before_insert` auto-stamp against the single-company default test scope
    (`tests/conftest.py::_default_company_scope_for_tests`, Sorento), the same
    convention that file's fixture already uses successfully."""
    from app.services.product_class_signal import backfill_category_signals
    from app.services.product_spec_registry import seed_spec_registry

    backfill_category_signals(db)
    seed_spec_registry(db)


def _seed_category_and_uom(db) -> tuple[str, str]:
    from app.models.product import ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT category"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    return category.id, uom.id


def _tap_product(db, *, category_id: str, uom_id: str, code: str | None = None):
    """A product whose DESCRIPTION contains the class-Tap trigger word ("TAP"), so
    `derive_for_code` - the same real spec-derivation pipeline `resolve_product_set`
    reads through `ProductSpecifications.values["class"]` - binds it to class "Tap"
    with no hand-built spec row (`product_spec_derivation.py`'s `("TAP", "Tap")` rule)."""
    from app.models.product import Product
    from app.services.product_spec_derivation import derive_for_code
    from tests._pg_fixture import unique_code

    code = code or unique_code("ZZTAP")[:50]
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=f"{code} CHROME BASIN TAP",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=10,
        is_active=True,
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


def _basin_product(db, *, category_id: str, uom_id: str, code: str | None = None):
    """A class-Wash-Basin contrast product - the class word must be the description's
    TRAILING noun (`product_spec_derivation._class_from_description` only matches the
    tail: "500MM" after "WASH BASIN" would break the match), so this carries no
    dimension suffix, unlike `_tap_product`'s own description."""
    from app.models.product import Product
    from app.services.product_spec_derivation import derive_for_code
    from tests._pg_fixture import unique_code

    code = code or unique_code("ZZBSN")[:50]
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=f"{code} WHITE WASH BASIN",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=10,
        is_active=True,
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


def _certificate_for(db, *, product_id: str, valid_until=None, scheme: str = "ZZT-CERT"):
    from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
    from tests._pg_fixture import unique_code

    cert = Certificate(
        id=str(uuid.uuid4()),
        scheme=scheme,
        certificate_number=unique_code("CERTNO")[:60],
        status="active",
    )
    db.add(cert)
    db.flush()
    if valid_until is not None:
        rev = CertificateRevision(
            id=str(uuid.uuid4()), certificate_id=cert.id, revision_no=1, valid_until=valid_until
        )
        db.add(rev)
        db.flush()
        cert.current_revision_id = rev.id
        db.flush()
    db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product_id))
    db.flush()
    return cert


def _warehouse(db):
    from app.models.inventory import Warehouse
    from tests._pg_fixture import unique_code

    row = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=unique_code("WH")[:50],
        warehouse_name="ZZT Warehouse",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _stock_for(db, *, product_id: str, warehouse_id: str, on_hand: int = 10):
    from app.models.inventory import Stock

    row = Stock(
        id=str(uuid.uuid4()),
        product_id=product_id,
        warehouse_id=warehouse_id,
        quantity_on_hand=on_hand,
        quantity_reserved=0,
    )
    db.add(row)
    db.flush()
    return row


def _run_has_lane(db, ctx: dict[str, Any], *, fake_call_tool) -> tuple[dict[str, Any], dict[str, Any]]:
    """resolve -> gate -> fetch, the real production seams (`resolve_gate.run` then
    `lanes.business.run_fetch`), with only the MCP call stubbed. Returns
    `(resolve_gate_output, fetch_fragment)`."""
    from app.services.chatbot.lanes import business
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings

    def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        payload = {**body, "spec_fallback": False, "understand_phrase": False}
        principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
        return resolve_reference_post(ResolveReferenceRequest(**payload), current_user=principal, db=db)

    services = ResolveGateServices(
        access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
    )
    out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")

    fetch_services = FetchServices(mcp_call=fake_call_tool)
    fragment = business.run_fetch(out, services=fetch_services, dry_run=False, space_id="364817")
    return out, fragment


def _cert_fake_call_tool(db):
    """Mirrors `sorento_crm_mcp.presenters._product_attachments`' field labels for a
    certificate-bearing row (Product Code / Attachment Type / File Name / Certificate
    Number / Valid Until / Validity), over the seeded register - no MCP server, no
    network."""
    import json

    from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
    from app.models.product import Product

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        product_ids = list(args.get("product_ids") or [])
        rows = (
            db.query(Product, Certificate, CertificateRevision)
            .join(CertificateProduct, CertificateProduct.product_id == Product.id)
            .join(Certificate, Certificate.id == CertificateProduct.certificate_id)
            .outerjoin(CertificateRevision, CertificateRevision.id == Certificate.current_revision_id)
            .filter(Product.id.in_(product_ids))
            .order_by(Product.product_code)
            .all()
        )
        limit = args.get("limit")
        if isinstance(limit, int):
            rows = rows[:limit]
        items = []
        for product, cert, revision in rows:
            valid_until = revision.valid_until if revision is not None else None
            expired = bool(valid_until and valid_until < date.today())
            items.append(
                {
                    "title": product.product_code,
                    "fields": [
                        {"key": "product_code", "label": "Product Code", "value": product.product_code},
                        {"key": "attachment_type", "label": "Attachment Type", "value": "Certification"},
                        {"key": "file_name", "label": "File Name", "value": f"{product.product_code}.pdf"},
                        {
                            "key": "certificate_number",
                            "label": "Certificate Number",
                            "value": cert.certificate_number,
                        },
                        {
                            "key": "valid_until",
                            "label": "Valid Until",
                            "value": valid_until.isoformat() if valid_until else None,
                        },
                        {"key": "validity", "label": "Validity", "value": "Expired" if expired else "Valid"},
                    ],
                    "flags": {"expired": expired},
                }
            )
        return json.dumps(
            {
                "result_type": "product_attachments",
                "intro": "I have attached the file(s) below.",
                "items": items,
                "has_result": bool(items),
            }
        )

    return fake_call_tool


def _stock_fake_call_tool(db):
    """Mirrors `sorento_crm_mcp.presenters._stock`'s field labels (Product Code /
    Warehouse / System Location / Quantity On Hand); never emits a Sellable /
    Outstanding field, matching a contact with no `inventory.sellable` field reveal."""
    import json

    from app.models.inventory import Stock, Warehouse
    from app.models.product import Product

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        product_ids = list(args.get("product_ids") or [])
        rows = (
            db.query(Product, Stock, Warehouse)
            .join(Stock, Stock.product_id == Product.id)
            .join(Warehouse, Warehouse.id == Stock.warehouse_id)
            .filter(Product.id.in_(product_ids))
            .order_by(Product.product_code)
            .all()
        )
        items = [
            {
                "title": product.product_code,
                "fields": [
                    {"key": "product_code", "label": "Product Code", "value": product.product_code},
                    {"key": "warehouse", "label": "Warehouse", "value": warehouse.warehouse_name},
                    {"key": "system_location", "label": "System Location", "value": warehouse.warehouse_code},
                    {"key": "quantity_on_hand", "label": "Quantity On Hand", "value": stock.quantity_on_hand},
                ],
                "flags": {},
            }
            for product, stock, warehouse in rows
        ]
        return json.dumps(
            {
                "result_type": "stock",
                "intro": "Stock details found for the requested products.",
                "items": items,
                "has_result": bool(items),
            }
        )

    return fake_call_tool


_ITEM_NUM_RE = re.compile(r"^\d+\.\s+")


def _block_for(text: str, code: str) -> str:
    """The item paragraph naming `code` ("*Product Code:* <code>" through the next
    blank line), position number stripped - two replies numbering the SAME product
    differently (1 vs 2 items on the page) must not fail this on the number alone."""
    for chunk in text.split("\n\n"):
        if f"*Product Code:* {code}" in chunk:
            lines = chunk.strip().split("\n")
            lines[0] = _ITEM_NUM_RE.sub("", lines[0])
            return "\n".join(lines)
    raise AssertionError(f"no item block for {code!r} in reply: {text!r}")


def _cert_ctx(text: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "text": {"message": {"message": {"text": text}}},
        "contact": {"id": "999"},
        "parse": {
            "output": {
                "message_type": "business_query",
                "intent_hint": "check_product_attachment",
                "domain_hint": "product_attachment",
                "match_mode": "or",
                "access_levels": [],
                "entities": entities,
            }
        },
    }


@pytest.mark.parametrize(
    "qualifying_total, shown, set_noun, require, expected",
    [
        (1256, 5, "taps", {"certificate": True}, "1,256 taps have certificates. Showing 5."),
        (3, 3, "taps", {"certificate": True}, "3 taps have certificates."),
        (1, 1, "tap", {"certificate": True}, "1 tap has certificates."),
        (7, 5, "taps", {"stock": True}, "7 taps have stock. Showing 5."),
        (2, 2, "taps", {"attachment_type": "Product Photos"}, "2 taps have product photos."),
        (4, 4, "sinks", {"incoming": True}, "4 sinks have incoming stock."),
        (4, 4, "sinks", {"promotion": True}, "4 sinks have a promotion."),
        (
            9,
            5,
            "taps",
            {"certificate": True, "stock": True},
            "9 taps have certificates and stock. Showing 5.",
        ),
    ],
)
def test_build_set_header_strings(qualifying_total, shown, set_noun, require, expected):
    """AC-1316 (S3, work item E2): the header line, as a pure string function.

    RED: `answer.build_set_header` does not exist - `ImportError`.
    """
    from app.services.chatbot.lanes.business.answer import build_set_header

    assert build_set_header(qualifying_total, shown, set_noun, require) == expected


@pytest.mark.parametrize(
    "class_labels, expected",
    [
        (["Tap"], "taps"),
        (["Wash Basin"], "wash basins"),
        (["Water Closet"], "water closets"),
        ([], "products"),
        (["Tap", "Shower"], "products"),
    ],
)
def test_set_noun_for(class_labels, expected):
    """AC-1316 (S3, work item E2): the header's noun, off the described set's class
    label(s) - two classes fall back to the generic "products" (D5's set answer has no
    single noun to say).

    RED: `answer.set_noun_for` does not exist - `ImportError`.
    """
    from app.services.chatbot.lanes.business.answer import set_noun_for

    assert set_noun_for(class_labels) == expected


def test_set_answer_carries_the_header_and_shows_five():
    """AC-1316: a HAS turn's reply opens with "<qualifying_total> <set noun> have
    <predicate noun>. Showing <n>." before the existing certificate block, and the
    shown count must actually BE `n` - seven certified class-Tap products, no explicit
    product entity at all (the described set comes purely from the class binding on
    "which tap has cert", per AC-1306/C2).

    RED (see the module-section docstring above): today's reply's first line is the
    tool's own `intro` ("I have attached the file(s) below."), never a header, and the
    render shows all 7 products (no limit was ever threaded through `run_fetch`), not 5.
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        for _ in range(7):
            product = _tap_product(db, category_id=category_id, uom_id=uom_id)
            _certificate_for(db, product_id=product.id)
        db.commit()

        ctx = _cert_ctx(
            "which tap has cert", [{"raw": "cert", "hint": "attachment_type"}]
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "7 taps have certificates. Showing 5.", reply
    assert reply.count("*Product Code:*") == 5, reply


def test_set_answer_is_scoped_to_the_class_word():
    """AC-1306 + AC-1316 (captain follow-up, after the S3 red-test report): a HAS turn's
    described set must be scoped to the class word in the message, not to "every
    certified product regardless of class" - the gap
    `tests/test_resolve_predicate.py::test_class_word_in_query_scopes_the_described_set`
    pins directly against the resolver. World: two certified class-Tap products AND one
    certified class-Wash-Basin product, so a reply naming "2 taps" and omitting the
    basin code is proof of real scoping, not an all-Tap world's coincidence (the
    accidental-pass the S3 tester's own module-section banner comment flags for the
    siblings of this test).

    RED: the header line does not exist yet (same E2 gap as every other test in this
    module), so `lines[0]` fails first; AND even once a header renders, today's
    `qualifying_total` would be 3 (every certified product, unscoped - see the
    resolver-level test above for the root cause), not 2, and the basin code would
    appear in the reply's product list rather than being correctly excluded.
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        tap1 = _tap_product(db, category_id=category_id, uom_id=uom_id)
        tap2 = _tap_product(db, category_id=category_id, uom_id=uom_id)
        basin = _basin_product(db, category_id=category_id, uom_id=uom_id)
        for product in (tap1, tap2, basin):
            _certificate_for(db, product_id=product.id)
        db.commit()

        ctx = _cert_ctx(
            "which tap has cert", [{"raw": "cert", "hint": "attachment_type"}]
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""
        basin_code = basin.product_code

    lines = reply.splitlines()
    assert lines and lines[0] == "2 taps have certificates.", reply
    assert basin_code not in reply, reply


def test_set_answer_header_omits_showing_when_all_fit():
    """AC-1316: when `qualifying_total` is 5 or fewer the header omits "Showing" -
    three certified class-Tap products, all three render.

    RED: the header line is entirely absent from today's reply (see the module-section
    docstring above).
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        for _ in range(3):
            product = _tap_product(db, category_id=category_id, uom_id=uom_id)
            _certificate_for(db, product_id=product.id)
        db.commit()

        ctx = _cert_ctx(
            "which tap has cert", [{"raw": "cert", "hint": "attachment_type"}]
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "3 taps have certificates.", reply
    assert "Showing" not in reply, reply


def test_expired_only_certificate_still_counts_and_is_flagged():
    """AC-1318: "has cert" counts any ACTIVE register certificate regardless of date
    validity (D6) - one class-Tap product whose only certificate's current revision
    expired years ago still qualifies, and the render keeps flagging it exactly as
    today (`fetch._item_line`'s existing "(EXPIRED)" flag and the presenter's own
    "Validity: Expired" field - neither is new in this slice).

    RED: only the header line is missing (a single qualifying product never hits the
    limit-wiring gap the other tests above name), so this is the cleanest single-reason
    red of the set - `lines[0]` is the tool's `intro`, not "1 tap has certificates.".
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        _certificate_for(db, product_id=product.id, valid_until=date(2020, 1, 1))
        db.commit()

        ctx = _cert_ctx(
            "which tap has cert", [{"raw": "cert", "hint": "attachment_type"}]
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "1 tap has certificates.", reply
    assert "*Validity:* Expired" in reply, reply
    assert "(EXPIRED)" in reply, reply


def test_unknown_term_clarifies_with_nearest_names():
    """AC-1320 (work item F2): a HAS turn whose free term binds NO class /
    product_type / brand (AC-1301's own "water tap" example - "tap" alone is a class
    keyword, but the two-word phrase as a whole is not) must clarify with the nearest
    vocabulary, never answer the generic miss copy.

    RED, and NOT for the reason this docstring first guessed (kept below as a
    CONTRACT CONTRADICTION for the coder, per the tester brief): `unrecognized_terms`
    is EMPTY in production for this turn, not `["water tap"]`. Measured directly
    (`resolve_gate.run(...)["resolved"]["predicate"]` == `{"require": {"certificate":
    True}, "qualifying_total": 0, "truncated": False, "unrecognized_terms": []}`).
    Root cause: `app/api/v1/system/references.py`'s require branch calls
    `derive_search_inputs(db, query_text, specs=[], free_terms=[], ...)` and DELIBERATELY
    drops the function's own returned free terms (its comment: "merging that in fed the
    raw sentence to filter_specs's honesty check... reporting 'which kitchen sinks have
    stock' itself as unrecognized"), then calls `resolve_product_set(..., free_terms=
    payload.free_terms)` - and `resolve_entity_body` never populates a `free_terms` key
    on the resolve body at all, so this is `[]` on every chatbot turn. A bare class word
    like "tap" is bound only through `filter_specs`'s OWN `free_terms` argument
    (`resolve_classes_for_term`, exercised by `test_filter_specs_resolves_a_class_term`
    directly) - which this call path never reaches either. So for THIS turn `specs=[]`
    AND `free_terms=[]`, `described_given` is False, and `resolve_product_set` falls to
    its "nothing was given to describe the set" branch, which - for a `require`-only
    call with no described-set input at all - counts every ACTIVE product satisfying the
    leg with NO restriction (measured: `product_predicate_service.py` ~line 292-303,
    the `described = []` case skips the `query.filter(...)` call entirely). That is what
    also makes `test_set_answer_carries_the_header_and_shows_five` and its siblings above
    "pass" their product count today - every certified/stocked product THIS suite seeds
    happens to be a class-Tap product, so "count everything, no class filter" and "count
    only taps" are indistinguishable there. Here the world has ONLY class-Tap products
    too (by design - AC-1320 needs "tap" in the vocabulary for its "Did you mean"
    suggestion), so `qualifying_total` is 0 regardless, and the actual reply is
    "Couldn't find a water tap with a certificate. Would you like me to escalate to
    customer service team?" - AC-1319's S1 honest-zero copy, not AC-1320's. F2 cannot be
    "just" a new clarify-copy branch: it also has to make a bare class word reach
    `unrecognized_terms` at all (a content-word extraction over `query_text`, fed to
    `filter_specs`'s `free_terms` - NOT the raw derive_search_inputs echo the S1 comment
    above correctly refuses to use, which flags whole phrases like "which kitchen sinks
    have stock" as unrecognized whole-cloth).
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        _tap_product(db, category_id=category_id, uom_id=uom_id)
        _tap_product(db, category_id=category_id, uom_id=uom_id)
        db.commit()

        from app.services.chatbot.lanes.business import resolve_gate
        from app.services.chatbot.lanes.business.answer import not_found_error_message
        from app.services.chatbot.lanes.business.services import ResolveGateServices
        from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
        from app.config import settings

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = _cert_ctx(
            "which water tap has cert",
            [
                {"raw": "water tap", "hint": "product"},
                {"raw": "cert", "hint": "attachment_type"},
            ],
        )
        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert "I don't know 'water tap' as a product type" in text, text
    assert "Did you mean" in text, text
    assert "Couldn't find" not in text, text


def test_stock_set_answer_matches_forward_block_for_a_dealer():
    """AC-1323: field-reveal gating is unchanged between a forward turn and a HAS
    turn - a dealer contact with NO field reveals (`ctx["access"]` absent, so
    `include_sellable` never sets and the render never carries a Sellable /
    Outstanding field either way) sees the SAME stock block for the same product on
    both. Two class-Tap products with stock in one warehouse; the forward turn types
    a real code (predicate skipped per AC-1305, byte-identical to today), the HAS turn
    asks "which tap has stock" (predicate runs, both qualify).

    RED: the two blocks already match today (nothing in this slice touches the block
    body), so the only failing assertion is the header - the HAS reply's first line is
    the tool's own `intro`, never "2 taps have stock.".
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        p1 = _tap_product(db, category_id=category_id, uom_id=uom_id)
        p2 = _tap_product(db, category_id=category_id, uom_id=uom_id)
        warehouse = _warehouse(db)
        _stock_for(db, product_id=p1.id, warehouse_id=warehouse.id)
        _stock_for(db, product_id=p2.id, warehouse_id=warehouse.id)
        db.commit()

        fake_call_tool = _stock_fake_call_tool(db)

        ctx_forward = {
            "text": {"message": {"message": {"text": f"{p1.product_code} stock"}}},
            "contact": {"id": "998"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_stock",
                    "domain_hint": "inventory",
                    "match_mode": "and",
                    "access_levels": [],
                    "entities": [
                        {
                            "raw": p1.product_code,
                            "hint": "product",
                            "canonical_code": p1.product_code,
                            "confident": True,
                        }
                    ],
                }
            },
        }
        ctx_has = {
            "text": {"message": {"message": {"text": "which tap has stock"}}},
            "contact": {"id": "998"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_stock",
                    "domain_hint": "inventory",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [{"raw": "tap", "hint": "product"}],
                }
            },
        }

        out_forward, fragment_forward = _run_has_lane(db, ctx_forward, fake_call_tool=fake_call_tool)
        out_has, fragment_has = _run_has_lane(db, ctx_has, fake_call_tool=fake_call_tool)

        assert out_forward.get("_exit_kind") == "continue", out_forward.get("gate_reason")
        assert out_has.get("_exit_kind") == "continue", out_has.get("gate_reason")

        reply_forward = (fragment_forward.get("fetch") or {}).get("response") or ""
        reply_has = (fragment_has.get("fetch") or {}).get("response") or ""

    block_forward = _block_for(reply_forward, p1.product_code)
    block_has = _block_for(reply_has, p1.product_code)

    assert block_forward == block_has, (reply_forward, reply_has)
    assert "Sellable" not in reply_forward, reply_forward
    assert "Sellable" not in reply_has, reply_has
    lines_has = reply_has.splitlines()
    assert lines_has and lines_has[0] == "2 taps have stock.", reply_has


# --------------------------------------------------------------------------- #
# Console fix round 2 (11 Sep 2026, PLAN-attribute-first-asks.md R2/R3/R6/R9/   #
# R10, AC-1327/AC-1329) - full lane runs, real resolver (`_run_has_lane`, the   #
# same seam S3's tests above use). Every world below seeds a WORD-token         #
# forward hit alongside the real certified/stocked set, so a picker built off   #
# the forward hit (rather than the predicate) is provably wrong, not merely     #
# untested.                                                                     #
# --------------------------------------------------------------------------- #


def _wash_basin_category(db):
    """A category whose CODE `backfill_category_signals` recognises as
    `<brand>-WB` (`product_class_signal.CLASS_SUFFIXES["WB"] == "Wash Basin"`),
    so `resolve_classes_for_term(db, "basin")` finds it through the category's
    OWN `search_synonyms` (`CLASS_SYNONYMS["Wash Basin"]` lists "basin"
    verbatim) - not only through `stored_class_labels`' whole-label match,
    which "basin" alone can never satisfy against the two-word label "Wash
    Basin". `_seed_category_and_uom`'s own generic `CAT...` code carries no
    such mapping, which is why a test that needs the bare word "basin" to
    resolve needs this category instead of that one.
    """
    from app.services.product_class_signal import backfill_category_signals
    from app.models.product import ProductCategory

    category = ProductCategory(
        id=str(uuid.uuid4()), category_code="ZZT-WB", category_name="ZZT Wash Basin"
    )
    db.add(category)
    db.flush()
    backfill_category_signals(db)
    db.refresh(category)
    return category


def test_set_answer_replaces_the_found_line_and_no_picker_forms():
    """AC-1327/AC-1326 (R2/R3, fix round 2): "which tap has cert" against a world
    with a genuine forward hit for the word token "tap" (two products whose CODE
    contains "TAP" as a plain substring, neither certified) must still answer the
    3-certified-tap SET, never a "Found: ..." + "Please choose" picker built off
    that forward hit.

    RED: nothing on the require path strips the "tap" token's own forward product
    matches once HAS has run (same gap `test_has_removes_word_token_product_
    matches_from_the_forward_result` pins at the resolver level) - the gate's own
    per-token ambiguity block (`gate.py`, `REQUIRE_SPECIFIC_DOMAINS`) only skips a
    group whose matches are ALL `spec_search` tier, and the "tap" resolution's two
    forward substring matches are tier "substring" - so it falls to `still_
    ambiguous` and the reply carries the "Found: ..." / "Please choose" picker
    text instead of the header this AC demands - measured directly: `gate_reason`
    is "'product_attachment' ambiguous (no single exact match); user must pick"
    and `_exit_kind` is "not_found", never "continue".
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)

        def _plain(code, name):
            from app.models.product import Product

            row = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=name,
                description=f"{name} DESCRIPTION",
                category_id=category_id,
                base_uom_id=uom_id,
                list_price=10,
                is_active=True,
            )
            db.add(row)
            db.flush()
            return row

        _plain("ZZT-COLD-TAP", "ZZT COLD TAP")
        _plain("ZZT-HOT-TAP", "ZZT HOT TAP")

        for _ in range(3):
            product = _tap_product(db, category_id=category_id, uom_id=uom_id)
            _certificate_for(db, product_id=product.id)
        db.commit()

        ctx = _cert_ctx(
            "which tap has cert",
            [
                {"hint": "category", "raw": "tap"},
                {"hint": "attachment_type", "raw": "cert", "canonical_code": "certificate"},
            ],
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "3 taps have certificates.", reply
    assert "Found:" not in reply, reply
    assert "Please choose" not in reply, reply
    assert "needs to be more specific" not in reply, reply


def test_brand_and_category_words_give_a_set_answer_not_a_picker():
    """AC-1327 (R3, fix round 2): "which sorento bidet has cert" - a brand word
    plus a category word, both forward-hitting NON-certified products (three
    bidets, one branded Sorento, none certified) - alongside a FOURTH, unrelated
    Sorento product whose derived spec `product_type` is "bidet" and which DOES
    carry a certificate - must answer the 1-qualifying SET, never keep the
    3-bidet picker the forward hits would otherwise build.
    """
    from app.models.product import Brand, Product
    from tests._pg_fixture import unique_code

    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)

        sorento = Brand(id=str(uuid.uuid4()), brand_code=unique_code("ZZT-SRT")[:20], brand_name="SORENTO")
        cabana = Brand(id=str(uuid.uuid4()), brand_code=unique_code("ZZT-CAB")[:20], brand_name="CABANA")
        db.add_all([sorento, cabana])
        db.flush()

        def _bidet(code, brand_id):
            row = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                description="BIDET SPRAY SET",
                category_id=category_id,
                base_uom_id=uom_id,
                brand_id=brand_id,
                list_price=10,
                is_active=True,
            )
            db.add(row)
            db.flush()
            return row

        _bidet("ACC-BIDET", cabana.id)
        _bidet("CABANA-BIDET", cabana.id)
        srt_bidet = _bidet("SRT-BIDET", sorento.id)

        cert_product = Product(
            id=str(uuid.uuid4()),
            product_code="SRTWT5875",
            product_name="SRTWT5875",
            description="SORENTO CHROME BIDET SPRAY",
            category_id=category_id,
            base_uom_id=uom_id,
            brand_id=sorento.id,
            list_price=10,
            is_active=True,
        )
        db.add(cert_product)
        db.flush()
        from app.services.product_spec_derivation import derive_for_code

        derive_for_code(db, "SRTWT5875")
        _certificate_for(db, product_id=cert_product.id)
        db.commit()

        ctx = _cert_ctx(
            "which sorento bidet has cert",
            [
                {"hint": "brand", "raw": "sorento"},
                {"hint": "category", "raw": "bidet"},
                {"hint": "attachment_type", "raw": "cert", "canonical_code": "certificate"},
            ],
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""
        cert_product_code = cert_product.product_code
        srt_bidet_code = srt_bidet.product_code

    lines = reply.splitlines()
    assert lines and lines[0] in (
        "1 Sorento bidet has certificates.",
        "1 bidet has certificates.",
    ), reply
    assert cert_product_code in reply, reply
    assert "Please choose" not in reply, reply
    assert srt_bidet_code not in reply, reply


def test_unrecognised_label_clarifies_as_a_document_type():
    """AC-1329 (R6, fix round 2): "which basin has photo" against an EMPTY
    `attachment_type_alias` set must clarify "photo" as a DOCUMENT type, naming
    the product-facing AttachmentType names on file - never the product-type
    sentence ("I don't know 'photo' as a product type"), which answers the wrong
    question (the unrecognised word names a FILE LABEL, not a class/product_type
    word).
    """
    from app.models.product import ProductAttachment, UnitOfMeasure
    from app.models.resources import Attachment, AttachmentType
    from tests._pg_fixture import unique_code

    with blank_session() as db:
        _seed_registry(db)
        category = _wash_basin_category(db)
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each")
        db.add(uom)
        db.flush()
        basin = _basin_product(db, category_id=category.id, uom_id=uom.id)
        attachment_type = AttachmentType(
            id=str(uuid.uuid4()),
            code="PRODUCT_PHOTOS",
            type_name="Product Photos",
            allowed_extensions="jpg,png",
        )
        db.add(attachment_type)
        db.flush()
        # AC-1329's product-facing rule: a type must appear in `product_attachments`
        # to be listed - linked to the basin here the same way `_linked_type` does
        # in `test_document_types_listed_are_product_facing_only`, or this type is
        # correctly excluded and the "Product Photos" assertion below fails for a
        # reason unrelated to what this test is actually about.
        attachment = Attachment(
            id=str(uuid.uuid4()),
            original_filename="basin-photo.jpg",
            stored_filename="basin-photo.jpg",
            file_path="https://cdn/basin-photo.jpg",
            attachment_type_id=attachment_type.id,
        )
        db.add(attachment)
        db.flush()
        db.add(
            ProductAttachment(id=str(uuid.uuid4()), product_id=basin.id, attachment_id=attachment.id)
        )
        db.commit()

        from app.services.chatbot.lanes.business import resolve_gate
        from app.services.chatbot.lanes.business.answer import not_found_error_message
        from app.services.chatbot.lanes.business.services import ResolveGateServices
        from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
        from app.config import settings

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = _cert_ctx(
            "which basin has photo",
            [
                {"hint": "category", "raw": "basin"},
                {"hint": "attachment_type", "raw": "photo"},
            ],
        )
        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert "I don't know 'photo' as a document type" in text, text
    assert "Types I know:" in text, text
    assert "Product Photos" in text, text
    assert "as a product type" not in text, text


# --------------------------------------------------------------------------- #
# Second live console pass (11 Sep 2026, PLAN-attribute-first-asks.md) - two    #
# polish items on top of the already-fixed R6/E2 work.                         #
# --------------------------------------------------------------------------- #


def test_document_types_listed_are_product_facing_only():
    """AC-1329 (R6 polish, second console pass): "Types I know:" must name only
    AttachmentType rows that actually appear in `product_attachments` - never
    the whole AttachmentType table. World: three product-facing types (Product
    Photos, Technical Specifications, Certification), each linked to the one
    seeded basin product through a real `product_attachments` row; two more
    types (Container Status, Complaint Document) exist in the table but carry
    NO product link at all - internal document classes a customer never asks
    about.

    RED: `_attachment_type_names_on_file` (`product_predicate_service.py`)
    reads every `AttachmentType.type_name` with no join to `product_attachments`
    at all, so both unlinked types leak into the reply - measured live: "which
    item has PPS cert" listed Complaint Document, Container Status, GRN, Portal
    Submission alongside the real product document classes.
    """
    from app.models.product import ProductAttachment, UnitOfMeasure
    from app.models.resources import Attachment, AttachmentType
    from tests._pg_fixture import unique_code

    with blank_session() as db:
        _seed_registry(db)
        category = _wash_basin_category(db)
        uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each")
        db.add(uom)
        db.flush()
        basin = _basin_product(db, category_id=category.id, uom_id=uom.id)

        def _linked_type(code: str, name: str) -> None:
            at = AttachmentType(id=str(uuid.uuid4()), code=code, type_name=name, allowed_extensions="pdf")
            db.add(at)
            db.flush()
            attachment = Attachment(
                id=str(uuid.uuid4()),
                original_filename=f"{code}.pdf",
                stored_filename=f"{code}.pdf",
                file_path=f"https://cdn/{code}.pdf",
                attachment_type_id=at.id,
            )
            db.add(attachment)
            db.flush()
            db.add(
                ProductAttachment(id=str(uuid.uuid4()), product_id=basin.id, attachment_id=attachment.id)
            )
            db.flush()

        _linked_type("PRODUCT_PHOTOS", "Product Photos")
        _linked_type("TECH_SPEC", "Technical Specifications")
        _linked_type("CERTIFICATION", "Certification")

        # Unlinked - carried in the table, never attached to any product.
        db.add(
            AttachmentType(
                id=str(uuid.uuid4()),
                code="CONTAINER_STATUS",
                type_name="Container Status",
                allowed_extensions="pdf",
            )
        )
        db.add(
            AttachmentType(
                id=str(uuid.uuid4()),
                code="COMPLAINT_DOC",
                type_name="Complaint Document",
                allowed_extensions="pdf",
            )
        )
        db.commit()

        from app.services.chatbot.lanes.business import resolve_gate
        from app.services.chatbot.lanes.business.answer import not_found_error_message
        from app.services.chatbot.lanes.business.services import ResolveGateServices
        from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
        from app.config import settings

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = _cert_ctx(
            "which basin has photo",
            [
                {"hint": "category", "raw": "basin"},
                {"hint": "attachment_type", "raw": "photo"},
            ],
        )
        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert "Product Photos" in text, text
    assert "Technical Specifications" in text, text
    assert "Certification" in text, text
    assert "Container Status" not in text, text
    assert "Complaint Document" not in text, text


# --------------------------------------------------------------------------- #
# Third console pass (11 Sep 2026, PLAN-attribute-first-asks.md R12, AC-1331)  #
# - a parser variant folds a two-word product description into ONE product    #
# entity ("Sorento bidet" -> token "Sorentobidet"), which never matches any    #
# real product code. The certificate leg still finds the real product through #
# the brand + class binding, but the reply took the miss copy anyway.         #
# --------------------------------------------------------------------------- #


def test_unresolved_word_token_is_the_description_not_a_miss():
    """AC-1331/R12 (third console pass): when `predicate.qualifying_total > 0`,
    an unresolved WORD token (the parser's single product entity "Sorento
    bidet", folded to "Sorentobidet" and matching no real code) must never be
    listed as a miss - it IS the described set's own description, and the set
    answer must render.

    World: one Sorento-branded, certified product whose description contains
    "BIDET" (`derive_for_code` reads `product_type: "bidet"` off it), plus two
    unrelated, uncertified products (a class-Tap and a class-Wash-Basin one) so
    the set answer naming exactly the one product is not a coincidence of an
    all-matching world.

    GREEN TODAY under this exact world, measured directly: `resolve_gate.run`
    exits `continue` (`gate_reason` "ok"), and the fetch renders "1 bidet has
    certificates." followed by the certificate block for ZZTWT5875 - never the
    "Couldn't find" / "Here's what you want: ... But no certificate matched
    these" combiner (`answer.py`'s `build_breakdown_msg`, reached only when the
    gate does NOT pass). AC-1326's own `predicate_bypass`
    (`isinstance(resolver.get("predicate"), dict)`) already short-circuits the
    ambiguity picker AND the product_attachment "subject did not resolve" block
    that would otherwise fail this turn on the unresolved "Sorentobidet" token,
    so this exact input shape does not reproduce R12's console finding here.
    Kept as the regression guard AC-1331 asks for, reported honestly per this
    file's own "CONTRACT CONTRADICTION" convention (see the S3 banner earlier
    in this file) rather than forced red by inventing a different world; if the
    live turn's actual parser output carried something this construction does
    not (a different domain_hint, a missing `canonical_code`, an additional
    entity), that is this test's own finding to hand back, not a reason to
    keep guessing inputs until it breaks.
    """
    from app.models.product import Brand, Product
    from app.services.product_spec_derivation import derive_for_code
    from tests._pg_fixture import unique_code

    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)

        sorento = Brand(id=str(uuid.uuid4()), brand_code=unique_code("ZZT-SRT")[:20], brand_name="SORENTO")
        db.add(sorento)
        db.flush()

        target = Product(
            id=str(uuid.uuid4()),
            product_code="ZZTWT5875",
            product_name="ZZTWT5875",
            description="SORENTO CHROME BIDET SPRAY SET",
            category_id=category_id,
            base_uom_id=uom_id,
            brand_id=sorento.id,
            list_price=10,
            is_active=True,
        )
        db.add(target)
        db.flush()
        derive_for_code(db, "ZZTWT5875")
        _certificate_for(db, product_id=target.id)

        # Two unrelated, UNCERTIFIED products - so a reply naming only ZZTWT5875
        # is proof of real scoping, not a coincidence of an all-matching world.
        _tap_product(db, category_id=category_id, uom_id=uom_id)
        _basin_product(db, category_id=category_id, uom_id=uom_id)
        db.commit()

        ctx = _cert_ctx(
            "which sorento bidet has cert",
            [
                {"hint": "product", "raw": "Sorento bidet"},
                {"hint": "attachment_type", "raw": "cert", "canonical_code": "certificate"},
            ],
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0].startswith("1 "), reply
    assert "has certificates." in lines[0], reply
    assert "ZZTWT5875" in reply, reply
    assert "Couldn't find" not in reply, reply
    assert "no certificate matched" not in reply, reply


def test_set_header_names_the_scheme():
    """AC-1316 (second console pass): a scheme-narrowed certificate require must
    name the SCHEME in the set header, not the bare "certificates" noun - "which
    item has PPS cert" must read "940 products have PPS certificates. Showing
    5.", never lose the scheme the customer asked about. A bare `{"certificate":
    True}` require is untouched (no scheme to name).

    RED: `build_set_header`'s own `_header_predicate_phrase` maps every
    `require["certificate"]` value (bool OR the `{"scheme": ...}` dict) to the
    same flat "certificates" noun via `_HEADER_PREDICATE_NOUN` - the scheme
    value is never read - so the scheme case renders "940 products have
    certificates. Showing 5.", losing the "PPS" the customer asked about
    (measured live on "which item has PPS cert").
    """
    from app.services.chatbot.lanes.business.answer import build_set_header

    assert (
        build_set_header(940, 5, "products", {"certificate": {"scheme": "PPS"}})
        == "940 products have PPS certificates. Showing 5."
    )
    assert (
        build_set_header(2, 2, "taps", {"certificate": True})
        == "2 taps have certificates."
    )


def test_common_product_types_fallback_is_never_empty_under_contact_scope():
    """AC-1329 (R10, fix round 2): "which zzqx has cert" (a nonsense product word,
    no class/product_type binds) must clarify with a "Try a product type such
    as ..." fallback drawn from the catalogue's OWN class labels under the
    request's real scope, ordered by how common each class is in that scope -
    never the generic "a class or product type I know" placeholder, and never
    empty. World: 3 taps, 2 wash basins, 1 water closet, so frequency order is
    tap, wash basin, water closet.

    GREEN TODAY, kept as the regression guard AC-1329/R10 asks for: measured
    directly against this exact world, `_common_class_labels`
    (`product_predicate_service.py`) already returns the frequency-ordered
    labels under the single-company scope `blank_session()` seeds into (the
    conftest default), so this scenario does not reproduce R10's console
    finding - the plan's own cause ("returned nothing under the live CONTACT
    scope") names a multi-company / real-contact scope this fixture cannot
    build. Reported honestly rather than forced red (the file's own
    "CONTRACT CONTRADICTION" convention, see the S3 banner above); the test 8
    sibling right above (`test_unrecognised_label_clarifies_as_a_document_
    type`) already pins the OTHER half of R10/AC-1329 - an attachment-label
    miss (`_leg_attachment_type`'s `_UnrecognizedLabel`) carries no
    `common_class_labels` at all, so a caller that reaches the generic
    product-type sentence via THAT path always sees the empty placeholder,
    whatever the catalogue holds. If the coder's fix genuinely needs a
    multi-company repro to fail here, that is this test's own finding to hand
    back, not a reason to invent different inputs until it breaks.
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        for _ in range(3):
            _tap_product(db, category_id=category_id, uom_id=uom_id)
        for _ in range(2):
            _basin_product(db, category_id=category_id, uom_id=uom_id)

        from app.models.product import Product
        from app.services.product_spec_derivation import derive_for_code
        from tests._pg_fixture import unique_code

        wc_code = unique_code("ZZWC")[:50]
        wc = Product(
            id=str(uuid.uuid4()),
            product_code=wc_code,
            product_name=wc_code,
            description=f"{wc_code} SORENTO WATER CLOSET",
            category_id=category_id,
            base_uom_id=uom_id,
            list_price=10,
            is_active=True,
        )
        db.add(wc)
        db.flush()
        derive_for_code(db, wc_code)
        db.commit()

        from app.services.chatbot.lanes.business import resolve_gate
        from app.services.chatbot.lanes.business.answer import not_found_error_message
        from app.services.chatbot.lanes.business.services import ResolveGateServices
        from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
        from app.config import settings

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = _cert_ctx(
            "which zzqx has cert",
            [
                {"hint": "product", "raw": "zzqx"},
                {"hint": "attachment_type", "raw": "cert", "canonical_code": "certificate"},
            ],
        )
        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert "Try a product type such as tap, wash basin, water closet" in text, text
    assert "a class or product type I know" not in text, text


def test_shown_counts_products_not_rows():
    """AC-1330 (R8, fix round 2): "which basin got stock" over five class-Wash-
    Basin products, each carrying stock rows in THREE warehouses (15 rows total),
    must count PRODUCTS in the header - `shown` is distinct product codes
    rendered, never tool rows. Five or fewer products leaves no "Showing"; seven
    products shows exactly five distinct codes and says "Showing 5.".

    Entities carry `hint: "product"` for "basin" (not "category") - matching
    `test_stock_set_answer_matches_forward_block_for_a_dealer`'s own convention
    just above: `inventory` is not in `_DOMAIN_HINT_EXPANSIONS`, so a `category`
    hint there widens only to `promotion` (never `product`), and "basin" would
    reach no product probe at all.
    """
    with blank_session() as db:
        _seed_registry(db)
        category = _wash_basin_category(db)
        _, uom_id = _seed_category_and_uom(db)
        warehouses = [_warehouse(db) for _ in range(3)]
        products = [_basin_product(db, category_id=category.id, uom_id=uom_id) for _ in range(5)]
        for product in products:
            for warehouse in warehouses:
                _stock_for(db, product_id=product.id, warehouse_id=warehouse.id)
        db.commit()

        ctx = {
            "text": {"message": {"message": {"text": "which basin got stock"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_stock",
                    "domain_hint": "inventory",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [{"hint": "product", "raw": "basin"}],
                }
            },
        }
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_stock_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "5 wash basins have stock.", reply
    assert "Showing" not in reply, reply

    with blank_session() as db:
        _seed_registry(db)
        category = _wash_basin_category(db)
        _, uom_id = _seed_category_and_uom(db)
        warehouses = [_warehouse(db) for _ in range(3)]
        products = [_basin_product(db, category_id=category.id, uom_id=uom_id) for _ in range(7)]
        for product in products:
            for warehouse in warehouses:
                _stock_for(db, product_id=product.id, warehouse_id=warehouse.id)
        db.commit()

        ctx = {
            "text": {"message": {"message": {"text": "which basin got stock"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_stock",
                    "domain_hint": "inventory",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [{"hint": "product", "raw": "basin"}],
                }
            },
        }
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_stock_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "7 wash basins have stock. Showing 5.", reply
    shown_codes = _s4_codes_in(reply)
    assert len(shown_codes) == 5, reply


# --------------------------------------------------------------------------- #
# S4 - AC-1317 (work item E3): "more" paging by 5 through the offer carry.
#
# Written BEFORE any S4 code exists: `variables.selection_context == "set_page"` is
# never written by the tail today (the tail's roster ladder in `compile_state.py`
# only ever writes `member_offer` / `suggest_offer` / `tier_offer` / `team_clarify`
# kinds), and `head/output_exchange.py` has no bare-word arm for "more" / "next" /
# "lagi" at all (grepped: absent). So every test below runs the REAL production seam
# end to end - `engine.run_turn` with the business lane wired to real DB reads (S1-S3
# are green, so a set answer's HEADER and PRODUCT BLOCK already render correctly) -
# and fails on the ONE thing S4 adds: the tail never stamps the `set_page` carry, and
# a bare "more" is read by NOTHING today, so it falls through the ordinary ladder and
# answers as an unrelated turn (typically a miss/clarify, never "Showing 6 to 7." or
# "That was all 7 taps.").
#
# CONTRACT NOTE for the coder (not a blocker, just named so a reviewer does not cite it
# out of context): `output_exchange.py`'s own module docstring says "No NEW [text-
# sniffing] site may be added: a reviewer finding one is a merge blocker" - that rule
# guards the D8 PARITY PORT of the n8n graph (no undocumented drift from the JS this
# module replaces), not new plan-approved business logic. E3 names this file as the
# bare-word arm's home explicitly, so the rule does not block it; flagged here only so
# the coder does not have to re-derive that distinction under review.
#
# CONTRACT NOTE 2: the plan's own quoted shape for the new carry is a DICT -
# `variables.last_result_set = {"kind": "set_page", "qualifying_ids": [...], ...}` -
# while `compile_state._offer_carry` gates every EXISTING carry kind on
# `jsc.is_array(prev_set)` (`last_result_set` there is always a roster LIST). The coder
# will need to either widen that gate to accept this dict shape or give `set_page` its
# own parallel carry check; the tests below assert only the OBSERVABLE session state
# and reply text, not which of the two the coder picks.
#
# MEASURED, worth naming for the coder: `route.decide()` classifies a domain-less,
# intent-less, entity-less short message (exactly the parser output E3's own risk note
# says a "more" turn gets) as `branch_kind = "low_signal"` (`head/route.py:315`,
# `is_low_signal()`), which today's `lanes/casual.py` owns - never the business lane.
# With only `business_query` in `chatbot_completed_lanes` (as every test below sets),
# that is why turn 2 in the tests below answers "Sorry, I ran into a problem
# understanding that." rather than reaching the business fetch step at all: the arm
# has to intercept BEFORE or AT that routing decision (reading `selection_context` off
# the carried session, which `route.decide` does not receive today), not only inside
# the business lane's own gate/fetch, or a "more" will never arrive there to page.
#
# Every full-turn test wires the SAME three seams `test_s6c_engine_paths.py` /
# `test_s6_s7_integration.py` use: `business_services.production_services` (resolve),
# `business_services.fetch_services` (the MCP call) and
# `business_services.answer_services_for` (the miss-flow probes, stubbed empty since
# none of these turns is expected to reach them) - real `resolve_gate` / `gate` /
# `fetch` / `answer` / tail code runs, only the network is stubbed. `chatbot_completed_
# lanes = ["business_query"]` plus both switches on so the CRM answers in one
# `run_turn` call rather than delegating to n8n.
# --------------------------------------------------------------------------- #


def _s4_no_probe_answer_services():
    from app.services.chatbot.lanes.business.services import AnswerServices

    def _mcp_probe(name: str, args: dict) -> Any:
        return {"answers": [], "has_result": False}

    def _family_fetch(query: str) -> Any:
        return {"data": []}

    return AnswerServices(mcp_probe=_mcp_probe, family_fetch=_family_fetch)


def _s4_real_resolve_entity(db):
    """The SAME closure `_run_has_lane` (S3) uses, calling the real resolver endpoint
    function against the seeded world - reused here because engine-level tests need a
    `ResolveGateServices` bundle, not a bare callable."""
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings

    def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        payload = {**body, "spec_fallback": False, "understand_phrase": False}
        principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
        return resolve_reference_post(ResolveReferenceRequest(**payload), current_user=principal, db=db)

    return resolve_entity


def _s4_counting_resolve_entity(counter: dict[str, int]):
    """A resolver that never touches the DB and never raises - used on a "more" turn
    so a call is COUNTED (proof the resolver ran) rather than crashing the turn and
    hiding the real red reason (the reply text) behind a traceback."""

    def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        counter["n"] = counter.get("n", 0) + 1
        return {"tokens": [], "resolutions": [], "unresolved_tokens": []}

    return resolve_entity


def _s4_wire_engine(session_factory, monkeypatch, *, resolve_entity, fetch_mcp_call):
    from app.models.user import SystemSetting
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices
    from tests.chatbot.conftest import set_chatbot_switches

    set_chatbot_switches(session_factory, business_lane=True, ordering=True)
    db = session_factory()
    setting = db.query(SystemSetting).first()
    setting.chatbot_completed_lanes = ["business_query"]
    db.commit()

    bundle = ResolveGateServices(
        access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
    )
    monkeypatch.setattr(
        engine_mod.business_services, "production_services", lambda db, *, space_id=None: bundle
    )
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=fetch_mcp_call)
    )
    monkeypatch.setattr(
        engine_mod.business_services, "answer_services_for", lambda session_factory: _s4_no_probe_answer_services()
    )
    return engine_mod


def _s4_envelope(*, contact_id: str, message_id: str, text: str):
    from tests.chatbot.test_engine import _envelope

    return _envelope(
        contact={
            "id": contact_id,
            "firstName": "ZZT",
            "custom_fields": [{"name": "is_human_intervened", "value": "false"}],
        },
        message={
            "event_type": "message.received",
            "contact": {"id": contact_id},
            "message": {
                "messageId": message_id,
                "contactId": contact_id,
                "channelId": "whatsapp",
                "traffic": "incoming",
                "message": {"type": "text", "text": text},
            },
        },
        is_test=False,
    )


def _s4_seed_contact(session_factory, *, contact_id: str, session_vars: dict[str, Any]) -> None:
    import json

    from sqlalchemy import text as sa_text

    db = session_factory()
    db.execute(
        sa_text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": contact_id, "phone": f"+6000{abs(hash(contact_id)) % 10**7:07d}", "sv": json.dumps(session_vars)},
    )
    db.commit()


def _s4_session_vars(session_factory, contact_id: str) -> dict[str, Any]:
    import json

    from sqlalchemy import text as sa_text

    db = session_factory()
    row = db.execute(
        sa_text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :cid"),
        {"cid": contact_id},
    ).first()
    raw = row.session_vars if row is not None else {}
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _s4_contact_id(tag: str) -> str:
    return f"ZZT-s4-{tag}-{uuid.uuid4().hex[:8]}"


def _s4_codes_in(reply: str) -> set[str]:
    return set(re.findall(r"\*Product Code:\* (\S+)", reply))


def _s4_cert_parser_output(**overrides: Any):
    from tests.chatbot.test_engine import _parser_output

    base = dict(
        intent_hint="check_product_attachment",
        domain_hint="product_attachment",
        match_mode="or",
        entities=[
            {
                "raw": "cert",
                "hint": "attachment_type",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
    )
    base.update(overrides)
    return _parser_output(**base)


def _s4_bare_parser_output(**overrides: Any):
    """"more" / "next" / "lagi" etc: the parser tags nothing (E3's own risk note - "a
    turn where the parser tags nothing and the intent is null gets no `require` and
    behaves as today, which is the safe failure"), so this is `intent_hint: None,
    domain_hint: None, entities: []` on every case this section exercises."""
    from tests.chatbot.test_engine import _parser_output

    base = dict(intent_hint=None, domain_hint=None, entities=[])
    base.update(overrides)
    return _parser_output(**base)


def _s4_seed_seven_taps(db) -> list[str]:
    codes: list[str] = []
    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    for _ in range(7):
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        _certificate_for(db, product_id=product.id)
        codes.append(product.product_code)
    db.commit()
    return codes


def _s4_seed_seven_taps_pps(db) -> tuple[list[str], list[str]]:
    """Same world as `_s4_seed_seven_taps`, but every tap's certificate carries
    scheme "PPS" - a scheme-narrowed require then qualifies all seven,
    letting a "more" page test reuse this world unchanged. Returns (product
    codes, certificate ids), both order-parallel."""
    codes: list[str] = []
    cert_ids: list[str] = []
    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    for _ in range(7):
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        cert = _certificate_for(db, product_id=product.id, scheme="PPS")
        codes.append(product.product_code)
        cert_ids.append(cert.id)
    db.commit()
    return codes, cert_ids


def _cert_capturing_fake_call_tool(db, calls: list[dict[str, Any]]):
    """Wraps `_cert_fake_call_tool` to also record every MCP call (name, args)
    so a test can inspect the `certificate_ids` argument the fetch step
    actually sent, without duplicating its rendering logic."""

    inner = _cert_fake_call_tool(db)

    def fake_call_tool(name: str, args: dict[str, Any]) -> Any:
        calls.append({"name": name, "args": dict(args)})
        return inner(name, args)

    return fake_call_tool


# --------------------------------------------------------------------------- #
# Owner regression (PR #833, R29, AC-1354): a scheme-narrowed certificate      #
# leg must pass the qualifying certificates' OWN ids to the tool, alongside    #
# the page's product_ids, on the first answer and on every "more" page (the   #
# carry stores them) - a bare certificate leg passes nothing extra.            #
# --------------------------------------------------------------------------- #


def test_scheme_narrowed_certificate_predicate_passes_certificate_ids_to_the_tool(
    session_factory, stub_parser, stub_access, monkeypatch
):
    """AC-1354/R29: "which tap has PPS cert" must call
    `crm_master_product_attachments_list` with `certificate_ids` alongside
    the first-five `product_ids` - only the PPS files should ever render, not
    every certificate file the qualifying products hold. The following
    "more" page must carry the SAME `certificate_ids` (the carry stores
    them).

    RED: `entity_ids_transformer` never reads `predicate.certificate_ids` -
    it only ever slices `product_ids` for a HAS turn - so the tool args carry
    no `certificate_ids` key at all on either turn.
    """
    contact_id = _s4_contact_id("certids")
    db = session_factory()
    codes, cert_ids = _s4_seed_seven_taps_pps(db)
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    calls: list[dict[str, Any]] = []
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_capturing_fake_call_tool(db, calls),
    )
    stub_parser(
        _s4_cert_parser_output(
            entities=[
                {
                    "raw": "PPS cert",
                    "hint": "attachment_type",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                }
            ]
        )
    )
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-certids-1", text="which tap has PPS cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    assert len(calls) == 1, calls
    turn1_args = calls[0]["args"]
    assert set(turn1_args.get("certificate_ids") or []) == set(cert_ids), turn1_args
    assert turn1_args.get("product_ids"), turn1_args

    stub_parser(_s4_bare_parser_output())
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-certids-2", text="more"),
        session_factory=session_factory,
    )
    assert turn2.status == "done", turn2.error
    assert len(calls) == 2, calls
    turn2_args = calls[1]["args"]
    assert set(turn2_args.get("certificate_ids") or []) == set(cert_ids), turn2_args


def test_bare_certificate_predicate_passes_no_certificate_ids(
    session_factory, stub_parser, stub_access, monkeypatch
):
    """AC-1354/R29 control: a BARE certificate leg (no scheme) must pass
    nothing extra - the tool renders every certificate file the qualifying
    products hold, exactly as it does today. Guards the fix against adding
    `certificate_ids` unconditionally.

    Green today (nothing computes this key either way, scheme or bare) -
    kept as the regression guard alongside the scheme-narrowed red case.
    """
    from app.models.certificate import Certificate, CertificateProduct

    contact_id = _s4_contact_id("nocertids")
    db = session_factory()
    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    for i in range(7):
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        # A certificate_number built WITHOUT the substring "cert" - the shared
        # `_certificate_for` helper's own `unique_code("CERTNO")` collides
        # with the bare word "cert" through an UNRELATED general entity-
        # resolution probe (the register's `certificate_number` column, not
        # this AC's predicate/require mechanism), which would make this
        # control world carry a stray `certificate_ids` entry for a reason
        # that has nothing to do with R29.
        cert = Certificate(
            id=str(uuid.uuid4()), scheme="ZZT-SIRIM", certificate_number=f"ZZT-{i:06d}", status="active"
        )
        db.add(cert)
        db.flush()
        db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product.id))
    db.commit()
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    calls: list[dict[str, Any]] = []
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_capturing_fake_call_tool(db, calls),
    )
    stub_parser(_s4_cert_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-nocertids-1", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    assert len(calls) == 1, calls
    assert "certificate_ids" not in calls[0]["args"], calls[0]["args"]


def test_set_answer_writes_the_set_page_carry(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1317: a set answer's tail stamps `selection_context = "set_page"` and a
    `last_result_set` carrying the described set, the offset already advanced past the
    5 shown, and the request's own predicate/set-noun/domain/tool - so a later "more"
    has everything it needs with no second resolver call.

    RED: nothing in `compile_state.py` writes a `set_page` kind today (the roster
    ladder's only kinds are `member_offer` / `suggest_offer` / `tier_offer` /
    `team_clarify`), so `selection_context` is left at whatever the ordinary ladder
    produces for an answered turn with no offer of its own - `None` - never
    `"set_page"`.
    """
    contact_id = _s4_contact_id("write")
    db = session_factory()
    codes = _s4_seed_seven_taps(db)
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_cert_parser_output())
    stub_access()

    result = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-1a", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert result.status == "done", result.error

    variables = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables.get("selection_context") == "set_page", variables

    carry = variables.get("last_result_set")
    assert isinstance(carry, dict), carry
    assert carry.get("kind") == "set_page", carry
    ids = carry.get("qualifying_ids") or []
    assert len(ids) == 7, carry
    assert carry.get("offset") == 5, carry
    assert carry.get("qualifying_total") == 7, carry
    assert carry.get("require") == {"certificate": True}, carry
    assert carry.get("set_noun") == "taps", carry
    assert carry.get("domain") == "product_attachment", carry


def test_more_returns_the_next_page_without_resolving(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1317: the next 5 (here, the remaining 2 of 7) of the SAME described set, no
    second resolver call.

    RED: turn 2's reply is not "7 taps have certificates. Showing 6 to 7." today -
    there is no bare-word arm reading "more" under a carried `set_page` context at all
    (grepped `output_exchange.py`, `contracts.py`, `compile_state.py`, `pending.py`:
    absent), so the turn falls through the ordinary ladder as an unrelated business
    query with no domain, no intent and no entities.
    """
    contact_id = _s4_contact_id("page")
    db = session_factory()
    codes = _s4_seed_seven_taps(db)
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    resolve_calls: dict[str, int] = {}
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_cert_parser_output())
    stub_access()
    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-2a", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    reply1 = (turn1.reply or {}).get("text") or ""
    shown1 = _s4_codes_in(reply1)

    # Turn 2's resolver is swapped for a COUNTING stub, never the real one: a call is
    # recorded rather than crashing the turn, so the reply-text assertion below is
    # still the primary, legible red reason.
    from app.services.chatbot.lanes.business.services import ResolveGateServices

    monkeypatch.setattr(
        engine_mod.business_services,
        "production_services",
        lambda db, *, space_id=None: ResolveGateServices(
            access_types=lambda **_: [],
            resolve_entity=_s4_counting_resolve_entity(resolve_calls),
            probe=lambda **_: None,
        ),
    )
    stub_parser(_s4_bare_parser_output())
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-2b", text="more"),
        session_factory=session_factory,
    )

    reply2 = (turn2.reply or {}).get("text") or ""
    lines2 = reply2.splitlines()
    assert lines2 and lines2[0] == "7 taps have certificates. Showing 6 to 7.", reply2

    shown2 = _s4_codes_in(reply2)
    assert shown2 == (set(codes) - shown1), (shown1, shown2, codes)
    assert resolve_calls.get("n", 0) == 0, "the resolver ran on a 'more' continuation turn"


def test_more_past_the_end_says_that_was_all(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1317: past the end of the carried set, "That was all <N> <noun>." and the
    carry is cleared - seeded directly at "already on the last page" (offset ==
    qualifying_total) so this test's own red reason is the "past the end" arm alone,
    not also whatever turn 1 / turn 2 do or do not carry yet (both untested here).

    RED: no code reads a `set_page` carry at all, so the reply is not "That was all 7
    taps." and `selection_context` is left exactly as seeded ("set_page"), never
    cleared.
    """
    contact_id = _s4_contact_id("end")
    db = session_factory()
    codes = _s4_seed_seven_taps(db)

    from app.models.product import Product

    ids = [row.id for row in db.query(Product).filter(Product.product_code.in_(codes)).all()]
    assert len(ids) == 7

    _s4_seed_contact(
        session_factory,
        contact_id=contact_id,
        session_vars={
            "variables": {
                "domain_hint": "product_attachment",
                "selection_context": "set_page",
                "last_result_set": {
                    "kind": "set_page",
                    "qualifying_ids": ids,
                    "offset": 7,
                    "qualifying_total": 7,
                    "require": {"certificate": True},
                    "set_noun": "taps",
                    "domain": "product_attachment",
                    "tool": "crm_master_product_attachments_list",
                },
            }
        },
    )

    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_counting_resolve_entity({}),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_bare_parser_output())
    stub_access()

    result = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-3a", text="more"),
        session_factory=session_factory,
    )

    reply = (result.reply or {}).get("text") or ""
    assert reply.strip() == "That was all 7 taps.", reply

    variables = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables.get("selection_context") != "set_page", variables


@pytest.mark.parametrize(
    "text, should_page",
    [
        ("more", True),
        ("next", True),
        ("lagi", True),
        ("more please", True),
        ("show more", True),
        ("more taps with stock please and thanks", False),
        ("SRTWC286", False),
    ],
)
def test_more_words_are_recognised_and_long_messages_are_not(
    session_factory, stub_parser, stub_access, monkeypatch, text, should_page
):
    """AC-1317: "more" / "next" / "lagi" recognised standalone or in a short (<= four
    word) reply; a longer message or an ordinary code is left to the normal ladder -
    the carry must not fire on a message that merely CONTAINS the word "more" as part
    of a different, longer question.

    RED (every case): no bare-word arm exists, so a paging case never renders "Showing
    6 to 7." and - the part that would make a non-paging case pass for the wrong
    reason if skipped - the two non-paging cases must ALSO not show it, which holds
    trivially today (nothing pages at all) but is asserted explicitly so a coder who
    wires the WORD LIST without the LENGTH GUARD cannot pass this file by accident.
    """
    contact_id = _s4_contact_id("word")
    db = session_factory()
    codes = _s4_seed_seven_taps(db)

    from app.models.product import Product

    ids = [row.id for row in db.query(Product).filter(Product.product_code.in_(codes)).all()]

    _s4_seed_contact(
        session_factory,
        contact_id=contact_id,
        session_vars={
            "variables": {
                "domain_hint": "product_attachment",
                "selection_context": "set_page",
                "last_result_set": {
                    "kind": "set_page",
                    "qualifying_ids": ids,
                    "offset": 5,
                    "qualifying_total": 7,
                    "require": {"certificate": True},
                    "set_noun": "taps",
                    "domain": "product_attachment",
                    "tool": "crm_master_product_attachments_list",
                },
            }
        },
    )

    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_counting_resolve_entity({}),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_bare_parser_output())
    stub_access()

    result = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id=f"ZZT-s4-word-{abs(hash(text))}", text=text),
        session_factory=session_factory,
    )
    reply = (result.reply or {}).get("text") or ""

    if should_page:
        # AC-1317: a "more" turn returns the next five PRODUCTS WITH their
        # blocks under the header, not the header alone -
        # `test_more_returns_the_next_page_without_resolving` already proves
        # that shape; this test's own job is which WORDS trigger paging at
        # all, so it checks the header line only (captain's ruling on the
        # coder's dispute, 11 Sep 2026).
        lines = reply.splitlines()
        assert lines and lines[0] == "7 taps have certificates. Showing 6 to 7.", reply
    else:
        assert "Showing" not in reply, reply


def test_a_set_answer_with_five_or_fewer_leaves_no_carry(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1317: when every qualifying product already fit on the first page (D5's
    header already omits "Showing" for this world, per S3's own
    `test_set_answer_header_omits_showing_when_all_fit`), there is nothing to page -
    the carry must not arm, and a following "more" answers as an ordinary turn.

    NOT RED TODAY - flagged rather than hidden. Every assertion in this test already
    holds with zero of S4 built: the header is right (S3 is green) and
    `selection_context` is never "set_page" for ANY answer yet, paged or not, so both
    halves pass vacuously rather than for the AC's own reason ("3 fits on one page so
    nothing carries"). It stays in the suite as the regression guard named in AC-1317
    (a coder who arms the carry unconditionally on every set answer, instead of gating
    it on `qualifying_total > 5`, breaks it) - the captain should read this one as a
    forward guard, not as red-run evidence.
    """
    contact_id = _s4_contact_id("small")
    db = session_factory()
    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    for _ in range(3):
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        _certificate_for(db, product_id=product.id)
    db.commit()
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_cert_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-5a", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    reply1 = (turn1.reply or {}).get("text") or ""
    assert reply1.splitlines()[0] == "3 taps have certificates.", reply1

    variables = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables.get("selection_context") != "set_page", variables

    stub_parser(_s4_bare_parser_output())
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-5b", text="more"),
        session_factory=session_factory,
    )
    reply2 = (turn2.reply or {}).get("text") or ""
    assert "Showing" not in reply2, reply2


def test_domain_change_clears_the_set_page_carry(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1317: `topic.changed` clears the carry exactly as it clears every other
    roster kind - a following stock turn for a real product code is a domain change
    (`product_attachment` -> `inventory`), per `topic.changed`'s own truth table.

    RED: `selection_context` is never "set_page" to begin with (same S4 gap every
    other test names), so this assertion cannot currently distinguish "cleared by a
    domain change" from "never armed" - it is included anyway because it is the
    correct standing regression once the carry exists, and it fails FIRST on the
    precondition (`variables.get("selection_context")` after turn 1 is not
    "set_page"), which is itself accurate: the precondition really is missing today.
    """
    contact_id = _s4_contact_id("domain")
    db = session_factory()
    codes = _s4_seed_seven_taps(db)

    from app.models.inventory import Stock, Warehouse
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    category = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    stock_product = Product(
        id=str(uuid.uuid4()),
        product_code="SRTWC286",
        product_name="SRTWC286",
        description="SRTWC286 CHROME BASIN TAP",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
        is_active=True,
    )
    db.add(stock_product)
    db.flush()
    warehouse = Warehouse(
        id=str(uuid.uuid4()), warehouse_code=unique_code("WH")[:50], warehouse_name="ZZT Warehouse", is_active=True
    )
    db.add(warehouse)
    db.flush()
    db.add(
        Stock(
            id=str(uuid.uuid4()),
            product_id=stock_product.id,
            warehouse_id=warehouse.id,
            quantity_on_hand=10,
            quantity_reserved=0,
        )
    )
    db.commit()

    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    stub_parser(_s4_cert_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-6a", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    variables_after_1 = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables_after_1.get("selection_context") == "set_page", variables_after_1

    from tests.chatbot.test_engine import _parser_output

    from app.services.chatbot.lanes.business.services import FetchServices as _FetchServices

    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: _FetchServices(mcp_call=_stock_fake_call_tool(db))
    )
    stub_parser(
        _parser_output(
            intent_hint="check_stock",
            domain_hint="inventory",
            match_mode="and",
            entities=[
                {
                    "raw": "SRTWC286",
                    "hint": "product",
                    "canonical_code": "SRTWC286",
                    "current_message": True,
                    "confident": True,
                }
            ],
        )
    )
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-6b", text="SRTWC286 stock"),
        session_factory=session_factory,
    )
    assert turn2.status == "done", turn2.error

    variables_after_2 = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables_after_2.get("selection_context") != "set_page", variables_after_2


def test_ids_are_capped_at_200_and_the_reply_asks_to_narrow(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1317: the carried id list is capped (named `SET_PAGE_ID_CAP` in
    `answer.py` per the plan) even though the true count keeps counting past it; a
    "more" that has exhausted the CAPPED list (but not the true count) asks to narrow
    rather than claiming "that was all".

    Seeded 12, not 206 (the plan's own escape hatch: "if seeding 206 is too slow, seed
    12 and assert the cap through a monkeypatched cap constant"). The cap is
    monkeypatched to 10 (`raising=False`: the attribute does not exist yet, so a
    strict `setattr` would raise `AttributeError` before the real red reason - a
    missing feature, not a missing constant - ever ran) so a 12-vs-10 gap is
    provable regardless of whether the coder's constant is named exactly this.

    RED, two independent reasons in one test, both named because either alone would
    look like a wrong test rather than a wrong build: (1) nothing writes a
    `qualifying_ids` cap today (there is no `set_page` write at all), so turn 1's own
    carry never exists to inspect; (2) the "narrow" reply for a carry seeded already
    AT the cap does not exist either (no bare-word arm reads it).
    """
    contact_id = _s4_contact_id("cap")
    db = session_factory()
    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    codes = []
    for _ in range(12):
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        _certificate_for(db, product_id=product.id)
        codes.append(product.product_code)
    db.commit()

    from app.services.chatbot.lanes.business import answer as answer_mod

    monkeypatch.setattr(answer_mod, "SET_PAGE_ID_CAP", 10, raising=False)

    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_cert_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-s4-7a", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    reply1 = (turn1.reply or {}).get("text") or ""
    assert reply1.splitlines()[0] == "12 taps have certificates. Showing 5.", reply1

    variables = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    carry = variables.get("last_result_set")
    assert isinstance(carry, dict), carry
    assert isinstance(carry.get("qualifying_ids"), list), carry
    assert len(carry["qualifying_ids"]) == 10, carry
    assert carry.get("qualifying_total") == 12, carry

    # Phase B: seeded directly AT the cap (offset == the capped list's own length, 10),
    # decoupled from whether phase A's own write half works yet - this isolates the
    # "narrow" arm's own red reason from phase A's.
    from app.models.product import Product

    ids = [row.id for row in db.query(Product).filter(Product.product_code.in_(codes)).all()][:10]
    contact_id_b = _s4_contact_id("cap-b")
    _s4_seed_contact(
        session_factory,
        contact_id=contact_id_b,
        session_vars={
            "variables": {
                "domain_hint": "product_attachment",
                "selection_context": "set_page",
                "last_result_set": {
                    "kind": "set_page",
                    "qualifying_ids": ids,
                    "offset": 10,
                    "qualifying_total": 12,
                    "require": {"certificate": True},
                    "set_noun": "taps",
                    "domain": "product_attachment",
                    "tool": "crm_master_product_attachments_list",
                },
            }
        },
    )
    stub_parser(_s4_bare_parser_output())
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id_b, message_id="ZZT-s4-7b", text="more"),
        session_factory=session_factory,
    )
    reply2 = (turn2.reply or {}).get("text") or ""
    assert "narrow" in reply2.lower(), reply2

    variables_b = _s4_session_vars(session_factory, contact_id_b).get("variables") or {}
    assert variables_b.get("selection_context") != "set_page", variables_b


# --------------------------------------------------------------------------- #
# Fix round (console findings, 11 Sep 2026, committed 3779b32d6) - AC-1316,     #
# AC-1320: a "category" entity the head retypes into an unresolved PRODUCT      #
# token must still yield a set answer, never fall through to a clarify; and     #
# a term with genuinely NO nearest class-label candidate must offer the three   #
# most common labels, never the empty "Did you mean the product types I        #
# know?".                                                                       #
# --------------------------------------------------------------------------- #


def test_category_entity_yields_a_set_answer_not_a_clarify():
    """AC-1316/AC-1320: world of 3 certified class-Tap products and 1 certified
    class-Wash-Basin product (product codes carry NO literal "tap"/"basin"
    substring, so a pass here cannot be the accidental LOOKUP-by-code-substring
    shortcut S3's own module banner warns about - the scoping has to come from
    the class binding). Message "which tap has cert" with an EXPLICIT product
    entity {"hint": "product", "raw": "tap"} that will not resolve (the shape
    the head produces when it retypes a parser "category" entity) plus the
    attachment_type entity carrying a `canonical_code` - reply opens "3 taps
    have certificates." and never says "I don't know" anywhere.

    NOT RED as constructed - measured directly against this exact world and
    entity shape (probe dropped after confirming): the reply already reads "3
    taps have certificates." with no clarify text. Reported to the captain as
    a finding rather than forced: this council finding may already be covered
    by the existing C2/C4 wiring, or it needs a shape this construction does
    not reach. Kept as the AC-1316/AC-1320 regression guard the captain named.
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        from app.models.product import Product
        from app.services.product_spec_derivation import derive_for_code
        from tests._pg_fixture import unique_code

        def _certified(description: str) -> Product:
            code = unique_code("ZQ")[:20]
            product = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                description=f"{unique_code('ZQ')[:10]} {description}",
                category_id=category_id,
                base_uom_id=uom_id,
                list_price=10,
                is_active=True,
            )
            db.add(product)
            db.flush()
            derive_for_code(db, code)
            _certificate_for(db, product_id=product.id)
            return product

        for _ in range(3):
            _certified("CHROME TAP")
        _certified("WHITE WASH BASIN")
        db.commit()

        ctx = {
            "text": {"message": {"message": {"text": "which tap has cert"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_product_attachment",
                    "domain_hint": "product_attachment",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [
                        {"raw": "tap", "hint": "product"},
                        {"raw": "cert", "hint": "attachment_type", "canonical_code": "certificate"},
                    ],
                }
            },
        }
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))
        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "3 taps have certificates.", reply
    assert "i don't know" not in reply.lower(), reply


def test_clarify_with_no_candidate_offers_common_product_types():
    """AC-1320: a term with NO nearest class-label candidate at all ("zzqx" -
    `difflib.get_close_matches` against Tap / Wash Basin / Water Closet at
    cutoff 0.6 returns nothing, and no exact word match either) must clarify
    with "Try a product type such as <a>, <b>, <c>." naming the world's own
    common class labels, never the contentless "Did you mean the product
    types I know?".

    RED: `not_found_error_message` (`answer.py`) has exactly one branch for
    `qualifying_total == 0` with a non-empty `unrecognized_terms` - when
    `predicate.suggestions` is empty it falls back to the literal string "the
    product types I know" ("Did you mean the product types I know?"); no
    "Try a product type such as" text exists anywhere in the file.
    """
    with blank_session() as db:
        # A term nothing binds to ("zzqx") falls through every probe to the last-
        # resort trigram fallback across EVERY entity type, including transporters
        # - whose `similarity()` call needs `pg_trgm`, installed in `public`.
        # `blank_session()`'s own `search_path` deliberately excludes `public` (so
        # raw SQL cannot leak onto the real tables); appending it here is scoped to
        # THIS test's `SET LOCAL` and never widens what any other test can reach.
        from sqlalchemy import text as sa_text

        current_search_path = db.execute(sa_text("SHOW search_path")).scalar()
        db.execute(sa_text(f"SET LOCAL search_path TO {current_search_path}, public"))

        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        from app.models.product import Product
        from app.services.product_spec_derivation import derive_for_code
        from tests._pg_fixture import unique_code

        def _seeded(description: str) -> Product:
            code = unique_code("ZQ")[:20]
            product = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                description=f"{unique_code('ZQ')[:10]} {description}",
                category_id=category_id,
                base_uom_id=uom_id,
                list_price=10,
                is_active=True,
            )
            db.add(product)
            db.flush()
            derive_for_code(db, code)
            _certificate_for(db, product_id=product.id)
            return product

        _seeded("CHROME TAP")
        _seeded("WHITE WASH BASIN")
        _seeded("AUTO WATER CLOSET")
        db.commit()

        from app.services.chatbot.lanes.business import resolve_gate
        from app.services.chatbot.lanes.business.answer import not_found_error_message
        from app.services.chatbot.lanes.business.services import ResolveGateServices
        from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
        from app.config import settings

        def resolve_entity(body: dict) -> dict:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(ResolveReferenceRequest(**payload), current_user=principal, db=db)

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = {
            "text": {"message": {"message": {"text": "which zzqx has cert"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_product_attachment",
                    "domain_hint": "product_attachment",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [
                        {"raw": "zzqx", "hint": "product"},
                        {"raw": "cert", "hint": "attachment_type"},
                    ],
                }
            },
        }
        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert "I don't know 'zzqx' as a product type" in text, text
    assert "Try a product type such as" in text, text
    for label in ("tap", "wash basin", "water closet"):
        assert label in text.lower(), text
    assert "Did you mean the product types I know?" not in text, text


# --------------------------------------------------------------------------- #
# Security review (11 Sep 2026, PLAN-attribute-first-asks.md SEC-B1/N1,       #
# AC-1333/AC-1336) - full `engine.run_turn` harness (S4 section above).       #
# --------------------------------------------------------------------------- #


def _sec_promo_fake_call_tool(db, calls: list[dict[str, Any]]):
    """Records every MCP call (name, args) so a test can inspect the
    `access_levels` argument the fetch step actually sent, and returns a
    plausible promotion-products envelope keyed off whatever `product_ids`
    the call carried."""
    import json

    from app.models.marketing import PromotionProduct
    from app.models.product import Product

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        calls.append({"name": name, "args": dict(args)})
        product_ids = list(args.get("product_ids") or [])
        rows = (
            db.query(Product)
            .join(PromotionProduct, PromotionProduct.product_id == Product.id)
            .filter(Product.id.in_(product_ids))
            .order_by(Product.product_code)
            .distinct()
            .all()
        )
        items = [
            {
                "title": p.product_code,
                "fields": [{"key": "product_code", "label": "Product Code", "value": p.product_code}],
                "flags": {},
            }
            for p in rows
        ]
        return json.dumps(
            {
                "result_type": "promotion_products",
                "intro": "Promotions found.",
                "items": items,
                "has_result": bool(items),
            }
        )

    return fake_call_tool


def _sec_seed_seven_promo_taps(db, *, access_levels: list[str]) -> list[str]:
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct

    codes: list[str] = []
    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    for _ in range(7):
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        promo = Promotion(
            id=str(uuid.uuid4()),
            description=f"ZZT promo {uuid.uuid4().hex[:6]}",
            is_active=True,
            access_levels=access_levels,
        )
        db.add(promo)
        db.flush()
        group = PromotionGroup(id=uuid.uuid4(), promotion_id=promo.id, group_name="G")
        db.add(group)
        db.flush()
        db.add(
            PromotionProduct(
                id=str(uuid.uuid4()), promotion_id=promo.id, promotion_group_id=group.id, product_id=product.id
            )
        )
        codes.append(product.product_code)
    db.commit()
    return codes


def _sec_wire_promo_engine(session_factory, monkeypatch, *, resolve_entity, fetch_mcp_call, access_types):
    from app.models.user import SystemSetting
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices
    from tests.chatbot.conftest import set_chatbot_switches

    set_chatbot_switches(session_factory, business_lane=True, ordering=True)
    db = session_factory()
    setting = db.query(SystemSetting).first()
    setting.chatbot_completed_lanes = ["business_query", "check_promotion"]
    db.commit()

    bundle = ResolveGateServices(access_types=access_types, resolve_entity=resolve_entity, probe=lambda **_: None)
    monkeypatch.setattr(
        engine_mod.business_services, "production_services", lambda db, *, space_id=None: bundle
    )
    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: FetchServices(mcp_call=fetch_mcp_call)
    )
    monkeypatch.setattr(
        engine_mod.business_services, "answer_services_for", lambda session_factory: _s4_no_probe_answer_services()
    )
    return engine_mod


def _sec_promo_parser_output(**overrides: Any):
    from tests.chatbot.test_engine import _parser_output

    base = dict(
        intent_hint="check_promotion",
        domain_hint="promotion",
        match_mode="and",
        entities=[
            {"raw": "tap", "hint": "category", "canonical_code": None, "current_message": True, "confident": True}
        ],
    )
    base.update(overrides)
    return _parser_output(**base)


def test_more_page_carries_the_contacts_access_levels(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1333/SEC-B1: a "more" page's promotion tool call must carry the SAME
    (non-empty) access_levels turn 1's own fetch used - never `[]` - or the
    tier filter silently disappears from the page and the customer can be
    shown promotions their tier cannot see.

    World: a contact holding ONE access type ("Sorento Dealer"), seven class-Tap
    products each in its own active promotion open to that same tier.

    RED: `_set_page_reply`'s "next page" arm stamps `tier_gate: None`
    unconditionally and only overrides the mutated parser's `domain_hint`, never
    its `access_levels` - so `_fetch_semantic_input` (no tier_gate to read
    `access_levels_recomposed` from) falls to the bare "more" parser output's own
    `access_levels`, which is `[]`. Turn 1's tool call carries `["Sorento
    Dealer"]` (from `tier_gate.access_levels_recomposed`); the page turn's carries
    `[]`.
    """
    from app.models.access import ContactAccessType

    contact_id = _s4_contact_id("secpromo")
    db = session_factory()
    db.add(ContactAccessType(code="sorento_dealer", name="Sorento Dealer"))
    db.commit()
    codes = _sec_seed_seven_promo_taps(db, access_levels=["sorento_dealer"])
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    calls: list[dict[str, Any]] = []
    engine_mod = _sec_wire_promo_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_sec_promo_fake_call_tool(db, calls),
        access_types=lambda **_: [{"name": "Sorento Dealer"}],
    )
    stub_parser(_sec_promo_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-sec-1a", text="which tap has promo"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    assert calls, "no MCP call recorded on turn 1"
    turn1_access_levels = calls[-1]["args"].get("access_levels")
    assert turn1_access_levels, ("turn 1's own tool call must carry a non-empty access_levels", turn1_access_levels)

    calls.clear()
    stub_parser(_s4_bare_parser_output())
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-sec-1b", text="more"),
        session_factory=session_factory,
    )
    assert turn2.status == "done", turn2.error
    assert calls, "no MCP call recorded on the 'more' turn"
    turn2_access_levels = calls[-1]["args"].get("access_levels")
    assert turn2_access_levels == turn1_access_levels, (turn1_access_levels, turn2_access_levels)
    assert turn2_access_levels != [], turn2_access_levels


def test_tier_ask_turn_does_not_arm_the_carry(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1333: a promotion turn the contact's OWN multi-tier entitlement forces
    to the existing tier-ask flow ("Which access level do you need ...") must
    arm NOTHING - a following "more" is not a paged reply.

    World: a contact holding TWO tiers of the SAME brand ("Sorento Dealer",
    "Sorento Office") - `needs_tier_ask` returns True for more than one held
    tier - over the same 7-tap promotion world.

    RED: the set_page carry is armed off `gate.predicate` alone (a predicate
    block is present regardless of whether the fetch actually rendered a set
    answer or hit the tier-ask arm first), so this turn wrongly arms
    `selection_context = "set_page"` even though nothing was ever shown.
    """
    contact_id = _s4_contact_id("secask")
    db = session_factory()
    codes = _sec_seed_seven_promo_taps(db, access_levels=["sorento_dealer"])
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    calls: list[dict[str, Any]] = []
    engine_mod = _sec_wire_promo_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_sec_promo_fake_call_tool(db, calls),
        access_types=lambda **_: [{"name": "Sorento Dealer"}, {"name": "Sorento Office"}],
    )
    stub_parser(_sec_promo_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-sec-2a", text="which tap has promo"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error

    variables = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables.get("selection_context") != "set_page", variables

    resolve_calls: dict[str, int] = {}
    from app.services.chatbot.lanes.business.services import ResolveGateServices

    monkeypatch.setattr(
        engine_mod.business_services,
        "production_services",
        lambda db, *, space_id=None: ResolveGateServices(
            access_types=lambda **_: [{"name": "Sorento Dealer"}, {"name": "Sorento Office"}],
            resolve_entity=_s4_counting_resolve_entity(resolve_calls),
            probe=lambda **_: None,
        ),
    )
    stub_parser(_s4_bare_parser_output())
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-sec-2b", text="more"),
        session_factory=session_factory,
    )
    reply2 = (turn2.reply or {}).get("text") or ""
    assert "Showing" not in reply2, reply2
    assert not reply2.lower().startswith("7 taps"), reply2


def test_carry_clears_on_a_non_page_business_answer(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1336/SEC-N1: the set_page carry clears on ANY business answer that is
    not itself a page - not only on a domain change - so a following unrelated
    turn never mistakenly pages a stale set, and a fresh set answer re-arms
    cleanly (offset 5, not compounded on old state).

    Turn 1: "which tap has cert" -> set answer, carry armed.
    Turn 2: "SRTWC1 stock" (a forward, code-exact stock turn) -> `selection_
    context` must no longer be "set_page".
    Turn 3: "which tap has cert" again -> re-armed, `offset == 5`.

    GREEN today under this exact construction, measured directly: turn 2 IS a
    domain change (product_attachment -> inventory), and clearing on a domain
    change already works (`test_domain_change_clears_the_set_page_carry`,
    unchanged by this security round). SEC-N1's own gap is narrower - the SAME
    domain, a non-page answer - which this turn 2 does not exercise. Kept as
    the AC-1336 regression guard (three turns, re-arm at a fresh offset of 5),
    reported honestly per this file's own "CONTRACT CONTRADICTION" convention
    rather than forced red.
    """
    contact_id = _s4_contact_id("secclear")
    db = session_factory()
    codes = _s4_seed_seven_taps(db)

    from app.models.inventory import Stock, Warehouse
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    category = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    stock_product = Product(
        id=str(uuid.uuid4()),
        product_code="ZZTWC1",
        product_name="ZZTWC1",
        description="ZZTWC1 SORENTO WATER CLOSET",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=10,
        is_active=True,
    )
    db.add(stock_product)
    db.flush()
    warehouse = Warehouse(
        id=str(uuid.uuid4()), warehouse_code=unique_code("WH")[:50], warehouse_name="ZZT Warehouse", is_active=True
    )
    db.add(warehouse)
    db.flush()
    db.add(
        Stock(
            id=str(uuid.uuid4()),
            product_id=stock_product.id,
            warehouse_id=warehouse.id,
            quantity_on_hand=10,
            quantity_reserved=0,
        )
    )
    db.commit()

    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    stub_parser(_s4_cert_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-sec-3a", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    variables_after_1 = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables_after_1.get("selection_context") == "set_page", variables_after_1

    from tests.chatbot.test_engine import _parser_output as _plain_parser_output
    from app.services.chatbot.lanes.business.services import FetchServices as _FetchServices

    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: _FetchServices(mcp_call=_stock_fake_call_tool(db))
    )
    stub_parser(
        _plain_parser_output(
            intent_hint="check_stock",
            domain_hint="inventory",
            match_mode="and",
            entities=[
                {
                    "raw": "ZZTWC1",
                    "hint": "product",
                    "canonical_code": "ZZTWC1",
                    "current_message": True,
                    "confident": True,
                }
            ],
        )
    )
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-sec-3b", text="ZZTWC1 stock"),
        session_factory=session_factory,
    )
    assert turn2.status == "done", turn2.error
    variables_after_2 = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables_after_2.get("selection_context") != "set_page", variables_after_2

    monkeypatch.setattr(
        engine_mod.business_services, "fetch_services", lambda db: _FetchServices(mcp_call=_cert_fake_call_tool(db))
    )
    stub_parser(_s4_cert_parser_output())
    turn3 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-sec-3c", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn3.status == "done", turn3.error
    variables_after_3 = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables_after_3.get("selection_context") == "set_page", variables_after_3
    carry_after_3 = variables_after_3.get("last_result_set") or {}
    assert carry_after_3.get("offset") == 5, carry_after_3


# --------------------------------------------------------------------------- #
# Correctness review (11 Sep 2026, PLAN-attribute-first-asks.md REV-S3,        #
# AC-1337) - two hand-synced copies across the module boundary                #
# (`references.py` sits outside `app.services.chatbot`, so it keeps its own    #
# copies rather than importing across it - see that file's own docstrings).   #
# --------------------------------------------------------------------------- #


def test_page_cap_and_cert_regex_are_pinned():
    """AC-1337/REV-S3: `answer.SET_PAGE_ID_CAP` and `references._SET_PAGE_ID_CAP`
    must stay equal, and `references._CERT_WORD_RE` must stay the same pattern
    as `output_exchange._CERT_RE` - both are hand-synced copies across the
    module boundary (`references.py`'s own docstrings say so), so a value
    that drifts silently under-pages a "more" carry or lets a cert-shaped word
    slip past the described-set stripping.

    Green today - both copies were kept in lockstep by hand at write time.
    Kept as the regression guard the drift would otherwise need a console
    turn to surface.
    """
    from app.api.v1.system import references
    from app.services.chatbot.head.output_exchange import _CERT_RE
    from app.services.chatbot.lanes.business import answer

    assert answer.SET_PAGE_ID_CAP == references._SET_PAGE_ID_CAP
    assert references._CERT_WORD_RE.pattern == _CERT_RE.pattern


# --------------------------------------------------------------------------- #
# Correctness review - REV-N1/AC-1337: `is_more_reply` must accept only the    #
# fixed paging phrases, never any short message merely containing the word.   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text, expected",
    [
        ("more", True),
        ("More!", True),
        ("next", True),
        ("lagi", True),
        ("more please", True),
        ("show more", True),
        ("next 5", True),
        ("next five", True),
        ("more 5", True),
        ("no more", False),
        ("next week?", False),
        ("more taps with stock", False),
        ("SRTWC286", False),
    ],
)
def test_is_more_reply_accepts_only_paging_phrases(text, expected):
    """AC-1337/REV-N1: `is_more_reply` must equal one of the fixed paging
    phrases (more, next, lagi, more please, show more, next 5, next five,
    "more"/"next"/"lagi" followed by a single number), lower-cased and
    stripped of punctuation - never any short message that merely CONTAINS
    one of those words.

    RED for "no more" and "next week?": today's `_MORE_WORD_RE` is a bare
    substring/word search (`\\b(more|next|lagi)\\b`) over a message capped
    only at 4 words, so both match and wrongly page a carry that was never
    asked to continue.
    """
    from app.services.chatbot.lanes.business.answer import is_more_reply

    assert is_more_reply(text) is expected, text


# --------------------------------------------------------------------------- #
# Correctness review - REV-N2/AC-1337: irregular pluralisation, and the        #
# header's singular is the class label itself, never a stripped plural.       #
# --------------------------------------------------------------------------- #


def test_set_noun_for_irregular_plurals():
    """AC-1337/REV-N2: `set_noun_for` must pluralise via a small irregular map
    (accessory -> accessories) before falling back to a bare "+s", and
    `build_set_header`'s own singular is the class label ITSELF, never a
    plural with the trailing "s" stripped off - the naive strip is what
    `fetch.py`'s own call site does today ("bathroom accessories"[:-1] ->
    "bathroom accessorie", never the real singular "bathroom accessory").

    RED (first assertion only): `set_noun_for` today does
    `f"{labels[0].strip().lower()}s"` unconditionally, so "Bathroom Accessory"
    becomes "bathroom accessorys", not "bathroom accessories". "Jacuzzi" -> "s"
    already happens to spell "jacuzzis" correctly with the naive rule, so that
    assertion is not itself red - kept because AC-1337 names it explicitly, and
    a future irregular-map refactor must not silently break it.

    The third assertion calls `build_set_header` directly with the class label
    as `set_noun` (bypassing `fetch.py`'s own singular-stripping call site
    entirely) - `build_set_header` itself has no pluralisation logic of its
    own, so this is GREEN today; it pins the CONTRACT `fetch.py`'s call site
    must honour once its own "-1 char" strip is replaced with the real
    singular.
    """
    from app.services.chatbot.lanes.business.answer import build_set_header, set_noun_for

    assert set_noun_for(["Bathroom Accessory"]) == "bathroom accessories"
    assert set_noun_for(["Jacuzzi"]) == "jacuzzis"
    assert (
        build_set_header(1, 1, "bathroom accessory", {"stock": True})
        == "1 bathroom accessory has stock."
    )


# --------------------------------------------------------------------------- #
# Fix round 3 - R19/AC-1343 (REV-S1 re-check): the set_page carry survives     #
# ONLY a page continuation - a same-domain non-page answer and a same-domain  #
# zero-qualifying clarify both clear it, so "more" afterwards answers the     #
# no-set copy; a rendered set answer re-arms it fresh.                        #
# --------------------------------------------------------------------------- #


def test_fresh_set_answer_rearms_the_carry_with_its_own_set(session_factory, stub_parser, stub_access, monkeypatch):
    """AC-1343/R19: a second, SAME-DOMAIN set answer for a DIFFERENT class
    ("which basin has cert" right after "which tap has cert") must re-arm the
    carry with the basin set alone - never merge with or retain the old tap
    identity.

    Likely GREEN today, measured directly: `_set_page_carry`'s fresh arm
    writes a brand-new dict (no `**prev_carry` spread, unlike its own
    page-continuation arm), so a second genuine RENDER already replaces the
    carry wholesale. Kept as the AC-1343 regression guard the fix must not
    break while closing the (different) clarify gap below, reported honestly
    rather than forced red.
    """
    contact_id = _s4_contact_id("r19rearm")
    db = session_factory()
    tap_codes = _s4_seed_seven_taps(db)

    from app.models.product import Product, ProductCategory, UnitOfMeasure

    category = db.query(ProductCategory).first()
    uom = db.query(UnitOfMeasure).first()
    # The bare word "basin" only resolves to class "Wash Basin" through a
    # category coded `<brand>-WB`'s own `search_synonyms` - a plain product's
    # class derivation (from its description) is unaffected by which category
    # it sits under, so this is vocabulary-only, not a category reassignment.
    _wash_basin_category(db)
    basin_codes: list[str] = []
    for _ in range(6):
        product = _basin_product(db, category_id=category.id, uom_id=uom.id)
        _certificate_for(db, product_id=product.id)
        basin_codes.append(product.product_code)
    db.commit()

    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_cert_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-r19r-1", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error

    stub_parser(
        _s4_cert_parser_output(
            entities=[
                {
                    "raw": "basin",
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
                {
                    "raw": "cert",
                    "hint": "attachment_type",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
            ]
        )
    )
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-r19r-2", text="which basin has cert"),
        session_factory=session_factory,
    )
    assert turn2.status == "done", turn2.error

    variables = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables.get("selection_context") == "set_page", variables
    carry = variables.get("last_result_set") or {}
    ids = set(carry.get("qualifying_ids") or [])

    basin_ids = {row.id for row in db.query(Product).filter(Product.product_code.in_(basin_codes)).all()}
    tap_ids = {row.id for row in db.query(Product).filter(Product.product_code.in_(tap_codes)).all()}

    assert ids == basin_ids, (ids, basin_ids, tap_ids)
    assert not (ids & tap_ids), (ids, tap_ids)


def test_carry_clears_on_a_same_domain_zero_qualifying_clarify(
    session_factory, stub_parser, stub_access, monkeypatch
):
    """AC-1343/R19: after "which tap has cert", a SAME-DOMAIN clarify that
    renders nothing (AC-1320's own zero-qualifying-with-unrecognized-terms
    shape) must clear the set_page carry - not leave the tap set armed for a
    later, unrelated "more" to page through under the wrong header.

    Turn 1: "which tap has cert" -> set answer, carry armed (7 taps, offset 5).
    Turn 2: "which flurbish has cert" -> AC-1320 clarify (qualifying_total 0,
    unrecognized_terms carrying "flurbish"), same domain (product_attachment),
    NOTHING rendered, no roster - `selection_context` must no longer be
    "set_page".
    Turn 3: "more" - AC-1343 (amended): with the carry cleared, `head/route.py`'s
    `is_set_page_more_reply` (gated on `prev.selection_context == "set_page"`)
    is false, so the turn takes the SAME ordinary low-signal route a bare
    "more" with no prior set takes today - never `resolve_gate._set_page_reply`
    at all. The harness registers "low_signal" in `chatbot_completed_lanes` so
    this turn completes in the CRM rather than hitting the S7 hard refusal for
    an un-registered lane, and its clarifier call is stubbed so no live model
    call runs.

    RED: `_offer_carry`'s set_page arm only clears on `answered or topic.
    changed(...)` - turn 2 is neither answered (nothing was ever rendered) nor
    a domain change (still product_attachment), so `variables["selection_
    context"]` is restored to "set_page" off `prev` and turn 3's bare "more"
    is wrongly routed as a page continuation, paging the STALE tap set under
    the old header.
    """
    contact_id = _s4_contact_id("r19clear")
    db = session_factory()
    codes = _s4_seed_seven_taps(db)
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_cert_parser_output())
    stub_access()

    turn1 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-r19-1", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn1.status == "done", turn1.error
    variables_after_1 = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables_after_1.get("selection_context") == "set_page", variables_after_1

    stub_parser(
        _s4_cert_parser_output(
            entities=[
                {
                    "raw": "flurbish",
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
                {
                    "raw": "cert",
                    "hint": "attachment_type",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                },
            ]
        )
    )
    turn2 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-r19-2", text="which flurbish has cert"),
        session_factory=session_factory,
    )
    assert turn2.status == "done", turn2.error
    variables_after_2 = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables_after_2.get("selection_context") != "set_page", variables_after_2

    resolve_calls: dict[str, int] = {}
    from app.services.chatbot.lanes.business.services import ResolveGateServices

    monkeypatch.setattr(
        engine_mod.business_services,
        "production_services",
        lambda db, *, space_id=None: ResolveGateServices(
            access_types=lambda **_: [],
            resolve_entity=_s4_counting_resolve_entity(resolve_calls),
            probe=lambda **_: None,
        ),
    )
    # Register "low_signal" so this turn's own lane completes in the CRM instead
    # of hitting S7's hard refusal for a branch kind `chatbot_completed_lanes`
    # does not name; the resolver-counting stub above stays wired regardless
    # (a "more" with no carry never reaches `resolve_gate.run` either way).
    from app.models.user import SystemSetting

    settings_db = session_factory()
    setting = settings_db.query(SystemSetting).first()
    setting.chatbot_completed_lanes = ["business_query", "low_signal"]
    settings_db.commit()

    from app.services.chatbot.lanes import casual

    monkeypatch.setattr(casual, "resolve_for_prompt", lambda db, *, ctx: {"resolutions": []})
    monkeypatch.setattr(casual, "resolve_clarifier_config", lambda db, **_: object())
    monkeypatch.setattr(
        casual, "call_clarifier", lambda config, prompt: '{"response": "Not paging anything right now."}'
    )

    stub_parser(_s4_bare_parser_output())
    turn3 = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-r19-3", text="more"),
        session_factory=session_factory,
    )
    assert turn3.status == "done", turn3.error
    assert turn3.branch_kind == "low_signal", turn3.branch_kind

    variables_after_3 = _s4_session_vars(session_factory, contact_id).get("variables") or {}
    assert variables_after_3.get("selection_context") != "set_page", variables_after_3

    reply3 = (turn3.reply or {}).get("text") or ""
    assert "Showing 6 to 7" not in reply3, reply3
    assert not (_s4_codes_in(reply3) & set(codes)), (reply3, codes)


# --------------------------------------------------------------------------- #
# Round 3 re-check (R26, AC-1350): the page arm's `fetch_rendered_result`      #
# guard (`_set_page_carry`, compile_state.py ~line 1947) has no test of its    #
# own today - the reviewer proved disabling it leaves the whole file green.   #
# --------------------------------------------------------------------------- #


def test_set_page_carry_page_arm_keeps_the_offset_when_the_fetch_never_rendered():
    """AC-1350/R26: a page-continuation turn (`gate_json.predicate.page`
    present, off a carried `set_page` selection) whose OWN fetch never
    reached the tool (`fetch_rendered_result=False` - a tier-ask, an
    infrastructure error, the gate's own picker) must leave the carry's
    `offset` EXACTLY as `prev` left it - nothing new was shown, so a retried
    "more" has to start from the SAME position, not skip past rows the
    customer never actually saw.

    Unit-level, not a full engine turn: measured directly that a genuine MCP
    failure fails the WHOLE turn before `compile_current_state` ever runs at
    all (`engine.py`'s `fetch_failed_hard` path), so a full-turn construction
    of this scenario would pass whether or not the guard exists - proving
    nothing. Calling `_set_page_carry` itself is the only construction that
    actually exercises the guarded branch.

    GREEN today (the guard already exists at compile_state.py ~line 1947) -
    confirmed as a genuine kill test by manually disabling the guard locally
    (offset then advances to 7, the fabricated page's own `new_offset`) and
    reverting; not committed as a mutation, this docstring is the record.
    """
    from app.services.chatbot.tail.compile_state import _set_page_carry

    prev_carry = {
        "kind": "set_page",
        "qualifying_ids": ["a", "b", "c", "d", "e", "f", "g"],
        "offset": 5,
        "qualifying_total": 7,
        "require": {"certificate": True},
        "set_noun": "taps",
        "domain": "product_attachment",
        "access_levels": [],
    }
    prev = {
        "selection_context": "set_page",
        "last_result_set": prev_carry,
        "domain_hint": "product_attachment",
    }
    gate_json = {
        "predicate": {
            "require": {"certificate": True},
            "qualifying_total": 7,
            "page": {"start": 6, "end": 7, "new_offset": 7, "set_noun": "taps"},
        }
    }
    variables: dict[str, Any] = {}

    touched = _set_page_carry(
        variables,
        gate_json=gate_json,
        gate_ran=True,
        prev=prev,
        qf={"domain_hint": "product_attachment"},
        fetch_rendered_result=False,
    )

    assert touched is True
    assert variables.get("selection_context") == "set_page"
    carry = variables.get("last_result_set")
    assert carry == prev_carry, carry
    assert carry["offset"] == 5, carry


# --------------------------------------------------------------------------- #
# Owner regression (PR #833, R30, AC-1355): a set answer whose products were  #
# described with spec words must carry the forward path's Match line          #
# ("_Matched on: ..."), rendered by the SAME `_matched_on_line` (compile_     #
# state.py) the forward path already uses - the set path's candidates carry   #
# `matched_specs: []` on the require-only arm and the HAS turn never          #
# populates `result["spec_asked"]` at all, so the line is skipped entirely.   #
# --------------------------------------------------------------------------- #


def test_set_answer_carries_the_match_line_when_every_shown_product_matches(
    session_factory, stub_parser, stub_access, monkeypatch
):
    """AC-1355/R30: "check stock water closet with s trap 250mm" against five
    Water Closet products, all `trap_type=s_trap` / `trap_length=250`, all in
    stock - the reply must carry the SAME "_Matched on: ..." line the forward
    path renders for a spec-described product, naming trap type S Trap, trap
    length 250 and class Water Closet (the renderer's own wording - class
    verbatim with no key prefix, every other key as "<pretty key>: <value>",
    `class` first).

    RED: `resolve_product_set`'s require-only arm hardcodes `matched_specs:
    []` on every candidate (measured in `product_predicate_service.py`), and
    the resolver's HAS/require branch never sets `result["spec_asked"]` at
    all (only the `spec_fallback` branch does, `references.py` ~line 2856) -
    so `_matched_on_line`'s own `keys` list is empty for every shown row and
    the whole line is skipped ("if not keys: return user_response"). The
    reply text carries no "_Matched on:" substring at all.
    """
    contact_id = _s4_contact_id("matchline")
    db = session_factory()

    from app.models.inventory import Stock, Warehouse
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.models.product_spec import ProductSpecifications
    from app.services.product_spec_derivation import derive_for_code
    from tests._pg_fixture import unique_code

    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    warehouse = Warehouse(id=str(uuid.uuid4()), warehouse_code=unique_code("WH")[:50], warehouse_name="ZZT WH")
    db.add(warehouse)
    db.flush()

    for _ in range(5):
        code = unique_code("ZZTWC")[:50]
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description=f"{code} SORENTO CERAMIC WATER CLOSET",
            category_id=category_id,
            base_uom_id=uom_id,
            list_price=10,
            is_active=True,
        )
        db.add(product)
        db.flush()
        derive_for_code(db, code)
        spec_row = (
            db.query(ProductSpecifications).filter(ProductSpecifications.product_id == product.id).one()
        )
        values = dict(spec_row.values or {})
        values["trap_type"] = {"value": "s_trap"}
        values["trap_length"] = {"value": 250}
        spec_row.values = values
        db.add(
            Stock(
                id=str(uuid.uuid4()),
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity_on_hand=5,
                quantity_reserved=0,
                quantity_damaged=0,
            )
        )
    db.commit()

    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_stock_fake_call_tool(db),
    )
    stub_parser(
        _s4_bare_parser_output(
            message_type="business_query",
            intent_hint="check_stock",
            domain_hint="inventory",
            match_mode="and",
            entities=[
                {
                    "raw": "water closet",
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                }
            ],
        )
    )
    stub_access()

    turn = engine_mod.run_turn(
        _s4_envelope(
            contact_id=contact_id,
            message_id="ZZT-matchline-1",
            text="check stock water closet with s trap 250mm",
        ),
        session_factory=session_factory,
    )
    assert turn.status == "done", turn.error
    text = (turn.reply or {}).get("text") or ""
    assert "_Matched on:" in text, text
    assert "Water Closet" in text, text
    assert "S Trap" in text, text
    assert "250" in text, text


def test_set_answer_carries_the_match_line_when_shown_entities_include_promotions(
    session_factory, stub_parser, stub_access, monkeypatch
):
    """AC-1356/R31: the SAME world as
    `test_set_answer_carries_the_match_line_when_every_shown_product_matches`
    (five Water Closet products, all trap_type=s_trap/trap_length=250, all in
    stock), but `compatible_entities` is augmented exactly as replayed on the
    owner's local stack: alongside the five real product entities, 30 extra
    `entity_type="promotion"` rows ride along (uuid-only, no canonical_code,
    tier "substring") - noise from OTHER tokens ("water closet" as a category
    word, "Sorento" as a brand word) that reached `compatible_entities` via
    `gate.py`'s type-agnostic flattening of every `resolutions[].matches`
    entry, not just the product ones the require leg itself qualified.

    Patches `resolve_gate.run_gate` (not the resolver) to inject this shape
    directly onto its returned `compatible_entities`, since `gate.py`'s own
    `ALLOWED` matrix filters by domain BEFORE this bug's own code runs - a
    live turn's domain is whatever the parser gave it (unrelated to this
    bug), and this test's job is the renderer's handling of the noise once it
    IS present, not re-deriving which domain lets it through.

    The Match line must still render for the product rows shown; it must
    count PRODUCTS only, not every entity type the resolver happened to
    surface.

    RED: `_matched_on_line` (`compile_state.py` ~line 1071) builds `shown_set`
    from every `compatible_entities` row with no entity-type filter, then
    requires ALL of them to be spec rows (`all_shown_are_spec`). The 30
    injected promotion uuids are never in `spec_keys` (built only from
    `match_tier == "spec_search"` matches), so `all_shown_are_spec` is False
    and the whole line is skipped ("if not all_shown_are_spec: return
    user_response") even though every PRODUCT shown matched.
    """
    contact_id = _s4_contact_id("matchlinepromo")
    db = session_factory()

    from app.models.inventory import Stock, Warehouse
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.models.product_spec import ProductSpecifications
    from app.services.product_spec_derivation import derive_for_code
    from tests._pg_fixture import unique_code

    category_id, uom_id = _seed_category_and_uom(db)
    _seed_registry(db)
    warehouse = Warehouse(id=str(uuid.uuid4()), warehouse_code=unique_code("WH")[:50], warehouse_name="ZZT WH")
    db.add(warehouse)
    db.flush()

    for _ in range(5):
        code = unique_code("ZZTWC")[:50]
        product = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            description=f"{code} SORENTO CERAMIC WATER CLOSET",
            category_id=category_id,
            base_uom_id=uom_id,
            list_price=10,
            is_active=True,
        )
        db.add(product)
        db.flush()
        derive_for_code(db, code)
        spec_row = (
            db.query(ProductSpecifications).filter(ProductSpecifications.product_id == product.id).one()
        )
        values = dict(spec_row.values or {})
        values["trap_type"] = {"value": "s_trap"}
        values["trap_length"] = {"value": 250}
        spec_row.values = values
        db.add(
            Stock(
                id=str(uuid.uuid4()),
                product_id=product.id,
                warehouse_id=warehouse.id,
                quantity_on_hand=5,
                quantity_reserved=0,
                quantity_damaged=0,
            )
        )
    db.commit()

    def _promotion_noise_entities() -> list[dict[str, Any]]:
        return [
            {
                "uuid": str(uuid.uuid4()),
                "entity_type": "promotion",
                "code": None,
            }
            for _ in range(30)
        ]

    def _wrap_run_gate(real_run_gate: Any) -> Any:
        def run_gate(*args: Any, **kwargs: Any) -> dict[str, Any]:
            item = real_run_gate(*args, **kwargs)
            if isinstance(item, dict):
                item = dict(item)
                item["compatible_entities"] = list(
                    jsc.array(item.get("compatible_entities"))
                ) + _promotion_noise_entities()
            return item

        return run_gate

    from app.services.chatbot import jsc
    from app.services.chatbot.lanes.business import resolve_gate as resolve_gate_mod

    monkeypatch.setattr(resolve_gate_mod, "run_gate", _wrap_run_gate(resolve_gate_mod.run_gate))

    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})
    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_stock_fake_call_tool(db),
    )
    stub_parser(
        _s4_bare_parser_output(
            message_type="business_query",
            intent_hint="check_stock",
            domain_hint="inventory",
            match_mode="and",
            entities=[
                {
                    "raw": "water closet",
                    "hint": "product",
                    "canonical_code": None,
                    "current_message": True,
                    "confident": True,
                }
            ],
        )
    )
    stub_access()

    turn = engine_mod.run_turn(
        _s4_envelope(
            contact_id=contact_id,
            message_id="ZZT-matchlinepromo-1",
            text="check stock water closet with s trap 250mm",
        ),
        session_factory=session_factory,
    )
    assert turn.status == "done", turn.error
    text = (turn.reply or {}).get("text") or ""
    assert "_Matched on:" in text, text
    assert "Water Closet" in text, text
    assert "S Trap" in text, text
    assert "250" in text, text


def test_set_answer_with_no_spec_words_carries_no_match_line(
    session_factory, stub_parser, stub_access, monkeypatch
):
    """AC-1355/R30 control: "which tap has cert" (no spec bindings at all)
    must carry NO "_Matched on:" line - the certificate leg names no spec
    key for `_matched_on_line` to intersect against.

    Green today - `_matched_on_line` already returns the response unchanged
    when `matched_specs` is empty for every shown row, which is already true
    for a certificate-only HAS turn regardless of the R30 fix; kept as the
    regression guard against the fix adding a Match line to every set answer
    unconditionally.
    """
    contact_id = _s4_contact_id("nomatchline")
    db = session_factory()
    _s4_seed_seven_taps(db)
    _s4_seed_contact(session_factory, contact_id=contact_id, session_vars={"variables": {}})

    engine_mod = _s4_wire_engine(
        session_factory,
        monkeypatch,
        resolve_entity=_s4_real_resolve_entity(db),
        fetch_mcp_call=_cert_fake_call_tool(db),
    )
    stub_parser(_s4_cert_parser_output())
    stub_access()

    turn = engine_mod.run_turn(
        _s4_envelope(contact_id=contact_id, message_id="ZZT-nomatchline-1", text="which tap has cert"),
        session_factory=session_factory,
    )
    assert turn.status == "done", turn.error
    text = (turn.reply or {}).get("text") or ""
    assert "_Matched on:" not in text, text
