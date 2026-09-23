/**
 * AC-16 (PLAN-brand-flows-to-purchasing.md) - the brands DataGrid gets a "Purchasing"
 * column reading "Yes" / "No" from `flows_to_purchasing`.
 *
 * RED for Phase 2: `buildBrandColumns` has no such column yet - every assertion below
 * fails against TODAY's code.
 */
import { render, screen } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it } from 'vitest';
import { buildBrandColumns } from './BrandTable';
import type { Brand } from '../types/brand.types';

function brand(overrides: Partial<Brand>): Brand {
  return {
    id: 'brand-1',
    brand_code: 'ZZT-BFTP',
    brand_name: 'ZZT Test Brand',
    is_active: true,
    created_at: new Date(),
    updated_at: new Date(),
    flows_to_purchasing: true,
    ...overrides,
  } as Brand;
}

function headerTitleOf(column: unknown): string | undefined {
  return (column as { meta?: { headerTitle?: string } }).meta?.headerTitle;
}

function Table({ rows }: { rows: Brand[] }) {
  const columns = buildBrandColumns({});
  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id}>
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id} data-testid={`cell-${cell.column.id}`}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

describe('AC-16: the Purchasing column', () => {
  it('is a column with the header title "Purchasing"', () => {
    const columns = buildBrandColumns({});
    const purchasing = columns.find((c) => headerTitleOf(c) === 'Purchasing');
    expect(purchasing).toBeDefined();
  });

  it('reads "No" for a blocked brand, through the same Badge pattern as Active', () => {
    render(<Table rows={[brand({ flows_to_purchasing: false })]} />);
    const cell = screen.getByTestId('cell-purchasing');
    expect(cell).toHaveTextContent('No');
    expect(cell.querySelector('[data-slot="badge"]')).toBeInTheDocument();
  });

  it('reads "Yes" for a brand that flows to purchasing, through a Badge', () => {
    render(<Table rows={[brand({ flows_to_purchasing: true })]} />);
    const cell = screen.getByTestId('cell-purchasing');
    expect(cell).toHaveTextContent('Yes');
    expect(cell.querySelector('[data-slot="badge"]')).toBeInTheDocument();
  });
});
