/**
 * Move to Left/Right's underlying logic (S4, M5 review run 1).
 *
 * `moveColumn`/`canMove` in `data-grid-column-header.tsx` read
 * `table.getState().columnOrder` raw. TanStack initialises that to `[]` until a caller
 * sets it explicitly, which most grids never do (`useListingColumnPreferences` only calls
 * `setColumnOrder` once personalization loads) - so `indexOf(column.id)` was `-1` on every
 * column, and Move to Left/Right read as permanently disabled on the ~200 grids without
 * column-order state.
 *
 * This is a logic-level test, not a render-and-click one, for a reason worth recording:
 * the menu that holds these buttons (`headerControls` in that file) is not currently
 * mounted anywhere - `DataGridColumnHeader`'s own render path only ever returns
 * `headerButton()` (sorting) or `headerLabel()`, and `headerControls` is referenced only
 * via `void headerControls;` to keep it from tripping the unused-var lint. That predates
 * this fix (`63b93d74b`, "personalized columns", 26 Mar 2026: "we currently render only
 * sorting") and re-wiring it into the render tree - a settings icon and dropdown on every
 * column header, across roughly 200 grids - is a separate, materially bigger change than
 * this bug fix. So `canMoveColumnInOrder`/`moveColumnInOrder` are exported for a direct
 * unit test instead of exercising them through a menu that does not render.
 */
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useReactTable, getCoreRowModel, type ColumnDef } from '@tanstack/react-table';

import { canMoveColumnInOrder, moveColumnInOrder } from './data-grid-column-header';
import { mergeColumnOrderWithLeafColumns } from '@/lib/listing-column-preferences/mergeColumnOrder';

describe('canMoveColumnInOrder / moveColumnInOrder', () => {
  const ORDER = ['a', 'b', 'c'];

  it('the first column cannot move left, and the last cannot move right', () => {
    expect(canMoveColumnInOrder(ORDER, 'a', 'left')).toBe(false);
    expect(canMoveColumnInOrder(ORDER, 'c', 'right')).toBe(false);
  });

  it('the first column can move right, and the last can move left', () => {
    expect(canMoveColumnInOrder(ORDER, 'a', 'right')).toBe(true);
    expect(canMoveColumnInOrder(ORDER, 'c', 'left')).toBe(true);
  });

  it('a middle column can move either way', () => {
    expect(canMoveColumnInOrder(ORDER, 'b', 'left')).toBe(true);
    expect(canMoveColumnInOrder(ORDER, 'b', 'right')).toBe(true);
  });

  it('a column not in the order cannot move', () => {
    expect(canMoveColumnInOrder(ORDER, 'ghost', 'left')).toBe(false);
    expect(canMoveColumnInOrder(ORDER, 'ghost', 'right')).toBe(false);
  });

  it('moves a column one step left or right', () => {
    expect(moveColumnInOrder(ORDER, 'b', 'left')).toEqual(['b', 'a', 'c']);
    expect(moveColumnInOrder(ORDER, 'b', 'right')).toEqual(['a', 'c', 'b']);
  });

  it('is a no-op past either edge, returning the SAME array reference', () => {
    expect(moveColumnInOrder(ORDER, 'a', 'left')).toBe(ORDER);
    expect(moveColumnInOrder(ORDER, 'c', 'right')).toBe(ORDER);
  });
});

type Row = { id: string; a: string; b: string; c: string };

const COLUMNS: ColumnDef<Row>[] = [
  { id: 'a', accessorKey: 'a', header: 'A', size: 100 },
  { id: 'b', accessorKey: 'b', header: 'B', size: 100 },
  { id: 'c', accessorKey: 'c', header: 'C', size: 100 },
];

const ROWS: Row[] = [{ id: '1', a: 'x', b: 'y', c: 'z' }];

describe('the S4 bug, reproduced against a real table with no columnOrder state', () => {
  it('table.getState().columnOrder starts empty', () => {
    const { result } = renderHook(() =>
      useReactTable({
        columns: COLUMNS,
        data: ROWS,
        getRowId: (r) => r.id,
        getCoreRowModel: getCoreRowModel(),
      }),
    );
    expect(result.current.getState().columnOrder).toEqual([]);
  });

  it('reading that raw state directly disables every Move button (the bug)', () => {
    const { result } = renderHook(() =>
      useReactTable({
        columns: COLUMNS,
        data: ROWS,
        getRowId: (r) => r.id,
        getCoreRowModel: getCoreRowModel(),
      }),
    );
    const rawOrder = result.current.getState().columnOrder as string[];
    // -1 for every column: this is what made every "Move to Left/Right" read as disabled.
    expect(rawOrder.indexOf('a')).toBe(-1);
    expect(canMoveColumnInOrder(rawOrder, 'a', 'right')).toBe(false);
  });

  it('falling back to leaf ids (the DnD handler\'s own pattern) fixes it', () => {
    const { result } = renderHook(() =>
      useReactTable({
        columns: COLUMNS,
        data: ROWS,
        getRowId: (r) => r.id,
        getCoreRowModel: getCoreRowModel(),
      }),
    );
    const table = result.current;
    const columnOrderState = table.getState().columnOrder as string[] | undefined;
    const leafIds = table.getAllLeafColumns().map((c) => c.id);
    const rawOrder =
      Array.isArray(columnOrderState) && columnOrderState.length > 0 ? columnOrderState : leafIds;
    const effectiveOrder = mergeColumnOrderWithLeafColumns(rawOrder, leafIds);

    expect(effectiveOrder).toEqual(['a', 'b', 'c']);
    // The first column: Move to Right is enabled, Move to Left is not.
    expect(canMoveColumnInOrder(effectiveOrder, 'a', 'right')).toBe(true);
    expect(canMoveColumnInOrder(effectiveOrder, 'a', 'left')).toBe(false);
    // The last column: the reverse.
    expect(canMoveColumnInOrder(effectiveOrder, 'c', 'left')).toBe(true);
    expect(canMoveColumnInOrder(effectiveOrder, 'c', 'right')).toBe(false);
    // And clicking it reorders.
    expect(moveColumnInOrder(effectiveOrder, 'a', 'right')).toEqual(['b', 'a', 'c']);
  });
});
