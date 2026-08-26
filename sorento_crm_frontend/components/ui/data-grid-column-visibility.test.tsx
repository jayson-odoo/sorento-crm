/**
 * The Columns panel lists a grid's columns in DEFINITION order (every listing, app-wide).
 *
 * It used to read `getAllColumns()`, which is definition order, and was switched to
 * `getAllLeafColumns()` so a grouped column's members could be shown or hidden at all.
 * That list is in VISUAL order: it follows the user's saved column order, so on any listing
 * where somebody had dragged a column the panel silently re-sorted itself and the checkbox
 * they were looking for had moved. Both facts are asserted below.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type Table,
} from '@tanstack/react-table';

import { leafColumnsInDefinitionOrder } from './data-grid-column-visibility';

type Row = { id: string; agent: string; value: number; y1: boolean; y2: boolean };

const ROWS: Row[] = [{ id: '1', agent: 'Alice', value: 1, y1: true, y2: false }];

const COLUMNS: ColumnDef<Row>[] = [
  { accessorKey: 'agent', id: 'agent', header: 'Sales agent' },
  { accessorKey: 'value', id: 'value', header: 'Project value' },
  {
    id: 'delivery',
    header: 'Expected year of delivery',
    columns: [
      { accessorKey: 'y1', id: 'y1', header: '2026' },
      { accessorKey: 'y2', id: 'y2', header: '2027' },
    ],
  },
];

function tableWithOrder(order: string[]): Table<Row> {
  let table: Table<Row> | null = null;
  function Probe() {
    table = useReactTable({
      data: ROWS,
      columns: COLUMNS,
      getRowId: (row) => row.id,
      state: { columnOrder: order },
      onColumnOrderChange: () => {},
      getCoreRowModel: getCoreRowModel(),
    });
    return null;
  }
  render(<Probe />);
  return table as unknown as Table<Row>;
}

describe('leafColumnsInDefinitionOrder', () => {
  it('lists every leaf, group members included, in the order the grid declares them', () => {
    const table = tableWithOrder([]);

    expect(leafColumnsInDefinitionOrder(table.getAllColumns()).map((c) => c.id)).toEqual([
      'agent',
      'value',
      'y1',
      'y2',
    ]);
  });

  it('does not re-sort itself when the user has dragged a column', () => {
    const dragged = ['value', 'agent', 'y1', 'y2'];
    const table = tableWithOrder(dragged);

    // The list the panel used to read follows the drag...
    expect(table.getAllLeafColumns().map((c) => c.id)).toEqual(dragged);
    // ...and the one it reads now does not.
    expect(leafColumnsInDefinitionOrder(table.getAllColumns()).map((c) => c.id)).toEqual([
      'agent',
      'value',
      'y1',
      'y2',
    ]);
  });
});
