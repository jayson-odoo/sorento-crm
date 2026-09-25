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

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.import_alias import ImportFieldAlias

#: A column the operator has looked at and decided means nothing (grill G2, AC-M7). Saved
#: as a real row like any other pick - `field_for_header` resolves it to `None` (nothing to
#: read), but `unmapped_headers` counts it as known, so an ignored column does not put the
#: mapper back in front of the operator on every later upload of the same layout (R3).
IGNORE_FIELD = "ignore"


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

    def __init__(
        self,
        doc_type: str,
        alias_to_field: Mapping[str, str],
        source: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.doc_type = doc_type
        # RAW field per normalised key - may be `IGNORE_FIELD`, which `field_for_header`
        # folds to `None` for reading but `raw_field_for_header`/`unmapped_headers` still
        # see, so an ignored column stays "known" without ever being read as data (AC-M7).
        self._alias_to_field = dict(alias_to_field)
        # Which kind of row answered each key - "supplier" or "shared" (B4's probe
        # response, `source`). Not populated for a key resolved only by the identity
        # fallback (a header that already spells the field name) - nothing asked for that.
        self._source = dict(source or {})
        # Resolved per row-set, so `missing_required` can answer honestly about THIS file.
        self._seen_fields: set[str] = set()

    # -- construction --------------------------------------------------------

    @classmethod
    def for_doc_type(cls, db: Session, doc_type: str) -> "AliasResolver":
        """SHARED rows only (`supplier_id IS NULL`) - review round 1, R5: unfiltered, a
        supplier-scoped row (say, one supplier's own override) leaked into every caller
        with no supplier chosen at all, which is exactly the "same header, different
        meaning per supplier" case `for_supplier` exists to keep apart. A caller that
        wants a supplier's own rows too calls `for_supplier`."""
        rows = (
            db.query(ImportFieldAlias.field, ImportFieldAlias.alias)
            .filter(
                ImportFieldAlias.doc_type == doc_type,
                ImportFieldAlias.supplier_id.is_(None),
            )
            .all()
        )
        mapping: dict[str, str] = {}
        source: dict[str, str] = {}
        for field, alias in rows:
            key = normalize_header(alias)
            if key:
                # First alias wins on a collision; a duplicate alias pointing at two
                # fields is a data error, and silently flipping between them per query
                # would be worse than being deterministic about it.
                mapping.setdefault(key, field)
                source.setdefault(key, "shared")
        # The canonical field name is always its own alias. Saves seeding an identity row
        # per field and means a file whose headers already match needs no configuration.
        for field, _ in rows:
            mapping.setdefault(normalize_header(field), field)
        return cls(doc_type, mapping, source)

    @classmethod
    def for_supplier(
        cls, db: Session, doc_type: str, supplier_id: Optional[str]
    ) -> "AliasResolver":
        """Like `for_doc_type`, but a SUPPLIER-scoped row beats a shared row on the same
        normalised header (B1, R1/R2) - never the reverse, and never another supplier's
        row, which is why the query narrows to `supplier_id` rather than reading every
        row the way `for_doc_type` does. Same header, different meaning per supplier
        (design section) is exactly what a shared table alone cannot hold.

        A `supplier_id` that is not a real id at all (review round 3, R18 - same guard
        `WordList.for_supplier` in `supplier_code_composer.py` already uses) reads as the
        SHARED-only list rather than reaching the uuid column comparison, which raises
        `InvalidTextRepresentation` - not an `AppException` - and leaves the session
        aborted.
        """
        from app.services.scm.supplier_scope import is_uuid

        valid_supplier_id = supplier_id if supplier_id and is_uuid(supplier_id) else None
        query = db.query(
            ImportFieldAlias.field, ImportFieldAlias.alias, ImportFieldAlias.supplier_id
        ).filter(ImportFieldAlias.doc_type == doc_type)
        if valid_supplier_id:
            query = query.filter(
                or_(
                    ImportFieldAlias.supplier_id.is_(None),
                    ImportFieldAlias.supplier_id == valid_supplier_id,
                )
            )
        else:
            query = query.filter(ImportFieldAlias.supplier_id.is_(None))
        rows = query.all()

        mapping: dict[str, str] = {}
        source: dict[str, str] = {}
        # Shared rows first - first spelling wins on a collision, same rule as
        # `for_doc_type`.
        for field, alias, sid in rows:
            if sid is not None:
                continue
            key = normalize_header(alias)
            if key:
                mapping.setdefault(key, field)
                source.setdefault(key, "shared")
        # THEN the supplier's own rows overwrite the same key unconditionally - a
        # supplier override beats a shared row every time, regardless of which the
        # query happened to return first. Among the supplier's own rows, first wins.
        supplier_seen: set[str] = set()
        for field, alias, sid in rows:
            if sid is None:
                continue
            key = normalize_header(alias)
            if key and key not in supplier_seen:
                mapping[key] = field
                source[key] = "supplier"
                supplier_seen.add(key)
        for field, _, _ in rows:
            mapping.setdefault(normalize_header(field), field)
        return cls(doc_type, mapping, source)

    # -- resolution ----------------------------------------------------------

    def raw_field_for_header(self, header: Any) -> Optional[str]:
        """The stored field for this header, `IGNORE_FIELD` included - what the mapper's
        own probe (B4) shows the operator, as opposed to `field_for_header`, which is
        what a READER is allowed to act on."""
        return self._alias_to_field.get(normalize_header(header))

    def source_for_header(self, header: Any) -> Optional[str]:
        """"supplier" or "shared" - which row answered this header, for the probe
        response (B4). `None` when nothing has ever mapped it, or it resolved only
        through the identity fallback (the header already spells the field name)."""
        return self._source.get(normalize_header(header))

    def field_for_header(self, header: Any) -> Optional[str]:
        field = self.raw_field_for_header(header)
        if field is None or field == IGNORE_FIELD:
            return None
        return field

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
        table once someone can see it. Checked against `raw_field_for_header`, not
        `field_for_header` (AC-M7): an IGNORED header still resolves to nothing at read
        time, but it is a KNOWN answer, not a missing one.
        """
        return [
            str(h)
            for h in row.keys()
            if normalize_header(h) and self.raw_field_for_header(h) is None
        ]

    def missing_required(self, required: Iterable[str]) -> list[str]:
        """Required canonical fields no header in this file resolved to."""
        return [f for f in required if f not in self._seen_fields]

    @property
    def known_fields(self) -> set[str]:
        return set(self._alias_to_field.values())


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


#: Internal bookkeeping fields every reader's dataclasses carry that are never something a
#: header maps TO (B7): a row/document position, the container `list[...]` fields, or the
#: reader's own error bag. Denied here, once, rather than per doc type - a field this list
#: excludes never reached the mapper's own field picker either way (measured 24 Sep,
#: PLAN-import-column-mapper-24sep.md).
_DENY_INTERNAL_FIELDS = {"row_number", "index", "header_row", "lines", "problems"}


def canonical_fields(doc_type: str) -> list[str]:
    """The canonical field names a document type's own reader asks for (S5, AC-E1) - read
    off the reader's OWN dataclasses (`dataclasses.fields`), never hand-typed: a field the
    reader adds tomorrow is on this list the same day, with no second place to update it.

    Deferred imports: both readers import `AliasResolver` FROM this module, so importing
    them back at module level here would cycle.
    """
    import dataclasses

    if doc_type == "proforma_invoice":
        from app.services.scm.proforma_invoice_reader import ProformaDocument, ProformaLine

        classes: tuple[type, ...] = (ProformaLine, ProformaDocument)
    elif doc_type == "packing_list":
        from app.services.scm.packing_list_reader import PackingBlock, PackingLine

        classes = (PackingLine, PackingBlock)
    elif doc_type == "supplier_inventory":
        # B7: this doc type used to answer `[]` here (measured 24 Sep) - the stock list
        # could not be mapped through the API at all. One row's own dataclass, unlike the
        # other two, which each need a line AND its enclosing document/block.
        from app.services.scm.supplier_inventory_reader import InventoryRow

        classes = (InventoryRow,)
    else:
        # `supplier_inventory_word` included (review round 1, item 4): its field is an OPEN,
        # shape-validated vocabulary (`supplier_code_composer.WORD_TOKEN_RE`), not a reader's
        # dataclass fields at all - `_assert_known_field` validates it by shape instead of
        # reading this list.
        return []

    seen: set[str] = set()
    out: list[str] = []
    for cls in classes:
        for f in dataclasses.fields(cls):
            if f.name in _DENY_INTERNAL_FIELDS or f.name in seen:
                continue
            seen.add(f.name)
            out.append(f.name)
    return out
