'use client';

import { useMemo } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { useCostingSuppliers } from '../hooks/useCosting';
import { money, percent, reasonText } from '../lib/format';
import type { CostingReason, SupplierBreakdown } from '../types/costing.types';

const RIGHT = { cellClassName: 'text-right tabular-nums', headerClassName: 'text-right' };

function Pill({ reasons }: { reasons: CostingReason[] }) {
  const reason = reasons[0];
  if (!reason) return <span className="text-muted-foreground">-</span>;
  return (
    <span className="block truncate text-xs text-muted-foreground" title={reasonText(reason)}>
      {reasonText(reason)}
    </span>
  );
}

function figure(value: number | null, reasons: CostingReason[], text = money(value)) {
  return value === null ? <Pill reasons={reasons} /> : <span>{text}</span>;
}

/**
 * A row's suppliers (AC-CG-06): what each would cost if bought there, at this view's mark-up. The
 * party view says "Margin if bought here"; the Company standard view, whose Final is the list
 * price, says "Mark-up if bought here".
 */
export function CostingSupplierGrid({
  productId,
  partyId,
  asOf,
}: {
  productId: string;
  partyId: string | null;
  asOf: string | undefined;
}) {
  const scope = useMemo(
    () => ({ ...(partyId ? { party_id: partyId } : {}), ...(asOf ? { as_of: asOf } : {}) }),
    [partyId, asOf],
  );
  const { data, isLoading, error } = useCostingSuppliers(productId, scope);

  const columns = useMemo<ColumnDef<SupplierBreakdown>[]>(
    () => [
      {
        id: 'supplier',
        accessorFn: (r) => r.supplier_code,
        header: ({ column }) => <DataGridColumnHeader title="Supplier" column={column} />,
        sortUndefined: 'last',
        cell: ({ row }) => (
          <div className="min-w-0">
            <span className="block truncate font-medium" title={row.original.supplier_code}>
              {row.original.supplier_code}
            </span>
            <span className="block truncate text-xs text-muted-foreground" title={row.original.supplier_name}>
              {row.original.supplier_name}
            </span>
          </div>
        ),
        size: 180,
      },
      {
        id: 'primary',
        accessorFn: (r) => (r.is_primary ? 1 : 0),
        header: ({ column }) => <DataGridColumnHeader title="Primary" column={column} />,
        sortUndefined: 'last',
        cell: ({ row }) => (row.original.is_primary ? 'Yes' : 'No'),
        size: 80,
      },
      {
        id: 'lead_time',
        accessorFn: (r) => r.lead_time_days ?? undefined,
        header: ({ column }) => <DataGridColumnHeader title="Lead time" column={column} />,
        sortUndefined: 'last',
        cell: ({ row }) => (row.original.lead_time_days === null ? '-' : `${row.original.lead_time_days} days`),
        size: 100,
        meta: RIGHT,
      },
      {
        id: 'cost',
        accessorFn: (r) => r.unit_cost ?? undefined,
        header: ({ column }) => <DataGridColumnHeader title="Cost" column={column} />,
        sortUndefined: 'last',
        cell: ({ row }) =>
          row.original.unit_cost === null ? (
            <span className="text-muted-foreground">-</span>
          ) : (
            <span>{`${row.original.currency ?? ''} ${money(row.original.unit_cost)}`.trim()}</span>
          ),
        size: 120,
        meta: RIGHT,
      },
      {
        id: 'landing',
        accessorFn: (r) => r.landing ?? undefined,
        header: ({ column }) => <DataGridColumnHeader title="Landing (RM)" column={column} />,
        sortUndefined: 'last',
        cell: ({ row }) => figure(row.original.landing, row.original.reasons),
        size: 140,
        meta: RIGHT,
      },
      {
        id: 'final',
        accessorFn: (r) => r.final ?? undefined,
        header: ({ column }) => <DataGridColumnHeader title="Final (RM)" column={column} />,
        sortUndefined: 'last',
        cell: ({ row }) => figure(row.original.final, row.original.reasons),
        size: 120,
        meta: RIGHT,
      },
      partyId
        ? {
            id: 'margin',
            accessorFn: (r) => r.margin_pct ?? undefined,
            header: ({ column }) => <DataGridColumnHeader title="Margin if bought here" column={column} />,
        sortUndefined: 'last',
            cell: ({ row }) =>
              row.original.margin_pct === null ? (
                <span className="text-muted-foreground">-</span>
              ) : (
                <span>{percent(row.original.margin_pct)}</span>
              ),
            size: 170,
            meta: RIGHT,
          }
        : {
            id: 'markup',
            accessorFn: (r) => r.markup_pct ?? undefined,
            header: ({ column }) => <DataGridColumnHeader title="Mark-up if bought here" column={column} />,
        sortUndefined: 'last',
            cell: ({ row }) =>
              row.original.markup_pct === null ? (
                <span className="text-muted-foreground">-</span>
              ) : (
                <span>{percent(row.original.markup_pct)}</span>
              ),
            size: 170,
            meta: RIGHT,
          },
    ],
    [partyId],
  );

  return (
    <div className="p-3" data-testid="costing-supplier-grid">
      <PanelDataGrid<SupplierBreakdown>
        columns={columns}
        rows={data?.data ?? []}
        getRowId={(row) => row.supplier_id}
        listingKey="products.cost.view::costing-suppliers"
        isLoading={isLoading}
        error={error}
        emptyTitle="No suppliers for this product"
        paginate={false}
        sortable
      />
    </div>
  );
}

export default CostingSupplierGrid;
