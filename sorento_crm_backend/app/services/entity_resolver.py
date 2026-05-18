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

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

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


logger = logging.getLogger(__name__)


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

    entity_type: str  # product | customer_order | customer | inbound_shipment | spo_allocation | grn | warehouse | supplier | promotion
    canonical_code: str  # the business code the user should pass to tools (e.g. order_number)
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
def _probe_product(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    """Exact match on product_code (case-insensitive)."""
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(Product.product_code, Product.product_name, Product.is_active)
        .filter(func.lower(Product.product_code).in_(lowered))
        .all()
    )
    code_to_token = {t.lower(): t for t in tokens}
    for code, name, is_active in rows:
        token = code_to_token.get(str(code).lower())
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="product",
                canonical_code=code,
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
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(
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
        .filter(func.lower(Order.order_number).in_(lowered), Order.deleted_at.is_(None))
        .all()
    )
    code_to_token = {t.lower(): t for t in tokens}
    for row in rows:
        token = code_to_token.get(str(row.order_number).lower())
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="customer_order",
                canonical_code=row.order_number,
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
    # Exact by customer_code
    rows = (
        db.query(
            Customer.customer_code,
            Customer.customer_name,
            Customer.phone_number,
            Customer.email,
            Customer.is_active,
        )
        .filter(func.lower(Customer.customer_code).in_(lowered))
        .all()
    )
    code_to_token = {t.lower(): t for t in tokens}
    for code, name, phone, email, is_active in rows:
        token = code_to_token.get(str(code).lower())
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="customer",
                canonical_code=code,
                match_field="customer_code",
                display={
                    "customer_name": name,
                    "phone_number": phone,
                    "email": email,
                    "is_active": bool(is_active) if is_active is not None else True,
                },
            )
        )
    # Fuzzy on name / phone (only if still unresolved to avoid noise)
    unresolved = [t for t in tokens if not result[t]]
    for token in unresolved:
        term = f"%{token}%"
        rows = (
            db.query(
                Customer.customer_code,
                Customer.customer_name,
                Customer.phone_number,
                Customer.email,
            )
            .filter(
                or_(
                    Customer.customer_name.ilike(term),
                    Customer.phone_number.ilike(term),
                )
            )
            .limit(3)
            .all()
        )
        for code, name, phone, email in rows:
            result[token].append(
                ResolvedEntity(
                    entity_type="customer",
                    canonical_code=code or name,
                    match_field="customer_name" if (name and token.lower() in (name or "").lower()) else "phone_number",
                    display={"customer_name": name, "phone_number": phone, "email": email},
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
        db.query(Order.debtor_name, Order.debtor_code)
        .filter(
            Order.deleted_at.is_(None),
            Order.debtor_name.isnot(None),
            func.lower(Order.debtor_name).in_(lowered),
        )
        .distinct()
        .all()
    )
    name_to_token = {t.lower(): t for t in tokens if t}
    for debtor_name, debtor_code in rows:
        token = name_to_token.get(str(debtor_name).lower())
        if not token:
            continue
        if any(m.canonical_code == debtor_name for m in result[token]):
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="customer",
                canonical_code=debtor_name,
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
        rows = (
            db.query(Order.debtor_name, Order.debtor_code)
            .filter(
                Order.deleted_at.is_(None),
                Order.debtor_name.isnot(None),
                or_(*like_clauses),
            )
            .distinct()
            .limit(5)
            .all()
        )
        for debtor_name, debtor_code in rows:
            if any(m.canonical_code == debtor_name for m in result[token]):
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="customer",
                    canonical_code=debtor_name,
                    match_field="debtor_name",
                    display={"debtor_name": debtor_name, "debtor_code": debtor_code, "source": "orders"},
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
            db.query(Transporter.code, Transporter.name, Transporter.normalized_name)
            .filter(
                or_(
                    Transporter.name.ilike(term),
                    Transporter.normalized_name.ilike(term),
                    Transporter.code.ilike(term),
                )
            )
            .limit(5)
            .all()
        )
        for code, name, _norm in rows:
            if any(m.canonical_code == code for m in result[token]):
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="transporter",
                    canonical_code=code,
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
    rows = (
        db.query(Transporter.code, Transporter.name, Transporter.normalized_name)
        .filter(
            or_(
                func.lower(Transporter.code).in_(lowered),
                func.lower(Transporter.name).in_(lowered),
                func.lower(Transporter.normalized_name).in_(lowered),
            )
        )
        .all()
    )
    for code, name, norm in rows:
        for token in tokens:
            tl = token.lower()
            if tl not in {(code or "").lower(), (name or "").lower(), (norm or "").lower()}:
                continue
            if any(m.canonical_code == code for m in result[token]):
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="transporter",
                    canonical_code=code,
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
            db.query(Transporter.code, Transporter.name, Transporter.normalized_name)
            .filter(
                or_(
                    Transporter.name.ilike(term),
                    Transporter.normalized_name.ilike(term),
                )
            )
            .limit(5)
            .all()
        )
        for code, name, _norm in rows:
            if any(m.canonical_code == code for m in result[token]):
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="transporter",
                    canonical_code=code,
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
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(
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
                func.lower(InboundShipment.shipment_number).in_(lowered),
                func.lower(InboundShipment.shipping_container_number).in_(lowered),
                func.lower(InboundShipment.bill_of_lading_number).in_(lowered),
                func.lower(InboundShipment.invoice_number).in_(lowered),
            )
        )
        .all()
    )
    for row in rows:
        for token in tokens:
            tl = token.lower()
            match_field = None
            if row.shipment_number and row.shipment_number.lower() == tl:
                match_field = "shipment_number"
            elif row.shipping_container_number and row.shipping_container_number.lower() == tl:
                match_field = "shipping_container_number"
            elif row.bill_of_lading_number and row.bill_of_lading_number.lower() == tl:
                match_field = "bill_of_lading_number"
            elif row.invoice_number and row.invoice_number.lower() == tl:
                match_field = "invoice_number"
            if not match_field:
                continue
            result[token].append(
                ResolvedEntity(
                    entity_type="inbound_shipment",
                    canonical_code=row.shipment_number,
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
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(SPOAllocation.spo_number)
        .filter(func.lower(SPOAllocation.spo_number).in_(lowered))
        .distinct()
        .all()
    )
    code_to_token = {t.lower(): t for t in tokens}
    for (spo_number,) in rows:
        token = code_to_token.get(str(spo_number or "").lower())
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="spo_allocation",
                canonical_code=spo_number,
                match_field="spo_number",
                display={"spo_number": spo_number},
            )
        )
    return result


