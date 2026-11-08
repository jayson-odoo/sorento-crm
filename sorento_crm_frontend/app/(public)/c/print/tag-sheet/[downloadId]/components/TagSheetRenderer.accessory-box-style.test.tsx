/**
 * PRICETAG-ACCESSORY-DESIGNER S6: a product or combo on the tag may name its own box style; the print
 * page draws that design in the template's box (position and size kept).
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { accessoryDesign } from '@/lib/dealer-kit/accessory-card';
import {
  defaultAccessoriesProps,
  type TagAccessory,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

function mount(style: unknown) {
  const layer = {
    id: 'acc', type: 'accessories', x_mm: 3, y_mm: 4, width_mm: 60, height_mm: 80, rotation_deg: 0,
    z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultAccessoriesProps(), headerText: 'OWN HEADER', showHeader: true },
  } as unknown as TagLayer;
  const doc = {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [{ id: 's1', tags: [{ id: 't1', template_id: 'tpl', request_tag_id: TAG_ID, x_mm: 5, y_mm: 5, width_mm: 148, height_mm: 105, layers: [layer] }] }],
  } as TagSheetDoc;
  const data = {
    tag_id: TAG_ID, tag_label: '1a', line_id: 'l', code: 'X', name: 'X', dimensions: '', spec_lines: '',
    set_members: '', list_price: 1, sell_price: null, show_promo_price: false, included_accessories: '', quantity: 1,
    accessories: [{ id: 'a', name: 'COLANDER', spec: null, image: null } as TagAccessory],
    accessory_box_style: style,
  } as unknown as ResolvedLineData;
  return render(<TagSheetRenderer doc={doc} resolvedData={{ [TAG_ID]: data }} assets={{}} />);
}

describe('TagSheetRenderer, box style override', () => {
  it('draws the box style the owner names instead of the box\'s own design', () => {
    mount({ id: 's1', name: 'FREE', design: { ...accessoryDesign(defaultAccessoriesProps()), headerText: 'STYLE HEADER', showHeader: true } });
    expect(screen.getByTestId('accessories-header').textContent).toBe('STYLE HEADER');
  });

  it('draws the box\'s own design when no style resolves', () => {
    mount(null);
    expect(screen.getByTestId('accessories-header').textContent).toBe('OWN HEADER');
  });
});
