/**
 * Feature icons review fix round 1 (N2): the print page reads the line part named by
 * `subjectPart`, and skips an icon it has no signed URL for.
 */
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TagLayer, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';
const spec = (key: string, value: string, raw: string) => ({ key, label: key, value, unit: null, raw });

const resolved = {
  tag_id: TAG_ID,
  tag_label: '1a',
  line_id: 'line-1',
  code: 'SINK',
  name: 'Sink',
  dimensions: '',
  spec_lines: '',
  set_members: '',
  list_price: 100,
  sell_price: null,
  show_promo_price: false,
  included_accessories: '',
  quantity: 1,
  specs: [spec('water_supply', 'Cold Only', 'cold_only')],
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
} as unknown as ResolvedLineData;

function docWith(props: Record<string, unknown>): TagSheetDoc {
  const layer = {
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
            x_mm: 0,
            y_mm: 0,
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
];

const alts = (c: HTMLElement) => Array.from(c.querySelectorAll('img')).map((i) => i.getAttribute('alt'));

describe('TagSheetRenderer feature icons with subjectPart', () => {
  it('prints the part named by subjectPart', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith({ subjectPart: 0 })}
        resolvedData={{ [TAG_ID]: resolved }}
        assets={{ cold: 'https://cdn/cold.png', hot: 'https://cdn/hot.png' }}
        featureIcons={FEATURE_ICONS}
      />,
    );
    expect(alts(container)).toEqual(['Cold', 'Hot']);
  });

  it('skips an icon with no signed URL and closes the gap', () => {
    const { container } = render(
      <TagSheetRenderer
        doc={docWith({ subjectPart: 0 })}
        resolvedData={{ [TAG_ID]: resolved }}
        assets={{ hot: 'https://cdn/hot.png' }}
        featureIcons={FEATURE_ICONS}
      />,
    );
    const imgs = Array.from(container.querySelectorAll('img'));
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Hot']);
    expect(parseFloat(imgs[0].style.left)).toBe(0);
  });
});
