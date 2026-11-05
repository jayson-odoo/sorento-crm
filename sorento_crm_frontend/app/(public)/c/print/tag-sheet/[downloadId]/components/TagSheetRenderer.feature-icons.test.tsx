/**
 * PRICETAG-DESIGNER-GAPS item 3: the print page draws a feature_icons layer as <img alt=name>
 * in packed order, from the subject's specs, and prints nothing when no icon matches.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TagLayer, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

const spec = (key: string, value: string, raw: string) => ({ key, label: key, value, unit: null, raw });

function resolved(over: Record<string, unknown> = {}): ResolvedLineData {
  return {
    tag_id: TAG_ID,
    tag_label: '1a',
    line_id: 'line-1',
    code: 'TP-1',
    name: 'Mixer Tap',
    dimensions: '',
    spec_lines: '',
    set_members: '',
    list_price: 100,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    specs: [spec('water_supply', 'Mixer', 'mixer')],
    ...over,
  } as unknown as ResolvedLineData;
}

function docWith(props: Record<string, unknown> = {}): TagSheetDoc {
  const layer = {
    id: 'fi',
    type: 'feature_icons',
    x_mm: 3,
    y_mm: 4,
    width_mm: 40,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 8, gap_mm: 2, align: 'left', ...props },
  } as unknown as TagLayer;
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [
      {
        id: 's1',
        tags: [
          {
            id: 't1',
            template_id: 'tpl-1',
            request_tag_id: TAG_ID,
            x_mm: 5,
            y_mm: 5,
            width_mm: 95,
            height_mm: 130,
            layers: [layer],
          },
        ],
      },
    ],
  } as TagSheetDoc;
}

const FEATURE_ICONS = [
  { id: 'cold', name: 'Cold', spec_key: 'water_supply', values: ['cold_only', 'mixer'] },
  { id: 'hot', name: 'Hot', spec_key: 'water_supply', values: ['mixer'] },
  { id: 'sus', name: 'SUS 304', spec_key: 'steel_grade', values: ['304'] },
];
const ASSETS = {
  cold: 'https://cdn.test/cold.png',
  hot: 'https://cdn.test/hot.png',
  sus: 'https://cdn.test/sus.png',
};

function renderIt(doc: TagSheetDoc, data: ResolvedLineData, icons = FEATURE_ICONS) {
  // `featureIcons` is the new TagSheetMedia member (contract B7).
  const extra = { featureIcons: icons } as Record<string, unknown>;
  return render(
    <TagSheetRenderer doc={doc} resolvedData={{ [TAG_ID]: data }} assets={ASSETS} {...extra} />,
  );
}

describe('TagSheetRenderer feature icons', () => {
  it('prints the matching icons as <img alt=name> in packed order', () => {
    const { container } = renderIt(docWith(), resolved());
    const imgs = Array.from(container.querySelectorAll('img'));
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Cold', 'Hot']);
    expect(imgs.map((i) => i.getAttribute('src'))).toEqual([ASSETS.cold, ASSETS.hot]);
    // 8mm icons, 2mm gap, left aligned: left edges 0 and 10 mm inside the layer box.
    expect(imgs.map((i) => parseFloat(i.style.left))).toEqual([0, 10]);
    expect(imgs.every((i) => parseFloat(i.style.width) === 8)).toBe(true);
  });

  it('prints in the sequence the icons came in (no per-layer order)', () => {
    const { container } = renderIt(docWith(), resolved(), [...FEATURE_ICONS].reverse());
    const imgs = Array.from(container.querySelectorAll('img'));
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Hot', 'Cold']);
  });

  it('prints nothing when no spec matches', () => {
    const { container } = renderIt(
      docWith(),
      resolved({ specs: [spec('water_supply', 'Basin', 'basin_only')] }),
    );
    expect(container.querySelectorAll('img')).toHaveLength(0);
  });

  it('prints nothing when the product has no specs at all', () => {
    const { container } = renderIt(docWith(), resolved({ specs: [] }));
    expect(container.querySelectorAll('img')).toHaveLength(0);
  });

  it('reads the combo part named by subjectSlot, not the host', () => {
    const tap = {
      product_id: 'p-tap',
      code: 'TAP',
      name: 'Tap',
      dimensions: '',
      list_price: 1,
      sell_price: null,
      images: [],
      specs: [spec('water_supply', 'Cold Only', 'cold_only')],
    };
    const { container } = renderIt(
      docWith({ subjectSlot: { kind: 'fixed', index: 0 } }),
      resolved({
        // The host reads Mixer (hot + cold); the tap position reads cold only.
        slots: { fixed: [tap], groups: [], upgrades: [] },
      }),
    );
    const imgs = Array.from(container.querySelectorAll('img'));
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Cold']);
  });
});
