"""Shape B's `require` seam: a pure map off what the parser already emits.

Work item B1 (`PLAN-attribute-first-asks.md`). No message-text matching beyond the
existing `_CERT_RE` on an `attachment_type` entity's own `raw` - `derive_require` is
`derive_routing`'s sibling, not a second parser. A turn whose intent carries no leg returns `None` and behaves exactly
as it does today (AC-1322's invariant).

Contract: `documentation/plans/chatbot/attribute-first-asks-acceptance-criteria.md`
AC-1303, AC-1304.
"""
from __future__ import annotations

import re
from typing import Any

# The two cert-word tests, declared HERE since the head module that used to own them is
# retired with the rest of the post-processor. `_CERT_RE` also matches a SCHEME name
# (span, sirim, bomba, ms####, halal, ikram), which is what lets "pps cert" split into a
# bare leg plus a scheme; `_CERTIFICATE_RE` is the plain word on its own.
_CERT_RE = re.compile(r"cert|ikram|span|sirim|bomba|ms\s?[0-9]|halal", re.IGNORECASE)
_CERTIFICATE_RE = re.compile(r"cert|certificate", re.IGNORECASE)

# Intents that need nothing beyond their own name to name a leg - the customer's own
# word for each is also the leg's key, which is what `derive_predicate_words` below
# subtracts from the described set.
_BARE_LEG_BY_INTENT: dict[str, str] = {
    "check_stock": "stock",
    "check_incoming": "incoming",
    "check_promotion": "promotion",
}

# The word ITSELF that names "a certificate", in English and Malay - distinct from
# `_CERT_RE`, which also matches a SCHEME name (span, sirim, bomba, ms9001, halal,
# ikram) so `derive_routing` can route a bare scheme word to the cert team too.
# Stripping this set off the raw is what is left over is a SCHEME word (S2, AC-1303):
# "pps cert" -> scheme "pps", "watermark certificate" -> scheme "watermark", while
# "cert" alone strips to nothing and stays the bare leg.
#
# R21/AC-1345 (console pass 6): every INFLECTION of the word, not only "cert"/
# "certificate" - the head's `entity_op: reuse` hands `derive_require` the
# AttachmentType's own NAME ("Certification"), not the customer's original
# word, so "certs", "certification(s)" and any case must all read as the bare
# leg too, the same as "cert" always has.
_BARE_CERT_WORDS: frozenset[str] = frozenset(
    {"cert", "certs", "certificate", "certificates", "certification", "certifications", "sijil"}
)

# R33/AC-1358 (reviewer round 4, should-fix): word-anchored over the bare
# cert word FAMILY - `cert`/`certs` exactly, `certif`-prefixed for every
# certify/certificate/certification INFLECTION (certified, certifying,
# certificate(s), certification(s), ...), and the Malay `sijil` - never a
# bare substring search. `_CERTIFICATE_RE`/`_CERT_RE` have no word boundary
# at all, so "certainly" and "concert" (both merely CONTAIN "cert") false-
# positived as a certificate question in the no-raw fallback below, and
# `sijil` was never tried there at all (only ever checked against an
# attachment_type RAW, which this fallback by definition has none of).
_BARE_CERT_WORD_RE = re.compile(r"\b(?:certs?|certif\w*|sijil)\b", re.IGNORECASE)


# Words that describe a certificate's own PROPERTY (its validity, expiry, number),
# never a scheme: "valid cert", "cert validity", "certificate expiry", "cert no".
# Reviewer B1 on PR #833: before this they split off as scheme "valid", which no
# register holds, so the answer said "0 products" over an unfiltered list. Validity
# is flagged on every row, never filtered (D-lane), so these read as the bare leg.
_CERT_PROPERTY_WORDS: frozenset[str] = frozenset(
    {
        "valid", "validity", "invalid", "expiry", "expired", "expire", "expires",
        "expiration", "no", "no.", "number", "num", "status", "date", "copy",
        "latest", "current", "active", "still", "sah", "tamat",
    }
)


def _cert_scheme_from_raw(raw: str) -> str | None:
    """What is left of `raw` once every bare cert word and every certificate
    PROPERTY word is removed, or None when nothing is - the raw named no scheme."""
    words = [w for w in re.split(r"\s+", raw.strip()) if w]
    remainder = [
        w for w in words if w.lower() not in _BARE_CERT_WORDS and w.lower() not in _CERT_PROPERTY_WORDS
    ]
    return " ".join(remainder).strip() or None


