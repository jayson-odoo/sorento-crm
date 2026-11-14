/**
 * SPEC-SHEET-PARITY-B2 v3 editor, AC-C4.1 / AC-C5.2 on the PRINT page and in the PowerPoint layout
 * export. Written test-FIRST.
 *
 * - Header row (table prop `headerRow: true`): row 1 prints bold on a light shade; the cell's own
 *   fill wins; other rows stay plain.
 * - ALL CAPS (table prop `uppercase: true`, text layer prop `uppercase: true`): printed in capitals,
 *   either as transformed text or as CSS `text-transform: uppercase`; stored text is unchanged.
 * - The layout export (`window.__tagSheetLayout`, read by the PowerPoint worker) carries
 *   `headerRow` / `uppercase` on the table and `uppercase` on the text layer.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { TagLayer, TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

const TAG_ID = 'tag-1';

function tableProps(extra: Record<string, unknown> = {}) {
  const side = { color: '#000000', width_mm: 0.2 };
  const cell = (text: string, more: Record<string, unknown> = {}) => ({
    text,
    padding_mm: 1,
    border: { top: side, right: side, bottom: side, left: side },
    ...more,
  });
  return {
    kind: 'table' as const,
    columns: [{ width_mm: 30 }, { width_mm: 30 }],
    rows: [{ height_mm: 6 }, { height_mm: 6 }],
    cells: [
      [cell('Ref'), cell('Value', { fill: '#ff0000' })],
      [cell('Code'), cell('Mixed case')],
    ],
    fontFamily: 'DM Sans',
    fontSize: 10,
    color: '#000000',
    align: 'left',
    verticalAlign: 'middle',
    ...extra,
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

const TEXT = {
  kind: 'text',
  text: 'Wall hung water closet',
  fontFamily: 'DM Sans',
  fontSize: 12,
  fontWeight: 400,
  color: '#000000',
  align: 'left',
  lineHeight: 1.2,
  letterSpacing: 0,
};

function docWith(layers: TagLayer[]): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'custom', page_width_mm: 338.7, page_height_mm: 190.5, bleed_mm: 0, gap_mm: 0 },
    sheets: [
      {
        id: 's1',
        tags: [
          { id: 't1', template_id: 'tpl', request_tag_id: TAG_ID, x_mm: 0, y_mm: 0, width_mm: 338.7, height_mm: 190.5, layers },
        ],
      },
    ],
  } as unknown as TagSheetDoc;
}

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

function renderIt(layers: TagLayer[]) {
  return render(<TagSheetRenderer doc={docWith(layers)} resolvedData={{ [TAG_ID]: DATA }} assets={{}} />);
}

const isBold = (el: HTMLElement) => {
  const own = el.style.fontWeight;
  const inner = Array.from(el.querySelectorAll<HTMLElement>('*')).map((n) => n.style.fontWeight);
  const tags = el.querySelector('b, strong') !== null;
  return tags || [own, ...inner].some((w) => w === 'bold' || Number(w) >= 600);
};

/** Printed in capitals: the text itself, or CSS text-transform on the element or an ancestor. */
function showsUpper(el: HTMLElement, stored: string) {
  const text = el.textContent ?? '';
  if (text.includes(stored.toUpperCase())) return true;
  for (let node: HTMLElement | null = el; node; node = node.parentElement) {
    if (node.style.textTransform === 'uppercase') return text.includes(stored);
  }
  return false;
}

describe('print: Header row (AC-C4.1)', () => {
  it('row 1 prints bold, the other rows do not', () => {
    renderIt([layer('tbl', 'table', tableProps({ headerRow: true }), 30)]);
    expect(isBold(screen.getByTestId('table-cell-0-0'))).toBe(true);
    expect(isBold(screen.getByTestId('table-cell-0-1'))).toBe(true);
    expect(isBold(screen.getByTestId('table-cell-1-0'))).toBe(false);
  });

  it('row 1 gets a light shade; the cell own fill wins; other rows have none', () => {
    renderIt([layer('tbl', 'table', tableProps({ headerRow: true }), 30)]);
    expect(screen.getByTestId('table-cell-0-0').style.backgroundColor).not.toBe('');
    expect(screen.getByTestId('table-cell-0-1').style.backgroundColor).toBe('rgb(255, 0, 0)');
    expect(screen.getByTestId('table-cell-1-0').style.backgroundColor).toBe('');
  });

  it('an old table (no headerRow) prints row 1 plain', () => {
    renderIt([layer('tbl', 'table', tableProps(), 30)]);
    expect(isBold(screen.getByTestId('table-cell-0-0'))).toBe(false);
    expect(screen.getByTestId('table-cell-0-0').style.backgroundColor).toBe('');
  });
});

describe('print: ALL CAPS (AC-C5.2)', () => {
  it('a table with uppercase prints its cells in capitals', () => {
    renderIt([layer('tbl', 'table', tableProps({ uppercase: true }), 30)]);
    expect(showsUpper(screen.getByTestId('table-cell-1-1'), 'Mixed case')).toBe(true);
  });

  it('a table without uppercase keeps the case', () => {
    renderIt([layer('tbl', 'table', tableProps(), 30)]);
    const el = screen.getByTestId('table-cell-1-1');
    expect(el.textContent).toContain('Mixed case');
    expect(showsUpper(el, 'Mixed case')).toBe(false);
  });

  it('a text layer with uppercase prints in capitals', () => {
    const { container } = renderIt([layer('txt', 'text', { ...TEXT, uppercase: true }, 4)]);
    const holder = Array.from(container.querySelectorAll<HTMLElement>('div')).find((d) =>
      (d.textContent ?? '').toLowerCase().includes('wall hung'),
    );
    expect(holder).toBeTruthy();
    const deepest = Array.from(holder!.querySelectorAll<HTMLElement>('*'))
      .filter((d) => (d.textContent ?? '').toLowerCase().includes('wall hung'))
      .pop() ?? holder!;
    expect(showsUpper(deepest, 'Wall hung water closet')).toBe(true);
  });
});

describe('layout export for PowerPoint carries the flags (AC-C4.1, AC-C5.2)', () => {
  type Exposed = { pages: { layers: Record<string, unknown>[] }[] };
  const exposed = () => (window as unknown as { __tagSheetLayout?: Exposed }).__tagSheetLayout;

  afterEach(() => {
    delete (window as unknown as { __tagSheetLayout?: unknown }).__tagSheetLayout;
    window.history.replaceState({}, '', '/');
  });

  it('a table exports headerRow and uppercase; a text layer exports uppercase', async () => {
    window.history.replaceState({}, '', '/?layout=1');
    renderIt([
      layer('txt', 'text', { ...TEXT, uppercase: true }, 4),
      layer('tbl', 'table', tableProps({ headerRow: true, uppercase: true }), 30),
    ]);
    await waitFor(() => expect(exposed()).toBeTruthy());
    const layers = exposed()!.pages[0].layers;
    const table = layers.find((l) => l.kind === 'table')!;
    const text = layers.find((l) => l.kind === 'text')!;
    expect(table.headerRow).toBe(true);
    expect(table.uppercase).toBe(true);
    expect(text.uppercase).toBe(true);
  });
});
