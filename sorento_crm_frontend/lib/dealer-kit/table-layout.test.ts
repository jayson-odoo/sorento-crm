/**
 * SPEC-SHEET-DESIGNER-PARITY B4: the table element's one layout module, used by the canvas and the
 * print page. Written test-FIRST (`lib/dealer-kit/table-layout.ts` does not exist yet).
 *
 * Contract assumption: `insertRow(props, at)` / `insertColumn(props, at)` put the NEW row/column
 * at index `at` (the old one at `at` moves down/right); the menu's "below"/"right" passes r+1.
 */
import { describe, expect, it } from 'vitest';

import {
  defaultTableProps,
  deleteColumn,
  deleteRow,
  insertColumn,
  insertRow,
  mergeCells,
  tableLayout,
  unmergeCell,
} from './table-layout';

type Props = ReturnType<typeof defaultTableProps>;

const cell = (text: string) => ({ text, padding_mm: 1 });

function grid(): Props {
  return {
    ...defaultTableProps(2, 2, 40),
    columns: [{ width_mm: 20 }, { width_mm: 20 }],
    rows: [{ height_mm: 5 }, { height_mm: 5 }],
    cells: [
      [cell('A'), cell('B')],
      [cell('C'), cell('D')],
    ],
  } as Props;
}

/** 3 mm per character-less call; a taller fake for the text 'TALL'. */
const measure = (text: string) => (text === 'TALL' ? 10 : 3);

describe('defaultTableProps', () => {
  it('builds rows x cols of blank cells with equal columns that sum to the layer width', () => {
    const props = defaultTableProps(3, 2, 60);
    expect(props.kind).toBe('table');
    expect(props.rows).toHaveLength(3);
    expect(props.columns).toHaveLength(2);
    expect(props.columns.map((c) => c.width_mm)).toEqual([30, 30]);
    expect(props.cells).toHaveLength(3);
    for (const row of props.cells) {
      expect(row).toHaveLength(2);
      for (const c of row) expect(c.text).toBe('');
    }
  });

  it('has visible black borders and 1 mm padding by default', () => {
    const c = defaultTableProps(1, 1, 20).cells[0][0];
    expect(c.padding_mm).toBe(1);
    for (const side of ['top', 'right', 'bottom', 'left'] as const) {
      expect(c.border?.[side]?.color?.toLowerCase()).toMatch(/^(#000000|#000)$/);
      expect(c.border?.[side]?.width_mm).toBeGreaterThan(0);
    }
  });
});

describe('tableLayout', () => {
  it('places cells row-major and scales the columns to the layer width', () => {
    const out = tableLayout(grid(), 80, measure);
    expect(out.cells.map((c) => [c.row, c.col, c.text])).toEqual([
      [0, 0, 'A'],
      [0, 1, 'B'],
      [1, 0, 'C'],
      [1, 1, 'D'],
    ]);
    expect(out.cells.map((c) => [c.x_mm, c.width_mm])).toEqual([
      [0, 40],
      [40, 40],
      [0, 40],
      [40, 40],
    ]);
  });

  it('keeps the set row height when the text is shorter, grows to measured text plus padding when taller', () => {
    const props = grid();
    props.cells[0][1] = cell('TALL');
    const out = tableLayout(props, 40, measure);
    // Row 0: max(5, 10 + 2 * 1) = 12; row 1: max(5, 3 + 2) = 5.
    expect(out.rowHeights_mm).toEqual([12, 5]);
    expect(out.height_mm).toBe(17);
    expect(out.cells.find((c) => c.row === 1 && c.col === 0)?.y_mm).toBe(12);
    expect(out.cells.find((c) => c.row === 0 && c.col === 0)?.height_mm).toBe(12);
  });

  it('a merged anchor spans the summed width and height, covered cells are skipped', () => {
    const props = grid();
    props.cells[0][0] = { ...cell('A'), colSpan: 2, rowSpan: 2 };
    const out = tableLayout(props, 40, measure);
    expect(out.cells).toHaveLength(1);
    expect(out.cells[0]).toMatchObject({ row: 0, col: 0, x_mm: 0, y_mm: 0, width_mm: 40, height_mm: 10 });
  });

  it('a spanning cell does not force the height of the single row it starts in', () => {
    const props = grid();
    props.cells[0][0] = { ...cell('TALL'), rowSpan: 2 };
    const out = tableLayout(props, 40, measure);
    expect(out.rowHeights_mm[0]).toBe(5);
  });
});

describe('row and column operations', () => {
  it('insertRow puts a blank row at the index and keeps the others', () => {
    const next = insertRow(grid(), 1);
    expect(next.rows).toHaveLength(3);
    expect(next.cells.map((r) => r.map((c) => c.text))).toEqual([['A', 'B'], ['', ''], ['C', 'D']]);
    expect(insertRow(grid(), 2).cells[2].map((c) => c.text)).toEqual(['', '']);
  });

  it('insertColumn puts a blank column at the index', () => {
    const next = insertColumn(grid(), 1);
    expect(next.columns).toHaveLength(3);
    expect(next.cells.map((r) => r.map((c) => c.text))).toEqual([['A', '', 'B'], ['C', '', 'D']]);
  });

  it('deleteRow and deleteColumn remove that line', () => {
    expect(deleteRow(grid(), 0).cells.map((r) => r.map((c) => c.text))).toEqual([['C', 'D']]);
    expect(deleteRow(grid(), 0).rows).toHaveLength(1);
    expect(deleteColumn(grid(), 1).cells.map((r) => r.map((c) => c.text))).toEqual([['A'], ['C']]);
    expect(deleteColumn(grid(), 1).columns).toHaveLength(1);
  });

  it('refuses to delete the last row or the last column (props unchanged)', () => {
    const one = deleteRow(grid(), 1);
    expect(deleteRow(one, 0)).toEqual(one);
    const single = deleteColumn(grid(), 1);
    expect(deleteColumn(single, 0)).toEqual(single);
  });

  it('deleting a row inside a merge shrinks the merge', () => {
    const props = grid();
    props.cells[0][0] = { ...cell('A'), rowSpan: 2 };
    const next = deleteRow(props, 1);
    expect(next.cells[0][0].rowSpan ?? 1).toBe(1);
  });
});

describe('merge and unmerge', () => {
  it('merges a range into its anchor, which keeps the joined text', () => {
    const merged = mergeCells(grid(), 0, 0, 1, 1);
    const out = tableLayout(merged, 40, measure);
    expect(out.cells).toHaveLength(1);
    const text = out.cells[0].text;
    for (const t of ['A', 'B', 'C', 'D']) expect(text).toContain(t);
    expect(text.indexOf('A')).toBeLessThan(text.indexOf('B'));
    expect(text.indexOf('B')).toBeLessThan(text.indexOf('C'));
    expect(text.indexOf('C')).toBeLessThan(text.indexOf('D'));
    expect(out.cells[0]).toMatchObject({ width_mm: 40 });
  });

  it('a range that cuts an existing merge expands to cover it', () => {
    const first = mergeCells(grid(), 0, 0, 0, 1); // A+B across the top
    const next = mergeCells(first, 0, 1, 1, 1); // touches the covered B
    const out = tableLayout(next, 40, measure);
    expect(out.cells).toHaveLength(1); // the whole 2x2 block
  });

  it('unmergeCell restores the covered cells', () => {
    const merged = mergeCells(grid(), 0, 0, 1, 1);
    const out = tableLayout(unmergeCell(merged, 0, 0), 40, measure);
    expect(out.cells).toHaveLength(4);
  });
});
