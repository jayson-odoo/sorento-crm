/**
 * FILTER-MULTISELECT: a dropdown filter holds several values, OR-ed within the filter.
 *
 * A list's filter map (and the URL it is written to) is `Record<string, string>`, so the values ride
 * one param comma-joined (`status=draft,submitted`). The backend reads that, a repeated param and a
 * lone value alike (`app/utils/multi_value.py`), so a link from before a filter went multi still works.
 */

/** The distinct non-blank values of one filter param; `[]` when absent (no filter). */
export function splitMulti(raw: string | null | undefined): string[] {
  const out: string[] = [];
  for (const part of (raw ?? '').split(',')) {
    const value = part.trim();
    if (value && !out.includes(value)) out.push(value);
  }
  return out;
}

/** The param value for `values`; `''` when none is chosen, so the caller leaves the param out. */
export function joinMulti(values: readonly string[]): string {
  return splitMulti(values.join(',')).join(',');
}

/** "Draft, Submitted +2": the first `shown` labels and a count of the rest. */
export function multiValueSummary(labels: readonly string[], shown = 2): string {
  const head = labels.slice(0, shown).join(', ');
  const rest = labels.length - shown;
  return rest > 0 ? `${head} +${rest}` : head;
}

/** A filter chip naming several values: "Status: Draft, Submitted +2". */
export function multiChipLabel(title: string, labels: readonly string[], shown = 2): string {
  return `${title}: ${multiValueSummary(labels, shown)}`;
}

/**
 * The labels of a multi-select's chosen options for a trigger whose values are ids. The
 * component renders a value it holds no option for as a bare chip whose label IS the value, so
 * an id would show; this names it with a neutral word instead (the way the chips already do).
 * Only for filters whose values are ids: where a value is its own label, do not use it.
 */
export function idFilterLabels(
  chosen: readonly { value: string; label: string }[],
  unknown = 'Selected',
): string[] {
  return chosen.map((o) => (o.label === o.value ? unknown : o.label));
}

/**
 * The values of a FREE-TEXT filter read from a link: an item is split on commas only when it is a
 * legacy comma-joined list of plain values ("Tap,Basin"); an item with a comma followed by a space
 * ("Sink, Undermount") is one value. Same rule as the backend's `multi_text`. Free-text filters
 * write one repeated param per value, so this only matters for an older link.
 */
export function splitText(raws: readonly string[]): string[] {
  const out: string[] = [];
  for (const raw of raws) {
    const parts = raw.includes(', ') ? [raw] : raw.split(',');
    for (const part of parts) {
      const value = part.trim();
      if (value && !out.includes(value)) out.push(value);
    }
  }
  return out;
}
