import type { SpecRuleBuilder, SpecRuleKind } from '../types/productSpec.types';

/**
 * What the server refuses a rule for, checked the same way before it gets there
 * (S-11, review round 2) - ONE function, used by the rule modal and by the rules
 * grid's in-place edit, so the two cannot drift from each other or from
 * `validate_rules` (`product_spec_rules.py`). The wording is the server's own; each
 * message starts lower case so `ruleMessage` can put "Rule n: " in front, or
 * capitalise it where the rule has no number yet.
 */
export const MAX_WORDS_PER_LIST = 20;
export const MAX_WORD_LENGTH = 60;

const ONLY_DOTS_AND_DASHES = /^[\s.\-]*$/;

/** A word has to be more than dots and dashes, the way the server reads it: split
 *  on "...", it needs a non-blank part, and no non-blank part may be only spaces,
 *  dots and hyphens. "(" and "/" are real words ("the number between ( and MM");
 *  "...", "-", "--", " . " and "GOLD ... -" are not. */
const isMoreThanDotsAndDashes = (word: string) => {
  const parts = word.split('...').filter((part) => part.trim() !== '');
  return parts.length > 0 && parts.every((part) => !ONLY_DOTS_AND_DASHES.test(part));
};

/** Null while a list of words is within every limit; the problem otherwise. Applies
 *  to every list a rule holds - words, skip after, before, after, code text. */
export function wordsListProblem(words: readonly string[]): string | null {
  if (words.length > MAX_WORDS_PER_LIST) return `use at most ${MAX_WORDS_PER_LIST} words in a list.`;
  for (const word of words) {
    if (!isMoreThanDotsAndDashes(word)) return 'each word needs more than dots and dashes.';
    if (word.split('...').length - 1 > 1) return 'use at most one ... in a phrase.';
    if (word.length > MAX_WORD_LENGTH) {
      return `keep each word to ${MAX_WORD_LENGTH} characters or fewer.`;
    }
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

/** A rule may hold "..." in ONE phrase only, across every list it has. */
export function gapPhrasesProblem(lists: readonly (readonly string[])[]): string | null {
  const withGap = lists.flat().filter((word) => word.includes('...')).length;
  return withGap > 1 ? ONE_GAP_PHRASE_PROBLEM : null;
}

/** Every list of words a builder holds, whichever kind it is. */
function listsOf(builder: SpecRuleBuilder): string[][] {
  switch (builder.kind) {
    case 'words':
      return [builder.words, builder.skip_after ?? []];
    case 'number':
      return [builder.before ?? [], builder.after ?? [], builder.skip_after ?? []];
    case 'code':
      return [builder.texts];
    default:
      return [];
  }
}

const isMissing = (value: unknown) =>
  value === null || value === undefined || (typeof value === 'string' && value.trim() === '');

/** The limits every list must keep, then the one-gap-phrase rule across them. */
export function listsProblem(lists: readonly (readonly string[])[]): string | null {
  for (const list of lists) {
    const problem = wordsListProblem(list);
    if (problem) return problem;
  }
  return gapPhrasesProblem(lists);
}

/** Every problem the server would name for one rule, first one only. */
export function builderProblem(builder: SpecRuleBuilder): string | null {
  const lists = listsOf(builder);
  switch (builder.kind) {
    case 'words':
      if (builder.words.length === 0) return emptyListProblem('words');
      return listsProblem(lists) ?? (isMissing(builder.value) ? MISSING_VALUE_PROBLEM : null);
    case 'number':
      if ((builder.before?.length ?? 0) === 0 && (builder.after?.length ?? 0) === 0) {
        return emptyListProblem('number');
      }
      return listsProblem(lists);
    case 'code':
      if (builder.texts.length === 0) return emptyListProblem('code');
      return listsProblem(lists) ?? (isMissing(builder.value) ? MISSING_VALUE_PROBLEM : null);
    default:
      return null;
  }
}

/** "Rule 3: pick the value it sets." for a numbered rule, "Pick the value it sets."
 *  for one that has no number yet (a rule being added). */
export function ruleMessage(problem: string, ruleNumber?: number | null): string {
  if (ruleNumber) return `Rule ${ruleNumber}: ${problem}`;
  return problem.charAt(0).toUpperCase() + problem.slice(1);
}
