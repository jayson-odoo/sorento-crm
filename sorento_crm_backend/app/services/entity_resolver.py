"""Entity reference resolver.

Given a free-text user query, extract "code-like" tokens and look each one up in parallel
across the key business entities (products, orders, shipments, customers, suppliers,
warehouses, SPOs, GRNs, promotions). Returns a structured resolution that the AI assistant
can inject into the LLM prompt so the model does not have to guess what entity a code refers
to.

Design notes
------------
- Deterministic SQL only. No RAG / embedding call. Each probe is an indexed equality or
  ILIKE lookup so the whole resolver runs in tens of milliseconds.
- No UUIDs are ever returned. We keep the resolver user-facing: it returns business codes
  and a minimal display payload (name, status, ETA...).
- If zero entities match a token, the token is returned in `unresolved` so the LLM can
  tell the user "no record found for X" rather than hallucinating a match.
- Tokens that look like ordinary English words are filtered via a short stopword list and
  a minimum-length / digit-presence requirement.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional

from functools import reduce
from operator import add

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import Session

from app.models.forms import Form
from app.models.inventory import Warehouse
from app.models.marketing import Promotion
from app.models.order import Customer, Order, OrderStatus, Transporter
from app.models.procurement import (
    InboundShipment,
    PickingHeader,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product
from app.models.resources import Attachment, AttachmentType


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Entity-type aliases
# --------------------------------------------------------------------------- #
# Resolver uses canonical internal names (e.g. "customer_order"). External callers
# sometimes pass UI-facing synonyms (e.g. "delivery_order"). Map them once here so
# both `allowed_entity_types` filtering AND positional token<->type pairing stay
# consistent regardless of which label the caller used.
_ENTITY_TYPE_ALIASES: dict[str, str] = {
    "delivery_order": "customer_order",
    "do": "customer_order",
    "order": "customer_order",
    "sales_order": "customer_order",
    # Product-domain hints. Caller uses these labels as `domain_hint` to scope
    # ambiguous aliases (brand / category) to product probes.
    "product_attachment": "product",
    "product_attachments": "product",
    "master_products": "product",
    "master_product": "product",
    "products": "product",
    # Attachment type catalog (AttachmentType row, NOT a file row). Resolves a
    # free-text doc-class label like "catalogue", "brochure", "spec sheet" into
    # the canonical AttachmentType UUID, suitable for `attachment_type_ids` /
    # `attachment_type_id` filters on attachment list tools.
    "attachment-type": "attachment_type",
    "attachmenttype": "attachment_type",
    "doc_type": "attachment_type",
    "document_type": "attachment_type",
    "file_type": "attachment_type",
    # Brand / category handled via `_ENTITY_TYPE_EXPANSIONS` below (one-to-many
    # fan-out), NOT the 1:1 alias map. Listed here as identity so
    # `_canonical_entity_type` does not drop them before expansion runs.
    "brand": "brand",
    "brands": "brand",
    "category": "category",
    "categories": "category",
    "product_category": "category",
    "product_categories": "category",
}


# One-to-many fan-out for canonical names that have NO dedicated probe but map
# to one or more concrete entity types in the resolver. Applied after
# `_canonical_entity_type` when building the `allowed` set. Brand / category
# resolve to promotion only — keeping the surface narrow (promotions group
# products by brand + category, which is what the n8n promo agent needs).
_ENTITY_TYPE_EXPANSIONS: dict[str, frozenset[str]] = {
    "brand": frozenset({"promotion"}),
    "category": frozenset({"promotion"}),
}


# Domain-scoped overrides for one-to-many expansions. When the caller passes
# `domain_hint`, ambiguous aliases like brand / category gain a different
# meaning. Example — domain_hint="order" + token="super ceramic": the user is
# almost certainly naming a customer / debtor, not a promotion bucket. Routing
# the expansion to {customer, customer_order, transporter} keeps the resolver
# inside the order domain.
_DOMAIN_HINT_EXPANSIONS: dict[str, dict[str, frozenset[str]]] = {
    "order": {
        "brand": frozenset({"customer", "customer_order", "transporter"}),
        "category": frozenset({"customer", "customer_order", "transporter"}),
    },
    "customer_order": {
        "brand": frozenset({"customer", "customer_order", "transporter"}),
        "category": frozenset({"customer", "customer_order", "transporter"}),
    },
    "delivery_order": {
        "brand": frozenset({"customer", "customer_order", "transporter"}),
        "category": frozenset({"customer", "customer_order", "transporter"}),
    },
    # Product domain — `product_attachment` / `master_products` / `products`
    # all canonicalize to `product` via `_ENTITY_TYPE_ALIASES`. Brand / category
    # in that context should hit product probes (products carry brand_id +
    # category_id directly) instead of fanning out to promotion.
    "product": {
        "brand": frozenset({"product"}),
        "category": frozenset({"product"}),
    },
}


def _expand_entity_types(
    types: Iterable[str],
    domain_hint: Optional[str] = None,
) -> frozenset[str]:
    """Canonicalize + fan-out one-to-many expansions into a concrete probe set.

    `_canonical_entity_type` only does 1:1 alias rewriting. Brand / category
    have no probes of their own and need to map to a SET of concrete probe
    types. When `domain_hint` is supplied AND it has an override in
    `_DOMAIN_HINT_EXPANSIONS`, the override takes precedence over the default
    `_ENTITY_TYPE_EXPANSIONS` map — keeps brand / category scoped to the
    domain the caller actually cares about.
    """
    hint_canon = _canonical_entity_type(domain_hint) if domain_hint else None
    overrides = _DOMAIN_HINT_EXPANSIONS.get(hint_canon or "", {}) if hint_canon else {}
    out: set[str] = set()
    for raw in types:
        if not raw:
            continue
        canon = _canonical_entity_type(raw)
        expansion = overrides.get(canon) or _ENTITY_TYPE_EXPANSIONS.get(canon)
        if expansion:
            out.update(expansion)
        else:
            out.add(canon)
    return frozenset(out)


def _canonical_entity_type(et: str) -> str:
    key = (et or "").strip().lower()
    return _ENTITY_TYPE_ALIASES.get(key, key)


def _build_token_type_map(
    tokens: list[str] | None,
    allowed_entity_types: Iterable[str] | None,
) -> Optional[dict[str, str]]:
    """Deprecated — positional pairing is disabled.

    Historically returned a positional token -> canonical_entity_type map when
    caller passed parallel lists of equal length, so token[i] would be resolved
    ONLY against allowed_entity_types[i]. This behaviour surprised callers who
    wanted each token resolved against EVERY allowed type (set-filter mode),
    e.g. tokens=["Sorento water closet", "latest promo"] with
    allowed_entity_types=["product", "promotion"] — they expect both tokens
    probed against both types.

    Always returns None now, so every code path falls through to the set-filter
    branch: `allowed` becomes the canonical set of all supplied types, and each
    surviving probe sees every token. Callers that need 1:1 pairing must make
    multiple resolve calls, one per (token, type).
    """
    return None


# --------------------------------------------------------------------------- #
# Token extraction
# --------------------------------------------------------------------------- #
# Code-like token: contains at least one letter AND at least one digit, min length 3.
# Allows letters, digits, hyphens, slashes, underscores, dots — but not pure numbers.
# Examples accepted: ACC-SRT1024, RF2601-025, FJ24041192, MSCU5475129, CB310-BL, CB313, PL.2026.001
# Examples rejected: the, and, 2026 (all digits), order, RF (no digit), product
_CODE_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[-_./][A-Za-z0-9]+)+"  # multi-segment: e.g. ACC-SRT1024, RF2601-025
    r"|[A-Za-z]+\d+[A-Za-z0-9]*"  # letters-then-digits: FJ24041192, CB313, MSCU5475129
    r"|\d+[A-Za-z]+[A-Za-z0-9]*"  # digits-then-letters: 10KG, 24HR
)

# Tokens that match the regex but are almost always English words or noise. Keep SHORT
# — we prefer false positives (extra SQL work) over false negatives (missed entity).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "today",
        "tomorrow",
        "yesterday",
        "please",
        "thanks",
        "thank",
    }
)


# Marker-driven name capture. We only run this when the user/agent has explicitly
# tagged the value with a customer/debtor/client/account marker, to avoid pulling
# every random capitalised word as a "name".
#   - "customer is Jayson", "customer: Jayson Lim", "customer name IJM Land"
#   - "debtor jayson", "debtor name IJM Land Sdn Bhd"
#   - "client: ABC Corp", "account name Pang Holdings"
# The lookahead stops the (non-greedy) capture before common verbs / connectors so
# "client: ABC Corp ordered RF2601-025" yields just "ABC Corp" rather than the rest.
_NAME_STOP_WORDS_RE = (
    r"(?:and|with|for|of|the|a|an|is|was|has|have|had|who|that|"
    r"order(?:ed|ing|s)?|buy(?:s|ing)?|bought|"
    r"want(?:s|ed|ing)?|need(?:s|ed|ing)?|file(?:d|s)?|filing|"
    r"product|sku|date|do|delivery|complaint|complain(?:t|ing|s|ed)?|"
    r"quantity|qty|in|on|at|by|to|from)"
)
_NAME_MARKER_RE = re.compile(
    r"(?:customer(?:\s+name)?|debtor(?:\s+name)?|client(?:\s+name)?|account(?:\s+name)?|company)"
    r"\s*(?:is|are|:|=|->|→|—|-)?\s*"
    r"([A-Za-z][A-Za-z0-9&'.\- ]{1,60}?)"
    r"(?=$|[,;.\n!?]|\s+" + _NAME_STOP_WORDS_RE + r"\b)",
    re.IGNORECASE,
)


# Free-word scan for names that lack an explicit marker. We extract alphabetic
# words/phrases (>=3 chars, not a stopword) so the resolver's Tier-1 debtor probe can
# do a single bulk `LOWER(debtor_name) IN (...)` lookup. This stays cheap because the
# probe runs ONE indexed query regardless of how many candidate words we feed it, and
# everything that doesn't match a real debtor name is dropped.
_FREEWORD_STOPWORDS: frozenset[str] = frozenset(
    {
        # functional / common English noise
        "the", "and", "for", "with", "from", "into", "onto", "this", "that", "those",
        "these", "their", "there", "then", "than", "what", "when", "where", "which",
        "who", "whom", "whose", "want", "wants", "wanted", "need", "needs", "needed",
        "have", "has", "had", "having", "is", "are", "was", "were", "been", "being",
        "do", "does", "did", "doing", "done",
        # CRM domain words that should never be matched as a customer name
        "complaint", "complaints", "complain", "complaining", "defect", "defects",
        "defective", "broken", "leak", "leaking", "warranty", "salesperson",
        "delivery", "deliveries", "delivered", "delivering", "ordered", "ordering",
        "order", "orders", "product", "products", "sku", "skus", "quantity", "qty",
        "customer", "customers", "debtor", "debtors", "client", "clients", "company",
        "companies", "account", "accounts", "invoice", "invoices", "shipment",
        "shipments", "stock", "incoming", "outgoing", "pending", "cancelled",
        "category", "brand", "promotion", "supplier", "suppliers", "warehouse",
        "warehouses", "discount", "price", "prices",
        # date words
        "today", "tomorrow", "yesterday", "morning", "afternoon", "evening", "night",
        "week", "weeks", "month", "months", "year", "years", "day", "days",
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        # short fillers
        "find", "look", "looking", "search", "searching", "show", "list", "lookup",
        "file", "filed", "files", "filing", "submit", "submits", "submitted",
        "submitting", "create", "created", "creating", "raise", "raised", "raising",
        "report", "reported", "reporting", "please", "thanks", "thank", "ok",
        "okay", "yes", "yeah", "no", "not",
        "all", "any", "some", "more", "less", "new", "old", "in", "on", "at", "to",
        "by", "of", "or", "if", "as", "be", "it", "i", "me", "my", "we", "us", "our",
        "you", "your", "he", "she", "him", "her", "they", "them",
        # form fields commonly mentioned
        "warranty", "type", "types", "address", "phone", "email", "name", "names",
        "person", "title", "project",
    }
)
_FREEWORD_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'.\-&]+")


def _extract_name_tokens(query: str, *, max_candidates: int) -> list[str]:
    """Pull name-like phrases that follow `customer`/`debtor`/`client` markers.

    Conservative: only fires on explicit markers, so "the customer is Jayson" yields
    `["Jayson"]` but "I am Jayson today" does not.
    """
    if not query:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for match in _NAME_MARKER_RE.finditer(query):
        raw = (match.group(1) or "").strip(" ,.;:-_'")
        if not raw or len(raw) < 2:
            continue
        # Strip trailing filler that slipped past the lookahead (defensive).
        cleaned = re.sub(
            r"\s+(?:has|who|that|with|for|of|the|order(?:ed|ing|s)?|bought|buy(?:s|ing)?)\s*.*$",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()
        if not cleaned or cleaned.lower() in _STOPWORDS:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= max_candidates:
            break
    return out



def _extract_freeword_tokens(query: str, *, max_candidates: int) -> list[str]:
    """Pull alphabetic word/phrase candidates that may be customer (debtor) names.

    Algorithm:
        1. Tokenise into individual alphabetic words.
        2. Drop stopwords / short fragments / month names / etc.
        3. Group consecutive non-stopword survivors into phrases (max 4 words each)
           so multi-word debtors like "IJM Land Sdn Bhd" stay together.
        4. Also emit each survivor as a single-word candidate so 1-word debtors
           ("Jayson") still resolve when the multi-word group misses.

    Used as a free-text fallback when the user just writes "Find DO for jayson Feb
    2026" with no explicit `customer:` marker. The resolver's debtor probe runs in
    a single bulk query so feeding it a handful of words is cheap; everything that
    doesn't hit a real `Order.debtor_name` is silently dropped.
    """
    if not query:
        return []
    surviving: list[str] = []  # words that pass stopword filtering, in order
    is_separator: list[bool] = []  # parallel flag: True when we crossed a stopword
    last_end = 0
    for match in _FREEWORD_TOKEN_RE.finditer(query):
        raw = (match.group(0) or "").strip(" ,.;:-_'")
        if not raw:
            continue
        lower = raw.lower()
        if lower in _FREEWORD_STOPWORDS or lower in _STOPWORDS:
            # Mark the next survivor as a phrase boundary.
            if surviving:
                is_separator[-1] = True
            last_end = match.end()
            continue
        if len(raw) < 3:
            if surviving:
                is_separator[-1] = True
            last_end = match.end()
            continue
        # Detect punctuation / digit / boundary between this word and the last
        # survivor — also treat as a phrase boundary.
        if surviving:
            gap = query[last_end : match.start()]
            if any(c in gap for c in (",", ";", ":", "\n", "!", "?", "(", ")", "/", "|")) or any(
                c.isdigit() for c in gap
            ):
                is_separator[-1] = True
        surviving.append(raw)
        is_separator.append(False)
        last_end = match.end()

    # Build phrases by grouping survivors until a separator flag.
    phrases: list[str] = []
    current: list[str] = []
    for word, sep in zip(surviving, is_separator):
        current.append(word)
        if sep or len(current) >= 4:
            phrases.append(" ".join(current))
            current = []
    if current:
        phrases.append(" ".join(current))

    out: list[str] = []
    seen: set[str] = set()
    # Emit phrases first (more specific), then individual words.
    for candidate in phrases + surviving:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
        if len(out) >= max_candidates:
            break
    return out


def extract_candidate_tokens(query: str, *, max_candidates: int = 8) -> list[str]:
    """Pull code-like tokens from the user's free-text query.

    Returns at most `max_candidates` unique tokens, preserving order of first appearance.
    Also includes name-like phrases that follow customer/debtor/client markers, so
    free-text customer references can be resolved against `Order.debtor_name`.
    """
    if not query:
        return []
    raw = _CODE_RE.findall(query)
    seen: set[str] = set()
    out: list[str] = []
    for tok in raw:
        t = tok.strip(".-_/").strip()
        if not t:
            continue
        if len(t) < 3:
            continue
        if t.lower() in _STOPWORDS:
            continue
        # Require BOTH a digit and a letter — rejects pure numbers ("2026", phone fragments)
        # and pure words simultaneously.
        if not (any(c.isdigit() for c in t) and any(c.isalpha() for c in t)):
            continue
        key = t.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= max_candidates:
            break

    # Append name-marker tokens (e.g. "customer is Jayson" → "Jayson"). These are
    # alphabetic and won't pass the code-token filter, so we add them here. They get
    # routed to `_probe_customer_debtor_name` and `_prefix_probe_customer_debtor_name`.
    remaining = max_candidates - len(out)
    if remaining > 0:
        for name_tok in _extract_name_tokens(query, max_candidates=remaining):
            key = name_tok.upper()
            if key in seen:
                continue
            seen.add(key)
            out.append(name_tok)
            if len(out) >= max_candidates:
                break
    return out


def extract_freeword_candidates(query: str, *, max_candidates: int = 6) -> list[str]:
    """Public helper exposing free-word debtor candidates (used by the resolver).

    Kept separate from `extract_candidate_tokens` so the regular code-token list
    stays small; these candidates are only fed to the `Order.debtor_name` probe.
    """
    return _extract_freeword_tokens(query, max_candidates=max_candidates)


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #
@dataclass
class ResolvedEntity:
    """One hit for a candidate token."""

    entity_type: str  # product | customer_order | customer | inbound_shipment | spo_allocation | grn | warehouse | supplier | promotion | transporter | form | attachment | attachment_type
    canonical_code: str  # the business code the user should pass to tools (e.g. order_number)
    uuid: Optional[str] = None  # the row's primary key — required for tools that accept UUID-only inputs
    display: dict[str, Any] = field(default_factory=dict)
    match_field: str = ""  # which column matched (e.g. "product_code", "product_name")
    match_tier: str = "exact"  # "exact" | "prefix" | "substring" | "embedding"
    similarity: Optional[float] = None  # cosine similarity for embedding-tier matches


@dataclass
class TokenResolution:
    token: str
    matches: list[ResolvedEntity] = field(default_factory=list)
    ambiguous: bool = False  # True when we found multiple candidates but picked none

    @property
    def resolved(self) -> bool:
        # A single confident match. Ambiguous tokens are NOT resolved — the LLM must ask.
        return bool(self.matches) and not self.ambiguous

    @property
    def confident_match(self) -> Optional[ResolvedEntity]:
        """The single canonical match to pass to other tools, or None if ambiguous / unresolved."""
        if self.ambiguous or not self.matches:
            return None
        return self.matches[0]


@dataclass
class ResolutionResult:
    tokens: list[str]
    resolutions: list[TokenResolution]
    elapsed_ms: float

    @property
    def unresolved_tokens(self) -> list[str]:
        """Tokens with zero candidate matches (NOT tokens that are ambiguous)."""
        return [r.token for r in self.resolutions if not r.matches]

    @property
    def ambiguous_tokens(self) -> list[str]:
        return [r.token for r in self.resolutions if r.ambiguous]

    @property
    def has_any_match(self) -> bool:
        return any(r.resolved for r in self.resolutions)

    def to_prompt_block(self) -> str:
        """Render an authoritative block for the LLM. Empty string when nothing useful."""
        if not self.resolutions:
            return ""
        lines: list[str] = []
        resolved = [r for r in self.resolutions if r.resolved]
        ambiguous = [r for r in self.resolutions if r.ambiguous]
        unresolved = [r.token for r in self.resolutions if not r.matches]
        if resolved:
            lines.append("Resolved references in user query (authoritative \u2014 use these):")
            for tr in resolved:
                for match in tr.matches:
                    display_bits = [f"{k}={v}" for k, v in match.display.items() if v not in (None, "", [])]
                    desc = ", ".join(display_bits)
                    tier_note = ""
                    if match.match_tier == "prefix":
                        tier_note = f" (fuzzy prefix match on {match.match_field})"
                    elif match.match_tier == "substring":
                        tier_note = f" (fuzzy substring match on {match.match_field})"
                    elif match.match_tier == "embedding":
                        sim_str = f"{match.similarity:.2f}" if match.similarity is not None else "?"
                        tier_note = f" (semantic match, similarity={sim_str})"
                    lines.append(
                        f'- "{tr.token}" \u2192 {match.entity_type} (canonical_code={match.canonical_code})'
                        + tier_note
                        + (f" [{desc}]" if desc else "")
                    )
        if ambiguous:
            if lines:
                lines.append("")
            lines.append(
                "Ambiguous references in user query (multiple candidates \u2014 ask the user to pick one, "
                "do NOT call any tool yet):"
            )
            for tr in ambiguous:
                lines.append(f'- "{tr.token}" could be any of:')
                for match in tr.matches:
                    display_bits = [f"{k}={v}" for k, v in match.display.items() if v not in (None, "", [])]
                    desc = ", ".join(display_bits)
                    lines.append(
                        f"    \u00b7 {match.entity_type} (canonical_code={match.canonical_code})"
                        + (f" [{desc}]" if desc else "")
                    )
        if unresolved:
            if lines:
                lines.append("")
            lines.append("Unresolved references (tell the user no record was found, do not guess):")
            for t in unresolved:
                lines.append(
                    f'- "{t}" \u2014 no matching product, order, shipment, customer, supplier, warehouse, SPO, GRN, or promotion.'
                )
        return "\n".join(lines).strip()

    def to_query_hint(self) -> str:
        """Short hint appended to the reformulated query so the RAG tool picker sees entity types."""
        if not self.resolutions:
            return ""
        bits: list[str] = []
        for tr in self.resolutions:
            if tr.resolved:
                types = ", ".join(sorted({m.entity_type for m in tr.matches}))
                bits.append(f'"{tr.token}" is {types}')
            elif tr.ambiguous:
                types = ", ".join(sorted({m.entity_type for m in tr.matches}))
                bits.append(f'"{tr.token}" ambiguous ({types})')
            else:
                bits.append(f'"{tr.token}" unresolved')
        return "Resolved references: " + "; ".join(bits) + "."

    def as_dict(self) -> dict[str, Any]:
        return {
            "tokens": self.tokens,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "resolutions": [
                {
                    "token": tr.token,
                    "resolved": tr.resolved,
                    "ambiguous": tr.ambiguous,
                    "matches": [
                        {
                            "entity_type": m.entity_type,
                            "canonical_code": m.canonical_code,
                            "uuid": m.uuid,
                            "match_field": m.match_field,
                            "match_tier": m.match_tier,
                            "similarity": m.similarity,
                            "display": m.display,
                        }
                        for m in tr.matches
                    ],
                }
                for tr in self.resolutions
            ],
            "unresolved_tokens": self.unresolved_tokens,
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _first_nonempty(values: Iterable[Any]) -> Any:
    for v in values:
        if v not in (None, "", []):
            return v
    return None


# --------------------------------------------------------------------------- #
# Per-entity probes
# --------------------------------------------------------------------------- #
def _strip_all_ws(value: str) -> str:
    """Collapse every whitespace run to empty. For code-style tokens where the
    agent typed (or the user pasted) a stray space inside what should be one
    contiguous code — e.g. 'cgb9032b- new' → 'cgb9032b-new'."""
    return re.sub(r"\s+", "", value or "")


def _ws_insensitive_lower(col):
    """Postgres expression: `lower(regexp_replace(col, '\\s+', '', 'g'))`.

    Pair with python-side `_strip_all_ws(token.lower())` so code-style fields
    (product_code, order_number, shipment_number, supplier_code, ...) match
    whether either side carries stray whitespace. Cheap on small lookup
    tables; for large tables consider a functional index if hot."""
    return func.lower(func.regexp_replace(col, r"\s+", "", "g"))


def _probe_product(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Exact match on product_code (case-insensitive, whitespace-insensitive).

    Both sides are whitespace-stripped so 'cgb9032b- new' matches DB code
    'CGB9032B-NEW' (and vice versa, if a DB row was seeded with a stray space)."""
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    # Build (original_token, normalized_token) pairs so we can map matched rows
    # back to the caller's token after the SQL comparison.
    normalized_tokens = [_strip_all_ws(t.lower()) for t in tokens]
    norm_to_token = dict(zip(normalized_tokens, tokens))
    rows = (
        db.query(Product.id, Product.product_code, Product.product_name, Product.is_active)
        .filter(_ws_insensitive_lower(Product.product_code).in_(list(norm_to_token.keys())))
        .all()
    )
    for pid, code, name, is_active in rows:
        norm = _strip_all_ws(str(code).lower())
        token = norm_to_token.get(norm)
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="product",
                canonical_code=code,
                uuid=str(pid) if pid else None,
                match_field="product_code",
                display={"product_name": name, "is_active": bool(is_active)},
            )
        )
    return result


