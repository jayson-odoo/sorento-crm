/**
 * The plain word for a spec key's `data_type`, everywhere the type is shown (D10).
 *
 * The registry only ever creates `enum` / `numeric` / `boolean` (the API's
 * `_EDITABLE_DATA_TYPES`); `string` is kept as a defensive fallback so a value the
 * data model never actually produces still reads as something instead of the raw
 * backend word.
 */
export const SPEC_TYPE_LABEL: Record<string, string> = {
  enum: 'Choice',
  numeric: 'Number',
  boolean: 'Yes or no',
  string: 'Text',
};

/** The pill word for a `data_type`, falling back to the stored value itself. */
export function specTypeLabel(dataType: string): string {
  return SPEC_TYPE_LABEL[dataType] ?? dataType;
}

/** The three types a specification may be created as (AC-A.5). */
export const CREATABLE_SPEC_TYPE_OPTIONS = [
  { value: 'enum', label: SPEC_TYPE_LABEL.enum },
  { value: 'numeric', label: SPEC_TYPE_LABEL.numeric },
  { value: 'boolean', label: SPEC_TYPE_LABEL.boolean },
];
