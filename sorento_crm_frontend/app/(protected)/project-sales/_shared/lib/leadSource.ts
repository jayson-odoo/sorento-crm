/** A stored code ("tender_notice") as a readable phrase. No dictionary to drift. */
export function labelise(value?: string | null): string | null {
  if (!value) return null;
  const words = value.replace(/[_-]+/g, ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : null;
}

/**
 * A lead source's label from the editable `project_lead_source` lookup set, else the code
 * made readable (a value since removed from the set still reads as words, not as a key).
 */
export function leadSourceLabel(
  options: { value: string; label: string }[] | unknown,
  value?: string | null,
): string | null {
  const list = Array.isArray(options) ? (options as { value: string; label: string }[]) : [];
  return list.find((o) => o.value === value)?.label ?? labelise(value);
}
