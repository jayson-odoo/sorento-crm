import { describe, expect, it } from 'vitest';
import { compileBuilder, ruleCells } from './ruleSentence';
import type { SpecRuleBuilder } from '../types/productSpec.types';

/**
 * `compileBuilder` mirrors `compile_builder` in
 * `sorento_crm_backend/app/services/product_spec_rules.py` EXACTLY (contract
 * `CONTRACT-product-specs-rule-engine.md` sections 1-2.1) - a save is refused when the
 * two disagree. These are the plan's own worked examples (D5), one per kind, each
 * checked against the contract's own compiled shape rather than against this file's
 * memory of it.
 */
describe('compileBuilder mirrors the server compiler', () => {
  it('words: "SOFT CLOSE" or "SOFT CLOSING", any case, hyphen or space between words', () => {
    const builder: SpecRuleBuilder = {
      kind: 'words',
      look_in: 'any',
      words: ['SOFT CLOSE', 'SOFT CLOSING'],
      value: true,
    };
    const compiled = compileBuilder(builder);
    expect(compiled.kind).toBe('words');
    expect(compiled.scope).toBe('any');
    expect(compiled.capture).toBeNull();
    const pattern = new RegExp(compiled.pattern!, 'i');
    expect(pattern.test('SOFT-CLOSE HINGE')).toBe(true);
    expect(pattern.test('SOFTCLOSING SEAT')).toBe(true);
    expect(pattern.test('A SOFTLY CLOSED DOOR')).toBe(false);
  });

  it('words with a skip: SCREW, except right after W/O or WITHOUT', () => {
    const builder: SpecRuleBuilder = {
      kind: 'words',
      words: ['SCREW'],
      skip_after: ['W/O', 'WITHOUT'],
      value: true,
    };
    const compiled = compileBuilder(builder);
    const pattern = new RegExp(compiled.pattern!, 'i');
    const skip = new RegExp(compiled.skip!, 'i');
    expect(pattern.test('COMES WITH A FIXING SCREW')).toBe(true);
    // "W/O SCREW" still matches the words pattern; the caller checks `skip` against
    // the text BEFORE the hit and drops it there, exactly as the engine does.
    expect(skip.test('W/O ')).toBe(true);
  });

  it('number, before: the number before OZ (Capacity (oz))', () => {
    const builder: SpecRuleBuilder = { kind: 'number', before: ['OZ'] };
    const compiled = compileBuilder(builder);
    expect(compiled.capture).toBe(1);
    const pattern = new RegExp(compiled.pattern!, 'i');
    const match = '8OZ TUMBLER'.match(pattern);
    expect(match?.[1]).toBe('8');
    // The 1008 in SRTKS1008L is never read: a digit touches it in front.
    expect(pattern.test('SRTKS1008L')).toBe(false);
  });

  it('number, written in: the number before M, written in metres', () => {
    const builder: SpecRuleBuilder = {
      kind: 'number',
      before: ['M'],
      written_in: 'metres',
    };
    const compiled = compileBuilder(builder);
    expect(compiled.scale).toBe(1000);
    const pattern = new RegExp(compiled.pattern!, 'i');
    expect('1.2M HOSE'.match(pattern)?.[1]).toBe('1.2');
  });

  it('number, between: the number between S TRAP or P TRAP and MM', () => {
    const builder: SpecRuleBuilder = {
      kind: 'number',
      after: ['S TRAP', 'P TRAP'],
      before: ['MM'],
    };
    const compiled = compileBuilder(builder);
    const pattern = new RegExp(compiled.pattern!, 'i');
    expect('S-TRAP:100MM'.match(pattern)?.[1]).toBe('100');
  });

  it('number with a floor and a skip: ignore below 10, skip after S TRAP or P TRAP', () => {
    const builder: SpecRuleBuilder = {
      kind: 'number',
      before: ['MM'],
      ignore_below: 10,
      skip_after: ['S TRAP', 'P TRAP'],
    };
    const compiled = compileBuilder(builder);
    expect(compiled.min).toBe(10);
    expect(compiled.skip).not.toBeNull();
  });

  it('size: the 3rd number from a size like 1500 x 750 x 630', () => {
    const builder: SpecRuleBuilder = { kind: 'size', look_in: 'description', pick: 3 };
    const compiled = compileBuilder(builder);
    expect(compiled.scope).toBe('description');
    expect(compiled.pick).toBe(3);
    const pattern = new RegExp(compiled.pattern!, 'i');
    const match = '1500 X 750 X 630'.match(pattern);
    expect(match?.[6]).toBe('630');
  });

  it('size, labelled: the number labelled W (like W165)', () => {
    const builder: SpecRuleBuilder = { kind: 'size', pick: 'W' };
    const compiled = compileBuilder(builder);
    const pattern = new RegExp(compiled.pattern!, 'i');
    const match = 'L750 X W165'.match(pattern);
    expect(match?.[3]).toBe('W');
    expect(match?.[4]).toBe('165');
  });

  it('code: ends with -GM, sets Gunmetal', () => {
    const builder: SpecRuleBuilder = {
      kind: 'code',
      code_match: 'ends_with',
      texts: ['-gm'],
      value: 'gunmetal',
    };
    const compiled = compileBuilder(builder);
    expect(compiled.scope).toBe('code');
    expect(compiled.pattern).toBeNull();
    expect(compiled.code_match).toBe('ends_with');
    expect(compiled.texts).toEqual(['-GM']);
  });

  it('product: the product category class', () => {
    const builder: SpecRuleBuilder = { kind: 'product', fact: 'class' };
    const compiled = compileBuilder(builder);
    expect(compiled.scope).toBe('product');
    expect(compiled.pattern).toBeNull();
    expect(compiled.fact).toBe('class');
  });
});

describe('ruleCells: the grid row, never a sentence', () => {
  it('renders a number-between rule as labelled parts', () => {
    const builder: SpecRuleBuilder = {
      kind: 'number',
      after: ['S TRAP', 'P TRAP'],
      before: ['MM'],
    };
    const cells = ruleCells(builder);
    expect(cells.whatToFind.primary).toBe('After: S TRAP, P TRAP · Before: MM');
    expect(cells.valueItSets).toBe('The number it finds');
    expect(cells.whatToFind.primary).not.toMatch(/\bif\b/i);
  });

  it('renders Only when as "Shape is not: Round, Square"', () => {
    const builder: SpecRuleBuilder = {
      kind: 'product',
      fact: 'length',
      only_when: { spec: 'shape', is: false, values: ['round', 'square'] },
    };
    const cells = ruleCells(builder, undefined, (key) =>
      key === 'shape'
        ? ({ label: 'Shape', value_labels: {} } as never)
        : undefined,
    );
    expect(cells.onlyWhen).toBe('Shape is not: Round, Square');
  });

  it('Code and Product rules read their own place, not asked for Where to look', () => {
    expect(ruleCells({ kind: 'code', code_match: 'ends_with', texts: ['-GM'], value: 'gunmetal' }).whereToLook).toBe(
      'Product code',
    );
    expect(ruleCells({ kind: 'product', fact: 'length' }).whereToLook).toBe('The product');
  });
});
