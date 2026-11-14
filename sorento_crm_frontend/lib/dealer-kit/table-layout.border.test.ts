/** SPEC-SHEET-DESIGNER-PARITY B4: editing a cell's border writes both sides of a shared edge. */
import { describe, expect, it } from 'vitest';

import { defaultTableProps, mergeCells, setCellBorder, tableLayout } from './table-layout';

const measure = () => 0;
const RED = { color: '#ff0000', width_mm: 0.6 };

function plain(rows: number, cols: number) {
  const props = defaultTableProps(rows, cols, cols * 20);
  props.cells = props.cells.map((row) => row.map((cell) => ({ ...cell, border: undefined })));
  return props;
}
const sidesOf = (props: ReturnType<typeof plain>, r: number, c: number) => props.cells[r][c].border ?? {};

describe('setCellBorder', () => {
  it("editing the lower cell's top changes the drawn inner edge", () => {
    const base = defaultTableProps(2, 1, 20); // every side set to the default black
    const next = setCellBorder(base, 1, 0, 'top', RED);
    const inner = tableLayout(next, 20, measure).edges.find((e) => e.orientation === 'h' && e.line === 1);
    expect(inner).toMatchObject({ color: '#ff0000', width_mm: 0.6 });
    expect(next.cells[0][0].border?.bottom).toEqual(RED);
  });

  it('all sides of the middle cell of a 3x3 change its neighbours facing sides only', () => {
    const next = setCellBorder(plain(3, 3), 1, 1, 'all', RED);
    expect(sidesOf(next, 1, 1)).toEqual({ top: RED, right: RED, bottom: RED, left: RED });
    expect(sidesOf(next, 0, 1)).toEqual({ bottom: RED });
    expect(sidesOf(next, 2, 1)).toEqual({ top: RED });
    expect(sidesOf(next, 1, 0)).toEqual({ right: RED });
    expect(sidesOf(next, 1, 2)).toEqual({ left: RED });
    for (const [r, c] of [[0, 0], [0, 2], [2, 0], [2, 2]]) expect(sidesOf(next, r, c)).toEqual({});
  });

  it('an outer side has no neighbour to write', () => {
    const next = setCellBorder(plain(2, 2), 0, 0, 'top', RED);
    expect(sidesOf(next, 0, 0)).toEqual({ top: RED });
    expect(sidesOf(next, 1, 0)).toEqual({});
  });

  it('a merged anchor writes along its full span', () => {
    const merged = mergeCells(plain(3, 3), 1, 0, 2, 0); // column 0, rows 1-2
    const next = setCellBorder(merged, 1, 0, 'right', RED);
    expect(sidesOf(next, 1, 0).right).toEqual(RED);
    expect(sidesOf(next, 1, 1).left).toEqual(RED);
    expect(sidesOf(next, 2, 1).left).toEqual(RED);
    expect(sidesOf(next, 0, 1)).toEqual({});
  });
});
