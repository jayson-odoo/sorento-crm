/**
 * SPEC-VALUE-ICONS R1: one spec row's icons, through the tag's own matcher.
 *
 * The Specifications tab asks "which icons does THIS value print", so it runs `featureIconsFor`
 * over a single row. These pin that it matches the STORED value the tag matches (contract B4),
 * not the display label, and keeps the admin's order.
 */
import { describe, expect, it } from 'vitest';

import { iconsForSpecValue, type FeatureIcon } from './feature-icons';

const ICONS: FeatureIcon[] = [
  { id: 'hot', name: 'Hot water', spec_key: 'water_supply', values: ['mixer'] },
  {
    id: 'cold',
    name: 'Cold water',
    spec_key: 'water_supply',
    values: ['mixer'],
  },
  {
    id: 'cold-only',
    name: 'Cold only',
    spec_key: 'water_supply',
    values: ['cold_only'],
  },
  { id: 'smart', name: 'Smart', spec_key: 'is_smart', values: ['true'] },
  { id: 'sus', name: 'SUS 304', spec_key: 'steel_grade', values: ['304'] },
];

describe('iconsForSpecValue', () => {
  it('returns every icon the stored value carries, in the order the list gives', () => {
    expect(
      iconsForSpecValue('water_supply', 'mixer', ICONS).map((i) => i.id),
    ).toEqual(['hot', 'cold']);
  });

  it('matches the stored value, never its display label', () => {
    expect(iconsForSpecValue('water_supply', 'Mixer', ICONS)).toEqual([]);
  });

  it('reads a stored boolean as true / false, like the tag payload does', () => {
    expect(iconsForSpecValue('is_smart', true, ICONS).map((i) => i.id)).toEqual(
      ['smart'],
    );
    expect(iconsForSpecValue('is_smart', false, ICONS)).toEqual([]);
  });

  it('reads a stored number as its text', () => {
    expect(
      iconsForSpecValue('steel_grade', 304, ICONS).map((i) => i.id),
    ).toEqual(['sus']);
  });

  it('gives nothing for a value with no icon, an empty value or no list', () => {
    expect(iconsForSpecValue('colour', 'black', ICONS)).toEqual([]);
    expect(iconsForSpecValue('water_supply', null, ICONS)).toEqual([]);
    expect(iconsForSpecValue('water_supply', 'mixer', undefined)).toEqual([]);
  });
});
