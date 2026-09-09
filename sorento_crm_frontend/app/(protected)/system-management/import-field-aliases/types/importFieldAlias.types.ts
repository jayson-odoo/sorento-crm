/** The two document readers this lane teaches aliases to (S5). One more doc type is one
 *  more entry here - a union, not a table, because the readers are fixed in code. */
export type ImportFieldAliasDocType = 'proforma_invoice' | 'packing_list';

export const IMPORT_FIELD_ALIAS_DOC_TYPES: { value: ImportFieldAliasDocType; label: string }[] = [
  { value: 'proforma_invoice', label: 'Proforma invoice' },
  { value: 'packing_list', label: 'Packing list' },
];

/** One header the supplier used, on file as meaning `field`. */
export interface ImportFieldAlias {
  id: string;
  alias: string;
  locale: string | null;
  created_at: string;
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
