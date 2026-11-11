/**
 * SPEC-SHEET-DESIGNER-PARITY B5: after render the print page exposes the resolved per-page layers
 * on `window.__tagSheetLayout = { page_mm: [w, h], pages: [{ layers: [...] }] }`, for the
 * PowerPoint worker. Text has merge fields applied; a table carries its cells and its border edges
 * from `tableLayout`. Written test-FIRST.
 */
import { render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { TagLayer, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

type Exposed = {
  page_mm: [number, number];
  pages: { layers: Record<string, unknown>[] }[];
};
const exposed = () => (window as unknown as { __tagSheetLayout?: Exposed }).__tagSheetLayout;

afterEach(() => {
  delete (window as unknown as { __tagSheetLayout?: unknown }).__tagSheetLayout;
});

function tableProps() {
  const none = { color: '#000000', width_mm: 0 };
  const red = { color: '#ff0000', width_mm: 0.5 };
  const cell = (text: string, border = {}) => ({
    text,
    padding_mm: 1,
    border: { top: none, right: none, bottom: none, left: none, ...border },
  });
  return {
    kind: 'table' as const,
    columns: [{ width_mm: 30 }, { width_mm: 30 }],
    rows: [{ height_mm: 6 }, { height_mm: 6 }],
    cells: [
      [cell('REF', { top: red }), cell('{{doc.ref}}', { top: red })],
      [cell('A'), cell('B')],
    ],
    fontFamily: 'DM Sans',
    fontSize: 10,
    color: '#000000',
    align: 'left',
    verticalAlign: 'middle',
  };
}

function layer(id: string, type: string, props: Record<string, unknown>, y_mm: number): TagLayer {
  return {
    id,
    type,
    x_mm: 3,
    y_mm,
    width_mm: 60,
    height_mm: 12,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props,
  } as unknown as TagLayer;
}

const DOC = {
  kind: 'tag_sheet',
  imposition: { preset: 'custom', page_width_mm: 338.7, page_height_mm: 190.5, bleed_mm: 0, gap_mm: 0 },
  sheets: [
    {
      id: 's1',
      tags: [
        {
          id: 't1',
          template_id: 'tpl',
          request_tag_id: TAG_ID,
          x_mm: 0,
          y_mm: 0,
          width_mm: 338.7,
          height_mm: 190.5,
          layers: [
            layer(
              'txt',
              'text',
              { kind: 'text', text: 'Ref {{doc.ref}}', fontFamily: 'DM Sans', fontSize: 12, color: '#112233', align: 'left', fontWeight: 700 },
              4,
            ),
            layer('tbl', 'table', tableProps(), 30),
          ],
        },
      ],
    },
  ],
} as unknown as TagSheetDoc;

const DATA = {
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

describe('window.__tagSheetLayout', () => {
  it('carries the page size and one entry per page', async () => {
    render(<TagSheetRenderer doc={DOC} resolvedData={{ [TAG_ID]: DATA }} assets={{}} />);
    await waitFor(() => expect(exposed()).toBeTruthy());
    expect(exposed()!.page_mm).toEqual([338.7, 190.5]);
    expect(exposed()!.pages).toHaveLength(1);
  });

  it('exposes text with its merge fields applied, its box and style', async () => {
    render(<TagSheetRenderer doc={DOC} resolvedData={{ [TAG_ID]: DATA }} assets={{}} />);
    await waitFor(() => expect(exposed()).toBeTruthy());
    const text = exposed()!.pages[0].layers.find((l) => l.kind === 'text');
    expect(text).toMatchObject({ text: 'Ref Q-2026-001', x_mm: 3, y_mm: 4, fontFamily: 'DM Sans', fontSize: 12 });
    expect(String(text!.color).toLowerCase()).toBe('#112233');
  });

  it('exposes a table with resolved cell text and its border edges', async () => {
    render(<TagSheetRenderer doc={DOC} resolvedData={{ [TAG_ID]: DATA }} assets={{}} />);
    await waitFor(() => expect(exposed()).toBeTruthy());
    const table = exposed()!.pages[0].layers.find((l) => l.kind === 'table') as Record<string, unknown>;
    expect(table).toBeTruthy();
    expect(table.columns_mm).toEqual([30, 30]);
    const cells = table.cells as { row: number; col: number; text: string }[];
    expect(cells.find((c) => c.row === 0 && c.col === 1)?.text).toBe('Q-2026-001');
    const edges = table.edges as { color: string; width_mm: number; y1_mm: number; y2_mm: number }[];
    const red = edges.filter((e) => e.color.toLowerCase() === '#ff0000');
    expect(red.length).toBeGreaterThan(0);
    expect(red.every((e) => e.y1_mm === e.y2_mm && e.width_mm === 0.5)).toBe(true);
    // Zero-width borders draw nothing.
    expect(edges.every((e) => e.width_mm > 0)).toBe(true);
  });
});
