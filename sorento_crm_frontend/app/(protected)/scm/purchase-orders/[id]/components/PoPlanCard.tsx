'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { type ColumnDef } from '@tanstack/react-table';

import { Card, CardHeader, CardHeading, CardTable, CardTitle } from '@/components/ui/card';
import { DrillTable, RIGHT } from '../../../components/PlanRowDialog';
import { EM_DASH, fmtInt } from '../../../lib/format';
import type { SpoPlan } from '../../../types/scm.types';

/**
 * The PO detail's Plan card (R1, `PLAN-scm-spo-planner-feedback-3sep.md`, AC-H7) - a `crm_spo`
 * order's own pulls and covers, read off `spo_conversion_service.plan_of`. Rendered only for
 * `po.source === 'crm'`; every other order carries no plan at all.
 *
 * Two `DrillTable`s, the shared shell every SCM lightbox/summary table already uses
 * (`PoLinePlacementsBody`'s own pattern) - "Pulled from" names the SOURCE PO line(s) this
 * SPO's own lines drew from, "Covers" names the RETAIL sales-order lines it is promised to
 * (the project half is on the order-inquiry worklist's own "Linked to" instead - `plan_of`'s
 * docstring explains why).
 */
export function PoPlanCard({ plan }: { plan: SpoPlan }) {
  const pullColumns = useMemo<ColumnDef<SpoPlan['pulls'][number]>[]>(
    () => [
      {
        id: 'po_number',
        header: 'PO number',
        cell: ({ row }) => {
          const p = row.original;
          if (!p.po_number) return <span className="text-muted-foreground">{EM_DASH}</span>;
          return p.purchase_order_id ? (
            <Link
              href={`/scm/purchase-orders/${p.purchase_order_id}`}
              className="font-medium text-primary hover:underline"
              title={`Open ${p.po_number}`}
            >
              {p.po_number}
            </Link>
          ) : (
            <span className="font-medium">{p.po_number}</span>
          );
        },
        size: 150,
      },
      {
        id: 'po_line_label',
        header: 'Product',
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.po_line_label ?? undefined}>
            {row.original.po_line_label || <span className="text-muted-foreground">{EM_DASH}</span>}
          </span>
        ),
        size: 160,
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row }) => fmtInt(row.original.qty),
        size: 90,
        meta: RIGHT,
      },
    ],
    [],
  );

  const coverColumns = useMemo<ColumnDef<SpoPlan['covers'][number]>[]>(
    () => [
      {
        id: 'so_number',
        header: 'Sales order',
        cell: ({ row }) => row.original.so_number || <span className="text-muted-foreground">{EM_DASH}</span>,
        size: 140,
      },
      {
        id: 'customer',
        header: 'Customer',
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.customer ?? undefined}>
            {row.original.customer || <span className="text-muted-foreground">{EM_DASH}</span>}
          </span>
        ),
        size: 170,
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row }) => fmtInt(row.original.qty),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'warehouse',
        header: 'Warehouse',
        cell: ({ row }) => row.original.warehouse || <span className="text-muted-foreground">{EM_DASH}</span>,
        size: 120,
      },
    ],
    [],
  );

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Plan</CardTitle>
        </CardHeading>
      </CardHeader>
      <div className="space-y-4 p-4">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Pulled from</p>
          <CardTable>
            <DrillTable
              columns={pullColumns}
              rows={plan.pulls}
              getRowId={(row, index) => `${row.purchase_order_id ?? row.po_number ?? 'pull'}-${index}`}
              emptyMessage="No PO pull recorded."
            />
          </CardTable>
        </div>
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">Covers</p>
          <CardTable>
            <DrillTable
              columns={coverColumns}
              rows={plan.covers}
              getRowId={(row, index) => `${row.so_number ?? 'cover'}-${index}`}
              emptyMessage="No sales order covered."
            />
          </CardTable>
        </div>
      </div>
    </Card>
  );
}

export default PoPlanCard;
