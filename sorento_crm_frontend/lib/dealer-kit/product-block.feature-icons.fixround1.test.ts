/**
 * Feature icons review fix round 1 (N2): a feature_icons layer bound with `subjectPart` (a
 * non-combo line part) reads that part's specs on the canvas.
 */
import { describe, expect, it } from 'vitest';

import { layerDisplay } from './product-block';
import type { LineTagData, TagBindingData, TagLayer } from './tag-template-types';

const spec = (key: string, value: string, raw: string) => ({ key, label: key, value, unit: null, raw });

function lineWithPart(): TagBindingData {
  return {
    kind: 'line',
    line: {
      tag_id: 't1',
      line_id: 'l1',
      tag_label: '1a',
      open_groups: [],
      code: 'SINK',
      name: 'Sink',
      dimensions: '',
      spec_lines: '',
      specs: [spec('water_supply', 'Cold Only', 'cold_only')],
      set_members: '',
      images: [],
      list_price: 1,
      sell_price: null,
      show_promo_price: false,
      included_accessories: '',
      quantity: 1,
      barcode: null,
      parts: [
        {
          product_id: 'p-tap',
          code: 'TAP',
          name: 'Tap',
          dimensions: '',
          list_price: 1,
          sell_price: null,
          images: [],
          specs: [spec('water_supply', 'Mixer', 'mixer')],
        },
      ],
    } as unknown as LineTagData,
  };
}

function iconsLayer(props: Record<string, unknown>): TagLayer {
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

describe('layerDisplay feature_icons with subjectPart', () => {
  it('reads the line part named by subjectPart, not the host', () => {
    const display = layerDisplay(iconsLayer({ subjectPart: 0 }), lineWithPart(), URLS, ICONS);
    expect(display?.icons?.map((i) => i.id)).toEqual(['cold', 'hot']);
  });

  it('subjectPart -1 reads the parent alone', () => {
    const display = layerDisplay(iconsLayer({ subjectPart: -1 }), lineWithPart(), URLS, ICONS);
    expect(display?.icons?.map((i) => i.id)).toEqual(['cold']);
  });

  it('skips a matched icon that has no signed URL', () => {
    const display = layerDisplay(iconsLayer({ subjectPart: 0 }), lineWithPart(), { cold: URLS.cold }, ICONS);
    expect(display?.icons?.map((i) => i.id)).toEqual(['cold']);
  });
});
