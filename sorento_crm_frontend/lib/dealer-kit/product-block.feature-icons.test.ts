/**
 * PRICETAG-DESIGNER-GAPS item 3: `layerDisplay` for a feature_icons layer reads the specs of
 * the layer's own SUBJECT (main product, or a combo position via subjectSlot), not the host's.
 */
import { describe, expect, it } from 'vitest';

import { layerDisplay } from './product-block';
import type { LineTagData, TagBindingData, TagLayer } from './tag-template-types';

const spec = (key: string, value: string, raw: string) => ({ key, label: key, value, unit: null, raw });

function part(code: string, specs: ReturnType<typeof spec>[]) {
  return {
    product_id: `id-${code}`,
    code,
    name: `Name ${code}`,
    dimensions: '',
    list_price: 100,
    sell_price: null,
    images: [],
    specs,
    currency: 'MYR',
  };
}

const MIXER = [spec('water_supply', 'Mixer', 'mixer')];
const COLD_ONLY = [spec('water_supply', 'Cold Only', 'cold_only')];

function lineWith(): TagBindingData {
  return {
    kind: 'line',
    line: {
      tag_id: 't1',
      line_id: 'l1',
      tag_label: '1a',
      open_groups: [],
      parts: [],
      code: 'HOST',
      name: 'Host sink',
      dimensions: '',
      spec_lines: '',
      specs: COLD_ONLY, // the HOST reads cold only
      set_members: '',
      images: [],
      list_price: 1,
      sell_price: null,
      show_promo_price: false,
      included_accessories: '',
      quantity: 1,
      barcode: null,
      slots: { fixed: [part('TAP', MIXER)], groups: [], upgrades: [] },
    } as unknown as LineTagData,
  };
}

function iconsLayer(props: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'fi',
    type: 'feature_icons',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 1, align: 'left', ...props },
  } as unknown as TagLayer;
}

const ICONS = [
  { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['cold_only', 'mixer'] },
  { id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] },
];
const URLS = { cold: 'https://cdn/cold.png', hot: 'https://cdn/hot.png' };

describe('layerDisplay for a feature_icons layer', () => {
  it('reads the combo position part, not the host product', () => {
    const display = layerDisplay(
      iconsLayer({ subjectSlot: { kind: 'fixed', index: 0 } }),
      lineWith(),
      URLS,
      ICONS,
    );
    expect(display?.icons).toEqual([
      { id: 'cold', url: 'https://cdn/cold.png' },
      { id: 'hot', url: 'https://cdn/hot.png' },
    ]);
  });

  it('reads the host when the layer has no subject', () => {
    const display = layerDisplay(iconsLayer(), lineWith(), URLS, ICONS);
    expect(display?.icons).toEqual([{ id: 'cold', url: 'https://cdn/cold.png' }]);
  });

  it('keeps the sequence the icons came in (no per-layer order)', () => {
    const display = layerDisplay(
      iconsLayer({ subjectSlot: { kind: 'fixed', index: 0 } }),
      lineWith(),
      URLS,
      [...ICONS].reverse(),
    );
    expect(display?.icons?.map((i) => i.id)).toEqual(['hot', 'cold']);
  });

  it('answers an empty icon list when the library is not given', () => {
    const display = layerDisplay(iconsLayer(), lineWith(), URLS);
    expect(display?.icons).toEqual([]);
  });

  it('answers an empty icon list for an empty position', () => {
    const display = layerDisplay(
      iconsLayer({ subjectSlot: { kind: 'fixed', index: 3 } }),
      lineWith(),
      URLS,
      ICONS,
    );
    expect(display?.icons).toEqual([]);
  });
});