def _probe_customer_order(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Exact match on orders.order_number, joined to order_statuses for the label."""
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    normalized = [_strip_all_ws(t.lower()) for t in tokens]
    norm_to_token = dict(zip(normalized, tokens))
    rows = (
        db.query(
            Order.id,
            Order.order_number,
            Order.debtor_name,
            Order.order_date,
            Order.estimated_delivery_date,
            Order.actual_delivery_date,
            Order.pickup_time,
            Order.transporter,
            Order.is_cancelled,
            OrderStatus.status_name,
            OrderStatus.status_code,
        )
        .outerjoin(OrderStatus, OrderStatus.id == Order.order_status_id)
        .filter(_ws_insensitive_lower(Order.order_number).in_(list(norm_to_token.keys())), Order.deleted_at.is_(None))
        .all()
    )
    for row in rows:
        token = norm_to_token.get(_strip_all_ws(str(row.order_number).lower()))
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="customer_order",
                canonical_code=row.order_number,
                uuid=str(row.id) if row.id else None,
                match_field="order_number",
                display={
                    "customer_name": row.debtor_name,
                    "status": row.status_name or row.status_code,
                    "order_date": _iso(row.order_date),
                    "estimated_delivery_date": _iso(row.estimated_delivery_date),
                    "actual_delivery_date": _iso(row.actual_delivery_date),
                    "pickup_time": row.pickup_time,
                    "transporter": row.transporter,
                    "is_cancelled": bool(row.is_cancelled) if row.is_cancelled is not None else False,
                },
            )
        )
    return result


def _probe_customer(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Exact match on customer_code; fuzzy ILIKE on customer_name / phone_number / email."""
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    lowered = [t.lower() for t in tokens]
    # Exact by customer_code — whitespace-insensitive on both sides so a typed
    # "300- C043" still hits "300-C043".
    norm_to_token = {_strip_all_ws(t.lower()): t for t in tokens}
    rows = (
        db.query(
            Customer.id,
            Customer.customer_code,
            Customer.customer_name,
            Customer.phone_number,
            Customer.email,
            Customer.is_active,
        )
        .filter(_ws_insensitive_lower(Customer.customer_code).in_(list(norm_to_token.keys())))
        .all()
    )
    for cid, code, name, phone, email, is_active in rows:
        token = norm_to_token.get(_strip_all_ws(str(code).lower()))
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="customer",
                canonical_code=code,
                uuid=str(cid) if cid else None,
                match_field="customer_code",
                display={
                    "customer_name": name,
                    "phone_number": phone,
                    "email": email,
                    "is_active": bool(is_active) if is_active is not None else True,
                },
            )
        )
    # Fuzzy on name / phone (only if still unresolved to avoid noise).
    # Phone probe restricted to digit-bearing tokens — keeps name tokens like
    # "chin chun" from accidentally substring-hitting phone numbers, which
    # otherwise floods the fuzzy result with unrelated rows.
    _CUSTOMER_FUZZY_LIMIT = 25
    unresolved = [t for t in tokens if not result[t]]
    for token in unresolved:
        term = f"%{token}%"
        token_has_digit = any(ch.isdigit() for ch in token)
        name_or_phone = (
            or_(
                Customer.customer_name.ilike(term),
                Customer.phone_number.ilike(term),
            )
            if token_has_digit
            else Customer.customer_name.ilike(term)
        )
        rows = (
            db.query(
                Customer.id,
                Customer.customer_code,
                Customer.customer_name,
                Customer.phone_number,
                Customer.email,
            )
            .filter(name_or_phone)
            .limit(_CUSTOMER_FUZZY_LIMIT + 1)
            .all()
        )
        truncated = len(rows) > _CUSTOMER_FUZZY_LIMIT
        rows = rows[:_CUSTOMER_FUZZY_LIMIT]
        for cid, code, name, phone, email in rows:
            display = {"customer_name": name, "phone_number": phone, "email": email}
            if truncated:
                display["truncated_more_available"] = True
            result[token].append(
                ResolvedEntity(
                    entity_type="customer",
                    canonical_code=code or name,
                    uuid=str(cid) if cid else None,
                    match_field="customer_name" if (name and token.lower() in (name or "").lower()) else "phone_number",
                    display=display,
                )
            )
    return result


