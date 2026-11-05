/**
 * PRICETAG-DESIGNER-GAPS item 3 (feature icons): the ONE rule that picks and lays out
 * the icons for canvas, preview and print. Contract: documentation/plans/dealer-kit/
 * pricetag-feature-icons-contract.md F2. Written test-first: the module does not exist yet.
 */
import { describe, expect, it } from 'vitest';

import { featureIconFit, featureIconRow, featureIconsFor, type FeatureIcon } from './feature-icons';

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

  it('keeps the order the icons came in, never by name (the registry sends the one sequence)', () => {
    // Owner 5 Nov 21:0x: spec Icon order, then the value's own list; no per-layer order.
    const a = icon('a', 'alpha', 'k', ['x']);
    const b = icon('b', 'Bravo', 'k', ['x']);
    const c = icon('c', 'charlie', 'k', ['x']);
    const d = icon('d', 'Delta', 'k', ['x']);
    const out = featureIconsFor([spec('k', 'X', 'x')], [d, c, b, a]);
    expect(out.map((i) => i.id)).toEqual(['d', 'c', 'b', 'a']);
  });

  it('Pull-out (Icon order 1) then Water supply Mixer (2) reads [pull-out, hot, cold]', () => {
    // The backend's one sequence: pull-out's true, then water supply's cold_only, then mixer.
    const sequence = [
      icon('pull', 'Pull-out', 'has_pull_out_shower', ['true']),
      icon('cold', 'Cold', 'water_supply', ['cold_only']),
      icon('hot', 'Hot', 'water_supply', ['mixer']),
      icon('cold', 'Cold', 'water_supply', ['mixer']),
    ];
    const both = [spec('has_pull_out_shower', 'Yes', 'true'), spec('water_supply', 'Mixer', 'mixer')];
    expect(featureIconsFor(both, sequence).map((i) => i.id)).toEqual(['pull', 'hot', 'cold']);
    expect(featureIconsFor([both[1]], sequence).map((i) => i.id)).toEqual(['hot', 'cold']);
  });

  it("keeps a value's own icon order [b, a]", () => {
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

describe('featureIconFit', () => {
  const props = (over: Record<string, unknown> = {}) => ({
    kind: 'feature_icons' as const,
    iconSize_mm: 12,
    gap_mm: 3,
    align: 'left' as const,
    ...over,
  });

  it('shows every icon that fits', () => {
    expect(featureIconFit(2, props(), 40)).toEqual({ shown: 2, dropped: 0 });
  });

  it('reports the icon that does not fit (crew: 3 x 12 mm in a 40 mm box)', () => {
    // 3 * 12 + 2 * 3 = 42 mm > 40 mm.
    expect(featureIconFit(3, props(), 40)).toEqual({ shown: 2, dropped: 1 });
  });

  it('does not depend on the alignment', () => {
    for (const align of ['left', 'center', 'right'] as const) {
      expect(featureIconFit(3, props({ align }), 40)).toEqual({ shown: 2, dropped: 1 });
    }
  });

  it('agrees with featureIconRow', () => {
    for (const count of [0, 1, 2, 3, 5]) {
      expect(featureIconRow(count, props(), 40)).toHaveLength(featureIconFit(count, props(), 40).shown);
    }
  });

  it('drops everything when not even one fits, and nothing for no icons', () => {
    expect(featureIconFit(2, props(), 5)).toEqual({ shown: 0, dropped: 2 });
    expect(featureIconFit(0, props(), 40)).toEqual({ shown: 0, dropped: 0 });
  });
});
