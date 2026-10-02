"""The low stock report's filters, settled before any run (LOWSTOCK-FILTER-ASK).

`documentation/plans/chatbot/lowstock-filter-ask-behaviour-card.md`, "Ruled behaviour".
The low stock report's config for the shared `required_fields` helper, and the reading of
its own words:

* product CATEGORY is the one required field: a category word ("water tap", "SRT-FT"),
  narrowed by a brand word ("Sorento") through `product_categories.brand_hint`; a brand
  alone is every category of that brand; "all" is the whole book;
* SUPPLIER is optional (never asked): a supplier name in the message, matched against the
  supplier master list, a numbered pick when it names several;
* GROUPING is never asked: "by supplier", "by category", "by supplier and category".

What it settles goes to the route as `categories` (codes), `suppliers` (names) and
`split`, applied to the WORKBOOK of the usual whole-book run (crew ruling Q1 (a)).
"""
from __future__ import annotations

import re
from typing import Any

from app.services.chatbot import required_fields as rf
from app.services.chatbot.lanes.business import services as business_services

ASK_NAME = "low_stock_report"
SUPPLIER_GRANT = "purchase_orders.supplier"

QUESTION = 'Which product category? Reply with a category (e.g. water tap) or "all".'
CANCELLED = "Low stock report cancelled."
GIVE_UP = "I still can't place '{word}'. Ask for the low stock report again with a category or \"all\"."

SPLIT_LABELS = {
    "none": "none",
    "supplier": "supplier",
    "category": "category",
    "supplier_category": "supplier x category",
}

#: Words a low stock ask is made of, never a supplier name.
_ASK_WORDS = frozenset(
    """low stock stok list report reorder reordering laporan rendah needs need what is are
    below level levels for the a an of by group grouped grouping and x please pls show me give
    send all item items product products category categories supplier suppliers in at
    on from with""".split()
)


def _category_rows(db: Any, ids: list[str] | None = None) -> list[tuple[str, str, str]]:
    from app.models.product import ProductCategory

    q = db.query(ProductCategory.id, ProductCategory.category_code, ProductCategory.brand_hint)
    if ids is not None:
        q = q.filter(ProductCategory.id.in_(ids))
    return [(str(i), code or "", brand or "") for i, code, brand in q.all()]


def _brand_matches(brand: str, hint: str, code: str) -> bool:
    from app.services.product_class_signal import BRAND_PREFIXES

    b = brand.strip().casefold()
    if not b:
        return True
    if hint.casefold() == b:
        return True
    prefix = code.split("-", 1)[0]
    return prefix.casefold() == b or BRAND_PREFIXES.get(prefix, "").casefold() == b


def _codes(rows: list[tuple[str, str, str]], brand: str) -> list[str]:
    return sorted({code for _i, code, hint in rows if code and _brand_matches(brand, hint, code)})


def _ok(codes: list[str]) -> rf.Resolved:
    return rf.Resolved("ok", value=codes, label=", ".join(codes))


def resolve_category(db: Any, word: str, extras: dict[str, Any]) -> rf.Resolved:
    """A category word -> category CODES, narrowed by the carried brand. An exact code or
    name, else a whole-word run of a name, else the catalogue's class vocabulary ("water
    tap" -> class Tap -> every Tap category). Several codes for one exact word, or several
    classes, are a numbered pick."""
    if db is None:
        return rf.Resolved("unknown")
    brand = str(extras.get("brand") or "")
    matched = business_services.resolve_category_token(db, word)
    if matched:
        codes = _codes(_category_rows(db, [r[0] for r in matched]), brand)
        if not codes:
            return rf.Resolved("unknown")
        if len(codes) > 1:
            return rf.Resolved("ambiguous", options=tuple(([c], c) for c in codes))
        return _ok(codes)
    ids, labels = business_services.resolve_category_class(db, word)
    if ids:
        codes = _codes(_category_rows(db, ids), brand)
        return _ok(codes) if codes else rf.Resolved("unknown")
    if len(labels) > 1:
        options = []
        for label in labels:
            label_ids, _ = business_services.resolve_category_class(db, label)
            codes = _codes(_category_rows(db, label_ids), brand)
            if codes:
                options.append((codes, label))
        if len(options) == 1:
            return _ok(options[0][0])
        if options:
            return rf.Resolved("ambiguous", options=tuple(options))
    return rf.Resolved("unknown")


