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
from app.services.import_alias_service import IGNORE_FIELD, AliasResolver, canonical_fields
from app.services.scm.header_probe import probe as probe_headers


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
    probed = probe_headers(file_data, header_row=header_row)
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

    return {
        "header_row": probed.header_row,
        "columns": columns,
        "required_fields": required_fields,
        "missing_required": [f for f in required_fields if f not in seen_fields],
        "fields": _merged_fields(doc_types),
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

    `ON CONFLICT (doc_type, field, alias) DO NOTHING` (the table's own triple, unchanged -
    "no new table, no migration"): that triple has no `supplier_id` in it by design (see
    the model's own comment), so a header already aliased - shared, or another supplier's
    own row - to the SAME field cannot be re-inserted for this supplier too. The insert
    silently does nothing in that case rather than erroring, and reading still works: the
    existing row (whoever it belongs to) already answers this supplier's header the same
    way theirs would have. Only a genuinely NEW (doc_type, field, alias) triple - the
    common case, since two suppliers rarely write the exact same header text - actually
    lands a new row.
    """
    known_by_doc_type = {doc_type: set(canonical_fields(doc_type)) for doc_type in doc_types}

    def _write(doc_type: str, header: str, field_value: str) -> None:
        db.query(ImportFieldAlias).filter(
            ImportFieldAlias.doc_type == doc_type,
            ImportFieldAlias.supplier_id == supplier_id,
            ImportFieldAlias.alias == header,
        ).delete(synchronize_session=False)
        stmt = (
            pg_insert(ImportFieldAlias)
            .values(doc_type=doc_type, field=field_value, alias=header, supplier_id=supplier_id)
            .on_conflict_do_nothing(constraint="uq_import_field_alias_triple")
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
