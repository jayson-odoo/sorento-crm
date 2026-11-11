/**
 * SPEC-SHEET-DESIGNER-PARITY B4: the print page draws a `table` layer. Written test-FIRST.
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

describe('TagSheetRenderer, table layer', () => {
  it('prints the cell text and resolves {{doc.ref}} through the merge fields', () => {
    renderIt(docWith());
    expect(screen.getByTestId('table-layer')).toBeInTheDocument();
    expect(screen.getByTestId('table-cell-0-0').textContent).toContain('REF');
    expect(screen.getByTestId('table-cell-0-1').textContent).toContain('Q-2026-001');
    expect(screen.getByTestId('table-cell-0-1').textContent).not.toContain('{{');
  });

  it('draws a cell border in its own colour', () => {
    renderIt(docWith());
    expect(screen.getByTestId('table-cell-0-1')).toHaveStyle({ borderTopColor: '#ff0000' });
  });

  it('emits one element per laid-out cell and none for a merged-away cell', () => {
    renderIt(
      docWith((props) => {
        props.cells[0][0] = { ...props.cells[0][0], colSpan: 2 };
      }),
    );
    expect(screen.getByTestId('table-cell-0-0')).toBeInTheDocument();
    expect(screen.queryByTestId('table-cell-0-1')).toBeNull();
    expect(screen.getByTestId('table-cell-1-0')).toBeInTheDocument();
  });
});
