/** B review: a layer with no (or a non-finite) z_index must never make the next z NaN. */
import { describe, expect, it } from 'vitest';

import { nextLayerZ } from './canvas-geometry';
import { normalizeLayer } from './tag-template-types';
import type { TagLayer } from './tag-template-types';

const layer = (z: unknown) => ({ id: 'a', z_index: z }) as unknown as TagLayer;

describe('nextLayerZ', () => {
  it('is one above the highest finite z_index, 1 for none', () => {
    expect(nextLayerZ([])).toBe(1);
    expect(nextLayerZ([layer(3), layer(7)])).toBe(8);
  });

  it('ignores a missing or non-finite z_index instead of returning NaN', () => {
    expect(nextLayerZ([layer(undefined)])).toBe(1);
    expect(nextLayerZ([layer(NaN), layer(4)])).toBe(5);
    expect(nextLayerZ([layer('x')])).toBe(1);
  });
});

describe('normalizeLayer', () => {
  it('gives a layer with a non-finite z_index its position', () => {
    expect(normalizeLayer(layer(NaN), 2).z_index).toBe(2);
    expect(normalizeLayer(layer(undefined), 3).z_index).toBe(3);
    expect(normalizeLayer(layer(5), 3).z_index).toBe(5);
  });
});
