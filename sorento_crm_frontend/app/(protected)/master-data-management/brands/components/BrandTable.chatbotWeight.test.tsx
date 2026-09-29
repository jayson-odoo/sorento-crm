/**
 * R1 (owner console test of round 3 on PR #833, 27 Sep 2026): the Brands list shows each
 * brand's chatbot weight, so the ranking the chatbot answers by is readable at a glance.
 */
import { render, screen } from '@testing-library/react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { describe, expect, it } from 'vitest';
import { buildBrandColumns } from './BrandTable';
import type { Brand } from '../types/brand.types';

function brand(overrides: Partial<Brand>): Brand {
  return {
    id: 'brand-1',
    brand_code: 'ZZT-BCW',
    brand_name: 'ZZT Test Brand',
    is_active: true,
    created_at: new Date(),
    updated_at: new Date(),
    flows_to_purchasing: true,
    chatbot_weight: 0,
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

describe('R1: the Chatbot weight column', () => {
  it('is a sized column with the header title "Chatbot weight"', () => {
    const column = buildBrandColumns({}).find((c) => headerTitleOf(c) === 'Chatbot weight');
    expect(column).toBeDefined();
    expect(column?.size).toBeGreaterThan(0);
  });

  it('reads the stored weight', () => {
    render(<Table rows={[brand({ chatbot_weight: 1.5 })]} />);
    expect(screen.getByTestId('cell-chatbot_weight')).toHaveTextContent('1.5');
  });

  it('reads 0 for an unweighted brand', () => {
    render(<Table rows={[brand({ chatbot_weight: 0 })]} />);
    expect(screen.getByTestId('cell-chatbot_weight')).toHaveTextContent('0');
  });
});
