/**
 * "Is this word already in the vocabulary under another spelling?"
 *
 * Run before offering to create anything - a value, or a whole key. The catalogue's
 * vocabulary is the contract the ranker and the n8n parser both hold, so "Brushed
 * Brass" arriving beside "brushed brass" does not add a word, it splits one: half the
 * products answer a customer's question and half do not, and nothing on any screen says
 * why.
 *
 * This is a LATENCY COURTESY and never the guard (D11). The same comparison runs on the
 * server, which is what actually decides; running it here only means the common case -
 * the word is already there - never costs a round trip.
 */

/** Case, spacing, punctuation and separators all folded away. */
export function normaliseVocabulary(text: string): string {
  return String(text ?? '')
    .trim()
    .toLowerCase()
    .replace(/[\s_\-/]+/g, ' ')
    .replace(/[^a-z0-9 ]/g, '')
    .trim();
}

export interface VocabularyMatch {
  /** The stored value the typed word collides with. */
  value: string;
  /** True when the collision is on a synonym rather than on the value itself. */
  viaSynonym: boolean;
  /** The synonym that matched, when it was one. */
  synonym?: string;
}

/**
 * The existing value a typed word already means, or null when it genuinely is new.
 *
 * Synonyms are checked as well as values, because that is where the near-duplicates
 * actually are: `matte black` ships as a WORD for `black`, so adding it as a value of
 * its own would create a value nothing can ever match.
 */
export function findVocabularyMatch(
  typed: string,
  values: string[],
  synonyms: Record<string, string[]> = {},
): VocabularyMatch | null {
  const needle = normaliseVocabulary(typed);
  if (!needle) return null;

  for (const value of values) {
    if (normaliseVocabulary(value) === needle) return { value, viaSynonym: false };
  }
  for (const [value, words] of Object.entries(synonyms)) {
    for (const word of words ?? []) {
      if (normaliseVocabulary(word) === needle) {
        return { value, viaSynonym: true, synonym: word };
      }
    }
  }
  return null;
}
