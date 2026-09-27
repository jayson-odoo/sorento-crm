import type { SpecRegistryKey, SpecRuleBuilder, SpecRuleKind } from '../types/productSpec.types';

/**
 * What the server refuses a rule for, checked the same way before it gets there
 * (S-11, review round 2) - ONE function, used by the rule modal and by the rules
 * grid's in-place edit, so the two cannot drift from each other or from
 * `validate_rules` (`product_spec_rules.py`). The wording is the server's own; each
 * message starts lower case so `ruleMessage` can put "Rule n: " in front, or
 * capitalise it where the rule has no number yet. The checks run in the server's
 * order (`_check_limits`, then the kind's own parts), so a rule breaking two limits
 * gets the same first message on both sides (N-R1, review round 3).
 */
export const MAX_WORDS_PER_LIST = 20;
export const MAX_WORD_LENGTH = 60;

/** What a list of words is for. `find`: a words rule's words; `code`: a code rule's
 *  texts (both need a letter or a number, S-R2); `phrase`: skip after, before and
 *  after, where punctuation such as "(" still says something. A code text is not a
 *  phrase, so its "..." is not counted (the server's `_PHRASE_LISTS`). */
export type WordsListRole = 'find' | 'phrase' | 'code';

const ONLY_DOTS_AND_DASHES = /^[\s.\-]*$/;
const LETTER_OR_NUMBER = /[\p{L}\p{N}]/u;

/** A word has to be more than dots and dashes, the way the server reads it: split
 *  on "...", it needs a non-blank part, and no non-blank part may be only spaces,
 *  dots and hyphens. "(" and "/" are real words next to a number ("the number
 *  between ( and MM"); "...", "-", "--", " . " and "GOLD ... -" are not. */
const isMoreThanDotsAndDashes = (word: string) => {
  const parts = word.split('...').filter((part) => part.trim() !== '');
  return parts.length > 0 && parts.every((part) => !ONLY_DOTS_AND_DASHES.test(part));
};

/** Null while a list of words is within every limit; the problem otherwise. */
export function wordsListProblem(
  words: readonly string[],
  role: WordsListRole = 'phrase',
): string | null {
  if (words.length > MAX_WORDS_PER_LIST) return `use at most ${MAX_WORDS_PER_LIST} words in a list.`;
  for (const word of words) {
    if (word.trim() === '') continue;
    if (!isMoreThanDotsAndDashes(word)) return 'each word needs more than dots and dashes.';
    if (role !== 'phrase' && !LETTER_OR_NUMBER.test(word)) {
      return 'each word needs a letter or a number.';
    }
    if (word.trim().length > MAX_WORD_LENGTH) {
      return `keep each word to ${MAX_WORD_LENGTH} characters or fewer.`;
    }
    if (role !== 'code' && word.split('...').length - 1 > 1) return 'use at most one ... in a phrase.';
  }
  return null;
}

/** What an empty word list is called, per kind. Null for a kind with no list. */
export function emptyListProblem(kind: SpecRuleKind): string | null {
  if (kind === 'words') return 'add at least one word to find.';
  if (kind === 'number') return 'add at least one word next to the number.';
  if (kind === 'code') return 'add at least one piece of code to find.';
  return null;
}

export const MISSING_VALUE_PROBLEM = 'pick the value it sets.';
export const ONE_GAP_PHRASE_PROBLEM = 'use ... in one phrase only.';
export const UNKNOWN_VALUE_PROBLEM =
  'sets a value this specification does not have. Pick one of its choices, or add the choice first.';

/** A rule may hold "..." in ONE phrase only, across its phrase lists (code texts are
 *  not phrases and are not counted). */
export function gapPhrasesProblem(lists: readonly (readonly string[])[]): string | null {
  const withGap = lists.flat().filter((word) => word.includes('...')).length;
  return withGap > 1 ? ONE_GAP_PHRASE_PROBLEM : null;
}

type RoledList = readonly [readonly string[], WordsListRole];

/** Every list of words a builder holds, in the server's order (`_WORD_LISTS`:
 *  words, skip after, before, after, texts). */
function listsOf(builder: SpecRuleBuilder): RoledList[] {
  switch (builder.kind) {
    case 'words':
      return [
        [builder.words, 'find'],
        [builder.skip_after ?? [], 'phrase'],
      ];
    case 'number':
      return [
        [builder.skip_after ?? [], 'phrase'],
        [builder.before ?? [], 'phrase'],
        [builder.after ?? [], 'phrase'],
      ];
    case 'code':
      return [[builder.texts ?? [], 'code']];
    default:
      return [];
  }
}

const isMissing = (value: unknown) =>
  value === null || value === undefined || (typeof value === 'string' && value.trim() === '');

/** The limits every list must keep, then the one-gap-phrase rule across the phrase
 *  lists. */
export function listsProblem(lists: readonly RoledList[]): string | null {
  for (const [list, role] of lists) {
    const problem = wordsListProblem(list, role);
    if (problem) return problem;
  }
  return gapPhrasesProblem(lists.filter(([, role]) => role !== 'code').map(([list]) => list));
}

/** The value a words or code rule sets: missing, or (for a closed list of choices)
 *  one the specification does not have. `choices` is null when any value goes. */
function valueProblem(value: unknown, choices: readonly string[] | null): string | null {
  if (isMissing(value)) return MISSING_VALUE_PROBLEM;
  if (choices && choices.length > 0 && !choices.includes(String(value).trim())) {
    return UNKNOWN_VALUE_PROBLEM;
  }
  return null;
}

/** The closed list a rule's value must come from, the server's `_rule_allowed_values`:
 *  an enum's choices with the taken-away ones included. Null when any value goes. */
export function ruleChoices(
  spec: Pick<SpecRegistryKey, 'data_type' | 'allowed_values' | 'suppressed_values'>,
): string[] | null {
  if (spec.data_type !== 'enum') return null;
  return [...(spec.allowed_values ?? []), ...(spec.suppressed_values ?? [])].map(String);
}

/** Every problem the server would name for one rule, first one only. `choices` is the
 *  closed list a words or code rule's value must come from (an enum's choices, the
 *  taken-away ones included, as the server's `_rule_allowed_values`); omit it when
 *  any value goes. */
export function builderProblem(
  builder: SpecRuleBuilder,
  choices: readonly string[] | null = null,
): string | null {
  const limits = listsProblem(listsOf(builder));
  if (limits) return limits;
  switch (builder.kind) {
    case 'words':
      if (builder.words.length === 0) return emptyListProblem('words');
      return valueProblem(builder.value, choices);
    case 'number':
      if ((builder.before?.length ?? 0) === 0 && (builder.after?.length ?? 0) === 0) {
        return emptyListProblem('number');
      }
      return null;
    case 'code':
      if ((builder.texts ?? []).length === 0) return emptyListProblem('code');
      return valueProblem(builder.value, choices);
    default:
      return null;
  }
}

/** "Rule 3: pick the value it sets." for a numbered rule, "Pick the value it sets."
 *  for one that has no number yet (a rule being added). The unknown-value refusal
 *  reads as a sentence about the rule, the server's "Rule 3 sets a value ...". */
export function ruleMessage(problem: string, ruleNumber?: number | null): string {
  if (problem === UNKNOWN_VALUE_PROBLEM) {
    return ruleNumber ? `Rule ${ruleNumber} ${problem}` : `This rule ${problem}`;
  }
  if (ruleNumber) return `Rule ${ruleNumber}: ${problem}`;
  return problem.charAt(0).toUpperCase() + problem.slice(1);
}
