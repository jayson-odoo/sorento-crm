/** B review: a table whose grid does not match its rows / columns lays out without throwing. */
import { describe, expect, it } from 'vitest';

import { defaultTableProps, tableLayout } from './table-layout';

describe('tableLayout on a mismatched grid', () => {
  it('treats missing cells as empty', () => {
    const props = defaultTableProps(2, 2, 40);
    props.cells = [[props.cells[0][0]]]; // 1 row of 1 cell for a 2 x 2 grid
    const out = tableLayout(props, 40, () => 0);
    expect(out.rowHeights_mm).toHaveLength(2);
    expect(out.columnWidths_mm).toHaveLength(2);
    expect(Array.isArray(out.edges)).toBe(true);
  });

  it('ignores cells beyond the grid', () => {
    const props = defaultTableProps(1, 1, 20);
    props.cells = [[props.cells[0][0], props.cells[0][0]], [props.cells[0][0]]];
    expect(() => tableLayout(props, 20, () => 0)).not.toThrow();
  });
});
