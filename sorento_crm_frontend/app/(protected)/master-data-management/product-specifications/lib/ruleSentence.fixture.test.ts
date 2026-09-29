import { describe, expect, it } from 'vitest';
import { compileBuilder } from './ruleSentence';
import type { SpecRuleBuilder, SpecCompiledRule } from '../types/productSpec.types';
import fixtures from './__fixtures__/rule-builders.json';

/**
 * AC-S1.1: `compile_builder` (server, `app/services/product_spec_rules.py`) and
 * `compileBuilder` (here) are two implementations of the same compiler - a rule
 * the screen saves has to run on the server exactly as it read on screen, and the
 * server refuses a save where the two disagree (contract section 3). This fixture
 * is the shared pin: every shipped rule, converted to its builder, with the
 * SERVER's own compiled result recorded alongside it. A drift on either side
 * fails HERE, not in a live save.
 */
describe('compileBuilder matches the server, over every shipped rule', () => {
  const rows = fixtures as { spec_key: string; builder: SpecRuleBuilder; compiled: SpecCompiledRule }[];

  it('the fixture is non-trivial', () => {
    expect(rows.length).toBeGreaterThan(50);
  });

  it.each(rows.map((row) => [`${row.spec_key}: ${JSON.stringify(row.builder)}`, row] as const))(
    '%s',
    (_label, row) => {
      expect(compileBuilder(row.builder)).toEqual(row.compiled);
    },
  );
});
