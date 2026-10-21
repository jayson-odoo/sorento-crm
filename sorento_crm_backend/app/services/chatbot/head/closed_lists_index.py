"""CLOSED-LISTS-INDEX-MODE (owner, 20 Oct 2026): the closed lists as an index, not a block.

`system_settings.chatbot_closed_lists_mode` says how a CLOSED LISTS parser version sees the
closed lists. `block` (the default, today) renders every full list into the system prompt.
`index` renders each full list variable as ONE fixed pointer line (`SYSTEM_BLANKS`), so the
system prompt stays byte-identical across turns and its cache holds, and the per-turn CLOSED
LISTS block (the candidate lines, `head/candidates.py`) also carries, in the lines the rules
already read (`block`):

- under the candidates' own heading, the file types, certificate kinds and schemes the
  message's own words name (their code, name, own words or a lookup keyword the owner linked:
  the data `closed_list_items` reads), and the spec values a word names as a registry code
  suffix (`code_suffix_forms`: a derivation rule's `-FRG` typed as "frg");
- under `HELD_HEADER`, the file types, certificate kinds and schemes the held products have on
  record, and their own spec values (one line per visible key that holds one).

A word nothing matches gets no line; the existing ask paths handle it. Data only: no word is
special-cased. Product reads go through the scoped session and `chat_searchable_products`.
Warehouses are no index line: their closed list is checked at grounding (`head/grounding`).
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

#: The one heading over the held products' own lines: they are on record, not said this turn.
HELD_HEADER = "On record for the held products (their own values, not words of this message):"

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


def _named_by(grams: set[str], keys: list[str]) -> tuple[str, bool] | None:
    """The gram of the message that names one of `keys` (a code, name or word on file), and
    whether it did so only by near spelling (same word count, pg_trgm score); None when none does."""
    from app.services.chatbot.head.candidates import MIN_NEAR_CHARS, NEAR_PHRASE, _phrase, similarity, trigrams

    folded = {k for k in (_phrase(key) for key in keys) if k}
    exact = sorted(grams & folded, key=lambda g: (-len(g.split()), g))
    if exact:
        return exact[0], False
    for key in sorted(folded):
        if len(key.replace(" ", "")) < MIN_NEAR_CHARS:
            continue
        size = len(key.split())
        key_trigrams = trigrams(key)
        for gram in sorted(grams):
            if len(gram.split()) == size and len(gram.replace(" ", "")) >= MIN_NEAR_CHARS:
                if similarity(trigrams(gram), key_trigrams) >= NEAR_PHRASE:
                    return gram, True
    return None


def _named(grams: set[str], keys: list[str]) -> bool:
    """Does the message name one of `keys`: exactly, or spelt near it the way the candidate
    lines read near spellings."""
    return _named_by(grams, keys) is not None


def _file_matches(db: "Session", message: str, held_ids: list[str]) -> tuple[list[dict], list[dict]]:
    """`file_lines`, with the list each line belongs to and the gram that named it: the named
    items as {"line", "list", "word", "near"} and the held items as {"line", "list"}, uncapped."""
    from app.services import chatbot_prompt_vars as pv

    grams = _grams(message)
    held_types = _held_types(db, held_ids) if held_ids else set()
    held_schemes = _held_schemes(db, held_ids) if held_ids else set()
    aliases = pv._alias_words(db)

    def type_keys(row: dict) -> list[str]:
        return [pv._item(row), str(row.get("type_name") or ""), *pv._type_words(row, aliases)]

    named: list[dict] = []
    held: list[dict] = []

    def add(line: str, list_name: str, hit: tuple[str, bool] | None, held_here: bool) -> None:
        if hit is not None:
            named.append({"line": line, "list": list_name, "word": hit[0], "near": hit[1]})
        if held_here:
            held.append({"line": line, "list": list_name})

    for row in pv._file_type_rows(db):
        add(pv.file_type_line(row, aliases), "File types", _named_by(grams, type_keys(row)), pv._item(row).casefold() in held_types)
    for row in pv._cert_kind_rows(db):
        add(pv.cert_kind_line(row, aliases), "Certificates", _named_by(grams, type_keys(row)), pv._item(row).casefold() in held_types)
    for name, words in pv._cert_schemes(db):
        add(pv.cert_scheme_line(name, words), "Certificate schemes", _named_by(grams, [name, *words]), name.casefold() in held_schemes)
    return named, held


def file_lines(db: "Session", message: str, held_ids: list[str]) -> tuple[list[str], list[str]]:
    """The File type, Certificate kind and Certificate scheme lines (the `{{attachment_types}}`
    / `{{certification_types}}` wording), in list order: those for the items the message's words
    name, and those for the items the held products have on record. An item can be in both."""
    named, held = _file_matches(db, message, held_ids)
    return (
        list(dict.fromkeys(m["line"] for m in named))[:CAP_FILE_LINES],
        list(dict.fromkeys(m["line"] for m in held))[:CAP_FILE_LINES],
    )


# --------------------------------------------------------------------------- #
# (a) Spec values a word names as a registry code suffix
# --------------------------------------------------------------------------- #


def code_suffix_forms(db: "Session", hidden: frozenset[str] = frozenset()) -> dict[str, list[tuple[Any, Any]]]:
    """The registry's code-suffix short forms: for every visible key's own derivation rule of kind
    `code`, `ends_with` a text `-X`, read the way derivation reads it (`stored_or_shipped_rules`,
    suppressed values out), the folded X ("frg" for `-FRG`) -> the (registry row, value) pairs it
    sets. The one reader the index lines (`code_suffix_lines`) and grounding's finish-word check
    share."""
    from app.services.chatbot.head.candidates import SKIP_KEYS, _phrase, _registry
    from app.services.product_spec_derivation import stored_or_shipped_rules, without_suppressed
    from app.services.product_spec_rules import builder_of

    forms: dict[str, list[tuple[Any, Any]]] = {}
    for row in _registry(db, hidden):
        if row.spec_key in SKIP_KEYS:
            continue
        for rule in without_suppressed(stored_or_shipped_rules(row), row.suppressed_values):
            builder = builder_of(rule)
            if builder.get("kind") != "code" or builder.get("code_match") != "ends_with":
                continue
            for text in builder.get("texts") or []:
                text = str(text).strip()
                word = _phrase(text[1:]) if text.startswith("-") else ""
                if word:
                    forms.setdefault(word, []).append((row, builder.get("value")))
    return forms


def _code_suffix_matches(db: "Session", grams: set[str], hidden: frozenset[str] = frozenset()) -> list[tuple[str, str, list[str]]]:
    """Per word a message gram names as a registry code-suffix short form: (word, its candidate
    line, the spec items on it)."""
    out: list[tuple[str, str, list[str]]] = []
    for word, pairs in code_suffix_forms(db, hidden).items():
        if word not in grams:
            continue
        items: list[str] = []
        for row, value in pairs:
            items += [item for item in _spec_items(row, value) if item not in items]
        if items:
            out.append((word, f'- "{word}": ' + "; ".join(items), items))
    return out


def code_suffix_lines(db: "Session", grams: set[str], hidden: frozenset[str] = frozenset()) -> list[str]:
    """The spec values a word of the message names exactly as a registry code-suffix short form
    (`code_suffix_forms`), one candidate line per word in the candidate lines'
    `- "word": spec K = V (label)` format."""
    return [line for _word, line, _items in _code_suffix_matches(db, grams, hidden)]


HELD_LIST = "On record for the held product"

_ITEM_LISTS = (
    ("set code ", "Products"),
    ("code ", "Products"),
    ("product type ", "Product types"),
    ("spec ", "Specifications"),
    ("flag", "Specifications"),
    ("size ", "Sizes"),
)


def _item_list(item: str) -> str:
    return next((name for prefix, name in _ITEM_LISTS if item.startswith(prefix)), "Other")


def _match(word: str | None, list_name: str, entry: str, line: str, *, near: bool = False, held: bool = False) -> dict:
    return {"word": word, "list": list_name, "entry": entry, "close_spelling": near, "held": held, "line": line}


def block_with_matches(
    db: "Session",
    entries: list[Any],
    message: str,
    held_ids: list[str] | None,
    hidden: frozenset[str] = frozenset(),
) -> tuple[list[str], list[dict]]:
    """`block()`'s lines for the `candidates.shortlist` result `entries`, and one match dict per
    entry sent (the word, which list it is on, the entry, whether the word only spells it
    closely, whether it is a held product's own line, and the line it sits on): what the
    per-turn trace shows."""
    from app.services.chatbot.head.candidates import CAP_LINES, HEADER, candidate_lines

    held = list(dict.fromkeys(str(h) for h in held_ids or [] if h))[:CAP_HELD_PRODUCTS]
    file_named, file_held = _file_matches(db, message, held)
    suffixes = _code_suffix_matches(db, _grams(message), hidden)

    matches: list[dict] = []
    lines = candidate_lines(entries)
    for entry in [e for e in entries if e.items][:CAP_LINES]:
        line = f'- "{entry.gram}": ' + "; ".join(entry.items)
        for item in entry.items:
            near = item.startswith("near ")
            text = item[len("near "):] if near else item
            matches.append(_match(entry.gram, _item_list(text), text, line, near=near))

    out = list(lines)
    sent = set(out)
    named: list[str] = []
    for word, line, items in suffixes:
        if line in sent or line in named:
            continue
        named.append(line)
        matches += [_match(word, "Specifications", item, line) for item in items]
    capped = list(dict.fromkeys(m["line"] for m in file_named))[:CAP_FILE_LINES]
    first = {}
    for m in file_named:
        first.setdefault(m["line"], m)
    file_seen = [line for line in capped if line not in sent and line not in named]
    for line in file_seen:
        m = first[line]
        matches.append(_match(m["word"], m["list"], line, line, near=m["near"]))
    named += file_seen
    if named:
        out = [*(out or [HEADER]), *named]

    held_texts = [*dict.fromkeys(m["line"] for m in file_held)][:CAP_FILE_LINES]
    spec_held = held_spec_lines(db, held, hidden)
    held_lines = [*held_texts, *spec_held]
    if held_lines:
        out += [HELD_HEADER, *held_lines]
        matches += [_match(None, HELD_LIST, line, line, held=True) for line in [*held_texts, *spec_held]]
    return out, matches


def block(
    db: "Session",
    candidate_lines: list[str],
    message: str,
    held_ids: list[str] | None,
    hidden: frozenset[str] = frozenset(),
) -> list[str]:
    """The CLOSED LISTS block in index mode: the candidate lines, with the code suffix and file type /
    certificate lines the message's words name under the same `candidates.HEADER`; then, under
    `HELD_HEADER`, the file types / certificates the held products have on record and their own spec
    lines. Each heading only when it has a line under it (a word matching nothing gets no line)."""
    from app.services.chatbot.head.candidates import HEADER

    held = list(dict.fromkeys(str(h) for h in held_ids or [] if h))[:CAP_HELD_PRODUCTS]
    named, on_record = file_lines(db, message, held)
    named = [*code_suffix_lines(db, _grams(message), hidden), *named]
    out = list(candidate_lines)
    named = [line for line in named if line not in out]
    if named:
        out = [*(out or [HEADER]), *named]
    held_lines = [*on_record, *held_spec_lines(db, held, hidden)]
    if held_lines:
        out += [HELD_HEADER, *held_lines]
    return out
