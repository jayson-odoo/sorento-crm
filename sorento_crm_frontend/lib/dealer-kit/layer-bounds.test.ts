/**
 * PRICETAG-DESIGNER-GAPS item 4: resizing a template keeps every layer where
 * it is, so the warning counts the layers the new size would cut off.
 */
import { describe, expect, it } from 'vitest';
import type { TagLayer } from './tag-template-types';
import { layersCutOff } from './layer-bounds';

const BIG = { width_mm: 1000, height_mm: 1000 };
const layersOutside = (layers: TagLayer[], w: number, h: number) =>
  layersCutOff(layers, BIG, { width_mm: w, height_mm: h });

function layer(id: string, x: number, y: number, w: number, h: number, extra: Partial<TagLayer> = {}): TagLayer {
  return {
    id,
    type: 'shape',
    x_mm: x,
    y_mm: y,
    width_mm: w,
    height_mm: h,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'shape', shape: 'rect', fill: '#000', stroke: '#000', strokeWidth: 0, cornerRadius: 0 },
    ...extra,
  } as TagLayer;
}

describe('layersCutOff from a size everything fits', () => {
  const layers = [layer('a', 0, 0, 40, 20), layer('b', 50, 10, 30, 30), layer('c', 5, 60, 10, 10)];

  it('is zero when everything still fits', () => {
    expect(layersOutside(layers, 85, 130)).toBe(0);
  });

  it('counts a layer that crosses the new right edge', () => {
    expect(layersOutside(layers, 70, 130)).toBe(1);
  });

  it('counts a layer that crosses the new bottom edge', () => {
    expect(layersOutside(layers, 85, 65)).toBe(1);
  });

  it('counts each layer once even when it crosses both edges', () => {
    expect(layersOutside(layers, 60, 30)).toBe(2);
  });

  it('treats a layer that ends exactly on the edge as inside (no float noise)', () => {
    expect(layersOutside([layer('a', 10.1, 0, 19.9, 5)], 30, 5)).toBe(0);
  });

  it('does not count a group box on top of its children', () => {
    const group = layer('g', 50, 10, 30, 30, { type: 'group', props: { kind: 'group', children: ['b'] } as never });
    expect(layersOutside([...layers, group], 70, 130)).toBe(1);
  });
});

describe('layersCutOff', () => {
  const layers = [layer('a', 0, 0, 40, 20), layer('b', 50, 10, 30, 30), layer('stray', 80, 0, 20, 5)];

  it('counts only layers the new size cuts off, not ones already outside the old size', () => {
    // `stray` reaches 100 mm: already outside 85 mm wide, so it is not news.
    expect(layersCutOff(layers, { width_mm: 85, height_mm: 130 }, { width_mm: 85, height_mm: 140 })).toBe(0);
  });

  it('counts a layer that fitted before and does not now', () => {
    expect(layersCutOff(layers, { width_mm: 85, height_mm: 130 }, { width_mm: 70, height_mm: 130 })).toBe(1);
  });
});
