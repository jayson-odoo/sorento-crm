/**
 * B review: a table colour that is not a plain colour never reaches a CSS value (a `url(...)` would
 * make the headless browser fetch it). Written test-FIRST.
 *
 * DOM contract (no table drawing exists yet): the layer renders `data-testid="table-layer"`, each
 * laid-out cell is `data-testid="table-cell-{row}-{col}"` carrying its resolved text and its
 * per-side borders as CSS (`border-*-color`), and a covered (merged-away) cell is not emitted.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TagLayer, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

/** A 2-column table fixture written out here so this file does not depend on the layout module. */
function tableProps(rows: number, cols: number, width: number) {
  const side = { color: '#000000', width_mm: 0.2 };
  const blank = () => ({ text: '', padding_mm: 1, border: { top: side, right: side, bottom: side, left: side } });
  return {
    kind: 'table' as const,
    columns: Array.from({ length: cols }, () => ({ width_mm: width / cols })),
    rows: Array.from({ length: rows }, () => ({ height_mm: 6 })),
    cells: Array.from({ length: rows }, () => Array.from({ length: cols }, blank)),
    fontFamily: 'DM Sans',
    fontSize: 10,
    color: '#000000',
    align: 'left',
    verticalAlign: 'middle',
  };
}

function resolved(): ResolvedLineData {
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
    doc: { ref: 'Q-2026-001' },
  } as unknown as ResolvedLineData;
}

function docWith(mutate?: (props: ReturnType<typeof tableProps>) => void): TagSheetDoc {
  const props = tableProps(2, 2, 60);
  props.cells[0][0].text = 'REF';
  props.cells[0][1].text = '{{doc.ref}}';
  props.cells[0][1].border = {
    ...props.cells[0][1].border,
    top: { color: '#ff0000', width_mm: 0.5 },
  };
  mutate?.(props);
  const layer = {
    id: 'tbl',
    type: 'table',
    x_mm: 3,
    y_mm: 4,
    width_mm: 60,
    height_mm: 20,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props,
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

function renderIt(doc: TagSheetDoc) {
  return render(<TagSheetRenderer doc={doc} resolvedData={{ [TAG_ID]: resolved() }} assets={{}} />);
}

describe('TagSheetRenderer, table colours', () => {
  const EVIL = 'url(http://169.254.169.254/latest/meta-data)';

  it('a url() cell fill, border colour or text colour renders no url in the DOM', () => {
    const { container } = renderIt(
      docWith((props) => {
        props.cells[0][0] = {
          ...props.cells[0][0],
          fill: EVIL,
          border: { top: { color: EVIL, width_mm: 0.4 } },
        } as never;
        (props as { color: string }).color = EVIL;
      }),
    );
    expect(container.innerHTML).not.toContain('169.254');
    expect(container.innerHTML).not.toContain('url(');
  });

  it('a plain colour still draws', () => {
    renderIt(
      docWith((props) => {
        props.cells[0][0] = { ...props.cells[0][0], fill: '#eeeeee' } as never;
      }),
    );
    expect(screen.getByTestId('table-cell-0-0')).toHaveStyle({ backgroundColor: '#eeeeee' });
  });
});
