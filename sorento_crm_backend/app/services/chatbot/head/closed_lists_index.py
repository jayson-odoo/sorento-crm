"""CLOSED-LISTS-INDEX-MODE (owner, 20 Oct 2026): the closed lists as an index, not a block.

`system_settings.chatbot_closed_lists_mode` says how a CLOSED LISTS parser version sees the
closed lists. `block` (the default, today) renders every full list into the system prompt.
`index` renders each full list variable as ONE fixed pointer line (`SYSTEM_BLANKS`), so the
system prompt stays byte-identical across turns and its cache holds, and the per-turn CLOSED
LISTS block (the candidate lines, `head/candidates.py`) also carries, in the lines the rules
already read (`index_lines`):

- the file types, certificate kinds and schemes the message's own words name (their code,
  name, own words or a lookup keyword the owner linked: the data `closed_list_items` reads);
- the held products' own spec values, one line per visible key that holds one;
- the file types, certificate kinds and schemes the held products have on record.

A word nothing matches gets no line; the existing ask paths handle it. Data only: no word is
special-cased. Product reads go through the scoped session and `chat_searchable_products`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

MODE_BLOCK = "block"
MODE_INDEX = "index"
MODES = frozenset({MODE_BLOCK, MODE_INDEX})

#: The full closed-list registry variables index mode blanks, each to one FIXED line (never
#: anything that varies per turn or per contact: the system prompt's cache must hold).
SYSTEM_BLANKS: dict[str, str] = {
    "specs": (
        "Specification lines: the user turn lists them for this message, as spec K = V lines "
        "(the values its words name and the held products' own values)."
    ),
    "attachment_types": (
        "File type lines: the user turn lists them for this message (the file types its words "
        "name and the held products have)."
    ),
    "certification_types": (
        "Certificate kind and Certificate scheme lines: the user turn lists them for this "
        "message (the ones its words name and the held products have)."
    ),
}

#: Held products read per turn, spec keys printed for them, values per key, and file /
#: certificate lines in all: the per-turn text is not cached, so it stays lean.
CAP_HELD_PRODUCTS = 5
CAP_HELD_KEYS = 20
CAP_VALUES_PER_KEY = 5
CAP_FILE_LINES = 12


def normalised(mode: Any) -> str:
    """A stored mode; anything unknown (or none) is `block`."""
    text = str(mode or MODE_BLOCK)
    return text if text in MODES else MODE_BLOCK


def read_mode(db: "Session") -> str:
    """The mode, read now (no cache: a flip reaches the very next turn)."""
    from app.models.user import SystemSetting

    row = db.query(SystemSetting.chatbot_closed_lists_mode).first()
    return normalised(row[0] if row is not None else None)


# --------------------------------------------------------------------------- #
# (b) The held products' own spec values
# --------------------------------------------------------------------------- #


def _number_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return None
    return str(int(number)) if number.is_integer() else repr(number)


def _spec_items(row: Any, raw: Any) -> list[str]:
    """One stored value of a registry key in the candidate line format the rules read."""
    from app.services.chatbot.head.candidates import TYPE_KEYS, _Value
    from app.services.chatbot_prompt_vars import candidate_text
    from app.services.product_spec_registry import display_spec_value

    data_type = (row.data_type or "").lower()
    values = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for value in values:
        if value is None or str(value).strip() == "":
            continue
        if data_type == "numeric":
            number = _number_text(value)
            if number is not None:
                out.append(f"spec {candidate_text(row.spec_key)} = {number}")
            continue
        if data_type == "boolean" or isinstance(value, bool):
            out.append(_Value("flag", row.spec_key, str(value).strip().lower(), str(row.label or row.spec_key)).text())
            continue
        labels = dict(getattr(row, "value_labels", None) or {})
        kind = "product type" if row.spec_key in TYPE_KEYS else "spec"
        out.append(_Value(kind, row.spec_key, str(value), display_spec_value(value, labels)).text())
    return out


def held_spec_lines(db: "Session", held_ids: list[str], hidden: frozenset[str] = frozenset()) -> list[str]:
    """One line per visible registry key the held products hold a value under, the values
    they hold (deduped) in the `spec K = V (label)` / `spec K = N` format; a contact-hidden key
    is named by no line."""
    from app.models.product import Product, chat_searchable_products
    from app.models.product_spec import ProductSpecifications
    from app.services.chatbot.head.candidates import SKIP_KEYS, _registry

    if not held_ids:
        return []
    registry = {row.spec_key: row for row in _registry(db, hidden) if row.spec_key not in SKIP_KEYS}
    if not registry:
        return []
    rows = (
        db.query(ProductSpecifications.values)
        .join(Product, Product.id == ProductSpecifications.product_id)
        .filter(ProductSpecifications.product_id.in_(held_ids), chat_searchable_products())
        .all()
    )
    by_key: dict[str, list[str]] = {}
    for (values,) in rows:
        for key, entry in (values or {}).items():
            row = registry.get(key)
            if row is None:
                continue
            raw = entry.get("value") if isinstance(entry, dict) else entry
            held = by_key.setdefault(key, [])
            for item in _spec_items(row, raw):
                if item not in held:
                    held.append(item)
    return ["; ".join(items[:CAP_VALUES_PER_KEY]) for key, items in sorted(by_key.items()) if items][:CAP_HELD_KEYS]


# --------------------------------------------------------------------------- #
# (a) + (c) File types, certificate kinds and schemes
# --------------------------------------------------------------------------- #


def _held_types(db: "Session", held_ids: list[str]) -> set[str]:
    """The attachment types (by their listed item, casefolded) of the held products' live files."""
    from sqlalchemy import func

    from app.models.product import Product, ProductAttachment, chat_searchable_products
    from app.models.resources import Attachment, AttachmentType
    from app.services.chatbot_prompt_vars import _item

    rows = (
        db.query(AttachmentType.code, AttachmentType.type_name)
        .join(Attachment, Attachment.attachment_type_id == AttachmentType.id)
        .join(ProductAttachment, ProductAttachment.attachment_id == Attachment.id)
        .join(Product, Product.id == ProductAttachment.product_id)
        .filter(
            ProductAttachment.product_id.in_(held_ids),
            func.coalesce(Attachment.is_deleted, False).is_(False),
            chat_searchable_products(),
        )
        .distinct()
        .all()
    )
    return {_item({"code": code, "type_name": name}).casefold() for code, name in rows}