def _probe_customer_debtor_name(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Resolve a token against the unique `Order.debtor_name` set.

    Customers are stored as denormalised `debtor_name` on `orders`, so a complaint flow
    that asks the user "which customer?" may receive a free-text name (e.g. "Jayson",
    "IJM Land"). We treat any matching debtor as `entity_type=customer` and surface the
    debtor_name as the canonical code so downstream tools can pass it via `query`.
    """
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result

    # Tier 1 — exact case-insensitive match.
    lowered = [t.lower() for t in tokens if t]
    rows = (
        db.query(Order.debtor_name, Order.debtor_code, Customer.id)
        .outerjoin(Customer, func.lower(func.btrim(Customer.customer_name)) == func.lower(func.btrim(Order.debtor_name)))
        .filter(
            Order.deleted_at.is_(None),
            Order.debtor_name.isnot(None),
            func.lower(Order.debtor_name).in_(lowered),
        )
        .distinct()
        .all()
    )
    name_to_token = {t.lower(): t for t in tokens if t}
    for debtor_name, debtor_code, customer_id in rows:
        token = name_to_token.get(str(debtor_name).lower())
        if not token:
            continue
        if any(m.canonical_code == debtor_name for m in result[token]):
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="customer",
                canonical_code=debtor_name,
                uuid=str(customer_id) if customer_id else None,
                match_field="debtor_name",
                display={"debtor_name": debtor_name, "debtor_code": debtor_code, "source": "orders"},
            )
        )

    # Tier 2 fallback — partial / fuzzy ILIKE on debtor_name for any token still
    # unresolved. The debtor master is denormalised onto `orders`, so customers
    # without a `customers` row (e.g. "FIRA VENTURE ENTERPRISE (PROJECT-CASH)")
    # are only reachable via this scan. Also tolerates pluralised input
    # ("fira ventures" → "FIRA VENTURE …") by stripping a trailing 's'.
    unresolved = [t for t in tokens if not result[t]]
    for token in unresolved:
        # Guard: a 2-3 char token (e.g. "DO" meaning Delivery Order) is too
        # short to safely substring-match a debtor name without false hits
        # like "FREDONIA". Tier-1 exact match above still catches short
        # tokens that legitimately equal a full debtor_name.
        if len(token) < 4:
            continue
        variants: list[str] = [token]
        stripped = token.rstrip("s")
        if stripped and stripped != token and len(stripped) >= 4:
            variants.append(stripped)
        like_clauses = [Order.debtor_name.ilike(f"%{v}%") for v in variants if v]
        if not like_clauses:
            continue
        _DEBTOR_FUZZY_LIMIT = 25
        rows = (
            db.query(Order.debtor_name, Order.debtor_code, Customer.id)
            .outerjoin(Customer, func.lower(func.btrim(Customer.customer_name)) == func.lower(func.btrim(Order.debtor_name)))
            .filter(
                Order.deleted_at.is_(None),
                Order.debtor_name.isnot(None),
                or_(*like_clauses),
            )
            .distinct()
            .limit(_DEBTOR_FUZZY_LIMIT + 1)
            .all()
        )
        truncated = len(rows) > _DEBTOR_FUZZY_LIMIT
        rows = rows[:_DEBTOR_FUZZY_LIMIT]
        for debtor_name, debtor_code, customer_id in rows:
            if any(m.canonical_code == debtor_name for m in result[token]):
                continue
            display = {"debtor_name": debtor_name, "debtor_code": debtor_code, "source": "orders"}
            if truncated:
                display["truncated_more_available"] = True
            result[token].append(
                ResolvedEntity(
                    entity_type="customer",
                    canonical_code=debtor_name,
                    uuid=str(customer_id) if customer_id else None,
                    match_field="debtor_name",
                    display=display,
                )
            )
    return result


def _probe_transporter_freeword(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Free-text substring lookup against `Transporter.name` / `normalized_name`.

    The free-text debtor_name scan handles customer phrases like "fira ventures";
    this mirror covers transporter phrases like "gt delivery" or "suncrest" so
    a single `entities` bag can resolve transporter mentions without an explicit
    marker. Token length >= 4 to avoid false positives like "DO".
    """
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    for token in tokens:
        if not token or len(token) < 4:
            continue
        term = f"%{token}%"
        rows = (
            db.query(Transporter.id, Transporter.code, Transporter.name, Transporter.normalized_name)
            .filter(
                or_(
                    Transporter.name.ilike(term),
                    Transporter.normalized_name.ilike(term),
                    Transporter.code.ilike(term),
                )
            )
            .limit(25)
            .all()
        )
        for tid, code, name, _norm in rows:
            if any(m.canonical_code == code for m in result[token]):
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="transporter",
                    canonical_code=code,
                    uuid=str(tid) if tid else None,
                    match_field="transporter_name",
                    match_tier="substring",
                    display={"code": code, "name": name},
                )
            )
    return result


def _probe_transporter(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Exact match on transporter code/name/normalized_name; ilike fallback for
    tokens that look like a transporter label (e.g. "suncrest", "asac")."""
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    lowered = [t.lower() for t in tokens if t]
    # Code is whitespace-insensitive; name / normalized_name keep spaces because
    # human names ("GT Delivery") legitimately contain them.
    normalized_codes = [_strip_all_ws(t) for t in lowered]
    rows = (
        db.query(Transporter.id, Transporter.code, Transporter.name, Transporter.normalized_name)
        .filter(
            or_(
                _ws_insensitive_lower(Transporter.code).in_(normalized_codes),
                func.lower(Transporter.name).in_(lowered),
                func.lower(Transporter.normalized_name).in_(lowered),
            )
        )
        .all()
    )
    for tid, code, name, norm in rows:
        for token in tokens:
            tl = token.lower()
            tl_no_ws = _strip_all_ws(tl)
            code_no_ws = _strip_all_ws((code or "").lower())
            if tl_no_ws != code_no_ws and tl not in {(name or "").lower(), (norm or "").lower()}:
                continue
            if any(m.canonical_code == code for m in result[token]):
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="transporter",
                    canonical_code=code,
                    uuid=str(tid) if tid else None,
                    match_field="transporter_code" if tl == (code or "").lower() else "transporter_name",
                    display={"code": code, "name": name},
                )
            )
    # Substring fallback for unresolved tokens.
    unresolved = [t for t in tokens if not result[t]]
    for token in unresolved:
        if len(token) < 4:
            continue
        term = f"%{token}%"
        rows = (
            db.query(Transporter.id, Transporter.code, Transporter.name, Transporter.normalized_name)
            .filter(
                or_(
                    Transporter.name.ilike(term),
                    Transporter.normalized_name.ilike(term),
                )
            )
            .limit(25)
            .all()
        )
        for tid, code, name, _norm in rows:
            if any(m.canonical_code == code for m in result[token]):
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="transporter",
                    canonical_code=code,
                    uuid=str(tid) if tid else None,
                    match_field="transporter_name",
                    display={"code": code, "name": name},
                )
            )
    return result


def _probe_inbound_shipment(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Exact match across shipment_number / container / BOL / invoice."""
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    # All four match fields are number-style identifiers — strip whitespace
    # both sides so 'SHP- 2026-001' matches 'SHP-2026-001' etc.
    normalized = [_strip_all_ws(t.lower()) for t in tokens]
    rows = (
        db.query(
            InboundShipment.id,
            InboundShipment.shipment_number,
            InboundShipment.shipping_container_number,
            InboundShipment.bill_of_lading_number,
            InboundShipment.invoice_number,
            InboundShipment.shipment_status,
            InboundShipment.estimated_arrival_date,
            InboundShipment.actual_arrival_date,
        )
        .filter(
            or_(
                _ws_insensitive_lower(InboundShipment.shipment_number).in_(normalized),
                _ws_insensitive_lower(InboundShipment.shipping_container_number).in_(normalized),
                _ws_insensitive_lower(InboundShipment.bill_of_lading_number).in_(normalized),
                _ws_insensitive_lower(InboundShipment.invoice_number).in_(normalized),
            )
        )
        .all()
    )
    for row in rows:
        for token in tokens:
            tl_no_ws = _strip_all_ws(token.lower())
            match_field = None
            if row.shipment_number and _strip_all_ws(row.shipment_number.lower()) == tl_no_ws:
                match_field = "shipment_number"
            elif row.shipping_container_number and _strip_all_ws(row.shipping_container_number.lower()) == tl_no_ws:
                match_field = "shipping_container_number"
            elif row.bill_of_lading_number and _strip_all_ws(row.bill_of_lading_number.lower()) == tl_no_ws:
                match_field = "bill_of_lading_number"
            elif row.invoice_number and _strip_all_ws(row.invoice_number.lower()) == tl_no_ws:
                match_field = "invoice_number"
            if not match_field:
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="inbound_shipment",
                    canonical_code=row.shipment_number,
                    uuid=str(row.id) if row.id else None,
                    match_field=match_field,
                    display={
                        "shipment_number": row.shipment_number,
                        "shipping_container_number": row.shipping_container_number,
                        "shipment_status": row.shipment_status,
                        "estimated_arrival_date": _iso(row.estimated_arrival_date),
                        "actual_arrival_date": _iso(row.actual_arrival_date),
                    },
                )
            )
    return result


def _probe_spo(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    norm_to_token = {_strip_all_ws(t.lower()): t for t in tokens}
    rows = (
        db.query(SPOAllocation.id, SPOAllocation.spo_number)
        .filter(_ws_insensitive_lower(SPOAllocation.spo_number).in_(list(norm_to_token.keys())))
        .distinct()
        .all()
    )
    for sid, spo_number in rows:
        token = norm_to_token.get(_strip_all_ws(str(spo_number or "").lower()))
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="spo_allocation",
                canonical_code=spo_number,
                uuid=str(sid) if sid else None,
                match_field="spo_number",
                display={"spo_number": spo_number},
            )
        )
    return result


def _probe_grn(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    norm_to_token = {_strip_all_ws(t.lower()): t for t in tokens}
    rows = (
        db.query(
            PickingHeader.id,
            PickingHeader.picking_number,
            PickingHeader.picking_date,
            PickingHeader.picking_status,
            PickingHeader.picking_type,
        )
        .filter(
            _ws_insensitive_lower(PickingHeader.picking_number).in_(list(norm_to_token.keys())),
            PickingHeader.picking_type == "goods_received",
        )
        .all()
    )
    for row in rows:
        token = norm_to_token.get(_strip_all_ws(str(row.picking_number).lower()))
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="grn",
                canonical_code=row.picking_number,
                uuid=str(row.id) if row.id else None,
                match_field="picking_number",
                display={
                    "grn_number": row.picking_number,
                    "grn_date": _iso(row.picking_date),
                    "grn_status": row.picking_status,
                },
            )
        )
    return result


def _probe_warehouse(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    norm_to_token = {_strip_all_ws(t.lower()): t for t in tokens}
    rows = (
        db.query(Warehouse.id, Warehouse.warehouse_code, Warehouse.warehouse_name, Warehouse.location, Warehouse.is_active)
        .filter(_ws_insensitive_lower(Warehouse.warehouse_code).in_(list(norm_to_token.keys())))
        .all()
    )
    for wid, code, name, location, is_active in rows:
        token = norm_to_token.get(_strip_all_ws(str(code).lower()))
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="warehouse",
                canonical_code=code,
                uuid=str(wid) if wid else None,
                match_field="warehouse_code",
                display={
                    "warehouse_name": name,
                    "location": location,
                    "is_active": bool(is_active) if is_active is not None else True,
                },
            )
        )
    return result


def _probe_supplier(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    norm_to_token = {_strip_all_ws(t.lower()): t for t in tokens}
    rows = (
        db.query(
            Supplier.id,
            Supplier.supplier_code,
            Supplier.supplier_name,
            Supplier.contact_name,
            Supplier.email,
            Supplier.phone_number,
            Supplier.is_active,
        )
        .filter(_ws_insensitive_lower(Supplier.supplier_code).in_(list(norm_to_token.keys())))
        .all()
    )
    for sid, code, name, contact, email, phone, is_active in rows:
        token = norm_to_token.get(_strip_all_ws(str(code).lower()))
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="supplier",
                canonical_code=code,
                uuid=str(sid) if sid else None,
                match_field="supplier_code",
                display={
                    "supplier_name": name,
                    "contact_name": contact,
                    "email": email,
                    "phone_number": phone,
                    "is_active": bool(is_active) if is_active is not None else True,
                },
            )
        )
    return result


