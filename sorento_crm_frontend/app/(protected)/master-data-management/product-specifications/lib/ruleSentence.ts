import type { SpecDerivationRule } from '../types/productSpec.types';

/**
 * A derivation rule as a sentence a merchandiser can check.
 *
 * The editor showed rules as raw fields: a dropdown reading "Pattern, capture a number"
 * next to `\bSINGLE\s+BOWLS?\b`. That is the engine's own notation, and it asks the
 * person least equipped to read regular expressions to verify the thing the whole
 * catalogue depends on. The rule is unchanged — only how it is read.
 */

/**
 * A regular expression as the words it actually looks for.
 *
 * Deliberately partial: it undoes the handful of constructs the shipped rules use
 * (\b, \s+, ?, character classes for digits) and gives up on anything else rather than
 * mistranslating it. `null` means "show the pattern as it is" — an honest fallback,
 * where a wrong plain-English reading of a live rule would not be.
 */
export function plainPattern(pattern: string): string | null {
  if (!pattern) return null;
  // Anything with alternation, lookaround, or nested groups is beyond this: those
  // rules are genuinely for someone who writes regular expressions.
  if (/[|()[\]{}^$]/.test(pattern.replace(/\\[dsw]/gi, ''))) return null;

  const plain = pattern
    .replace(/\\b|\\m|\\M/g, '') // word boundaries: implied by "whole words"
    .replace(/\\s\+|\\s\*/g, ' ') // any gap: just a space
    .replace(/\\[.\-/]/g, (m) => m[1]) // escaped punctuation
    .replace(/\\d\+?/g, 'a number')
    .trim();

  // A trailing optional letter ("BOWLS?") reads as the plural it is.
  const readable = plain.replace(/([A-Za-z])\?/g, '($1)');
  return /^[A-Za-z0-9 .\-/()]+$/.test(readable) ? readable : null;
}

/** What a rule does, in one sentence. */
export function ruleSentence(rule: SpecDerivationRule, label: string): string {
  const shown = plainPattern(rule.pattern) ?? rule.pattern;
  const where =
    rule.source === 'flyer'
      ? 'the flyer card'
      : rule.source === 'description'
        ? 'the description'
        : 'the description or flyer';
  const answer =
    rule.value === true
      ? 'yes'
      : rule.value === false
        ? 'no'
        : rule.value === undefined || rule.value === ''
          ? 'the number it finds'
          : String(rule.value);

  switch (rule.match) {
    case 'contains':
      return `If ${where} contains “${shown}”, ${label} is ${answer}.`;
    case 'ends_with':
      return `If ${where} ends with “${shown}”, ${label} is ${answer}.`;
    case 'present':
      return `If “${shown}” appears in ${where} at all, ${label} is yes.`;
    case 'regex':
      // A pattern rule does one of two jobs and they read very differently. With a
      // `value` it is a condition like any other; only a `capture` pulls a number out
      // of the text. Saying "read the number out of SINGLE BOWL(S)" about a rule that
      // simply answers 1 describes something that does not happen.
      return rule.capture !== undefined && rule.value === undefined
        ? `Read ${label} out of ${where} where it says “${shown}”.`
        : `If ${where} matches “${shown}”, ${label} is ${answer}.`;
    case 'code_contains':
      return `If the product code contains “${shown}”, ${label} is ${answer}.`;
    case 'code_starts_with':
      return `If the product code starts with “${shown}”, ${label} is ${answer}.`;
    case 'code_suffix':
      return `If the product code ends in “${shown}”, ${label} is ${answer}.`;
    case 'product_column':
      return `${label} is taken straight from the product's own ${shown || 'record'}.`;
    default:
      return `${label}: ${rule.match} “${shown}”.`;
  }
}
