/**
 * PRICETAG-DESIGNER-GAPS item 3 (feature icons): the ONE rule that picks and lays out
 * the icons for canvas, preview and print. Contract: documentation/plans/dealer-kit/
 * pricetag-feature-icons-contract.md F2. Written test-first: the module does not exist yet.
 */
import { describe, expect, it } from 'vitest';

import { featureIconRow, featureIconsFor, type FeatureIcon } from './feature-icons';

const spec = (key: string, value: string, raw?: string) => ({
  key,
  label: key,
  value,
  unit: null,
  ...(raw === undefined ? {} : { raw }),
});

const icon = (id: string, name: string, spec_key: string, values: string[]): FeatureIcon => ({
  id,
  name,
  spec_key,
  values,
});

const COLD = icon('cold', 'Cold', 'water_supply', ['cold_only', 'mixer']);
const HOT = icon('hot', 'Hot', 'water_supply', ['mixer']);
const SUS = icon('sus', 'SUS 304', 'steel_grade', ['304']);

describe('featureIconsFor', () => {
  it('shows the cold icon alone for a cold-only tap', () => {
    const out = featureIconsFor([spec('water_supply', 'Cold Only', 'cold_only')], [COLD, HOT]);
    expect(out.map((i) => i.id)).toEqual(['cold']);
  });

  it('shows hot and cold for a mixer', () => {
    const out = featureIconsFor([spec('water_supply', 'Mixer', 'mixer')], [HOT, COLD]);
    expect(out.map((i) => i.id).sort()).toEqual(['cold', 'hot']);
  });

  it('shows nothing when the product has no water_supply spec', () => {
    const out = featureIconsFor([spec('steel_grade', '304', '304')], [COLD, HOT]);
    expect(out).toEqual([]);
  });

  it('never matches on display text, only on raw', () => {
    // "Mixer" is the label and the raw value is missing: no match.
    expect(featureIconsFor([spec('water_supply', 'mixer')], [HOT, COLD])).toEqual([]);
    // The display text differs from raw: raw wins.
    const out = featureIconsFor([spec('water_supply', 'Hot And Cold', 'mixer')], [HOT]);
    expect(out.map((i) => i.id)).toEqual(['hot']);
  });

  it('puts ids in `order` first, in that order, then the rest in the order they came (never by name)', () => {
    // Owner ruling 5 Nov 20:4x: the default is the order the admin set on the spec value.
    const a = icon('a', 'alpha', 'k', ['x']);
    const b = icon('b', 'Bravo', 'k', ['x']);
    const c = icon('c', 'charlie', 'k', ['x']);
    const d = icon('d', 'Delta', 'k', ['x']);
    const out = featureIconsFor([spec('k', 'X', 'x')], [d, c, b, a], ['c', 'missing', 'a']);
    expect(out.map((i) => i.id)).toEqual(['c', 'a', 'd', 'b']);
  });

  it("keeps a value's own icon order [b, a] when the layer names no order", () => {
    const b = icon('b', 'Bravo', 'k', ['x']);
    const a = icon('a', 'Alpha', 'k', ['x']);
    expect(featureIconsFor([spec('k', 'X', 'x')], [b, a]).map((i) => i.id)).toEqual(['b', 'a']);
  });

  it('shows ONE combined icon when Mixer maps to a single red-blue icon', () => {
    const combined = icon('red-blue', 'Hot and cold', 'water_supply', ['mixer']);
    const blue = icon('blue', 'Cold', 'water_supply', ['cold_only']);
    const icons = [blue, combined];
    expect(featureIconsFor([spec('water_supply', 'Mixer', 'mixer')], icons).map((i) => i.id)).toEqual([
      'red-blue',
    ]);
    expect(
      featureIconsFor([spec('water_supply', 'Cold Only', 'cold_only')], icons).map((i) => i.id),
    ).toEqual(['blue']);
  });

  it('shows an icon reached twice for one product once, at its first position', () => {
    // The backend sends one entry per (value, icon); the same asset can sit on two values
    // the product holds (here on two keys).
    const coldOnSupply = icon('cold', 'Cold', 'water_supply', ['mixer']);
    const hot = icon('hot', 'Hot', 'water_supply', ['mixer']);
    const coldOnFinish = icon('cold', 'Cold', 'finish', ['ice']);
    const out = featureIconsFor(
      [spec('water_supply', 'Mixer', 'mixer'), spec('finish', 'Ice', 'ice')],
      [hot, coldOnFinish, coldOnSupply],
    );
    expect(out.map((i) => i.id)).toEqual(['hot', 'cold']);
  });

  it('lists an icon at most once even when the order repeats it', () => {
    const out = featureIconsFor([spec('water_supply', 'Mixer', 'mixer')], [HOT, COLD], ['hot', 'hot', 'cold']);
    expect(out.map((i) => i.id)).toEqual(['hot', 'cold']);
  });

  it('does not show an icon in `order` whose rule does not match', () => {
    const out = featureIconsFor([spec('water_supply', 'Cold Only', 'cold_only')], [HOT, COLD], ['hot']);
    expect(out.map((i) => i.id)).toEqual(['cold']);
  });

  it('handles no specs and no icons', () => {
    expect(featureIconsFor([], [COLD])).toEqual([]);
    expect(featureIconsFor([spec('water_supply', 'Mixer', 'mixer')], [])).toEqual([]);
  });

  it('matches two different rules at once', () => {
    const out = featureIconsFor(
      [spec('water_supply', 'Cold Only', 'cold_only'), spec('steel_grade', '304', '304')],
      [SUS, COLD],
    );
    expect(out.map((i) => i.id)).toEqual(['sus', 'cold']);
  });
});

describe('featureIconRow', () => {
  const props = (over: Record<string, unknown> = {}) => ({
    kind: 'feature_icons' as const,
    iconSize_mm: 8,
    gap_mm: 2,
    align: 'left' as const,
    order: [],
    ...over,
  });
  const close = (got: number[], want: number[]) => {
    expect(got).toHaveLength(want.length);
    got.forEach((v, i) => expect(v).toBeCloseTo(want[i], 5));
  };

  it('packs icons from the left with the gap between them', () => {
    close(featureIconRow(3, props(), 40), [0, 10, 20]);
  });

  it('centres the packed row in the box', () => {
    // total 3*8 + 2*2 = 28, free 12, offset 6
    close(featureIconRow(3, props({ align: 'center' }), 40), [6, 16, 26]);
  });

  it('right-aligns the packed row', () => {
    close(featureIconRow(3, props({ align: 'right' }), 40), [12, 22, 32]);
  });

  it('a single icon sits at the left, centre or right edge', () => {
    close(featureIconRow(1, props(), 40), [0]);
    close(featureIconRow(1, props({ align: 'center' }), 40), [16]);
    close(featureIconRow(1, props({ align: 'right' }), 40), [32]);
  });

  it('drops icons that do not fit entirely inside the box', () => {
    // 2 icons = 18mm fit in 25mm, 3 icons = 28mm do not.
    close(featureIconRow(3, props(), 25), [0, 10]);
    expect(featureIconRow(5, props({ align: 'right' }), 25)).toHaveLength(2);
  });

  it('draws nothing when not even one icon fits', () => {
    expect(featureIconRow(2, props(), 5)).toEqual([]);
  });

  it('draws nothing for zero icons', () => {
    expect(featureIconRow(0, props(), 40)).toEqual([]);
  });

  it('allows an icon that exactly fills the box', () => {
    close(featureIconRow(1, props(), 8), [0]);
  });
});
