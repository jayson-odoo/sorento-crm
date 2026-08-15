"""Resolve spreadsheet headers to canonical fields, from the alias table.

The contract every new importer calls, so that none of them hardcodes a header list.
Deliberately small: build a resolver once per file, then ask it for fields.

    r = AliasResolver.for_doc_type(db, "outstanding_so")
    code = r.get(row, "item_code")          # None when the column is absent
    date = r.get(row, "required_date")
    missing = r.missing_required(["item_code", "qty_outstanding", "required_date"])

Normalisation is the whole trick. Real files carry trailing spaces, newlines inside header
cells (the packing list has "净重\\n(kg)"), doubled spaces, full-width brackets, and
inconsistent case. Two headers that a human reads as the same header must resolve to the
same field, or the alias table just moves the problem.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy.orm import Session

from app.models.import_alias import ImportFieldAlias


def normalize_header(value: Any) -> str:
    """Fold a header cell to a comparison key.

    NFKC first, which is what collapses full-width punctuation (（） to ()) and is why a
    Chinese header typed on a different keyboard still matches. Then strip everything that
    is not alphanumeric or CJK, so spacing, newlines, brackets and units drop out:
    "净重\\n(kg)" and "净重(kg)" and "净重 (KG)" all become the same key.
    """
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value)).strip().lower()
    # Keep letters, digits and CJK; drop the rest rather than trying to enumerate it.
    s = re.sub(r"[^0-9a-z㐀-䶿一-鿿]+", "", s)
    return s


class AliasResolver:
    """Header-to-field resolution for ONE document type.

    Holds a normalised alias -> field map, built once. `get` accepts the row as a mapping
    keyed by the file's own header strings, which is how every existing importer already
    reads its rows, so adopting this costs a line rather than a rewrite.
    """

    def __init__(self, doc_type: str, alias_to_field: Mapping[str, str]) -> None:
        self.doc_type = doc_type
        self._alias_to_field = dict(alias_to_field)
        # Resolved per row-set, so `missing_required` can answer honestly about THIS file.
        self._seen_fields: set[str] = set()

    # -- construction --------------------------------------------------------

    @classmethod
    def for_doc_type(cls, db: Session, doc_type: str) -> "AliasResolver":
        rows = (
            db.query(ImportFieldAlias.field, ImportFieldAlias.alias)
            .filter(ImportFieldAlias.doc_type == doc_type)
            .all()
        )
        mapping: dict[str, str] = {}
        for field, alias in rows:
            key = normalize_header(alias)
            if key:
                # First alias wins on a collision; a duplicate alias pointing at two
                # fields is a data error, and silently flipping between them per query
                # would be worse than being deterministic about it.
                mapping.setdefault(key, field)
        # The canonical field name is always its own alias. Saves seeding an identity row
        # per field and means a file whose headers already match needs no configuration.
        for field, _ in rows:
            mapping.setdefault(normalize_header(field), field)
        return cls(doc_type, mapping)

    # -- resolution ----------------------------------------------------------

    def field_for_header(self, header: Any) -> Optional[str]:
        return self._alias_to_field.get(normalize_header(header))

    def index_row(self, row: Mapping[Any, Any]) -> dict[str, Any]:
        """Re-key one row from file headers to canonical fields.

        Values are taken from the FIRST header that resolves to a field and is non-empty,
        so a file carrying both "ITEM CODE" and "型号" for the same field does not depend
        on dictionary ordering to pick the populated one.
        """
        out: dict[str, Any] = {}
        for header, value in row.items():
            field = self.field_for_header(header)
            if field is None:
                continue
            self._seen_fields.add(field)
            if field not in out or _is_blank(out[field]):
                out[field] = value
        return out

    def get(self, row: Mapping[Any, Any], field: str) -> Any:
        """Read one canonical field out of a raw row. `None` when absent or blank."""
        for header, value in row.items():
            if self.field_for_header(header) == field:
                self._seen_fields.add(field)
                if not _is_blank(value):
                    return value
        return None

    # -- diagnostics ---------------------------------------------------------

    def unmapped_headers(self, row: Mapping[Any, Any]) -> list[str]:
        """Headers this document type has no alias for.

        Surfaced on the import preview rather than dropped: an unmapped header is usually
        the first sign that a client's export changed, and it is a one-row fix in the alias
        table once someone can see it.
        """
        return [
            str(h)
            for h in row.keys()
            if normalize_header(h) and self.field_for_header(h) is None
        ]

    def missing_required(self, required: Iterable[str]) -> list[str]:
        """Required canonical fields no header in this file resolved to."""
        return [f for f in required if f not in self._seen_fields]

    @property
    def known_fields(self) -> set[str]:
        return set(self._alias_to_field.values())


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