def brand_categories(db: Any, brand: str) -> rf.Resolved | None:
    """A brand alone: every category of that brand. None when the word is no brand."""
    if db is None or not brand.strip():
        return None
    codes = _codes(_category_rows(db), brand)
    return _ok(codes) if codes else None


def resolve_supplier(db: Any, word: str, _extras: dict[str, Any]) -> rf.Resolved:
    """A supplier word against the supplier master list (crew ruling Q5 (a)): an exact
    name or code wins alone; otherwise every active supplier whose name holds the word as
    a whole-word run, several -> a numbered pick."""
    from app.models.procurement import Supplier

    if db is None:
        return rf.Resolved("unknown")
    want = " ".join(word.split()).casefold()
    if not want:
        return rf.Resolved("unknown")
    rows = [
        (name or "", code or "")
        for name, code in db.query(Supplier.supplier_name, Supplier.supplier_code)
        .filter(Supplier.is_active.is_(True))
        .order_by(Supplier.supplier_name)
        .all()
    ]
    exact = [name for name, code in rows if want in (name.casefold(), code.casefold())]
    found = exact or [name for name, _code in rows if _word_run(want, name.casefold())]
    found = list(dict.fromkeys(found))
    if not found:
        return rf.Resolved("unknown")
    if len(found) == 1:
        return rf.Resolved("ok", value=found, label=found[0])
    return rf.Resolved("ambiguous", options=tuple(([n], n) for n in found))


def _word_run(needle: str, haystack: str) -> bool:
    want, have = needle.split(), haystack.split()
    return bool(want) and any(have[i : i + len(want)] == want for i in range(len(have) - len(want) + 1))


CATEGORY = rf.FieldSpec(name="category", noun="category", question=QUESTION, resolve=resolve_category)
SUPPLIER = rf.FieldSpec(
    name="supplier", noun="supplier", question="Which supplier?", resolve=resolve_supplier,
    allow_all=False, required=False,
)

#: The config (owner ruling Q2): category required, supplier taken when given. Making the
#: supplier required is `required=True` on `SUPPLIER` above, nothing else.
LOW_STOCK_ASK = rf.register(rf.AskType(
    name=ASK_NAME,
    fields=(CATEGORY, SUPPLIER),
    reroute={
        "message_type": "business_query",
        "intent_hint": "low_stock_report",
        "domain_hint": "inventory",
        "order_status": None,
        "document": None,
        "status": None,
    },
    cancelled=CANCELLED,
    give_up=GIVE_UP,
))


# --------------------------------------------------------------------------- #
# Reading the first message
# --------------------------------------------------------------------------- #

_SPLIT_PATTERNS = (
    (re.compile(r"\bby\s+(supplier|suppliers)\s*(and|x|&|/|,)\s*(category|categories)\b"), "supplier_category"),
    (re.compile(r"\bby\s+(category|categories)\s*(and|x|&|/|,)\s*(supplier|suppliers)\b"), "supplier_category"),
    (re.compile(r"\bby\s+(supplier|suppliers)\b"), "supplier"),
    (re.compile(r"\bby\s+(category|categories)\b"), "category"),
)
_ALL_CATEGORIES = re.compile(r"\ball\s+(product\s+)?(category|categories)\b")


def split_from(text: str) -> str:
    low = (text or "").casefold()
    for pattern, split in _SPLIT_PATTERNS:
        if pattern.search(low):
            return split
    return "none"


def says_all_categories(text: str) -> bool:
    return bool(_ALL_CATEGORIES.search((text or "").casefold()))


def supplier_word(text: str, used: list[str]) -> str | None:
    """What is left of the message once the ask's own words, the grouping and every word
    the parser already placed (category, brand, location, product) are taken out: the
    supplier, when there is one. Matched against the master list only by the caller."""
    low = " " + (text or "").casefold() + " "
    for pattern, _split in _SPLIT_PATTERNS:
        low = pattern.sub(" ", low)
    for word in sorted((u for u in used if u), key=len, reverse=True):
        low = re.sub(r"(?<!\w)" + re.escape(word.casefold()) + r"(?!\w)", " ", low)
    left = [w for w in re.findall(r"[\w&.'-]+", low) if w not in _ASK_WORDS]
    return " ".join(left) or None


