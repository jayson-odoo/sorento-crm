/**
 * SPEC-SHEET-PARITY-B2 v3 editor, AC-C5.1 / AC-C5.3: a row's height is a MINIMUM that holds when its
 * cells are empty (the tall blank COMMENT row of the owner's title block) and grows only when the
 * text needs more. Pinned on the one layout module canvas, print and PowerPoint share.
 */
import { describe, expect, it } from 'vitest';

import type { TableLayerProps } from './tag-template-types';
import { tableLayout, tableMeasure } from './table-layout';

const GREEN = { color: '#3f7d3a', width_mm: 0.2 };
const cell = (text: string) => ({
  text,
  padding_mm: 1,
  border: { top: GREEN, right: GREEN, bottom: GREEN, left: GREEN },
});

/** The owner's right-edge title block (mock section I): one column, 7 rows. */
function titleBlock(): TableLayerProps {
  return {
    kind: 'table',
    columns: [{ width_mm: 50 }],
    rows: [80, 8, 8, 8, 8, 8, 40].map((height_mm) => ({ height_mm })),
    cells: [
      [cell('{{doc.subject_title}}')],
      [cell('REF : {{doc.ref}}')],
      [cell('AREA : {{line.area}}')],
      [cell('PREPARED BY : {{doc.prepared_by}} {{doc.prepared_by_phone}}')],
      [cell('DATE : {{doc.date}}')],
      [cell('COMMENT :')],
      [cell('')],
    ],
    fontFamily: 'Arial',
    fontSize: 8,
    color: '#000000',
    align: 'left',
    verticalAlign: 'top',
    uppercase: true,
  } as TableLayerProps;
}

describe('table rows keep their set height (AC-C5.1)', () => {
  it('an empty row keeps its height_mm', () => {
    const props = titleBlock();
    const layout = tableLayout(props, 50, tableMeasure(props));
    expect(layout.rowHeights_mm[6]).toBe(40);
    expect(layout.rowHeights_mm[0]).toBe(80);
  });

  it('the title block lays out as 7 rows in one column, at least the set heights', () => {
    const props = titleBlock();
    const layout = tableLayout(props, 50, tableMeasure(props));
    expect(layout.columnWidths_mm).toEqual([50]);
    expect(layout.rowHeights_mm).toHaveLength(7);
    props.rows.forEach((row, i) => expect(layout.rowHeights_mm[i]).toBeGreaterThanOrEqual(row.height_mm));
  });

  it('a row grows only when its text needs more than the set height', () => {
    const props = titleBlock();
    props.rows[5] = { height_mm: 2 };
    props.cells[5][0] = cell('COMMENT : ' + 'long words '.repeat(40));
    const layout = tableLayout(props, 50, tableMeasure(props));
    expect(layout.rowHeights_mm[5]).toBeGreaterThan(2);
    expect(layout.rowHeights_mm[6]).toBe(40);
  });
});
