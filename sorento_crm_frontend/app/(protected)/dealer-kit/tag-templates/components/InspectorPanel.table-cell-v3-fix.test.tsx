/**
 * SPEC-SHEET-PARITY-B2 v3 fix round (browser F3, review S1): the table Inspector's Row height and
 * Column width are real millimetres, shown to 0.1 mm.
 *
 * - F3: a stored 26.700000762939453 shows as 26.7.
 * - S1: stored column widths are relative (the layout scales them to the table width); the box shows
 *   the printed mm and writes back through the same scale, the right-hand neighbour (the left one
 *   for the last column) giving up the width so the table keeps its width, as the edge drag does.
 *   A one-column table's Column width is the table's width. Row height never goes below 2 mm
 *   (the edge drag's minimum). Written test-FIRST.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const side = { color: '#000000', width_mm: 0.2 };
const cell = (text: string) => ({ text, padding_mm: 1, border: { top: side, right: side, bottom: side, left: side } });

function tableLayer(width_mm: number, columns: number[], rows: number[]): TagLayer {
  return {
    id: 'tbl',
    type: 'table',
    x_mm: 0,
    y_mm: 0,
    width_mm,
    height_mm: 30,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'table',
      columns: columns.map((width) => ({ width_mm: width })),
      rows: rows.map((height) => ({ height_mm: height })),
      cells: rows.map(() => columns.map(() => cell(''))),
      fontFamily: 'DM Sans',
      fontSize: 8,
      color: '#000000',
      align: 'left',
      verticalAlign: 'top',
    },
  } as unknown as TagLayer;
}

function mount(layer: TagLayer, tableCell = { row: 0, col: 0 }) {
  const onUpdate = vi.fn();
  const onUpdateProps = vi.fn();
  render(
    <InspectorPanel
      layer={layer}
      onUpdate={onUpdate}
      onUpdateProps={onUpdateProps}
      tableCell={tableCell}
      onInsertField={vi.fn()}
    />,
  );
  return { onUpdate, onUpdateProps };
}

const box = (name: RegExp) => screen.getByLabelText(name) as HTMLInputElement;

describe('Row height shows to 0.1 mm (browser F3)', () => {
  it('a float32 height reads 26.7', () => {
    mount(tableLayer(60, [60], [26.700000762939453]));
    expect(box(/^Row height/).value).toBe('26.7');
  });

  it('never writes a row below 2 mm', () => {
    const { onUpdateProps } = mount(tableLayer(60, [60], [6]));
    fireEvent.change(box(/^Row height/), { target: { value: '1' } });
    for (const [, changes] of onUpdateProps.mock.calls) {
      const rows = (changes as { rows?: { height_mm: number }[] }).rows;
      if (rows) expect(rows[0].height_mm).toBeGreaterThanOrEqual(2);
    }
  });
});

describe('Column width is printed millimetres (review S1)', () => {
  // 120 mm table, stored 20 / 40: printed 40 / 80.
  it('shows the printed width, not the stored relative one', () => {
    mount(tableLayer(120, [20, 40], [6]), { row: 0, col: 1 });
    expect(box(/^Column width/).value).toBe('80');
  });

  it('writes back through the scale; the neighbour gives the width up, the table total stays', () => {
    const { onUpdateProps } = mount(tableLayer(120, [20, 40], [6]), { row: 0, col: 0 });
    fireEvent.change(box(/^Column width/), { target: { value: '50' } });
    const [, changes] = onUpdateProps.mock.calls.at(-1)!;
    expect((changes as { columns: { width_mm: number }[] }).columns.map((c) => c.width_mm)).toEqual([25, 35]);
  });

  it('the last column takes from its left neighbour', () => {
    const { onUpdateProps } = mount(tableLayer(60, [30, 30], [6]), { row: 0, col: 1 });
    fireEvent.change(box(/^Column width/), { target: { value: '20' } });
    const [, changes] = onUpdateProps.mock.calls.at(-1)!;
    expect((changes as { columns: { width_mm: number }[] }).columns.map((c) => c.width_mm)).toEqual([40, 20]);
  });

  it('a column never goes below 5 mm and never takes the neighbour below 5 mm', () => {
    const { onUpdateProps } = mount(tableLayer(60, [30, 30], [6]), { row: 0, col: 0 });
    fireEvent.change(box(/^Column width/), { target: { value: '58' } });
    const [, changes] = onUpdateProps.mock.calls.at(-1)!;
    expect((changes as { columns: { width_mm: number }[] }).columns.map((c) => c.width_mm)).toEqual([55, 5]);
  });

  it('on a one-column table (the title block) the Column width is the table width', () => {
    const { onUpdate } = mount(tableLayer(50, [60], [6]), { row: 0, col: 0 });
    expect(box(/^Column width/).value).toBe('50');
    fireEvent.change(box(/^Column width/), { target: { value: '45' } });
    expect(onUpdate).toHaveBeenCalledWith('tbl', { width_mm: 45 });
  });
});
