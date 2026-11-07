/**
 * PRICETAG-ACCESSORIES (review S5): the print page draws the "Accessories" box with the SAME layout
 * the canvas uses (`accessoryBoxLayout`, A10): nothing at all for an empty list (A7), whole cards
 * only and a frame closed up around them (A5/A6), product entries as code / description / LP.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { accessoryBoxLayout } from '@/lib/dealer-kit/accessory-box';
import {
  defaultAccessoriesProps,
  type TagAccessory,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';
const item = (name: string, spec: string | null = null): TagAccessory => ({ id: name, name, spec, image: null });

function resolved(accessories: TagAccessory[] | undefined): ResolvedLineData {
  return {
    tag_id: TAG_ID,
    tag_label: '1a',
    line_id: 'line-1',
    code: 'SRTKS7846',
    name: 'SRTKS7846',
    dimensions: '',
    spec_lines: '',
    set_members: '',
    list_price: 100,
    sell_price: null,
    show_promo_price: false,
    included_accessories: '',
    quantity: 1,
    ...(accessories ? { accessories } : {}),
  } as unknown as ResolvedLineData;
}

function docWith(height_mm: number): TagSheetDoc {
  const layer = {
    id: 'acc',
    type: 'accessories',
    x_mm: 3,
    y_mm: 4,
    width_mm: 45,
    height_mm,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultAccessoriesProps(),
  } as unknown as TagLayer;
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

function renderIt(doc: TagSheetDoc, data: ResolvedLineData) {
  return render(<TagSheetRenderer doc={doc} resolvedData={{ [TAG_ID]: data }} assets={{}} />);
}

const THREE = [item('CHOPPING BOARD'), item('COLANDER', '390x300x140, Depth: 160mm'), item('DRAINER', '390x300x140, Depth: 160mm')];

describe('TagSheetRenderer, accessories box', () => {
  it('prints nothing at all for an empty list, or a row pinned before lists existed (A7)', () => {
    renderIt(docWith(60), resolved([]));
    expect(screen.queryByTestId('accessories-box')).toBeNull();
    renderIt(docWith(60), resolved(undefined));
    expect(screen.queryByTestId('accessories-box')).toBeNull();
  });

  it('prints every card in order with the frame closed up around them (A5)', () => {
    renderIt(docWith(80), resolved(THREE));
    const box = screen.getByTestId('accessories-box');
    expect(box.textContent).toContain('ACCESSORIES INCLUDED');
    const text = box.textContent ?? '';
    expect(text.indexOf('CHOPPING BOARD')).toBeLessThan(text.indexOf('COLANDER'));
    expect(text.indexOf('COLANDER')).toBeLessThan(text.indexOf('DRAINER'));
    const expected = accessoryBoxLayout(3, defaultAccessoriesProps(), 45, 80, 2).boxHeight_mm;
    expect(box.style.height).toBe(`${expected}mm`);
  });

  it('prints only the whole cards that fit (A6)', () => {
    const one = accessoryBoxLayout(1, defaultAccessoriesProps(), 45, 200, 2).boxHeight_mm;
    renderIt(docWith(one + 1), resolved(THREE));
    const text = screen.getByTestId('accessories-box').textContent ?? '';
    expect(text).toContain('CHOPPING BOARD');
    expect(text).not.toContain('COLANDER');
  });

  it('prints a product entry as code, description and LP', () => {
    renderIt(
      docWith(60),
      resolved([
        { kind: 'product', id: 'p', name: 'Popup Waste 80mm (w/o Overflow) Brass', spec: null, image: null, code: 'SRTW5000', list_price: 68 },
      ]),
    );
    const text = screen.getByTestId('accessories-box').textContent ?? '';
    expect(text).toContain('SRTW5000');
    expect(text).toContain('Popup Waste 80mm (w/o Overflow) Brass');
    expect(text).toContain('LP: RM 68');
  });
});

describe('TagSheetRenderer, header at 45 mm (crew pass 2)', () => {
  it('prints the whole header at the layout font size, never an ellipsis', () => {
    renderIt(docWith(80), resolved(THREE));
    const header = screen.getByTestId('accessories-header');
    expect(header.textContent).toBe('ACCESSORIES INCLUDED');
    const box = accessoryBoxLayout(3, defaultAccessoriesProps(), 45, 80, 2);
    expect(header.style.fontSize).toBe(`${box.header!.fontSize_pt}pt`);
    expect(header.style.textOverflow).toBe('');
    expect(header.style.overflow).toBe('');
  });
});