def take_words(verdict: dict[str, Any], text: str) -> dict[str, Any]:
    """Engine seam, a FRESH low stock ask: the category and brand words come off the
    entity list (the shared resolver would read them as promotions and end the turn in a
    miss before the lane, the owner's own report) onto `low_stock_words`, with the message
    text the lane reads the supplier and grouping words from."""
    if verdict.get("intent_hint") != ASK_NAME or verdict.get("required_ask"):
        return verdict
    entities = [e for e in (verdict.get("entities") or []) if isinstance(e, dict)]
    kept, words = [], {"category": [], "brand": [], "used": []}
    for e in entities:
        hint = str(e.get("hint") or "").strip().lower()
        raw = " ".join(str(e.get("raw") or "").split())
        if e.get("current_message") is False:
            kept.append(e)
            continue
        if hint in ("category", "brand") and raw:
            words[hint].append(raw)
            words["used"].append(raw)
            continue
        if raw:
            words["used"].append(raw)
        kept.append(e)
    return {**verdict, "entities": kept, "low_stock_words": words, "low_stock_text": text}


# --------------------------------------------------------------------------- #
# The lane's call
# --------------------------------------------------------------------------- #


def settle(db: Any, parse_output: dict[str, Any], *, include_supplier: bool) -> rf.Outcome:
    """Every field settled, or the one line to send instead of running."""
    slot = parse_output.get("required_ask")
    slot = slot if isinstance(slot, dict) and slot.get("ask") == ASK_NAME else None
    if slot is not None:
        extras = dict(slot.get("extras") or {})
        return rf.collect(
            db, LOW_STOCK_ASK, slot=slot, reply=str(parse_output.get("required_ask_reply") or ""),
            given=extras.get("given") or {},
        )

    words = parse_output.get("low_stock_words") if isinstance(parse_output.get("low_stock_words"), dict) else {}
    text = str(parse_output.get("low_stock_text") or "")
    brand = " ".join(words.get("brand") or [])
    category_word = " ".join(words.get("category") or [])
    split = split_from(text)
    given: dict[str, Any] = {}
    if says_all_categories(text):
        given["category"] = rf.ALL
    elif category_word:
        given["category"] = category_word
    elif brand:
        settled = brand_categories(db, brand)
        if settled is not None:
            given["category"] = settled
    if include_supplier:
        word = supplier_word(text, list(words.get("used") or []))
        if word:
            given["supplier"] = word
    else:
        split = {"supplier": "none", "supplier_category": "category"}.get(split, split)
    extras = {
        "brand": brand,
        "split": split,
        "given": {k: v for k, v in given.items() if isinstance(v, str)},
        "include_supplier": include_supplier,
        "date_filter_start": parse_output.get("date_filter_start"),
        "date_filter_end": parse_output.get("date_filter_end"),
    }
    return rf.collect(db, LOW_STOCK_ASK, given=given, extras=extras)


def route_filters(outcome: rf.Outcome) -> dict[str, Any]:
    """`categories` / `suppliers` / `split` for the route, and the line said above the
    counts."""
    category = (outcome.values.get("category") or {}).get("value")
    supplier = (outcome.values.get("supplier") or {}).get("value")
    include_supplier = bool(outcome.extras.get("include_supplier", True))
    split = str(outcome.extras.get("split") or "none")
    out: dict[str, Any] = {"split": split}
    if isinstance(category, list) and category:
        out["categories"] = category
    if include_supplier and isinstance(supplier, list) and supplier:
        out["suppliers"] = supplier
    parts = [f"Category: {', '.join(out['categories']) if out.get('categories') else 'all'}"]
    if include_supplier:
        parts.append(f"Supplier: {', '.join(out['suppliers']) if out.get('suppliers') else 'all'}")
    parts.append(f"Grouping: {SPLIT_LABELS.get(split, split)}")
    out["line"] = " | ".join(parts)
    return out
