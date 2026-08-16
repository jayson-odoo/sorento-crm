/**
 * The client-side near-duplicate check - AC-A.11's courtesy half.
 *
 * The server runs the same comparison and is what actually decides (D11). This exists
 * so the common case - the word is already there under another spelling - never costs a
 * round trip, and these tests pin it to the SAME normalisation the backend uses
 * (`product_spec_registry.normalise_vocabulary`). Two normalisations that disagree
 * would show the user "Add brushed brass to Finish" and then have the server refuse it,
 * which is worse than not offering at all.
 */
import { describe, expect, it } from 'vitest';
import { findVocabularyMatch, normaliseVocabulary } from './specVocabulary';

describe('normalisation', () => {
  it.each([
    ['Brushed Brass', 'brushed brass'],
    ['brushed_brass', 'brushed brass'],
    ['  BRUSHED-BRASS  ', 'brushed brass'],
    ['Matt/Black', 'matt black'],
    ['finish!', 'finish'],
  ])('folds %s to %s', (raw, expected) => {
    expect(normaliseVocabulary(raw)).toBe(expected);
  });

  it('folds an empty or absent word to nothing', () => {
    expect(normaliseVocabulary('')).toBe('');
    expect(normaliseVocabulary('   ')).toBe('');
  });
});

describe('matching', () => {
  const values = ['chrome', 'matt_black', 'brushed_nickel'];
  const synonyms = { matt_black: ['matte black'], chrome: ['polished chrome'] };

  it('finds a value under a different spelling', () => {
    expect(findVocabularyMatch('Matt Black', values, synonyms)).toEqual({
      value: 'matt_black',
      viaSynonym: false,
    });
  });

  it('finds a value through one of its synonyms', () => {
    // `matte black` is a WORD for `matt_black`. Added as a value of its own it would
    // create one nothing can ever match.
    expect(findVocabularyMatch('matte black', values, synonyms)).toEqual({
      value: 'matt_black',
      viaSynonym: true,
      synonym: 'matte black',
    });
  });

  it('reports nothing for a genuinely new word', () => {
    expect(findVocabularyMatch('brushed brass', values, synonyms)).toBeNull();
  });

  it('reports nothing for an empty word rather than matching everything', () => {
    expect(findVocabularyMatch('   ', values, synonyms)).toBeNull();
  });

  it('works with no synonyms at all', () => {
    expect(findVocabularyMatch('CHROME', values)).toEqual({ value: 'chrome', viaSynonym: false });
  });

  it('prefers the value over a synonym when both would match', () => {
    const match = findVocabularyMatch('chrome', ['chrome'], { other: ['chrome'] });
    expect(match).toEqual({ value: 'chrome', viaSynonym: false });
  });
});
