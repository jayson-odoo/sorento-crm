/**
 * S-11 (review round 2) - the one shared check the rule modal and the rules grid
 * both call, in the server's own wording (`validate_rules`).
 */
import { describe, it, expect } from 'vitest';
import { builderProblem, ruleMessage } from './ruleValidation';
import type { SpecRuleBuilder } from '../types/productSpec.types';

const words = (list: string[], extra: Partial<SpecRuleBuilder> = {}): SpecRuleBuilder =>
  ({ kind: 'words', words: list, value: 'round', ...extra }) as SpecRuleBuilder;

describe('builderProblem - the server refusals, one function', () => {
  it.each([
    [words([]), 'add at least one word to find.'],
    [{ kind: 'number', before: [], after: [] } as SpecRuleBuilder, 'add at least one word next to the number.'],
    [{ kind: 'code', code_match: 'ends_with', texts: [], value: 'x' } as SpecRuleBuilder, 'add at least one piece of code to find.'],
    [words(['...']), 'each word needs more than dots and dashes.'],
    [words(['-']), 'each word needs more than dots and dashes.'],
    [words(['--']), 'each word needs more than dots and dashes.'],
    [words([' . ']), 'each word needs more than dots and dashes.'],
    [words(['GOLD ... -']), 'each word needs more than dots and dashes.'],
    [{ kind: 'code', code_match: 'contains', texts: ['-.-'], value: 'x' } as SpecRuleBuilder, 'each word needs more than dots and dashes.'],
    [words(['A ... B ... C']), 'use at most one ... in a phrase.'],
    [words(['X'.repeat(61)]), 'keep each word to 60 characters or fewer.'],
    [words(Array.from({ length: 21 }, (_, i) => `W${i}`)), 'use at most 20 words in a list.'],
    [words(['ROSE ... GOLD'], { skip_after: ['NOT ... EVER'] } as Partial<SpecRuleBuilder>), 'use ... in one phrase only.'],
    [words(['ROUND'], { value: '' } as Partial<SpecRuleBuilder>), 'pick the value it sets.'],
    [{ kind: 'code', code_match: 'ends_with', texts: ['-RG'], value: '' } as SpecRuleBuilder, 'pick the value it sets.'],
  ])('%j -> %s', (builder, problem) => {
    expect(builderProblem(builder)).toBe(problem);
  });

  it('"(" and "/" are real words next to a number: the number between ( and MM is a real rule', () => {
    expect(builderProblem({ kind: 'number', after: ['('], before: ['MM'] })).toBeNull();
    expect(builderProblem({ kind: 'number', after: ['/'], before: ['MM'] })).toBeNull();
    // A word to find, or a code text, needs a letter or a number (S-R2, review round 3).
    expect(builderProblem(words(['/']))).toBe('each word needs a letter or a number.');
    expect(builderProblem({ kind: 'code', code_match: 'contains', texts: ['/'], value: 'x' })).toBe(
      'each word needs a letter or a number.',
    );
  });

  it('a rule within every limit has no problem', () => {
    expect(builderProblem(words(['ROSE ... GOLD', 'ROSE GOLD']))).toBeNull();
    expect(builderProblem({ kind: 'size', pick: 1 })).toBeNull();
  });
});

describe('ruleMessage - numbered or not, the same text', () => {
  it('prefixes "Rule n: " for a numbered rule and capitalises otherwise', () => {
    expect(ruleMessage('pick the value it sets.', 3)).toBe('Rule 3: pick the value it sets.');
    expect(ruleMessage('pick the value it sets.')).toBe('Pick the value it sets.');
  });
});