def _attachment_type_raws(parser_output: dict[str, Any]) -> list[str]:
    """Every `attachment_type` entity's own raw, in order, non-empty, deduped."""
    raws: list[str] = []
    for entity in parser_output.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if str(entity.get("hint") or "").strip().lower() != "attachment_type":
            continue
        raw = str(entity.get("raw") or "").strip()
        if raw and raw not in raws:
            raws.append(raw)
    return raws


# The v3 verdict's own carrier for an attribute-first ask (turn re-architecture):
# `requested_attributes` is what the customer asked ABOUT, and for these words the
# attribute IS the leg. Read BEFORE the intent, because v3 states the attribute
# explicitly where the pre-rearch prompt could only imply it through `intent_hint`.
_LEG_BY_ATTRIBUTE_WORD: dict[str, str] = {
    "cert": "certificate",
    "certs": "certificate",
    "certificate": "certificate",
    "certificates": "certificate",
    "certification": "certificate",
    "certifications": "certificate",
    "sijil": "certificate",
    "stock": "stock",
    "stok": "stock",
    "incoming": "incoming",
    "eta": "incoming",
    "promotion": "promotion",
    "promotions": "promotion",
    "promo": "promotion",
    "promosi": "promotion",
}


def _require_from_attributes(parser_output: dict[str, Any]) -> dict[str, Any] | None:
    """`{leg: True}` for the first `requested_attributes` word that names a leg.

    An attribute word the table does not know is NOT guessed into a leg: it stays a
    plain requested attribute and the ordinary answer projects it, which is what a
    spec question ("what is its width") has always done.

    A cert PHRASE ("PPS cert", "sirim certificate") is the same split an
    `attachment_type` raw gets below (S2, AC-1303): the scheme is what is left once the
    bare cert word is removed. Without it the phrase missed the one-word table, fell to
    the bare leg, and "PPS" was then stripped from the remainder as a predicate word, so
    nothing downstream could recover the scheme either.
    """
    for raw in parser_output.get("requested_attributes") or []:
        if not isinstance(raw, str):
            continue
        leg = _LEG_BY_ATTRIBUTE_WORD.get(raw.strip().lower())
        if leg:
            return {leg: True}
        words = [w for w in re.split(r"\s+", raw.strip()) if w]
        if len(words) > 1 and _CERT_RE.search(raw):
            scheme = _cert_scheme_from_raw(raw)
            return {"certificate": {"scheme": scheme}} if scheme else {"certificate": True}
    return None