def _held_schemes(db: "Session", held_ids: list[str]) -> set[str]:
    """The schemes (casefolded) of the active certificates filed against the held products'
    own files (the link `scheme_index._held_certificates` reads)."""
    from sqlalchemy import func

    from app.models.certificate import Certificate, CertificateRevision
    from app.models.product import Product, ProductAttachment, chat_searchable_products

    rows = (
        db.query(func.lower(Certificate.scheme))
        .join(CertificateRevision, CertificateRevision.certificate_id == Certificate.id)
        .join(ProductAttachment, ProductAttachment.attachment_id == CertificateRevision.attachment_id)
        .join(Product, Product.id == ProductAttachment.product_id)
        .filter(
            ProductAttachment.product_id.in_(held_ids),
            Certificate.status == "active",
            Certificate.scheme.isnot(None),
            chat_searchable_products(),
        )
        .distinct()
        .all()
    )
    return {str(scheme) for (scheme,) in rows if scheme}


def _grams(message: str) -> set[str]:
    """Every run of up to `MAX_PHRASE_WORDS` words of the message, as `_phrase` folds them."""
    from app.services.chatbot.head.candidates import MAX_PHRASE_WORDS, _phrase, _tokens

    words = [w for w in (_phrase(t) for t in _tokens(message)) if w]
    out: set[str] = set()
    for size in range(1, MAX_PHRASE_WORDS + 1):
        for start in range(len(words) - size + 1):
            out.add(" ".join(words[start : start + size]))
    return out


def _named(grams: set[str], keys: list[str]) -> bool:
    """Does the message name one of `keys` (a code, name or word on file): exactly, or spelt
    near it the way the candidate lines read near spellings (same word count, pg_trgm score)."""
    from app.services.chatbot.head.candidates import MIN_NEAR_CHARS, NEAR_PHRASE, _phrase, similarity, trigrams

    folded = {k for k in (_phrase(key) for key in keys) if k}
    if grams & folded:
        return True
    for key in folded:
        if len(key.replace(" ", "")) < MIN_NEAR_CHARS:
            continue
        size = len(key.split())
        key_trigrams = trigrams(key)
        for gram in grams:
            if len(gram.split()) == size and len(gram.replace(" ", "")) >= MIN_NEAR_CHARS:
                if similarity(trigrams(gram), key_trigrams) >= NEAR_PHRASE:
                    return True
    return False


def file_lines(db: "Session", message: str, held_ids: list[str]) -> list[str]:
    """The File type, Certificate kind and Certificate scheme lines (the `{{attachment_types}}`
    / `{{certification_types}}` wording) for the items the message's words name and the items
    the held products have on record, in list order."""
    from app.services import chatbot_prompt_vars as pv

    grams = _grams(message)
    held_types = _held_types(db, held_ids) if held_ids else set()
    held_schemes = _held_schemes(db, held_ids) if held_ids else set()
    aliases = pv._alias_words(db)

    def type_keys(row: dict) -> list[str]:
        return [pv._item(row), str(row.get("type_name") or ""), *pv._type_words(row, aliases)]

    lines: list[str] = []
    for row in pv._file_type_rows(db):
        if pv._item(row).casefold() in held_types or _named(grams, type_keys(row)):
            lines.append(pv.file_type_line(row, aliases))
    for row in pv._cert_kind_rows(db):
        if pv._item(row).casefold() in held_types or _named(grams, type_keys(row)):
            lines.append(pv.cert_kind_line(row, aliases))
    for name, words in pv._cert_schemes(db):
        if name.casefold() in held_schemes or _named(grams, [name, *words]):
            lines.append(pv.cert_scheme_line(name, words))
    return list(dict.fromkeys(lines))[:CAP_FILE_LINES]


def index_lines(
    db: "Session", message: str, held_ids: list[str] | None, hidden: frozenset[str] = frozenset()
) -> list[str]:
    """What index mode adds to the CLOSED LISTS block: the held products' spec lines, then the
    file type / certificate lines the words name or the held products have. Empty when nothing
    matches (a word matching nothing gets no line)."""
    held = list(dict.fromkeys(str(h) for h in held_ids or [] if h))[:CAP_HELD_PRODUCTS]
    return [*held_spec_lines(db, held, hidden), *file_lines(db, message, held)]
