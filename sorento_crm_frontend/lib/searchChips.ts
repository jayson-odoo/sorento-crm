/** Search chips (SEARCH-CHIPS): pasted text to chip values, and adding chips under the cap. */

/** The backend's limit on values per search (`app/utils/multi_value.py`). */
export const MAX_SEARCH_CHIPS = 200;

/**
 * Commas and new lines always split. Spaces split only when every piece has a digit
 * (document numbers), so a name like "Acme Trading" stays one value.
 */
export function splitPastedSearch(text: string): string[] {
  const pieces = text
    .split(/[,\r\n]+/)
    .map((piece) => piece.trim())
    .filter(Boolean);
  if (pieces.length !== 1) return pieces;
  const words = pieces[0].split(/\s+/);
  return words.length > 1 && words.every((word) => /\d/.test(word)) ? words : pieces;
}

/** Appends trimmed, non-blank values not already present (case-insensitive), up to `cap`. */
export function addSearchChips(
  existing: string[],
  incoming: string[],
  cap: number = MAX_SEARCH_CHIPS,
): { chips: string[]; capped: boolean } {
  const chips = [...existing];
  const seen = new Set(existing.map((chip) => chip.toLowerCase()));
  let capped = false;
  for (const raw of incoming) {
    const value = raw.trim();
    if (!value || seen.has(value.toLowerCase())) continue;
    if (chips.length >= cap) {
      capped = true;
      break;
    }
    chips.push(value);
    seen.add(value.toLowerCase());
  }
  return { chips, capped };
}
