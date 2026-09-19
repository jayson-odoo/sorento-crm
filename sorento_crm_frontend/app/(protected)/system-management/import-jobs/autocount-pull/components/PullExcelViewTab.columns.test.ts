/**
 * PullExcelViewTab - Excel view column order (AC-RV-4, X1).
 *
 * The grid itself needs `usePullRows` (react-query) plus the shared DataGrid harness to render
 * under jsdom (see `project_datagrid_jsdom_rows_mockable.md`), so this pins the column
 * DEFINITIONS directly rather than rendering the table - `PRODUCT_COLUMNS` and `STOCK_COLUMNS`
 * are not exported from `PullExcelViewTab.tsx` today.
 *
 * RED reason: importing `PRODUCT_COLUMNS` / `STOCK_COLUMNS` from the component module today
 * returns `undefined` (not exported), so `.map(...)` throws - not a missing-route defect, but
 * the SR2 contract still requires the module to expose a testable seam for this AC. The column
 * ORDER itself is already correct in Phase 1 source and should need no logic change, only the
 * `export` keyword.
 */
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { PRODUCT_COLUMNS, STOCK_COLUMNS } from './PullExcelViewTab';

/** Renders one column's `cell` renderer against a bare `{ row: { original } }` context - the
 *  smallest fixture that satisfies what these renderers actually read (`row.original`), no
 *  full table/DataGrid needed. */
function renderCell(columns: typeof PRODUCT_COLUMNS, id: string, original: unknown) {
  const column = columns.find((c) => c.id === id);
  if (!column || typeof column.cell !== 'function') {
    throw new Error(`column '${id}' has no function cell renderer`);
  }
  const Cell = column.cell as (ctx: { row: { original: unknown } }) => React.ReactElement;
  return render(Cell({ row: { original } }));
}

describe('Excel view columns - Price cell (captain ruling, Phase 3 fix round, V-5)', () => {
  it('renders a NUMBER 150 as "150.00"', () => {
    const { container } = renderCell(PRODUCT_COLUMNS, 'price', {
      item_code: 'X', description: 'X', desc_2: '', item_group: null, item_brand: null,
      price: 150, is_active: true,
    });
    expect(container.textContent).toBe('150.00');
  });

  it('renders a NUMBER 0 as "0.00"', () => {
    const { container } = renderCell(PRODUCT_COLUMNS, 'price', {
      item_code: 'X', description: 'X', desc_2: '', item_group: null, item_brand: null,
      price: 0, is_active: true,
    });
    expect(container.textContent).toBe('0.00');
  });
});

describe('Excel view columns (AC-RV-3, AC-RV-4)', () => {
  it('X1a: products columns in order Item Code, Description, Desc 2, Item Group, Item Brand, Price, Is Active', () => {
    expect(PRODUCT_COLUMNS.map((c) => c.id)).toEqual([
      'item_code',
      'description',
      'desc_2',
      'item_group',
      'item_brand',
      'price',
      'is_active',
    ]);
  });

  it('X1b: stock columns in order Item Code, Item Description, Location, On Hand Qty', () => {
    expect(STOCK_COLUMNS.map((c) => c.id)).toEqual([
      'item_code',
      'item_description',
      'location',
      'on_hand_qty',
    ]);
  });
});
