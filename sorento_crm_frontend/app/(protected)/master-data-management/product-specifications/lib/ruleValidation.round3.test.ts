/**
 * Review round 3 (PR #1302), the client half of S-R2 and the four N-R1 differences:
 * the shared rule check says what `validate_rules` says, in the same order.
 */
import { describe, it, expect } from 'vitest';
import { builderProblem, ruleChoices, ruleMessage } from './ruleValidation';
import type { SpecRuleBuilder } from '../types/productSpec.types';

const words = (list: string[], extra: Partial<SpecRuleBuilder> = {}): SpecRuleBuilder =>
  ({ kind: 'words', words: list, value: 'round', ...extra }) as SpecRuleBuilder;
const code = (texts: string[], value = 'round'): SpecRuleBuilder =>
  ({ kind: 'code', code_match: 'contains', texts, value }) as SpecRuleBuilder;

const NO_LETTER = 'each word needs a letter or a number.';

describe('S-R2 - a word to find, or a code text, needs a letter or a number', () => {
  it.each([
    [words(['&'])],
    [words(['+'])],
    [words(['GOLD', ','])],
    [words(['( ... /'])],
    [code(['&'])],
    [code(['/'])],
  ])('%j is refused', (builder) => {
    expect(builderProblem(builder)).toBe(NO_LETTER);
  });

  it('punctuation stays allowed next to a number and in Skip after', () => {
    expect(builderProblem({ kind: 'number', after: ['('], before: ['MM'] })).toBeNull();
    expect(builderProblem({ kind: 'number', before: ['MM'], skip_after: ['/'] })).toBeNull();
    expect(builderProblem(words(['BLACK'], { skip_after: ['&'] } as Partial<SpecRuleBuilder>))).toBeNull();
  });
});

describe('N-R1 - the client check is the server check', () => {
  it('a code text with two "..." is not a phrase, so it is not counted for "..."', () => {
    expect(builderProblem(code(['SRT ... A ... B']))).toBeNull();
  });

  it('the length is measured trimmed, as the server strips', () => {
    expect(builderProblem(words([`  ${'X'.repeat(60)}  `]))).toBeNull();
  });

  it('a word breaking two limits gets the server first message (length before "...")', () => {
    const long = `${'A'.repeat(30)} ... ${'B'.repeat(15)} ... ${'C'.repeat(15)}`;
    expect(builderProblem(words([long]))).toBe('keep each word to 60 characters or fewer.');
  });

  it('a list problem comes before an empty list, as the server checks limits first', () => {
    const builder = words([], { skip_after: ['A ... B ... C'] } as Partial<SpecRuleBuilder>);
    expect(builderProblem(builder)).toBe('use at most one ... in a phrase.');
  });

  it('a value the specification does not have is refused in the server wording', () => {
    const choices = ruleChoices({ data_type: 'enum', allowed_values: ['round'], suppressed_values: ['oval'] });
    expect(builderProblem(words(['SQUARE'], { value: 'square' } as Partial<SpecRuleBuilder>), choices)).toBe(
      'sets a value this specification does not have. Pick one of its choices, or add the choice first.',
    );
    expect(builderProblem(words(['OVAL'], { value: 'oval' } as Partial<SpecRuleBuilder>), choices)).toBeNull();
    expect(builderProblem(code(['-SQ'], 'square'), choices)).not.toBeNull();
    expect(
      ruleMessage(builderProblem(words(['SQUARE'], { value: 'square' } as Partial<SpecRuleBuilder>), choices)!, 3),
    ).toBe(
      'Rule 3 sets a value this specification does not have. Pick one of its choices, or add the choice first.',
    );
  });

  it('a spec with no closed list takes any value', () => {
    expect(ruleChoices({ data_type: 'text', allowed_values: [], suppressed_values: [] })).toBeNull();
    expect(builderProblem(words(['X'], { value: 'anything' } as Partial<SpecRuleBuilder>), null)).toBeNull();
  });
});
