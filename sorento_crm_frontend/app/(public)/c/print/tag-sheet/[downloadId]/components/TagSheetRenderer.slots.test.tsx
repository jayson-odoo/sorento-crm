/**
 * PRICETAG-COMBO-RENDER AC-A4: the print page resolves positions through the same `subjectOf`
 * as the canvas, so the text it prints for each shape equals the canvas's `layerText`.
 *
 * Written test-FIRST. The renderer ignores `subjectSlot` today, so it prints the main product
 * where a position's own product belongs.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { layerText } from '@/lib/dealer-kit/product-block';
import type { LineTagData, TagLayer, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';
const part = (code: string) => ({
  product_id: `id-${code}`,
  code,
  name: code,
  dimensions: '',
  list_price: 100,
  sell_price: null,
  images: [],
  price_tag_description: null,
});

const S1 = {
  fixed: [],
  groups: [
    {
      role: 'Kitchen tap',
      size: 5,
      picks: [part('SRTKT1863SS'), part('SRTKT1862SS'), part('SRTKT1871SS')],
    },
  ],
  upgrades: [{ ...part('SRTKT71SS'), chosen: false }],
};
const S2 = { fixed: [part('SRTWT7449-BL')], groups: [], upgrades: [] };
const S3 = {
  fixed: [],
  groups: [{ role: 'Tap colour', size: 2, picks: [part('SRTWT7449-BL'), part('SRTWT7449-RG')] }],
  upgrades: [],
};
const S4 = { fixed: [part('SRTMCB8083-BL'), part('SRTWT6203-GM')], groups: [], upgrades: [] };
const S5 = { ...S1, upgrades: [{ ...part('SRTKT71SS'), chosen: true }] };

function resolved(slots: unknown): ResolvedLineData {
  return {
    tag_id: TAG_ID,
    tag_label: '1a',
    line_id: 'line-1',
    code: 'SRTKS7061',
    name: 'Host',
    dimensions: '',
    spec_lines: '',
    set_members: '',
    list_price: null,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    parts: [],
    slots,
  } as unknown as ResolvedLineData;
}

function codeLayer(slot: unknown): TagLayer {
  return {
    id: 'l1',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 45,
    height_mm: 17,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: 'code',
    text_override: null,
    props: {
      kind: 'text',
      text: 'placeholder',
      fontFamily: 'Inter',
      fontSize: 10,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
      subjectSlot: slot,
    },
  } as unknown as TagLayer;
}

function docWith(layer: TagLayer): TagSheetDoc {
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
  };
}

const CASES: [string, unknown, unknown, string][] = [
  ['S1 pick 0', S1, { kind: 'pick', group: 0, index: 0 }, 'SRTKT1863SS'],
  ['S1 pick 2', S1, { kind: 'pick', group: 0, index: 2 }, 'SRTKT1871SS'],
  ['S1 upgrade 0', S1, { kind: 'upgrade', index: 0 }, 'SRTKT71SS'],
  ['S2 fixed 0', S2, { kind: 'fixed', index: 0 }, 'SRTWT7449-BL'],
  ['S3 pick 1', S3, { kind: 'pick', group: 0, index: 1 }, 'SRTWT7449-RG'],
  ['S4 fixed 1', S4, { kind: 'fixed', index: 1 }, 'SRTWT6203-GM'],
  ['S5 upgrade 0', S5, { kind: 'upgrade', index: 0 }, 'SRTKT71SS'],
  ['S1 main', S1, { kind: 'main' }, 'SRTKS7061'],
];

describe('the print page prints a position the way the canvas does', () => {
  it.each(CASES)('%s', (_name, slots, slot, expected) => {
    const layer = codeLayer(slot);
    const canvas = layerText(layer, { kind: 'line', line: resolved(slots) as unknown as LineTagData });
    expect(canvas).toBe(expected);
    render(<TagSheetRenderer doc={docWith(layer)} resolvedData={{ [TAG_ID]: resolved(slots) }} />);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it('a position the line has not filled prints no code, never the main product', () => {
    const layer = codeLayer({ kind: 'pick', group: 0, index: 4 });
    const canvas = layerText(layer, { kind: 'line', line: resolved(S1) as unknown as LineTagData });
    render(<TagSheetRenderer doc={docWith(layer)} resolvedData={{ [TAG_ID]: resolved(S1) }} />);
    expect(canvas).not.toContain('SRTKS7061');
    expect(screen.queryByText('SRTKS7061')).toBeNull();
  });
});

describe('an empty price or picture prints nothing (AC-A3)', () => {
  const priceLayer = (showCurrency: boolean | undefined, slot: unknown): TagLayer => {
    const base = codeLayer(slot);
    return {
      ...base,
      slot_binding: 'list_price',
      props: { ...(base.props as object), showCurrency },
    } as unknown as TagLayer;
  };

  it('a price with showCurrency prints RM and the figure, and no RM when the price is empty', () => {
    const slots = { fixed: [part('A')], groups: [], upgrades: [] };
    const layer = priceLayer(true, { kind: 'fixed', index: 0 });
    const { container, unmount } = render(
      <TagSheetRenderer doc={docWith(layer)} resolvedData={{ [TAG_ID]: resolved(slots) }} />,
    );
    expect(container.textContent).toContain('RM 100');
    unmount();
    const empty = render(
      <TagSheetRenderer
        doc={docWith(priceLayer(true, { kind: 'fixed', index: 3 }))}
        resolvedData={{ [TAG_ID]: resolved(slots) }}
      />,
    );
    expect(empty.container.textContent).not.toContain('RM');
    expect(empty.container.textContent).not.toContain('placeholder');
  });

  const imageLayer = (slot: unknown): TagLayer =>
    ({
      ...codeLayer(slot),
      type: 'image',
      slot_binding: 'product_image',
      props: { kind: 'image', source: null, fit: 'contain', subjectSlot: slot },
    }) as unknown as TagLayer;

  it('a picture with no photo draws no box and no img', () => {
    const slots = { fixed: [part('A')], groups: [], upgrades: [] };
    const { container } = render(
      <TagSheetRenderer
        doc={docWith(imageLayer({ kind: 'fixed', index: 0 }))}
        resolvedData={{ [TAG_ID]: resolved(slots) }}
      />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.innerHTML).not.toContain('#f5f5f5');
    expect(container.innerHTML).not.toContain('rgb(245, 245, 245)');
  });
});

describe('a per-position merge field prints what the preview draws (O1)', () => {
  it('prints {{slot.fixed.2.code}} and is empty for a position the line lacks', () => {
    const base = codeLayer(undefined);
    const textLayer = (text: string): TagLayer =>
      ({
        ...base,
        slot_binding: null,
        props: { ...(base.props as object), text },
      }) as unknown as TagLayer;
    const layer = textLayer('A {{slot.fixed.1.code}} B {{slot.fixed.2.code}} C {{slot.fixed.3.code}}');
    const data = { kind: 'line' as const, line: resolved(S4) as unknown as LineTagData };
    expect(layerText(layer, data)).toBe('A SRTMCB8083-BL B SRTWT6203-GM C ');
    const { container } = render(<TagSheetRenderer doc={docWith(layer)} resolvedData={{ [TAG_ID]: resolved(S4) }} />);
    expect(container.textContent?.replace(/\s+/g, ' ')).toContain('A SRTMCB8083-BL B SRTWT6203-GM C');
    expect(container.textContent).not.toContain('{{');
  });
});
