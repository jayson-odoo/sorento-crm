/**
 * PRICETAG-ACCESSORIES crew pass (6 Nov): the request designer and the print page draw the same
 * box from the same request row. The designer's canvas resolves a layer through `layerDisplay`
 * (the list) and `accessoryBoxLayout` (the geometry); print must show the same entries, in the
 * same order, in a frame of the same size. An Ala Carte row with no list prints no box at all.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { accessoryBoxLayout, accessoryLineCount } from '@/lib/dealer-kit/accessory-box';
import { layerDisplay } from '@/lib/dealer-kit/product-block';
import {
  defaultAccessoriesProps,
  type LineTagData,
  type TagAccessory,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

const LIST: TagAccessory[] = [
  { kind: 'accessory', id: 'a1', name: 'DRAINER', spec: '390x300x140, Depth: 160mm', image: null },
  {
    kind: 'product',
    id: 'p1',
    name: 'Popup Waste 80mm (w/o Overflow) Brass',
    spec: null,
    image: null,
    code: 'SRTW5000',
    list_price: 68,
  },
];

function row(accessories: TagAccessory[]): ResolvedLineData {
  return {
    tag_id: TAG_ID,
    tag_label: '1a',
    line_id: 'line-1',
    code: 'SRTWB7065',
    name: 'SRTWB7065',
    dimensions: '',
    spec_lines: '',
    set_members: '',
    list_price: 100,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    parts: [],
    open_groups: [],
    specs: [],
    images: [],
    accessories,
  } as unknown as ResolvedLineData;
}

const layer = {
  id: 'acc',
  type: 'accessories',
  x_mm: 3,
  y_mm: 4,
  width_mm: 45,
  height_mm: 60,
  rotation_deg: 0,
  z_index: 1,
  locked: false,
  visible: true,
  slot_binding: null,
  text_override: null,
  props: { ...defaultAccessoriesProps(), headerText: 'FREE' },
} as unknown as TagLayer;

function doc(): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [
      {
        id: 's1',
        tags: [
          { id: 't1', template_id: 'tpl', request_tag_id: TAG_ID, x_mm: 5, y_mm: 5, width_mm: 148, height_mm: 105, layers: [layer] },
        ],
      },
    ],
  } as TagSheetDoc;
}

function designerView(data: ResolvedLineData) {
  const display = layerDisplay(layer, { kind: 'line', line: data as unknown as LineTagData }, {});
  const items = display?.accessories ?? [];
  const props = layer.props as ReturnType<typeof defaultAccessoriesProps>;
  return {
    items,
    box: accessoryBoxLayout(items.length, props, layer.width_mm, layer.height_mm, accessoryLineCount(items)),
  };
}

describe('request designer and print draw the same accessories box', () => {
  it('same entries, same order, same frame size', () => {
    const designer = designerView(row(LIST));
    expect(designer.items.map((i) => i.id)).toEqual(['a1', 'p1']);

    render(<TagSheetRenderer doc={doc()} resolvedData={{ [TAG_ID]: row(LIST) }} assets={{}} />);
    const box = screen.getByTestId('accessories-box');
    expect(box.style.width).toBe(`${designer.box.boxWidth_mm}mm`);
    expect(box.style.height).toBe(`${designer.box.boxHeight_mm}mm`);
    const text = box.textContent ?? '';
    expect(text.indexOf('DRAINER')).toBeLessThan(text.indexOf('SRTW5000'));
    expect(text).toContain('LP: RM 68');
    expect(text).toContain('FREE');
  });

  it('an Ala Carte row with no list: the designer gets an empty list and print draws no box', () => {
    const designer = designerView(row([]));
    expect(designer.items).toEqual([]);
    expect(designer.box.shown).toBe(0);
    render(<TagSheetRenderer doc={doc()} resolvedData={{ [TAG_ID]: row([]) }} assets={{}} />);
    expect(screen.queryByTestId('accessories-box')).toBeNull();
  });
});