def derive_require(
    parser_output: dict[str, Any], *, message_text: str | None = None
) -> dict[str, Any] | None:
    """`{leg: value}` for the turn's intent, or `None` when it carries no leg.

    `check_product_attachment` splits on the FIRST `attachment_type` entity's raw:
    a cert-shaped word (`_CERT_RE`, the same regex `derive_routing` already uses for
    the cert-vs-photo team split) maps to the `certificate` leg - bare when the raw
    is only the cert word ("cert", "certificate", "sijil"), else `{"scheme": ...}`
    with the rest of the raw (S2, AC-1303: "pps cert" -> scheme "pps"). The
    function stays pure - it never touches the `certificate_scheme` lookup set,
    that normalisation happens server-side in `_leg_certificate`. Any other label
    passes through verbatim as the `attachment_type` leg, resolved server-side
    (`_leg_attachment_type` in `product_predicate_service.py`) so a new document
    class never needs a parser prompt change.

    R4/AC-1328 (console fix round 2): a SCHEME-ONLY raw ("PPS") carries no
    `_CERT_RE` word of its own - that regex names a cert BODY (cert/ikram/span/
    sirim/bomba/ms####/halal), never a bare register spelling - so this mirrors
    `derive_routing`'s `is_cert`: also certificate when the intent is
    `check_product_attachment` and `_CERTIFICATE_RE` matches `user_goal` (the
    parser's own field, read the same way `derive_routing` does) or, when that is
    absent, `message_text` (the caller's own fallback - `resolve_entity_body`
    passes `_query_text(ctx)`, the same seam every other reader of the raw
    message uses). The raw itself becomes the scheme verbatim in that case - it
    named no cert word to strip.

    R21/AC-1345 (console pass 6): the BARE-WORD check runs FIRST, before the
    `_CERT_RE` test - every word of the raw (whitespace-split, lower-cased)
    being in `_BARE_CERT_WORDS` is the bare `certificate` leg regardless of
    what `_CERT_RE` itself matches. This is what catches "sijil": that word
    names no cert BODY `_CERT_RE` recognises (it is Malay for "certificate",
    not one of the scheme-name synonyms the regex also matches), so without
    this it fell through past the cert branch entirely and reached the
    generic `attachment_type` leg. "PPS certification" still splits: it is
    not ALL bare-cert words, so it falls to the `_CERT_RE` branch below, which
    strips "certification" (now in `_BARE_CERT_WORDS`) and returns scheme
    "PPS".

    R28/AC-1353 (owner console run 10): the head can drop the attachment_type
    entity ENTIRELY - an entity whose raw resolved no `canonical_code`
    ("PPS", measured null) is normalised away before this function ever sees
    it, leaving `entities: []`. With no raw to split on, the cert question
    survives only in `user_goal` / `message_text` - the same fallback R4
    already reads for a scheme-only raw, tried here BEFORE giving up, never
    after: there is no raw left to fall through past.

    R33/AC-1358 (reviewer round 4, should-fix): this no-raw fallback matches
    `_BARE_CERT_WORD_RE`, word-anchored, never `_CERTIFICATE_RE` as a bare
    substring - "certainly, send me the drawing" and "concert hall basin
    photo" both merely CONTAIN "cert" and must not read as a certificate
    question, while "is this certified?" and the Malay "ada sijil untuk
    basin?" genuinely are one.
    """
    from_attributes = _require_from_attributes(parser_output)
    if from_attributes is not None:
        if from_attributes == {"certificate": True}:
            # The attribute names only the bare leg; an attachment_type raw beside it
            # may still carry the scheme ("certificate" + entity "PPS cert").
            for raw in _attachment_type_raws(parser_output):
                if _CERT_RE.search(raw):
                    scheme = _cert_scheme_from_raw(raw)
                    if scheme:
                        return {"certificate": {"scheme": scheme}}
        return from_attributes

    intent = parser_output.get("intent_hint")
    if intent in _BARE_LEG_BY_INTENT:
        return {_BARE_LEG_BY_INTENT[intent]: True}

    if intent == "check_product_attachment":
        raws = _attachment_type_raws(parser_output)
        if not raws:
            goal_or_message = parser_output.get("user_goal") or message_text or ""
            if _BARE_CERT_WORD_RE.search(str(goal_or_message)):
                return {"certificate": True}
            return None
        raw = raws[0]
        raw_words = [w for w in re.split(r"\s+", raw.strip()) if w]
        if raw_words and all(w.lower() in _BARE_CERT_WORDS for w in raw_words):
            return {"certificate": True}
        if _CERT_RE.search(raw):
            scheme = _cert_scheme_from_raw(raw)
            return {"certificate": {"scheme": scheme}} if scheme else {"certificate": True}
        goal_or_message = parser_output.get("user_goal") or message_text or ""
        if _CERTIFICATE_RE.search(str(goal_or_message)):
            return {"certificate": {"scheme": raw}}
        return {"attachment_type": raw}

    return None


def derive_predicate_words(
    parser_output: dict[str, Any], require: dict[str, Any] | None, *, message_text: str | None = None
) -> list[str]:
    """Every word the described set must strip from the customer's own query.

    Every `attachment_type` entity's raw, plus the intent's own word for a bare leg
    (`stock`, `incoming`, `promotion` - the leg key IS the word, since nothing else
    named it). `check_product_attachment` needs no extra word: the attachment_type
    raw already covers it.

    R28/AC-1353: when `require` is the BARE `certificate` leg (`{"certificate":
    True}`) and no attachment_type raw contributed a word (there was none to
    read - `derive_require` recovered it off `message_text` instead), the word
    that actually earned the leg never left the remainder on its own. Pull the
    cert word(s) `message_text` itself carries (matching `_BARE_CERT_WORD_RE`,
    the same word-anchored pattern `derive_require` used - R33/AC-1358) so the
    described-set reader strips the bare word ITSELF, with no trailing
    punctuation glued on ("certified", never "certified?"), rather than
    reading "item pps cert" as an unrecognized phrase.
    """
    if not require:
        return []
    words = _attachment_type_raws(parser_output)
    for raw in parser_output.get("requested_attributes") or []:
        if isinstance(raw, str) and raw.strip() and raw not in words:
            words.append(raw)
    intent = parser_output.get("intent_hint")
    if intent in _BARE_LEG_BY_INTENT:
        leg = _BARE_LEG_BY_INTENT[intent]
        if leg not in words:
            words.append(leg)
    if not words and require.get("certificate") is True and message_text:
        for match in _BARE_CERT_WORD_RE.finditer(message_text):
            word = match.group()
            if word and word not in words:
                words.append(word)
    return words
