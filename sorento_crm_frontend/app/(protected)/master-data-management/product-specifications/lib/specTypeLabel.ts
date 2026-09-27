/**
 * The plain word for a spec key's `data_type`, everywhere the type is shown
 * (AC-S3.2: List, Number (unit), Yes or no, Text; owner rulings 26-27 Sep 2026).
 *
 * The registry only ever creates `enum` / `numeric` / `boolean` (the API's
 * `_EDITABLE_DATA_TYPES`); `string` is kept as a defensive fallback so a value the
 * data model never actually produces still reads as something instead of the raw
 * backend word.
 */
export const SPEC_TYPE_LABEL: Record<string, string> = {
  enum: 'List',
  numeric: 'Number',
  boolean: 'Yes or no',
  string: 'Text',
};

/**
 * The pill word for a `data_type`, with the unit folded in for a numeric key
 * ("Number (mm)") - review L7, L8; AC-S3.2. Falls back to the stored value itself
 * for anything the registry does not create.
 */
export function specTypeLabel(dataType: string, unit?: string | null): string {
  const base = SPEC_TYPE_LABEL[dataType] ?? dataType;
  if (dataType === 'numeric' && unit) return `${base} (${unit})`;
  return base;
}

/** The three types a specification may be created as (AC-A.5). */
export const CREATABLE_SPEC_TYPE_OPTIONS = [
  { value: 'enum', label: SPEC_TYPE_LABEL.enum },
  { value: 'numeric', label: SPEC_TYPE_LABEL.numeric },
  { value: 'boolean', label: SPEC_TYPE_LABEL.boolean },
];
