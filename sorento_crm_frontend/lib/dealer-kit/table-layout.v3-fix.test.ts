/**
 * SPEC-SHEET-PARITY-B2 v3 fix round, review N4: a Header row prints bold, so its text is measured
 * bold (wider), and a header line that only just fits plain wraps when bold. Also the shared
 * anchor lookup (review B3): a picked position resolves to the laid-out cell that owns it, clamped
 * into the grid. Written test-FIRST.
 */
import { describe, expect, it } from 'vitest';

import type { TableLayerProps } from './tag-template-types';
import { cellAnchor, tableLayout, tableMeasure } from './table-layout';

function table(extra: Partial<TableLayerProps> = {}): TableLayerProps {
  return {
    kind: 'table',
    columns: [{ width_mm: 30 }],
    rows: [{ height_mm: 2 }, { height_mm: 2 }],
    // 14 characters: one line at 10 pt in a 28 mm text width plain, two lines bold.
    cells: [[{ text: 'ABCDEFGHIJKLMN', padding_mm: 1 }], [{ text: 'ABCDEFGHIJKLMN', padding_mm: 1 }]],
    fontSize: 10,
    ...extra,
  };
}

describe('a bold header row is measured bold (review N4)', () => {
  it('row 1 is taller with Header row on; row 2 is unchanged', () => {
    const plain = tableLayout(table(), 30, tableMeasure(table()));
    const header = tableLayout(table({ headerRow: true }), 30, tableMeasure(table({ headerRow: true })));
    expect(header.rowHeights_mm[0]).toBeGreaterThan(plain.rowHeights_mm[0]);
    expect(header.rowHeights_mm[1]).toBeCloseTo(plain.rowHeights_mm[1], 6);
  });
});

describe('cellAnchor (review B3)', () => {
  const grid = (): TableLayerProps => ({
    kind: 'table',
    columns: [{ width_mm: 10 }, { width_mm: 10 }],
    rows: [{ height_mm: 5 }, { height_mm: 5 }],
    cells: [
      [{ text: 'a', colSpan: 2 }, { text: '' }],
      [{ text: 'c' }, { text: 'd' }],
    ],
  });

  it('a covered position resolves to the merge that owns it', () => {
    expect(cellAnchor(grid(), 0, 1)).toEqual({ row: 0, col: 0 });
  });

  it('a position past the grid (a deleted row or column) is clamped into it', () => {
    expect(cellAnchor(grid(), 5, 1)).toEqual({ row: 1, col: 1 });
    expect(cellAnchor(grid(), 1, 9)).toEqual({ row: 1, col: 1 });
  });

  it('a plain position is itself', () => {
    expect(cellAnchor(grid(), 1, 0)).toEqual({ row: 1, col: 0 });
  });
});
