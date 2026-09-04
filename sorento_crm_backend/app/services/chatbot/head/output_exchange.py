"""Port of `output_exchange.js` (1,882 lines) and `suggest-follow-up.js` (55).

This is the deterministic post-processor that turns the parser's ~26 emitted keys into
the ~95-key `qf` object the whole rest of the turn reads. It is the single largest piece
of business logic in the n8n graph and the reason the port is worth doing at all: every
rule below was measured against a real execution, is named after the execution that
forced it, and had no test until the replay corpus existed.

**Ported line by line, deliberately.** D8 is parity before improvement, so the structure,
the ordering, the lazy predicate evaluation, the loose `==` comparisons and even the
diagnostic keys emitted only when non-empty are reproduced exactly. Where the JS relies
on JavaScript semantics Python does not share - `[]` is truthy, `String(null)` is
`"null"`, an absent key is `undefined` - the shim in `app/services/chatbot/jsc.py`
supplies them rather than each site guessing.

**Text sniffing.** D11's rule is that understanding text is the parser's job. Several
blocks here do match the raw message (the domain-switch words, the date-widen phrases,
the member-offer extractor, the "all/semua" test). Every one of them is reproduced for
parity and inventoried in the plan's text-sniffing table as a candidate to move into the
prompt AFTER parity, never before. No NEW site may be added: a reviewer finding one is a
merge blocker.

The n8n node runs `runOnceForEachItem`, so `output_exchange` handles ONE item;
`suggest-follow-up` runs `runOnceForAllItems` over the first item only.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot.contracts import ENTITY_HINTS, INTENT_HINTS


class ParserOutputError(ValueError):
    """The parser did not emit a JSON object.

    n8n limped on with `output.output` as a raw string and threw a few lines later on
    `reference_positions.length`; R5 makes that explicit instead - a failed `understood`
    stage with today's error reply and NO default routing (H44 closed). With the strict
    `json_schema` the CRM sends, this cannot be reached from a well-formed provider
    response at all.
    """


# --------------------------------------------------------------------------- #
# ROUTING DERIVATION (mechanical map; parser emits semantic signals only)
# --------------------------------------------------------------------------- #

_CERT_RE = re.compile(r"cert|ikram|span|sirim|bomba|ms\s?[0-9]|halal", re.IGNORECASE)
_CERTIFICATE_RE = re.compile(r"cert|certificate", re.IGNORECASE)
_VALID_BRANDS = ("sorento", "cabana", "mocha")


def derive_routing(out: dict) -> dict:
    domain = out.get("domain_hint")
    ents = jsc.array(out.get("entities"))

    # attachment_type discriminator (the cert-vs-photo split within product_attachment)
    attach_types = [
        jsc.lower_or_empty(e.get("canonical_code") if jsc.truthy(e.get("canonical_code")) else e.get("raw"))
        for e in ents
        if jsc.lower_or_empty(jsc.get(e, "hint")) == "attachment_type"
    ]
    # Fire when EITHER an attachment_type raw names a cert body/word, OR the semantic
    # signal (attachment intent + a cert word in user_goal) says certificate.
    # Brand-named certs (SPAN/SIRIM/BOMBA/MS####/Halal) arrive as attachment_type raw.
    is_cert = any(_CERT_RE.search(t) for t in attach_types) or (
        out.get("intent_hint") == "check_product_attachment"
        and bool(_CERTIFICATE_RE.search(jsc.lower_or_empty(out.get("user_goal")) or ""))
    )

    # brand for promotion routing (entity wins, else access level). D9: prefer the
    # DERIVED query_brands - it is the union of the brand entity and the brand half of a
    # compound stated level, so it survives the tier-token normalisation that made the
    # access-level fallback below dead.
    brand_ent = jsc.find(ents, lambda e: jsc.lower_or_empty(jsc.get(e, "hint")) == "brand")
    access = [jsc.js_string(a).lower() for a in jsc.array(out.get("access_levels"))]
    query_brands = out.get("query_brands")
    brand = query_brands[0] if jsc.is_array(query_brands) and len(query_brands) else None
    if not jsc.truthy(brand):
        brand = jsc.lower_or_empty(jsc.get(brand_ent, "raw")) if brand_ent is not None else None
    if not jsc.truthy(brand):
        if any("mocha" in a for a in access):
            brand = "mocha"
        elif any("cabana" in a for a in access):
            brand = "cabana"
        elif any("sorento" in a for a in access):
            brand = "sorento"
    # D3 fix: clamp to the valid promotion-brand enum; garbled/unknown -> None.
    _b2 = re.sub(r"[^a-z]", "", jsc.js_string(brand if jsc.truthy(brand) else ""))
    brand = next((v for v in _VALID_BRANDS if v in _b2), None)

    if domain == "master_products":
        return {"suggested_team": "purchasing", "suggested_agent": "general_enquiries"}
    if domain == "incoming":
        return {"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"}
    if domain == "product_attachment":
        return (
            {"suggested_team": "purchasing_certification", "suggested_agent": "general_enquiries"}
            if is_cert
            else {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}
        )
    # resource_attachment (catalogue / warranty / price tag template / shipping schedule)
    # is the same marketing-material hand-off as product_attachment's non-cert row.
    if domain == "resource_attachment":
        return {"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"}
    if domain == "forms":
        return {"suggested_team": "marketing_form", "suggested_agent": "marketing_form"}
    if domain == "inventory":
        return {"suggested_team": "warehouse", "suggested_agent": "general_enquiries"}
    if domain == "order":
        return {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"}
    # ONE promotion team for every brand (CRM migration 371 collapsed the legacy
    # marketing_promotion_<brand> rows into base + brand_code). The brand travels
    # separately (query_brands / brand entity), never in the team name.
    if domain == "promotion":
        return {"suggested_team": "marketing_promotion", "suggested_agent": "general_enquiries"}
    # ideate: no CS team (an idea is captured, never escalated) but its OWN access agent.
    # This is the SINGLE source of truth for the ideate agent: check-access keys on
    # suggested_agent and the no-access message renders from the SAME field.
    if domain == "ideate":
        return {"suggested_team": None, "suggested_agent": "ideation"}
    return {"suggested_team": None, "suggested_agent": None}


# --------------------------------------------------------------------------- #
# Constant tables (module scope in the JS too)
# --------------------------------------------------------------------------- #

# axis depends on DOMAIN: in promotion, product/brand/category/flyer all scope "which
# promotion".
AXIS_BY_DOMAIN: dict[str, dict[str, str]] = {
    "promotion": {
        "brand": "promo_scope",
        "category": "promo_scope",
        "promotion": "promo_scope",
        "flyer": "promo_scope",
        "product": "promo_scope",
    },
    "master_products": {
        "product": "product_scope",
        "category": "product_scope",
        "brand": "product_scope",
    },
    "order": {
        "order": "order_scope",
        "order_number": "order_scope",
        "customer_order": "order_scope",
        "customer": "order_scope",
        "transporter": "order_scope",
        "product": "order_scope",
    },
    "incoming": {
        "product": "incoming_scope",
        "inbound_shipment": "incoming_scope",
        "category": "incoming_scope",
        "brand": "incoming_scope",
    },
    "product_attachment": {
        "product": "product_scope",
        "category": "product_scope",
        "brand": "product_scope",
        "attachment_type": "attachment_scope",
        # B2' part 1: these were `__certificate` / `__attachment`, private axes nothing
        # could collide with, so they were never evicted (exec 11509873).
        "certificate": "attachment_scope",
        "attachment": "attachment_scope",
    },
}

HINT_AXIS_DEFAULT: dict[str, str] = {
    "brand": "promo_scope",
    "category": "promo_scope",
    "promotion": "promo_scope",
    "flyer": "promo_scope",
    "product": "product_scope",
    "attachment_type": "attachment_scope",
    "certificate": "attachment_scope",
    "attachment": "attachment_scope",
    "customer": "order_scope",
    "transporter": "order_scope",
    "order": "order_scope",
    "order_number": "order_scope",
    "customer_order": "order_scope",
    "warehouse": "location",
    "goods_receive": "doc",
    "spo": "doc",
    "form": "doc",
    "inbound_shipment": "incoming_scope",
    "grn": "doc",
}

# C1: an unrecognised hint must NEVER get a private axis (`__${hint}` produced an island
# no current-turn entity could collide with, so it survived every turn). Two-step
# fallback: the domain's SUBJECT axis, then ONE shared axis.
DOMAIN_SUBJECT_AXIS: dict[str, str] = {
    "product_attachment": "product_scope",
    "master_products": "product_scope",
    "inventory": "product_scope",
    "resource_attachment": "product_scope",
    "incoming": "incoming_scope",
    "promotion": "promo_scope",
    "order": "order_scope",
    "spo_allocation": "order_scope",
    "goods_receive": "doc",
    "forms": "doc",
    "portal_link": "doc",
}

# Domain -> the entity HINT naming that domain's own subject. Read by the AXIS BROADEN
# restore and by the reference-positions block; hoisted so there is one copy.
DOMAIN_SUBJECT_HINT: dict[str, str] = {
    "product_attachment": "product",
    "master_products": "product",
    "inventory": "product",
    "incoming": "product",
    "resource_attachment": "attachment",
    "portal_link": "form",
    "goods_receive": "goods_receive",
    "spo_allocation": "spo",
    "forms": "form",
    "order": "order",
    "promotion": "promotion",
}

MENU_LABELS: dict[str, dict[str, str]] = {
    "stock enquiry": {
        "intent_hint": "get_portal_link",
        "domain_hint": "portal_link",
        "portal": "stock_enquiry",
    },
    "stock inquiry": {
        "intent_hint": "get_portal_link",
        "domain_hint": "portal_link",
        "portal": "stock_enquiry",
    },
    "complaint": {
        "intent_hint": "get_portal_link",
        "domain_hint": "portal_link",
        "portal": "complaint",
    },
    "price enquiry": {
        "intent_hint": "get_portal_link",
        "domain_hint": "portal_link",
        "portal": "price_enquiry",
    },
}

# rev4: the reliable this-turn signal is the LLM intent_hint. Decisive intents fire ONLY
# on a real purpose-word classification; bare codes reliably get intent_hint null. Today
# EVERY declared intent is decisive - including `submit_idea`, because a proposal must
# OVERRIDE a carried CRM domain (the reverse still carries: a bare continuation has no
# decisive intent). Derived rather than re-listed so a new intent forces a deliberate
# decision here instead of silently defaulting to "not decisive" (H28).
NON_DECISIVE_INTENTS: frozenset[str] = frozenset()
DECISIVE_INTENTS = frozenset(INTENT_HINTS) - NON_DECISIVE_INTENTS

DOMAIN_SWITCH_WORDS: dict[str, str] = {
    "promo": "promotion",
    "promos": "promotion",
    "promotion": "promotion",
    "promotions": "promotion",
    "promosi": "promotion",
    "stock": "inventory",
    "stocks": "inventory",
    "inventory": "inventory",
    "stok": "inventory",
    "qty": "inventory",
    "quantity": "inventory",
    "order": "order",
    "orders": "order",
    "outstanding": "order",
    "tempahan": "order",
    "incoming": "incoming",
    "eta": "incoming",
    "shipment": "incoming",
    "shipments": "incoming",
    "arriving": "incoming",
    "container": "incoming",
    "containers": "incoming",
    "catalogue": "master_products",
    "catalog": "master_products",
    "spec": "master_products",
    "specs": "master_products",
    "specification": "master_products",
    "specifications": "master_products",
    "dimension": "master_products",
    "dimensions": "master_products",
}

SWITCH_FILLER = frozenset(
    {
        "the", "a", "an", "for", "to", "of", "on", "in", "me", "my", "i", "is", "are",
        "be", "any", "some", "pls", "plz", "please", "can", "could", "would", "you",
        "u", "got", "have", "has", "had", "do", "does", "did", "what", "whats", "how",
        "much", "many", "check", "get", "show", "give", "tell", "about", "need", "want",
        "wanna", "see", "list", "all", "ada", "untuk", "tolong", "boleh", "nak", "saya",
        "ni", "tu", "ke", "yang", "dan", "ada?", "pun", "je", "ya", "ha",
    }
)

DW_FILLERS = frozenset(
    {
        "yes", "ya", "yeah", "yep", "yup", "ok", "okay", "okie", "oki", "k", "sure",
        "please", "pls", "plz", "pl", "kindly", "thanks", "thank", "ty", "tq",
        "lah", "la", "leh", "lor", "ah", "one",
        "the", "a", "an", "to", "for", "of",
    }
)

DW_PHRASES = frozenset(
    {
        "all dates", "all date", "all time", "all times", "any date", "any dates",
        "every date", "no date limit", "no date filter", "remove date filter",
        "since ever",
    }
)

# Always-blocked: hints that never make sense for the domain.
DOMAIN_BLOCKED_HINTS: dict[str, list[str]] = {
    "master_products": ["forms", "form", "attachment", "promotion", "customer", "transporter", "order", "customer_order", "order_number", "spo", "grn", "goods_receive", "inbound_shipment", "access_levels", "attachment_type", "flyer"],
    "product_attachment": ["forms", "form", "promotion", "customer", "transporter", "order", "spo", "grn", "goods_receive", "attachment", "inbound_shipment", "access_levels", "customer_order", "order_number", "flyer"],
    "promotion": ["forms", "form", "attachment", "customer", "transporter", "order", "customer_order", "order_number", "spo", "grn", "goods_receive", "inbound_shipment", "access_levels", "attachment_type"],
    "forms": ["product", "attachment", "promotion", "customer", "transporter", "order", "customer_order", "order_number", "spo", "grn", "goods_receive", "inbound_shipment", "access_levels"],
    "inventory": ["customer", "transporter", "order", "customer_order", "order_number", "spo", "grn", "goods_receive", "inbound_shipment", "attachment_type"],
    # 'spo' removed: PS-codes resolve as customer_order; a bare code hinted spo must
    # survive reuse under the order domain.
    "order": ["forms", "form", "promotion", "grn", "goods_receive", "inbound_shipment", "access_levels", "category", "brand", "attachment_type", "attachment", "resource_attachment", "flyer"],
    "incoming": ["forms", "form", "attachment", "promotion", "customer", "transporter", "warehouse", "spo", "grn", "goods_receive", "access_levels", "category", "brand", "attachment_type", "flyer", "resource_attachment"],
    "portal_link": ["forms", "form", "product", "attachment", "promotion", "customer", "transporter", "order", "customer_order", "order_number", "spo", "grn", "goods_receive", "inbound_shipment", "access_levels", "category", "brand", "attachment_type", "flyer"],
    # 'brand' + 'category' added 2026-08-09 (live exec 11818957): a promotion turn left
    # brand='Sorento' in state, the next turn routed to resource_attachment and CARRIED
    # it, and 'Sorento' fuzzy-matched promotion PDFs. `crm_resource_attachments_list` has
    # no brand or category param, so these can only pollute a document lookup.
    "resource_attachment": ["forms", "form", "product", "promotion", "customer", "transporter", "order", "customer_order", "order_number", "spo", "grn", "goods_receive", "inbound_shipment", "access_levels", "attachment_type", "flyer", "brand", "category"],
    "goods_receive": ["forms", "form", "product", "attachment", "promotion", "customer", "transporter", "order", "customer_order", "order_number", "spo", "grn", "goods_receive", "inbound_shipment", "access_levels", "category", "brand", "attachment_type", "flyer"],
    "spo_allocation": ["forms", "form", "product", "attachment", "promotion", "customer", "transporter", "order", "customer_order", "order_number", "spo", "grn", "goods_receive", "inbound_shipment", "access_levels", "category", "brand", "attachment_type", "flyer"],
}

# Broaden-only blocked: hints that NARROW the result and therefore contradict an
# "all / everything" request. Brand/access stay - they are context, not a subset filter.
DOMAIN_BROADEN_BLOCKED_HINTS: dict[str, list[str]] = {
    "promotion": ["promotion", "attachment"],
    "master_products": ["product"],
    "product_attachment": ["product", "attachment_type"],
    "inventory": ["product"],
    "order": ["order", "customer"],
    "incoming": ["inbound_shipment", "product"],
    "forms": ["form"],
    "resource_attachment": ["attachment"],
    "goods_receive": ["goods_receive"],
    "spo_allocation": ["spo"],
}

# C2's guard list is deliberately WIDER than the parser's declared enum: these eight are
# hints minted downstream of the parser (by the resolver, the flyer injection and the
# picker rows), never emitted by the LLM. Derived from the declared tuple so the two can
# only ever differ by this named extension (H28).
KNOWN_ENTITY_HINTS = frozenset(ENTITY_HINTS) | {
    "certificate",
    "flyer",
    "order_number",
    "customer_order",
    "goods_receive",
    "spo",
    "grn",
    "forms",
}

HINT_MAP = {
    "promotion": "promotion",
    "product": "product",
    "order": "order",
    "order_number": "order",
    "customer": "customer",
    "form": "form",
}

# >>> mapper-embed (byte-copy of tests/offline/access-tier/mapper.js) <<<
BRANDS = ["sorento", "cabana", "mocha"]
TIER_WORDS = {"dealer": "dealer", "office": "office", "end user": "end_user"}
TIER_ORDER = ["dealer", "office", "end_user"]

_LEVEL_RE = re.compile(r"^(sorento|cabana|mocha) (dealer|office)$")
_DEALER_RE = re.compile(r" (dealer|dealers|pengedar) ")
_OFFICE_RE = re.compile(r" (office|ofis) ")
_ENDUSER_RE = re.compile(r" end ?users? |ke pengguna? | enduser ")


def _parse_level(name: Any) -> dict | None:
    s = re.sub(r"\s+", " ", jsc.nullish_str(name).strip().lower())
    if s in ("end user", "enduser", "end-user"):
        return {"brand": None, "tier": "end_user"}
    m = _LEVEL_RE.match(s)
    return {"brand": m.group(1), "tier": m.group(2)} if m else None


def _stated_tiers(message: Any, entities: Any) -> list[str]:
    found: set[str] = set()
    txt = " " + re.sub(r"[^a-z0-9]+", " ", jsc.nullish_str(message).lower()) + " "
    if _DEALER_RE.search(txt):
        found.add("dealer")
    if _OFFICE_RE.search(txt):
        found.add("office")
    if _ENDUSER_RE.search(txt):
        found.add("end_user")
    for e in jsc.array(entities):
        raw = jsc.get(e, "canonical_code") if jsc.truthy(jsc.get(e, "canonical_code")) else jsc.get(e, "raw")
        p = _parse_level(raw)
        if p:
            found.add(p["tier"])
        else:
            s = jsc.nullish_str(raw).strip().lower()
            if s in TIER_WORDS:
                found.add(TIER_WORDS[s])
    return [t for t in TIER_ORDER if t in found]


def _stated_brands(entities: Any, raw_levels: Any, message: Any) -> list[str]:
    out: set[str] = set()
    txt = " " + re.sub(r"[^a-z0-9]+", " ", jsc.nullish_str(message).lower()) + " "
    for b in BRANDS:
        if (" " + b + " ") in txt:
            out.add(b)
    for e in jsc.array(entities):
        if jsc.lower_or_empty(jsc.get(e, "hint")) != "brand":
            continue
        s = jsc.lower_or_empty(
            jsc.get(e, "canonical_code") if jsc.truthy(jsc.get(e, "canonical_code")) else jsc.get(e, "raw")
        )
        v = next((b for b in BRANDS if b in s), None)
        if v:
            out.add(v)
    from_levels: set[str] = set()
    for level in jsc.array(raw_levels):
        p = _parse_level(level)
        if p and p["brand"]:
            from_levels.add(p["brand"])
    if len(from_levels) == 1:
        out |= from_levels
    return [b for b in BRANDS if b in out]


# <<< mapper-embed

_ORD = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6,
}

# STOPGAP mirror of escalation-context's own table; the real source is the CRM
# `companies.code` column threaded through the resolver.
CO_ALIASES = {"sorento": ["sorento", "srt"], "mocha": ["mocha", "mch"], "cabana": ["cabana", "cbn"]}

DATE_FILTER_DOMAINS = frozenset({"promotion", "order"})

# DIGITS and WORD BOUNDARIES are ASCII here; WHITESPACE is not. Python's `\d` and `\b`
# are Unicode-aware and JavaScript's are not - a full-width "\uff11" satisfies Python's
# `^\d+$` and not JS's, so a message the live bot reads as free text would have resolved
# to a member PICK here and fired a real assignment.
#
# `re.ASCII` is deliberately NOT used: it narrows `\s` too, and JavaScript's `\s` DOES
# match Unicode whitespace (a non-breaking space between "1," and "2" is a real IME and
# copy-paste artefact). Narrowing it would have broken a reply that works today, which is
# the opposite mistake. So the digit classes are written out as `[0-9]` / `[^0-9]`, the
# one leading word boundary is written out as a lookbehind, and `\s` is left alone.
_REPLY_TO_SPLIT = re.compile(r"\s*reply to:", re.IGNORECASE)
_OFFERED_ESCALATION_RE = re.compile(r"would you like me to escalate", re.IGNORECASE)
_ALL_RE = re.compile(
    r"^(all|all of them|all of it|everything|every one|semua|semuanya|semua sekali|both|kedua|kedua-duanya)[.!\s]*$",
    re.IGNORECASE,
)
_ALL_EXACT_RE = re.compile(
    r"^(all|all of them|all of it|everything|every one|semua|semuanya|semua sekali|both|kedua|kedua-duanya)$",
    re.IGNORECASE,
)
_DIGITS_ONLY_RE = re.compile(
    r"^#?\s*[0-9]+(\s*(?:,|and|&|\+)?\s*[0-9]+)*[\s.!]*$", re.IGNORECASE
)
_BARE_NUMBER_RE = re.compile(r"^#?\s*[0-9]+$")
_OPTION_ANY_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:option|number|no\.?|choice)\s*#?\s*[0-9]+"
)
_PROMO_TEAM_RE = re.compile(r"^marketing_promotion_(sorento|cabana|mocha)$")
_HONORIFIC_RE = re.compile(r"^(ms|miss|mrs|mr|encik|en|puan|pn|cik|tuan|dato|datin|dr)\.?\s+")
_ISO_DATE_RE = re.compile(r"^[0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}$")
_SHORT_DATE_RE = re.compile(r"^[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4}$")
_FENCE_RE = re.compile(r"```[\s\S]*?```")
_FENCE_MARK_RE = re.compile(r"```json?|```")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
# U+2010..U+2015, U+2212, U+FE58, U+FE63, U+FF0D - the copy-paste dashes Excel / Word /
# Sheets / PDF emit instead of ASCII '-' (observed live, exec 12053189).
_DASHES = re.compile("[‐-―−﹘﹣－]")


def _split_reply_to(message: Any) -> str:
    """`String(m ?? '').split(/\\s*reply to:/i)[0]` - strip the quoted tail n8n appends."""
    return _REPLY_TO_SPLIT.split(jsc.nullish_str(message))[0]


def _ce_norm(value: Any) -> str:
    return jsc.nullish_str(value).strip().lower()


def _ce_key(e: Any) -> str:
    code = jsc.get(e, "canonical_code") if jsc.truthy(jsc.get(e, "canonical_code")) else jsc.get(e, "raw")
    return _ce_norm(jsc.get(e, "hint")) + "|" + _ce_norm(code if jsc.truthy(code) else "")


def _ce_keys_of(e: Any) -> list[str]:
    """Both forms of an entity's key.

    `_ceKey` collapses to `canonical_code || raw`, so the SAME entity keys differently
    depending on whether it has been resolved yet: prior state holds a picked customer as
    `customer|dbr-59e57de1b7` while the LLM re-emits it as `customer|yoo living house`.
    Comparing on BOTH forms is what stops the eviction pass dropping it (exec 13246777).
    """
    prefix = _ce_norm(jsc.get(e, "hint")) + "|"
    out = []
    if jsc.truthy(jsc.get(e, "canonical_code")):
        out.append(prefix + _ce_norm(jsc.get(e, "canonical_code")))
    if jsc.truthy(jsc.get(e, "raw")):
        out.append(prefix + _ce_norm(jsc.get(e, "raw")))
    return out or [_ce_key(e)]


def _offer_is_open(state: Any) -> bool:
    """R3 / AC-106: is an escalation offer open? BOTH forms, during the migration window.

    The JS decided this by matching the frozen phrase "would you like me to escalate"
    against the previous reply - H13's frozen string contract, and D11's own counter
    example (understanding text is the parser's job). S2 writes `pending.kind =
    escalation_offer` instead; S8 deletes the regex. Until then a session written by n8n
    carries only the string and a session written by the CRM carries the marker, so the
    reader accepts either and neither deployment order strands a customer mid-offer.
    """
    if jsc.get(jsc.get(state, "pending"), "kind") == "escalation_offer":
        return True
    response = jsc.get(state, "response")
    return bool(
        _OFFERED_ESCALATION_RE.search(jsc.js_string(response if jsc.truthy(response) else ""))
    )


def _unwrap(json_item: dict) -> dict:
    """The node's own opening lines: get to `{output: <the LLM object>}`.

    The AI Agent hands back either a JSON STRING (every one of the 116 captured inputs) or
    an already-shaped object - `mock-reformulator-output` returns `{output: <object>}`, so
    the object branch takes it whole. The string branch strips code fences, then slices
    from the first `{` to the last `}` because the model occasionally wraps the object in
    prose.
    """
    raw_output = json_item.get("output")
    if isinstance(raw_output, dict):
        return raw_output
    raw = jsc.js_string(raw_output if jsc.truthy(raw_output) else "")
    raw = _FENCE_RE.sub(lambda m: _FENCE_MARK_RE.sub("", m.group(0)), raw)
    idx = raw.find("{")
    if idx == -1:
        return {"output": raw, "quick_reply": json_item.get("quick_reply")}
    start_slice = raw[idx:]
    last = start_slice.rfind("}")
    clean_slice = start_slice[: last + 1] if last != -1 else start_slice
    return {"output": json.loads(clean_slice)}


def output_exchange(json_item: dict, parent_input: dict) -> dict:
    """One n8n item through the post-processor. The fixture-facing entry point."""
    return post_process(_unwrap(json_item), json_item, parent_input or {})


def post_process(output: dict, json_item: dict, parent_input: dict) -> dict:  # noqa: C901, PLR0912, PLR0915
    """The body. `output` is `{output: <the LLM object>}`; returns it with `_parser_raw`.

    The CRM calls this directly: `parser.parse` already returns a validated dict, so there
    is no string to unwrap and no reason to re-serialise one just to parse it back.
    """
    parent_input = parent_input or {}
    json_item = json_item or {}
    norm = jsc.norm

    if not isinstance(output.get("output"), dict):
        # n8n limped on with a string here and threw a few lines later on
        # `reference_positions.length`. R5 makes it explicit: a failed `understood` stage.
        raise ParserOutputError("parser did not emit a JSON object")

    o: dict[str, Any] = output["output"]

    # -- state-transition monitor: snapshot the RAW LLM object BEFORE any post-processing.
    # Everything below mutates `o`; this is the only point where the pre-code shape exists.
    try:
        parser_raw_snapshot = json.loads(json.dumps(o))
    except Exception:
        parser_raw_snapshot = None

    # miss-company-routing: the LLM may emit escalation.company_pick. This frozen snapshot
    # is the SOLE pick source; strip the raw key so an unvalidated value never rides the
    # live escalation object (and never diffs golden turns).
    try:
        esc0 = o.get("escalation")
        if isinstance(esc0, dict) and "company_pick" in esc0:
            del esc0["company_pick"]
    except Exception:
        pass

    # -- B2' CARRIED-ENTITY PROVENANCE ------------------------------------------------- #
    # "Carried" is derived from PROVENANCE, never from `current_message`: applyDymPick
    # re-maps EVERY prior entity to `current_message: true` before the executor runs. The
    # uncorrupted this-turn signal is the frozen snapshot.
    prev_state_entities = jsc.array(jsc.get(parent_input.get("previous_conversation_state"), "entities"))
    ce_prior_keys_any = {k for e in prev_state_entities for k in _ce_keys_of(e)}
    ce_llm_keys_any = {
        k for e in jsc.array(jsc.get(parser_raw_snapshot, "entities")) for k in _ce_keys_of(e)
    }
    # Codes minted by applyDymPick THIS TURN are genuine this-turn choices, so they are
    # RECORDED rather than inferred.
    ce_dym_picked_keys: set[str] = set()
    # M2: the SAME record-don't-infer pattern for REFERENCE POSITIONS. B2' tested the
    # persisted `e.ordinal`, which lives forever, so a positional pick was exempt from
    # eviction for the rest of the session.
    ce_ref_picked_keys: set[str] = set()

    def ce_is_carried(e: Any) -> bool:
        if not jsc.truthy(e):
            return False
        if _ce_key(e) in ce_ref_picked_keys:
            return False
        if _ce_key(e) in ce_dym_picked_keys:
            return False
        ks = _ce_keys_of(e)
        return any(k in ce_prior_keys_any for k in ks) and not any(k in ce_llm_keys_any for k in ks)

    # -- hoist raw LLM signals + coerce string-"null" hints ----------------------------- #
    # (a) Capture the LLM's RAW message_type + routing at the TOP, BEFORE any downstream
    #     mutation. The retarget intent must be immune to ALL of them.
    llm_msg_type_raw = o.get("message_type")
    req_help = llm_msg_type_raw == "request_for_help"
    llm_team_raw = jsc.get(o.get("routing"), "suggested_team")
    llm_agent_raw = jsc.get(o.get("routing"), "suggested_agent")
    llm_team_n = norm(llm_team_raw)
    llm_agent_n = norm(llm_agent_raw)
    # B-TEAM-1': the LLM's OWN confidence marker for the team it named this turn.
    llm_team_source_raw = jsc.get(o.get("routing"), "team_source")
    llm_team_source_n = (
        llm_team_source_raw if llm_team_source_raw in ("explicit", "inferred") else None
    )
    # (b) The LLM occasionally emits the LITERAL STRING "null" for a hint. That is truthy,
    #     so it mis-fires the domain->business_query clobber. Coerce to real null here.
    o["domain_hint"] = norm(o.get("domain_hint"))
    o["intent_hint"] = norm(o.get("intent_hint"))

    # reuse means "no new value this turn" - but if the parser emitted current entities it
    # contradicts itself. Promote to additive replace_combine so the new value survives.
    prior_ents0 = prev_state_entities
    if (
        o.get("entity_op") == "reuse"
        and jsc.is_array(o.get("entities"))
        and len(o["entities"]) > 0
        and (
            any(jsc.get(e, "current_message") is True for e in o["entities"])
            or len(prior_ents0) == 0
        )
    ):
        if len(prior_ents0) == 0:
            o["entities"] = [{**e, "current_message": True} for e in o["entities"]]
        o["entity_op"] = "replace_combine"
        o["entity_op_corrected"] = "reuse->replace_combine"

    if o.get("domain_hint") == "resource_attachment":
        ents = jsc.array(o.get("entities"))
        if any(jsc.lower_or_empty(jsc.get(e, "hint")) == "product" for e in ents):
            o["domain_hint"] = "product_attachment"
            o["intent_hint"] = "check_product_attachment"
            o["domain_corrected"] = "resource_attachment->product_attachment (product present)"

    # -- MENU-LABEL OVERRIDE ------------------------------------------------------------ #
    # Exact menu/button labels are SELECTIONS (-> portal link), not free-text queries.
    # Matched against the ORIGINAL user message, not the LLM output.
    user_msg_raw = json_item.get("user_message")
    if user_msg_raw is None:
        user_msg_raw = json_item.get("latest_user_message")
    if user_msg_raw is None:
        user_msg_raw = ""
    user_msg = jsc.js_string(user_msg_raw).strip().lower()
    menu_hit = MENU_LABELS.get(user_msg)
    if menu_hit:
        o["message_type"] = "business_query"
        o["intent_hint"] = menu_hit["intent_hint"]
        o["domain_hint"] = menu_hit["domain_hint"]
        o["portal"] = menu_hit["portal"]
        o["entities"] = []  # a label has no filter entities
        o["is_menu_label"] = True

    # -- FLYER INJECTION ---------------------------------------------------------------- #
    # Flyer is a resource-type filter that COEXISTS with brand/category, not a scope
    # competitor. Its own hint means the axis/replace logic never drops it.
    if not jsc.truthy(o.get("is_menu_label")) and o.get("contains_flyer") is True:
        ents = jsc.array(o.get("entities"))
        if not any(jsc.lower_or_empty(jsc.get(e, "raw")) == "flyer" for e in ents):
            ents.append({"raw": "flyer", "hint": "flyer", "current_message": True})
        o["entities"] = ents

    # -- DID-YOU-MEAN PICK RECONCILIATION ----------------------------------------------- #
    def apply_dym_pick(hit: dict, offer: Any, prior_ents: Any, use_slot: bool) -> list:
        """RETAIN all prior entities, REPLACE only the source token's entity in place.

        Shared by the code-reply path (`try_dym_pick`, slot matching ON) and the numbered
        multi-select handler (slot matching OFF, so multi-picks ACCUMULATE - ADD-BOTH).
        """
        def n(s: Any) -> str:
            return jsc.nullish_str(s).strip().lower()

        pv = parent_input.get("previous_conversation_state") or {}
        prior = [dict(e) for e in jsc.array(prior_ents)]
        # The offer id, stamped onto the picked entity, is a STABLE handle back to the
        # offer: the first pick overwrites raw, destroying the for_raw linkage.
        slot = offer.get("id") if isinstance(offer, dict) and offer.get("id") is not None else None

        idx = -1
        if use_slot is not False and slot is not None:
            idx = jsc.find_index(
                prior,
                lambda e: jsc.truthy(e)
                and jsc.get(e, "dym_slot") is not None
                and n(jsc.get(e, "dym_slot")) == n(slot),
            )
        if idx < 0:
            idx = jsc.find_index(prior, lambda e: n(jsc.get(e, "raw")) == n(hit.get("for_raw")))
        if idx < 0 and jsc.truthy(hit.get("for_canonical")):
            idx = jsc.find_index(
                prior, lambda e: n(jsc.get(e, "canonical_code")) == n(hit.get("for_canonical"))
            )
        # A hint is a TYPE, not an identity, so this last tier is a guess - and on a path
        # whose whole contract is ADD-BOTH, a pick that cannot be tied to its own source
        # token must ADD, never guess. The `_ceDymPickedKeys` exclusion stops the second
        # candidate of a multi-pick landing on the first pick's own entity (exec 13203346).
        if idx < 0 and use_slot is not False and jsc.truthy(hit.get("for_hint")):
            same_hint = [
                e
                for e in prior
                if n(jsc.get(e, "hint")) == n(hit.get("for_hint"))
                and _ce_key(e) not in ce_dym_picked_keys
            ]
            if len(same_hint) == 1:
                # `indexOf` is IDENTITY in JS. `list.index` compares by equality, so two
                # entities that happen to be equal dicts would both resolve to the first.
                idx = next(i for i, e in enumerate(prior) if e is same_hint[0])

        # FORCE the type from the candidate record - entity_type is the PICKED candidate's
        # resolved type; for_hint describes the SOURCE token. Never trust the LLM hint here.
        picked_hint = hit.get("entity_type")
        if not jsc.truthy(picked_hint):
            picked_hint = hit.get("for_hint")
        if not jsc.truthy(picked_hint):
            picked_hint = jsc.get(prior[idx], "hint") if idx >= 0 else None
        picked = {
            "raw": hit.get("code"),
            "hint": picked_hint,
            "canonical_code": hit.get("code"),
            "uuid": hit.get("uuid") if jsc.truthy(hit.get("uuid")) else None,
            "current_message": True,
        }
        if slot is not None:
            picked["dym_slot"] = slot
        ce_dym_picked_keys.add(_ce_key(picked))

        if idx >= 0:
            prior[idx] = picked
            final = [{**e, "current_message": True} for e in prior]
        else:
            final = [picked] + [{**e, "current_message": True} for e in prior]
            o["dym_replace_unmatched"] = True

        o["entity_op"] = "replace_combine"
        o["scope_exclusive"] = False  # IGNORE the LLM's scope_exclusive=true
        o["message_type"] = "business_query"
        # carry the prior date window if THIS turn named none
        if not (jsc.truthy(o.get("date_filter_start")) or jsc.truthy(o.get("date_filter_end"))):
            if jsc.truthy(pv.get("date_filter_start")):
                o["date_filter_start"] = pv["date_filter_start"]
            if jsc.truthy(pv.get("date_filter_end")):
                o["date_filter_end"] = pv["date_filter_end"]
            if jsc.truthy(pv.get("date_mode")):
                o["date_mode"] = pv["date_mode"]
        o["dym_pick_applied"] = True
        o["dym_offer_pick_code"] = hit.get("code")
        # #5 domain-carry: a CONFIRMED, UNAMBIGUOUS pick STAYS in the offer's domain.
        # STRICT gate: force ONLY when the whole message IS the picked code, or the pick
        # came through the numbered handler. An offered code inside a larger NEW-domain
        # phrase is neither, so the parser's classified domain passes through.
        is_bare_code = n(hit.get("code")) == n(_split_reply_to(parent_input.get("latest_user_message")))
        via_numbered = use_slot is False
        if (is_bare_code or via_numbered) and isinstance(offer, dict) and jsc.truthy(offer.get("domain")):
            o["domain_hint"] = offer["domain"]
            o["intent_hint"] = pv.get("intent_hint") if pv.get("intent_hint") is not None else None
            o["dym_pick_domain_forced"] = offer["domain"]
        return final

    def try_dym_pick() -> None:
        prev = parent_input.get("previous_conversation_state") or {}
        # Source candidates from the offer object; fall back to the legacy flat array
        # during the spine/parser promotion window.
        offer = prev.get("dym_offer") if isinstance(prev.get("dym_offer"), dict) else None
        cands = (
            offer["candidates"]
            if offer is not None and jsc.is_array(offer.get("candidates"))
            else jsc.array(prev.get("dym_candidates"))
        )
        if not len(cands):
            return

        def n(s: Any) -> str:
            return jsc.nullish_str(s).strip().lower()

        def is_date_like(s: Any) -> bool:
            v = jsc.nullish_str(s).strip()
            return bool(_ISO_DATE_RE.match(v) or _SHORT_DATE_RE.match(v))

        msg = n(_split_reply_to(parent_input.get("latest_user_message")))
        cur_ents = [
            e
            for e in jsc.array(o.get("entities"))
            if jsc.truthy(e) and jsc.get(e, "current_message") is True
        ]

        def code_matches(c: Any) -> bool:
            if is_date_like(jsc.get(c, "code")):
                return False
            if n(jsc.get(c, "code")) == msg:
                return True
            return any(
                n(jsc.get(e, "raw")) == n(jsc.get(c, "code"))
                or n(jsc.get(e, "canonical_code")) == n(jsc.get(c, "code"))
                for e in cur_ents
            )

        # picked[] is a RECORD, not a filter - re-picking the same code is idempotent, so
        # codes already in offer.picked are NOT skipped. That is what makes a SECOND pick
        # from the same offer work.
        hit = jsc.find(cands, code_matches)
        if hit is None:
            return
        o["entities"] = apply_dym_pick(hit, offer, prev.get("entities"), True)

    try_dym_pick()

    # -- REVISION 4: intent-only effective domain signal --------------------------------- #
    explicit = o.get("intent_hint") in DECISIVE_INTENTS and jsc.truthy(o.get("domain_hint"))
    o["domain_signal_source"] = "intent_explicit" if explicit else "intent_none"

    # -- #6: deterministic domain-SWITCH word signal (this-turn-only) -------------------- #
    # A bare/dominant domain word in the CURRENT message must SWITCH domain, not let the
    # continuity carry reuse the prior one (repro exec 10826285: "promo" after a stock
    # turn -> stock again). Whole-word, case-insensitive.
    switch_domain: str | None = None
    if not explicit:
        sw_msg = _split_reply_to(parent_input.get("latest_user_message")).lower()
        sw_toks = [t for t in _TOKEN_RE.findall(sw_msg) if t not in SWITCH_FILLER]
        # defense-in-depth: a current-message entity means this is a real query
        sw_has_cur_ent = any(
            jsc.truthy(e) and jsc.get(e, "current_message") is True
            for e in jsc.array(o.get("entities"))
        )
        if len(sw_toks) >= 1 and not sw_has_cur_ent:
            sw_doms = [DOMAIN_SWITCH_WORDS.get(t) for t in sw_toks]
            # EVERY remaining content token must be a switch word of the SAME domain.
            if all(d is not None for d in sw_doms) and len(set(sw_doms)) == 1:
                switch_domain = sw_doms[0]

    ce_unknown_hints: set[str] = set()

    def ce_axis_for(e: Any, domain: Any) -> str:
        hint = jsc.lower_or_empty(jsc.get(e, "hint"))
        domain_map = AXIS_BY_DOMAIN.get(domain) if isinstance(domain, str) else None
        known = (domain_map or {}).get(hint) or HINT_AXIS_DEFAULT.get(hint)
        if known:
            return known
        if hint:
            ce_unknown_hints.add(hint)
        return DOMAIN_SUBJECT_AXIS.get(domain, "unscoped_scope") if isinstance(domain, str) else "unscoped_scope"

    # -- DATE-WIDEN RE-ATTACH (deterministic; no prompt change) -------------------------- #
    # After a windowed answer, the bare widen reply "all dates" came back as
    # scope_intent 'broaden' + entity_op 'clear' + entities [] + domain null, the executor
    # wiped the carried scope and the clarifier improvised (execs 13873180 -> 13873625).
    # This arm re-emits the shape of the turn that WORKED, with the window forced open.
    def compute_date_widen() -> bool:
        if jsc.truthy(o.get("is_menu_label")):
            return False
        # a did-you-mean code reply is its own re-attach; never re-widen off entities it
        # just minted.
        if o.get("dym_pick_applied") is True:
            return False
        msg = _split_reply_to(parent_input.get("latest_user_message")).strip().lower()
        if not msg:
            return False
        kept = [t for t in _TOKEN_RE.findall(msg) if t not in DW_FILLERS]
        if " ".join(kept) not in DW_PHRASES:
            return False
        pv = parent_input.get("previous_conversation_state") or {}
        if not (jsc.is_array(pv.get("entities")) and len(pv["entities"])):
            return False  # (2) nothing to widen onto
        if not (jsc.truthy(pv.get("date_filter_start")) or jsc.truthy(pv.get("date_filter_end"))):
            return False  # (3) no window to drop
        return True

    date_widen = compute_date_widen()
    if date_widen:
        o["entity_op"] = "reuse"
        o["message_type"] = "business_query"
        # ONE axis widened, not an entity broaden - the broaden-blocklist must not strip
        # the carried scope.
        o["scope_intent"] = None
        # LLM-misread neutralisation, widen turns only.
        o["is_affirmative"] = None
        o["person_mention"] = None
        o["reference_positions"] = []
        o["reference_target"] = None
        o["escalation"] = {"is_escalation_confirmation": False}
        o["date_widen_applied"] = True

    prev_state_domain = jsc.get(parent_input.get("previous_conversation_state"), "domain_hint") or None

    # -- AXIS BROADEN: naming a KIND of thing widens one filter, not the subject --------- #
    # exec 13624889: after "srt59-cr for mastile klang" in the order domain, "all products"
    # came back master_products / entity_op clear - it jumped to the catalogue AND dropped
    # the customer. Restore the domain BEFORE the executor.
    ba = jsc.lower_or_empty(o.get("broaden_axis"))
    prev_dom0 = prev_state_domain
    wandered_dom0 = o.get("domain_hint") if jsc.truthy(o.get("domain_hint")) else None
    if ba and jsc.truthy(prev_dom0):
        o["domain_hint"] = prev_dom0
        prev_intent = jsc.get(parent_input.get("previous_conversation_state"), "intent_hint")
        o["intent_hint"] = (
            prev_intent
            if jsc.truthy(prev_intent)
            else (o.get("intent_hint") if jsc.truthy(o.get("intent_hint")) else None)
        )
        o["broaden_axis_domain_restored"] = True

        # exec 13728314: "all products" on an order in progress came back entity_op
        # "clear" + broaden_axis "all" + scope_intent the STRING "null" - the model misread
        # ONE axis being widened as a request for the whole catalogue. A genuine
        # broaden-everything turn must still clear; only a MISREAD "all" is rescued.
        scope_intent = jsc.nullish_str(o.get("scope_intent")).lower()
        if ba == "all" and scope_intent != "broaden":
            if o.get("entity_op") == "clear":
                o["entity_op"] = "reuse"
                o["broaden_axis_clear_rescued"] = True
            # The domain the model wandered TO names the axis it actually meant.
            wandered_hint = DOMAIN_SUBJECT_HINT.get(wandered_dom0) if wandered_dom0 else None
            if jsc.truthy(wandered_hint):
                o["broaden_axis"] = wandered_hint
                o["broaden_axis_resolved_from_domain"] = wandered_dom0
            # an unmapped wandered domain leaves broaden_axis as "all" - fail open.

    # -- ENTITY OPERATION EXECUTOR (op + axis-aware replace/combine) --------------------- #
    if not jsc.truthy(o.get("is_menu_label")):
        domain = o.get("domain_hint")

        def axis_of(e: Any) -> str:
            return ce_axis_for(e, domain)

        op = o.get("entity_op") if jsc.truthy(o.get("entity_op")) else "replace_combine"
        all_ents = jsc.array(o.get("entities"))
        # split on the flag the PARSER set - do NOT override it
        current = [e for e in all_ents if jsc.get(e, "current_message") is True]
        prior = [{**e, "current_message": False} for e in prev_state_entities]

        if op == "clear":
            final_entities: list = []
        elif op == "reuse":
            final_entities = prior
            has_current_date = jsc.truthy(o.get("date_filter_start")) or jsc.truthy(
                o.get("date_filter_end")
            )
            pcs = parent_input.get("previous_conversation_state")
            # broaden_axis "date" = the user explicitly asked to drop the window. Such a
            # turn names no date, so the carry below would silently restore the PREVIOUS
            # window and answer the opposite of what was asked.
            all_time = jsc.lower_or_empty(o.get("broaden_axis")) == "date"
            if all_time:
                o["date_filter_start"] = None
                o["date_filter_end"] = None
                o["date_mode"] = None
            elif not has_current_date:
                if jsc.truthy(jsc.get(pcs, "date_filter_start")):
                    o["date_filter_start"] = jsc.get(pcs, "date_filter_start")
                if jsc.truthy(jsc.get(pcs, "date_filter_end")):
                    o["date_filter_end"] = jsc.get(pcs, "date_filter_end")
                if jsc.truthy(jsc.get(pcs, "date_mode")):
                    o["date_mode"] = jsc.get(pcs, "date_mode")

            # requested_attributes: the PERSPECTIVE of the question is an axis the pick
            # turn did not name - carry it like the date window (exec 13951947).
            cur_attrs = [a for a in jsc.array(o.get("requested_attributes")) if jsc.truthy(a)]
            prev_attrs = [
                a for a in jsc.array(jsc.get(pcs, "requested_attributes")) if jsc.truthy(a)
            ]
            if len(cur_attrs) == 0 and len(prev_attrs) > 0:
                o["requested_attributes"] = prev_attrs

            # is_active: only carry if THIS turn left it null (no status word)
            cur_active = norm(o.get("is_active"))
            if (
                cur_active is None
                and jsc.has(pcs, "is_active")
                and norm(jsc.get(pcs, "is_active")) is not None
            ):
                o["is_active"] = jsc.get(pcs, "is_active")
            # domain continuity for entity-less reuse (e.g. "and the price?")
            if o.get("message_type") != "casual" and o.get("message_type") != "request_for_help":
                if not explicit and not switch_domain:  # a domain switch beats the carry
                    o["domain_hint"] = (
                        jsc.get(pcs, "domain_hint")
                        if jsc.truthy(jsc.get(pcs, "domain_hint"))
                        else (o.get("domain_hint") if jsc.truthy(o.get("domain_hint")) else None)
                    )
                    o["intent_hint"] = (
                        jsc.get(pcs, "intent_hint")
                        if jsc.truthy(jsc.get(pcs, "intent_hint"))
                        else (o.get("intent_hint") if jsc.truthy(o.get("intent_hint")) else None)
                    )
                    o["domain_reused_entityless"] = True
        else:  # 'modify' | 'replace_combine' | anything else
            current_axes = {axis_of(e) for e in current}
            exclusive = o.get("scope_exclusive") is True
            if exclusive:
                if len(current) == 0:
                    # "restrict to only [nothing]" is meaningless - almost always a
                    # tier/attribute change, not an entity narrow. Keep prior.
                    kept_prior = prior
                    o["exclusive_ignored_no_current"] = True
                else:
                    kept_prior = []  # genuine exclusive: current IS the full scope
            else:
                kept_prior = [e for e in prior if axis_of(e) not in current_axes]
            final_entities = [*current, *kept_prior]
            o["scope_exclusive_applied"] = exclusive

        o["entities"] = final_entities
        o["entity_op_applied"] = op

    # -- DATE-WIDEN RE-ATTACH, part 2 ---------------------------------------------------- #
    # Runs AFTER the executor because the reuse arm has just RESTORED the prior window. The
    # domain pin exists because a date widen is ALWAYS about whatever the user is already
    # asking about; it is never evidence of a shipment question.
    if date_widen:
        o["date_filter_start"] = None
        o["date_filter_end"] = None
        o["date_mode"] = None
        dw_pv = parent_input.get("previous_conversation_state") or {}
        if jsc.truthy(dw_pv.get("domain_hint")):
            o["domain_hint"] = dw_pv["domain_hint"]
            o["intent_hint"] = dw_pv.get("intent_hint") if jsc.truthy(dw_pv.get("intent_hint")) else None

    prev_state = parent_input.get("previous_conversation_state") or {}

    # order_status: order delivery-status filter (outstanding|delivered|null).
    if not jsc.has(o, "order_status"):
        o["order_status"] = None
    if o.get("order_status") != "outstanding" and o.get("order_status") != "delivered":
        o["order_status"] = o.get("order_status") if jsc.truthy(o.get("order_status")) else None

    # -- TIER-ONLY ACCESS ASK ------------------------------------------------------------ #
    # (a) a positional / tier-word reply to the tier ask resolves to TIER TOKENS in
    #     access_levels, NEVER to entities. Keyed STRICTLY on selection_context so it can
    #     never shadow member_offer / suggest_offer / disambiguation (TA-14).
    def tier_offer_pick() -> None:
        if jsc.truthy(o.get("is_menu_label")):
            return
        if jsc.nullish_str(prev_state.get("selection_context") or "") != "tier_offer":
            return
        roster = [
            r
            for r in jsc.array(prev_state.get("last_result_set"))
            if jsc.truthy(r)
            and jsc.lower_or_empty(
                r.get("tier") if r.get("tier") is not None else r.get("value")
            )
            in TIER_ORDER
        ]
        if not roster:
            return

        def tier_of(r: dict) -> str:
            return jsc.lower_or_empty(r.get("tier") if r.get("tier") is not None else r.get("value"))

        msg = _split_reply_to(parent_input.get("latest_user_message")).strip().lower()
        is_all = bool(_ALL_RE.match(msg))
        pos = [
            jsc.js_number(p)
            for p in jsc.array(o.get("reference_positions"))
        ]
        pos = [p for p in pos if jsc.is_integer(p) and p >= 1]
        # the LLM often tags a bare number `casual` with no positions - extract digits
        # ourselves, but ONLY from a digits-and-connectives reply, never a query.
        if not pos and _DIGITS_ONLY_RE.match(msg):
            pos = [jsc.js_number(d) for d in re.findall(r"[0-9]+", msg)]
        stated = _stated_tiers(msg, o.get("entities"))
        chosen = set(stated)
        if is_all:
            for r in roster:
                chosen.add(tier_of(r))
        for p in pos:
            r = jsc.find(roster, lambda x, _p=p: jsc.js_number(jsc.get(x, "idx")) == _p)
            if r is not None:
                chosen.add(tier_of(r))  # an out-of-range position is simply not a pick
        if not chosen:
            return  # no pick signal -> a new query / casual abandons the ask
        o["access_levels"] = [t for t in TIER_ORDER if t in chosen]
        # (c) carry the ORIGINAL scope to the answer turn - S5-shaped, own flag
        prev_ents = jsc.array(prev_state.get("entities"))
        if prev_ents:
            o["entities"] = [{**x, "current_message": False} for x in prev_ents]
            o["entity_op"] = "reuse"
        if not (jsc.truthy(o.get("date_filter_start")) or jsc.truthy(o.get("date_filter_end"))):
            if jsc.truthy(prev_state.get("date_filter_start")):
                o["date_filter_start"] = prev_state["date_filter_start"]
            if jsc.truthy(prev_state.get("date_filter_end")):
                o["date_filter_end"] = prev_state["date_filter_end"]
            if jsc.truthy(prev_state.get("date_mode")):
                o["date_mode"] = prev_state["date_mode"]
        o["_tier_pick_scope_reused"] = True
        o["domain_hint"] = "promotion"
        o["intent_hint"] = (
            prev_state.get("intent_hint") if jsc.truthy(prev_state.get("intent_hint")) else "check_promotion"
        )
        o["message_type"] = "business_query"
        o["scope_intent"] = None
        # consumed: the positions were TIER picks - they must not mint entities off the
        # roster nor re-trigger the S5 promo scope-reuse below.
        o["reference_positions"] = []
        o["reference_target"] = None

    tier_offer_pick()

    # (b)+(d) stated tiers -> access_levels as TIER TOKENS, every turn. Deterministic and
    # idempotent. D9: the brand must be harvested HERE because this is the LAST point
    # where the raw compound level still exists ("Cabana Dealer" becomes ["dealer"] one
    # line later and the brand is unrecoverable). Word order must not decide a SECURITY
    # BOUNDARY, so statedBrands unions entity, level and message.
    msg_t = _split_reply_to(parent_input.get("latest_user_message"))
    raw_levels = [
        *jsc.array(jsc.get(parser_raw_snapshot, "access_levels")),
        *jsc.array(o.get("access_levels")),
    ]
    o["query_brands"] = _stated_brands(o.get("entities"), raw_levels, msg_t)
    # F7: the brand is part of the QUERY SCOPE, so it must travel with the scope. Two
    # conditions, both required, so the carry can never widen or silently narrow.
    if not len(o["query_brands"]):
        prev_brands = [
            b for b in jsc.array(prev_state.get("query_brands")) if jsc.nullish_str(b).lower() in BRANDS
        ]
        ents = jsc.array(o.get("entities"))
        reusing_scope = o.get("entity_op") == "reuse" or (
            len(ents) > 0
            and not any(jsc.truthy(e) and jsc.get(e, "current_message") is True for e in ents)
        )
        if prev_brands and reusing_scope:
            o["query_brands"] = [b for b in BRANDS if b in prev_brands]
            o["_query_brands_carried"] = True

    tier_set = set(_stated_tiers(msg_t, o.get("entities")))
    for a in raw_levels:
        s = jsc.nullish_str(a).strip().lower()
        if s in TIER_ORDER:
            tier_set.add(s)
            continue
        p = _parse_level(a)
        if p:
            tier_set.add(p["tier"])
    o["access_levels"] = [t for t in TIER_ORDER if t in tier_set]
    # F4(b): carry the PICKED TIER across a continuation of the SAME question. Same
    # predicate as the brand carry; kept separate because the two axes can legitimately
    # disagree (new brand, same tier).
    if not len(o["access_levels"]):
        prev_tiers = [
            t
            for t in (jsc.nullish_str(x).strip().lower() for x in jsc.array(prev_state.get("access_levels")))
            if t in TIER_ORDER
        ]
        ents2 = jsc.array(o.get("entities"))
        reusing2 = o.get("entity_op") == "reuse" or (
            len(ents2) > 0
            and not any(jsc.truthy(e) and jsc.get(e, "current_message") is True for e in ents2)
        )
        if prev_tiers and reusing2:
            o["access_levels"] = [t for t in TIER_ORDER if t in prev_tiers]
            o["_tier_carried"] = True

    # -- "ALL / SEMUA" on a numbered menu -> expand to EVERY offered position ------------ #
    sel_ctx0 = jsc.nullish_str(prev_state.get("selection_context") or "")
    # A quote-reply delivers the replied-to menu in referenced_result_set - prefer it over
    # the immediate last_result_set, and treat its presence as a pick-context.
    ref_set = jsc.array(parent_input.get("referenced_result_set"))
    lrs_all = ref_set if len(ref_set) > 0 else jsc.array(prev_state.get("last_result_set"))
    pick_ctx = len(ref_set) > 0 or sel_ctx0 in ("disambiguation", "suggest_offer")
    msg_all_src = parent_input.get("latest_user_message")
    if msg_all_src is None:
        msg_all_src = parent_input.get("user_message")
    if msg_all_src is None:
        msg_all_src = user_msg
    msg_all = re.sub(r"[.!\s]+$", "", _split_reply_to(msg_all_src).strip().lower())
    is_all0 = bool(_ALL_EXACT_RE.match(msg_all))
    no_pos = not jsc.is_array(o.get("reference_positions")) or len(o["reference_positions"]) == 0
    # #4: "all" over an ACTIVE did-you-mean offer selects EVERY suggestion. STRUCTURAL gate
    # (a non-empty dym_last_result_set persisted on the partial-miss turn), no marker regex.
    dym_active = jsc.is_array(prev_state.get("dym_last_result_set")) and len(
        prev_state["dym_last_result_set"]
    ) > 0
    if is_all0 and no_pos and dym_active:
        o["reference_positions"] = [
            n
            for n in (jsc.js_number(jsc.get(r, "idx")) for r in prev_state["dym_last_result_set"])
            if jsc.is_integer(n)
        ]
        o["reference_target"] = "dym"  # dymNumberedMultiSelect catches this forced route
        o["scope_intent"] = None  # cancel the LLM's broaden reading
        o["message_type"] = "business_query"
        o["select_all_expanded"] = True
    elif is_all0 and pick_ctx and len(lrs_all) > 0 and no_pos:
        o["reference_positions"] = [
            n for n in (jsc.js_number(jsc.get(r, "idx")) for r in lrs_all) if jsc.is_integer(n)
        ]
        o["scope_intent"] = None  # NOT a broaden
        o["entity_op"] = "reuse"
        o["message_type"] = "business_query"
        if not jsc.truthy(o.get("domain_hint")):
            o["domain_hint"] = prev_state.get("domain_hint")
        if not jsc.truthy(o.get("intent_hint")):
            o["intent_hint"] = prev_state.get("intent_hint")
        o["select_all_expanded"] = True

    if (
        not jsc.truthy(o.get("domain_hint"))
        and jsc.truthy(prev_state.get("domain_hint"))
        and len(o["reference_positions"]) > 0
    ):
        o["domain_hint"] = prev_state.get("domain_hint")
        o["intent_hint"] = (
            o.get("intent_hint") if jsc.truthy(o.get("intent_hint")) else prev_state.get("intent_hint")
        )
        o["message_type"] = "business_query"
        o["domain_inherited_for_position"] = True

    # pick under a menu business_query, even if the LLM carried a domain_hint
    if (
        prev_state.get("selection_context") == "disambiguation"
        and jsc.is_array(o.get("reference_positions"))
        and len(o["reference_positions"]) > 0
        and o.get("message_type") == "casual"
    ):
        o["message_type"] = "business_query"

    # -- NUMBERED did-you-mean MULTI-SELECT handler -------------------------------------- #
    # A positional reply tagged reference_target='dym' resolves against the SEPARATE
    # dym_last_result_set. LOOP every position (ADD-BOTH): each picked row goes through the
    # shared applyDymPick with slot matching OFF, threading the entity set so replacements
    # ACCUMULATE. Then clear the positions so the stock byIdx block no-ops this turn.
    def dym_numbered_multi_select() -> None:
        if jsc.truthy(o.get("is_menu_label")):
            return
        if (o.get("reference_target") if o.get("reference_target") is not None else None) != "dym":
            return
        positions = jsc.array(o.get("reference_positions"))
        if len(positions) == 0:
            return
        dym_set = jsc.array(prev_state.get("dym_last_result_set"))
        if len(dym_set) == 0:
            return  # no dym set -> untouched byIdx (backbone guard)
        offer = prev_state.get("dym_offer") if isinstance(prev_state.get("dym_offer"), dict) else None
        by_idx = jsc.JsMap([(jsc.js_number(jsc.get(r, "idx")), r) for r in dym_set])
        base = jsc.array(prev_state.get("entities"))  # retains the resolved stock entity
        applied = False
        for p in positions:
            row = by_idx.get(jsc.js_number(p))
            if row is None:
                continue  # out-of-range position -> skip (never resolve)
            hit = {
                "code": row.get("value") if row.get("value") is not None else row.get("product"),
                "uuid": row.get("uuid") if jsc.truthy(row.get("uuid")) else None,
                "entity_type": row.get("entity_type") if jsc.truthy(row.get("entity_type")) else None,
                "for_raw": row.get("for_raw"),
                "for_hint": row.get("for_hint"),
                "for_canonical": row.get("for_canonical"),
            }
            base = apply_dym_pick(hit, offer, base, False)  # thread; slot-match OFF
            applied = True
        if applied:
            o["entities"] = base
            o["reference_positions"] = []  # consumed -> stock byIdx no-ops this turn

    dym_numbered_multi_select()

    # -- REFERENCE POSITIONS -> ENTITIES ------------------------------------------------- #
    if (
        not jsc.truthy(o.get("is_menu_label"))
        and jsc.is_array(o.get("reference_positions"))
        and len(o["reference_positions"]) > 0
    ):
        last_set = (
            parent_input["referenced_result_set"]
            if jsc.is_array(parent_input.get("referenced_result_set"))
            else jsc.array(prev_state.get("last_result_set"))
        )
        by_idx = jsc.JsMap([(jsc.get(r, "idx"), r) for r in last_set])

        # C2: NEVER stamp a domain name into an entity hint. Prefer the resolver's
        # authoritative entity_type, then the DOMAIN's SUBJECT entity hint. The legacy
        # `|| 'promotion'` tail is DROPPED: a pick on an unknown domain became a
        # *promotion* entity, which is an instance of the same defect.
        def c2_hint(candidate: Any, domain: Any) -> str:
            h = jsc.nullish_str(candidate).strip().lower()
            if h and h in KNOWN_ENTITY_HINTS:
                return h
            return DOMAIN_SUBJECT_HINT.get(domain, "product") if isinstance(domain, str) else "product"

        resolved: list[dict] = []
        out_of_range: list = []
        for pos_raw in o["reference_positions"]:
            pos = jsc.js_number(pos_raw)
            row = by_idx.get(pos)
            if row is None or not jsc.truthy(jsc.get(row, "label")):
                out_of_range.append(pos)
                continue
            label = row["label"]
            sep = label.find(": ")
            if sep != -1:
                before = label[:sep].strip().lower()
                raw = label[sep + 2 :].strip()
                candidate = HINT_MAP.get(before)
                if not jsc.truthy(candidate):
                    candidate = before if jsc.truthy(before) else row.get("entity_type")
                hint = c2_hint(candidate, o.get("domain_hint"))
            else:
                raw = label.strip()
                hint = c2_hint(row.get("entity_type"), o.get("domain_hint"))
            # carry uuid/code straight from the frozen row so it needn't re-resolve
            resolved.append(
                {
                    "raw": raw,
                    "hint": hint,
                    "ordinal": pos,
                    "current_message": True,
                    "uuid": row.get("uuid") if jsc.truthy(row.get("uuid")) else None,
                    "canonical_code": row.get("product") if jsc.truthy(row.get("product")) else raw,
                }
            )
            # M2: this pick was minted THIS TURN - record it, never infer it from `ordinal`.
            ce_ref_picked_keys.add(
                _ce_key(
                    {
                        "hint": hint,
                        "canonical_code": row.get("product") if jsc.truthy(row.get("product")) else raw,
                        "raw": raw,
                    }
                )
            )

        o["entities"] = [*resolved]
        # match_mode: 'or' only when MULTIPLE positions were picked
        # `r.ordinal !== undefined` is a PRESENCE test: a row carrying an explicit
        # `ordinal: null` counts, and `.get(...) is not None` would have dropped it.
        positional_picks = len([r for r in resolved if jsc.has(r, "ordinal")])
        if positional_picks > 1:
            o["match_mode"] = "or"
        o["positions_resolved"] = positional_picks
        o["positions_out_of_range"] = out_of_range

    # (B) product_attachment: re-attach attachment_type if the current turn lacks one.
    if o.get("domain_hint") == "product_attachment":
        current_has_attach_type = any(
            jsc.lower_or_empty(jsc.get(r, "hint")) == "attachment_type" for r in o["entities"]
        ) or any(
            jsc.lower_or_empty(jsc.get(e, "hint")) == "attachment_type"
            and jsc.get(e, "current_message") is True
            for e in jsc.array(o.get("entities"))
        )
        if not current_has_attach_type:
            prior_ents = jsc.array(prev_state.get("entities"))
            for at in [
                e for e in prior_ents if jsc.lower_or_empty(jsc.get(e, "hint")) == "attachment_type"
            ]:
                o["entities"].append(
                    {
                        "raw": at.get("raw"),
                        "hint": at.get("hint"),
                        "canonical_code": at.get("canonical_code"),
                        "current_message": True,
                    }
                )

    # (C) A CUSTOMER PICK NARROWS *WHO*, NOT *WHAT*.
    # The positional path replaces the whole entity set, so answering "Which customer do
    # you mean?" threw the rest of the question away (exec 13214595). Re-attach the prior
    # scope for every OTHER entity type. The customer itself is deliberately NOT carried -
    # replacing it is the entire point of the pick.
    if jsc.is_array(o.get("entities")) and any(
        jsc.truthy(e)
        and jsc.lower_or_empty(jsc.get(e, "hint")) == "customer"
        and jsc.has(e, "ordinal")  # `e.ordinal !== undefined` - presence, not non-null
        for e in o["entities"]
    ):
        cp_prior = jsc.array(prev_state.get("entities"))

        def cp_key(e: Any) -> str:
            code = jsc.get(e, "canonical_code") if jsc.truthy(jsc.get(e, "canonical_code")) else jsc.get(e, "raw")
            return jsc.lower_or_empty(jsc.get(e, "hint")) + "|" + jsc.lower_or_empty(code)

        cp_seen = {cp_key(e) for e in o["entities"]}
        for p in cp_prior:
            h = jsc.lower_or_empty(jsc.get(p, "hint"))
            if not h or h == "customer":
                continue
            k = cp_key(p)
            if k in cp_seen:
                continue
            o["entities"].append({**p, "current_message": True})
            cp_seen.add(k)

    # -- domain continuity for entity-bearing continuations (bare "Y" code) -------------- #
    # Key on the EFFECTIVE domain signal, NOT domain_hint===null. Must run BEFORE
    # blocklist-apply so the correct domain drives the filter.
    if o.get("message_type") != "casual" and o.get("message_type") != "request_for_help":
        if not explicit and not switch_domain:
            prev_dom = jsc.get(parent_input.get("previous_conversation_state"), "domain_hint") or None
            cur_ents = [
                e
                for e in jsc.array(o.get("entities"))
                if jsc.truthy(e) and jsc.get(e, "current_message") is True
            ]
            if jsc.truthy(prev_dom) and len(cur_ents) > 0:
                blocked_for_prev = set(DOMAIN_BLOCKED_HINTS.get(prev_dom, []))
                compatible = all(
                    jsc.lower_or_empty(jsc.get(e, "hint")) not in blocked_for_prev for e in cur_ents
                )
                if compatible:
                    o["domain_hint"] = prev_dom  # OVERRIDE guessed domain
                    prev_intent = jsc.get(parent_input.get("previous_conversation_state"), "intent_hint")
                    o["intent_hint"] = (
                        prev_intent
                        if jsc.truthy(prev_intent)
                        else (o.get("intent_hint") if jsc.truthy(o.get("intent_hint")) else None)
                    )
                    o["domain_inherited_compatible"] = True
                else:
                    o["domain_inherit_blocked"] = prev_dom  # topic switch, kept current

    # #6: a bare/dominant domain-switch word overrides the continuity carry.
    if switch_domain:
        o["domain_hint"] = switch_domain
        o["domain_switched_by_keyword"] = switch_domain
        o["intent_hint"] = None  # downstream re-derives from the new domain

    # -- B2' POST-MERGE ENTITY RECONCILIATION -------------------------------------------- #
    # Placed AFTER every entity-set writer and after the domain carries, so `domain_hint`
    # is FINAL. A wider `prior` filter in the executor could not do this job: applyDymPick
    # promotes carried entities into `current` (which the executor spreads unfiltered) and
    # dymNumberedMultiSelect overwrites the executor's output wholesale afterwards.
    if not jsc.truthy(o.get("is_menu_label")) and jsc.is_array(o.get("entities")):
        rc_domain = o.get("domain_hint")
        rc_ents = o["entities"]
        # INSTANCE-bound attachment scope: a specific certificate NUMBER or attachment.
        # Stale by construction the moment product scope changes (an empty intersection
        # reads to the customer as a confident "no certificate for X"). `attachment_type`
        # is deliberately NOT evictable: it is a TYPE filter that outlives a product change.
        rc_instance_hints = {"certificate", "attachment"}

        rc_contrib_attach = False
        rc_contrib_product = False
        for e in rc_ents:
            if ce_is_carried(e):
                continue
            ax = ce_axis_for(e, rc_domain)
            if ax == "attachment_scope":
                rc_contrib_attach = True
            if ax == "product_scope":
                rc_contrib_product = True
        rc_evict = rc_contrib_attach or rc_contrib_product
        rc_dropped: list[str] = []
        rc_kept = rc_ents
        if rc_evict:
            kept = []
            for e in rc_ents:
                drop = (
                    ce_is_carried(e)
                    and ce_axis_for(e, rc_domain) == "attachment_scope"
                    and _ce_norm(jsc.get(e, "hint")) in rc_instance_hints
                )
                if drop:
                    code = jsc.get(e, "canonical_code") if jsc.truthy(jsc.get(e, "canonical_code")) else jsc.get(e, "raw")
                    rc_dropped.append(jsc.js_string(jsc.get(e, "hint")) + ":" + jsc.js_string(code))
                else:
                    kept.append(e)
            rc_kept = kept

        # Part 5 - dedupe. `current` is spread unconditionally and never pruned, so once
        # applyDymPick promotes the carried set into `current` the list becomes append-only
        # for that axis (five copies of PC 000078 in the observed state).
        rc_seen_key: set[str] = set()
        rc_seen_uuid: set[str] = set()
        rc_out: list = []
        rc_dupes = 0
        for e in rc_kept:
            k = _ce_key(e)
            u = (
                _ce_norm(jsc.get(e, "hint")) + "|" + _ce_norm(jsc.get(e, "uuid"))
                if jsc.truthy(e) and jsc.truthy(jsc.get(e, "uuid"))
                else None
            )
            if k in rc_seen_key or (u and u in rc_seen_uuid):
                rc_dupes += 1
                # never lose a resolution to the dedupe: backfill onto the retained twin
                first = jsc.find(rc_out, lambda x, _k=k: _ce_key(x) == _k)
                if first is None and u:
                    first = jsc.find(
                        rc_out,
                        lambda x, _u=u: jsc.truthy(x)
                        and jsc.truthy(jsc.get(x, "uuid"))
                        and (_ce_norm(jsc.get(x, "hint")) + "|" + _ce_norm(jsc.get(x, "uuid"))) == _u,
                    )
                if first is not None:
                    if not jsc.truthy(first.get("uuid")) and jsc.truthy(jsc.get(e, "uuid")):
                        first["uuid"] = e["uuid"]
                    if not jsc.truthy(first.get("canonical_code")) and jsc.truthy(
                        jsc.get(e, "canonical_code")
                    ):
                        first["canonical_code"] = e["canonical_code"]
                continue
            rc_seen_key.add(k)
            if u:
                rc_seen_uuid.add(u)
            rc_out.append(e)

        o["entities"] = rc_out
        # diagnostics: emitted ONLY when non-zero, so they are drop-when-absent in replay
        if rc_dropped:
            o["carried_attachment_evicted"] = rc_dropped
        if rc_dupes > 0:
            o["entities_deduped"] = rc_dupes

    # C1 residual-class diagnostic. Classify the FINAL entity set explicitly: the
    # contribution loop above short-circuits on carried entities BEFORE classifying, and a
    # reuse turn never calls axisOf at all, so the immortal population this exists to
    # measure was never counted (exec 11645628). Diagnostic-only; cannot change behaviour.
    if not jsc.truthy(o.get("is_menu_label")) and jsc.is_array(o.get("entities")):
        for e in o["entities"]:
            ce_axis_for(e, o.get("domain_hint"))
    if not jsc.truthy(o.get("is_menu_label")) and ce_unknown_hints:
        o["unknown_entity_hints"] = sorted(ce_unknown_hints)

    # -- domain-aware entity-type blocklist ---------------------------------------------- #
    if jsc.truthy(o.get("entities")) and jsc.is_array(o.get("entities")):
        domain = o.get("domain_hint")
        # A TIME-only or single-axis widening is not an entity-scope broaden: it keeps the
        # customer and product the user already named. Without this, "all time" would
        # silently become "all orders".
        ba_raw = jsc.lower_or_empty(o.get("broaden_axis"))
        is_broaden = o.get("scope_intent") == "broaden" and (not ba_raw or ba_raw == "all")
        blocked = set(DOMAIN_BLOCKED_HINTS.get(domain, [])) | (
            set(DOMAIN_BROADEN_BLOCKED_HINTS.get(domain, [])) if is_broaden else set()
        )
        if len(blocked) > 0:
            before = len(o["entities"])
            dropped = []
            kept = []
            for e in o["entities"]:
                hit = jsc.lower_or_empty(jsc.get(e, "hint")) in blocked
                if hit:
                    dropped.append(f"{jsc.get(e, 'hint')}:{jsc.get(e, 'raw')}")
                else:
                    kept.append(e)
            o["entities"] = kept
            after = len(o["entities"])
            o["entities_filtered"] = after != before
            o["entities_emptied_by_filter"] = before > 0 and after == 0
            if dropped:
                o["broaden_dropped"] = dropped

    prior_routing = jsc.get(parent_input.get("previous_conversation_state"), "routing")
    if prior_routing is None:
        prior_routing = {}

    # escalation confirmation = the previous response OFFERED escalation (fixed wording)
    # AND the current message is affirmative.
    offered_escalation = _offer_is_open(parent_input.get("previous_conversation_state"))
    is_affirmative = o.get("is_affirmative") is True
    is_decline = o.get("is_affirmative") is False

    # A position pick is NOT a decline of the escalation offer - don't let
    # is_affirmative=false collapse it to casual (which would wipe the resolved entities).
    is_position_pick = (
        jsc.js_number(o.get("positions_resolved")) > 0
        or o.get("select_all_expanded") is True
        or (jsc.is_array(o.get("reference_positions")) and len(o["reference_positions"]) > 0)
    )
    if offered_escalation and is_affirmative:
        o["escalation"] = {"is_escalation_confirmation": True}
    elif offered_escalation and is_decline and not is_position_pick and not req_help:
        o["escalation"] = {"is_escalation_confirmation": False, "escalation_declined": True}
        o["message_type"] = "casual"

    # -- S5: a positional pick carries its own scope (promotion domain only) ------------- #
    # "1 and 2" resolves to reference_positions but entities [], so the gate saw a
    # scope-less promotion ask and refused (exec 11827959). The pick must NOT become the
    # new scope, or the roster collapses to 1 and every later number returns the same file.
    prev5 = parent_input.get("previous_conversation_state") or {}
    picking = jsc.is_array(o.get("reference_positions")) and len(o["reference_positions"]) > 0
    no_scope = not jsc.is_array(o.get("entities")) or len(o["entities"]) == 0
    # QUOTE-REPLY WINS: the parser already resolved the position against
    # referenced_result_set, and the scope reuse would discard it (PP-7).
    quoted = jsc.is_array(parent_input.get("referenced_result_set")) and len(
        parent_input["referenced_result_set"]
    ) > 0
    # F1: a numbered pick on a promotion DID-YOU-MEAN offer also arrives with positions.
    # `reference_target === 'dym'` is NOT the signal - it is the model's DEFAULT and comes
    # back on an ordinary promo-roster pick too. The real discriminator is whether a dym
    # offer was actually PENDING in the previous state.
    prev_dym = (
        jsc.is_array(prev5.get("dym_last_result_set")) and len(prev5["dym_last_result_set"]) > 0
    ) or bool(prev5.get("dym_offer") is not None and isinstance(prev5.get("dym_offer"), dict))
    dym_pick = prev_dym or o.get("dym_pick_applied") is True
    # F10: do NOT drop promotion-hinted entities here - Q25 allows a list scoped BY A
    # PROMOTION NAME, and filtering those out left the scope empty.
    prev_scope = [] if (quoted or dym_pick) else jsc.array(prev5.get("entities"))
    if o.get("domain_hint") == "promotion" and picking and len(prev_scope) > 0:
        o["entities"] = [{**x, "current_message": False} for x in prev_scope]
        o["entity_op"] = "reuse"
        o["_promo_pick_scope_reused"] = True
        # N2: name WHICH rows were picked, from the roster the customer actually saw.
        # promo-picker prefers these over a raw index - indexing assumes the re-run returns
        # the same order as the turn that built the roster, and nothing guarantees that.
        roster = (
            jsc.array(parent_input.get("referenced_result_set"))
            if quoted
            else jsc.array(prev5.get("last_result_set"))
        )
        if len(roster):
            labels = []
            for n in o["reference_positions"]:
                index = jsc.js_number(n) - 1
                row = roster[int(index)] if isinstance(index, int) and 0 <= index < len(roster) else {}
                label = jsc.get(row, "label")
                if jsc.truthy(label):
                    labels.append(label)
            o["_promo_pick_labels"] = labels
    elif (
        o.get("domain_hint") == "promotion"
        and picking
        and no_scope
        and not quoted
        and not dym_pick
        and jsc.is_array(prev5.get("entities"))
        and len(prev5["entities"]) > 0
    ):
        o["entities"] = [{**x, "current_message": False} for x in prev5["entities"]]
        o["entity_op"] = "reuse"
        o["_promo_pick_scope_reused"] = True

    engages_offer = is_affirmative or is_decline or is_position_pick
    if o.get("message_type") == "casual" and not engages_offer:
        o["entities"] = []

    if (
        jsc.truthy(o.get("domain_hint"))
        and o.get("message_type") != "casual"
        and o.get("message_type") != "request_for_help"
    ):
        o["message_type"] = "business_query"

    # -- attachment_type i18n normalize -------------------------------------------------- #
    # The resolver + get-results read entity.raw. The LLM sets canonical_code to the
    # English kind for attachment_type; mirror it into raw so a foreign word (gambar ->
    # photo) resolves. Authority/brand certs keep canonical_code null -> raw untouched.
    if jsc.is_array(o.get("entities")):
        for e in o["entities"]:
            if jsc.lower_or_empty(jsc.get(e, "hint")) == "attachment_type" and jsc.truthy(
                jsc.get(e, "canonical_code")
            ):
                e["raw"] = e["canonical_code"]

    derived = derive_routing(o) if jsc.truthy(o.get("domain_hint")) else {
        "suggested_team": None,
        "suggested_agent": None,
    }

    # -- B-TEAM-1': STATE-keyed routing rank ladder --------------------------------------- #
    # Priority, never the customer's own words:
    #   (1) LLM EXPLICIT team - the customer named one, in any language.
    #   (2) the PRIOR OFFERED team - ONLY when THIS turn actually engages an open offer
    #       (`offeredEscalation && isAffirmative`, the same test that flips
    #       is_escalation_confirmation above).
    #   (3) derived-from-domain, or the LLM's own low-confidence 'inferred' guess.
    #   (4) null TEAM - never a hard team default; clarify-team-gate asks instead.
    # TEAM and AGENT are read from the SAME winning rank: two independent `??` chains let
    # an explicit team pair with a stale open-offer agent, exactly the mismatch the
    # CS-order-pick divert and the roster-lane check both require to be coherent. A rank
    # wins when its OWN team OR its OWN agent is non-null (not team alone: derived's
    # `ideate` case is an intentional team:null / agent:'ideation' pair).
    explicit_team = llm_team_n if llm_team_source_n == "explicit" else None
    explicit_agent = llm_agent_n if llm_team_source_n == "explicit" else None
    accepted_open_offer = offered_escalation and is_affirmative
    open_offer_team = norm(jsc.get(prior_routing, "suggested_team")) if accepted_open_offer else None
    open_offer_agent = norm(jsc.get(prior_routing, "suggested_agent")) if accepted_open_offer else None
    derived_team = norm(derived.get("suggested_team"))
    derived_agent = norm(derived.get("suggested_agent"))
    inferred_team = llm_team_n if llm_team_source_n == "inferred" else None
    inferred_agent = llm_agent_n if llm_team_source_n == "inferred" else None

    routing_ranks = [
        {"team": explicit_team, "agent": explicit_agent},
        {"team": open_offer_team, "agent": open_offer_agent},
        {"team": derived_team, "agent": derived_agent},
        {"team": inferred_team, "agent": inferred_agent},
    ]
    winning = next(
        (r for r in routing_ranks if r["team"] is not None or r["agent"] is not None),
        {"team": None, "agent": None},
    )
    suggested_team = winning["team"]
    # AGENT keeps a hard default WITHIN the winning rank: it is the spine's ACCESS key,
    # read unconditionally before any routing decision runs. TEAM stays null when no rank
    # resolves - the null-when-unsure contract is TEAM-only.
    suggested_agent = winning["agent"] if winning["agent"] is not None else "general_enquiries"

    o["routing"] = {"suggested_team": suggested_team, "suggested_agent": suggested_agent}
    # normalise a legacy suffixed promotion team to the single base team
    if _PROMO_TEAM_RE.match(jsc.lower_or_empty(o["routing"].get("suggested_team")) or ""):
        o["routing"]["suggested_team"] = "marketing_promotion"

    # -- rev 3: pending team_clarify completion / abandon ---------------------------------- #
    # `selection_context === 'team_clarify'` means the LAST bot turn was the clarify ask:
    # the team resolved to null and the customer was asked instead of silently defaulted.
    # Without this the bare reply "order" re-parsed as a fresh business_query and answered
    # normally - the escalation intent was lost (clone exec 14992562 -> 14992601).
    if prev_state.get("selection_context") == "team_clarify":
        # ABANDON: a fresh current-message entity means the customer asked something
        # SPECIFIC and new, not merely answering "what's this about".
        fresh_entity_this_turn = jsc.is_array(o.get("entities")) and any(
            jsc.truthy(e) and jsc.get(e, "current_message") is True for e in o["entities"]
        )
        # rev 4: two more abandon clauses, same "no signal -> fall through" shape.
        #   (a) casual - without it "haha ok nvm" force-completes and the clarify re-fires
        #       with the same frozen string every turn: an unbounded identical-copy loop.
        #   (b) an explicit decline - force-completing on top of it would produce the
        #       forbidden pair {escalation_declined, is_escalation_confirmation}.
        abandon_clarify = (
            fresh_entity_this_turn
            or o.get("message_type") == "casual"
            or jsc.get(o.get("escalation"), "escalation_declined") is True
        )
        if not abandon_clarify:
            # COMPLETE: route this turn to escalation exactly as an accepted open offer
            # would. escalation-context then recomputes `team` from THIS turn's routing.
            o["escalation"] = {
                **(o.get("escalation") if jsc.truthy(o.get("escalation")) else {}),
                "is_escalation_confirmation": True,
            }

    # -- miss-company-routing: company-pick resolver (STATE-ONLY as of rev 8) -------------- #
    # The offer names companies; a reply that resolves to exactly ONE company of the
    # OFFERED pool is a pool pick, not a new query. The LLM owns the language understanding
    # (typos, any language, ordinals, correcting negations) via `escalation.company_pick`;
    # this resolver's ONLY job is to VALIDATE that emission against the pool, refusing
    # anything not actually offered. It never re-reads the customer's words.
    def co_company_pick(candidate_output: dict) -> dict:
        st = parent_input.get("previous_conversation_state") or {}
        rp = jsc.array(st.get("routing_roster_plan"))
        # (A) POOL = the companies actually OFFERED: the roster plan when non-empty, else
        # routing_companies. Never the union: on a Sorento-only offer "yes mocha" must NOT
        # route to Mocha.
        src = rp if len(rp) else jsc.array(st.get("routing_companies"))
        pool: dict[str, dict] = {}
        for c in src:
            if not jsc.truthy(c) or not jsc.truthy(jsc.get(c, "company_name")):
                continue
            name = jsc.js_string(c["company_name"])
            nk = name.lower().strip()
            ent = pool.get(nk) or {"name": name, "keys": set()}
            ent["keys"].add(nk)
            for ck in (c.get("company_code"), c.get("code")):
                if isinstance(ck, str) and ck.strip():
                    ent["keys"].add(ck.lower().strip())
            for a in CO_ALIASES.get(nk, []):
                ent["keys"].add(a)
            pool[nk] = ent

        def hits(texts: list[str]) -> str | None:
            h: set[str] = set()
            for ent in pool.values():
                for k in ent["keys"]:
                    if any(jsc.word_boundary_re(k).search(t) for t in texts):
                        h.add(ent["name"])
                        break
            return next(iter(h)) if len(h) == 1 else None

        try:
            if not pool:
                return {"any": None}
            raw = jsc.get(jsc.get(parser_raw_snapshot, "escalation"), "company_pick")
            if isinstance(raw, str) and raw.strip():
                k = raw.lower().strip()
                direct = [ent for ent in pool.values() if k in ent["keys"]]
                if len(direct) == 1:
                    return {"any": direct[0]["name"]}
                if len(direct) > 1:
                    return {"any": None}
                by_raw = hits([k])
                if by_raw:
                    return {"any": by_raw}
            # secondary LLM signal: person_mention, same pool validation.
            pm = candidate_output.get("person_mention")
            pm_raw = pm.strip().lower() if isinstance(pm, str) and pm.strip() else ""
            return {"any": hits([pm_raw]) if pm_raw else None}
        except Exception:
            return {"any": None}

    # -- CS member-pick override (final say) ---------------------------------------------- #
    sel_ctx = jsc.get(parent_input.get("previous_conversation_state"), "selection_context")
    if sel_ctx == "member_offer" and o.get("dym_pick_applied") is not True:
        last_set = jsc.array(jsc.get(parent_input.get("previous_conversation_state"), "last_result_set"))
        max_idx = len(last_set)

        def extract(msg: Any, llm: Any) -> list:
            if jsc.is_array(llm) and len(llm):
                seen = []
                for v in (jsc.js_number(x) for x in llm):
                    if not jsc.is_nan(v) and v not in seen:
                        seen.append(v)
                return seen
            t = jsc.nullish_str(msg if jsc.truthy(msg) else "").strip().lower()
            c: list = []
            if _BARE_NUMBER_RE.match(t):
                c.append(int(re.sub(r"[^0-9]", "", t) or 0))
            for w, n in _ORD.items():
                # `re.ASCII` is safe HERE: the pattern is a bare word boundary around an
                # ordinal word, with no `\s` for the flag to narrow. JS's `\b` is ASCII.
                if re.search(r"\b" + re.escape(w) + r"\b", t, re.ASCII):
                    c.append(n)
            # `t.match(/.../g)` with a capture group returns the FULL matches, so the
            # digits are pulled out of each whole "option 4" / "no. 4" hit.
            for m in _OPTION_ANY_RE.finditer(t):
                c.append(int(re.sub(r"[^0-9]", "", m.group(0)) or 0))
            if len(c) == 0 and len([w for w in re.split(r"\s+", t) if w]) <= 4:
                for w in re.split(r"\s+", t):
                    if re.match(r"^#?[0-9]+$", w):
                        c.append(int(re.sub(r"[^0-9]", "", w) or 0))
            out = []
            for n in c:
                if n not in out and not jsc.is_nan(n):
                    out.append(n)
            return out

        def norm_name(s: Any) -> str:
            v = jsc.lower_or_empty(s).strip()
            v = re.sub(r"\s+", " ", v)
            return _HONORIFIC_RE.sub("", v)  # strip ONE leading honorific

        # In member_offer context a bare number, or a short reply matching a member label,
        # is ALWAYS a pick - never a new query - even if the LLM speculatively assigned a
        # domain (bare "Nur", which also looks like customer NURTECH). Force the pick.
        raw_reply = _split_reply_to(parent_input.get("latest_user_message")).strip()
        reply_words = [w for w in re.split(r"\s+", raw_reply) if w]
        reply_is_number = bool(_BARE_NUMBER_RE.match(raw_reply))

        def reply_matches_member() -> bool:
            if not (0 < len(reply_words) <= 3):
                return False
            b = norm_name(raw_reply)
            for r in last_set:
                a = norm_name(jsc.get(r, "label"))
                if not a or not b:
                    continue
                if (
                    a == b
                    or any(t and t == b for t in a.split(" "))
                    or any(t and t == a for t in b.split(" "))
                    or b in a
                    or a in b
                ):
                    return True
            return False

        force_pick = reply_is_number or reply_matches_member()

        co = co_company_pick(o)
        co_pick_any = co["any"]

        # entry-gate precedence: 1 retarget -> 2 pick -> 3 new-query abandon -> 4 reprompt
        prior_team = norm(jsc.get(prior_routing, "suggested_team")) or "customer_service"
        # execs 13045880 / 13206773 ("4 smart delivery status" on a 4-member offer): the
        # loose "any bare-digit word in a <=4-word reply" arm read the customer NAME
        # "4 smart" as pick #4 and escalated a delivery question. Keep the guess ONLY when
        # the LLM did not read the turn as a new business query.
        pos = extract(parent_input.get("latest_user_message"), o.get("reference_positions"))
        t_low = _split_reply_to(parent_input.get("latest_user_message")).strip().lower()
        strict = (
            (jsc.is_array(o.get("reference_positions")) and len(o["reference_positions"]) > 0)
            or bool(_BARE_NUMBER_RE.match(t_low))
            # ASCII `\b`, as JS has; no `\s` in the pattern for the flag to narrow.
            or any(re.search(r"\b" + re.escape(w) + r"\b", t_low, re.ASCII) for w in _ORD)
            or bool(_OPTION_ANY_RE.search(t_low))
        )
        llm_new_query = (
            jsc.truthy(o.get("domain_hint")) or o.get("message_type") == "business_query"
        ) and o.get("is_affirmative") is not True
        def _digit_in_raw(e: Any) -> bool:
            raw = jsc.js_string(jsc.get(e, "raw") if jsc.truthy(jsc.get(e, "raw")) else "")
            return any(
                re.search(
                    r"(^|[^0-9])" + re.escape(jsc.js_string(n)) + r"([^0-9]|$)", raw
                )
                for n in pos
            )

        digit_in_entity = any(
            jsc.truthy(e) and jsc.truthy(jsc.get(e, "current_message")) and _digit_in_raw(e)
            for e in jsc.array(o.get("entities"))
        )
        if not strict and pos and llm_new_query and digit_in_entity:
            pos = []

        # key ONLY on an actual extracted person name: the old `: _rawReply` fallback made
        # this arm truthy for EVERY worded reply and shadowed the yes/no arms below.
        pm_val = o.get("person_mention")
        pm = pm_val.strip() if isinstance(pm_val, str) and pm_val.strip() else ""
        is_new_query = (
            jsc.truthy(o.get("domain_hint"))
            or o.get("message_type") == "business_query"
            or o.get("message_type") == "clarification"
        ) and o.get("is_affirmative") is not True
        has_pick_signal = (
            force_pick
            or len(pos) > 0
            or bool(pm)
            or o.get("is_affirmative") is True
            or o.get("is_affirmative") is False
        )

        if req_help and jsc.truthy(llm_team_n) and llm_team_n != prior_team:
            # Tier 1 - RETARGET: the LLM named a DIFFERENT team mid-offer -> abandon the CS
            # roster and direct-assign it.
            o["routing"] = {
                "suggested_team": llm_team_n,
                "suggested_agent": norm(llm_agent_raw) or "general_enquiries",
            }
            if _PROMO_TEAM_RE.match(jsc.js_string(llm_team_n)):
                o["routing"]["suggested_team"] = "marketing_promotion"
            o["escalation"] = {"is_escalation_confirmation": True, "retarget_team": True}
            o["message_type"] = "request_for_help"
            o["selection_context"] = None
            o["last_result_set"] = []
            o["member_pick_context"] = False
        elif has_pick_signal:
            # Tier 2 - PICK SIGNAL: number / position / person-name / bare yes|no.
            if len(pos) == 1 and 1 <= pos[0] <= max_idx:
                row = jsc.find(last_set, lambda r: jsc.js_number(jsc.get(r, "idx")) == pos[0])
                o["escalation"] = {
                    "is_escalation_confirmation": True,
                    "preferred_assignee_id": row["uuid"] if "uuid" in row else None,
                }
                o["entities"] = []
            elif len(pos) > 1:
                o["escalation"] = {"is_escalation_confirmation": False, "member_reprompt": "multi"}
                o["correction"] = True  # re-offer the member list (only one allowed)
            elif len(pos) == 1:
                o["escalation"] = {
                    "is_escalation_confirmation": False,
                    "member_reprompt": "out_of_range",
                }
                o["correction"] = True
            elif pm:
                # name-resolution arm: no numeric position + a person_mention -> match
                # against last_result_set labels, tiered exact -> token overlap -> substring.
                q = norm_name(pm)
                qt = {t for t in q.split(" ") if t}
                normed = [
                    {"idx": jsc.js_number(jsc.get(r, "idx")), "uuid": jsc.get(r, "uuid"), "ln": norm_name(jsc.get(r, "label"))}
                    for r in last_set
                ]
                m = [r for r in normed if r["ln"] == q]
                if not m:
                    m = [r for r in normed if any(t in qt for t in r["ln"].split(" ") if t)]
                if not m:
                    m = [r for r in normed if q in r["ln"] or r["ln"] in q]
                dedup: dict = {}
                for r in m:
                    dedup[r["idx"]] = r
                m = list(dedup.values())
                if len(m) == 1:
                    o["escalation"] = {
                        "is_escalation_confirmation": True,
                        "preferred_assignee_id": m[0]["uuid"],
                    }
                    o["entities"] = []
                elif len(m) > 1:
                    o["escalation"] = {
                        "is_escalation_confirmation": False,
                        "member_reprompt": "multi",
                    }
                    o["correction"] = True  # ambiguity gate: reprompt, NEVER auto-pick
                elif jsc.truthy(co_pick_any):
                    # the person-extractor surfaced a company name; no member matched ->
                    # it is the company pick, not an unknown person.
                    o["escalation"] = {
                        "is_escalation_confirmation": True,
                        "company_pick": co_pick_any,
                    }
                    o["entities"] = []
                else:
                    o["escalation"] = {
                        "is_escalation_confirmation": False,
                        "member_reprompt": "out_of_range",
                    }
                    o["correction"] = True  # 0 match -> reprompt the member list
            elif o.get("is_affirmative") is True:
                # "yes mocha": the LLM reads it as an affirmative. A validated company pick
                # rides the confirmation; without one it is the plain round-robin yes.
                o["escalation"] = (
                    {"is_escalation_confirmation": True, "company_pick": co_pick_any}
                    if jsc.truthy(co_pick_any)
                    else {"is_escalation_confirmation": True}
                )
            elif o.get("is_affirmative") is False and jsc.truthy(co_pick_any):
                # the LLM read a decline but the reply names exactly ONE offered company
                # ("nah just sorento") -> company pick.
                o["escalation"] = {"is_escalation_confirmation": True, "company_pick": co_pick_any}
                o["entities"] = []
            elif o.get("is_affirmative") is False:
                # plain decline. Emit a DETERMINISTIC marker the spine's
                # is-escalation-declined keys on, so the reply is a FIXED
                # "Escalation declined." and NEVER the clarification LLM.
                o["escalation"] = {
                    "is_escalation_confirmation": False,
                    "escalation_declined": True,
                }
                o["message_type"] = "casual"
            o["member_pick_context"] = True
        elif jsc.truthy(co_pick_any):
            # Tier 2.5 - COMPANY PICK: no member/number/yes-no signal, but the validated
            # LLM company_pick names exactly one persisted company.
            o["escalation"] = {"is_escalation_confirmation": True, "company_pick": co_pick_any}
            o["entities"] = []
            o["member_pick_context"] = True
        elif is_new_query:
            # Tier 3 - NEW QUERY: abandon the offer. Touch nothing.
            pass
        else:
            # Tier 4 - junk / no signal: reprompt the member list once.
            o["escalation"] = {"is_escalation_confirmation": False, "member_reprompt": "out_of_range"}
            o["correction"] = True
            o["member_pick_context"] = True

    # -- rev-4: company pick on an OPEN offer WITHOUT member-pick context ------------------ #
    # An escalation offer can be open without member_offer (a multi-company offer whose
    # rosters all came back empty). "Open" = the FROZEN phrase is in the persisted previous
    # response - deliberately NOT the persisted roster plan, which the spine carries
    # forward across same-team turns and would re-open a closed offer.
    if sel_ctx != "member_offer" and o.get("dym_pick_applied") is not True:
        st_o = parent_input.get("previous_conversation_state") or {}
        open_o = _offer_is_open(st_o)
        if open_o and not jsc.truthy(o.get("domain_hint")):
            co_o = co_company_pick(o)
            retarget_o = (
                req_help
                and jsc.truthy(llm_team_n)
                and llm_team_n != (norm(jsc.get(prior_routing, "suggested_team")) or "customer_service")
            )
            if jsc.truthy(co_o["any"]) and not retarget_o:
                o["escalation"] = {"is_escalation_confirmation": True, "company_pick": co_o["any"]}
                o["entities"] = []
                o["member_pick_context"] = True

    # -- rev 5/6: a validated PICK completes rank 2 ---------------------------------------- #
    # Rank 2 fires only on isAffirmative, so a reply that ENGAGES the offer by resolving a
    # company/member pick without the LLM flagging is_affirmative missed it and fell to
    # null (clone exec 15019770). This COMPLETES rank 2 - same priority, not a backfill -
    # so it overwrites whatever a lower rank computed. Only "the customer named a different
    # team this turn" still wins: rank 1 EXPLICIT, or a Tier-1 RETARGET.
    explicit_won = explicit_team is not None or explicit_agent is not None
    prior_offered_team = norm(jsc.get(prior_routing, "suggested_team"))
    if (
        offered_escalation
        and o.get("member_pick_context") is True
        and jsc.get(o.get("escalation"), "is_escalation_confirmation") is True
        and not explicit_won
        and jsc.get(o.get("escalation"), "retarget_team") is not True
        and jsc.truthy(prior_offered_team)
    ):
        o["routing"]["suggested_team"] = prior_offered_team
        agent = norm(jsc.get(prior_routing, "suggested_agent"))
        o["routing"]["suggested_agent"] = agent if agent is not None else "general_enquiries"

    # -- DATE-FILTER DOMAIN GATE (policy lives here, not in the LLM) ----------------------- #
    # The parser extracts a date window whenever the message names one, for ANY domain.
    # This whitelist is the deterministic policy for which domains actually honour it.
    if o.get("domain_hint") not in DATE_FILTER_DOMAINS:
        if (
            jsc.truthy(o.get("date_filter_start"))
            or jsc.truthy(o.get("date_filter_end"))
            or jsc.truthy(o.get("date_mode"))
        ):
            o["date_filter_gated"] = o.get("domain_hint") if jsc.truthy(o.get("domain_hint")) else None
        o["date_filter_start"] = None
        o["date_filter_end"] = None
        o["date_mode"] = None

    # -- D11 - PENDING NON-TIER PICK ------------------------------------------------------- #
    # The tier-gate must not fire the access-level ask on top of a pick the parser already
    # resolved. TWO signals, and the BOUND between them is the whole design: an explicitly
    # RESOLVED pick (provenance flags), or a CONTINUATION (a non-tier roster is pending AND
    # this turn named no new scope). The second half is what keeps D4 alive - "promo for
    # CBS212-WH" with a roster pending IS a new query and MUST re-ask.
    pp_prev_ctx = jsc.nullish_str(prev_state.get("selection_context") or "")
    pp_roster_pending = pp_prev_ctx in ("suggest_offer", "member_offer", "disambiguation") or (
        pp_prev_ctx != "tier_offer"
        and jsc.is_array(prev_state.get("last_result_set"))
        and len(prev_state["last_result_set"]) > 0
    )
    pp_named_new_scope = any(
        jsc.truthy(e) and jsc.get(e, "current_message") is True for e in jsc.array(o.get("entities"))
    )
    pp_resolved_pick = (
        o.get("_promo_pick_scope_reused") is True
        or o.get("dym_pick_applied") is True
        or o.get("member_pick_context") is True
        or jsc.js_number(o.get("positions_resolved")) > 0
        or o.get("select_all_expanded") is True
        or (jsc.is_array(o.get("reference_positions")) and len(o["reference_positions"]) > 0)
    )
    if o.get("_tier_pick_scope_reused") is not True and (
        pp_resolved_pick or (pp_roster_pending and not pp_named_new_scope)
    ):
        o["_pending_pick"] = True

    # -- A CORRECTION RETIRES THE SPELLING IT CORRECTED ------------------------------------ #
    # Exec 13688567: the bot asked "Couldn't find WESRP10B. Did you mean WESERP10B?", the
    # customer answered with the exact code offered, and got the identical question back -
    # for as long as they cared to keep answering. No words are matched to fix it: the model
    # says the turn accepts a correction (dym_pick_applied), and the offer records which
    # token each candidate was for.
    dym_applied = o.get("dym_pick_applied") is True
    dym_cands = jsc.get(prev_state.get("dym_offer"), "candidates")
    if dym_applied and jsc.is_array(dym_cands) and len(dym_cands) and jsc.is_array(o.get("entities")):
        def sn(v: Any) -> str:
            return re.sub(r"[^a-z0-9]+", "", jsc.nullish_str(v).strip().lower())

        named: set[str] = set()
        for e in o["entities"]:
            if not jsc.truthy(e):
                continue
            r = sn(jsc.get(e, "raw"))
            if r:
                named.add(r)
            c = sn(jsc.get(e, "canonical_code"))
            if c:
                named.add(c)
        superseded: set[str] = set()
        for cand in dym_cands:
            if not jsc.truthy(cand):
                continue
            code = sn(jsc.get(cand, "code"))
            for_raw = sn(jsc.get(cand, "for_raw"))
            # only when the customer actually took THIS candidate, and never let a
            # candidate retire itself
            if code and for_raw and for_raw != code and code in named:
                superseded.add(for_raw)
        if superseded:
            before = len(o["entities"])
            o["entities"] = [e for e in o["entities"] if sn(jsc.get(e, "raw")) not in superseded]
            o["dym_superseded_dropped"] = before - len(o["entities"])

    # -- AXIS BROADEN, FINAL PASS: the widened filter must not come back -------------------- #
    # This drop used to sit right after the executor; a LATER writer re-attached the product
    # anyway (~47 sites assign entities/domain_hint), so it runs immediately before the
    # return, where `entities` is final by definition. Drop by HINT, not by axis: live's
    # maps lump customer/product/order into ONE order_scope, so an axis-equality drop would
    # take the customer out with the product.
    ba_final = jsc.lower_or_empty(o.get("broaden_axis"))
    if ba_final and ba_final != "all" and ba_final != "date" and jsc.is_array(o.get("entities")):
        before = len(o["entities"])
        o["entities"] = [
            e for e in o["entities"] if jsc.lower_or_empty(jsc.get(e, "hint")) != ba_final
        ]
        o["broaden_axis_dropped"] = before - len(o["entities"])

    output["_parser_raw"] = parser_raw_snapshot
    return output


def suggest_follow_up(item: dict, parent_input: dict) -> dict:
    """Port of `suggest-follow-up.js`. Runs AFTER output_exchange, on the same item.

    When the PREVIOUS turn was a `suggest_offer`: a tapped code / typed position re-queries
    in the RETAINED domain (never a CS assign); a plain "yes" escalates; "no" declines and
    stops. Inert on every other turn - byte-identical output when selection_context differs.
    """
    output = item
    parent_input = parent_input or {}
    prev_state = parent_input.get("previous_conversation_state") or {}
    if (
        jsc.truthy(output)
        and jsc.truthy(jsc.get(output, "output"))
        and prev_state.get("selection_context") == "suggest_offer"
    ):
        o = output["output"]
        has_entity_pick = jsc.is_array(o.get("entities")) and any(
            jsc.get(e, "current_message") is True for e in o["entities"]
        )
        has_pos_pick = jsc.is_array(o.get("reference_positions")) and len(o["reference_positions"]) > 0
        if has_entity_pick or has_pos_pick:
            # a bare code (button tap) or a position was given -> keep the prior domain when
            # the reply carried no decisive domain term, then let normal processing re-query.
            if not jsc.truthy(o.get("domain_hint")) and jsc.truthy(prev_state.get("domain_hint")):
                o["domain_hint"] = prev_state["domain_hint"]
                o["intent_hint"] = (
                    o.get("intent_hint") if jsc.truthy(o.get("intent_hint")) else prev_state.get("intent_hint")
                )
                o["domain_inherited_for_suggest"] = True
            if jsc.truthy(o.get("domain_hint")):
                o["message_type"] = "business_query"
        elif o.get("is_affirmative") is True:
            # plain "yes" on a suggest_offer = escalate, ALWAYS (never a pick)
            o["escalation"] = {"is_escalation_confirmation": True}
            o["entities"] = []
        elif o.get("is_affirmative") is False:
            o["escalation"] = {"is_escalation_confirmation": False, "escalation_declined": True}
            o["message_type"] = "casual"
            o["entities"] = []
        o["suggest_pick_context"] = True

    # -- unicode dash normalize ------------------------------------------------------------ #
    # Excel/Word/Sheets/PDF copy-paste emits U+2212 MINUS SIGN, U+2013 EN DASH and friends
    # instead of ASCII '-'. Observed live (exec 12053189): "SRT332-GM" carrying a U+2212
    # reached the resolver verbatim, missed the exact match because the CRM stores that code
    # with an ASCII hyphen, and only survived as a did-you-mean. Runs on EVERY turn,
    # deliberately outside the suggest_offer branch above.
    if jsc.truthy(output) and jsc.truthy(jsc.get(output, "output")) and jsc.is_array(
        jsc.get(output.get("output"), "entities")
    ):
        for e in output["output"]["entities"]:
            if not jsc.truthy(e):
                continue
            if isinstance(jsc.get(e, "raw"), str):
                e["raw"] = _DASHES.sub("-", e["raw"])
            if isinstance(jsc.get(e, "canonical_code"), str):
                e["canonical_code"] = _DASHES.sub("-", e["canonical_code"])
    return output