def _probe_promotion(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    return {t: [] for t in tokens}


def _probe_attachment(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Exact case-insensitive match on attachments.original_filename (without extension or with).

    Attachments have no business code; the filename and user-editable description are the
    only human handles. Tier-1 matches a token equal to the filename (e.g. "catalogue-2026.pdf").
    """
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(
            Attachment.id,
            Attachment.original_filename,
            Attachment.description,
            Attachment.mime_type,
            Attachment.full_directory_path,
            AttachmentType.type_name,
        )
        .outerjoin(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(
            Attachment.is_deleted.is_(False),
            func.lower(Attachment.original_filename).in_(lowered),
        )
        .all()
    )
    name_to_token = {t.lower(): t for t in tokens}
    for aid, filename, description, mime, dir_path, type_name in rows:
        token = name_to_token.get(str(filename).lower())
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="attachment",
                canonical_code=filename,
                uuid=str(aid) if aid else None,
                match_field="original_filename",
                display={
                    "filename": filename,
                    "description": description,
                    "attachment_type": type_name,
                    "mime_type": mime,
                    "directory": dir_path,
                },
            )
        )
    return result


def _probe_attachment_type(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Exact case-insensitive match on AttachmentType.code OR type_name.

    AttachmentType is a small reference table (BROCHURE / SPEC SHEET / DATASHEET /
    CATALOGUE / etc.). Free-text doc-class words like "catalogue", "brochure",
    "spec sheet" resolve to the canonical AttachmentType UUID, which downstream
    callers feed as `attachment_type_ids` / `attachment_type_id` to attachment
    list tools.
    """
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(
            AttachmentType.id,
            AttachmentType.code,
            AttachmentType.type_name,
            AttachmentType.description,
        )
        .filter(
            or_(
                func.lower(AttachmentType.code).in_(lowered),
                func.lower(AttachmentType.type_name).in_(lowered),
            )
        )
        .all()
    )
    norm_to_token = {t.lower(): t for t in tokens}
    for tid, code, type_name, description in rows:
        key = (code or "").lower()
        token = norm_to_token.get(key)
        match_field = "code"
        if not token:
            key = (type_name or "").lower()
            token = norm_to_token.get(key)
            match_field = "type_name"
        if not token:
            continue
        canonical = code or type_name
        result[token].append(
            ResolvedEntity(
                entity_type="attachment_type",
                canonical_code=canonical,
                uuid=str(tid) if tid else None,
                match_field=match_field,
                display={
                    "code": code,
                    "type_name": type_name,
                    "description": description,
                },
            )
        )
    return result


# --------------------------------------------------------------------------- #
# Tier 2 — prefix / substring probes (run only for tokens Tier 1 missed)
# --------------------------------------------------------------------------- #
# A Tier-2 probe takes a SINGLE token and returns a list of candidate entities.
# - Preference order: prefix match first, then substring.
# - Any token with >1 candidate is surfaced to the LLM as "ambiguous" so it asks
#   the user to pick, rather than silently guessing or failing with "no record".
PREFIX_LIMIT = 20


def _prefix_probe_product(db: Session, token: str) -> list[ResolvedEntity]:
    # Strip whitespace from both sides so 'cgb9032b- new' matches 'CGB9032B-NEW'.
    norm_token = _strip_all_ws(token)
    prefix = f"{norm_token}%"
    substr = f"%{norm_token}%"
    code_norm = _ws_insensitive_lower(Product.product_code)
    rows = (
        db.query(Product.id, Product.product_code, Product.product_name, Product.is_active)
        .filter(code_norm.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    tier = "prefix"
    if not rows:
        rows = (
            db.query(Product.id, Product.product_code, Product.product_name, Product.is_active)
            .filter(code_norm.ilike(substr))
            .limit(PREFIX_LIMIT)
            .all()
        )
        tier = "substring"
    if not rows:
        # Name-search fallback for free-text product phrases ("basin",
        # "kitchen sink", "matte black bathtub"). Code-only matching above
        # misses these because the token isn't a SKU. AND across words, OR
        # across columns. Single words must be ≥4 chars (filters short noise
        # like "the" / "and"); multi-word phrases keep the ≥3 cutoff per word.
        # Caller intent (e.g. brand / category hint) flows through the
        # `_TIER2_PROBES` filter, so this only fires when the agent asked for
        # product candidates.
        if " " in token:
            words = [w for w in token.split() if len(w) >= 3]
            min_words = 2
        else:
            words = [token] if len(token) >= 4 else []
            min_words = 1
        if len(words) >= min_words:
            q = db.query(
                Product.id, Product.product_code, Product.product_name, Product.is_active
            )
            for w in words:
                ws = f"%{w}%"
                q = q.filter(
                    or_(
                        Product.product_name.ilike(ws),
                        Product.description.ilike(ws),
                    )
                )
            rows = q.limit(PREFIX_LIMIT).all()
            tier = "word"
    return [
        ResolvedEntity(
            entity_type="product",
            canonical_code=code,
            uuid=str(pid) if pid else None,
            match_field="product_code",
            match_tier=tier,
            display={"product_name": name, "is_active": bool(is_active)},
        )
        for pid, code, name, is_active in rows
    ]


def _prefix_probe_customer_order(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(
            Order.id,
            Order.order_number,
            Order.debtor_name,
            Order.estimated_delivery_date,
            Order.actual_delivery_date,
            OrderStatus.status_name,
        )
        .outerjoin(OrderStatus, OrderStatus.id == Order.order_status_id)
        .filter(Order.order_number.ilike(prefix), Order.deleted_at.is_(None))
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="customer_order",
            canonical_code=row.order_number,
            uuid=str(row.id) if row.id else None,
            match_field="order_number",
            match_tier="prefix",
            display={
                "customer_name": row.debtor_name,
                "status": row.status_name,
                "estimated_delivery_date": _iso(row.estimated_delivery_date),
                "actual_delivery_date": _iso(row.actual_delivery_date),
            },
        )
        for row in rows
    ]


def _prefix_probe_inbound_shipment(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(
            InboundShipment.id,
            InboundShipment.shipment_number,
            InboundShipment.shipping_container_number,
            InboundShipment.shipment_status,
            InboundShipment.estimated_arrival_date,
        )
        .filter(
            or_(
                InboundShipment.shipment_number.ilike(prefix),
                InboundShipment.shipping_container_number.ilike(prefix),
                InboundShipment.bill_of_lading_number.ilike(prefix),
                InboundShipment.invoice_number.ilike(prefix),
            )
        )
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="inbound_shipment",
            canonical_code=row.shipment_number,
            uuid=str(row.id) if row.id else None,
            match_field="shipment_number",
            match_tier="prefix",
            display={
                "shipment_number": row.shipment_number,
                "shipping_container_number": row.shipping_container_number,
                "shipment_status": row.shipment_status,
                "estimated_arrival_date": _iso(row.estimated_arrival_date),
            },
        )
        for row in rows
    ]


def _prefix_probe_customer(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(Customer.id, Customer.customer_code, Customer.customer_name, Customer.phone_number)
        .filter(Customer.customer_code.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="customer",
            canonical_code=code,
            uuid=str(cid) if cid else None,
            match_field="customer_code",
            match_tier="prefix",
            display={"customer_name": name, "phone_number": phone},
        )
        for cid, code, name, phone in rows
    ]


def _prefix_probe_customer_debtor_name(db: Session, token: str) -> list[ResolvedEntity]:
    """Prefix → substring ILIKE on `Order.debtor_name` (distinct).

    Returns at most PREFIX_LIMIT distinct debtors. The caller treats >1 result as
    ambiguous and asks the user to pick.
    """
    if not token or len(token) < 3:
        return []
    prefix = f"{token}%"
    substr = f"%{token}%"
    rows = (
        db.query(Order.debtor_name, Order.debtor_code, Customer.id)
        .outerjoin(Customer, func.lower(func.btrim(Customer.customer_name)) == func.lower(func.btrim(Order.debtor_name)))
        .filter(
            Order.deleted_at.is_(None),
            Order.debtor_name.isnot(None),
            Order.debtor_name.ilike(prefix),
        )
        .distinct()
        .limit(PREFIX_LIMIT)
        .all()
    )
    tier = "prefix"
    if not rows:
        rows = (
            db.query(Order.debtor_name, Order.debtor_code, Customer.id)
            .outerjoin(Customer, func.lower(func.btrim(Customer.customer_name)) == func.lower(func.btrim(Order.debtor_name)))
            .filter(
                Order.deleted_at.is_(None),
                Order.debtor_name.isnot(None),
                Order.debtor_name.ilike(substr),
            )
            .distinct()
            .limit(PREFIX_LIMIT)
            .all()
        )
        tier = "substring"
    if not rows:
        # Per-word AND fallback — handles typos / dropped letters in multi-word
        # debtor phrases. Token "Delux home centre" against "DELUXE HOME CENTRE
        # SDN BHD": full-string substring miss (extra 'E' in DELUXE breaks the
        # contiguous phrase) but every word still appears individually. AND
        # across words ≥3 chars on debtor_name.
        words = [w for w in token.split() if len(w) >= 3]
        if len(words) >= 2:
            q = (
                db.query(Order.debtor_name, Order.debtor_code, Customer.id)
                .outerjoin(Customer, func.lower(func.btrim(Customer.customer_name)) == func.lower(func.btrim(Order.debtor_name)))
                .filter(Order.deleted_at.is_(None), Order.debtor_name.isnot(None))
            )
            for w in words:
                q = q.filter(Order.debtor_name.ilike(f"%{w}%"))
            rows = q.distinct().limit(PREFIX_LIMIT).all()
            tier = "word"
    seen: set[str] = set()
    out: list[ResolvedEntity] = []
    for debtor_name, debtor_code, customer_id in rows:
        key = (debtor_name or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            ResolvedEntity(
                entity_type="customer",
                canonical_code=debtor_name,
                uuid=str(customer_id) if customer_id else None,
                match_field="debtor_name",
                match_tier=tier,
                display={"debtor_name": debtor_name, "debtor_code": debtor_code, "source": "orders"},
            )
        )
    return out


def _prefix_probe_warehouse(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(Warehouse.id, Warehouse.warehouse_code, Warehouse.warehouse_name, Warehouse.is_active)
        .filter(Warehouse.warehouse_code.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="warehouse",
            canonical_code=code,
            uuid=str(wid) if wid else None,
            match_field="warehouse_code",
            match_tier="prefix",
            display={"warehouse_name": name, "is_active": bool(is_active)},
        )
        for wid, code, name, is_active in rows
    ]


def _prefix_probe_supplier(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(Supplier.id, Supplier.supplier_code, Supplier.supplier_name, Supplier.is_active)
        .filter(Supplier.supplier_code.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="supplier",
            canonical_code=code,
            uuid=str(sid) if sid else None,
            match_field="supplier_code",
            match_tier="prefix",
            display={"supplier_name": name, "is_active": bool(is_active)},
        )
        for sid, code, name, is_active in rows
    ]


def _prefix_probe_spo(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(SPOAllocation.id, SPOAllocation.spo_number)
        .filter(SPOAllocation.spo_number.ilike(prefix))
        .distinct()
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="spo_allocation",
            canonical_code=spo,
            uuid=str(sid) if sid else None,
            match_field="spo_number",
            match_tier="prefix",
            display={"spo_number": spo},
        )
        for sid, spo in rows
    ]


def _prefix_probe_grn(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(
            PickingHeader.id,
            PickingHeader.picking_number,
            PickingHeader.picking_date,
            PickingHeader.picking_status,
        )
        .filter(
            PickingHeader.picking_number.ilike(prefix),
            PickingHeader.picking_type == "goods_received",
        )
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="grn",
            canonical_code=row.picking_number,
            uuid=str(row.id) if row.id else None,
            match_field="picking_number",
            match_tier="prefix",
            display={
                "grn_number": row.picking_number,
                "grn_date": _iso(row.picking_date),
                "grn_status": row.picking_status,
            },
        )
        for row in rows
    ]


def _prefix_probe_transporter(db: Session, token: str) -> list[ResolvedEntity]:
    """Prefix → substring ILIKE on `Transporter.code` / `name` / `normalized_name`.

    Lets a free-text chunk like "gt delivery" / "suncrest" resolve to a transporter
    without needing an explicit marker word in the user's phrasing. Tier-2 keeps
    short noise tokens out via the >=3 length guard.
    """
    if not token or len(token) < 3:
        return []
    prefix = f"{token}%"
    substr = f"%{token}%"
    rows = (
        db.query(Transporter.id, Transporter.code, Transporter.name, Transporter.normalized_name)
        .filter(
            or_(
                Transporter.code.ilike(prefix),
                Transporter.name.ilike(prefix),
                Transporter.normalized_name.ilike(prefix),
            )
        )
        .limit(PREFIX_LIMIT)
        .all()
    )
    tier = "prefix"
    if not rows:
        rows = (
            db.query(Transporter.id, Transporter.code, Transporter.name, Transporter.normalized_name)
            .filter(
                or_(
                    Transporter.code.ilike(substr),
                    Transporter.name.ilike(substr),
                    Transporter.normalized_name.ilike(substr),
                )
            )
            .limit(PREFIX_LIMIT)
            .all()
        )
        tier = "substring"
    seen: set[str] = set()
    out: list[ResolvedEntity] = []
    for tid, code, name, _norm in rows:
        key = (code or name or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            ResolvedEntity(
                entity_type="transporter",
                canonical_code=code,
                uuid=str(tid) if tid else None,
                match_field="transporter_name",
                match_tier=tier,
                display={"code": code, "name": name},
            )
        )
    return out


