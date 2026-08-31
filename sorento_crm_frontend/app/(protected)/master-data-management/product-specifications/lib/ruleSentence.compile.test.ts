import { describe, expect, it } from 'vitest';
import { compileBuilder } from './ruleSentence';
import type { SpecRuleBuilder } from '../types/productSpec.types';

/**
 * Mirrors `_SENTENCES` in `sorento_crm_backend/tests/test_product_spec_derivation.py`,
 * row for row. `compile_builder` (server) and `compileBuilder` (here) are two
 * implementations of the same compiler - a rule the editor saves has to run on the
 * server exactly as it read on screen, and the server refuses a save where the two
 * disagree (`spec_rule_builder_mismatch`, AC-A.7). Nothing on the frontend guarded
 * that agreement before this file: a browser-only compiler bug would only ever be
 * caught by a save round-trip failing in the browser.
 */
const SENTENCES: [
  SpecRuleBuilder,
  Pick<
    ReturnType<typeof compileBuilder>,
    'match' | 'pattern' | 'capture' | 'value'
  >,
][] = [
  [
    { kind: 'number_after', word: 'L' },
    { match: 'regex', pattern: '\\bL\\s*(\\d+(?:\\.\\d+)?)', capture: 1 },
  ],
  [
    { kind: 'number_before', word: 'MM' },
    {
      match: 'regex',
      pattern: '(?<![A-Z0-9X])(\\d+(?:\\.\\d+)?)\\s*MM\\b',
      capture: 1,
    },
  ],
  [
    { kind: 'number_between', from: 'S-TRAP', to: 'MM' },
    {
      match: 'regex',
      pattern: 'S-TRAP\\s*[:,]?\\s*(\\d+(?:\\.\\d+)?)\\s*MM',
      capture: 1,
    },
  ],
  [
    { kind: 'text_contains', word: 'RIMLESS', value: true },
    { match: 'contains', pattern: 'RIMLESS', value: true },
  ],
  [
    { kind: 'text_ends_with', word: 'SQUATTING PAN', value: 'Squatting Pan' },
    { match: 'ends_with', pattern: 'SQUATTING PAN', value: 'Squatting Pan' },
  ],
  [
    { kind: 'word_present', word: 'THERMOSTATIC' },
    { match: 'present', pattern: 'THERMOSTATIC', value: true },
  ],
  [
    { kind: 'code_contains', word: 'SRTSC', value: 'Seat Cover' },
    { match: 'code_contains', pattern: 'SRTSC', value: 'Seat Cover' },
  ],
  [
    { kind: 'code_starts_with', word: 'SRT', value: 'Sorento' },
    { match: 'code_starts_with', pattern: 'SRT', value: 'Sorento' },
  ],
  [
    { kind: 'code_ends_with', word: 'UF', value: 'uf' },
    { match: 'code_suffix', pattern: 'UF', value: 'uf' },
  ],
  [
    { kind: 'from_field', field: 'brand' },
    { match: 'from_field', pattern: 'brand' },
  ],
  [
    { kind: 'size_triple', position: 2 },
    {
      match: 'regex',
      // NOT `DIM_TRIPLE_PATTERN` - both suites were self-referential, each
      // comparing its own compiler against its own engine regex, so a drift
      // between the two languages' patterns would pass on both sides (reviewer,
      // 31 Aug). Copied verbatim from Python's `_DIM_RE.pattern`
      // (`app/services/product_spec_derivation.py`), pinned on that side by
      // `tests/test_product_spec_derivation.py::_SENTENCES`'s own `size_triple`
      // row - a change to EITHER pattern that the other does not follow fails HERE.
      pattern:
        '(?:[LWHDlwhd]\\s*)?(\\d+(?:\\.\\d+)?)\\s*(?:MM|mm)?\\s*[xX*]\\s*(?:[LWHDlwhd]\\s*)?(\\d+(?:\\.\\d+)?)\\s*(?:MM|mm)?(?:\\s*[xX*]\\s*(?:[LWHDlwhd]\\s*)?(\\d+(?:\\.\\d+)?)\\s*(?:MM|mm)?)?(?:\\s*[xX*]\\s*(?:[LWHDlwhd]\\s*)?(\\d+(?:\\.\\d+)?)\\s*(?:MM|mm)?)?',
      capture: 2,
    },
  ],
  [{ kind: 'name_head' }, { match: 'name_head', pattern: 'class_tail' }],
];

describe('a sentence compiles to one engine rule, matching the server exactly', () => {
  it.each(SENTENCES)('%o', (builder, expected) => {
    const compiled = compileBuilder(builder);
    for (const [field, value] of Object.entries(expected)) {
      expect(compiled[field as keyof typeof compiled]).toEqual(value);
    }
  });
});
