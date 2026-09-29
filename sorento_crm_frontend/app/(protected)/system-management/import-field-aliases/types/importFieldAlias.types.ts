/** The document readers this lane teaches aliases to (S5; `supplier_inventory_word` added
 *  S4, `PLAN-stock-list-bare-model-codes.md`). One more doc type is one more entry here - a
 *  union, not a table, because the readers are fixed in code. */
export type ImportFieldAliasDocType =
  | 'proforma_invoice'
  | 'packing_list'
  | 'supplier_inventory'
  | 'supplier_inventory_word';

export const IMPORT_FIELD_ALIAS_DOC_TYPES: { value: ImportFieldAliasDocType; label: string }[] = [
  { value: 'proforma_invoice', label: 'Proforma invoice' },
  { value: 'packing_list', label: 'Packing list' },
  { value: 'supplier_inventory', label: 'Stock list' },
  { value: 'supplier_inventory_word', label: 'Stock list words' },
];

/** One header the supplier used, on file as meaning `field`. `supplier_id`/`supplier_name`
 *  (S4, D6): `null` on every doc type but `supplier_inventory_word`'s SHARED rows - a
 *  supplier-scoped word row carries the name, never the id, so nothing renders a UUID. */
export interface ImportFieldAlias {
  id: string;
  alias: string;
  locale: string | null;
  created_at: string;
  supplier_id?: string | null;
  supplier_name?: string | null;
}

/** One system field, and every header on file that resolves to it (AC-E1's grouped
 *  shape) - what the settings page's grid reads one row of. */
export interface ImportFieldAliasGroup {
  field: string;
  label: string;
  aliases: ImportFieldAlias[];
}

/** A field the reader can bind a header to (AC-E1's `/fields` list, AC-E4's "Map to..."
 *  picker) - `label` is this page's own wording, never the raw column name. */
export interface ImportFieldAliasFieldOption {
  field: string;
  label: string;
}