def _prefix_probe_promotion(db: Session, token: str) -> list[ResolvedEntity]:
    """Prefix → substring ILIKE on Promotion.description.

    Phrase like "kitchen sink" should hit BOTH descriptions that start with it
    ("Kitchen Sink Promotion") and descriptions that contain it elsewhere
    ("Sorento Kitchen Sink Promo"). Prefix-only would miss the latter.
    """
    if not token or len(token) < 3:
        return []
    prefix = f"{token}%"
    substr = f"%{token}%"
    rows = (
        db.query(Promotion.id, Promotion.description, Promotion.is_active)
        .filter(Promotion.description.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    tier = "prefix"
    if not rows:
        rows = (
            db.query(Promotion.id, Promotion.description, Promotion.is_active)
            .filter(Promotion.description.ilike(substr))
            .limit(PREFIX_LIMIT)
            .all()
        )
        tier = "substring"
    seen: set[str] = set()
    out: list[ResolvedEntity] = []
    # Merge: also include substring hits not already captured by prefix.
    if tier == "prefix" and rows:
        substring_rows = (
            db.query(Promotion.id, Promotion.description, Promotion.is_active)
            .filter(Promotion.description.ilike(substr))
            .filter(~Promotion.description.ilike(prefix))
            .limit(PREFIX_LIMIT)
            .all()
        )
        rows = list(rows) + list(substring_rows)
    # Multi-word union (always runs alongside contiguous ILIKE when the token
    # has 2+ words; results merge + dedupe). Contiguous ILIKE misses
    # descriptions where the user's words are separated by other tokens
    # (e.g. token "sorento kitchen sink" vs description
    # "SORENTO NEW ARRIVAL KITCHEN SINK ..."). Require every word (>=2 chars)
    # to appear anywhere in Promotion.description.
    words = [w for w in token.split() if len(w) >= 2]
    if len(words) >= 2:
        word_query = db.query(Promotion.id, Promotion.description, Promotion.is_active)
        for w in words:
            word_query = word_query.filter(Promotion.description.ilike(f"%{w}%"))
        rows = list(rows) + list(word_query.limit(PREFIX_LIMIT).all())
    for pid, description, is_active in rows:
        key = str(pid)
        if key in seen:
            continue
        seen.add(key)
        is_substring_match = description and not str(description).lower().startswith(token.lower())
        out.append(
            ResolvedEntity(
                entity_type="promotion",
                canonical_code=str(pid),
                uuid=str(pid),
                match_field="description",
                match_tier="substring" if is_substring_match else "prefix",
                display={"description": description, "is_active": bool(is_active)},
            )
        )
    return out[: PREFIX_LIMIT * 2]


def _prefix_probe_form(db: Session, token: str) -> list[ResolvedEntity]:
    """Prefix → substring ILIKE on Form.code / Form.name / Form.purpose, with
    multi-token AND fallback.

    Forms have three searchable text columns. Match code first (highest signal),
    then name, then purpose (longest text, lowest signal). Each column tries
    prefix first, then substring. For multi-word inputs ("renovation form",
    "sponsorship request"), a final AND-tokenized pass requires every token to
    appear somewhere across code/name/purpose — covers descriptive phrasings
    where no single column carries the literal phrase.
    """
    if not token or len(token) < 3:
        return []
    from sqlalchemy import or_, and_
    prefix = f"{token}%"
    substr = f"%{token}%"
    fields = (
        (Form.code, "form_code"),
        (Form.name, "form_name"),
        (Form.purpose, "purpose"),
    )
    seen: set[str] = set()
    out: list[ResolvedEntity] = []

    def _append(fid, code, name, purpose, is_active, form_type, label, tier):
        key = str(fid)
        if key in seen:
            return
        seen.add(key)
        out.append(
            ResolvedEntity(
                entity_type="form",
                canonical_code=code,
                uuid=str(fid) if fid else None,
                match_field=label,
                match_tier=tier,
                display={
                    "form_code": code,
                    "form_name": name,
                    "form_type": form_type,
                    "is_active": bool(is_active),
                },
            )
        )

    for col, label in fields:
        rows = (
            db.query(Form.id, Form.code, Form.name, Form.purpose, Form.is_active, Form.form_type)
            .filter(col.ilike(prefix))
            .limit(PREFIX_LIMIT)
            .all()
        )
        substring_rows = (
            db.query(Form.id, Form.code, Form.name, Form.purpose, Form.is_active, Form.form_type)
            .filter(col.ilike(substr))
            .filter(~col.ilike(prefix))
            .limit(PREFIX_LIMIT)
            .all()
        )
        for fid, code, name, purpose, is_active, form_type in list(rows) + list(substring_rows):
            col_value = {"form_code": code, "form_name": name, "purpose": purpose}[label]
            tier = (
                "substring"
                if col_value and not str(col_value).lower().startswith(token.lower())
                else "prefix"
            )
            _append(fid, code, name, purpose, is_active, form_type, label, tier)

    # Multi-token AND fallback: each token must appear in code OR name OR purpose.
    tokens = [t for t in token.lower().split() if len(t) >= 3]
    if len(tokens) >= 2:
        token_conds = [
            or_(
                Form.code.ilike(f"%{t}%"),
                Form.name.ilike(f"%{t}%"),
                Form.purpose.ilike(f"%{t}%"),
            )
            for t in tokens
        ]
        and_rows = (
            db.query(Form.id, Form.code, Form.name, Form.purpose, Form.is_active, Form.form_type)
            .filter(and_(*token_conds))
            .limit(PREFIX_LIMIT)
            .all()
        )
        for fid, code, name, purpose, is_active, form_type in and_rows:
            _append(fid, code, name, purpose, is_active, form_type, "form_name", "tokenized")

    return out[: PREFIX_LIMIT * 2]


def _prefix_probe_attachment(db: Session, token: str) -> list[ResolvedEntity]:
    """Prefix → substring ILIKE on filename, description, attachment_type.type_name.

    Free-text doc references like "catalogue", "price list 2026", "spec sheet kitchen"
    resolve to attachment UUIDs. Excludes soft-deleted rows.
    """
    if not token or len(token) < 3:
        return []
    prefix = f"{token}%"
    substr = f"%{token}%"
    base = (
        db.query(
            Attachment.id,
            Attachment.original_filename,
            Attachment.description,
            Attachment.mime_type,
            Attachment.full_directory_path,
            AttachmentType.type_name,
        )
        .outerjoin(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(Attachment.is_deleted.is_(False))
    )
    prefix_rows = (
        base.filter(
            or_(
                Attachment.original_filename.ilike(prefix),
                Attachment.description.ilike(prefix),
                AttachmentType.type_name.ilike(prefix),
            )
        )
        .limit(PREFIX_LIMIT)
        .all()
    )
    substring_rows = (
        base.filter(
            or_(
                Attachment.original_filename.ilike(substr),
                Attachment.description.ilike(substr),
                AttachmentType.type_name.ilike(substr),
            )
        )
        .limit(PREFIX_LIMIT)
        .all()
    )
    # Multi-word union (always runs alongside the contiguous prefix/substring
    # queries when the token has 2+ words; results are merged + deduped, not
    # gated on the contiguous result being empty). Contiguous ILIKE misses
    # filenames where the user's words are separated by other tokens
    # (e.g. token "sorento kitchen sink" vs filename
    # "SORENTO NEW ARRIVAL KITCHEN SINK_..."). Split on whitespace and require
    # every word (>=2 chars) to appear in any of the searched columns.
    # AND across words, OR across columns per word.
    words = [w for w in token.split() if len(w) >= 2]
    word_and_rows: list = []
    if len(words) >= 2:
        word_query = base
        for w in words:
            wsub = f"%{w}%"
            word_query = word_query.filter(
                or_(
                    Attachment.original_filename.ilike(wsub),
                    Attachment.description.ilike(wsub),
                    AttachmentType.type_name.ilike(wsub),
                )
            )
        word_and_rows = word_query.limit(PREFIX_LIMIT).all()
    seen: set[str] = set()
    out: list[ResolvedEntity] = []
    for aid, filename, description, mime, dir_path, type_name in list(prefix_rows) + list(substring_rows) + list(word_and_rows):
        key = str(aid)
        if key in seen:
            continue
        seen.add(key)
        name_l = (filename or "").lower()
        desc_l = (description or "").lower()
        type_l = (type_name or "").lower()
        tier = (
            "prefix"
            if name_l.startswith(token.lower()) or desc_l.startswith(token.lower()) or type_l.startswith(token.lower())
            else "substring"
        )
        out.append(
            ResolvedEntity(
                entity_type="attachment",
                canonical_code=filename,
                uuid=key,
                match_field="original_filename",
                match_tier=tier,
                display={
                    "filename": filename,
                    "description": description,
                    "attachment_type": type_name,
                    "mime_type": mime,
                    "directory": dir_path,
                },
            )
        )
    return out[: PREFIX_LIMIT * 2]


def _prefix_probe_attachment_type(db: Session, token: str) -> list[ResolvedEntity]:
    """Prefix → substring → per-word ILIKE on AttachmentType.code / type_name / description.

    Handles partial / fuzzy doc-class words (e.g. token "cataloge" → "catalogue",
    "broch" → "Brochure"). Three-stage matching:
      1. Contiguous prefix ILIKE on code OR type_name.
      2. Contiguous substring ILIKE on code OR type_name OR description.
      3. Per-word substring ILIKE — for every word ≥4 chars in the token,
         match rows whose code / type_name / description contains it. Lets a
         loose user phrase like "technical drawing" resolve to
         "Technical Specifications" (one shared word is enough — caller already
         narrowed to attachment_type so semantic drift risk is bounded).
    Returns up to PREFIX_LIMIT candidates so ambiguous labels surface for LLM
    disambiguation.
    """
    if not token or len(token) < 2:
        return []
    prefix = f"{token}%"
    substr = f"%{token}%"
    base = db.query(
        AttachmentType.id,
        AttachmentType.code,
        AttachmentType.type_name,
        AttachmentType.description,
    )
    prefix_rows = (
        base.filter(
            or_(
                AttachmentType.code.ilike(prefix),
                AttachmentType.type_name.ilike(prefix),
            )
        )
        .limit(PREFIX_LIMIT)
        .all()
    )
    substring_rows = (
        base.filter(
            or_(
                AttachmentType.code.ilike(substr),
                AttachmentType.type_name.ilike(substr),
                AttachmentType.description.ilike(substr),
            )
        )
        .limit(PREFIX_LIMIT)
        .all()
    )
    # Per-word fallback for multi-word phrases (e.g. "technical drawing" with
    # no contiguous match against "Technical Specifications"). OR across words
    # so a single shared word is enough — attachment_type was explicitly hinted
    # by the caller, so loose matching is safer here than for general entities.
    word_rows: list = []
    words = [w for w in token.split() if len(w) >= 4]
    if words:
        word_clauses = []
        for w in words:
            ws = f"%{w}%"
            word_clauses.extend(
                [
                    AttachmentType.code.ilike(ws),
                    AttachmentType.type_name.ilike(ws),
                    AttachmentType.description.ilike(ws),
                ]
            )
        word_rows = base.filter(or_(*word_clauses)).limit(PREFIX_LIMIT).all()

    seen: set[str] = set()
    out: list[ResolvedEntity] = []
    token_lower = token.lower()
    token_word_set = {w.lower() for w in words}
    for tid, code, type_name, description in (
        list(prefix_rows) + list(substring_rows) + list(word_rows)
    ):
        key = str(tid)
        if key in seen:
            continue
        seen.add(key)
        code_l = (code or "").lower()
        type_l = (type_name or "").lower()
        desc_l = (description or "").lower()
        if code_l.startswith(token_lower) or type_l.startswith(token_lower):
            tier = "prefix"
            match_field = "code" if code_l.startswith(token_lower) else "type_name"
        elif token_lower in code_l or token_lower in type_l or token_lower in desc_l:
            tier = "substring"
            match_field = "type_name"
        else:
            tier = "word"
            # Surface which token word actually hit so the agent can explain
            # the loose match.
            hit_word = next(
                (w for w in token_word_set if w in code_l or w in type_l or w in desc_l),
                "",
            )
            match_field = f"word:{hit_word}" if hit_word else "type_name"
        out.append(
            ResolvedEntity(
                entity_type="attachment_type",
                canonical_code=code or type_name,
                uuid=key,
                match_field=match_field,
                match_tier=tier,
                display={
                    "code": code,
                    "type_name": type_name,
                    "description": description,
                },
            )
        )
    return out[:PREFIX_LIMIT]


# Tier-2 probes paired with the entity_type(s) they produce, so callers can opt
# out of probes that can't return anything they accept.
_TIER2_PROBES: tuple[tuple[Callable[[Session, str], list[ResolvedEntity]], frozenset[str]], ...] = (
    (_prefix_probe_product, frozenset({"product"})),
    (_prefix_probe_customer_order, frozenset({"customer_order"})),
    (_prefix_probe_inbound_shipment, frozenset({"inbound_shipment"})),
    (_prefix_probe_customer, frozenset({"customer"})),
    (_prefix_probe_customer_debtor_name, frozenset({"customer"})),
    (_prefix_probe_transporter, frozenset({"transporter"})),
    (_prefix_probe_warehouse, frozenset({"warehouse"})),
    (_prefix_probe_supplier, frozenset({"supplier"})),
    (_prefix_probe_spo, frozenset({"spo_allocation"})),
    (_prefix_probe_grn, frozenset({"grn"})),
    (_prefix_probe_promotion, frozenset({"promotion"})),
    (_prefix_probe_form, frozenset({"form"})),
    (_prefix_probe_attachment, frozenset({"attachment"})),
    (_prefix_probe_attachment_type, frozenset({"attachment_type"})),
)


def _tier2_fuzzy_lookup(
    db: Session,
    token: str,
    allowed_entity_types: Optional[frozenset[str]] = None,
) -> list[ResolvedEntity]:
    """Run Tier-2 prefix probes for a single token and return combined candidates.

    When `allowed_entity_types` is provided, probes whose output type is not in the set
    are skipped entirely — keeps per-tool resolution lean.
    """
    combined: list[ResolvedEntity] = []
    for probe, produces in _TIER2_PROBES:
        if allowed_entity_types is not None and produces.isdisjoint(allowed_entity_types):
            continue
        try:
            combined.extend(probe(db, token))
        except Exception:
            logger.exception("Tier-2 probe %s failed for token=%s", probe.__name__, token)
    return combined


# --------------------------------------------------------------------------- #
# Tier 3 — embedding vector fallback (last resort)
# --------------------------------------------------------------------------- #
# Source types in embedding_chunks that correspond to primary business entities.
# Child tables (order_line, picking_line, ...) are excluded: they'd match on noise.
_EMBEDDING_SOURCE_TYPES: dict[str, str] = {
    "product": "product",
    "order": "customer_order",
    "inbound_shipment": "inbound_shipment",
    "spo_allocation": "spo_allocation",
    "picking_header": "grn",
    "promotion": "promotion",
    # Customer master rows + synthetic `debtor:<code>` chunks seeded from
    # distinct orders.debtor_code with no master row. Lets tokens like
    # "fira ventures" resolve to entity_type=customer via vector similarity
    # against the seeded debtor chunk text.
    "customer": "customer",
    # Transporter master (code + name) so "search DO by transporter X"
    # resolves to entity_type=transporter via vector similarity.
    "transporter": "transporter",
    "attachment": "attachment",
    "form": "form",
}
EMBEDDING_MIN_SIMILARITY = 0.80
EMBEDDING_CONFIDENCE_GAP = 0.05


def _tier3_embedding_lookup(
    db: Session,
    token: str,
    allowed_entity_types: Optional[frozenset[str]] = None,
) -> list[ResolvedEntity]:
    """Vector search over embedding_chunks for primary entities. Returns at most one
    confident match, or an empty list when ambiguous / below threshold."""
    # Local imports: these modules pull in heavy deps; we only want to pay the cost
    # on the last-resort path.
    try:
        from app.services.embedding_worker import _embed_text_chunks
    except Exception:
        logger.exception("Tier-3 embedding worker import failed; skipping")
        return []

    try:
        query_vec = _embed_text_chunks([token])[0]
    except Exception:
        logger.exception("Tier-3 query embedding failed for token=%s", token)
        return []

    if allowed_entity_types is None:
        allowed_types = tuple(_EMBEDDING_SOURCE_TYPES.keys())
    else:
        allowed_types = tuple(
            src for src, ent in _EMBEDDING_SOURCE_TYPES.items() if ent in allowed_entity_types
        )
        if not allowed_types:
            return []
    sql = text(
        """
        SELECT ec.source_type, ec.source_id, ed.source_key,
               1 - (ec.embedding <=> CAST(:vec AS vector)) AS similarity
        FROM embedding_chunks ec
        JOIN embedding_documents ed ON ed.source_type = ec.source_type AND ed.source_id = ec.source_id
        WHERE ec.is_current = TRUE
          AND ec.source_type = ANY(:types)
        ORDER BY ec.embedding <=> CAST(:vec AS vector)
        LIMIT 5
        """
    )
    try:
        rows = db.execute(sql, {"vec": list(query_vec), "types": list(allowed_types)}).all()
    except Exception:
        logger.exception("Tier-3 vector query failed for token=%s", token)
        return []

    if not rows:
        return []

    top = rows[0]
    top_sim = float(top.similarity or 0.0)
    if top_sim < EMBEDDING_MIN_SIMILARITY:
        return []
    second_sim = float(rows[1].similarity) if len(rows) > 1 else 0.0
    if (top_sim - second_sim) < EMBEDDING_CONFIDENCE_GAP:
        return []

    entity_type = _EMBEDDING_SOURCE_TYPES.get(str(top.source_type))
    if not entity_type:
        return []
    canonical_code = top.source_key or str(top.source_id)
    return [
        ResolvedEntity(
            entity_type=entity_type,
            canonical_code=canonical_code,
            uuid=str(top.source_id) if top.source_id else None,
            match_field=f"embedding:{top.source_type}",
            match_tier="embedding",
            similarity=top_sim,
            display={"semantic_match": True},
        )
    ]


# --------------------------------------------------------------------------- #
# Tier 2.5 — pg_trgm typo-tolerant SQL match
# --------------------------------------------------------------------------- #
# Substring ILIKE (Tier-2) misses on typos / missing characters; embedding RAG
# (Tier-3) tolerates them but ranks noisily on short codes. pg_trgm sits in the
# middle: deterministic similarity-based SQL using GIN trigram indexes
# (migration 169 covers products.{product_code,product_name,description},
# orders.{order_number,debtor_name,debtor_code}, customers.{customer_code,
# customer_name}). Catches "sind entrprise" → "SVIND ENTERPRISE", "SRWC8088" →
# "SRTWC8088", etc.
TRGM_THRESHOLD = 0.25
TRGM_LIMIT = 15


def _trgm_lookup(
    db: Session,
    phrase: str,
    allowed_entity_types: frozenset[str],
) -> list[ResolvedEntity]:
    """Run pg_trgm similarity probes across allowed entity types' name+code columns.

    Returns up to `TRGM_LIMIT` hits per entity type sorted by similarity desc,
    filtered by `>= TRGM_THRESHOLD`. Uses indexed columns where available.
    """
    phrase = (phrase or "").strip()
    if not phrase or len(phrase) < 3:
        return []
    out: list[ResolvedEntity] = []

    if "product" in allowed_entity_types:
        try:
            rows = db.execute(
                text(
                    """
                    SELECT id, product_code, product_name,
                           GREATEST(
                               similarity(product_code, :p),
                               similarity(product_name, :p),
                               similarity(COALESCE(description, ''), :p)
                           ) AS sim
                    FROM products
                    WHERE (product_code % :p OR product_name % :p OR description % :p)
                    ORDER BY sim DESC
                    LIMIT :n
                    """
                ),
                {"p": phrase, "n": TRGM_LIMIT},
            ).all()
            for r in rows:
                sim = float(r.sim or 0.0)
                if sim < TRGM_THRESHOLD:
                    continue
                out.append(
                    ResolvedEntity(
                        entity_type="product",
                        canonical_code=r.product_code,
                        uuid=str(r.id) if r.id else None,
                        match_field="product_code",
                        match_tier="trgm",
                        similarity=sim,
                        display={"product_name": r.product_name},
                    )
                )
        except Exception:
            logger.exception("trgm product probe failed for phrase=%s", phrase)

    if "customer" in allowed_entity_types:
        try:
            rows = db.execute(
                text(
                    """
                    SELECT o.debtor_name, o.debtor_code,
                           c.id AS customer_id,
                           GREATEST(
                               similarity(COALESCE(o.debtor_name, ''), :p),
                               similarity(COALESCE(o.debtor_code, ''), :p)
                           ) AS sim
                    FROM orders o
                    LEFT JOIN customers c ON lower(btrim(c.customer_name)) = lower(btrim(o.debtor_name))
                    WHERE o.deleted_at IS NULL
                      AND o.debtor_name IS NOT NULL
                      AND (o.debtor_name % :p OR o.debtor_code % :p)
                    GROUP BY o.debtor_name, o.debtor_code, c.id
                    ORDER BY sim DESC
                    LIMIT :n
                    """
                ),
                {"p": phrase, "n": TRGM_LIMIT},
            ).all()
            for r in rows:
                sim = float(r.sim or 0.0)
                if sim < TRGM_THRESHOLD:
                    continue
                out.append(
                    ResolvedEntity(
                        entity_type="customer",
                        canonical_code=r.debtor_name,
                        uuid=str(r.customer_id) if r.customer_id else None,
                        match_field="debtor_name",
                        match_tier="trgm",
                        similarity=sim,
                        display={"debtor_name": r.debtor_name, "debtor_code": r.debtor_code, "source": "orders"},
                    )
                )
            rows = db.execute(
                text(
                    """
                    SELECT id, customer_code, customer_name,
                           GREATEST(
                               similarity(customer_code, :p),
                               similarity(customer_name, :p)
                           ) AS sim
                    FROM customers
                    WHERE (customer_code % :p OR customer_name % :p)
                    ORDER BY sim DESC
                    LIMIT :n
                    """
                ),
                {"p": phrase, "n": TRGM_LIMIT},
            ).all()
            for r in rows:
                sim = float(r.sim or 0.0)
                if sim < TRGM_THRESHOLD:
                    continue
                out.append(
                    ResolvedEntity(
                        entity_type="customer",
                        canonical_code=r.customer_code,
                        uuid=str(r.id) if r.id else None,
                        match_field="customer_code",
                        match_tier="trgm",
                        similarity=sim,
                        display={"customer_name": r.customer_name},
                    )
                )
        except Exception:
            logger.exception("trgm customer probe failed for phrase=%s", phrase)

    if "customer_order" in allowed_entity_types:
        try:
            rows = db.execute(
                text(
                    """
                    SELECT id, order_number, similarity(order_number, :p) AS sim
                    FROM orders
                    WHERE deleted_at IS NULL AND order_number % :p
                    ORDER BY sim DESC
                    LIMIT :n
                    """
                ),
                {"p": phrase, "n": TRGM_LIMIT},
            ).all()
            for r in rows:
                sim = float(r.sim or 0.0)
                if sim < TRGM_THRESHOLD:
                    continue
                out.append(
                    ResolvedEntity(
                        entity_type="customer_order",
                        canonical_code=r.order_number,
                        uuid=str(r.id) if r.id else None,
                        match_field="order_number",
                        match_tier="trgm",
                        similarity=sim,
                        display={},
                    )
                )
        except Exception:
            logger.exception("trgm order probe failed for phrase=%s", phrase)

    if "promotion" in allowed_entity_types:
        try:
            rows = db.execute(
                text(
                    """
                    SELECT id, description,
                           similarity(COALESCE(description, ''), :p) AS sim
                    FROM promotions
                    WHERE description % :p
                    ORDER BY sim DESC
                    LIMIT :n
                    """
                ),
                {"p": phrase, "n": TRGM_LIMIT},
            ).all()
            for r in rows:
                sim = float(r.sim or 0.0)
                if sim < TRGM_THRESHOLD:
                    continue
                out.append(
                    ResolvedEntity(
                        entity_type="promotion",
                        canonical_code=str(r.id),
                        uuid=str(r.id),
                        match_field="promotion_id",
                        match_tier="trgm",
                        similarity=sim,
                        display={"description": r.description},
                    )
                )
        except Exception:
            logger.exception("trgm promotion probe failed for phrase=%s", phrase)

    if "transporter" in allowed_entity_types:
        try:
            rows = db.execute(
                text(
                    """
                    SELECT id, code, name, normalized_name,
                           GREATEST(
                               similarity(COALESCE(code, ''), :p),
                               similarity(COALESCE(name, ''), :p),
                               similarity(COALESCE(normalized_name, ''), :p)
                           ) AS sim
                    FROM transporters
                    WHERE (code % :p OR name % :p OR normalized_name % :p)
                    ORDER BY sim DESC
                    LIMIT :n
                    """
                ),
                {"p": phrase, "n": TRGM_LIMIT},
            ).all()
            for r in rows:
                sim = float(r.sim or 0.0)
                if sim < TRGM_THRESHOLD:
                    continue
                out.append(
                    ResolvedEntity(
                        entity_type="transporter",
                        canonical_code=r.code,
                        uuid=str(r.id) if r.id else None,
                        match_field="transporter_code",
                        match_tier="trgm",
                        similarity=sim,
                        display={"code": r.code, "name": r.name},
                    )
                )
        except Exception:
            logger.exception("trgm transporter probe failed for phrase=%s", phrase)

    out.sort(key=lambda e: e.similarity or 0.0, reverse=True)
    return out[: TRGM_LIMIT * 2]


# --------------------------------------------------------------------------- #
# AND-mode (cross-token intersection) probes
# --------------------------------------------------------------------------- #
# When the caller asks for "cabana filter tap", a per-token OR resolver yields
# two ambiguous lists that the agent must intersect manually — and the PREFIX
# limit can evict legitimate cross-matches before that intersection runs.
#
# AND-mode runs a single SQL per entity type with all tokens ANDed across the
# entity's concatenated searchable columns. Result: only rows whose combined
# text contains EVERY token. Skips code-only entity types (SPO, GRN, inbound
# shipment) where multi-token AND has no semantic meaning.

# Cap per AND probe BEFORE downstream post-filters (access_levels, promotion-
# domain product expansion). 200 is the same ceiling the API's `limit` param
# uses — keeps the SQL bounded while ensuring the post-filters see enough rows
# to find legitimate matches. Without this slack, e.g. 22 Sorento+End-User
# promotions get clipped to ~3 because the first 20 raw Sorento rows happen to
# have dealer-only access_levels.
AND_MODE_LIMIT = 200


def _concat_ws(*cols):
    """Sqlalchemy concat_ws helper used by AND-mode probes."""
    return func.concat_ws(" ", *cols)


def _word_variants(word: str) -> list[str]:
    """Return `word` plus a singular fallback when it looks like an alphabetic
    plural. Lets a token like 'ventures' still match 'VENTURE ENTERPRISE' so
    minor plural typos ('Fira ventures' vs DB 'FIRA VENTURE') don't drop the
    match. Codes containing digits are NEVER stripped — `TT440s` must keep its
    trailing s.
    """
    if not word:
        return []
    out = [word]
    low = word.lower()
    if (
        len(word) >= 4
        and low.endswith("s")
        and not low.endswith("ss")
        and word.isalpha()
    ):
        out.append(word[:-1])
    return out


def _and_token_match_counts(blob, tokens: list[str]):
    """Return one match-count expression per token over `blob`.

    Each expression is `sum(0/1 indicators)` across the token's words, where
    each word's indicator is `blob ILIKE %word%` OR a singular-fallback
    variant. The probe uses these expressions to find the GLOBAL MAX match
    count for each token across the table, then keeps only rows hitting that
    max — so filler words ("promotion", "version") never poison results: any
    row that hits the most semantic words wins, regardless of how many words
    the token had.
    """
    counts = []
    for tok in tokens or []:
        if not tok:
            continue
        words = [w for w in tok.split() if w]
        if not words:
            continue
        indicators = []
        for word in words:
            variants = _word_variants(word)
            if not variants:
                continue
            ilike_any = or_(*[blob.ilike(f"%{v}%") for v in variants])
            indicators.append(case((ilike_any, 1), else_=0))
        if not indicators:
            continue
        counts.append(reduce(add, indicators))
    return counts


def _and_max_tier_filter(base_query, counts):
    """Given a base query already filtered by non-token predicates and a list
    of per-token match-count expressions, return the additional filter that
    keeps only rows reaching the GLOBAL MAX match count for EVERY token.

    Returns `None` when any token has no possible hits (max == 0) — caller
    should short-circuit and return no rows.
    """
    if not counts:
        return None
    maxes = base_query.with_entities(*[func.max(c) for c in counts]).one()
    if any((m is None or m == 0) for m in maxes):
        return None
    return and_(*[c == m for c, m in zip(counts, maxes)])


def _and_probe_product(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    blob = _concat_ws(Product.product_code, Product.product_name, Product.description)
    counts = _and_token_match_counts(blob, tokens)
    base = db.query(Product.id, Product.product_code, Product.product_name, Product.is_active)
    tier = _and_max_tier_filter(base, counts)
    if tier is None:
        return []
    rows = base.filter(tier).limit(AND_MODE_LIMIT).all()
    return [
        ResolvedEntity(
            entity_type="product",
            canonical_code=code,
            uuid=str(pid) if pid else None,
            match_field="product_code",
            match_tier="and",
            display={"product_name": name, "is_active": bool(is_active)},
        )
        for pid, code, name, is_active in rows
    ]


def _and_probe_promotion(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    counts = _and_token_match_counts(Promotion.description, tokens)
    base = db.query(Promotion.id, Promotion.description, Promotion.is_active)
    tier = _and_max_tier_filter(base, counts)
    if tier is None:
        return []
    rows = base.filter(tier).limit(AND_MODE_LIMIT).all()
    return [
        ResolvedEntity(
            entity_type="promotion",
            canonical_code=str(pid),
            uuid=str(pid),
            match_field="description",
            match_tier="and",
            display={"description": description, "is_active": bool(is_active)},
        )
        for pid, description, is_active in rows
    ]


def _and_probe_attachment(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    blob = _concat_ws(Attachment.original_filename, Attachment.description, AttachmentType.type_name)
    counts = _and_token_match_counts(blob, tokens)
    base = (
        db.query(
            Attachment.id,
            Attachment.original_filename,
            Attachment.description,
            Attachment.mime_type,
            Attachment.full_directory_path,
            AttachmentType.type_name,
        )
        .outerjoin(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
        .filter(Attachment.is_deleted.is_(False))
    )
    tier = _and_max_tier_filter(base, counts)
    if tier is None:
        return []
    rows = base.filter(tier).limit(AND_MODE_LIMIT).all()
    return [
        ResolvedEntity(
            entity_type="attachment",
            canonical_code=filename,
            uuid=str(aid) if aid else None,
            match_field="original_filename",
            match_tier="and",
            display={
                "filename": filename,
                "description": description,
                "attachment_type": type_name,
                "mime_type": mime,
                "directory": dir_path,
            },
        )
        for aid, filename, description, mime, dir_path, type_name in rows
    ]


def _and_probe_customer(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    # Two sources: customers master (preferred — has UUID) and orders.debtor_name
    # (legacy fallback). Run both; orders.debtor_name JOINs Customer for UUID.
    out: list[ResolvedEntity] = []
    blob_c = _concat_ws(Customer.customer_code, Customer.customer_name, Customer.phone_number, Customer.email)
    counts_c = _and_token_match_counts(blob_c, tokens)
    base_c = db.query(Customer.id, Customer.customer_code, Customer.customer_name, Customer.phone_number, Customer.email, Customer.is_active)
    tier_c = _and_max_tier_filter(base_c, counts_c)
    if tier_c is not None:
        rows = base_c.filter(tier_c).limit(AND_MODE_LIMIT).all()
        for cid, code, name, phone, email, is_active in rows:
            out.append(
                ResolvedEntity(
                    entity_type="customer",
                    canonical_code=code,
                    uuid=str(cid) if cid else None,
                    match_field="customer_code",
                    match_tier="and",
                    display={"customer_name": name, "phone_number": phone, "email": email, "is_active": bool(is_active) if is_active is not None else True},
                )
            )
    # Legacy debtor_name path — only if no customers master hit covers the same name.
    seen_names = {(m.display or {}).get("customer_name", "").lower() for m in out}
    blob_o = _concat_ws(Order.debtor_name, Order.debtor_code)
    counts_o = _and_token_match_counts(blob_o, tokens)
    base_o = (
        db.query(Order.debtor_name, Order.debtor_code, Customer.id)
        .outerjoin(Customer, func.lower(func.btrim(Customer.customer_name)) == func.lower(func.btrim(Order.debtor_name)))
        .filter(Order.deleted_at.is_(None), Order.debtor_name.isnot(None))
    )
    tier_o = _and_max_tier_filter(base_o, counts_o)
    if tier_o is not None:
        rows = base_o.filter(tier_o).distinct().limit(AND_MODE_LIMIT).all()
        for debtor_name, debtor_code, customer_id in rows:
            if (debtor_name or "").lower() in seen_names:
                continue
            out.append(
                ResolvedEntity(
                    entity_type="customer",
                    canonical_code=debtor_name,
                    uuid=str(customer_id) if customer_id else None,
                    match_field="debtor_name",
                    match_tier="and",
                    display={"debtor_name": debtor_name, "debtor_code": debtor_code, "source": "orders"},
                )
            )
    return out


def _and_probe_form(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    blob = _concat_ws(Form.code, Form.name, Form.purpose)
    counts = _and_token_match_counts(blob, tokens)
    base = db.query(Form.id, Form.code, Form.name, Form.purpose, Form.is_active, Form.form_type)
    tier = _and_max_tier_filter(base, counts)
    if tier is None:
        return []
    rows = base.filter(tier).limit(AND_MODE_LIMIT).all()
    return [
        ResolvedEntity(
            entity_type="form",
            canonical_code=code,
            uuid=str(fid) if fid else None,
            match_field="form_name",
            match_tier="and",
            display={"form_code": code, "form_name": name, "form_type": form_type, "is_active": bool(is_active)},
        )
        for fid, code, name, purpose, is_active, form_type in rows
    ]


def _and_probe_transporter(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    blob = _concat_ws(Transporter.code, Transporter.name, Transporter.normalized_name)
    counts = _and_token_match_counts(blob, tokens)
    base = db.query(Transporter.id, Transporter.code, Transporter.name)
    tier = _and_max_tier_filter(base, counts)
    if tier is None:
        return []
    rows = base.filter(tier).limit(AND_MODE_LIMIT).all()
    return [
        ResolvedEntity(
            entity_type="transporter",
            canonical_code=code,
            uuid=str(tid) if tid else None,
            match_field="transporter_name",
            match_tier="and",
            display={"code": code, "name": name},
        )
        for tid, code, name in rows
    ]


def _and_probe_warehouse(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    blob = _concat_ws(Warehouse.warehouse_code, Warehouse.warehouse_name, Warehouse.location)
    counts = _and_token_match_counts(blob, tokens)
    base = db.query(Warehouse.id, Warehouse.warehouse_code, Warehouse.warehouse_name, Warehouse.location, Warehouse.is_active)
    tier = _and_max_tier_filter(base, counts)
    if tier is None:
        return []
    rows = base.filter(tier).limit(AND_MODE_LIMIT).all()
    return [
        ResolvedEntity(
            entity_type="warehouse",
            canonical_code=code,
            uuid=str(wid) if wid else None,
            match_field="warehouse_code",
            match_tier="and",
            display={"warehouse_name": name, "location": location, "is_active": bool(is_active) if is_active is not None else True},
        )
        for wid, code, name, location, is_active in rows
    ]


def _and_probe_supplier(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    blob = _concat_ws(Supplier.supplier_code, Supplier.supplier_name, Supplier.contact_name)
    counts = _and_token_match_counts(blob, tokens)
    base = db.query(Supplier.id, Supplier.supplier_code, Supplier.supplier_name, Supplier.is_active)
    tier = _and_max_tier_filter(base, counts)
    if tier is None:
        return []
    rows = base.filter(tier).limit(AND_MODE_LIMIT).all()
    return [
        ResolvedEntity(
            entity_type="supplier",
            canonical_code=code,
            uuid=str(sid) if sid else None,
            match_field="supplier_code",
            match_tier="and",
            display={"supplier_name": name, "is_active": bool(is_active) if is_active is not None else True},
        )
        for sid, code, name, is_active in rows
    ]


def _and_probe_customer_order(db: Session, tokens: list[str]) -> list[ResolvedEntity]:
    # Code-only entity. Match exclusively on `order_number` so generic abbreviations
    # like "DO" (delivery order) don't accidentally hit any debtor_name containing
    # the substring (e.g. customer "MOCHA SDN BHD (DOCUMENT)" matched "DO"). Anyone
    # filtering orders by customer name should resolve the customer separately and
    # pass the customer entity, not bundle the name into a customer_order token.
    conds = [Order.order_number.ilike(f"%{t}%") for t in tokens if t]
    if not conds:
        return []
    rows = (
        db.query(Order.id, Order.order_number, Order.debtor_name, Order.actual_delivery_date, Order.estimated_delivery_date)
        .filter(Order.deleted_at.is_(None), *conds)
        .limit(AND_MODE_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="customer_order",
            canonical_code=row.order_number,
            uuid=str(row.id) if row.id else None,
            match_field="order_number",
            match_tier="and",
            display={
                "customer_name": row.debtor_name,
                "actual_delivery_date": _iso(row.actual_delivery_date),
                "estimated_delivery_date": _iso(row.estimated_delivery_date),
            },
        )
        for row in rows
    ]


_AND_PROBES: tuple[tuple[Callable[[Session, list[str]], list[ResolvedEntity]], frozenset[str]], ...] = (
    (_and_probe_product, frozenset({"product"})),
    (_and_probe_promotion, frozenset({"promotion"})),
    (_and_probe_attachment, frozenset({"attachment"})),
    (_and_probe_customer, frozenset({"customer"})),
    (_and_probe_form, frozenset({"form"})),
    (_and_probe_transporter, frozenset({"transporter"})),
    (_and_probe_warehouse, frozenset({"warehouse"})),
    (_and_probe_supplier, frozenset({"supplier"})),
    (_and_probe_customer_order, frozenset({"customer_order"})),
)


@dataclass
class IntersectionResolutionResult:
    """Cross-token AND result. Returned when match_mode=and."""

    tokens: list[str]
    intersection: list[ResolvedEntity]
    elapsed_ms: float
    match_mode: str = "and"

    @property
    def empty(self) -> bool:
        return not self.intersection

    def as_dict(self) -> dict[str, Any]:
        # Group hits by entity_type for stable agent-facing shape.
        by_type: dict[str, list[dict[str, Any]]] = {}
        for m in self.intersection:
            by_type.setdefault(m.entity_type, []).append({
                "entity_type": m.entity_type,
                "canonical_code": m.canonical_code,
                "uuid": m.uuid,
                "match_field": m.match_field,
                "match_tier": m.match_tier,
                "display": m.display,
            })
        return {
            "match_mode": self.match_mode,
            "tokens": self.tokens,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "intersection": [
                {
                    "entity_type": m.entity_type,
                    "canonical_code": m.canonical_code,
                    "uuid": m.uuid,
                    "match_field": m.match_field,
                    "match_tier": m.match_tier,
                    "display": m.display,
                }
                for m in self.intersection
            ],
            "by_entity_type": by_type,
            "empty": self.empty,
            "unresolved_tokens": list(self.tokens) if self.empty else [],
        }


def resolve_references_intersection(
    db: Session,
    tokens: list[str],
    *,
    allowed_entity_types: Optional[Iterable[str]] = None,
    domain_hint: Optional[str] = None,
) -> IntersectionResolutionResult:
    """AND-mode resolver. Returns rows matching EVERY token in the concatenated
    searchable columns of each entity type. Skips code-only types.

    `allowed_entity_types` (when set) is always a global set filter — every
    surviving probe sees every token. Positional pairing (token[i] vs
    allowed_entity_types[i]) is no longer auto-triggered on equal-length lists;
    callers that need 1:1 pairing must issue one resolve call per pair.
    """
    raw_tokens = list(tokens or [])
    pair_map = _build_token_type_map(raw_tokens, allowed_entity_types)

    t0 = time.perf_counter()
    clean_tokens = [t.strip() for t in raw_tokens if t and t.strip()]
    if not clean_tokens:
        return IntersectionResolutionResult(tokens=[], intersection=[], elapsed_ms=0.0)

    if pair_map is not None:
        allowed: Optional[frozenset[str]] = frozenset(pair_map.values())
    elif allowed_entity_types is not None:
        # Apply one-to-many expansion (brand / category → product + promotion).
        allowed = _expand_entity_types(allowed_entity_types, domain_hint=domain_hint)
    else:
        allowed = None

    hits: list[ResolvedEntity] = []
    for probe, produces in _AND_PROBES:
        if allowed is not None and produces.isdisjoint(allowed):
            continue
        if pair_map is not None:
            probe_tokens = [t for t in clean_tokens if pair_map.get(t) in produces]
            if not probe_tokens:
                continue
        else:
            probe_tokens = clean_tokens
        try:
            rows = probe(db, probe_tokens)
        except Exception:
            logger.exception("AND probe %s failed", probe.__name__)
            continue
        hits.extend(rows)

    elapsed = (time.perf_counter() - t0) * 1000.0
    return IntersectionResolutionResult(
        tokens=clean_tokens,
        intersection=hits,
        elapsed_ms=elapsed,
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
_TIER1_PROBES: tuple[tuple[Callable[[Session, list[str]], dict[str, list[ResolvedEntity]]], frozenset[str]], ...] = (
    (_probe_product, frozenset({"product"})),
    (_probe_customer_order, frozenset({"customer_order"})),
    (_probe_inbound_shipment, frozenset({"inbound_shipment"})),
    (_probe_spo, frozenset({"spo_allocation"})),
    (_probe_grn, frozenset({"grn"})),
    (_probe_warehouse, frozenset({"warehouse"})),
    (_probe_supplier, frozenset({"supplier"})),
    (_probe_promotion, frozenset({"promotion"})),
    (_probe_transporter, frozenset({"transporter"})),
    (_probe_customer, frozenset({"customer"})),
    (_probe_customer_debtor_name, frozenset({"customer"})),
    (_probe_attachment, frozenset({"attachment"})),
    (_probe_attachment_type, frozenset({"attachment_type"})),
)


def resolve_references(
    db: Session,
    query_or_tokens: str | list[str],
    *,
    max_candidates: int = 8,
    enable_prefix_fallback: bool = True,
    enable_embedding_fallback: bool = True,
    allowed_entity_types: Optional[Iterable[str]] = None,
    cross_type_expand: bool = False,
    domain_hint: Optional[str] = None,
) -> ResolutionResult:
    """Main entry point.

    Runs three tiers in order, stopping per-token as soon as a tier yields a match:

      Tier 1 — exact case-insensitive lookup on all code fields.
      Tier 2 — prefix / substring ILIKE on the same code fields (handles partial codes).
      Tier 3 — embedding vector search over primary entities (semantic last resort).

    Tier 2/3 results with ambiguity (multiple candidates, or low confidence gap) are
    flagged `ambiguous=True` so the LLM asks the user to pick rather than guessing.

    When `allowed_entity_types` is set, probes whose output type is outside the set are
    skipped, and Tier-3 vector search filters to allowed source_types. Per-list-tool
    callers pass the types they can filter on so resolution doesn't return entities the
    caller has nowhere to send.
    """
    t0 = time.perf_counter()
    raw_query: Optional[str] = None
    if isinstance(query_or_tokens, list):
        tokens = [t for t in (s.strip() for s in query_or_tokens) if t][:max_candidates]
    else:
        raw_query = query_or_tokens or ""
        tokens = extract_candidate_tokens(raw_query, max_candidates=max_candidates)

    # Positional pairing: when caller passed parallel lists of tokens + entity types
    # of equal length, each token resolves ONLY against its paired type. Otherwise
    # `allowed` is treated as the legacy global type-set filter.
    pair_map = _build_token_type_map(tokens, allowed_entity_types)
    if pair_map is not None:
        allowed: Optional[frozenset[str]] = frozenset(pair_map.values())
    elif allowed_entity_types is not None:
        # Apply one-to-many expansion (brand / category → product + promotion).
        allowed = _expand_entity_types(allowed_entity_types, domain_hint=domain_hint)
    else:
        allowed = None

    def _types_for(tok: str) -> Optional[frozenset[str]]:
        if pair_map is not None:
            paired = pair_map.get(tok)
            return frozenset({paired}) if paired else frozenset()
        return allowed

    # ----- Tier 1: exact -----
    per_token: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    ambiguous_tokens: set[str] = set()
    if tokens:
        for probe, produces in _TIER1_PROBES:
            if allowed is not None and produces.isdisjoint(allowed):
                continue
            if pair_map is not None:
                probe_tokens = [t for t in tokens if pair_map.get(t) in produces]
                if not probe_tokens:
                    continue
            else:
                probe_tokens = tokens
            try:
                hits = probe(db, probe_tokens)
            except Exception:
                logger.exception("Tier-1 probe %s failed", probe.__name__)
                continue
            for tok, matches in hits.items():
                per_token[tok].extend(matches)

    # ----- Tier 2: prefix / substring fallback (only for tokens still empty) -----
    if enable_prefix_fallback:
        for tok in tokens:
            tok_allowed = _types_for(tok)
            if tok_allowed is not None and not tok_allowed:
                continue
            # Product variant expansion: Tier 1 exact returns only the row whose
            # code equals the token (e.g. SRTKS6145). Variants like SRTKS6145-NEW
            # / -UF / -OLD share a base stem and never match exact. When Tier 1
            # already produced a product hit, additionally probe prefix on the
            # product table so siblings surface alongside the exact match. Other
            # entity types keep strict single-hit semantics — variant siblings
            # are a product-domain concept (SKU suffixes); customers / orders /
            # promotions don't have the same family pattern.
            existing_product_hit = any(
                m.entity_type == "product" for m in per_token[tok]
            )
            if existing_product_hit and (tok_allowed is None or "product" in tok_allowed):
                seen_uuids = {m.uuid for m in per_token[tok] if m.uuid}
                for variant in _prefix_probe_product(db, tok):
                    if variant.uuid and variant.uuid in seen_uuids:
                        continue
                    per_token[tok].append(variant)
                    if variant.uuid:
                        seen_uuids.add(variant.uuid)
                # Multi-row product result must flag ambiguous so the LLM asks
                # the user to pick / treats them as a set rather than picking
                # the first match silently.
                if len([m for m in per_token[tok] if m.entity_type == "product"]) > 1:
                    ambiguous_tokens.add(tok)
            if per_token[tok]:
                continue
            candidates = _tier2_fuzzy_lookup(db, tok, allowed_entity_types=tok_allowed)
            if not candidates:
                continue
            if len(candidates) == 1:
                per_token[tok] = candidates
                continue
            # 2+ matches — let the LLM ask the user to pick, cap surface size.
            # Per-type balanced cap: when several entity types matched (e.g.
            # `kitchen sink` hits 20 products + 6 promotions), a flat top-N
            # would crowd out the smaller types entirely. Allocate the budget
            # across active types so every type that matched gets seen.
            per_type: dict[str, list[ResolvedEntity]] = {}
            for c in candidates:
                per_type.setdefault(c.entity_type, []).append(c)
            n_types = len(per_type)
            per_type_cap = max(1, PREFIX_LIMIT // max(1, n_types))
            balanced: list[ResolvedEntity] = []
            for items in per_type.values():
                balanced.extend(items[:per_type_cap])
            per_token[tok] = balanced[:PREFIX_LIMIT]
            ambiguous_tokens.add(tok)

    # Snapshot which tokens already had matches BEFORE cross-type expansion —
    # used below to flag tokens that grew into multi-type candidate sets so the
    # LLM disambiguates instead of picking the first match.
    pre_expand_type_count: dict[str, int] = {
        tok: len({m.entity_type for m in per_token[tok]}) for tok in tokens
    }

    # ----- Cross-type expansion (fallback discovery mode) -----
    # In `cross_type_expand` mode we keep probing OTHER entity types for tokens
    # that already got a tier-1 / tier-2 hit. The fallback path
    # (`fallback_to_all_types=True`) uses this so a token like "Sorento" which
    # exact-matches a `transporter` code can ALSO surface as a `promotion` /
    # `brand` / `customer` candidate. Without this, the per-token early exit
    # after tier-1 swallows every other type and `fallback_types_found` only
    # reports the first probe that fired.
    if cross_type_expand and tokens:
        for tok in tokens:
            existing_types = {m.entity_type for m in per_token[tok]}
            seen_uuids = {m.uuid for m in per_token[tok] if m.uuid}
            # Tier-1 (exact) across remaining types.
            for probe, produces in _TIER1_PROBES:
                if produces.issubset(existing_types):
                    continue
                if allowed is not None and produces.isdisjoint(allowed):
                    # Respect explicit whitelist when caller still passed one;
                    # fallback path clears `allowed` so this is a no-op there.
                    continue
                try:
                    hits = probe(db, [tok]).get(tok, [])
                except Exception:
                    logger.exception("Cross-type tier-1 probe %s failed", probe.__name__)
                    continue
                for m in hits:
                    if m.uuid and m.uuid in seen_uuids:
                        continue
                    per_token[tok].append(m)
                    if m.uuid:
                        seen_uuids.add(m.uuid)
                    existing_types.add(m.entity_type)
            # Tier-2 (prefix / substring) across remaining types.
            if enable_prefix_fallback:
                for probe, produces in _TIER2_PROBES:
                    if produces.issubset(existing_types):
                        continue
                    if allowed is not None and produces.isdisjoint(allowed):
                        continue
                    try:
                        hits = probe(db, tok)
                    except Exception:
                        logger.exception("Cross-type tier-2 probe %s failed", probe.__name__)
                        continue
                    for m in hits[:PREFIX_LIMIT]:
                        if m.uuid and m.uuid in seen_uuids:
                            continue
                        per_token[tok].append(m)
                        if m.uuid:
                            seen_uuids.add(m.uuid)
                        existing_types.add(m.entity_type)

    # Mark cross-type-expanded tokens ambiguous when expansion grew them from a
    # single-type confident match into a multi-type candidate union. Without
    # this, `TokenResolution.confident_match` would silently pick the first
    # match (e.g. transporter) even though the agent should reroute via the
    # newly-surfaced types (promotion, brand, ...).
    if cross_type_expand:
        for tok in tokens:
            current_types = {m.entity_type for m in per_token[tok]}
            if len(current_types) > 1 and len(current_types) > pre_expand_type_count.get(tok, 0):
                ambiguous_tokens.add(tok)

    # ----- Tier 3: embedding fallback (only for tokens still empty AND not ambiguous) -----
    if enable_embedding_fallback:
        for tok in tokens:
            if per_token[tok] or tok in ambiguous_tokens:
                continue
            tok_allowed = _types_for(tok)
            if tok_allowed is not None and not tok_allowed:
                continue
            hits = _tier3_embedding_lookup(db, tok, allowed_entity_types=tok_allowed)
            if hits:
                per_token[tok] = hits

    # ----- Free-text debtor + transporter scan (when raw query string was given) -----
    # Lets "Find DO for jayson Feb 2026" resolve "jayson" → entity_type=customer, and
    # "transporter Svind gt delivery" resolve "gt delivery" → entity_type=transporter,
    # without explicit markers. Free-word candidates are bulk-queried so the cost
    # stays bounded regardless of how many surface from the phrase.
    # Positional pairing already pins every token to a single type, so the free-word
    # scan would only produce noise — skip it in that mode.
    freeword_resolutions: list[TokenResolution] = []
    if raw_query and pair_map is None and (allowed is None or {"customer", "transporter"} & allowed):
        existing_lower = {t.lower() for t in tokens}
        freeword_candidates = [
            w
            for w in extract_freeword_candidates(raw_query, max_candidates=max_candidates)
            if w.lower() not in existing_lower
        ]
        if freeword_candidates:
            customer_hits: dict[str, list[ResolvedEntity]] = {}
            transporter_hits: dict[str, list[ResolvedEntity]] = {}
            if allowed is None or "customer" in allowed:
                try:
                    customer_hits = _probe_customer_debtor_name(db, freeword_candidates)
                except Exception:
                    logger.exception("Free-word debtor probe failed")
                    customer_hits = {t: [] for t in freeword_candidates}
            if allowed is None or "transporter" in allowed:
                try:
                    transporter_hits = _probe_transporter_freeword(db, freeword_candidates)
                except Exception:
                    logger.exception("Free-word transporter probe failed")
                    transporter_hits = {t: [] for t in freeword_candidates}
            for tok in freeword_candidates:
                matches: list[ResolvedEntity] = []
                matches.extend(customer_hits.get(tok) or [])
                matches.extend(transporter_hits.get(tok) or [])
                if matches:
                    freeword_resolutions.append(TokenResolution(token=tok, matches=matches))

    resolutions = [
        TokenResolution(token=t, matches=per_token[t], ambiguous=(t in ambiguous_tokens))
        for t in tokens
    ]
    resolutions.extend(freeword_resolutions)
    final_tokens = list(tokens) + [r.token for r in freeword_resolutions]
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return ResolutionResult(tokens=final_tokens, resolutions=resolutions, elapsed_ms=elapsed_ms)


# --------------------------------------------------------------------------- #
# Single-bag `entities` API for list tools
# --------------------------------------------------------------------------- #
@dataclass
class EntityFilterBuckets:
    """Per-type canonical values + structured echo for `entities: list[str]` callers.

    A list tool collapses customer/product/transporter/order filters into a single
    `entities` param. The resolver decides each input's entity_type; this helper
    packages the result into ready-to-use SQL inputs plus an authoritative echo so
    the agent can surface "what did you actually match" back to the user.
    """

    product_codes: list[str] = field(default_factory=list)
    debtor_names: list[str] = field(default_factory=list)
    customer_codes: list[str] = field(default_factory=list)
    customer_names: list[str] = field(default_factory=list)
    transporter_codes: list[str] = field(default_factory=list)
    transporter_names: list[str] = field(default_factory=list)
    order_numbers: list[str] = field(default_factory=list)
    shipment_numbers: list[str] = field(default_factory=list)
    picking_numbers: list[str] = field(default_factory=list)
    spo_numbers: list[str] = field(default_factory=list)
    supplier_codes: list[str] = field(default_factory=list)
    promotion_ids: list[str] = field(default_factory=list)
    attachment_filenames: list[str] = field(default_factory=list)
    form_codes: list[str] = field(default_factory=list)
    resolved: list[dict[str, Any]] = field(default_factory=list)
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def has_resolved_filter(self) -> bool:
        return bool(
            self.product_codes
            or self.debtor_names
            or self.customer_codes
            or self.customer_names
            or self.transporter_codes
            or self.transporter_names
            or self.order_numbers
            or self.shipment_numbers
            or self.picking_numbers
            or self.spo_numbers
            or self.supplier_codes
            or self.promotion_ids
            or self.attachment_filenames
            or self.form_codes
        )

    def as_echo(self) -> dict[str, Any]:
        """Shape for `_resolved_entities` in tool responses."""
        return {
            "resolved": self.resolved,
            "ambiguous": self.ambiguous,
            "unresolved": self.unresolved,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


def _dedupe_preserve_order(values: Iterable[Optional[str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if not v:
            continue
        s = str(v)
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


RAG_MIN_SIMILARITY = 0.20
RAG_TOP_K = 15
RAG_AMBIGUOUS_GAP = 0.04


def _rag_resolve_phrase(
    db: Session,
    phrase: str,
    allowed_entity_types: frozenset[str],
    *,
    top_k: int = RAG_TOP_K,
    min_similarity: float = RAG_MIN_SIMILARITY,
) -> list[ResolvedEntity]:
    """One embed call + top-k vector search against embedding_chunks.

    Returns the top-k hits filtered by `allowed_entity_types`, ranked by cosine
    similarity desc, dropping anything below `min_similarity`. No tokenization,
    no fallback tiers — the entire surface area is "embed the user's phrase,
    ask pgvector who looks closest, trust the score."

    `embedding_documents.source_key` is populated per source_type by the embedding
    backfill service (`product` → product_code, `transporter` → code,
    `customer_order` → order_number, `customer` → customer_code or
    `debtor:<code>`), so the returned `canonical_code` is the value the caller
    should feed directly into SQL filter buckets.
    """
    try:
        from app.services.embedding_worker import _embed_text_chunks
    except Exception:
        logger.exception("RAG embedding worker import failed; phrase=%s", phrase)
        return []

    allowed_source_types = [
        src for src, ent in _EMBEDDING_SOURCE_TYPES.items() if ent in allowed_entity_types
    ]
    if not allowed_source_types:
        return []

    try:
        query_vec = _embed_text_chunks([phrase])[0]
    except Exception:
        logger.exception("RAG embed failed for phrase=%s", phrase)
        return []

    sql = text(
        """
        SELECT ec.source_type, ec.source_id, ed.source_key,
               1 - (ec.embedding <=> CAST(:vec AS vector)) AS similarity
        FROM embedding_chunks ec
        JOIN embedding_documents ed
          ON ed.source_type = ec.source_type AND ed.source_id = ec.source_id
        WHERE ec.is_current = TRUE
          AND ec.source_type = ANY(:types)
        ORDER BY ec.embedding <=> CAST(:vec AS vector)
        LIMIT :k
        """
    )
    try:
        rows = db.execute(
            sql,
            {"vec": list(query_vec), "types": allowed_source_types, "k": top_k},
        ).all()
    except Exception:
        logger.exception("RAG vector query failed for phrase=%s", phrase)
        try:
            db.rollback()
        except Exception:
            logger.exception("rollback after RAG query failure also failed")
        return []

    out: list[ResolvedEntity] = []
    seen_keys: set[tuple[str, str]] = set()
    for r in rows:
        sim = float(r.similarity or 0.0)
        if sim < min_similarity:
            continue
        entity_type = _EMBEDDING_SOURCE_TYPES.get(str(r.source_type))
        if not entity_type:
            continue
        raw_key = r.source_key or str(r.source_id)
        # Customer debtor-synthetic keys arrive as "debtor:<code>" — strip the
        # prefix so the canonical_code matches `Order.debtor_code` directly.
        match_field = "embedding"
        canonical = raw_key
        if entity_type == "customer" and isinstance(raw_key, str) and raw_key.startswith("debtor:"):
            canonical = raw_key.split(":", 1)[1]
            match_field = "debtor_code"
        elif entity_type == "customer":
            match_field = "customer_code"
        elif entity_type == "product":
            match_field = "product_code"
        elif entity_type == "transporter":
            match_field = "transporter_code"
        elif entity_type == "customer_order":
            match_field = "order_number"
        elif entity_type == "inbound_shipment":
            match_field = "shipment_number"
        elif entity_type == "spo_allocation":
            match_field = "spo_number"
        elif entity_type == "grn":
            match_field = "picking_number"
        elif entity_type == "promotion":
            match_field = "promotion_id"
        elif entity_type == "attachment":
            match_field = "filename"
        elif entity_type == "form":
            match_field = "form_code"
        dedupe_key = (entity_type, canonical.lower() if canonical else str(r.source_id))
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        out.append(
            ResolvedEntity(
                entity_type=entity_type,
                canonical_code=canonical,
                match_field=match_field,
                match_tier="embedding",
                similarity=sim,
                display={"source_type": str(r.source_type)},
            )
        )

    # Substring re-rank: embedding similarity on short product/customer codes is
    # noisy — the top-K above similarity threshold is often a mix of relevant
    # and completely unrelated codes that happen to share token shape. When ANY
    # candidate's canonical_code (case-insensitive) contains the input phrase
    # as a substring, keep only those candidates — substring containment is a
    # stronger human-meaningful signal than embedding rank, and it cuts the
    # noise from 15 candidates down to the ones the user could plausibly mean.
    phrase_lower = (phrase or "").strip().lower()
    if phrase_lower and len(phrase_lower) >= 3:
        substring_hits = [
            h for h in out
            if h.canonical_code and phrase_lower in str(h.canonical_code).lower()
        ]
        if substring_hits:
            return substring_hits
    return out


def resolve_entities_to_filters(
    db: Session,
    entities: Optional[list[str]],
    *,
    allowed_entity_types: Iterable[str],
    max_candidates: int = 8,
) -> EntityFilterBuckets:
    """Resolve a free-text `entities` bag via pure-RAG top-k vector search.

    Strategy: for each entity string, one embedding call + one pgvector top-K
    lookup against `embedding_chunks` restricted to source_types matching
    `allowed_entity_types`. The top hit is treated as the resolved entity; if
    the top-2 hits are within `RAG_AMBIGUOUS_GAP` of each other the input is
    flagged ambiguous and ALL near-tie candidates surface in the echo so the
    agent can ask the user to pick one. Anything below `RAG_MIN_SIMILARITY`
    falls into `unresolved` so the agent can tell the user no match was found.

    No token extraction, no n-gram sweep, no Tier-1 / Tier-2 ILIKE — the
    embedding pipeline already indexed the relevant business vocabulary, so we
    let pgvector do the work in one round-trip per entity.
    """
    buckets = EntityFilterBuckets()
    if not entities:
        return buckets

    allowed_set = frozenset(allowed_entity_types)
    inputs = [s.strip() for s in entities if s and s.strip()]
    if not inputs:
        return buckets

    t_start = time.perf_counter()
    aggregated: list[TokenResolution] = []
    for phrase in inputs:
        # Hybrid retrieval. The agent's input is unpredictable — sometimes a full
        # product_code, sometimes a partial prefix the user typed, sometimes a
        # loose customer phrase. Sequence:
        #   1. Tier-2 prefix / substring ILIKE across every allowed entity type's
        #      name + code columns. Deterministic. Matches what the in-app list
        #      search does — "SRTWC8088" returns every product_code containing it.
        #   2. Only if Tier-2 finds nothing → RAG embedding top-K fallback.
        #      Catches semantic phrasings ("fira ventures" → "FIRA VENTURE
        #      ENTERPRISE SDN BHD") that pure substring would miss.
        substring_hits = _tier2_fuzzy_lookup(
            db, phrase, allowed_entity_types=allowed_set
        )
        if substring_hits:
            ambiguous = len(substring_hits) > 1
            aggregated.append(
                TokenResolution(
                    token=phrase,
                    matches=substring_hits,
                    ambiguous=ambiguous,
                )
            )
            continue

        # Tier 2.5: pg_trgm fuzzy SQL — catches typos / missing chars before
        # falling through to the heavier embedding lookup.
        trgm_hits = _trgm_lookup(db, phrase, allowed_set)
        if trgm_hits:
            aggregated.append(
                TokenResolution(
                    token=phrase,
                    matches=trgm_hits,
                    ambiguous=len(trgm_hits) > 1,
                )
            )
            continue

        hits = _rag_resolve_phrase(
            db,
            phrase,
            allowed_set,
            top_k=max(RAG_TOP_K, 1),
            min_similarity=RAG_MIN_SIMILARITY,
        )
        if not hits:
            aggregated.append(TokenResolution(token=phrase, matches=[]))
            continue
        top = hits[0]
        same_type_candidates = [h for h in hits if h.entity_type == top.entity_type]
        if len(same_type_candidates) > 1:
            aggregated.append(
                TokenResolution(
                    token=phrase,
                    matches=same_type_candidates,
                    ambiguous=True,
                )
            )
        else:
            aggregated.append(TokenResolution(token=phrase, matches=[top]))
    result = ResolutionResult(
        tokens=[tr.token for tr in aggregated],
        resolutions=aggregated,
        elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
    )
    buckets.elapsed_ms = result.elapsed_ms

    for tr in result.resolutions:
        if tr.ambiguous:
            # Surface the ambiguity in the echo so the agent can tell the user
            # we matched several near-equal candidates, but ALSO let every
            # candidate flow into the filter buckets below. Returning empty on
            # ambiguity is worse than over-matching — caller sees stock for all
            # near matches and the user can disambiguate verbally.
            buckets.ambiguous.append(
                {
                    "input": tr.token,
                    "candidates": [
                        {
                            "type": m.entity_type,
                            "canonical_code": m.canonical_code,
                            "match_field": m.match_field,
                            "match_tier": m.match_tier,
                            "display": m.display,
                        }
                        for m in tr.matches
                    ],
                }
            )
        if not tr.matches:
            buckets.unresolved.append(tr.token)
            continue
        for m in tr.matches:
            if m.entity_type not in allowed_set:
                # Resolver may emit related types we don't filter on; skip silently.
                continue
            if m.entity_type == "product":
                buckets.product_codes.append(m.canonical_code)
            elif m.entity_type == "customer_order":
                buckets.order_numbers.append(m.canonical_code)
            elif m.entity_type == "customer":
                if m.match_field == "debtor_name":
                    buckets.debtor_names.append(m.canonical_code)
                elif m.match_field in ("customer_code", "debtor_code"):
                    buckets.customer_codes.append(m.canonical_code)
                else:
                    buckets.customer_names.append(m.canonical_code)
            elif m.entity_type == "transporter":
                if m.match_field == "transporter_code":
                    buckets.transporter_codes.append(m.canonical_code)
                else:
                    buckets.transporter_names.append(
                        m.display.get("name") or m.canonical_code
                    )
                    if m.canonical_code:
                        buckets.transporter_codes.append(m.canonical_code)
            elif m.entity_type == "inbound_shipment":
                buckets.shipment_numbers.append(m.canonical_code)
            elif m.entity_type == "grn":
                buckets.picking_numbers.append(m.canonical_code)
            elif m.entity_type == "spo_allocation":
                buckets.spo_numbers.append(m.canonical_code)
            elif m.entity_type == "supplier":
                buckets.supplier_codes.append(m.canonical_code)
            elif m.entity_type == "promotion":
                buckets.promotion_ids.append(m.canonical_code)
            elif m.entity_type == "attachment":
                buckets.attachment_filenames.append(m.canonical_code)
            elif m.entity_type == "form":
                buckets.form_codes.append(m.canonical_code)
            buckets.resolved.append(
                {
                    "input": tr.token,
                    "type": m.entity_type,
                    "canonical_code": m.canonical_code,
                    "match_field": m.match_field,
                    "match_tier": m.match_tier,
                    "similarity": m.similarity,
                    "display": m.display,
                }
            )

    buckets.product_codes = _dedupe_preserve_order(buckets.product_codes)
    buckets.debtor_names = _dedupe_preserve_order(buckets.debtor_names)
    buckets.customer_codes = _dedupe_preserve_order(buckets.customer_codes)
    buckets.customer_names = _dedupe_preserve_order(buckets.customer_names)
    buckets.transporter_codes = _dedupe_preserve_order(buckets.transporter_codes)
    buckets.transporter_names = _dedupe_preserve_order(buckets.transporter_names)
    buckets.order_numbers = _dedupe_preserve_order(buckets.order_numbers)
    buckets.shipment_numbers = _dedupe_preserve_order(buckets.shipment_numbers)
    buckets.picking_numbers = _dedupe_preserve_order(buckets.picking_numbers)
    buckets.spo_numbers = _dedupe_preserve_order(buckets.spo_numbers)
    buckets.supplier_codes = _dedupe_preserve_order(buckets.supplier_codes)
    buckets.promotion_ids = _dedupe_preserve_order(buckets.promotion_ids)
    buckets.attachment_filenames = _dedupe_preserve_order(buckets.attachment_filenames)
    buckets.form_codes = _dedupe_preserve_order(buckets.form_codes)
    return buckets
