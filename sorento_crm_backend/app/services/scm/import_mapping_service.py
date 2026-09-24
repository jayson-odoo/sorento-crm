"""The inline import column mapper's own two verbs (B4/B5, PLAN-import-column-mapper-24sep.md):
probe a file's headers against a supplier-scoped resolver, and save what the operator picked.

No new table: a saved mapping IS a supplier-scoped `import_field_alias` row (R1/R2) - `save`
upserts through the SAME table every reader already resolves through, so a saved layout is
live the moment the next probe or preview asks for it, with nothing else to wire.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.import_alias import ImportFieldAlias
from app.services.error_handler import AppException
from app.services.field_access import field_label
from app.services.import_alias_service import (
    IGNORE_FIELD,
    AliasResolver,
    canonical_fields,
    normalize_header,
)
from app.services.scm.header_probe import probe as probe_headers
from app.services.scm.outstanding_reader import all_sheet_rows
from app.services.scm.packing_list_reader import header_field_candidates

#: Header-block fields' own display wording (AC-F2: "PI number, Invoice date, BL,
#: Container, Seal, Currency") - `field_label`'s generic `field_key.replace("_",
#: " ").capitalize()` fallback would read "Bl no"/"Pi number" instead, so these six are
#: spelled out rather than left to the generic rule the COLUMN section's labels use.
_HEADER_FIELD_LABELS: dict[str, str] = {
    "pi_number": "PI number",
    "invoice_date": "Invoice date",
    "bl_no": "BL",
    "container_no": "Container",
    "seal_no": "Seal",
    "currency": "Currency",
}


def _header_field_label(field: str) -> str:
    return _HEADER_FIELD_LABELS.get(field) or field_label(field)


#: Doc types whose readers carry a header BLOCK at all (F1/R-D,
#: PLAN-pi-header-fields-convert-fixes-24sep.md) - `supplier_inventory` is one row per
#: line, nothing above it to scan.
_HEADER_FIELD_DOC_TYPES = {"proforma_invoice", "packing_list"}


def _block_fields_for(doc_type: str) -> tuple[str, ...]:
    if doc_type == "proforma_invoice":
        from app.services.scm.proforma_invoice_reader import _BLOCK_FIELDS

        return _BLOCK_FIELDS
    if doc_type == "packing_list":
        from app.services.scm.packing_list_reader import _BLOCK_FIELDS

        return _BLOCK_FIELDS
    return ()


def _required_columns(doc_type: str) -> tuple[str, ...]:
    if doc_type == "proforma_invoice":
        from app.services.scm.proforma_invoice_reader import REQUIRED_COLUMNS
    elif doc_type == "packing_list":
        from app.services.scm.packing_list_reader import REQUIRED_COLUMNS
    elif doc_type == "supplier_inventory":
        from app.services.scm.supplier_inventory_reader import REQUIRED_COLUMNS
    else:
        return ()
    return REQUIRED_COLUMNS


def _merged_required(doc_types: list[str]) -> list[str]:
    """Every required field ACROSS the doc types, in first-seen order - a combined file
    (G4/AC-M13) shows one mapper section whose "still needed" line covers both readers."""
    seen: set[str] = set()
    out: list[str] = []
    for doc_type in doc_types:
        for f in _required_columns(doc_type):
            if f not in seen:
                seen.add(f)
                out.append(f)
    return out


def _merged_fields(doc_types: list[str]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for doc_type in doc_types:
        for f in canonical_fields(doc_type):
            if f not in seen:
                seen.add(f)
                out.append({"field": f, "label": field_label(f)})
    return out


def probe(
    db: Session,
    file_data: bytes,
    *,
    supplier_id: str,
    doc_types: list[str],
    header_row: Optional[int] = None,
) -> dict:
    """The FE's own contract (`importMappingService.ts`'s `ProbeImportMappingResult`,
    Phase 1): `header_row`, `columns` (each carrying the resolver's CURRENT answer for
    this supplier), `required_fields`, `missing_required`, `fields`.

    A combined file (two doc types) resolves a header through WHICHEVER of the two
    resolvers answers first (doc_types order) - after a save they agree (G4 writes the
    same rows under both), so which one answers first only matters before that first
    save.
    """
    try:
        probed = probe_headers(file_data, header_row=header_row)
    except Exception as exc:  # noqa: BLE001 - R4: a plain 422, never a raw 500 with a
        # traceback and a module path leaked to whoever uploaded the wrong file.
        raise AppException(422, "This file could not be read.", detail="file") from exc
    resolvers = [AliasResolver.for_supplier(db, doc_type, supplier_id) for doc_type in doc_types]
    required_fields = _merged_required(doc_types)

    columns: list[dict] = []
    seen_fields: set[str] = set()
    for col in probed.columns:
        raw_field: Optional[str] = None
        source = "none"
        for resolver in resolvers:
            rf = resolver.raw_field_for_header(col.header)
            if rf is not None:
                raw_field = rf
                source = resolver.source_for_header(col.header) or "shared"
                break
        if raw_field is not None and raw_field != IGNORE_FIELD:
            seen_fields.add(raw_field)
        columns.append(
            {
                "position": col.position,
                "header": col.header,
                "samples": col.samples,
                "field": raw_field,
                "source": source,
                "required": raw_field is not None and raw_field in required_fields,
            }
        )

    # F1/R-D: every `label：value` pair ABOVE the header row, for a doc type whose reader
    # carries a header block at all - the mapper's own "Header fields" section (F2). Block
    # fields ACROSS every requested doc type, `consignee` excluded (R-B: always the PI's
    # own company, never a mapper pick) - resolved through whichever of THIS probe's own
    # resolvers answers for a relevant doc type, the same "first doc type wins" rule the
    # columns above already follow. Computed unconditionally (not gated on `header_fields`
    # actually finding anything): `header_field_choices` (V2, review round 1) is the
    # mapper's own field VOCABULARY for this doc type, independent of whether this
    # particular file states any pairs at all.
    block_fields: set[str] = set()
    for dt in doc_types:
        block_fields.update(_block_fields_for(dt))
    block_fields.discard("consignee")

    header_fields: list[dict] = []
    if probed.header_row and probed.header_row > 1 and block_fields:
        resolver = next(
            (r for r, dt in zip(resolvers, doc_types) if dt in _HEADER_FIELD_DOC_TYPES), None
        )
        if resolver is not None:
            rows = all_sheet_rows(file_data)
            above_rows = rows[: probed.header_row - 1]
            if above_rows:
                header_fields = header_field_candidates(above_rows, resolver, tuple(block_fields))

    return {
        "header_row": probed.header_row,
        "columns": columns,
        "required_fields": required_fields,
        "missing_required": [f for f in required_fields if f not in seen_fields],
        "fields": _merged_fields(doc_types),
        # Review round 1, item 12: the stepper's own ceiling, so "move header row down"
        # has somewhere to stop.
        "row_count": probed.row_count,
        "header_fields": header_fields,
        # V2 (review round 1): the "Header fields" section's own choices - the doc
        # type(s)' block fields, `consignee` excluded, so a packing-list-only upload is
        # never offered Currency (a proforma-invoice-only concept no reader for it saves).
        "header_field_choices": [
            {"field": f, "label": _header_field_label(f)} for f in sorted(block_fields)
        ],
    }


def save(
    db: Session,
    *,
    supplier_id: str,
    doc_types: list[str],
    mappings: list[tuple[str, str]],
) -> None:
    """Upsert supplier-scoped rows - a re-map REPLACES this supplier's earlier choice for
    the same header rather than accumulating (AC-M6): the DELETE below is scoped to this
    supplier's own prior row for the header, then the INSERT lands the new one.

    A field is written under EVERY doc type in `doc_types` that actually asks for it, and
    SILENTLY SKIPPED (not written, not an error) for one that does not - G4: "a field only
    one doc type reads is saved for that one" - a combined file's mapper offers the UNION
    of both readers' fields, and most fields belong to only one of them (`description` is
    a proforma_invoice field; a packing list calls the same idea `product_name`). `ignore`
    is written under every requested doc type regardless (G2: it means "nothing", the same
    nothing for either reader). A field that matches NONE of the requested doc types is a
    genuine mistake - unknown to every reader asked - and is refused, 422.

    Insert targets `uq_import_field_alias_supplier` (migration `ifa_supplier_uniq`, owner
    ruling A, review round 2 - a PLAIN, non-partial index, not partial the way its shared
    counterpart is; see that migration's own docstring for why): a different supplier
    saving the SAME header now gets its OWN row rather than losing the `ON CONFLICT` race
    against an earlier supplier's (R11) - the old plain triple had no `supplier_id` in it,
    so a second supplier's identical save silently no-opped and that supplier never got a
    row of their own. Before inserting, a SHARED row (`supplier_id IS NULL`) answering the
    exact same (doc_type, field, alias) is checked for and, if one exists, the insert is
    skipped entirely - the shared row already answers this supplier's header the same way
    theirs would have, so no redundant supplier row is written (R11's kept half).
    """
    known_by_doc_type = {doc_type: set(canonical_fields(doc_type)) for doc_type in doc_types}

    def _write(doc_type: str, header: str, field_value: str) -> None:
        # R6 (review round 1): matched by the NORMALISED key, not the literal `alias`
        # column - a re-map spelled differently ("Qty " then "QTY") is still the SAME
        # header to every reader here, and the old literal-string DELETE left the stale
        # row in place, silently blocked by the unique triple ever landing the new one.
        # Compared in Python (no raw SQL normalisation) so this stays the one place
        # `normalize_header` is the single source of truth for "same header".
        target_key = normalize_header(header)
        existing = (
            db.query(ImportFieldAlias.id, ImportFieldAlias.alias)
            .filter(
                ImportFieldAlias.doc_type == doc_type,
                ImportFieldAlias.supplier_id == supplier_id,
            )
            .all()
        )
        stale_ids = [row.id for row in existing if normalize_header(row.alias) == target_key]
        if stale_ids:
            db.query(ImportFieldAlias).filter(ImportFieldAlias.id.in_(stale_ids)).delete(
                synchronize_session=False
            )
        # A SHARED row already answering this exact (doc_type, field) for the SAME
        # normalised header makes a supplier row redundant - skip the insert rather than
        # duplicate what already resolves the same way for this supplier too (R11's kept
        # half). Matched by the normalised key (review round 3, R19), same reason as the
        # DELETE above: a literal `alias == header` comparison missed a header that only
        # differs by case or whitespace from the shared row's own spelling ('Qty ' vs the
        # seeded 'QTY'), so the check never fired and a redundant supplier row landed
        # anyway.
        shared_rows = (
            db.query(ImportFieldAlias.alias)
            .filter(
                ImportFieldAlias.doc_type == doc_type,
                ImportFieldAlias.field == field_value,
                ImportFieldAlias.supplier_id.is_(None),
            )
            .all()
        )
        shared_exists = any(normalize_header(row.alias) == target_key for row in shared_rows)
        if shared_exists:
            return
        # `uq_import_field_alias_supplier` is a PLAIN (non-partial) index - Postgres only
        # infers a partial index as an ON CONFLICT arbiter when the predicate is repeated
        # verbatim, and this insert always carries a non-NULL `supplier_id`, so the plain
        # four-column tuple is the correct, simpler target (see the model's own note).
        stmt = (
            pg_insert(ImportFieldAlias)
            .values(doc_type=doc_type, field=field_value, alias=header, supplier_id=supplier_id)
            .on_conflict_do_nothing(
                index_elements=["doc_type", "field", "alias", "supplier_id"]
            )
        )
        db.execute(stmt)

    for header, field_value in mappings:
        if field_value == IGNORE_FIELD:
            applicable = doc_types
        else:
            applicable = [dt for dt in doc_types if field_value in known_by_doc_type[dt]]
            if not applicable:
                raise AppException(
                    422,
                    f"'{field_value}' is not a field any of these readers ask for.",
                    detail="field",
                )
        for doc_type in applicable:
            _write(doc_type, header, field_value)
    db.flush()
