import { describe, expect, it } from 'vitest';
import { seedWordsFor, valuePayload, wordPayload } from './vocabularyEdit';
import type { SpecRegistryKey } from '../types/productSpec.types';

/**
 * The vocabulary editor sends whole lists, not deltas. These are the two ways that went
 * wrong on screen, both of which looked like the save had simply not worked.
 */

/** `finish` as the API returns it: merged words, with suppression already applied. */
function finish(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'enum',
    unit: null,
    allowed_values: ['black', 'french_gold', 'matte_black'],
    excluded_values: [],
    user_values: ['matte_black'],
    suppressed_values: [],
    value_weights: {},
    derivation_rules: [],
    effective_rules: [],
    rules_are_default: true,
    synonyms: { black: ['black', 'matt black'], matte_black: ['matte black'] },
    applies_when: {},
    read_from: 'rules',
    rank_weight: 1,
    measured_coverage: null,
    source: 'seed',
    user_synonyms: {},
    suppressed_synonyms: { black: ['matte black'] },
    match_tolerance: 0,
    match_decay: 0,
    is_active: true,
    ...overrides,
  };
}

describe('taking a shipped word away', () => {
  it('counts an already-suppressed word as shipped', () => {
    // `synonyms.black` no longer lists "matte black" - it is suppressed. Reading the
    // seed list off `synonyms` alone would miss it, which is the whole bug.
    expect(seedWordsFor(finish(), 'black')).toEqual(['black', 'matt black', 'matte black']);
  });

  it('keeps an earlier suppression when a second word is removed', () => {
    const key = finish();

    const payload = wordPayload(key, {
      // "matt black" has just been taken out of the box; "matte black" went last time.
      words: { black: ['black'] },
      dropped: { black: ['matte black', 'matt black'] },
    });

    expect(payload.suppressed_synonyms.black.sort()).toEqual(['matt black', 'matte black']);
  });

  it('puts a word back when it is typed in again', () => {
    const key = finish();

    const payload = wordPayload(key, {
      words: { black: ['black', 'matt black', 'matte black'] },
      dropped: { black: ['matte black'] },
    });

    expect(payload.suppressed_synonyms.black).toBeUndefined();
    expect(payload.user_synonyms.black).toBeUndefined();
  });

  it('records a word nobody shipped as staff’s own', () => {
    const payload = wordPayload(finish(), {
      words: { black: ['black', 'matt black', 'jet black'] },
      dropped: {},
    });

    expect(payload.user_synonyms.black).toEqual(['jet black']);
  });
});

describe('adding and removing values', () => {
  it('keeps a value staff added earlier when another is added', () => {
    // The bug: `user_values` was filtered against `allowed_values`, which already
    // contains matte_black once saved - so adding "blue" dropped matte_black and it
    // vanished from the screen.
    const payload = valuePayload(finish(), ['black', 'french_gold', 'matte_black', 'blue'], []);

    expect(payload.user_values).toEqual(['matte_black', 'blue']);
  });

  it('suppresses a shipped value rather than deleting it', () => {
    const payload = valuePayload(finish(), ['black', 'matte_black'], ['french_gold']);

    expect(payload.suppressed_values).toEqual(['french_gold']);
    expect(payload.user_values).toEqual(['matte_black']);
  });

  it('treats a restored value as live again', () => {
    const key = finish({
      allowed_values: ['black', 'matte_black'],
      suppressed_values: ['french_gold'],
    });

    const payload = valuePayload(key, ['black', 'matte_black', 'french_gold'], []);

    expect(payload.suppressed_values).toEqual([]);
    expect(payload.user_values).toEqual(['matte_black']);
  });
});
