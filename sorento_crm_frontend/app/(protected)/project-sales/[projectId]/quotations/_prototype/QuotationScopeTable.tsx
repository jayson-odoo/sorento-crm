'use client';

import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '../../../_shared/components/PanelDataGrid';
import { formatMyr } from '../../components/QuotationsPanel';
import { lineAmount, type MockLine, type MockScope } from './documentMocks';

/**
 * One scope's priced lines, in the column set the printed quotation actually uses.
 *
 * Three things here are not in the current editor and are the reason this screen exists:
 *
 * - **Item letters.** A water closet, its angle valve and its flexible hose are one item to
 *   the customer's QS. The letter carries that grouping; the sub-lines leave it blank rather
 *   than repeating it, exactly as the workbook does.
 * - **Bands.** `BILL NO 3 PAGE 15/4` is the customer's own bill of quantities talking. It is
 *   free text off their BQ, rendered through the shared grid's group header so a band is a
 *   property of row order and cannot drift out of sync with the lines under it.
 * - **Rate only.** A quoted alternate with no amount. It prints, and it contributes NOTHING to
 *   the total. Summing it would have overstated this sample by more than RM 400.
 *
 * The total sits in the table's own footer, under the amount column (AC-D1).
 */
export function QuotationScopeTable({
  scope,
  canEdit,
  onAddLine,
}: {
  scope: MockScope;
  canEdit: boolean;
  onAddLine?: () => void;
}) {
  const columns = React.useMemo<ColumnDef<MockLine>[]>(
    () => [
      {
        id: 'item_label',
        accessorFn: (row) => row.item_label ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Item" column={column} />,
        cell: ({ row }) => (
          <span className="text-sm font-semibold">{row.original.item_label ?? ''}</span>
        ),
        footer: () => <span className="text-muted-foreground">Total</span>,
        size: 70,
        meta: { headerTitle: 'Item' },
      },
      {
        id: 'description',
        accessorFn: (row) => row.description,
        header: ({ column }) => <DataGridColumnHeader title="Description" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm" title={row.original.description}>
            {row.original.description}
          </span>
        ),
        size: 340,
        meta: { headerTitle: 'Description' },
      },
      {
        id: 'technical_spec',
        accessorFn: (row) => row.technical_spec ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Tech spec" column={column} />,
        cell: ({ row }) =>
          row.original.technical_spec ? (
            <span className="truncate text-sm" title={row.original.technical_spec}>
              {row.original.technical_spec}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 150,
        meta: { headerTitle: 'Tech spec' },
      },
      {
        id: 'brand',
        accessorFn: (row) => row.brand ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Brand" column={column} />,
        cell: ({ row }) =>
          row.original.brand ? (
            <span className="truncate text-sm">{row.original.brand}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 110,
        meta: { headerTitle: 'Brand' },
      },
      {
        id: 'product_code',
        accessorFn: (row) => row.product_code ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Product code" column={column} />,
        cell: ({ row }) =>
          row.original.product_code ? (
            <span className="truncate text-sm font-medium">{row.original.product_code}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 140,
        meta: { headerTitle: 'Product code' },
      },
      {
        id: 'quantity',
        accessorFn: (row) => row.quantity,
        header: ({ column }) => <DataGridColumnHeader title="Qty" column={column} />,
        cell: ({ row }) => (
          <span className="text-sm tabular-nums">{row.original.quantity.toLocaleString()}</span>
        ),
        size: 90,
        meta: { headerTitle: 'Qty', cellClassName: 'text-end' },
      },
      {
        id: 'unit_rate',
        accessorFn: (row) => row.unit_rate,
        header: ({ column }) => <DataGridColumnHeader title="Unit rate" column={column} />,
        cell: ({ row }) => (
          <span className="text-sm tabular-nums">{formatMyr(String(row.original.unit_rate))}</span>
        ),
        size: 120,
        meta: { headerTitle: 'Unit rate', cellClassName: 'text-end' },
      },
      {
        id: 'complete_set',
        accessorFn: (row) => row.complete_set ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Complete set" column={column} />,
        cell: ({ row }) =>
          row.original.complete_set ? (
            <span className="truncate text-sm">{row.original.complete_set}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 130,
        meta: { headerTitle: 'Complete set' },
      },
      {
        id: 'amount',
        accessorFn: (row) => lineAmount(row) ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Amount" column={column} />,
        cell: ({ row }) => {
          const amount = lineAmount(row.original);
          // A quoted alternate says so in words. A blank cell would read as "we forgot",
          // and a zero would read as "free".
          if (amount === null) {
            return (
              <Badge variant="secondary" appearance="light" className="text-[11px]">
                rate only
              </Badge>
            );
          }
          return <span className="text-sm font-medium tabular-nums">{formatMyr(String(amount))}</span>;
        },
        /** Rate-only rows contribute zero here, which is the whole reason they are marked. */
        footer: ({ table }) =>
          formatMyr(
            String(
              table
                .getCoreRowModel()
                .rows.reduce((sum, row) => sum + (lineAmount(row.original) ?? 0), 0),
            ),
          ),
        size: 140,
        meta: { headerTitle: 'Amount', cellClassName: 'text-end' },
      },
    ],
    [],
  );

  return (
    <PanelDataGrid<MockLine>
      title={scope.label}
      toolbar={
        canEdit && onAddLine ? (
          <Button type="button" size="sm" onClick={onAddLine}>
            <Plus className="size-4" aria-hidden />
            Add a line
          </Button>
        ) : undefined
      }
      columns={columns}
      rows={scope.lines}
      getRowId={(row) => row.id}
      listingKey={`projects.projects.view::quotation-scope-lines`}
      emptyTitle="Nothing priced in this scope yet"
      emptyBody="Add the first line to start pricing it."
      searchPlaceholder="Search lines"
      searchOf={(row) => [row.description, row.product_code, row.brand].filter(Boolean).join(' ')}
      // A band heading is said once, above the row that opens it.
      renderGroupHeader={(row, previous) =>
        row.band_label && row.band_label !== previous?.band_label ? (
          <span className="font-semibold uppercase tracking-wide">{row.band_label}</span>
        ) : null
      }
      pageSize={25}
    />
  );
}
