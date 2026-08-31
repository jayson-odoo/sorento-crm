import type {
  SpecDerivationRule,
  SpecRuleBuilder,
} from '../types/productSpec.types';

/**
 * A derivation rule as a sentence a merchandiser can check.
 *
 * The editor showed rules as raw fields: a dropdown reading "Pattern, capture a number"
 * next to `\bSINGLE\s+BOWLS?\b`. That is the engine's own notation, and it asks the
 * person least equipped to read regular expressions to verify the thing the whole
 * catalogue depends on. The rule is unchanged - only how it is read.
 */

/**
 * A regular expression as the words it actually looks for.
 *
 * Deliberately partial: it undoes the handful of constructs the shipped rules use
 * (\b, \s+, ?, character classes for digits) and gives up on anything else rather than
 * mistranslating it. `null` means "show the pattern as it is" - an honest fallback,
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

/**
 * The sentence-builder layer.
 *
 * `ruleSentence` above reads an engine rule (match/pattern/capture/value) back as
 * English - the one-way translation a pattern row still needs. A `builder` row runs the
 * other direction: the kind menu picks a sentence FIRST, blanks get filled in, and
 * `compileBuilder` turns that into the same engine fields. One compiler, so the
 * pattern Advanced shows for a builder row is exactly what saving it sends.
 *
 * Deliberately partial the same way `plainPattern` is: `from_field` and `name_head`
 * read the product record or run a multi-step text transform the engine does natively,
 * not a single regex, so their compiled `pattern` here is for the Advanced pane only -
 * illustrative, not what S2's engine will actually execute for those two kinds.
 */

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Mirrors `_DIM_RE` in `product_spec_derivation.py`: 2-4 numbers separated by x/X/*,
 *  each optionally labelled (L/W/H/D) and optionally carrying its own "mm". */
const DIM_PART = '(?:[LWHDlwhd]\\s*)?(\\d+(?:\\.\\d+)?)\\s*(?:MM|mm)?';
export const DIM_TRIPLE_PATTERN =
  `${DIM_PART}\\s*[xX*]\\s*${DIM_PART}` +
  `(?:\\s*[xX*]\\s*${DIM_PART})?` +
  `(?:\\s*[xX*]\\s*${DIM_PART})?`;

/** Illustrative only (see banner above) - the real engine strips the parenthetical,
 *  the "WITH"/"C/W"/"FOR"/"W/" tail and the dimensions rather than matching one regex. */
const NAME_HEAD_PATTERN =
  '^(.*?)(?:\\(|\\bWITH\\b|\\bC/W\\b|\\bFOR\\b|\\bW/\\b|$)';

/** builder -> the engine fields it compiles to. What gets saved and what try-it runs. */
export function compileBuilder(
  builder: SpecRuleBuilder,
): Pick<SpecDerivationRule, 'match' | 'pattern' | 'capture' | 'value'> {
  const word = escapeRegex((builder.word ?? '').toUpperCase());
  switch (builder.kind) {
    case 'number_after':
      return {
        match: 'regex',
        pattern: `\\b${word}\\s*(\\d+(?:\\.\\d+)?)`,
        capture: 1,
      };
    case 'number_before':
      return {
        match: 'regex',
        pattern: `(?<![A-Z0-9X])(\\d+(?:\\.\\d+)?)\\s*${word}\\b`,
        capture: 1,
      };
    case 'number_between': {
      const from = escapeRegex((builder.from ?? '').toUpperCase());
      const to = escapeRegex((builder.to ?? '').toUpperCase());
      return {
        match: 'regex',
        pattern: `${from}\\s*[:,]?\\s*(\\d+(?:\\.\\d+)?)\\s*${to}`,
        capture: 1,
      };
    }
    case 'text_contains':
      return {
        match: 'contains',
        pattern: builder.word ?? '',
        value: builder.value ?? '',
      };
    case 'text_ends_with':
      return {
        match: 'ends_with',
        pattern: builder.word ?? '',
        value: builder.value ?? '',
      };
    case 'word_present':
      return { match: 'present', pattern: builder.word ?? '', value: true };
    case 'code_contains':
      return {
        match: 'code_contains',
        pattern: builder.word ?? '',
        value: builder.value ?? '',
      };
    case 'code_starts_with':
      return {
        match: 'code_starts_with',
        pattern: builder.word ?? '',
        value: builder.value ?? '',
      };
    case 'code_ends_with':
      // The engine's kind for this is `code_suffix` - it predates the sentence menu.
      return {
        match: 'code_suffix',
        pattern: builder.word ?? '',
        value: builder.value ?? '',
      };
    case 'from_field':
      return { match: 'from_field', pattern: builder.field || 'category' };
    case 'size_triple':
      return {
        match: 'regex',
        pattern: DIM_TRIPLE_PATTERN,
        capture: builder.position ?? 1,
      };
    case 'name_head':
      return { match: 'regex', pattern: NAME_HEAD_PATTERN, capture: 1 };
    default:
      return { match: 'regex', pattern: '' };
  }
}

function ordinal(n: number): string {
  const suffixes = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${suffixes[(v - 20) % 10] ?? suffixes[v] ?? suffixes[0]}`;
}

function fromFieldSentence(field?: string): string {
  if (!field) return "From the product's own field";
  if (field === 'category') return "From the product's category";
  if (field === 'brand') return "From the product's brand field";
  if (field.startsWith('column:'))
    return `From the product's \`${field.slice(7)}\` column`;
  return `From the product's ${field}`;
}

/** A builder as the sentence it reads, blanks filled in. What the row shows. */
export function builderSentence(builder: SpecRuleBuilder): string {
  const word = builder.word || '...';
  const value =
    builder.value === undefined || builder.value === ''
      ? '...'
      : String(builder.value);
  switch (builder.kind) {
    case 'number_after':
      return `Number after the word \`${word}\``;
    case 'number_before':
      return `Number before \`${word}\``;
    case 'number_between':
      return `Number between \`${builder.from || '...'}\` and \`${builder.to || '...'}\``;
    case 'text_contains':
      return `Text contains \`${word}\` → ${value}`;
    case 'text_ends_with':
      return `Text ends with \`${word}\` → ${value}`;
    case 'word_present':
      return `Word \`${word}\` is present → yes`;
    case 'code_contains':
      return `Code contains \`${word}\` → ${value}`;
    case 'code_starts_with':
      return `Code starts with \`${word}\` → ${value}`;
    case 'code_ends_with':
      return `Code ends with \`${word}\` → ${value}`;
    case 'from_field':
      return fromFieldSentence(builder.field);
    case 'size_triple':
      return `Size from \`L x W x H\`, take the ${ordinal(builder.position ?? 1)} number`;
    case 'name_head':
      return 'Product name head (text before the first bracket or WITH)';
    default:
      return 'Unrecognised rule';
  }
}
