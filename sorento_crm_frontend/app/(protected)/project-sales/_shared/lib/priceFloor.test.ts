/**
 * Reading a floor out loud.
 *
 * The two sentences are pinned separately because they answer different questions and a
 * surface may need one without the other: WHAT applies, and WHERE it came from. The
 * source sentence is the one that carries the whole point of surfacing floors on the
 * product and category editors, so its wording is behaviour, not decoration.
 */
import { describe, expect, it } from 'vitest';
import {
  describeEffectiveFloor,
  describeFloorRule,
  describeFloorSource,
} from './priceFloor';
import type { EffectiveFloorSource } from '../types/project.types';

function source(overrides: Partial<EffectiveFloorSource> = {}): EffectiveFloorSource {
  return {
    rule_id: 'rule-1',
    level: 'category',
    mode: 'percent',
    value: '80.00',
    amount: '800.00',
    source_label: 'Basins',
    ...overrides,
  };
}

describe('describeFloorRule', () => {
  it('reads a percentage against the list price', () => {
    expect(describeFloorRule({ mode: 'percent', value: '80.00' })).toBe(
      'At least 80% of the list price',
    );
  });

  it('says a fixed amount ignores list entirely', () => {
    expect(describeFloorRule({ mode: 'absolute', value: '950.00' })).toBe(
      'At least RM 950, whatever the list price says',
    );
  });

  it('leaves a value it cannot read as a number alone', () => {
    expect(describeFloorRule({ mode: 'percent', value: 'n/a' })).toContain('n/a');
  });
});

describe('describeEffectiveFloor', () => {
  it('adds the resolved ringgit amount to a percentage, since that is the number quoted against', () => {
    expect(describeEffectiveFloor(source())).toBe(
      'At least 80% of the list price (RM 800.00)',
    );
  });

  it('shows no amount for a percentage with nothing to apply it to', () => {
    // A category has no list price. Printing a number here would be inventing one.
    expect(describeEffectiveFloor(source({ amount: null }))).toBe(
      'At least 80% of the list price',
    );
  });

  it('does not repeat an absolute amount it has already stated', () => {
    expect(
      describeEffectiveFloor(
        source({ mode: 'absolute', value: '500.00', amount: '500.00' }),
      ),
    ).toBe('At least RM 500, whatever the list price says');
  });
});

describe('describeFloorSource', () => {
  it('names the category a product inherits from', () => {
    expect(describeFloorSource(source(), 'product')).toBe(
      'Inherited from the Basins category',
    );
  });

  it('names a more distant ancestor the same way', () => {
    expect(
      describeFloorSource(
        source({ level: 'category_ancestor', source_label: 'Sanitary Ware' }),
        'product',
      ),
    ).toBe('Inherited from the Sanitary Ware category');
  });

  it('says a product rule belongs to the product itself', () => {
    expect(describeFloorSource(source({ level: 'product' }), 'product')).toBe(
      'Set on this product',
    );
  });

  it('distinguishes a category reading its OWN rule from inheriting one', () => {
    expect(describeFloorSource(source({ level: 'category' }), 'category')).toBe(
      'Set on this category',
    );
    expect(
      describeFloorSource(
        source({ level: 'category_ancestor', source_label: 'Sanitary Ware' }),
        'category',
      ),
    ).toBe('Inherited from the Sanitary Ware category');
  });

  it('names the company default rather than leaving the source blank', () => {
    expect(
      describeFloorSource(
        source({ level: 'system', source_label: 'Company default' }),
        'product',
      ),
    ).toBe('Inherited from the company default');
  });
});
