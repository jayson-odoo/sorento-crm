'use client';

import { useMemo } from 'react';
import { type ColumnDef } from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { DrillTable, RIGHT } from '../../../components/PlanRowDialog';
import { EM_DASH, fmtDate, fmtInt } from '../../../lib/format';
import type { PurchaseOrderLineAllocation } from '../../../types/scm.types';

/**
 * What one purchase-order line is placed on - the lightbox the "Placed" column opens (R5,
 * AC-L1/AC-L2), replacing the "Allocated to" card that used to sit under the whole grid
 * (AC-L3, captain's Lavish ruling 3 Sep: "click the line in the lines table and open the
 * lightbox popup that shows this allocation").
 *
 * Three placement kinds share one table: an SPO pull (goods already on a container), an
 * order-inquiry link (somebody's demand), and a dedication (the AutoCount book, or a person,
 * claimed the line for a sales order with nothing linked yet). `placedQtyOf` is the ONE sum
 * both this body's footer and `PurchaseOrderDetail`'s own "Placed" column read, so the two
 * numbers cannot disagree.
 *
 * NOTE (measured, R5): `PurchaseOrderPlacement` carries no purchase-order id for an `spo`
 * row (only `spo_number`), so the SPO number renders as text here, not a link - the plan
 * text assumed one. Linking it needs a backend field and is out of scope for this
 * frontend-only slice.
 */

export function placedQtyOf(allocation: PurchaseOrderLineAllocation): number {
  const fromPlacements = allocation.placements.reduce((sum, p) => sum + Number(p.qty), 0);
  const fromDedications = (allocation.dedicated_to ?? []).reduce(
    (sum, d) => sum + Number(d.unplaced),
    0,
  );
  return fromPlacements + fromDedications;
}

interface PlacementRow {
  key: string;
  kind: 'spo' | 'inquiry' | 'dedicated';
  number: string | null;
  document: string | null;
  customer: string | null;
  qty: number;
  landsAt: string | null;
  locationDiffers: boolean;
  eta: string | null;
}

function rowsFor(allocation: PurchaseOrderLineAllocation): PlacementRow[] {
  const fromPlacements = allocation.placements.map((p, index): PlacementRow => {
    if (p.kind === 'spo') {
      return {
        key: `spo-${index}`,
        kind: 'spo',
        number: p.spo_number ?? null,
        document: p.packing_list ?? null,
        customer: p.customer,
        qty: p.qty,
        landsAt:
          (p.warehouses ?? []).map((w) => `${w.warehouse_code} ${fmtInt(w.qty)}`).join(', ') ||
          null,
        locationDiffers: Boolean(p.location_differs),
        eta: p.arrival_date ? fmtDate(p.arrival_date) : null,
      };
    }
    return {
      key: `inquiry-${index}`,
      kind: 'inquiry',
      number: p.inquiry_no,
      document: p.so_number,
      customer: p.customer,
      qty: p.qty,
      landsAt: p.needed_at,
      locationDiffers: Boolean(p.location_differs),
      eta: null,
    };
  });
  const fromDedications = (allocation.dedicated_to ?? []).map(
    (d, index): PlacementRow => ({
      key: `dedicated-${index}`,
      kind: 'dedicated',
      number: null,
      document: d.so_number,
      customer: null,
      qty: d.unplaced,
      landsAt: null,
      locationDiffers: false,
      eta: null,
    }),
  );
  return [...fromPlacements, ...fromDedications];
}

function textCell(value: string | null) {
  return value ? value : <span className="text-muted-foreground">{EM_DASH}</span>;
}

export function PoLinePlacementsBody({ allocation }: { allocation: PurchaseOrderLineAllocation }) {
  const rows = useMemo(() => rowsFor(allocation), [allocation]);

  const columns = useMemo<ColumnDef<PlacementRow>[]>(
    () => [
      {
        id: 'placed_on',
        header: 'Placed on',
        cell: ({ row }) => {
          const r = row.original;
          if (r.kind === 'spo') {
            return (
              <span className="flex flex-wrap items-center gap-1.5">
                <Badge variant="info" appearance="light" size="sm">
                  SPO
                </Badge>
                <span className="font-medium">{r.number || EM_DASH}</span>
              </span>
            );
          }
          if (r.kind === 'dedicated') {
            return (
              <Badge variant="warning" appearance="light" size="sm">
                Dedicated
              </Badge>
            );
          }
          return textCell(r.number);
        },
        size: 150,
      },
      {
        id: 'document',
        header: 'Document',
        cell: ({ row }) => textCell(row.original.document),
        size: 170,
      },
      {
        id: 'customer',
        header: 'Customer',
        cell: ({ row }) => (
          <span className="block truncate" title={row.original.customer ?? undefined}>
            {textCell(row.original.customer)}
          </span>
        ),
        size: 200,
      },
      {
        id: 'qty',
        header: 'Qty',
        cell: ({ row }) => fmtInt(row.original.qty),
        size: 90,
        meta: RIGHT,
      },
      {
        id: 'lands_at',
        header: 'Lands at',
        cell: ({ row }) => {
          const r = row.original;
          return (
            <span className="flex flex-wrap items-center gap-1.5">
              <span>{r.landsAt || EM_DASH}</span>
              {r.locationDiffers ? (
                <Badge variant="warning" appearance="light" size="sm">
                  Location differs
                </Badge>
              ) : null}
            </span>
          );
        },
        size: 200,
      },
      {
        id: 'eta',
        header: 'ETA',
        cell: ({ row }) => textCell(row.original.eta),
        size: 110,
        meta: RIGHT,
      },
    ],
    [],
  );

  return (
    <div className="space-y-2">
      <DrillTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.key}
        emptyMessage="Nothing is placed on this line."
      />
      <p className="border-t pt-2 text-2xs text-muted-foreground">
        {`Outstanding ${fmtInt(allocation.outstanding)} · Placed ${fmtInt(placedQtyOf(allocation))} · Free ${fmtInt(allocation.free)}`}
      </p>
    </div>
  );
}

export default PoLinePlacementsBody;
