/**
 * PRICETAG-ACCESSORY-DESIGNER fix round (security): a designed card's colours reach CSS through
 * `safeColour`, so a `url(...)` (or any non-colour) fill never becomes a style value.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  defaultAccessoriesProps,
  type TagAccessory,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

function mount(props: Record<string, unknown>) {
  const layer = {
    id: 'acc', type: 'accessories', x_mm: 3, y_mm: 4, width_mm: 60, height_mm: 80, rotation_deg: 0,
    z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultAccessoriesProps(), ...props },
  } as unknown as TagLayer;
  const doc = {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [{ id: 's1', tags: [{ id: 't1', template_id: 'tpl', request_tag_id: TAG_ID, x_mm: 5, y_mm: 5, width_mm: 148, height_mm: 105, layers: [layer] }] }],
  } as TagSheetDoc;
  const data = {
    tag_id: TAG_ID, tag_label: '1a', line_id: 'l', code: 'X', name: 'X', dimensions: '', spec_lines: '',
    set_members: '', list_price: 1, sell_price: null, show_promo_price: false, included_accessories: '', quantity: 1,
    accessories: [{ id: 'a', name: 'COLANDER', spec: null, image: null, colours: [{ name: 'Bad', hex: 'url(x)' }] } as TagAccessory],
  } as unknown as ResolvedLineData;
  return render(<TagSheetRenderer doc={doc} resolvedData={{ [TAG_ID]: data }} assets={{}} />);
}

describe('TagSheetRenderer, designed card colours', () => {
  it('ignores a url() fill, stroke, card fill and dot colour', () => {
    const { container } = mount({
      fill: 'url(https://evil.test/a)',
      stroke: 'url(https://evil.test/b)',
      cardFill: 'url(https://evil.test/c)',
      card: {
        width_mm: 30, height_mm: 20,
        elements: [
          { id: 'dots', kind: 'colour_dots', field: 'colours', x_mm: 0, y_mm: 0, width_mm: 20, height_mm: 4, dotOutline: 'url(https://evil.test/d)' },
          { id: 'r', kind: 'shape', shape: 'rect', x_mm: 0, y_mm: 6, width_mm: 5, height_mm: 5, fill: 'url(https://evil.test/e)' },
        ],
      },
    });
    expect(screen.getByTestId('accessories-box')).toBeInTheDocument();
    expect(container.innerHTML).not.toContain('evil.test');
    expect(container.innerHTML).not.toContain('url(');
  });

  it('keeps a real fill', () => {
    mount({ fill: '#f3f7f4', card: { width_mm: 30, height_mm: 20, elements: [] } });
    expect((screen.getByTestId('accessories-frame') as HTMLElement).style.backgroundColor).toBe('rgb(243, 247, 244)');
  });
});