def _probe_grn(db: Session, tokens: list[str]) -> dict[str, list[ResolvedEntity]]:
    result: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    if not tokens:
        return result
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(
            PickingHeader.picking_number,
            PickingHeader.picking_date,
            PickingHeader.picking_status,
            PickingHeader.picking_type,
        )
        .filter(
            func.lower(PickingHeader.picking_number).in_(lowered),
            PickingHeader.picking_type == "goods_received",
        )
        .all()
    )
    code_to_token = {t.lower(): t for t in tokens}
    for row in rows:
        token = code_to_token.get(str(row.picking_number).lower())
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="grn",
                canonical_code=row.picking_number,
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
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(Warehouse.warehouse_code, Warehouse.warehouse_name, Warehouse.location, Warehouse.is_active)
        .filter(func.lower(Warehouse.warehouse_code).in_(lowered))
        .all()
    )
    code_to_token = {t.lower(): t for t in tokens}
    for code, name, location, is_active in rows:
        token = code_to_token.get(str(code).lower())
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="warehouse",
                canonical_code=code,
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
    lowered = [t.lower() for t in tokens]
    rows = (
        db.query(
            Supplier.supplier_code,
            Supplier.supplier_name,
            Supplier.contact_name,
            Supplier.email,
            Supplier.phone_number,
            Supplier.is_active,
        )
        .filter(func.lower(Supplier.supplier_code).in_(lowered))
        .all()
    )
    code_to_token = {t.lower(): t for t in tokens}
    for code, name, contact, email, phone, is_active in rows:
        token = code_to_token.get(str(code).lower())
        if not token:
            continue
        result[token].append(
            ResolvedEntity(
                entity_type="supplier",
                canonical_code=code,
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


# --------------------------------------------------------------------------- #
# Tier 2 — prefix / substring probes (run only for tokens Tier 1 missed)
# --------------------------------------------------------------------------- #
# A Tier-2 probe takes a SINGLE token and returns a list of candidate entities.
# - Preference order: prefix match first, then substring.
# - Any token with >1 candidate is surfaced to the LLM as "ambiguous" so it asks
#   the user to pick, rather than silently guessing or failing with "no record".
PREFIX_LIMIT = 8


def _prefix_probe_product(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    substr = f"%{token}%"
    rows = (
        db.query(Product.product_code, Product.product_name, Product.is_active)
        .filter(Product.product_code.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    tier = "prefix"
    if not rows:
        rows = (
            db.query(Product.product_code, Product.product_name, Product.is_active)
            .filter(Product.product_code.ilike(substr))
            .limit(PREFIX_LIMIT)
            .all()
        )
        tier = "substring"
    return [
        ResolvedEntity(
            entity_type="product",
            canonical_code=code,
            match_field="product_code",
            match_tier=tier,
            display={"product_name": name, "is_active": bool(is_active)},
        )
        for code, name, is_active in rows
    ]


def _prefix_probe_customer_order(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(
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
        db.query(Customer.customer_code, Customer.customer_name, Customer.phone_number)
        .filter(Customer.customer_code.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="customer",
            canonical_code=code,
            match_field="customer_code",
            match_tier="prefix",
            display={"customer_name": name, "phone_number": phone},
        )
        for code, name, phone in rows
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
        db.query(Order.debtor_name, Order.debtor_code)
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
            db.query(Order.debtor_name, Order.debtor_code)
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
    seen: set[str] = set()
    out: list[ResolvedEntity] = []
    for debtor_name, debtor_code in rows:
        key = (debtor_name or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            ResolvedEntity(
                entity_type="customer",
                canonical_code=debtor_name,
                match_field="debtor_name",
                match_tier=tier,
                display={"debtor_name": debtor_name, "debtor_code": debtor_code, "source": "orders"},
            )
        )
    return out


def _prefix_probe_warehouse(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(Warehouse.warehouse_code, Warehouse.warehouse_name, Warehouse.is_active)
        .filter(Warehouse.warehouse_code.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="warehouse",
            canonical_code=code,
            match_field="warehouse_code",
            match_tier="prefix",
            display={"warehouse_name": name, "is_active": bool(is_active)},
        )
        for code, name, is_active in rows
    ]


def _prefix_probe_supplier(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(Supplier.supplier_code, Supplier.supplier_name, Supplier.is_active)
        .filter(Supplier.supplier_code.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="supplier",
            canonical_code=code,
            match_field="supplier_code",
            match_tier="prefix",
            display={"supplier_name": name, "is_active": bool(is_active)},
        )
        for code, name, is_active in rows
    ]


def _prefix_probe_spo(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(SPOAllocation.spo_number)
        .filter(SPOAllocation.spo_number.ilike(prefix))
        .distinct()
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="spo_allocation",
            canonical_code=spo,
            match_field="spo_number",
            match_tier="prefix",
            display={"spo_number": spo},
        )
        for (spo,) in rows
    ]


def _prefix_probe_grn(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(
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
        db.query(Transporter.code, Transporter.name, Transporter.normalized_name)
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
            db.query(Transporter.code, Transporter.name, Transporter.normalized_name)
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
    for code, name, _norm in rows:
        key = (code or name or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            ResolvedEntity(
                entity_type="transporter",
                canonical_code=code,
                match_field="transporter_name",
                match_tier=tier,
                display={"code": code, "name": name},
            )
        )
    return out


def _prefix_probe_promotion(db: Session, token: str) -> list[ResolvedEntity]:
    prefix = f"{token}%"
    rows = (
        db.query(Promotion.id, Promotion.description, Promotion.is_active)
        .filter(Promotion.description.ilike(prefix))
        .limit(PREFIX_LIMIT)
        .all()
    )
    return [
        ResolvedEntity(
            entity_type="promotion",
            canonical_code=str(pid),
            match_field="description",
            match_tier="prefix",
            display={"description": description, "is_active": bool(is_active)},
        )
        for pid, description, is_active in rows
    ]


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
            match_field=f"embedding:{top.source_type}",
            match_tier="embedding",
            similarity=top_sim,
            display={"semantic_match": True},
        )
    ]


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
)


def resolve_references(
    db: Session,
    query_or_tokens: str | list[str],
    *,
    max_candidates: int = 8,
    enable_prefix_fallback: bool = True,
    enable_embedding_fallback: bool = True,
    allowed_entity_types: Optional[Iterable[str]] = None,
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

    allowed: Optional[frozenset[str]] = (
        frozenset(allowed_entity_types) if allowed_entity_types is not None else None
    )

    # ----- Tier 1: exact -----
    per_token: dict[str, list[ResolvedEntity]] = {t: [] for t in tokens}
    ambiguous_tokens: set[str] = set()
    if tokens:
        for probe, produces in _TIER1_PROBES:
            if allowed is not None and produces.isdisjoint(allowed):
                continue
            try:
                hits = probe(db, tokens)
            except Exception:
                logger.exception("Tier-1 probe %s failed", probe.__name__)
                continue
            for tok, matches in hits.items():
                per_token[tok].extend(matches)

    # ----- Tier 2: prefix / substring fallback (only for tokens still empty) -----
    if enable_prefix_fallback:
        for tok in tokens:
            if per_token[tok]:
                continue
            candidates = _tier2_fuzzy_lookup(db, tok, allowed_entity_types=allowed)
            if not candidates:
                continue
            if len(candidates) == 1:
                per_token[tok] = candidates
                continue
            # 2+ matches — let the LLM ask the user to pick, cap surface size.
            per_token[tok] = candidates[:PREFIX_LIMIT]
            ambiguous_tokens.add(tok)

    # ----- Tier 3: embedding fallback (only for tokens still empty AND not ambiguous) -----
    if enable_embedding_fallback:
        for tok in tokens:
            if per_token[tok] or tok in ambiguous_tokens:
                continue
            hits = _tier3_embedding_lookup(db, tok, allowed_entity_types=allowed)
            if hits:
                per_token[tok] = hits

    # ----- Free-text debtor + transporter scan (when raw query string was given) -----
    # Lets "Find DO for jayson Feb 2026" resolve "jayson" → entity_type=customer, and
    # "transporter Svind gt delivery" resolve "gt delivery" → entity_type=transporter,
    # without explicit markers. Free-word candidates are bulk-queried so the cost
    # stays bounded regardless of how many surface from the phrase.
    freeword_resolutions: list[TokenResolution] = []
    if raw_query and (allowed is None or {"customer", "transporter"} & allowed):
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


RAG_MIN_SIMILARITY = 0.30
RAG_TOP_K = 5
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
        runners = hits[1:]
        same_type_runners = [
            h
            for h in runners
            if h.entity_type == top.entity_type
            and (top.similarity or 0) - (h.similarity or 0) < RAG_AMBIGUOUS_GAP
        ]
        if same_type_runners:
            aggregated.append(
                TokenResolution(
                    token=phrase,
                    matches=[top, *same_type_runners],
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
            continue
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
    return buckets
